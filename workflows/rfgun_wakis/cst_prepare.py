"""Owned-copy CST geometry/matrix preparation, with bounded process cleanup.

CST length units are mm and frequency units MHz. The field solve is stopped
after its FIT matrices are written; its discarded transient is never reported
as a completed wake. Only subsequent Wakis solves provide objective data.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from pathlib import Path
import json,math,shutil,threading,time,traceback
from .config import Config
from .geometry import Geometry
from .cad import parameters,port_faces
from .io import atomic_json,digest

@dataclass(frozen=True)
class ProcessIdentity:
    """PID plus creation timestamp and command prevent reuse-based cleanup."""
    pid: int
    parent: int
    created: float
    command: tuple[str,...]

    @classmethod
    def read(cls,pid: int) -> 'ProcessIdentity':
        import psutil
        p=psutil.Process(pid)
        return cls(p.pid,p.ppid(),p.create_time(),tuple(p.cmdline()))

    def alive(self) -> bool:
        import psutil
        try:
            if self!=self.read(self.pid) or not psutil.Process(self.pid).is_running():return False
            # Windows may retain an exited process object while another handle
            # is open. A signaled kernel handle is authoritative, unlike PID
            # enumeration alone. This does not attach to a CST project.
            import os
            if os.name=='nt':
                import ctypes
                from ctypes import wintypes
                kernel=ctypes.WinDLL('kernel32',use_last_error=True)
                kernel.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
                kernel.OpenProcess.restype=wintypes.HANDLE
                kernel.WaitForSingleObject.argtypes=(wintypes.HANDLE,wintypes.DWORD)
                kernel.WaitForSingleObject.restype=wintypes.DWORD
                kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
                handle=kernel.OpenProcess(0x00100000,False,self.pid)
                if not handle:
                    error=ctypes.get_last_error()
                    if error==87:return False
                    raise OSError(error,'Cannot confirm owned process kernel state')
                try:
                    wait=kernel.WaitForSingleObject(handle,0)
                    if wait==0:return False
                    if wait!=258:raise OSError('Unexpected process wait state')
                finally:kernel.CloseHandle(handle)
            return True
        except psutil.NoSuchProcess:return False

def valid_child(parent: ProcessIdentity, child: ProcessIdentity) -> bool:
    """Require an actual parent edge and nonnegative process birth ordering."""
    return child.parent==parent.pid and child.created>=parent.created

class OwnedSession:
    """Never attach to or terminate another CST desktop session."""
    def __init__(self,config: Config,out: Path):
        self.config=config;self.out=out;self.identities={};self.root=None
        self.stop=threading.Event();self.thread=None;self.conn=None

    def collect(self) -> None:
        import psutil
        if self.root is None or not self.root.alive():return
        found={self.root.pid:self.root}
        allp={p.pid:p.info for p in psutil.process_iter(['pid','ppid','create_time','cmdline'])}
        changed=True
        while changed:
            changed=False
            for pid,p in allp.items():
                if pid in found or p['ppid'] not in found:continue
                child=ProcessIdentity(pid,p['ppid'],p['create_time'],tuple(p['cmdline'] or ()))
                if valid_child(found[child.parent],child):found[pid]=child;changed=True
        self.identities.update({(v.pid,v.created):v for v in found.values()})
        atomic_json(self.out/'process_tree.json',dict(at=time.time(),processes=[asdict(v) for v in found.values()]))

    def __enter__(self):
        import os,psutil
        from cst_optimization.core.connection import CSTConnection
        if psutil.virtual_memory().available<self.config.runtime.start_free_ram_gib*2**30:
            raise RuntimeError('Insufficient RAM before CST preparation')
        self.out.mkdir(parents=True,exist_ok=True)
        self.conn=CSTConnection(self.config.paths.cst_library_path,mode='new')
        try:
            self.conn.connect();candidate=ProcessIdentity.read(self.conn.pid)
            worker=ProcessIdentity.read(os.getpid());cursor=candidate;chain=[cursor]
            while cursor.pid!=worker.pid:
                parent=ProcessIdentity.read(cursor.parent)
                if not valid_child(parent,cursor) or len(chain)>16:raise RuntimeError('CST ownership mismatch')
                chain.append(parent);cursor=parent
            self.root=candidate
            atomic_json(self.out/'owner.json',dict(root=asdict(self.root),chain=[asdict(v) for v in chain]))
            self.collect()
            def watch():
                while not self.stop.wait(1):
                    try:self.collect()
                    except Exception as exc:atomic_json(self.out/'watch_error.json',dict(error=repr(exc)))
            self.thread=threading.Thread(target=watch,daemon=True);self.thread.start()
            self.conn.set_quiet_mode(True)
            return self
        except BaseException:
            self.__exit__(None,None,None);raise

    def __exit__(self,*args):
        import psutil
        self.stop.set()
        if self.thread:self.thread.join(3)
        if self.root is None:return
        self.collect();errors=[]
        def close():
            try:self.conn.design_environment.close()
            except Exception as exc:errors.append(repr(exc))
        if self.root.alive():
            t=threading.Thread(target=close,daemon=True);t.start();t.join(5)
        terminated=[]
        for v in sorted(self.identities.values(),key=lambda v:v.created,reverse=True):
            if v.alive():
                psutil.Process(v.pid).kill();terminated.append(asdict(v))
        deadline=time.monotonic()+8
        while time.monotonic()<deadline and any(v.alive() for v in self.identities.values()):time.sleep(.25)
        remaining=[asdict(v) for v in self.identities.values() if v.alive()]
        atomic_json(self.out/'cleanup.json',dict(success=not remaining,remaining=remaining,terminated=terminated,errors=errors))
        if remaining:raise RuntimeError('Owned CST cleanup failed; stop dispatch')

def verify_wake_history(project: Path,length_mm: float=35000.) -> None:
    """Verify the final saved command, preventing template-default modal stalls."""
    import re
    history=json.loads((project.with_suffix('')/'Model/3D/ModelHistory.json').read_text(encoding='utf-8'))
    values=re.findall(r'\.WakeLength\s+\\?"([\d.eE+-]+)',json.dumps(history))
    if not values or not math.isclose(float(values[-1]),length_mm):
        raise ValueError('Saved WakeLength is missing or invalid (requires 35000 mm)')

def prepare_cst(config: Config,coordinates: dict[str,float],out: Path) -> dict:
    """Rebuild one immutable candidate and export full tensors before Wakis."""
    import psutil
    source=Path(config.paths.template);out.mkdir(parents=True,exist_ok=False)
    project=out/'project'/source.name;project.parent.mkdir()
    before=digest(source);shutil.copy2(source,project)
    shutil.copytree(source.with_suffix('')/'Model',project.with_suffix('')/'Model')
    geometry=out/'geometry';geometry.mkdir()
    expanded=Geometry(config).expand(coordinates)
    atomic_json(out/'input.json',dict(source=str(source),sha256=before,parameters=coordinates,expanded=expanded))
    try:
        with OwnedSession(config,out) as session:
            p=session.conn.open_project(str(project));p.activate()
            p.execute_vba('ChangeProblemType "Wakefield Solver"\nSolver.WakeLength "35000"',
                          header='WF7 valid wake context before parameter rebuild',timeout=180.)
            if not p.update_parameters(expanded,use_full_rebuild=True):raise RuntimeError('Candidate rebuild failed')
            if not p.save(include_results=False):raise RuntimeError('Candidate save failed')
            actual=parameters(project)
            if any(k not in actual or not math.isclose(actual[k],v,rel_tol=1e-10,abs_tol=1e-8) for k,v in expanded.items()):
                raise ValueError('Saved candidate parameter identity mismatch')
            code=['ChangeProblemType "Wakefield Solver"',f'Solver.FrequencyRange "0", "{config.physics.band_hz[1]/1e6:.16g}"',
                  f'Solver.WakeLength "{config.physics.wake_length_m*1000:.16g}"']
            for i,(x,y) in enumerate(((0,0),(-2,0),(2,0),(0,-2),(0,2))):
                code.append(f'''With ParticleBeam
 .Reset
 .Name "WF7MeshBeam{i}"
 .Length "70"
 .Beta "1.0"
 .Charge "-1e-9"
 .IsBunchGaussian "True"
 .ConsiderForMeshRefinement "True"
 .BeamPoint "False", "{x}", "{y}", "0"
 .BeamDir "0", "0", "1"
 .IndirectWakeIntegration "False"
 .WakeIntegrationShift "0", "0", "0"
 .Create
End With''')
            p.execute_vba('\n'.join(code),header='WF7 explicit excitation and common mesh',timeout=180.)
            p.save(include_results=False);verify_wake_history(project)
            export=Path(__file__).with_name('export_geometry.bas').read_text(encoding='utf-8')
            export=export.replace('MANIFEST',(geometry/'solids.tsv').as_posix()).replace('OUTDIR',geometry.as_posix())
            p.project.schematic.execute_vba_code(export,timeout=600)
            p.execute_vba('Solver.MatrixDump True\nMesh.MeshType "HexahedralFIT"\n'
                          'Mesh.AddAutomeshFixpoint True, True, False, 0, 0, 0\n'
                          'Mesh.AddAutomeshFixpoint True, True, False, 2, 2, 0\n'
                          'Mesh.AddAutomeshFixpoint True, True, False, -2, -2, 0\n'
                          'Mesh.ConvertGeometryDataAfterMeshing True\nMesh.ForceUpdate',
                          header='WF7 tensor export setup',timeout=180.)
            mif=project.with_suffix('')/'ModelCache/Model.mif'
            shutil.copy2(mif,geometry/'ported_Model.mif');faces=port_faces(mif)
            p.execute_vba('\n'.join('Port.Delete "'+f['name'].split('_')[-1]+'"' for f in faces)+'\nSolver.CalculateModesOnly False\nSolver.MatrixDump True',
                          header='WF7 omit CST modal ports during matrix assembly',timeout=120.)
            p.save(include_results=False)
            atomic_json(out/'assembly_started.json',dict(at=time.time(),owner=asdict(session.root)))
            p.model3d.start_solver(timeout=180)
            deadline=time.monotonic()+config.runtime.mesh_timeout_s;last=None;stable=0;present={}
            while time.monotonic()<deadline:
                result=project.with_suffix('')/'Result'
                present={n:(result/(n+'.mat')).stat().st_size if (result/(n+'.mat')).exists() else 0 for n in ('ds','dsd','dA','dad','Eps','Mue')}
                stable=stable+1 if all(present.values()) and present==last else 0;last=present
                atomic_json(out/'heartbeat.json',dict(at=time.time(),phase='matrix_assembly',files=present))
                if stable>=4:break
                if psutil.virtual_memory().available<config.runtime.running_free_ram_gib*2**30:raise MemoryError('CST preparation free RAM guard')
                if not p.model3d.is_solver_running(timeout=10):break
                time.sleep(.5)
            if p.model3d.is_solver_running(timeout=10):
                p.model3d.abort_solver(timeout=60)
                settle=time.monotonic()+60
                while p.model3d.is_solver_running(timeout=10) and time.monotonic()<settle:time.sleep(.5)
                # Matrix assembly has no completed CST field result to save.
                # The project geometry was saved before assembly. If CST keeps
                # its asynchronous cancellation flag, OwnedSession closes this
                # exact session and verifies all children have exited below.
            atomic_json(out/'assembly_stop.json',dict(at=time.time(),matrices_present=present,info=p.model3d.get_solver_run_info(timeout=10),messages=p.get_messages()))
            if not all(present.values()):raise RuntimeError('Incomplete matrix export')
        result=dict(project=str(project),geometry=str(geometry),source_sha256=before,parameters=coordinates)
        atomic_json(out/'result.json',result);return result
    except BaseException:
        atomic_json(out/'failure.json',dict(at=time.time(),traceback=traceback.format_exc()));raise
    finally:
        if digest(source)!=before:raise RuntimeError('Source template changed during preparation')
