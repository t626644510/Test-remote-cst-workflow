"""WF8.1 command line: explicit solving, saved-result export and offline reports."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
from .io import read_json


def parser() -> argparse.ArgumentParser:
    """Build the CLI without importing a live CST API."""
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest='command', required=True)
    for name in ('scan', 'resume'):
        p = commands.add_parser(name)
        p.add_argument('--root', type=Path, required=True)
        p.add_argument('--template', type=Path, required=name=='scan')
        p.add_argument('--cst-library', default=os.environ.get('CST_PYTHON_LIB'))
        p.add_argument('--selection', type=Path)
        p.add_argument('--solve-limit-seconds', type=float)
        p.add_argument('--abort-grace-seconds', type=float, default=180)
        p.add_argument('--batch-size', type=int, default=32)
        p.add_argument('--initial-idle-seconds', type=float, default=300)
    p = commands.add_parser('export')
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cst-library', default=os.environ.get('CST_PYTHON_LIB'))
    p.add_argument('--surfaces', action='store_true')
    p = commands.add_parser('analyze')
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--label')
    p.add_argument('--frequency-mhz', type=float)
    p.add_argument('--window-rf', type=int, default=3)
    p.add_argument('--surfaces', action='store_true')
    p = commands.add_parser('report')
    p.add_argument('--input', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> None:
    """Dispatch commands; existing STOP files and live ownership locks are respected."""
    cli = parser()
    a = cli.parse_args(argv)
    if a.command in ('scan', 'resume', 'export') and not a.cst_library:
        cli.error('Provide --cst-library or CST_PYTHON_LIB')
    if a.command in ('scan', 'resume'):
        from .trk_supervise import Supervisor
        snapshot = a.root/'snapshot.json'
        if a.command == 'scan' and snapshot.exists():
            cli.error('Run already exists; use resume')
        if a.command == 'resume' and not snapshot.exists():
            cli.error('No existing snapshot to resume')
        template = a.template or Path(read_json(snapshot)['template'])
        plan_path = a.selection or a.root/'selection.json'
        plan = read_json(plan_path) if plan_path.exists() else {}
        seconds = a.solve_limit_seconds if a.solve_limit_seconds is not None else plan.get('solve_limit_seconds', 600)
        if a.batch_size < 1 or a.initial_idle_seconds < 120:
            cli.error('Require positive batch size and at least 120 s initial idle threshold')
        Supervisor(a.root, template, a.cst_library, a.batch_size, a.initial_idle_seconds,
                   seconds, a.selection, a.abort_grace_seconds).run()
    elif a.command == 'export':
        from .export import export_saved
        export_saved(a.project, a.output, a.cst_library, surfaces=a.surfaces)
    elif a.command == 'analyze':
        from .analysis import analyze
        analyze(a.input, a.output, label=a.label, frequency_mhz=a.frequency_mhz,
                width_rf=a.window_rf, surfaces=a.surfaces)
    elif a.command == 'report':
        from .report import report
        print(report(a.input, a.output))
