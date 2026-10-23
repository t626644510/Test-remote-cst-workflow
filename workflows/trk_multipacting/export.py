"""Export saved TRK records using verified CST interfaces on a private copy.

No solver is started. Trajectory time is ns, macrocharge C, CAD/positions mm.
APIs follow the existing MP5/MP6 export scripts and installed CST 2026 help.
"""
from __future__ import annotations
from pathlib import Path
import shutil
from typing import Any
from .io import fingerprint, write_json
from .trk_run import generation_lifetime_macro


def endpoint_macro(output: Path) -> str:
    """Verified ParticleTrajectoryReader position getters; active coordinates mm."""
    return f'''Sub Main
Dim i As Long, xs As Variant, ys As Variant, zs As Variant
Open "{output}" For Output As #1
Print #1, "index birth_x_mm birth_y_mm birth_z_mm end_x_mm end_y_mm end_z_mm"
For i = 0 To ParticleTrajectoryReader.GetNTrajectories()-1
 ParticleTrajectoryReader.SelectTrajectory i
 xs = ParticleTrajectoryReader.GetPositionsX()
 ys = ParticleTrajectoryReader.GetPositionsY()
 zs = ParticleTrajectoryReader.GetPositionsZ()
 Print #1, i; " "; xs(LBound(xs)); " "; ys(LBound(ys)); " "; zs(LBound(zs)); " "; xs(UBound(xs)); " "; ys(UBound(ys)); " "; zs(UBound(zs))
Next i
Close #1
ParticleTrajectoryReader.Reset
End Sub'''


def solid_macro(output: Path) -> str:
    """Verified per-solid CAD STL export at 0.001 mm surface tolerance."""
    return f'''Sub Main
Dim i As Long, s As String, comp As String, nm As String, sep As Long
Open "{output/'solids.txt'}" For Output As #1
For i = 0 To Solid.GetNumberOfShapes()-1
 s = Solid.GetNameOfShapeFromIndex(i)
 If s <> "" Then
  Print #1, i; "|"; s; "|"; Solid.IsConsideredForSimulation(s)
  If Solid.IsConsideredForSimulation(s) Then
   sep = InStrRev(s, ":")
   comp = Left(s, sep-1)
   nm = Mid(s, sep+1)
   With STL
    .Reset
    .FileName "{output}\\solid_" & CStr(i) & ".stl"
    .Name nm
    .Component comp
    .ExportFromActiveCoordinateSystem False
    .ExportFileUnits "mm"
    .NormalTolerance 5
    .SurfaceTolerance 0.001
    .WriteCAD
   End With
  End If
 End If
Next i
Close #1
End Sub'''


def export_saved(project: Path, output: Path, library: str, *, surfaces: bool = False) -> dict[str, Any]:
    """Copy a saved project and export records, checking original fingerprints."""
    project, output = project.resolve(), output.resolve()
    if any(c in str(output) for c in ('"', '\n', '\r')):
        raise ValueError('Output path contains unsupported VBA delimiters')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Export requires a new or empty output directory')
    if project.with_suffix('') == output or project.with_suffix('') in output.parents:
        raise ValueError('Export must be outside the original project directory')
    raw = project.with_suffix('')/'Result'
    required = [project, raw/'Model.log', raw/'trajectories.bix']
    log = (raw/'Model.log').read_text(errors='replace')
    if 'Particle Tracking Solver successful.' not in log:
        raise ValueError('Source does not contain a completed/saved-aborted TRK result')
    before = fingerprint(required)
    output.mkdir(parents=True, exist_ok=True)
    private = output/'private'/project.name
    private.parent.mkdir()
    shutil.copy2(project, private)
    shutil.copytree(project.with_suffix(''), private.with_suffix(''), ignore=shutil.ignore_patterns('*.lok','*.lock'))
    for name in ('Model.log','field_import_0_0.rex','model.gex'):
        if (private.with_suffix('')/'Result'/name).exists():
            shutil.copy2(private.with_suffix('')/'Result'/name, output/name)
    from cst_optimization.core import init_cst_path
    from cst_optimization.core.connection import CSTConnection
    from cst_optimization.core.results import ResultReader
    from cst_optimization.core.session_cleanup import close_owned_session
    import numpy as np
    import psutil
    init_cst_path(library)
    reader = ResultReader(str(private), allow_interactive=True)
    curves, missing = {}, []
    try:
        for path in reader.list_tree_items():
            if path.startswith('1D Results') and ('Information\\' in path or 'Particle Sources\\' in path):
                try:
                    item = reader.get_result_item(path)
                    curves[path] = dict(x=np.atleast_1d(np.asarray(item.get_xdata(),float)).tolist(),
                                        y=np.atleast_1d(np.asarray(item.get_ydata(),float)).tolist(), xlabel=item.xlabel, ylabel=item.ylabel)
                except ValueError as exc:
                    missing.append(dict(path=path, error=str(exc)))
    finally:
        reader.invalidate_cache()
    write_json(output/'raw_curves.json', curves)
    write_json(output/'missing_curves.json', missing)
    connection = CSTConnection(library, mode='new')
    connection.connect()
    connection.set_quiet_mode(True)
    owner = (connection.pid, psutil.Process(connection.pid).create_time())
    opened = None
    try:
        opened = connection.open_project(str(private))
        if opened.project.model3d.is_solver_running():
            raise RuntimeError('Private copy unexpectedly has a running solver')
        execute = opened.project.model3d._execute_vba_code
        macro = generation_lifetime_macro(output/'trajectory_lifetimes.txt', output/'trajectory_generations.txt')
        if surfaces:
            # Keep the loaded reader for the following endpoint export.
            prefix, suffix = macro.rsplit('ParticleTrajectoryReader.Reset', 1)
            macro = prefix + suffix
        (output/'export_trajectories.bas').write_text(macro, encoding='utf8')
        execute(macro)
        if surfaces:
            geom = output/'surface_time'
            geom.mkdir()
            for name, code in (('export_solids.bas', solid_macro(geom)),
                               ('export_endpoints.bas', endpoint_macro(geom/'endpoint_positions.txt'))):
                (geom/name).write_text(code, encoding='utf8')
                execute(code)
    finally:
        try:
            if opened is not None:
                opened.project.close()
        finally:
            write_json(output/'cleanup.json', close_owned_session(connection, *owner))
    after = fingerprint(required)
    evidence = dict(project=str(project), private=str(private), solver='TRK', solver_started=False,
                    before=before, after=after, unchanged=before==after, surfaces=surfaces)
    write_json(output/'export_manifest.json', evidence)
    if before != after:
        raise RuntimeError('Original source changed during export; reject mixed snapshot')
    return evidence
