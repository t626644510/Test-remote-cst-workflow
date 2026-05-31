"""Structured logging utilities for the optimisation framework."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Any


_logger: logging.Logger | None = None


def get_logger(name: str = "cst_optimization") -> logging.Logger:
    """Return (or create) the package logger.

    Parameters
    ----------
    name : str
        Logger name.  Default ``"cst_optimization"``.

    Returns
    -------
    logging.Logger
    """
    global _logger
    if _logger is not None:
        return _logger

    _logger = logging.getLogger(name)
    _logger.setLevel(logging.INFO)

    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)
        _logger.addHandler(handler)

    return _logger


def log_optimization_step(
    iteration: int,
    n_total: int,
    x: Any,
    f: Any,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log a single optimisation step in a structured format."""
    logger = get_logger()
    msg = f"Iter {iteration:4d}/{n_total} | x={x} | f={f}"
    if extra:
        msg += f" | {extra}"
    logger.info(msg)
