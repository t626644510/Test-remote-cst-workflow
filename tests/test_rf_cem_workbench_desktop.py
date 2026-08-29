"""No-CST contracts for the RF-CEM Workbench portable profile and launcher."""

from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Iterator
from urllib.parse import urlsplit

import pytest

from rf_cem.workbench.desktop import (
    ACTION_REGISTRY,
    DEFAULT_PROFILE_RELATIVE,
    FixedCommand,
    LauncherConfig,
    OwnedWorkbenchChild,
    WORKBENCH_PAGE_ROUTES,
    WorkbenchDesktopController,
    WorkbenchDesktopError,
    build_fixed_command,
    discover_repository,
    load_launcher_config,
    resolve_repository_context,
    run_fixed_command,
    run_launcher_self_test,
    save_launcher_config,
)
from rf_cem.workbench.profile import (
    WorkbenchProfile,
    inspect_workbench_profile,
    load_workbench_profile,
    rebuild_workbench_profile,
    resolve_workbench_profile,
)
from rf_cem.workbench.registry import RegistryReader


pytestmark = pytest.mark.no_cst

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / DEFAULT_PROFILE_RELATIVE


@pytest.fixture
def repository_scratch() -> Iterator[Path]:
    scratch_root = ROOT / ".codex_tmp"
    scratch_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="desktop-test-", dir=scratch_root) as value:
        yield Path(value)
    try:
        scratch_root.rmdir()
    except OSError:
        pass


@pytest.fixture
def portable_context(repository_scratch: Path):
    canonical = resolve_workbench_profile(ROOT, PROFILE_PATH)
    if canonical.missing_sources():
        pytest.skip("canonical ignored W0-W4 proof inputs are not present")
    mapping = canonical.profile.to_mapping()
    relative_scratch = repository_scratch.relative_to(ROOT).as_posix()
    mapping["profile_id"] = "rf-cem-desktop-test"
    mapping["database"] = f"{relative_scratch}/workbench.sqlite"
    profile_path = repository_scratch / "workbench_profile.v0.json"
    _write_json(profile_path, mapping)
    context = resolve_repository_context(ROOT, profile=profile_path)
    return context


def test_profile_schema_is_strict_portable_and_w5_ready() -> None:
    profile = load_workbench_profile(PROFILE_PATH)
    assert profile.schema_version == "rf_cem_workbench_profile.v0"
    assert profile.optional_w5_bundle is None
    assert not Path(profile.database).is_absolute()
    assert profile.literature_packages == (
        "analysis_outputs/rf_cem_literature_pilot_20260710/frozen_baselines/"
        "sls2.r149.6593e02e/literature_semantics.v0.json",
    )
    assert profile.review_sessions == (
        "analysis_outputs/rf_cem_literature_pilot_20260710/frozen_baselines/"
        "sls2.r149.6593e02e/review_session.v1.json",
    )
    assert profile.family_induction_bundle
    assert profile.observation_contract_bundle

    invalid = profile.to_mapping()
    invalid["database"] = "../outside.sqlite"
    with pytest.raises(ValueError, match="repository-relative"):
        WorkbenchProfile.from_mapping(invalid)


def test_repository_discovery_uses_documented_priority(tmp_path: Path) -> None:
    explicit = discover_repository(explicit=ROOT)
    assert explicit == ROOT

    executable = ROOT / "dist" / "nested" / "RF-CEM-Workbench.exe"
    assert discover_repository(executable_path=executable, cwd=tmp_path) == ROOT

    saved = LauncherConfig(repo_root=str(ROOT))
    assert (
        discover_repository(
            executable_path=tmp_path / "launcher.exe",
            cwd=tmp_path,
            saved_config=saved,
        )
        == ROOT
    )
    with pytest.raises(WorkbenchDesktopError, match="explicit repository is invalid"):
        discover_repository(explicit=tmp_path)


def test_missing_source_has_actionable_diagnostic(repository_scratch: Path) -> None:
    mapping = load_workbench_profile(PROFILE_PATH).to_mapping()
    relative_scratch = repository_scratch.relative_to(ROOT).as_posix()
    mapping["database"] = f"{relative_scratch}/missing.sqlite"
    mapping["family_profile"] = f"{relative_scratch}/missing_family_profile.json"
    profile_path = repository_scratch / "missing_profile.v0.json"
    _write_json(profile_path, mapping)

    resolved = resolve_workbench_profile(ROOT, profile_path)
    status = inspect_workbench_profile(resolved)
    assert status.database_state == "blocked_missing_sources"
    assert "missing_family_profile.json" in status.diagnostic
    assert status.rebuild_required is False


def test_profile_fresh_and_stale_recipe_flows(portable_context) -> None:
    resolved = resolve_workbench_profile(ROOT, portable_context.profile_path)
    missing = inspect_workbench_profile(resolved)
    assert missing.database_state == "missing"
    rebuild_workbench_profile(resolved)
    fresh = inspect_workbench_profile(resolved)
    assert fresh.database_state == "fresh"
    assert all(item["status"] == "fresh" for item in fresh.source_statuses)
    reader = RegistryReader(resolved.database)
    source_kinds = {item["source_kind"] for item in reader.list_sources()}
    assert {"literature_semantics.v0", "review_session.v1"} <= source_kinds
    assert any(
        item["entity_id"].startswith("literature:")
        for item in reader.list_entities("semantic")
    )
    assert any(
        item["entity_id"].startswith("helper2:")
        for item in reader.list_entities("semantic")
    )
    assert reader.list_entities("review")

    mapping = json.loads(portable_context.profile_path.read_text(encoding="utf-8"))
    mapping["profile_id"] = "rf-cem-desktop-test-edited"
    _write_json(portable_context.profile_path, mapping)
    stale = inspect_workbench_profile(resolved)
    assert stale.database_state == "stale"
    assert any(
        item["status"] == "stale_profile_recipe" for item in stale.source_statuses
    )


def test_local_config_round_trip_is_root_confined(repository_scratch: Path) -> None:
    config = LauncherConfig(repo_root=str(ROOT))
    path = repository_scratch / "workbench_launcher_config.v0.json"
    save_launcher_config(config, path, allowed_root=repository_scratch)
    assert load_launcher_config(path) == config

    with pytest.raises(WorkbenchDesktopError, match="escapes"):
        save_launcher_config(
            config,
            repository_scratch.parent / "outside.json",
            allowed_root=repository_scratch,
        )


def test_fixed_action_allowlist_and_shell_injection_rejection(portable_context) -> None:
    expected = {
        "open_workbench",
        "rebuild_database",
        "refresh_status",
        "stop_workbench",
        "open_roadmap",
        "open_project_status",
        "open_analysis_outputs",
        "copy_workbench_url",
        "quick_no_cst_self_check",
        "view_logs",
    }
    assert set(ACTION_REGISTRY) == expected
    for operation in ("rebuild", "serve", "status", "self_test"):
        command = build_fixed_command(portable_context, operation)
        assert isinstance(command.argv, tuple)
        assert command.shell is False
    with pytest.raises(WorkbenchDesktopError, match="not allowlisted"):
        build_fixed_command(portable_context, "status & calc.exe")
    with pytest.raises(WorkbenchDesktopError, match="control characters"):
        FixedCommand("status", ("python", "status\ncalc.exe"), ROOT)


def test_desktop_import_is_thin_and_does_not_load_runtime_stacks() -> None:
    script = (
        "import json, sys; import rf_cem.workbench.desktop; "
        "forbidden=('rf_cem.workbench.indexer','cst','cst_optimization',"
        "'cadquery','OCP','numpy','pandas','scipy','plotly'); "
        "print(json.dumps([name for name in forbidden if name in sys.modules]))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == []


def test_fixed_command_runner_always_passes_shell_false(
    portable_context, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="{}\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    command = build_fixed_command(portable_context, "status")
    run_fixed_command(command)
    assert captured["shell"] is False
    assert captured["argv"] == list(command.argv)


def test_owned_child_start_stop_and_url_capture(portable_context) -> None:
    rebuild_workbench_profile(
        resolve_workbench_profile(ROOT, portable_context.profile_path)
    )
    child = OwnedWorkbenchChild(portable_context)
    url = child.start()
    process = child.process
    try:
        assert child.running
        assert process is not None
        assert url.startswith("http://127.0.0.1:")
        assert "token=" in url
        assert child.start() == url
    finally:
        child.stop()
    assert not child.running
    assert process is not None and process.poll() is not None
    child.stop()


def test_launcher_self_test_is_gui_free(portable_context) -> None:
    rebuild_workbench_profile(
        resolve_workbench_profile(ROOT, portable_context.profile_path)
    )
    report = run_launcher_self_test(
        ROOT,
        profile=portable_context.profile_path.relative_to(ROOT),
    )
    assert report["self_test"] == "pass"
    assert report["repository_discovered"] is True
    assert report["profile_loaded"] is True
    assert report["commands_shell_false"] is True
    assert report["injection_rejected"] is True
    assert report["config_round_trip"] is True


def test_controller_opens_w0_through_w4_and_web_stays_read_only(
    portable_context,
) -> None:
    rebuild_workbench_profile(
        resolve_workbench_profile(ROOT, portable_context.profile_path)
    )
    controller = WorkbenchDesktopController(portable_context, browser_enabled=False)
    url = controller.open_or_start()
    parsed = urlsplit(url)
    try:
        assert tuple(WORKBENCH_PAGE_ROUTES) == (
            "/",
            "/semantic-graphs",
            "/compile-records",
            "/family-induction",
            "/observations",
        )
        for page_url in controller.workbench_page_urls():
            page = urlsplit(page_url)
            connection = HTTPConnection(page.hostname, page.port, timeout=5)
            connection.request("GET", f"{page.path}?{page.query}")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            connection.close()
            assert response.status == 200
            assert "RF-CEM Workbench" in body

        for path, expected in (
            ("/reviews", "sls2::evidence::gallery"),
            ("/semantics", "paper_sls2 classification"),
        ):
            connection = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
            connection.request("GET", f"{path}?{parsed.query}")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            connection.close()
            assert response.status == 200
            assert expected in body

        connection = HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        connection.request("POST", f"/?{parsed.query}", body=b"write=forbidden")
        response = connection.getresponse()
        response.read()
        connection.close()
        assert response.status == 405
    finally:
        controller.stop()


def test_build_script_targets_ignored_real_windows_executable() -> None:
    script = (ROOT / "scripts/build_rf_cem_workbench_desktop.ps1").read_text(
        encoding="utf-8"
    )
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "-m PyInstaller" in script
    assert "--onefile" in script
    assert "--windowed" in script
    assert "RF-CEM-Workbench.exe" in script
    assert "--self-test" in script
    assert "dist/" in ignore


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
