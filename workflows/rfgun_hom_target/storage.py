"""Durable WF5 state, immutable template snapshots and shared evaluation DB."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

from cst_optimization.checkpoint import CheckpointManager, EvalRecord
from cst_optimization.evaluation.evaluation_database_schema import (
    EvaluationDatabaseRecord, ParameterIdentity, RawEvaluationPayload,
)
from cst_optimization.evaluation.evaluation_database_storage import (
    EvaluationDatabaseConfig, SQLiteEvaluationDatabase,
)


def atomic_json(path: Path, value: Any) -> None:
    """Flush before atomic replacement; never silently serialize NaN."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def digest(path: Path) -> str:
    """SHA-256 of file bytes, without loading large CST fields into memory."""
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(value: Any) -> str:
    """Deterministic JSON identity for a complete evaluation contract."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     allow_nan=False).encode()).hexdigest()


def project_manifest(project: Path) -> dict[str, str]:
    """Include project and all companion files except transient lock files."""
    folder = project.with_suffix("")
    if not project.is_file() or not folder.is_dir():
        raise ValueError("Template requires a .cst file and its same-name companion directory")
    files = [project] + sorted(p for p in folder.rglob("*")
                              if p.is_file() and p.suffix.lower() not in {".lok", ".lock"})
    return {str(p.relative_to(project.parent)): digest(p) for p in files}


def copy_verified_project(source: Path, destination_dir: Path) -> tuple[Path, dict[str, str]]:
    """Copy a consistent complete project, preserving the source and its locks."""
    source = source.resolve()
    destination_dir = destination_dir.resolve()
    if destination_dir == source.parent or source.with_suffix("") in destination_dir.parents:
        raise ValueError("Project copy destination overlaps its source")
    before = project_manifest(source)
    destination_dir.mkdir(parents=True, exist_ok=False)
    for relative in before:
        target = destination_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.parent / relative, target)
    target_project = destination_dir / source.name
    if before != project_manifest(source) or before != project_manifest(target_project):
        raise RuntimeError("Source changed while copying, or project snapshot is incomplete")
    return target_project, before


class BudgetExhausted(RuntimeError):
    """No further expensive solve may be started."""


class CampaignStore:
    """JSON journal is authoritative; SQLite and shared checkpoint mirror outcomes.

    Only a locally created campaign should be resumed. JSON, rather than pickle,
    is used to restore runtime state. Reservations survive an interrupted solve.
    """

    def __init__(self, root: Path, contract: str, max_solves: int, *, resume: bool = False):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock_stream = (self.root / "campaign.lock").open("a+b")
        if self._lock_stream.tell() == 0:
            self._lock_stream.write(b"0")
            self._lock_stream.flush()
        self._lock_stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._lock_stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._lock_stream.close()
            raise ValueError("Campaign is already owned by another running process") from exc
        try:
            self._initialize(contract, max_solves, resume)
        except BaseException:
            self.close()
            raise

    def _initialize(self, contract: str, max_solves: int, resume: bool) -> None:
        self.path = self.root / "state.json"
        self.max_solves = max_solves
        if self.path.exists():
            if not resume:
                raise ValueError("Campaign exists; use --resume or a new output directory")
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
            if self.state["contract"] != contract:
                raise ValueError("Template/configuration/code fingerprint changed; refusing result reuse")
        else:
            if resume:
                raise ValueError("No campaign state to resume")
            self.state = dict(schema_version=1, contract=contract, solve_count=0,
                              reservations=[], records=[], pending=None, rng_state=None,
                              radius=None, improvements=0, no_improvement=0, status="ready")
            self.save()
        self.db = SQLiteEvaluationDatabase(EvaluationDatabaseConfig(
            enabled=True, path=str(self.root / "evaluations.sqlite")))
        self.db.open()
        self.db.set_run_id(contract)
        self.checkpoint = CheckpointManager(str(self.root / "campaign.ckpt"))

    def save(self) -> None:
        """Commit campaign progress independently of the GP or CST state."""
        atomic_json(self.path, self.state)

    def reserve_solve(self, attempt: str) -> int:
        """Durably consume one solve immediately before starting it."""
        if self.state["solve_count"] >= self.max_solves:
            raise BudgetExhausted(f"CST solve budget {self.max_solves} exhausted")
        self.state["solve_count"] += 1
        self.state["reservations"].append(dict(number=self.state["solve_count"], attempt=attempt))
        self.save()
        return self.state["solve_count"]

    def finish(self, record: dict[str, Any]) -> None:
        """Commit once by evaluation ID; repair DB/checkpoint mirrors on resume."""
        if not any(r["id"] == record["id"] for r in self.state["records"]):
            self.state["records"].append(record)
        self.state["pending"] = None
        self.state.pop("error", None)
        self.save()
        self.sync_mirrors()

    def sync_mirrors(self) -> None:
        """Reconcile journal outcomes to the repository database/checkpoint."""
        present = {((r.get("raw_payload") or {}).get("diagnostics") or {}).get("evaluation_id")
                   for r in self.db.get_all_records()}
        # Storage rows expose diagnostics independently of raw_payload.
        for row in self.db.get_all_records():
            present.add((row.get("diagnostics") or {}).get("evaluation_id"))
        for r in self.state["records"]:
            if r["id"] in present:
                continue
            valid = r["status"] == "valid"
            metrics = {"worst_impedance_ohm_per_m": r["worst"]} if valid else {}
            self.db.insert_final_record(EvaluationDatabaseRecord(
                parameter_identity=ParameterIdentity(list(r["parameters"]), list(r["parameters"].values())),
                status="success" if valid else "solver_failed",
                raw_payload=RawEvaluationPayload(raw_metrics=metrics,
                    objective_values={"log_worst_ratio": r["objective"]} if valid else {},
                    diagnostics={"evaluation_id": r["id"], "status": r["status"],
                                 "error": r.get("error", ""), "source": r.get("source")},
                    artifact_refs={"attempt_dir": r.get("attempt_dir", "")}),
                source="rfgun_hom_target", provenance={"contract": self.state["contract"]}))
        self.checkpoint.iteration = self.state["solve_count"]
        self.checkpoint.rng_state = self.state.get("rng_state") or {}
        self.checkpoint.records = [EvalRecord(x=list(r["parameters"].values()),
            status="completed" if r["status"] == "valid" else "failed_permanent",
            solver_ok=r["status"] == "valid", error=r.get("error", ""),
            raw_values={"worst_impedance_ohm_per_m": r["worst"]} if r["status"] == "valid" else {})
            for r in self.state["records"]]
        self.checkpoint.save()

    def close(self) -> None:
        """Close the database; keep all campaign progress on disk."""
        if hasattr(self, "db"):
            self.db.close()
        if hasattr(self, "_lock_stream") and not self._lock_stream.closed:
            self._lock_stream.close()  # OS releases the lock even after a process crash.
