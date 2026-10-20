"""Optional local CPU affinity and process-tree samples for throughput measurements."""
from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
import threading
import time

import psutil


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
