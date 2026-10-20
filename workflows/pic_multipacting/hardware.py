"""Optional local CPU affinity and process-tree samples for throughput measurements."""
from __future__ import annotations

import json
from contextlib import nullcontext
import os
from pathlib import Path
import threading
import time
from typing import Any, TYPE_CHECKING

import psutil

if TYPE_CHECKING:
    from cst_optimization.core.connection import CSTConnection


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


class Sampler:
    """Sample only one newly created CST session and its currently owned descendants.

    CPU times are cumulative seconds, RSS is bytes. Processor numbers are Windows
    logical processor indexes, not physical core numbers. No process is terminated.
    """

    def __init__(self, pid: int, output: Path | None, affinity: list[int] | None = None):
        self.root = psutil.Process(pid)
        self.created = self.root.create_time()
        self.output = output
        self.affinity = affinity
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=6)

    def _run(self) -> None:
        stream = self.output.open("a", encoding="utf-8") if self.output else nullcontext(None)
        with stream as f:
            while not self.stop.is_set():
                rows = []
                try:
                    # Process.create_time() is cached: refresh the object to detect PID reuse.
                    root = psutil.Process(self.root.pid)
                    if root.create_time() != self.created:
                        return
                    pending = [root]
                    owned: dict[int, float] = {}
                    while pending:
                        p = pending.pop(0)
                        try:
                            born = p.create_time()
                            if p.pid != root.pid:
                                parent = p.parent()
                                if (parent is None or parent.pid not in owned
                                        or parent.create_time() != owned[parent.pid]
                                        or born < owned[parent.pid]):
                                    continue
                            if p.pid in owned:
                                continue
                            owned[p.pid] = born
                            pending.extend(p.children())
                            if self.affinity and p.cpu_affinity() != self.affinity:
                                p.cpu_affinity(self.affinity)
                            if f is None:
                                continue
                            cpu = p.cpu_times()
                            rows.append(dict(pid=p.pid, parent=p.ppid(), born=born, name=p.name(),
                                             cpu_s=cpu.user+cpu.system, rss_B=p.memory_info().rss,
                                             affinity=p.cpu_affinity()))
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    return
                if f is not None:
                    f.write(json.dumps(dict(time=time.time(), processes=rows,
                                            available_memory_B=psutil.virtual_memory().available)) + "\n")
                    f.flush()
                self.stop.wait(3)
