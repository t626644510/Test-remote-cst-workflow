from __future__ import annotations

from cst_optimization.core.connection import CSTConnection


def test_targeted_close_uses_recorded_pid_without_global_sweep(
    monkeypatch,
) -> None:
    connection = object.__new__(CSTConnection)

    class DeadApi:
        def pid(self):
            raise RuntimeError("connection lost")

    connection._de = DeadApi()
    killed: list[int] = []
    monkeypatch.setattr(
        "cst_optimization.core.cleanup.force_kill_cst",
        lambda pid: killed.append(pid) or True,
    )
    monkeypatch.setattr(
        "cst_optimization.core.connection.verify_process_cleanup",
        lambda pid, timeout_s: pid == 4321 and timeout_s == 15.0,
    )

    result = connection.close_targeted(pid_override=4321)

    assert result["success"] is True
    assert result["pid"] == 4321
    assert result["pid_source"] == "override"
    assert result["com_close_attempted"] is False
    assert result["global_sweep_attempted"] is False
    assert killed == [4321]
    assert connection._de is None


def test_targeted_close_refuses_unverifiable_pid(monkeypatch) -> None:
    connection = object.__new__(CSTConnection)
    connection._de = None
    monkeypatch.setattr(
        "cst_optimization.core.cleanup.force_kill_cst",
        lambda _pid: True,
    )

    result = connection.close_targeted()

    assert result["success"] is False
    assert result["reason"] == "pid_unavailable"
