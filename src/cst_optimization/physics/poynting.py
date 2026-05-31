"""Modified Poynting vector computation from CST 3D field exports.

The **modified Poynting vector** :math:`S_c` is used to detect RF
breakdown hot-spots in superconducting cavities::

    S  = 0.5 * (E × H^*)              complex Poynting vector
    Sc = |Re(S)| + gc * |Im(S)|        modified magnitude

where *gc* weights the reactive (imaginary) contribution.  Both real
power flow and stored-energy sloshing contribute to field-emission risk;
*gc* is typically 0.1–0.5 (default 0.125).

Reference
---------
The formula originates from the modified Poynting vector heuristic used
in SRF cavity design to correlate surface fields with breakdown probability.

File format (CST ASCII field export)
------------------------------------
CST exports 3D field data as space- or tab-delimited text with 9 columns::

    x  y  z  Fx_real  Fx_imag  Fy_real  Fy_imag  Fz_real  Fz_imag

where *F* is either the electric field (V/m) or magnetic field (A/m).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PoyntingResult:
    """Full result of a modified Poynting vector computation.

    Attributes
    ----------
    sc_max : float
        Maximum value of Sc (W/m²).
    sc_max_location : np.ndarray
        (x, y, z) coordinates of the maximum (m).
    sc_mean : float
        Spatial mean of Sc (W/m²).
    sc_median : float
        Spatial median of Sc (W/m²).
    sc_field : np.ndarray
        Full Sc field array (one value per field point).
    s_real_mag : np.ndarray
        |Re(S)| at each point.
    s_imag_mag : np.ndarray
        |Im(S)| at each point.
    x : np.ndarray
        x-coordinates (m).
    y : np.ndarray
        y-coordinates (m).
    z : np.ndarray
        z-coordinates (m).
    n_points : int
        Number of field sample points.
    """

    sc_max: float
    sc_max_location: np.ndarray
    sc_mean: float
    sc_median: float
    sc_field: np.ndarray
    s_real_mag: np.ndarray
    s_imag_mag: np.ndarray
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    n_points: int = 0


# ---------------------------------------------------------------------------
# Field data loading
# ---------------------------------------------------------------------------


def parse_cst_field_export(filepath: str) -> np.ndarray:
    """Read a CST ASCII field-export file.

    Handles both raw numeric files and files with CST-style headers
    (column-name line + separator line before the data block).

    Parameters
    ----------
    filepath : str
        Path to the exported text file.

    Returns
    -------
    np.ndarray
        Shape ``(N, 9)``.  Columns:
        ``[x, y, z, Fx_re, Fx_im, Fy_re, Fy_im, Fz_re, Fz_im]``.
        Coordinates are in whatever unit CST exported (typically mm);
        field components are in V/m (E) or A/m (H).
    """
    # Detect how many header rows to skip.  CST field exports have:
    #   line 0: column headers  ("  x [mm]   y [mm]  ...")
    #   line 1: separator       ("----------...")
    #   line 2+: data           ("-10.8205  -10.8205  0.0066...")
    # We scan until we find a line whose first whitespace-delimited
    # token can be parsed as a float.
    skip_rows = 0
    with open(filepath, "r") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                skip_rows += 1
                continue
            # Try to parse the first token as a float
            first_token = stripped.split()[0]
            try:
                float(first_token)
                break  # this is a data row
            except ValueError:
                skip_rows += 1

    data = np.loadtxt(filepath, dtype=float, skiprows=skip_rows)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    if data.shape[1] != 9:
        raise ValueError(
            f"Expected 9 columns (x,y,z,Fx_re,Fx_im,Fy_re,Fy_im,Fz_re,Fz_im), "
            f"got {data.shape[1]} after skipping {skip_rows} header row(s).  "
            f"Column names in file may differ from expected format."
        )
    return data


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_modified_poynting(
    e_data: np.ndarray,
    h_data: np.ndarray,
    gc: float = 0.125,
    coordinate_tolerance: float = 1e-6,
) -> PoyntingResult:
    """Compute the modified Poynting vector from E- and H-field data.

    Derivation
    ----------
    The complex Poynting vector (time-averaged) is::

        S = 0.5 * (E × H^*)

    In Cartesian components::

        Sx = 0.5 * (Ey·Hz^* - Ez·Hy^*)
        Sy = 0.5 * (Ez·Hx^* - Ex·Hz^*)
        Sz = 0.5 * (Ex·Hy^* - Ey·Hx^*)

    The modified magnitude combines real and reactive contributions::

        Sc = |Re(S)| + gc * |Im(S)|

    where::

        |Re(S)| = √(Re(Sx)² + Re(Sy)² + Re(Sz)²)
        |Im(S)| = √(Im(Sx)² + Im(Sy)² + Im(Sz)²)

    Parameters
    ----------
    e_data : np.ndarray
        ``(N, 9)`` E-field data from ``parse_cst_field_export()``.
    h_data : np.ndarray
        ``(N, 9)`` H-field data.
    gc : float
        Reactive-power weighting factor (default 0.125).
    coordinate_tolerance : float
        Maximum allowed mismatch between E- and H-field coordinate meshes.

    Returns
    -------
    PoyntingResult
    """
    # --- Coordinate validation ---
    x_e, y_e, z_e = e_data[:, 0], e_data[:, 1], e_data[:, 2]
    x_h, y_h, z_h = h_data[:, 0], h_data[:, 1], h_data[:, 2]

    if e_data.shape[0] != h_data.shape[0]:
        raise ValueError(
            f"E- and H-field must have the same number of points.  "
            f"Got {e_data.shape[0]} vs {h_data.shape[0]}"
        )
    if (
        np.max(np.abs(x_e - x_h)) > coordinate_tolerance
        or np.max(np.abs(y_e - y_h)) > coordinate_tolerance
        or np.max(np.abs(z_e - z_h)) > coordinate_tolerance
    ):
        raise ValueError(
            "E- and H-field coordinate meshes differ beyond tolerance "
            f"({coordinate_tolerance}).  Ensure both exports use the "
            f"same monitor grid."
        )

    n = e_data.shape[0]
    x = x_e
    y = y_e
    z = z_e

    # --- Build complex field components ---
    # Columns: 0,1,2 = x,y,z;  3,4 = re,im of x-comp;  5,6 = re,im of y;  7,8 = re,im of z
    Ex = e_data[:, 3] + 1j * e_data[:, 4]
    Ey = e_data[:, 5] + 1j * e_data[:, 6]
    Ez = e_data[:, 7] + 1j * e_data[:, 8]

    Hx = h_data[:, 3] + 1j * h_data[:, 4]
    Hy = h_data[:, 5] + 1j * h_data[:, 6]
    Hz = h_data[:, 7] + 1j * h_data[:, 8]

    # --- Complex Poynting vector: S = 0.5 * E × conj(H) ---
    Sx = 0.5 * (Ey * np.conj(Hz) - Ez * np.conj(Hy))
    Sy = 0.5 * (Ez * np.conj(Hx) - Ex * np.conj(Hz))
    Sz = 0.5 * (Ex * np.conj(Hy) - Ey * np.conj(Hx))

    # --- Magnitudes ---
    s_real_mag = np.sqrt(np.real(Sx) ** 2 + np.real(Sy) ** 2 + np.real(Sz) ** 2)
    s_imag_mag = np.sqrt(np.imag(Sx) ** 2 + np.imag(Sy) ** 2 + np.imag(Sz) ** 2)

    # --- Modified Poynting vector ---
    Sc = s_real_mag + gc * s_imag_mag

    # --- Statistics ---
    idx_max = int(np.argmax(Sc))
    sc_max = float(Sc[idx_max])
    sc_max_loc = np.array([x[idx_max], y[idx_max], z[idx_max]])

    return PoyntingResult(
        sc_max=sc_max,
        sc_max_location=sc_max_loc,
        sc_mean=float(np.mean(Sc)),
        sc_median=float(np.median(Sc)),
        sc_field=Sc,
        s_real_mag=s_real_mag,
        s_imag_mag=s_imag_mag,
        x=x,
        y=y,
        z=z,
        n_points=n,
    )


def max_modified_poynting(
    e_file: str,
    h_file: str,
    gc: float = 0.125,
    field_scale: float = 1.0,
) -> float:
    """Convenience: return ``max(Sc)`` from two field-export files.

    Parameters
    ----------
    e_file : str
        Path to E-field export.
    h_file : str
        Path to H-field export.
    gc : float
        Reactive weighting factor.
    field_scale : float
        Field scaling factor to reach target gradient.
        S ∝ E×H ∝ K², so the result is multiplied by ``field_scale²``.
        Set ``field_scale = E_target / E_sim`` where E_sim is the peak
        |E| from the simulation (e.g. from the ``MaxE_Z0`` template).

    Returns
    -------
    float
        Maximum modified Poynting vector value (W/m²), scaled to the
        target operating gradient.
    """
    e_data = parse_cst_field_export(e_file)
    h_data = parse_cst_field_export(h_file)
    result = compute_modified_poynting(e_data, h_data, gc=gc)
    return result.sc_max * (field_scale ** 2)


def discover_field_files(project_dir: str) -> tuple[str, str]:
    """Auto-locate E- and H-field export files in a CST project export directory.

    CST post-processing templates typically dump 3D field data to
    ``<project>/Export/3d/`` with filenames like ``e-field (f=f_data) [1].txt``
    and ``h-field (f=f_data) [1].txt``.

    Parameters
    ----------
    project_dir : str
        Path to the **unpacked** CST project directory
        (e.g. ``D:/ModelData/AllParaVer1_E2test`` — the folder alongside
        the ``.cst`` file, NOT the ``.cst`` file itself).

    Returns
    -------
    (e_file, h_file) : tuple[str, str]
        Absolute paths to the E-field and H-field ASCII export files.
        Returns empty strings for any that cannot be found.
    """
    import glob as _glob

    export_dir = os.path.join(project_dir, "Export", "3d")
    if not os.path.isdir(export_dir):
        return "", ""

    e_candidates = (
        _glob.glob(os.path.join(export_dir, "*e-field*"))
        + _glob.glob(os.path.join(export_dir, "*E-Field*"))
        + _glob.glob(os.path.join(export_dir, "*E_field*"))
        + _glob.glob(os.path.join(export_dir, "*e_field*"))
    )
    h_candidates = (
        _glob.glob(os.path.join(export_dir, "*h-field*"))
        + _glob.glob(os.path.join(export_dir, "*H-Field*"))
        + _glob.glob(os.path.join(export_dir, "*H_field*"))
        + _glob.glob(os.path.join(export_dir, "*h_field*"))
    )

    e_file = e_candidates[0] if e_candidates else ""
    h_file = h_candidates[0] if h_candidates else ""

    return e_file, h_file
