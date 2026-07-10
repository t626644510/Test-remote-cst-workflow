"""Workflow 4 CST message parsing and artifact-freshness diagnostics."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


_MODE_ROW = re.compile(
    r"^\s*(?P<mode>[1-9]\d*)\s+(?P<frequency>[0-9.eE+-]+)\s+MHz",
    re.MULTILINE,
)
_PORT_WARNING = re.compile(
    r"At least one propagating mode is not considered at port\s+(\d+)",
    re.IGNORECASE,
)
_FIELD_FILE = re.compile(
    r"^Mode\s+(?P<mode>[1-9]\d*)_(?P<kind>[eh])\.h5$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AttemptDiagnostics:
    """Facts parsed from the CST Message Window without guessing CST APIs."""

    meshing_successful: bool
    solver_successful: bool
    mode_table_present: bool
    final_mode_numbers: tuple[int, ...]
    final_mode_frequencies_hz: tuple[tuple[int, float], ...]
    propagating_warning_ports: tuple[int, ...]
    error_messages: tuple[str, ...]

    @property
    def boundary_sensitive(self) -> bool:
        return bool(self.propagating_warning_ports)

    @property
    def warning_codes(self) -> tuple[str, ...]:
        if not self.propagating_warning_ports:
            return ()
        ports = "_".join(str(port) for port in self.propagating_warning_ports)
        return (f"propagating_port_modes_not_considered:{ports}",)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_messages(messages: object) -> list[dict[str, str]]:
    """Normalize CST messages or legacy repr text into text/type mappings."""

    if isinstance(messages, list):
        return [
            {
                "text": str(item.get("text", "")),
                "type": str(item.get("type", "")),
            }
            for item in messages
            if isinstance(item, dict)
        ]
    if isinstance(messages, tuple):
        return normalize_messages(list(messages))
    if isinstance(messages, str):
        text = messages.strip()
        if not text:
            return []
        for loader in (json.loads, ast.literal_eval):
            try:
                loaded = loader(text)
            except Exception:
                continue
            return normalize_messages(loaded)
        return [{"text": text, "type": ""}]
    return [{"text": str(messages), "type": ""}]


def parse_attempt_diagnostics(messages: object) -> AttemptDiagnostics:
    normalized = normalize_messages(messages)
    final_mode_numbers: tuple[int, ...] = ()
    final_mode_frequencies_hz: tuple[tuple[int, float], ...] = ()
    mode_table_present = False
    ports: set[int] = set()
    errors: list[str] = []
    meshing_successful = False
    solver_successful = False
    for item in normalized:
        text = item["text"]
        lowered = text.lower()
        meshing_successful = meshing_successful or "meshing successful" in lowered
        solver_successful = (
            solver_successful or "eigenmode solver successful" in lowered
        )
        if "mode" in lowered and "frequency" in lowered and "mhz" in lowered:
            mode_table_present = True
            rows = tuple(
                (
                    int(match.group("mode")),
                    float(match.group("frequency")) * 1e6,
                )
                for match in _MODE_ROW.finditer(text)
            )
            final_mode_numbers = tuple(mode for mode, _frequency in rows)
            final_mode_frequencies_hz = rows
        ports.update(int(value) for value in _PORT_WARNING.findall(text))
        if item["type"].upper() == "ERROR":
            errors.append(text.splitlines()[0])
    return AttemptDiagnostics(
        meshing_successful=meshing_successful,
        solver_successful=solver_successful,
        mode_table_present=mode_table_present,
        final_mode_numbers=final_mode_numbers,
        final_mode_frequencies_hz=final_mode_frequencies_hz,
        propagating_warning_ports=tuple(sorted(ports)),
        error_messages=tuple(errors),
    )


def read_attempt_diagnostics(attempt_dir: str | Path) -> AttemptDiagnostics:
    attempt = Path(attempt_dir)
    json_path = attempt / "cst_messages.json"
    text_path = attempt / "cst_messages.txt"
    if json_path.is_file():
        return parse_attempt_diagnostics(
            json.loads(json_path.read_text(encoding="utf-8"))
        )
    if text_path.is_file():
        return parse_attempt_diagnostics(
            text_path.read_text(encoding="utf-8", errors="replace")
        )
    return parse_attempt_diagnostics([])


def write_messages(attempt_dir: str | Path, messages: object) -> AttemptDiagnostics:
    attempt = Path(attempt_dir)
    normalized = normalize_messages(messages)
    (attempt / "cst_messages.json").write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (attempt / "cst_messages.txt").write_text(
        repr(normalized),
        encoding="utf-8",
        errors="replace",
    )
    return parse_attempt_diagnostics(normalized)


def classify_solver_failure(
    diagnostics: AttemptDiagnostics,
    *,
    elapsed_s: float,
    long_attempt_threshold_s: float,
) -> str:
    """Classify cheap startup failures separately from scientific attempts."""

    _ = elapsed_s, long_attempt_threshold_s
    if (
        not diagnostics.meshing_successful
        and not diagnostics.mode_table_present
    ):
        return "init_fast"
    return "long_solve"


def archived_hdf5_mode_pairs(
    archived: Iterable[dict[str, Any]],
    patterns: dict[str, str] | None = None,
) -> dict[int, set[str]]:
    pairs: dict[int, set[str]] = {}
    for item in archived:
        relative = Path(str(item.get("relative_path", ""))).name
        if patterns is None:
            match = _FIELD_FILE.match(relative)
            if match:
                pairs.setdefault(int(match.group("mode")), set()).add(
                    match.group("kind").lower()
                )
            continue
        for kind, template in patterns.items():
            token = "__MODE_NUMBER__"
            rendered = Path(template.replace("{mode}", token)).name
            expression = re.escape(rendered).replace(
                re.escape(token),
                r"(?P<mode>[1-9]\d*)",
            )
            match = re.fullmatch(expression, relative, re.IGNORECASE)
            if match:
                pairs.setdefault(int(match.group("mode")), set()).add(
                    kind.lower()
                )
    return pairs
