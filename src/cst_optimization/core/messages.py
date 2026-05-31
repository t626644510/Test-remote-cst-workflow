"""CST Message Window capture and persistence.

Captures messages from the CST Studio Suite message window via
``Project.get_messages()`` and writes them to timestamped text files
so they survive solver crashes / DE restarts for post-hoc debugging.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .project import CSTProject

_logger = logging.getLogger(__name__)


class MessageLogger:
    """Capture CST Message Window content and persist to disk.

    Parameters
    ----------
    output_dir : str
        Directory for message log files.
    enabled : bool
        If ``False``, all operations are no-ops (production bypass).
    """

    def __init__(self, output_dir: str = "", enabled: bool = True) -> None:
        self._output_dir = output_dir
        self._enabled = enabled
        self._buffer: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(self, project: CSTProject) -> str:
        """Read current messages from the CST project and append to buffer."""
        if not self._enabled:
            return ""

        try:
            raw = project.get_messages()
        except Exception as exc:
            raw = f"[MessageLogger] get_messages() raised: {exc}"

        text = self._normalize(raw)
        if text:
            self._buffer.append(text)
        return text

    def write(self, label: str = "", iteration: int = 0) -> str | None:
        """Flush buffered messages to a timestamped file."""
        if not self._enabled or not self._buffer:
            return None

        try:
            os.makedirs(self._output_dir, exist_ok=True)
        except OSError:
            _logger.warning(
                "Cannot create message output dir: %s", self._output_dir
            )
            return None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"msg_{label}_iter{iteration:04d}_{ts}.txt"
        fpath = os.path.join(self._output_dir, fname)

        try:
            with open(fpath, "w", encoding="utf-8") as fh:
                fh.write(f"CST Messages — {label} — iteration {iteration}\n")
                fh.write(f"Captured: {datetime.now().isoformat()}\n")
                fh.write("=" * 72 + "\n\n")
                for i, msg in enumerate(self._buffer):
                    fh.write(f"--- Capture {i + 1} ---\n")
                    fh.write(msg)
                    fh.write("\n\n")
        except OSError:
            _logger.warning("Failed to write message log: %s", fpath, exc_info=True)
            return None

        self._buffer.clear()
        return fpath

    def write_now(
        self, text: str, label: str = "", iteration: int = 0
    ) -> str | None:
        """Directly write a string to a message file (bypasses buffer)."""
        if not self._enabled or not text.strip():
            return None

        try:
            os.makedirs(self._output_dir, exist_ok=True)
        except OSError:
            _logger.warning(
                "Cannot create message output dir: %s", self._output_dir
            )
            return None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"msg_{label}_iter{iteration:04d}_{ts}.txt"
        fpath = os.path.join(self._output_dir, fname)

        try:
            with open(fpath, "w", encoding="utf-8") as fh:
                fh.write(f"CST Messages — {label} — iteration {iteration}\n")
                fh.write(f"Captured: {datetime.now().isoformat()}\n")
                fh.write("=" * 72 + "\n\n")
                fh.write(text)
                fh.write("\n")
        except OSError:
            _logger.warning(
                "Failed to write message log: %s", fpath, exc_info=True
            )
            return None

        return fpath

    def clear(self) -> None:
        """Discard all buffered messages."""
        self._buffer.clear()

    @property
    def is_empty(self) -> bool:
        """Return ``True`` if the buffer is empty."""
        return len(self._buffer) == 0

    # ------------------------------------------------------------------
    # Message inspection
    # ------------------------------------------------------------------

    # Known fatal VBA history replay failure patterns.
    # When these appear, the parameter combination caused face-count /
    # topology changes that broke history steps referencing fixed Face IDs.
    _HISTORY_FAILURE_PATTERNS: tuple[str, ...] = (
        "history update failed",
        "not positioned at the very last entry",
    )

    def has_history_failure(self) -> bool:
        """Check buffered messages for VBA history replay failures.

        Returns ``True`` if any message contains a known failure pattern
        indicating that ``full_history_rebuild()`` did not complete.
        """
        if not self._buffer:
            return False
        for msg in self._buffer:
            msg_lower = msg.lower()
            if any(p in msg_lower for p in self._HISTORY_FAILURE_PATTERNS):
                return True
        return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(raw: object) -> str:
        """Convert the opaque ``get_messages()`` return to a string."""
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw.strip()
        if isinstance(raw, (list, tuple)):
            return "\n".join(str(item) for item in raw).strip()
        if isinstance(raw, dict):
            return "\n".join(f"{k}: {v}" for k, v in raw.items()).strip()
        try:
            return str(raw).strip()
        except Exception:
            return repr(raw).strip()
