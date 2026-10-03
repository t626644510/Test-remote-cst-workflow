"""Verified project copying and durable publication, adapted from WF5 2026-10-03."""
import hashlib,json,os,shutil,time
from pathlib import Path
from typing import Any

def atomic_json(path: Path, value: Any) -> None:
    """Flush before atomic replacement; never silently serialize NaN."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    # Windows readers can temporarily deny replacement. Keep the old complete
    # document visible and retry only this atomic publication, never the solve.
    for attempt in range(11):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if attempt == 10:
                raise
            time.sleep(0.1)


def digest(path: Path) -> str:
    """SHA-256 of file bytes, without loading large CST fields into memory."""
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(value: Any) -> str:
    """Deterministic JSON identity for a complete evaluation contract."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     allow_nan=False).encode()).hexdigest()


def project_manifest(project: Path) -> dict[str, str]:
    """Include project and all companion files except transient lock files."""
    folder = project.with_suffix("")
    if not project.is_file() or not folder.is_dir():
        raise ValueError("Template requires a .cst file and its same-name companion directory")
    files = [project] + sorted(p for p in folder.rglob("*")
                              if p.is_file() and p.suffix.lower() not in {".lok", ".lock"})
    return {str(p.relative_to(project.parent)): digest(p) for p in files}


def copy_verified_project(source: Path, destination_dir: Path) -> tuple[Path, dict[str, str]]:
    """Copy a consistent complete project, preserving the source and its locks."""
    source = source.resolve()
    destination_dir = destination_dir.resolve()
    if destination_dir == source.parent or source.with_suffix("") in destination_dir.parents:
        raise ValueError("Project copy destination overlaps its source")
    before = project_manifest(source)
    destination_dir.mkdir(parents=True, exist_ok=False)
    for relative in before:
        target = destination_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.parent / relative, target)
    target_project = destination_dir / source.name
    if before != project_manifest(source) or before != project_manifest(target_project):
        raise RuntimeError("Source changed while copying, or project snapshot is incomplete")
    return target_project, before


