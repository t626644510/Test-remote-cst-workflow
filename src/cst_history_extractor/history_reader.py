"""Read CST history sources.

The reliable text input is an exported history/macro file.  For ``.cst`` input,
the reader first looks for CST's unpacked ``Model/3D/ModelHistory.json`` file.
That JSON file has been observed to contain ordered history captions and VBA
code bodies.  If it is missing, the reader can optionally open the project via
documented CST Python APIs to trigger CST's normal unpacking behavior, then
checks for ``ModelHistory.json`` again.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import List, Optional

from .macro_parser import HistoryItem


@dataclass(frozen=True)
class HistorySource:
    """Input source metadata and optional raw history text."""

    source_type: str
    source_path: str
    raw_text: str
    limitations: List[str]
    cst_probe: dict
    history_items: List[HistoryItem]
    metadata: dict


def read_history_macro(path: Path) -> HistorySource:
    """Read an exported CST history or macro text file."""
    text = path.read_text(encoding="utf-8-sig")
    return HistorySource(
        source_type="history_macro",
        source_path=str(path),
        raw_text=text,
        limitations=[],
        cst_probe={},
        history_items=[],
        metadata={"source_type": "history_macro"},
    )


def read_cst_file_history(path: Path, cst_library_path: Optional[Path] = None) -> HistorySource:
    """Read CST history from a ``.cst`` project's unpacked ModelHistory JSON.

    If the unpacked JSON file is not already present, ``cst_library_path`` is
    used for a documented best-effort project open/probe.  Opening the project
    often causes CST to unpack the side folder next to the ``.cst`` file.
    """
    limitations: List[str] = []
    probe = {
        "attempted": False,
        "project_exists": path.exists(),
        "tree_items": [],
        "active_solver_name": None,
        "messages": [],
        "error": None,
        "model_history_path": None,
        "model_history_found_before_probe": False,
        "model_history_found_after_probe": False,
    }

    if not path.exists():
        probe["error"] = f"CST project file not found: {path}"
        return HistorySource("cst_file", str(path), "", limitations, probe, [], {})

    model_history_path = find_model_history_json(path)
    if model_history_path is not None:
        probe["model_history_found_before_probe"] = True
        probe["model_history_found_after_probe"] = True
        probe["model_history_path"] = str(model_history_path)
        return read_model_history_json(model_history_path, cst_file=path, cst_probe=probe)

    if cst_library_path is None:
        limitations.append(
            "Model/3D/ModelHistory.json was not found next to the CST file, "
            "and no CST Python library path was provided to trigger project unpacking."
        )
        return HistorySource("cst_file", str(path), "", limitations, probe, [], {})

    probe["attempted"] = True
    try:
        cst_library = str(cst_library_path)
        if cst_library not in sys.path:
            sys.path.insert(0, cst_library)
        from cst.interface import DesignEnvironment  # type: ignore

        de = DesignEnvironment.new()
        try:
            project = de.open_project(str(path))
            model3d = getattr(project, "model3d", None)
            if model3d is not None:
                try:
                    probe["tree_items"] = list(model3d.get_tree_items())
                except Exception as exc:  # pragma: no cover - CST-only path
                    probe["messages"].append(f"get_tree_items failed: {exc}")
                try:
                    probe["active_solver_name"] = str(model3d.get_active_solver_name())
                except Exception as exc:  # pragma: no cover - CST-only path
                    probe["messages"].append(f"get_active_solver_name failed: {exc}")
            try:
                project.close()
            except Exception:
                pass
        finally:
            try:
                de.close()
            except Exception:
                pass
    except Exception as exc:  # pragma: no cover - CST-only path
        probe["error"] = str(exc)

    model_history_path = find_model_history_json(path)
    if model_history_path is not None:
        probe["model_history_found_after_probe"] = True
        probe["model_history_path"] = str(model_history_path)
        return read_model_history_json(model_history_path, cst_file=path, cst_probe=probe)

    limitations.extend(
        [
            "The CST project was probed, but Model/3D/ModelHistory.json was not found.",
            "The local CST Python documentation confirms project open/probe APIs but "
            "does not document a method for reading existing History List macro bodies.",
        ]
    )
    return HistorySource("cst_file", str(path), "", limitations, probe, [], {})


def probe_cst_file(path: Path, cst_library_path: Optional[Path] = None) -> HistorySource:
    """Compatibility wrapper for callers that used the old probe-only name."""
    return read_cst_file_history(path, cst_library_path)


def find_model_history_json(path: Path) -> Optional[Path]:
    """Return the likely unpacked ``ModelHistory.json`` path, if present."""
    candidates: List[Path]
    if path.is_dir():
        candidates = [
            path / "Model" / "3D" / "ModelHistory.json",
            path / "3D" / "ModelHistory.json",
            path / "ModelHistory.json",
        ]
    else:
        project_dir = path.with_suffix("")
        candidates = [
            project_dir / "Model" / "3D" / "ModelHistory.json",
            path.parent / path.stem / "Model" / "3D" / "ModelHistory.json",
        ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def read_model_history_json(
    path: Path,
    cst_file: Optional[Path] = None,
    cst_probe: Optional[dict] = None,
) -> HistorySource:
    """Read CST's unpacked ``Model/3D/ModelHistory.json`` format."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    general = data.get("general", {}) if isinstance(data, dict) else {}
    entries = data.get("history", []) if isinstance(data, dict) else []
    if not isinstance(entries, list):
        entries = []

    items: List[HistoryItem] = []
    raw_blocks: List[str] = []
    entry_fields = set()
    hidden_count = 0
    type_counts: dict[str, int] = {}

    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            entry = {"caption": f"history_{index}", "code": [str(entry)]}
        entry_fields.update(str(key) for key in entry.keys())

        caption = str(entry.get("caption") or f"history_{index}")
        entry_type = str(entry.get("type") or "unknown")
        type_counts[entry_type] = type_counts.get(entry_type, 0) + 1
        if bool(entry.get("hidden", False)):
            hidden_count += 1

        code_value = entry.get("code", [])
        if isinstance(code_value, list):
            code_lines = [str(line) for line in code_value]
        elif code_value is None:
            code_lines = []
        else:
            code_lines = [str(code_value)]
        body = "\n".join(code_lines)
        raw_blocks.append(_format_history_block(caption, body))
        items.append(
            HistoryItem(
                index=index,
                raw_name=caption,
                macro_body=body,
                source_line_start=0,
                source_line_end=0,
                parser_strategy="modelhistory_json",
                raw_macro_excerpt=_excerpt(body),
            )
        )

    probe = dict(cst_probe or {})
    probe["model_history_path"] = str(path)
    probe["model_history_entry_count"] = len(items)
    probe["model_history_general"] = general

    metadata = {
        "source_type": "modelhistory_json",
        "cst_file": str(cst_file) if cst_file is not None else None,
        "model_history_path": str(path),
        "general": general,
        "history_entry_count": len(items),
        "history_entry_fields": sorted(entry_fields),
        "history_type_counts": type_counts,
        "hidden_history_entry_count": hidden_count,
        "format_note": (
            "Observed CST unpacked project format: top-level keys 'general' and "
            "'history'; each history entry commonly has caption/version/hidden/type/code."
        ),
    }
    limitations = [
        "Read CST unpacked Model/3D/ModelHistory.json directly. This is an observed "
        "CST project file format, not a documented CST Python API."
    ]
    return HistorySource(
        source_type="modelhistory_json",
        source_path=str(path),
        raw_text="\n\n".join(raw_blocks),
        limitations=limitations,
        cst_probe=probe,
        history_items=items,
        metadata=metadata,
    )


def _format_history_block(caption: str, body: str) -> str:
    if body.strip():
        return f"' History Item: {caption}\n{body.strip()}"
    return f"' History Item: {caption}"


def _excerpt(text: str, max_chars: int = 500) -> str:
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 3].rstrip() + "..."
