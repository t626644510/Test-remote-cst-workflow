"""Portable saved-record IO; inputs are never rewritten by offline analysis."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def fingerprint(paths: Iterable[Path]) -> dict[str, str]:
    result = {}
    for path in paths:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        result[str(path.resolve())] = digest.hexdigest()
    return result
