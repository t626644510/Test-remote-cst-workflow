from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from workflows.rfgun_hom_eigenmode.fields import (
    archive_changed_files,
    changed_files,
    read_complex_ez_line,
    snapshot_directory,
)

h5py = pytest.importorskip("h5py")


def test_reads_cst_vector_compound_hdf5_line(tmp_path: Path) -> None:
    path = tmp_path / "line.h5"
    complex_dtype = np.dtype([("re", "<f4"), ("im", "<f4")])
    vector_dtype = np.dtype(
        [("x", complex_dtype), ("y", complex_dtype), ("z", complex_dtype)]
    )
    values = np.zeros(5, dtype=vector_dtype)
    values["z"]["re"] = np.arange(5)
    values["z"]["im"] = -np.arange(5)
    with h5py.File(path, "w") as handle:
        field = handle.create_dataset("E-Field", data=values)
        field.attrs["unit"] = "V/m"
        z = handle.create_dataset("Mesh line z", data=np.arange(5, dtype=float))
        z.attrs["unit"] = "mm"

    line = read_complex_ez_line(path)

    assert line.z_m[-1] == pytest.approx(0.004)
    assert line.ez_v_per_m[-1] == pytest.approx(4 - 4j)


def test_archive_accepts_rewritten_identical_content(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    item = source / "field.h5"
    item.write_bytes(b"same")
    before = snapshot_directory(source)
    stat = item.stat()
    os.utime(item, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    after = snapshot_directory(source)

    changed = changed_files(before, after)
    archived = archive_changed_files(source, tmp_path / "raw", changed)

    assert len(changed) == 1
    assert len(archived) == 1
    assert (tmp_path / "raw" / "field.h5").read_bytes() == b"same"
