"""Atomic, finite JSON and immutable numeric evidence for the local campaign."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from typing import Any

def digest(path: str | Path) -> str:
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def atomic_json(path: str | Path, value: Any) -> None:
    """Write a complete finite record; keep the old file on interrupted writes."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.flush();os.fsync(stream.fileno())
    for attempt in range(9):
        try:temporary.replace(path);return
        except PermissionError:
            if attempt==8:raise
            time.sleep(min(.025*2**attempt,.5))

def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def manifest(directory: Path, paths: list[Path]) -> dict:
    """Record explicit retained files; no glob-based deletion is authorized here."""
    return {str(p.relative_to(directory)):dict(bytes=p.stat().st_size,sha256=digest(p)) for p in paths}

def validate_manifest(directory: Path, entries: dict) -> None:
    """Fail closed if any permanent evidence file is missing or changed."""
    base=directory.absolute()
    for relative,entry in entries.items():
        p=(base/relative).absolute()
        if '..' in Path(relative).parts or not p.is_relative_to(base):raise ValueError('Unsafe manifest path')
        if not p.is_file() or p.stat().st_size!=entry['bytes'] or digest(p)!=entry['sha256']:
            raise ValueError(f'Evidence mismatch: {relative}')
