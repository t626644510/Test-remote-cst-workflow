from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from workflows.rfgun_hom_eigenmode.config import _validate_config
from workflows.rfgun_hom_eigenmode.fields import save_complex_line_npz
from workflows.rfgun_hom_eigenmode.models import (
    ComplexLineField,
    EigenmodeCandidate,
    SolverWindow,
)
from workflows.rfgun_hom_eigenmode.state import CampaignState
from workflows.rfgun_hom_eigenmode.workflow import (
    AttemptFailure,
    CleanupIncompleteError,
    Workflow4Campaign,
)


def _window(window_id: str = "WIN_0001") -> SolverWindow:
    return SolverWindow(
        solver_window_id=window_id,
        cluster_ids=("TC_0001",),
        f_hom_mhz=1000.0,
        search_min_hz=990e6,
        search_max_hz=1010e6,
        coverage_min_hz=999e6,
        coverage_max_hz=1001e6,
    )


def _minimal_campaign(tmp_path: Path) -> Workflow4Campaign:
    campaign = object.__new__(Workflow4Campaign)
    campaign.campaign_dir = tmp_path
    campaign.config = SimpleNamespace(
        fast_retry_attempts=4,
        long_retry_attempts=2,
        fast_retry_backoff_s=(0.0, 0.0, 0.0),
        retry_cooldown_s=0.0,
        max_modes=3,
        long_attempt_threshold_s=120.0,
        template_path=tmp_path / "template.cst",
        field_contract=SimpleNamespace(export_dir=tmp_path / "external"),
    )
    campaign.state = CampaignState(tmp_path / "campaign_state.json")
    campaign.state.initialize(
        input_hash="input",
        template_hash="template",
        config_hash="config",
    )
    campaign._artifact_validation_cache = {}
    window = _window()
    campaign.state.set_window(
        window.solver_window_id,
        "pending",
        window=window.to_dict(),
        init_attempt_count=0,
        long_attempt_count=0,
        attempt_history=[],
    )
    return campaign


def test_workflow4_requires_a_dedicated_new_cst_connection() -> None:
    with pytest.raises(ValueError, match="connect_mode='new'"):
        _validate_config(SimpleNamespace(connect_mode="any"))


def test_successful_transition_clears_active_error_but_keeps_history(
    tmp_path: Path,
) -> None:
    state = CampaignState(tmp_path / "state.json")
    state.initialize(input_hash="i", template_hash="t", config_hash="c")
    state.set_window(
        "W",
        "retry_pending",
        error="old failure",
        failure_class="long_solve",
        failure_history=[{"error": "old failure"}],
    )

    state.set_window("W", "postprocessed", clear_active_error=True)
    record = state.get_window("W")

    assert "error" not in record
    assert "failure_class" not in record
    assert record["failure_history"] == [{"error": "old failure"}]


def test_fast_failures_get_four_clean_attempts(monkeypatch, tmp_path: Path) -> None:
    campaign = _minimal_campaign(tmp_path)
    window = _window()
    calls = 0

    def fake_run(_window: SolverWindow, _attempt: int) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls < 4:
            raise AttemptFailure("fast", failure_class="init_fast")
        return {
            "failed": False,
            "mode_count": 1,
            "mode_count_censored": False,
            "attempt_dir": "attempt",
            "candidates": [],
        }

    monkeypatch.setattr(campaign, "_run_window", fake_run)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    outcome = campaign._run_window_with_retries(window)

    assert outcome["failed"] is False
    assert calls == 4
    assert campaign.state.get_window(window.solver_window_id)[
        "init_attempt_count"
    ] == 3


def test_two_long_failures_enter_avoid_retry(tmp_path: Path) -> None:
    campaign = _minimal_campaign(tmp_path)
    window = _window()
    calls = 0

    def fake_run(_window: SolverWindow, _attempt: int) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise AttemptFailure(
            "long",
            failure_class="long_solve",
            elapsed_s=1000,
        )

    campaign._run_window = fake_run  # type: ignore[method-assign]

    outcome = campaign._run_window_with_retries(window)
    record = campaign.state.get_window(window.solver_window_id)

    assert outcome["failed"] is True
    assert calls == 2
    assert record["status"] == "avoid_retry"
    assert record["long_attempt_count"] == 2


def test_force_retry_resets_an_avoid_window_budget(
    monkeypatch, tmp_path: Path
) -> None:
    campaign = _minimal_campaign(tmp_path)
    window = _window()
    campaign.state.set_window(
        window.solver_window_id,
        "avoid_retry",
        init_attempt_count=4,
        long_attempt_count=2,
    )
    calls = 0

    def fake_run(_window: SolverWindow, _attempt: int) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "failed": False,
            "mode_count": 1,
            "mode_count_censored": False,
            "attempt_dir": "attempt",
            "candidates": [],
        }

    monkeypatch.setattr(campaign, "_run_window", fake_run)

    assert campaign._resume_decision(window, force_retry=True) == "run_forced"
    outcome = campaign._run_window_with_retries(window, force_retry=True)

    assert outcome["failed"] is False
    assert calls == 1
    record = campaign.state.get_window(window.solver_window_id)
    assert record["init_attempt_count"] == 0
    assert record["long_attempt_count"] == 0


def test_schema2_stale_running_is_migrated_and_charged_once(
    tmp_path: Path,
) -> None:
    campaign = _minimal_campaign(tmp_path)
    window = _window()
    attempt = (
        tmp_path / "windows" / window.solver_window_id / "attempt_001"
    )
    attempt.mkdir(parents=True)
    (attempt / "attempt_metadata.json").write_text(
        json.dumps(
            {
                "attempt_id": "attempt_001",
                "started_at": "2026-06-20T00:00:00+00:00",
                "phase": "solve",
            }
        ),
        encoding="utf-8",
    )
    campaign.state.set_window(
        window.solver_window_id,
        "running",
        attempt_id="attempt_001",
        attempt_dir=attempt.relative_to(tmp_path).as_posix(),
        long_attempt_count=0,
    )

    campaign._migrate_stale_running(persist=False)
    first = campaign.state.get_window(window.solver_window_id)
    campaign._migrate_stale_running(persist=False)
    second = campaign.state.get_window(window.solver_window_id)

    assert first["status"] == "interrupted"
    assert first["long_attempt_count"] == 1
    assert second["long_attempt_count"] == 1
    persisted_metadata = json.loads(
        (attempt / "attempt_metadata.json").read_text(encoding="utf-8")
    )
    assert "long_budget_charged" not in persisted_metadata


def test_interrupted_saved_project_retries_extraction_before_solve(
    monkeypatch, tmp_path: Path
) -> None:
    campaign = _minimal_campaign(tmp_path)
    window = _window()
    attempt = (
        tmp_path / "windows" / window.solver_window_id / "attempt_001"
    )
    project = campaign._attempt_project(attempt)
    project.parent.mkdir(parents=True)
    project.write_bytes(b"saved CST")
    export = project.with_suffix("") / "Export" / "3d"
    export.mkdir(parents=True)
    (export / "Mode 1_e.h5").write_bytes(b"fresh E")
    (export / "Mode 1_h.h5").write_bytes(b"fresh H")
    (attempt / "attempt_metadata.json").write_text(
        json.dumps(
            {
                "attempt_id": "attempt_001",
                "phase": "solved",
                "solver_successful": True,
            }
        ),
        encoding="utf-8",
    )
    (attempt / "cst_messages.json").write_text(
        json.dumps(
            [
                {
                    "type": "INFO",
                    "text": (
                        "Mode Frequency Total Q Accuracy\n"
                        "1 1000.000 MHz 10 1e-8"
                    ),
                },
                {
                    "type": "INFO",
                    "text": "Eigenmode solver successful",
                },
            ]
        ),
        encoding="utf-8",
    )
    campaign.state.set_window(
        window.solver_window_id,
        "interrupted",
        attempt_id="attempt_001",
        attempt_dir=attempt.relative_to(tmp_path).as_posix(),
        long_attempt_count=1,
    )
    expected = {
        "failed": False,
        "mode_count": 1,
        "mode_count_censored": False,
        "attempt_dir": attempt.relative_to(tmp_path).as_posix(),
        "candidates": [],
    }
    calls = 0

    def fake_extract(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return expected

    monkeypatch.setattr(campaign, "_extract_attempt", fake_extract)

    assert campaign._recover_saved_extraction(window) == expected
    assert calls == 1
    assert campaign._read_attempt_metadata(attempt)["recovery"] == (
        "saved_result_extraction"
    )


def test_config_hash_update_does_not_skip_legacy_migration(
    tmp_path: Path,
) -> None:
    input_csv = tmp_path / "input.csv"
    template = tmp_path / "template.cst"
    config_file = tmp_path / "config.yaml"
    input_csv.write_text("input", encoding="utf-8")
    template.write_text("template", encoding="utf-8")
    config_file.write_text("new config", encoding="utf-8")
    state_path = tmp_path / "campaign_state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "input_hash": hashlib.sha256(b"input").hexdigest(),
                "template_hash": hashlib.sha256(b"template").hexdigest(),
                "config_hash": "legacy-config",
                "windows": {
                    "WIN_0001": {
                        "status": "failed",
                        "window": _window("WIN_0001").to_dict(),
                    },
                    "WIN_0002": {
                        "status": "running",
                        "window": _window("WIN_0002").to_dict(),
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    campaign = object.__new__(Workflow4Campaign)
    campaign.config = SimpleNamespace(
        input_csv=input_csv,
        template_path=template,
        source_config_path=config_file,
    )
    campaign.campaign_dir = tmp_path
    campaign.resume = True
    campaign.state = CampaignState(state_path)
    campaign.windows = [_window("WIN_0001"), _window("WIN_0002")]

    campaign.initialize(
        require_template=True,
        allow_config_change=True,
        persist=False,
    )

    assert campaign.state.get_window("WIN_0001")["status"] == (
        "avoid_retry_legacy"
    )
    interrupted = campaign.state.get_window("WIN_0002")
    assert interrupted["status"] == "interrupted"
    assert interrupted["long_attempt_count"] == 1


def test_template_migration_preview_is_read_only_and_adoption_resets_only_long(
    monkeypatch, tmp_path: Path
) -> None:
    input_csv = tmp_path / "input.csv"
    template = tmp_path / "template.cst"
    config_file = tmp_path / "config.yaml"
    input_csv.write_text("input", encoding="utf-8")
    template.write_text("old template", encoding="utf-8")
    config_file.write_text("config", encoding="utf-8")
    campaign = object.__new__(Workflow4Campaign)
    campaign.config = SimpleNamespace(
        input_csv=input_csv,
        template_path=template,
        source_config_path=config_file,
        long_attempt_threshold_s=120.0,
    )
    campaign.campaign_dir = tmp_path
    campaign.resume = True
    campaign.state = CampaignState(tmp_path / "campaign_state.json")
    old_hash = hashlib.sha256(b"old template").hexdigest()
    campaign.state.initialize(
        input_hash=hashlib.sha256(b"input").hexdigest(),
        template_hash=old_hash,
        config_hash=hashlib.sha256(b"config").hexdigest(),
    )
    campaign.windows = [
        _window("DONE"),
        _window("LONG"),
        _window("FAST"),
        _window("PENDING"),
    ]
    campaign.state.set_window(
        "DONE",
        "postprocessed",
        window=_window("DONE").to_dict(),
    )
    campaign.state.set_window(
        "LONG",
        "avoid_retry",
        window=_window("LONG").to_dict(),
        init_attempt_count=1,
        long_attempt_count=2,
        error="old long failure",
        failure_class="long_solve",
    )
    campaign.state.set_window(
        "FAST",
        "avoid_retry_legacy",
        window=_window("FAST").to_dict(),
        init_attempt_count=2,
        long_attempt_count=0,
    )
    campaign.state.set_window(
        "PENDING",
        "pending",
        window=_window("PENDING").to_dict(),
        init_attempt_count=0,
        long_attempt_count=0,
    )
    before = campaign.state.path.read_bytes()
    template.write_text("new template", encoding="utf-8")

    campaign.initialize_template_migration(persist=False)
    preview = campaign.template_migration_preview()

    assert campaign.state.path.read_bytes() == before
    assert preview["changed"] is True
    assert preview["reset_window_ids"] == ["LONG"]
    assert preview["pure_fast_avoid_ids"] == ["FAST"]
    assert preview["run_count_after_adoption"] == 2

    monkeypatch.setattr(campaign, "_write_manifest", lambda: None)
    campaign.adopt_template_revision(
        retry_scope="long-related",
        change_note="disable adaptive meshing",
    )
    reset = campaign.state.get_window("LONG")
    assert reset["status"] == "retry_pending"
    assert reset["init_attempt_count"] == 0
    assert reset["long_attempt_count"] == 0
    assert reset["retry_generation"] == 1
    assert len(reset["retry_generation_history"]) == 1
    assert reset["retry_generation_history"][0]["long_attempt_count"] == 2
    assert "error" not in reset
    assert campaign.state.get_window("FAST")["status"] == (
        "avoid_retry_legacy"
    )
    assert campaign.state.get_window("DONE")["status"] == "postprocessed"
    assert campaign.state.data["template_hash"] == hashlib.sha256(
        b"new template"
    ).hexdigest()
    with pytest.raises(RuntimeError, match="hash is unchanged"):
        campaign.adopt_template_revision(
            retry_scope="long-related",
            change_note="duplicate adoption",
        )


def test_cleanup_failure_enters_non_runnable_terminal_state(
    tmp_path: Path,
) -> None:
    campaign = _minimal_campaign(tmp_path)
    attempt = tmp_path / "windows" / "WIN_0001" / "attempt_001"
    attempt.mkdir(parents=True)
    (attempt / "attempt_metadata.json").write_text(
        json.dumps(
            {
                "window": _window().to_dict(),
                "attempt_id": "attempt_001",
            }
        ),
        encoding="utf-8",
    )

    class FailedConnection:
        def close_targeted(self, **_kwargs):
            return {
                "success": False,
                "pid": 123,
                "pid_source": "override",
                "force_kill_ok": False,
                "exit_verified": False,
                "elapsed_s": 1.0,
                "reason": "targeted_process_cleanup_failed",
            }

    with pytest.raises(CleanupIncompleteError):
        campaign._close_attempt_connection(
            FailedConnection(),  # type: ignore[arg-type]
            window_id="WIN_0001",
            attempt_dir=attempt,
            phase="solve_close",
            recorded_pid=123,
        )

    record = campaign.state.get_window("WIN_0001")
    assert record["status"] == "cleanup_incomplete"
    assert campaign._resume_decision(_window()) == "avoid"


def _write_mode_artifacts(
    root: Path,
    *,
    window_id: str,
    attempt_id: str,
    mode_number: int,
    frequency_hz: float,
    reported_modes: tuple[int, ...],
    include_hdf5: bool,
    derived_valid: bool,
) -> None:
    attempt = root / "windows" / window_id / attempt_id
    attempt.mkdir(parents=True, exist_ok=True)
    window = _window(window_id)
    (attempt / "attempt_metadata.json").write_text(
        json.dumps({"window": window.to_dict(), "attempt_id": attempt_id}),
        encoding="utf-8",
    )
    base_frequency_hz = frequency_hz - (mode_number - 1) * 1000
    mode_rows = "\n".join(
        f"  {number} "
        f"{(base_frequency_hz + (number - 1) * 1000) / 1e6:.6f} "
        "MHz 10 1e-8"
        for number in reported_modes
    )
    (attempt / "cst_messages.json").write_text(
        json.dumps(
            [
                {
                    "type": "INFO",
                    "text": (
                        "Eigenmode solver results:\n"
                        "Mode Frequency Total Q Accuracy\n"
                        f"{mode_rows}"
                    ),
                },
                {"type": "INFO", "text": "Eigenmode solver successful"},
            ]
        ),
        encoding="utf-8",
    )
    mode_id = f"MODE_{window_id}_{attempt_id.upper()}_M{mode_number}"
    candidate = EigenmodeCandidate(
        mode_id=mode_id,
        solver_window_id=window_id,
        attempt_id=attempt_id,
        mode_number=mode_number,
        frequency_hz=frequency_hz,
        derived_valid=derived_valid,
    )
    candidate_path = attempt / "mode_candidates.json"
    candidates = (
        json.loads(candidate_path.read_text(encoding="utf-8"))
        if candidate_path.is_file()
        else []
    )
    candidates.append(candidate.to_dict())
    candidate_path.write_text(
        json.dumps(candidates),
        encoding="utf-8",
    )
    artifact_path = attempt / "artifact_index.json"
    archived = (
        json.loads(artifact_path.read_text(encoding="utf-8")).get(
            "archived", []
        )
        if artifact_path.is_file()
        else []
    )
    if include_hdf5:
        raw_3d = attempt / "raw" / "3d"
        raw_3d.mkdir(parents=True, exist_ok=True)
        for kind in ("e", "h"):
            name = f"Mode {mode_number}_{kind}.h5"
            payload = f"{mode_id}:{kind}".encode()
            path = raw_3d / name
            path.write_bytes(payload)
            archived.append(
                {
                    "relative_path": name,
                    "size": len(payload),
                    "mtime_ns": path.stat().st_mtime_ns,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    artifact_path.write_text(
        json.dumps({"archived": archived}),
        encoding="utf-8",
    )
    z = np.linspace(-0.01, 0.01, 5)
    field = ComplexLineField(z_m=z, ez_v_per_m=np.ones(5, dtype=complex))
    field_root = root / "fields" / mode_id
    for point in ("center", "x_plus", "x_minus", "y_plus", "y_minus"):
        save_complex_line_npz(field_root / f"{point}.npz", field)


def test_fixed_snapshot_shape_filters_one_stale_and_keeps_26_valid(
    tmp_path: Path,
) -> None:
    campaign = object.__new__(Workflow4Campaign)
    campaign.campaign_dir = tmp_path
    campaign.config = SimpleNamespace(max_modes=3)
    campaign._artifact_validation_cache = {}

    # Ten attempts x three candidates reproduce the audited 30-candidate
    # snapshot. The final candidate is absent from the final mode table and
    # has no fresh E/H pair, so it must be rejected as stale.
    for index in range(30):
        attempt_index, mode_offset = divmod(index, 3)
        window_id = f"WIN_{attempt_index + 1:04d}"
        mode_number = mode_offset + 1
        stale = index == 29
        _write_mode_artifacts(
            tmp_path,
            window_id=window_id,
            attempt_id="attempt_001",
            mode_number=mode_number,
            frequency_hz=1e9 + index * 1000,
            reported_modes=(1, 2) if stale else (1, 2, 3),
            include_hdf5=not stale,
            derived_valid=index < 26,
        )

    candidates = campaign._load_all_candidates()

    assert len(candidates) == 29
    assert sum(candidate.derived_valid for candidate in candidates) == 26
    assert sum(not candidate.derived_valid for candidate in candidates) == 3


def test_same_mode_number_with_wrong_final_frequency_is_rejected(
    tmp_path: Path,
) -> None:
    campaign = object.__new__(Workflow4Campaign)
    campaign.campaign_dir = tmp_path
    campaign.config = SimpleNamespace(max_modes=3)
    campaign._artifact_validation_cache = {}
    _write_mode_artifacts(
        tmp_path,
        window_id="WIN_0001",
        attempt_id="attempt_001",
        mode_number=1,
        frequency_hz=1e9,
        reported_modes=(1,),
        include_hdf5=True,
        derived_valid=True,
    )
    message_path = (
        tmp_path
        / "windows"
        / "WIN_0001"
        / "attempt_001"
        / "cst_messages.json"
    )
    message_path.write_text(
        json.dumps(
            [
                {
                    "type": "INFO",
                    "text": (
                        "Mode Frequency Total Q Accuracy\n"
                        "1 1000.500 MHz 10 1e-8"
                    ),
                }
            ]
        ),
        encoding="utf-8",
    )

    assert campaign._load_all_candidates() == []


def test_corrupted_archived_hdf5_is_rejected(tmp_path: Path) -> None:
    campaign = object.__new__(Workflow4Campaign)
    campaign.campaign_dir = tmp_path
    campaign.config = SimpleNamespace(max_modes=3)
    campaign._artifact_validation_cache = {}
    _write_mode_artifacts(
        tmp_path,
        window_id="WIN_0001",
        attempt_id="attempt_001",
        mode_number=1,
        frequency_hz=1e9,
        reported_modes=(1,),
        include_hdf5=True,
        derived_valid=True,
    )
    corrupt = (
        tmp_path
        / "windows"
        / "WIN_0001"
        / "attempt_001"
        / "raw"
        / "3d"
        / "Mode 1_e.h5"
    )
    corrupt.write_bytes(b"corrupt")

    assert campaign._load_all_candidates() == []


def test_legacy_candidate_is_attributed_to_initial_template_revision(
    tmp_path: Path,
) -> None:
    campaign = object.__new__(Workflow4Campaign)
    campaign.campaign_dir = tmp_path
    campaign.config = SimpleNamespace(max_modes=3)
    campaign._artifact_validation_cache = {}
    campaign.state = CampaignState(tmp_path / "campaign_state.json")
    campaign.state.initialize(
        input_hash="input",
        template_hash="a" * 64,
        config_hash="config",
    )
    _write_mode_artifacts(
        tmp_path,
        window_id="WIN_0001",
        attempt_id="attempt_001",
        mode_number=1,
        frequency_hz=1e9,
        reported_modes=(1,),
        include_hdf5=True,
        derived_valid=True,
    )

    candidates = campaign._load_all_candidates()

    assert len(candidates) == 1
    assert candidates[0].template_revision_id == "TR_aaaaaaaaaaaa"
    assert candidates[0].template_hash == "a" * 64
