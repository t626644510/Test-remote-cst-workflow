"""Owned CST worker. Lifecycle adapted from WF5, shared core is never copied.

Only verified CST wrappers, template history and WF5/QFactor VBA are used.
Importing this module does not import CST. Geometry mm, frequencies Hz.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict
import json, logging, math, re, time
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4
import numpy as np
from .config import Config
from .geometry import Geometry
from .io import atomic_json, copy_verified_project, digest, fingerprint
from .session_recovery import query_pid, ensure_sessions_inactive
from .thermal import losses_vba, voltage_vba, analyze_thermal
from .completion import validate_completion, legacy_messages

LOG=logging.getLogger(__name__)

class EvaluationFailure(RuntimeError):
    def __init__(self, message: str, category: str='solver_failed'):
        super().__init__(message); self.category=category


def validate_wake_tail(s_m: np.ndarray, requested_m: float) -> dict:
    """Allow one sampling cell at a completed wake endpoint, without padding.

    Distances are metres. CST may place its last sample just below the requested
    length despite completing every planned time step (checked separately).
    Bound the allowance by both the typical and final cell, capped at 0.01%
    of the requested tail; a sparse or enlarged final gap cannot hide truncation.
    """
    s=np.asarray(s_m,float)
    if s.ndim!=1 or len(s)<2 or not np.isfinite(s).all() or np.any(np.diff(s)<=0):
        raise ValueError('Invalid saved wake sample axis')
    steps=np.diff(s)
    tolerance=max(1e-5,min(float(np.median(steps)),float(steps[-1]),requested_m*1e-4)+1e-9)
    if s[-1]<requested_m-tolerance:
        raise ValueError('Saved wake does not cover the full configured tail')
    return dict(requested_m=requested_m,last_sample_m=float(s[-1]),endpoint_tolerance_m=tolerance,
                sample_count=len(s),endpoint_shortfall_m=max(0.,float(requested_m-s[-1])))

def metadata(path: Path) -> dict:
    root=path.with_suffix('')
    h=json.loads((root/'Model/3D/ModelHistory.json').read_text(encoding='utf-8-sig'))
    p=json.loads((root/'Model/Parameters.json').read_text(encoding='utf-8-sig'))
    return dict(general=h['general'], history=h['history'], parameters={x['name']:float(x['value']) for x in p['parameters']})

def effective_settings(path: Path, stage: str, config: Config) -> dict:
    info=metadata(path); general=info['general']; freq=general['frequency']
    if general['length']!='mm' or freq['unit']!=config.results.frequency_unit:
        raise EvaluationFailure('Template/result units disagree','settings_failed')
    factor={'Hz':1.,'MHz':1e6,'GHz':1e9}[freq['unit']]
    lo,hi=float(freq['minimum'])*factor,float(freq['maximum'])*factor
    band=config.physics.thermal_band_hz if stage=='thermal' else config.physics.band_hz
    if lo>band[0]+1 or hi<band[1]-1:
        raise EvaluationFailure(f'Actual frequency range {lo,hi} does not cover {band}','settings_failed')
    blocks=['\n'.join(row.get('code',[])) for row in info['history']]
    if stage!='thermal':
        beams=[b for b in blocks if 'With ParticleBeam' in b and '.Create' in b]
        if not beams:raise EvaluationFailure('Missing beam settings','settings_failed')
        beam=beams[-1]
        def field(name):
            match=re.search(r'\.'+name+r'\s+([^\r\n]+)',beam)
            if not match:raise EvaluationFailure('Missing beam property '+name,'settings_failed')
            return re.findall(r'"([^"]*)"',match[1])
        position=list(map(float,field('BeamPoint')[1:]));shift=list(map(float,field('WakeIntegrationShift')))
        expected={'axis':[0,0,0],'x':[config.physics.offset_m*1000,0,0],'y':[0,config.physics.offset_m*1000,0]}[stage]
        if not np.allclose(position,expected,rtol=0,atol=1e-9) or not np.allclose(np.add(position,shift),0,rtol=0,atol=1e-9):
            raise EvaluationFailure('Source offset or on-axis witness mismatch','settings_failed')
        if float(field('Length')[0])!=config.physics.sigma_m*1000 or float(field('Beta')[0])!=1 or field('IsBunchGaussian')[0].lower()!='true':
            raise EvaluationFailure('Bunch length, shape or beta mismatch','settings_failed')
        length=re.findall(r'\.WakeLength\s+"([^"]+)"','\n'.join(blocks))
        if not length or float(length[-1])!=config.physics.wake_length_m*1000:raise EvaluationFailure('Wake length mismatch','settings_failed')
    return {'frequency_hz':[lo,hi], 'general':general, 'parameters':info['parameters']}

def result_fingerprint(path: Path) -> dict:
    files=[path,path.with_suffix('')/'Model/Parameters.json']
    files+=sorted(p for p in (path.with_suffix('')/'Result').rglob('*') if p.is_file() and p.suffix.lower() not in ('.lok','.lock'))
    return {str(p.relative_to(path.parent)):digest(p) for p in files if p.is_file()}

class CSTWorker:
    """One isolated stage. Re-entry of a solved task performs extraction only."""
    def __init__(self, config: Config): self.config=config

    def run(self, task: dict) -> dict:
        """Solve once, or extract already-saved results without another solve."""
        directory=Path(task['directory']); directory.mkdir(parents=True,exist_ok=True)
        ensure_sessions_inactive(directory.parent)
        path=directory/'project'/Path(task['template']).name
        stage=task['stage']; raw=directory/'raw'; raw.mkdir(exist_ok=True)
        mapping=Geometry(self.config).expand(task['parameters'])
        if stage!='thermal': mapping.update(zip(self.config.runtime.port_parameters,task['ports']))
        solved=directory/'solved.json'
        if solved.exists():
            proof=json.loads(solved.read_text())
            if proof['identity']!=task['identity'] or proof['files']!=result_fingerprint(path):
                raise EvaluationFailure('Saved solve evidence changed','identity_failed')
        else:
            if (directory/'solve_started.json').exists():
                raise EvaluationFailure('Interrupted solve has no saved success; no implicit repeat','interrupted')
            if path.exists():
                raise EvaluationFailure('Interrupted preparation requires a new explicit attempt','interrupted')
            copy_verified_project(Path(task['template']),directory/'project')
            with self._project(path,directory,'prepare') as project:
                if not project.update_parameters(mapping,use_full_rebuild=True):
                    raise EvaluationFailure('Full geometry rebuild rejected','geometry_failed')
                if not project.save(include_results=False):
                    raise EvaluationFailure('Cannot save rebuilt candidate','save_failed')
            actual=metadata(path)['parameters']
            if any(not math.isclose(actual[k],v,rel_tol=1e-10,abs_tol=1e-8) for k,v in mapping.items()):
                raise EvaluationFailure('Rebuilt parameter mismatch','identity_failed')
            with self._project(path,directory,'solve') as project:
                # Commands below are recorded in these user templates / verified WF5.
                unit=metadata(path)['general']['frequency']['unit']
                factor={'Hz':1.,'MHz':1e6,'GHz':1e9}[unit]
                if stage=='thermal':
                    lo,hi=self.config.physics.thermal_band_hz
                    code='\n'.join(['ChangeSolverType "HF Eigenmode"',
                        f'Solver.FrequencyRange "{lo/factor:.16g}", "{hi/factor:.16g}"',
                        f'EigenmodeSolver.SetAccuracy "{self.config.physics.eigen_accuracy:.15g}"',f'EigenmodeSolver.SetQExternalAccuracy "{self.config.physics.external_q_accuracy:.15g}"'])
                else:
                    # Explicit effective range survives obsolete history expressions.
                    hi=self.config.physics.band_hz[1]
                    code='\n'.join(['ChangeProblemType "Wakefield Solver"',
                        f'Solver.FrequencyRange "0", "{hi/factor:.16g}"',
                        f'Solver.WakeLength "{self.config.physics.wake_length_m*1000:.16g}"'])
                project.execute_vba(code,header='WF6 effective solver settings',timeout=180.)
                if not project.save(include_results=False): raise EvaluationFailure('Settings save failed','save_failed')
                atomic_json(directory/'effective_settings.json',effective_settings(path,stage,self.config))
                log=path.with_suffix('')/'Result/Model.log'
                before=log.read_text(errors='replace') if log.exists() else ''
                messages_before=project.get_messages()
                from cst_optimization.core.solver import SolverRunner
                atomic_json(directory/'solve_started.json',dict(identity=task['identity'],started_ns=time.time_ns()))
                result=SolverRunner(timeout_s=self.config.runtime.stage_timeout_s,settle_s=2.).run(project)
                atomic_json(directory/'solver_result.json',asdict(result))
                records=project.get_messages()
                fresh=log.read_text(errors='replace') if log.exists() else ''
                if before and fresh.startswith(before):fresh=fresh[len(before):]
                if messages_before and records[:len(messages_before)]==messages_before:records=records[len(messages_before):]
                atomic_json(directory/'messages.json',records)
                messages=str(records)
                (directory/'messages.txt').write_text(messages,encoding='utf-8')
                (directory/'Model.log').write_text(fresh,encoding='utf-8')
                if not result.success: raise EvaluationFailure((result.error_message or '')+'\n'+messages+'\n'+fresh)
                start=json.loads((directory/'solve_started.json').read_text())
                try:proof=validate_completion(stage,asdict(result),fresh,records,start['started_ns'])
                except ValueError as exc:raise EvaluationFailure(str(exc)+'\n'+messages+'\n'+fresh) from exc
                atomic_json(directory/'completion.json',proof)
                if not project.save(include_results=True):raise EvaluationFailure('Result save failed','save_failed')
            atomic_json(solved,dict(identity=task['identity'],files=result_fingerprint(path)))
        try:
            result=self._extract(path,directory,stage,task)
        except Exception as exc:
            raise EvaluationFailure(str(exc),'postprocess_failed') from exc
        return dict(status='complete',stage=stage,project=str(path),raw=str(raw),identity=task['identity'],result=result)

    def recover_saved_wake(self, task: dict) -> dict:
        """Export a completed archived wake without opening CST or repeating a solve.

        Explicit operator entry point for legacy completion-recognition failures.
        Validate ownership, identity, settings, fresh full-tail log and raw curves
        before certifying. Original failure files and native results stay intact.
        """
        from .supervision import check_recovery
        directory=Path(task['directory']);check_recovery(directory)
        if task['stage'] not in ('axis','x','y'):raise ValueError('Saved recovery supports wake stages only')
        archived=json.loads((directory/'task.json').read_text())
        for key in ('identity','directory','template','parameters','ports','stage'):
            if archived[key]!=task[key]:raise ValueError('Archived task identity mismatch: '+key)
        start=json.loads((directory/'solve_started.json').read_text())
        if start['identity']!=task['identity']:raise ValueError('Solve-start identity mismatch')
        path=directory/'project'/Path(task['template']).name
        actual=effective_settings(path,task['stage'],self.config)
        expected=Geometry(self.config).expand(task['parameters'])
        expected.update(zip(self.config.runtime.port_parameters,task['ports']))
        if any(k not in actual['parameters'] or not math.isclose(actual['parameters'][k],v,rel_tol=1e-10,abs_tol=1e-8) for k,v in expected.items()):
            raise ValueError('Saved physical parameters or port lengths mismatch')
        if actual!=json.loads((directory/'effective_settings.json').read_text()):raise ValueError('Saved effective settings changed')
        log=(directory/'Model.log').read_text(errors='replace')
        native_log=(path.with_suffix('')/'Result/Model.log').read_text(errors='replace')
        if not native_log.endswith(log):raise ValueError('Archived log no longer matches native results')
        records=legacy_messages((directory/'messages.txt').read_text(encoding='utf-8'))
        proof=validate_completion(task['stage'],json.loads((directory/'solver_result.json').read_text()),log,records,start['started_ns'])
        files=result_fingerprint(path)
        if (directory/'solved.json').exists():
            prior=json.loads((directory/'solved.json').read_text())
            if prior['identity']!=task['identity'] or prior['files']!=files:raise ValueError('Saved certificate changed')
        (directory/'raw').mkdir(exist_ok=True)
        result=self._extract(path,directory,task['stage'],task)
        if files!=result_fingerprint(path):raise ValueError('Native results changed during read-only extraction')
        atomic_json(directory/'recovered_completion.json',dict(proof,identity=task['identity'],files=files,
            recovered_at_ns=time.time_ns(),new_solver_calls=0))
        atomic_json(directory/'solved.json',dict(identity=task['identity'],files=files,recovered=True))
        outcome=dict(status='complete',stage=task['stage'],project=str(path),raw=str(directory/'raw'),identity=task['identity'],result=result)
        atomic_json(directory/'worker_result_recovered.json',outcome)
        return outcome

    def recover_saved_thermal(self,task:dict)->dict:
        """Recover metal losses from a completed eigenmode on an isolated copy.

        The native source is immutable. QFactor/field export may create derived
        results in the copy, but this method never invokes an eigenmode solver.
        """
        from .supervision import check_recovery
        source_dir=Path(task['directory']);check_recovery(source_dir)
        archived=json.loads((source_dir/'task.json').read_text())
        for key in ('identity','directory','template','parameters','ports','stage'):
            if archived[key]!=task[key]:raise ValueError('Archived task identity mismatch: '+key)
        if task['stage']!='thermal':raise ValueError('Thermal task required')
        source=source_dir/'project'/Path(task['template']).name
        actual=effective_settings(source,'thermal',self.config)
        expected=Geometry(self.config).expand(task['parameters'])
        if any(not math.isclose(actual['parameters'][k],v,rel_tol=1e-10,abs_tol=1e-8) for k,v in expected.items()):
            raise ValueError('Saved thermal parameter mismatch')
        if actual!=json.loads((source_dir/'effective_settings.json').read_text()):raise ValueError('Saved thermal settings changed')
        start=json.loads((source_dir/'solve_started.json').read_text())
        if start['identity']!=task['identity']:raise ValueError('Thermal solve identity mismatch')
        log=(source_dir/'Model.log').read_text(errors='replace')
        if not (source.with_suffix('')/'Result/Model.log').read_text(errors='replace').endswith(log):
            raise ValueError('Thermal native log changed')
        proof=validate_completion('thermal',json.loads((source_dir/'solver_result.json').read_text()),log,
            json.loads((source_dir/'messages.json').read_text()),start['started_ns'])
        before=result_fingerprint(source)
        target=source_dir/'thermal_recovery'
        marker=target/'recovery_source.json'
        if target.exists():
            if not marker.exists() or json.loads(marker.read_text())!=dict(identity=task['identity'],files=before):
                raise ValueError('Recovery copy belongs to different source')
            ensure_sessions_inactive(source_dir)
            for session in target.glob('*_session.json'):
                pid=json.loads(session.read_text()).get('pid')
                if pid and query_pid(pid)!='absent':raise ValueError('Prior thermal extraction still active')
        else:
            target.mkdir();atomic_json(marker,dict(identity=task['identity'],files=before))
            copy_verified_project(source,target/'project')
        (target/'raw').mkdir(exist_ok=True)
        copy=target/'project'/source.name
        result=self._extract(copy,target,'thermal',task)
        if before!=result_fingerprint(source):raise ValueError('Original thermal result changed during recovery')
        outcome=dict(status='complete',stage='thermal',project=str(copy),raw=str(target/'raw'),identity=task['identity'],result=result)
        atomic_json(target/'recovered_completion.json',dict(proof,identity=task['identity'],source_files=before,new_solver_calls=0))
        atomic_json(target/'worker_result_recovered.json',outcome)
        return outcome

    def _extract(self,path: Path,directory: Path,stage: str,task: dict) -> dict:
        from cst_optimization.core import init_cst_path
        from cst_optimization.core.results import ResultReader
        init_cst_path(self.config.paths.cst_library_path)
        reader=ResultReader(str(path),allow_interactive=False,cache_project_file=False)
        raw=directory/'raw'; tree=reader.list_tree_items()
        atomic_json(raw/'tree.json',tree)
        if stage=='thermal':
            pattern=re.compile(re.escape(self.config.results.eigen_frequency).replace(re.escape('{mode}'),r'(\d+)'))
            modes=[]; factor={'Hz':1.,'MHz':1e6,'GHz':1e9}[self.config.results.frequency_unit]
            for item in tree:
                m=pattern.fullmatch(item)
                if m:
                    data=np.asarray(reader.get_result_item(item).get_ydata()).reshape(-1)
                    if len(data)!=1 or not np.isfinite(data).all():raise ValueError('Invalid eigenfrequency')
                    f=float(data[0].real)*factor
                    if self.config.physics.thermal_band_hz[0]<=f<=self.config.physics.thermal_band_hz[1]:modes.append((int(m[1]),f))
            if len(modes)!=1:raise ValueError('Working mode not uniquely identified inside configured band')
            mode,f=modes[0]
            with self._project(path,directory,'extract') as project:
                for name,macro in [('losses',losses_vba(mode,raw/'losses.txt',self.config.physics)),
                                   ('voltage',voltage_vba(mode,raw/'voltage.csv',self.config.physics))]:
                    (raw/(name+'.bas')).write_text(macro,encoding='utf-8')
                    project.project.schematic.execute_vba_code(macro,timeout=self.config.runtime.postprocess_timeout_s)
            result=analyze_thermal(raw,f,self.config.physics)
            result['mode']=mode
        else:
            arrays={}; labels={}; axes=[]; waves=[]
            factor={'mm':.001,'m':1.,'ns':.299792458}[self.config.results.wake_x_unit]
            for axis in 'XYZ':
                itempath=self.config.results.wake.format(beam=self.config.results.beam,axis=axis)
                item=reader.get_result_item(itempath)
                s=np.asarray(item.get_xdata(),float)*factor; w=np.asarray(item.get_ydata())
                if w.ndim!=1 or np.iscomplexobj(w) and np.any(w.imag!=0) or len(s)!=len(w):raise ValueError('Invalid signed wake curve')
                axes.append(s);waves.append(w.real)
                labels[axis]=dict(path=itempath,xlabel=str(item.xlabel),ylabel=str(item.ylabel))
                ylabel=str(item.ylabel).replace(' ','').lower()
                if ylabel and 'v/pc' not in ylabel:raise ValueError('Wake ordinate label contradicts configured V/pC units: '+ylabel)
                impath=self.config.results.impedance.format(beam=self.config.results.beam,axis=axis)
                imp=reader.get_result_item(impath)
                f=np.asarray(imp.get_xdata(),float)*{'Hz':1.,'MHz':1e6,'GHz':1e9}[self.config.results.frequency_unit]
                z=np.asarray(imp.get_ydata(),complex)
                if len(f)<2 or f[0]>self.config.physics.band_hz[0] or f[-1]<self.config.physics.band_hz[1]-1:
                    raise ValueError('Native impedance does not cover the full objective band')
                arrays['frequency_'+axis]=f;arrays['impedance_'+axis]=z
            if any(not np.array_equal(axes[0],s) for s in axes[1:]):raise ValueError('Wake components use different sample axes')
            arrays.update(s_m=axes[0],wake=np.column_stack(waves))
            tail_coverage=validate_wake_tail(axes[0],self.config.physics.wake_length_m)
            charge=reader.get_result_item(self.config.results.charge.format(beam=self.config.results.beam))
            charge_label=str(charge.xlabel).replace(' ','').lower()
            charge_factor={'mm':.001,'m':1.}.get(charge_label.rsplit('/',1)[-1])
            if charge_factor is None:raise ValueError('Charge distribution must have an explicit distance axis, mm or m')
            arrays['charge_s_m']=np.asarray(charge.get_xdata(),float)*charge_factor
            arrays['charge_density']=np.asarray(charge.get_ydata(),float)
            cs=arrays['charge_s_m'];rho=np.abs(arrays['charge_density'])
            area=np.trapz(rho,cs)
            if area<=0 or not np.isfinite(area):raise ValueError('Invalid saved bunch distribution')
            mean=np.trapz(rho*cs,cs)/area
            sigma=np.sqrt(np.trapz(rho*(cs-mean)**2,cs)/area)
            if not math.isclose(sigma,self.config.physics.sigma_m,rel_tol=.02):raise ValueError('Saved bunch RMS disagrees with configured sigma')
            if any(not np.isfinite(v).all() for v in arrays.values()):raise ValueError('Nonfinite raw result')
            np.savez_compressed(raw/'curves.npz',**arrays)
            result=dict(status='valid',ports=task['ports'],parameters=task['parameters'],stage=stage,
                units={'s_m':'m','wake':'V/pC','frequency':'Hz','impedance':'ohm'},paths=labels,identity=task['identity'],sigma_m=float(sigma),tail_coverage=tail_coverage)
        atomic_json(raw/'bundle.json',result)
        atomic_json(raw/'manifest.json',{p.name:digest(p) for p in raw.iterdir() if p.is_file() and p.name!='manifest.json'})
        return result

    @contextmanager
    def _project(self, path: Path, directory: Path, phase: str) -> Iterator[Any]:
        # Lazy imports: config, offline analysis and all pure numerical code need no CST.
        from cst_optimization.core.connection import CSTConnection
        project, pid, connection = None, None, None
        connect_started = False
        primary_error = None
        session = {"session_id": str(uuid4()), "pid": None,
                   "project": str(path.resolve()), "phase": "opening"}
        session_path = directory / f"{phase}_session.json"
        # Persist BEFORE any operation that can create a DesignEnvironment.
        atomic_json(session_path, session)
        try:
            connection = CSTConnection(library_path=self.config.paths.cst_library_path, mode="new")
            connect_started = True
            connection.connect()
            pid = connection.pid
            from .supervision import process_birth
            session.update(pid=pid, phase="active", process_birth=process_birth(pid))
            atomic_json(session_path, session)
            if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                raise EvaluationFailure("Owned CST PID could not be recorded", "cleanup_failed")
            project = connection.open_project(str(path))
            project.activate()
            if Path(project.filename).resolve() != path.resolve():
                raise EvaluationFailure("CST opened an unexpected project", "ownership_failed")
            yield project
        except BaseException as exc:
            primary_error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            # A failed connect may nevertheless have created its own DE and PID.
            # Recover only this connection's PID; never infer one from other processes.
            if (isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0) and connection is not None and connect_started:
                try:
                    recovered_pid = connection.pid
                except Exception:
                    recovered_pid = None
                if isinstance(recovered_pid, int) and not isinstance(recovered_pid, bool) and recovered_pid > 0:
                    pid = recovered_pid
                    session.update(pid=pid, phase="cleanup")
                    try:
                        atomic_json(session_path, session)
                    except Exception:
                        LOG.exception("Could not persist recovered owned PID; still attempting targeted cleanup")
            close_error = None
            try:
                if project is not None:
                    project.close(save=False)
            except BaseException as exc:
                close_error = exc
            finally:
                # This runs even if project.close raises. Never use generic close.
                result = {"success": False, "exit_verified": False}
                if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 and connection is not None:
                    try:
                        result = connection.close_targeted(pid_override=pid)
                    except Exception as exc:
                        result["error"] = f"{type(exc).__name__}: {exc}"
                    # Shared close_targeted uses tasklist. Independently verify exact
                    # PID absence before issuing a trustworthy cleanup certificate.
                    try:
                        pid_state = query_pid(pid)
                    except Exception:
                        pid_state = "unknown"
                    result["pid_state"] = pid_state
                    result["exit_verified"] = pid_state == "absent"
                    result["success"] = bool(result.get("success")) and pid_state == "absent"
                elif not connect_started:
                    result.update(success=True, no_session_started=True)
                else:
                    result["error"] = "Connection started without a recorded owned PID"
                result.update(session_id=session["session_id"], pid=pid, project=session["project"])
                if primary_error is not None:
                    result["primary_error"] = primary_error
                if close_error is not None:
                    result["project_close_error"] = f"{type(close_error).__name__}: {close_error}"
                atomic_json(directory / f"{phase}_cleanup.json", result)
            if not result.get("success"):
                raise EvaluationFailure(f"Owned session cleanup failed: {result}", "cleanup_failed")
            if close_error is not None:
                if isinstance(close_error, (KeyboardInterrupt, SystemExit)):
                    raise close_error
                raise EvaluationFailure(f"Project close failed; owned process cleanup completed: {close_error}", "project_close_failed") from close_error

