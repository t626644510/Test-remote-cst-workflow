"""HDF5 complex-field reading and immutable artifact archiving."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .models import ComplexLineField


@dataclass(frozen=True)
class FileFingerprint:
    """Content identity for one external post-processing artifact."""

    relative_path: str
    size: int
    mtime_ns: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "sha256": self.sha256,
        }


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_directory(root: str | Path) -> dict[str, FileFingerprint]:
    """Recursively fingerprint files below *root* without changing them."""

    root_path = Path(root)
    if not root_path.exists():
        return {}
    snapshot: dict[str, FileFingerprint] = {}
    for path in sorted(item for item in root_path.rglob("*") if item.is_file()):
        relative = path.relative_to(root_path).as_posix()
        stat = path.stat()
        snapshot[relative] = FileFingerprint(
            relative_path=relative,
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            sha256=sha256_file(path),
        )
    return snapshot


def changed_files(
    before: dict[str, FileFingerprint],
    after: dict[str, FileFingerprint],
) -> list[FileFingerprint]:
    """Return files added or content-changed between two snapshots."""

    return [
        fingerprint
        for relative, fingerprint in sorted(after.items())
        if (
            relative not in before
            or before[relative].sha256 != fingerprint.sha256
            or before[relative].mtime_ns != fingerprint.mtime_ns
            or before[relative].size != fingerprint.size
        )
    ]


def archive_changed_files(
    source_root: str | Path,
    destination_root: str | Path,
    fingerprints: Iterable[FileFingerprint],
    path_base: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Copy changed artifacts into an attempt-owned immutable directory."""

    source = Path(source_root)
    destination = Path(destination_root)
    archived: list[dict[str, Any]] = []
    for fingerprint in fingerprints:
        source_path = source / Path(fingerprint.relative_path)
        destination_path = destination / Path(fingerprint.relative_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if destination_path.exists():
            raise FileExistsError(
                f"immutable artifact already exists: {destination_path}"
            )
        shutil.copy2(source_path, destination_path)
        copied_hash = sha256_file(destination_path)
        if copied_hash != fingerprint.sha256:
            raise IOError(f"artifact hash mismatch after copy: {source_path}")
        archived.append(
            {
                **fingerprint.to_dict(),
                "archived_path": (
                    destination_path.resolve()
                    .relative_to(Path(path_base).resolve())
                    .as_posix()
                    if path_base is not None
                    else str(destination_path.resolve())
                ),
            }
        )
    return archived


def write_artifact_index(
    path: str | Path,
    *,
    source_root: str | Path,
    before: dict[str, FileFingerprint],
    after: dict[str, FileFingerprint],
    archived: list[dict[str, Any]],
) -> None:
    payload = {
        "source_root": str(Path(source_root).resolve()),
        "before_count": len(before),
        "after_count": len(after),
        "archived": archived,
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def _require_h5py() -> Any:
    try:
        import h5py
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "HDF5 field reading requires h5py. Install project dependencies "
            "with '.venv\\Scripts\\python.exe -m pip install -e .'"
        ) from exc
    return h5py


def _attribute_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.size == 1:
        return _attribute_text(value.reshape(-1)[0])
    return str(value)


def _unit_factor(unit: str, quantity: str) -> float:
    normalized = unit.strip().lower().replace(" ", "")
    if quantity == "length":
        factors = {
            "m": 1.0,
            "mm": 1e-3,
            "cm": 1e-2,
            "um": 1e-6,
            "µm": 1e-6,
        }
    else:
        factors = {
            "v/m": 1.0,
            "v/mm": 1e3,
            "kv/m": 1e3,
            "mv/m": 1e6,
        }
    if normalized not in factors:
        raise ValueError(f"unsupported {quantity} unit {unit!r}")
    return factors[normalized]


def _complex_from_array(data: np.ndarray, component: str = "z") -> np.ndarray:
    """Convert CST compound or native-complex arrays into a complex ndarray."""

    if np.iscomplexobj(data):
        return np.asarray(data, dtype=np.complex128)
    names = data.dtype.names or ()
    lowered = {name.lower(): name for name in names}
    if component.lower() in lowered:
        return _complex_from_array(data[lowered[component.lower()]], component)
    if "re" in lowered and "im" in lowered:
        return np.asarray(
            data[lowered["re"]], dtype=float
        ) + 1j * np.asarray(data[lowered["im"]], dtype=float)
    if "real" in lowered and "imag" in lowered:
        return np.asarray(
            data[lowered["real"]], dtype=float
        ) + 1j * np.asarray(data[lowered["imag"]], dtype=float)
    raise ValueError(
        f"field dataset is not complex and lacks re/im members: {names}"
    )


def _dataset_paths(handle: Any) -> list[str]:
    h5py = _require_h5py()
    paths: list[str] = []

    def visitor(name: str, item: Any) -> None:
        if isinstance(item, h5py.Dataset):
            paths.append(name)

    handle.visititems(visitor)
    return paths


def _select_dataset(
    handle: Any,
    explicit_path: str,
    preferred_names: tuple[str, ...],
) -> Any:
    if explicit_path:
        if explicit_path not in handle:
            raise KeyError(f"HDF5 dataset not found: {explicit_path}")
        return handle[explicit_path]
    paths = _dataset_paths(handle)
    for preferred in preferred_names:
        for path in paths:
            if path.lower().split("/")[-1] == preferred.lower():
                return handle[path]
    raise KeyError(
        f"could not discover HDF5 dataset; looked for {preferred_names}, "
        f"available={paths}"
    )


def read_complex_ez_line(
    path: str | Path,
    *,
    field_dataset: str = "",
    z_dataset: str = "",
    field_component: str = "z",
) -> ComplexLineField:
    """Read a one-dimensional complex Ez line from a CST HDF5 export.

    Supported field layouts are native complex arrays, ``re/im`` compound
    arrays, and CST vector compounds with ``x/y/z`` components whose selected
    component contains ``re/im``.
    """

    h5py = _require_h5py()
    source_path = Path(path)
    with h5py.File(source_path, "r") as handle:
        field_item = _select_dataset(
            handle,
            field_dataset,
            ("Ez", "E-Field", "E Field", "Electric Field"),
        )
        z_item = _select_dataset(
            handle,
            z_dataset,
            ("Mesh line z", "z", "Z-Coordinate", "Z Coordinate"),
        )
        ez = np.squeeze(_complex_from_array(field_item[...], field_component))
        z = np.squeeze(np.asarray(z_item[...], dtype=float))
        if ez.ndim != 1 or z.ndim != 1:
            raise ValueError(
                f"expected line data, got Ez shape {ez.shape}, z shape {z.shape}"
            )
        if len(ez) != len(z):
            raise ValueError(
                f"Ez/z length mismatch: {len(ez)} values vs {len(z)} positions"
            )
        if len(z) < 2:
            raise ValueError("at least two z samples are required")

        field_unit = _attribute_text(field_item.attrs.get("unit", "V/m"))
        z_unit = _attribute_text(z_item.attrs.get("unit", "m"))
        ez = ez * _unit_factor(field_unit, "field")
        z = z * _unit_factor(z_unit, "length")

    if not np.all(np.isfinite(z)):
        raise ValueError(f"non-finite z coordinates in {source_path}")
    if not np.all(np.isfinite(ez.real)) or not np.all(np.isfinite(ez.imag)):
        raise ValueError(f"non-finite complex field values in {source_path}")
    order = np.argsort(z)
    return ComplexLineField(
        z_m=z[order],
        ez_v_per_m=ez[order],
        source_path=str(source_path.resolve()),
    )


def resolve_field_file(
    raw_root: str | Path,
    pattern: str,
    *,
    mode: int,
    point: str,
) -> Path | None:
    """Resolve exactly one archived field artifact from a configured glob."""

    formatted = pattern.format(mode=mode, point=point)
    matches = sorted(Path(raw_root).glob(formatted))
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"field pattern {formatted!r} matched multiple files: {matches}"
        )
    return matches[0]


def save_complex_line_npz(path: str | Path, field: ComplexLineField) -> None:
    """Persist one complex Ez trajectory for CST-independent reprocessing."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        destination,
        z_m=np.asarray(field.z_m, dtype=float),
        ez_real_v_per_m=np.asarray(field.ez_v_per_m).real,
        ez_imag_v_per_m=np.asarray(field.ez_v_per_m).imag,
        source_path=np.asarray([field.source_path]),
    )


def read_complex_line_npz(path: str | Path) -> ComplexLineField:
    source = Path(path)
    with np.load(source, allow_pickle=False) as data:
        z = np.asarray(data["z_m"], dtype=float)
        ez = np.asarray(data["ez_real_v_per_m"], dtype=float) + 1j * np.asarray(
            data["ez_imag_v_per_m"], dtype=float
        )
        source_path = (
            str(data["source_path"][0]) if "source_path" in data.files else ""
        )
    return ComplexLineField(z_m=z, ez_v_per_m=ez, source_path=source_path)
