"""Portable task identities, validated artifacts and machine-local locking."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from importlib.metadata import version
import os
from pathlib import Path
import re
from typing import Any, Iterator
import zipfile

from ..storage import atomic_json, digest, fingerprint, project_manifest


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def owner_lock(path: Path) -> Iterator[None]:
    """Fail closed on an already-running worker; OS releases locks on exit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def execution_identity(config: Any) -> dict[str, Any]:
    """Exclude station paths, retain every scientific/search setting and source byte."""
    repository = Path(__file__).resolve().parents[3]
    paths = list((repository / "workflows/rfgun_hom_target").rglob("*.py"))
    paths += list((repository / "src/cst_optimization").rglob("*.py"))
    paths.append(repository / "run_workflow_5_async.py")
    settings = config.as_dict()
    settings.pop("paths")
    library = Path(config.paths.cst_library_path)
    return dict(settings=settings, template=project_manifest(config.paths.template_path),
                numerical_versions={name: version(name) for name in ("numpy", "scipy", "scikit-learn")},
                cst_python={p.relative_to(library).as_posix(): digest(p) for p in sorted((library / "cst").rglob("*.py"))},
                code={p.relative_to(repository).as_posix(): digest(p) for p in sorted(paths)})


def safe_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", value):
        raise ValueError("Invalid task/node identity")
    return value


@dataclass(frozen=True)
class Node:
    """One machine and its local filesystem; never a shared SQLite directory."""
    name: str
    root: str
    config: str
    python: str
    repository: str
    ssh_config: str = ""
    ssh_host: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Node":
        if set(value) - set(cls.__dataclass_fields__):
            raise ValueError("Unknown node settings")
        node = cls(**value)
        safe_id(node.name)
        if any(not isinstance(v, str) or not v for v in
               (node.root, node.config, node.python, node.repository)):
            raise ValueError("Node paths must be nonempty strings")
        if bool(node.ssh_config) != bool(node.ssh_host):
            raise ValueError("Remote node needs both SSH config and host alias")
        return node


def pack_evidence(evaluation: Path, target: Path) -> str:
    """Keep raw beam fields/energy and lifecycle proof; native 3D fields stay on node."""
    temporary = target.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(evaluation.rglob("*")):
            if path.is_file() and "project" not in path.relative_to(evaluation).parts:
                archive.write(path, path.relative_to(evaluation).as_posix())
        for path in evaluation.glob("attempt_*/project/*/Result/Model.log"):
            archive.write(path, path.relative_to(evaluation).parts[0] + "/CST_Model.log")
    os.replace(temporary, target)
    return digest(target)


def unpack_evidence(source: Path, target: Path, expected_sha256: str) -> None:
    """Reject corruption and traversal before extracting any returned worker file."""
    if digest(source) != expected_sha256:
        raise ValueError("Worker artifact digest mismatch")
    target = target.resolve()
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            name = member.filename.replace("\\", "/")
            resolved = (target / name).resolve()
            if ":" in name or name.startswith("/") or ".." in name.split("/") or target not in resolved.parents:
                raise ValueError("Unsafe worker artifact member")
            if member.file_size > 512 * 1024 * 1024:
                raise ValueError("Oversized evidence member")
        archive.extractall(target)


def publish_json(path: Path, value: Any) -> None:
    """Existing task specifications and grants are immutable and idempotent."""
    if path.exists():
        if read_json(path) != value:
            raise ValueError(f"Conflicting immutable message: {path.name}")
    else:
        atomic_json(path, value)
