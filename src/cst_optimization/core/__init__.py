"""CST interaction layer.

Provides a single lazily-called ``init_cst_path()`` entry point for CST
library setup.  Unlike the CST 2024-era pattern, the module no longer
manipulates ``sys.path`` as a side effect of import — callers (typically
``CSTConnection.__init__``) must explicitly invoke ``init_cst_path()``
before the first CST import.
"""

from __future__ import annotations

import logging
import os
import sys

_logger = logging.getLogger(__name__)

_DEFAULT_CST_LIBRARY_PATH = os.environ.get(
    "CST_LIBRARY_PATH", r"D:\CST\AMD64\python_cst_libraries"
)


def init_cst_path(library_path: str | None = None) -> str:
    """Ensure the CST Python library directory is on ``sys.path``.

    Uses ``sys.path.insert(0, ...)`` so the explicitly configured path
    takes priority over any older CST paths already on ``sys.path``
    (e.g. from a stale ``CST_LIBRARY_PATH`` env var).

    Idempotent — safe to call multiple times.

    Parameters
    ----------
    library_path : str | None
        Override the default CST library path.  If ``None``, the value
        of the ``CST_LIBRARY_PATH`` env var is used, falling back to
        ``D:\\CST\\AMD64\\python_cst_libraries``.

    Returns
    -------
    str
        The library path that was inserted (or would have been inserted).
    """
    path = library_path or _DEFAULT_CST_LIBRARY_PATH

    # Warn about conflicting CST paths already on sys.path
    existing_cst = [p for p in sys.path if "python_cst_libraries" in p.lower()]
    if existing_cst and path not in existing_cst:
        _logger.warning(
            "Conflicting CST library paths on sys.path — "
            "existing: %s — inserting configured path at front: %s",
            existing_cst, path,
        )
    elif path in existing_cst and existing_cst.index(path) != 0:
        # Path exists but not at front — reorder it to front
        sys.path.remove(path)

    if os.path.exists(path) and path not in sys.path:
        sys.path.insert(0, path)

    return path
