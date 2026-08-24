"""Safe Windows desktop launcher for the local read-only RF-CEM Workbench.

The launcher is intentionally thin.  It discovers a reviewed repository,
validates its portable profile, and invokes only fixed ``rf_cem.workbench``
commands through the repository virtual environment with ``shell=False``.
It never imports CST, exposes a command textbox, or terminates a process that
it did not start itself.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .profile import (
    WorkbenchProfile,
    WorkbenchProfileError,
    WorkbenchProfileStatus,
    load_workbench_profile,
)


DEFAULT_PROFILE_RELATIVE = Path("config/rf_cem_workbench_profile.v0.json")
LAUNCHER_CONFIG_SCHEMA_VERSION = "rf_cem_workbench_launcher_config.v0"
LOCAL_CONFIG_DIRECTORY_NAME = "RF-CEM"
LOCAL_CONFIG_FILE_NAME = "workbench_launcher_config.v0.json"
LOG_FILE_NAME = "workbench_desktop.log"

WORKBENCH_PAGE_ROUTES = (
    "/",
    "/semantic-graphs",
    "/compile-records",
    "/family-induction",
    "/observations",
)


@dataclass(frozen=True)
class ActionSpec:
    """One immutable native-launcher action exposed to the user."""

    action_id: str
    label: str


_ACTION_SPECS = (
    ActionSpec("open_workbench", "Open / Start Workbench"),
    ActionSpec("rebuild_database", "Rebuild Database"),
    ActionSpec("refresh_status", "Refresh Source Status"),
    ActionSpec("stop_workbench", "Stop Workbench"),
    ActionSpec("open_roadmap", "Open Roadmap"),
    ActionSpec("open_project_status", "Open Project Status"),
    ActionSpec("open_analysis_outputs", "Open analysis_outputs"),
    ActionSpec("copy_workbench_url", "Copy Workbench URL"),
    ActionSpec("quick_no_cst_self_check", "Run Quick no-CST Self Check"),
    ActionSpec("view_logs", "View Logs"),
)
ACTION_REGISTRY: Mapping[str, ActionSpec] = {
    item.action_id: item for item in _ACTION_SPECS
}

_COMMAND_OPERATIONS = frozenset({"rebuild", "serve", "status", "self_test"})
_UNSAFE_COMMAND_FRAGMENTS = (
    "cst.interface",
    "designenvironment",
    "license",
    "cleanup",
    "workflow_5",
    "kill",
)
_WORKBENCH_URL_RE = re.compile(r"^workbench_url=(https?://[^\s]+)$")


class WorkbenchDesktopError(RuntimeError):
    """Raised for an actionable launcher discovery or runtime failure."""


@dataclass(frozen=True)
class LauncherConfig:
    """User-local repository selection; tracked profiles stay portable."""

    repo_root: str
    profile: str = DEFAULT_PROFILE_RELATIVE.as_posix()
    schema_version: str = LAUNCHER_CONFIG_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LAUNCHER_CONFIG_SCHEMA_VERSION:
            raise WorkbenchDesktopError("unsupported launcher config schema")
        _safe_text(self.repo_root, "repo_root")
        _safe_text(self.profile, "profile")
        profile = Path(self.profile)
        if profile.is_absolute() or ".." in profile.parts:
            raise WorkbenchDesktopError("launcher profile must be repository-relative")

    def to_mapping(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "repo_root": self.repo_root,
            "profile": self.profile,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LauncherConfig":
        required = {"schema_version", "repo_root", "profile"}
        if set(value) != required:
            raise WorkbenchDesktopError(
                "launcher config keys mismatch; "
                f"missing={sorted(required - set(value))}, "
                f"extra={sorted(set(value) - required)}"
            )
        if not all(isinstance(value[key], str) for key in required):
            raise WorkbenchDesktopError("launcher config values must be strings")
        return cls(
            schema_version=value["schema_version"],
            repo_root=value["repo_root"],
            profile=value["profile"],
        )


@dataclass(frozen=True)
class RepositoryContext:
    """Validated paths used by every fixed launcher operation."""

    repo_root: Path
    profile_path: Path
    python_executable: Path
    profile: WorkbenchProfile
    database: Path


@dataclass(frozen=True)
class FixedCommand:
    """A command that can only be constructed by the fixed operation builder."""

    operation: str
    argv: tuple[str, ...]
    cwd: Path
    shell: bool = False

    def __post_init__(self) -> None:
        if self.operation not in _COMMAND_OPERATIONS:
            raise WorkbenchDesktopError(f"operation is not allowlisted: {self.operation}")
        if self.shell is not False:
            raise WorkbenchDesktopError("launcher commands must use shell=False")
        if not self.argv:
            raise WorkbenchDesktopError("launcher command must not be empty")
        for argument in self.argv:
            _safe_text(argument, "command argument")
        joined = " ".join(self.argv).lower()
        if any(fragment in joined for fragment in _UNSAFE_COMMAND_FRAGMENTS):
            raise WorkbenchDesktopError("command contains a forbidden operation")


def local_config_directory(*, local_app_data: Path | None = None) -> Path:
    """Return the validated user-local RF-CEM launcher directory."""

    if local_app_data is None:
        configured = os.environ.get("LOCALAPPDATA")
        base = Path(configured) if configured else Path.home() / "AppData" / "Local"
    else:
        base = local_app_data
    return (base.expanduser().resolve() / LOCAL_CONFIG_DIRECTORY_NAME).resolve()


def local_config_path(*, local_app_data: Path | None = None) -> Path:
    return local_config_directory(local_app_data=local_app_data) / LOCAL_CONFIG_FILE_NAME


def load_launcher_config(path: Path) -> LauncherConfig | None:
    """Load an optional strict local config; a missing file is normal."""

    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkbenchDesktopError(f"cannot load launcher config: {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise WorkbenchDesktopError("launcher config must be a JSON object")
    return LauncherConfig.from_mapping(value)


def save_launcher_config(
    config: LauncherConfig,
    path: Path,
    *,
    allowed_root: Path | None = None,
) -> None:
    """Atomically save config inside the expected user-local directory."""

    root = (allowed_root or local_config_directory()).resolve()
    target = path.resolve()
    _require_inside(root, target, "launcher config")
    root.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=root,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(config.to_mapping(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise


def discover_repository(
    *,
    explicit: Path | None = None,
    executable_path: Path | None = None,
    cwd: Path | None = None,
    saved_config: LauncherConfig | None = None,
) -> Path:
    """Discover a repository in the documented, deterministic priority order."""

    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if not _is_repository_root(candidate):
            raise WorkbenchDesktopError(f"explicit repository is invalid: {candidate}")
        return candidate

    candidates: list[Path] = []
    if executable_path is not None:
        executable = executable_path.expanduser().resolve()
        candidates.extend(_parent_candidates(executable.parent))
    candidates.extend(_parent_candidates((cwd or Path.cwd()).expanduser().resolve()))
    if saved_config is not None:
        candidates.append(Path(saved_config.repo_root).expanduser().resolve())

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if _is_repository_root(candidate):
            return candidate
    raise WorkbenchDesktopError(
        "RF-CEM repository was not found in executable parents, cwd parents, "
        "or saved local config"
    )


def detect_repository_python(repo_root: Path) -> Path:
    """Return the repository virtual-environment Python executable."""

    root = _validated_repository_root(repo_root)
    candidates = (
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise WorkbenchDesktopError(
        "repository Python is missing; expected .venv\\Scripts\\python.exe"
    )


def resolve_repository_context(
    repo_root: Path,
    *,
    profile: Path = DEFAULT_PROFILE_RELATIVE,
) -> RepositoryContext:
    """Resolve and validate every path used by the launcher."""

    root = _validated_repository_root(repo_root)
    profile_path = profile if profile.is_absolute() else root / profile
    profile_path = profile_path.resolve()
    _require_inside(root, profile_path, "Workbench profile")
    loaded_profile = load_workbench_profile(profile_path)
    database = _require_inside(
        root,
        root / loaded_profile.database,
        "Workbench database",
    )
    for source in loaded_profile.declared_source_paths():
        _require_inside(root, root / source, "Workbench profile source")
    return RepositoryContext(
        repo_root=root,
        profile_path=profile_path,
        python_executable=detect_repository_python(root),
        profile=loaded_profile,
        database=database,
    )


def build_fixed_command(context: RepositoryContext, operation: str) -> FixedCommand:
    """Build one command from the closed launcher operation set."""

    if operation not in _COMMAND_OPERATIONS:
        raise WorkbenchDesktopError(f"operation is not allowlisted: {operation}")
    common = (
        str(context.python_executable),
        "-m",
        "rf_cem.workbench",
    )
    profile_args = (
        "--repo-root",
        str(context.repo_root),
        "--profile",
        str(context.profile_path),
    )
    if operation == "self_test":
        argv = (
            str(context.python_executable),
            "-m",
            "rf_cem.workbench.desktop",
            "--self-test",
            "--repo-root",
            str(context.repo_root),
            "--no-browser",
        )
    elif operation == "serve":
        argv = (*common, "serve", *profile_args, "--port", "0")
    else:
        argv = (*common, operation, *profile_args)
    return FixedCommand(operation=operation, argv=argv, cwd=context.repo_root)


def run_fixed_command(
    command: FixedCommand,
    *,
    timeout: float = 300.0,
) -> subprocess.CompletedProcess[str]:
    """Run one pre-built fixed command without a shell."""

    completed = subprocess.run(
        list(command.argv),
        cwd=str(command.cwd),
        shell=command.shell,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "no diagnostic").strip()
        raise WorkbenchDesktopError(
            f"fixed action {command.operation!r} failed ({completed.returncode}): {detail}"
        )
    return completed


class OwnedWorkbenchChild:
    """Own exactly one Workbench subprocess and never inspect unrelated processes."""

    def __init__(
        self,
        context: RepositoryContext,
        *,
        log_line: Callable[[str], None] | None = None,
    ) -> None:
        self.context = context
        self._log_line = log_line or (lambda _line: None)
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._url_event = threading.Event()
        self._workbench_url: str | None = None
        self._startup_error: str | None = None
        self._lock = threading.Lock()

    @property
    def process(self) -> subprocess.Popen[str] | None:
        return self._process

    @property
    def workbench_url(self) -> str | None:
        return self._workbench_url

    @property
    def running(self) -> bool:
        process = self._process
        return process is not None and process.poll() is None

    def start(self, *, timeout: float = 20.0) -> str:
        """Start one server or return the URL of the already-owned server."""

        with self._lock:
            if self.running:
                if self._workbench_url is None:
                    raise WorkbenchDesktopError("owned Workbench is starting without a URL")
                return self._workbench_url
            self._workbench_url = None
            self._startup_error = None
            self._url_event.clear()
            command = build_fixed_command(self.context, "serve")
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                self._process = subprocess.Popen(
                    list(command.argv),
                    cwd=str(command.cwd),
                    shell=command.shell,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags,
                )
            except OSError as exc:
                raise WorkbenchDesktopError(f"cannot start Workbench child: {exc}") from exc
            self._reader_thread = threading.Thread(
                target=self._read_output,
                name="rf-cem-workbench-child-output",
                daemon=True,
            )
            self._reader_thread.start()

        if not self._url_event.wait(timeout):
            exit_code = self._process.poll() if self._process is not None else None
            self.stop()
            raise WorkbenchDesktopError(
                f"Workbench child did not publish a URL within {timeout:g}s; exit={exit_code}"
            )
        if self._workbench_url is None:
            detail = self._startup_error or "child exited before publishing its URL"
            self.stop()
            raise WorkbenchDesktopError(f"Workbench child failed to start: {detail}")
        return self._workbench_url

    def stop(self, *, timeout: float = 8.0) -> None:
        """Stop only the child process held by this object."""

        with self._lock:
            process = self._process
            self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=timeout)
        self._log_line(f"Workbench child stopped (exit={process.returncode})")

    def _read_output(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for raw_line in process.stdout:
            line = raw_line.rstrip("\r\n")
            match = _WORKBENCH_URL_RE.fullmatch(line)
            if match:
                candidate = match.group(1)
                _validate_workbench_url(candidate)
                self._workbench_url = candidate
                self._url_event.set()
                self._log_line("Workbench URL received (token redacted)")
            else:
                self._log_line(line)
        if not self._url_event.is_set():
            self._startup_error = f"child exit={process.poll()}"
            self._url_event.set()


class WorkbenchDesktopController:
    """Non-GUI launcher orchestration used by both tkinter and tests."""

    def __init__(
        self,
        context: RepositoryContext,
        *,
        browser_enabled: bool = True,
        logger: logging.Logger | None = None,
    ) -> None:
        self.context = context
        self.browser_enabled = browser_enabled
        self.logger = logger or logging.getLogger("rf_cem.workbench.desktop")
        self.child = OwnedWorkbenchChild(context, log_line=self.logger.info)

    def refresh_status(self) -> WorkbenchProfileStatus:
        completed = run_fixed_command(build_fixed_command(self.context, "status"))
        status = _parse_profile_status(completed.stdout)
        self.logger.info("Profile status: %s - %s", status.database_state, status.diagnostic)
        return status

    def rebuild_database(self) -> WorkbenchProfileStatus:
        if self.child.running:
            raise WorkbenchDesktopError("stop the owned Workbench before rebuilding")
        completed = run_fixed_command(build_fixed_command(self.context, "rebuild"))
        self.logger.info("Database rebuilt: %s", completed.stdout.strip())
        status = self.refresh_status()
        if not status.fresh:
            raise WorkbenchDesktopError(
                f"database rebuild completed but status is {status.database_state}: {status.diagnostic}"
            )
        return status

    def open_or_start(self) -> str:
        status = self.refresh_status()
        if status.database_state == "blocked_missing_sources":
            raise WorkbenchDesktopError(status.diagnostic)
        if status.rebuild_required:
            status = self.rebuild_database()
        if not status.fresh:
            raise WorkbenchDesktopError(
                f"Workbench database is not fresh: {status.diagnostic}"
            )
        url = self.child.start()
        if self.browser_enabled:
            webbrowser.open(url, new=2)
        return url

    def stop(self) -> None:
        self.child.stop()

    def run_quick_self_check(self) -> str:
        completed = run_fixed_command(
            build_fixed_command(self.context, "self_test"), timeout=120.0
        )
        output = completed.stdout.strip()
        self.logger.info("Quick no-CST self-check passed: %s", output or "exit 0")
        return output

    def fixed_repository_path(self, action_id: str) -> Path:
        relative_by_action = {
            "open_roadmap": Path("docs/RF_CEM_ROADMAP_AND_ARCHITECTURE.md"),
            "open_project_status": Path("docs/PROJECT_STATUS_CONTEXT.md"),
            "open_analysis_outputs": Path("analysis_outputs"),
        }
        if action_id not in relative_by_action:
            raise WorkbenchDesktopError(f"path action is not allowlisted: {action_id}")
        target = (self.context.repo_root / relative_by_action[action_id]).resolve()
        _require_inside(self.context.repo_root, target, action_id)
        if not target.exists():
            raise WorkbenchDesktopError(f"fixed path is missing: {target}")
        return target

    def open_fixed_repository_path(self, action_id: str) -> Path:
        target = self.fixed_repository_path(action_id)
        _open_local_path(target)
        return target

    def workbench_page_urls(self) -> tuple[str, ...]:
        url = self.child.workbench_url
        if url is None:
            raise WorkbenchDesktopError("Workbench has not published a URL")
        parsed = urlsplit(url)
        query = parse_qs(parsed.query, strict_parsing=True)
        token_values = query.get("token", [])
        if len(token_values) != 1:
            raise WorkbenchDesktopError("Workbench URL token is invalid")
        token = token_values[0]
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return tuple(f"{origin}{route}?token={token}" for route in WORKBENCH_PAGE_ROUTES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="RF-CEM-Workbench",
        description="Open the local read-only RF-CEM Workbench desktop launcher.",
    )
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def run_launcher_self_test(repo_root: Path, *, profile: Path) -> dict[str, Any]:
    """Exercise launcher contracts without GUI, browser, network, or CST."""

    discovered = discover_repository(explicit=repo_root)
    context = resolve_repository_context(discovered, profile=profile)
    loaded_profile = context.profile
    missing_sources = tuple(
        source
        for source in _resolved_declared_sources(context)
        if not source.exists()
    )
    database_state = (
        "blocked_missing_sources"
        if missing_sources
        else ("present" if context.database.is_file() else "missing")
    )
    commands = {
        operation: build_fixed_command(context, operation)
        for operation in sorted(_COMMAND_OPERATIONS)
    }
    try:
        build_fixed_command(context, "status & calc.exe")
    except WorkbenchDesktopError:
        injection_rejected = True
    else:
        injection_rejected = False
    if not injection_rejected:
        raise WorkbenchDesktopError("non-allowlisted operation was accepted")
    if tuple(ACTION_REGISTRY) != tuple(item.action_id for item in _ACTION_SPECS):
        raise WorkbenchDesktopError("fixed action registry order changed unexpectedly")
    if any(command.shell for command in commands.values()):
        raise WorkbenchDesktopError("a fixed command enables a shell")
    with tempfile.TemporaryDirectory(prefix="rf-cem-launcher-self-test-") as raw_temp:
        temporary_root = Path(raw_temp).resolve()
        config_path = temporary_root / LOCAL_CONFIG_FILE_NAME
        profile_relative = context.profile_path.relative_to(context.repo_root).as_posix()
        expected_config = LauncherConfig(
            repo_root=str(context.repo_root), profile=profile_relative
        )
        save_launcher_config(
            expected_config,
            config_path,
            allowed_root=temporary_root,
        )
        loaded_config = load_launcher_config(config_path)
        if loaded_config != expected_config:
            raise WorkbenchDesktopError("launcher config round-trip failed")
    return {
        "action_count": len(ACTION_REGISTRY),
        "commands_shell_false": True,
        "config_round_trip": True,
        "database_state": database_state,
        "injection_rejected": injection_rejected,
        "profile_id": loaded_profile.profile_id,
        "profile_loaded": True,
        "python": str(context.python_executable),
        "repo_root": str(context.repo_root),
        "repository_discovered": True,
        "self_test": "pass",
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = local_config_path()
    try:
        saved = load_launcher_config(config_path)
    except WorkbenchDesktopError:
        saved = None
    executable_path = Path(sys.executable)
    try:
        root = discover_repository(
            explicit=args.repo_root,
            executable_path=executable_path,
            cwd=Path.cwd(),
            saved_config=saved,
        )
    except WorkbenchDesktopError as exc:
        if args.self_test:
            _write_console(f"error: {exc}", error=True)
            return 2
        selected = _choose_repository_folder(str(exc))
        if selected is None:
            return 2
        root = selected

    profile = args.profile or (
        Path(saved.profile)
        if saved is not None and Path(saved.repo_root).expanduser().resolve() == root
        else DEFAULT_PROFILE_RELATIVE
    )
    try:
        context = resolve_repository_context(root, profile=profile)
        relative_profile = context.profile_path.relative_to(root).as_posix()
        save_launcher_config(
            LauncherConfig(repo_root=str(root), profile=relative_profile),
            config_path,
            allowed_root=config_path.parent,
        )
        if args.self_test:
            result = run_launcher_self_test(root, profile=profile)
            _write_console(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        logger, log_path = _configure_logging()
        controller = WorkbenchDesktopController(
            context,
            browser_enabled=not args.no_browser,
            logger=logger,
        )
        return _run_tk_launcher(controller, log_path)
    except (OSError, ValueError, WorkbenchDesktopError, WorkbenchProfileError) as exc:
        _write_console(f"error: {exc}", error=True)
        if not args.self_test:
            _show_error("RF-CEM Workbench", str(exc))
        return 2


def _run_tk_launcher(
    controller: WorkbenchDesktopController,
    log_path: Path,
) -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("RF-CEM Workbench Desktop v0")
    root.geometry("760x510")
    root.minsize(680, 430)

    state_text = tk.StringVar(value="Ready")
    url_text = tk.StringVar(value="Workbench URL: not started")
    details = tk.Text(root, height=10, wrap="word", state="disabled")
    event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
    busy = {"value": False}

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="RF-CEM Workbench", font=("Segoe UI", 16, "bold")).pack(anchor="w")
    ttk.Label(frame, text=f"Repository: {controller.context.repo_root}", wraplength=720).pack(anchor="w", pady=(4, 0))
    ttk.Label(frame, text=f"Profile: {controller.context.profile_path.name}").pack(anchor="w")
    ttk.Separator(frame).pack(fill="x", pady=10)

    button_frame = ttk.Frame(frame)
    button_frame.pack(fill="x")
    details.pack(in_=frame, fill="both", expand=True, pady=(12, 8))
    ttk.Label(frame, textvariable=url_text, wraplength=720).pack(anchor="w")
    ttk.Label(frame, textvariable=state_text).pack(anchor="w", pady=(4, 0))

    def set_details(value: str) -> None:
        details.configure(state="normal")
        details.delete("1.0", "end")
        details.insert("1.0", value)
        details.configure(state="disabled")

    def describe_status(status: WorkbenchProfileStatus) -> str:
        missing = [
            str(item.get("display_path"))
            for item in status.source_statuses
            if item.get("status") != "fresh"
        ]
        suffix = "" if not missing else "\n\nAffected sources:\n- " + "\n- ".join(missing)
        return f"Database state: {status.database_state}\n{status.diagnostic}{suffix}"

    def submit(label: str, callback: Callable[[], object]) -> None:
        if busy["value"]:
            state_text.set("Another fixed action is still running")
            return
        busy["value"] = True
        state_text.set(f"{label} …")

        def worker() -> None:
            try:
                event_queue.put(("ok", callback()))
            except Exception as exc:  # GUI boundary: present actionable diagnostics.
                event_queue.put(("error", exc))

        threading.Thread(target=worker, name="rf-cem-launcher-action", daemon=True).start()

    def poll_events() -> None:
        try:
            kind, value = event_queue.get_nowait()
        except queue.Empty:
            root.after(100, poll_events)
            return
        busy["value"] = False
        if kind == "error":
            state_text.set("Action failed")
            set_details(str(value))
            messagebox.showerror("RF-CEM Workbench", str(value), parent=root)
        else:
            state_text.set("Action completed")
            if isinstance(value, WorkbenchProfileStatus):
                set_details(describe_status(value))
            elif isinstance(value, str) and value.startswith("http"):
                url_text.set(f"Workbench URL: {value}")
                set_details("Authenticated read-only Workbench is running on 127.0.0.1.")
            elif value is not None:
                set_details(str(value))
        root.after(100, poll_events)

    def copy_url() -> None:
        url = controller.child.workbench_url
        if url is None:
            raise WorkbenchDesktopError("Workbench has not been started")
        root.clipboard_clear()
        root.clipboard_append(url)
        state_text.set("Authenticated Workbench URL copied")

    def open_logs() -> None:
        _open_local_path(log_path)

    handlers: Mapping[str, Callable[[], None]] = {
        "open_workbench": lambda: submit("Starting Workbench", controller.open_or_start),
        "rebuild_database": lambda: submit("Rebuilding database", controller.rebuild_database),
        "refresh_status": lambda: submit("Refreshing source status", controller.refresh_status),
        "stop_workbench": lambda: (controller.stop(), state_text.set("Owned Workbench stopped")),
        "open_roadmap": lambda: controller.open_fixed_repository_path("open_roadmap"),
        "open_project_status": lambda: controller.open_fixed_repository_path("open_project_status"),
        "open_analysis_outputs": lambda: controller.open_fixed_repository_path("open_analysis_outputs"),
        "copy_workbench_url": copy_url,
        "quick_no_cst_self_check": lambda: submit("Running quick no-CST self-check", controller.run_quick_self_check),
        "view_logs": open_logs,
    }
    if set(handlers) != set(ACTION_REGISTRY):
        raise WorkbenchDesktopError("native action handlers do not match fixed registry")

    def invoke_safely(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception as exc:
            state_text.set("Action failed")
            set_details(str(exc))
            messagebox.showerror("RF-CEM Workbench", str(exc), parent=root)

    for index, spec in enumerate(_ACTION_SPECS):
        ttk.Button(
            button_frame,
            text=spec.label,
            command=lambda action=handlers[spec.action_id]: invoke_safely(action),
            width=31,
        ).grid(row=index // 2, column=index % 2, padx=4, pady=4, sticky="ew")
    button_frame.columnconfigure(0, weight=1)
    button_frame.columnconfigure(1, weight=1)

    def close() -> None:
        controller.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll_events)
    root.after(250, lambda: submit("Starting Workbench", controller.open_or_start))
    root.mainloop()
    return 0


def _configure_logging() -> tuple[logging.Logger, Path]:
    directory = local_config_directory()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / LOG_FILE_NAME
    logger = logging.getLogger("rf_cem.workbench.desktop")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    logger.info("Launcher started")
    return logger, log_path


def _choose_repository_folder(diagnostic: str) -> Path | None:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        "RF-CEM Workbench",
        diagnostic + "\n\nSelect the RF-CEM repository folder.",
        parent=root,
    )
    selected = filedialog.askdirectory(title="Select RF-CEM repository", parent=root)
    root.destroy()
    if not selected:
        return None
    candidate = Path(selected).resolve()
    if not _is_repository_root(candidate):
        _show_error("RF-CEM Workbench", f"Selected folder is not a valid repository:\n{candidate}")
        return None
    return candidate


def _show_error(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message, parent=root)
        root.destroy()
    except Exception:
        _write_console(f"{title}: {message}", error=True)


def _write_console(value: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(value, file=stream, flush=True)


def _open_local_path(path: Path) -> None:
    if os.name != "nt" or not hasattr(os, "startfile"):
        raise WorkbenchDesktopError("opening local files requires Windows")
    os.startfile(str(path))  # type: ignore[attr-defined]


def _parent_candidates(start: Path) -> tuple[Path, ...]:
    resolved = start.resolve()
    return (resolved, *resolved.parents)


def _resolved_declared_sources(context: RepositoryContext) -> tuple[Path, ...]:
    return tuple(
        _require_inside(
            context.repo_root,
            context.repo_root / relative,
            "Workbench profile source",
        )
        for relative in context.profile.declared_source_paths()
    )


def _parse_profile_status(stdout: str) -> WorkbenchProfileStatus:
    try:
        value = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise WorkbenchDesktopError(f"Workbench status returned invalid JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise WorkbenchDesktopError("Workbench status must be a JSON object")
    profile_id = value.get("profile_id")
    database = value.get("database")
    database_state = value.get("database_state")
    diagnostic = value.get("diagnostic")
    raw_statuses = value.get("source_statuses")
    if not all(
        isinstance(item, str)
        for item in (profile_id, database, database_state, diagnostic)
    ) or not isinstance(raw_statuses, list):
        raise WorkbenchDesktopError("Workbench status fields are invalid")
    statuses: list[Mapping[str, Any]] = []
    for item in raw_statuses:
        if not isinstance(item, Mapping):
            raise WorkbenchDesktopError("Workbench source status must be an object")
        statuses.append(dict(item))
    return WorkbenchProfileStatus(
        profile_id=profile_id,
        database=Path(database),
        database_state=database_state,
        source_statuses=tuple(statuses),
        diagnostic=diagnostic,
    )


def _is_repository_root(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "pyproject.toml").is_file()
        and (path / "src" / "rf_cem" / "workbench").is_dir()
        and (path / DEFAULT_PROFILE_RELATIVE).is_file()
    )


def _validated_repository_root(path: Path) -> Path:
    root = path.expanduser().resolve()
    if not _is_repository_root(root):
        raise WorkbenchDesktopError(f"not an RF-CEM repository root: {root}")
    return root


def _require_inside(root: Path, candidate: Path, label: str) -> Path:
    root = root.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise WorkbenchDesktopError(f"{label} escapes its allowed root") from exc
    return candidate


def _safe_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise WorkbenchDesktopError(f"{label} must be a non-empty string")
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise WorkbenchDesktopError(f"{label} contains control characters")
    return value


def _validate_workbench_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        raise WorkbenchDesktopError("Workbench child published a non-loopback URL")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise WorkbenchDesktopError("Workbench child URL contains forbidden components")
    query = parse_qs(parsed.query, strict_parsing=True)
    token = query.get("token", [])
    if parsed.path != "/" or set(query) != {"token"} or len(token) != 1 or len(token[0]) < 16:
        raise WorkbenchDesktopError("Workbench child URL token contract is invalid")


__all__ = [
    "ACTION_REGISTRY",
    "DEFAULT_PROFILE_RELATIVE",
    "FixedCommand",
    "LauncherConfig",
    "OwnedWorkbenchChild",
    "RepositoryContext",
    "WORKBENCH_PAGE_ROUTES",
    "WorkbenchDesktopController",
    "WorkbenchDesktopError",
    "build_fixed_command",
    "detect_repository_python",
    "discover_repository",
    "load_launcher_config",
    "local_config_path",
    "main",
    "resolve_repository_context",
    "run_launcher_self_test",
    "save_launcher_config",
]


if __name__ == "__main__":
    raise SystemExit(main())
