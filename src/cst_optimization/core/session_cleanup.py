"""Ownership-checked cleanup for a private, already-closed CST project session."""
from __future__ import annotations
import os
from typing import Any, TYPE_CHECKING
import psutil
if TYPE_CHECKING:
    from .connection import CSTConnection


def close_owned_session(connection: CSTConnection, pid: int, created: float) -> dict[str, Any]:
    """After project closure, terminate only the verified private CST session.

    Reuse shared targeted cleanup rather than the crash-prone GUI shutdown path.
    Verify creation times and every current parent-child edge before tree cleanup.
    """
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return dict(success=True, pid=pid, already_exited=True)
    if root.create_time() != created or root.ppid() != os.getpid():
        raise RuntimeError("CST session ownership changed; refusing cleanup")
    pending = [root]
    while pending:
        parent = pending.pop()
        for child in parent.children():
            try:
                if child.create_time() < parent.create_time():
                    raise RuntimeError("CST child predates parent; refusing tree cleanup")
                pending.append(child)
            except psutil.NoSuchProcess:
                pass
    result = connection.close_targeted(pid_override=pid, timeout_s=15)
    if not result["success"]:
        raise RuntimeError(f"Private CST cleanup failed: {result}")
    return result
