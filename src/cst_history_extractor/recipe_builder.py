"""Build recipe-oriented manifests from classified CST history commands."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .command_classifier import ClassifiedCommand


_QUOTED_RE = re.compile(r'"((?:[^"]|"")*)"')
_METHOD_RE = re.compile(r"^\s*\.(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<args>.*)$")
_WITH_OBJECT_RE = re.compile(r"\bWith\s+(?P<object>[A-Za-z_][A-Za-z0-9_]*)\b", re.IGNORECASE)
_PARAM_RE = re.compile(
    r"\bStoreParameter(?:WithDescription)?\s+\"(?P<name>(?:[^\"]|\"\")*)\"\s*,\s*(?P<value>[^,\n]+)",
    re.IGNORECASE,
)
_FREQ_RANGE_RE = re.compile(
    r"\bFrequencyRange\s+\"?(?P<min>[-+0-9.eE]+)\"?\s*,\s*\"?(?P<max>[-+0-9.eE]+)\"?",
    re.IGNORECASE,
)
_CHANGE_SOLVER_RE = re.compile(
    r"\bChangeSolverType\s+\"(?P<solver>(?:[^\"]|\"\")*)\"",
    re.IGNORECASE,
)
_FILE_RE = re.compile(
    r'"([^"]+\.(?:step|stp|sat|sab|iges|igs|stl|dxf|brep|x_t|x_b))"',
    re.IGNORECASE,
)


def build_recipe_manifest(
    project_id: str,
    source: str,
    classified_commands: Sequence[ClassifiedCommand],
    history_limitations: Optional[Sequence[str]] = None,
) -> dict:
    """Build the v0 ``cst_recipe_manifest.json`` payload."""
    geometry_summary = summarize_geometry_history(classified_commands)
    manifest = {
        "schema_version": "0.1",
        "project_id": project_id,
        "source": source,
        "extraction_notes": {
            "history_limitations": list(history_limitations or []),
        },
        "project": {
            "units": _extract_units(classified_commands),
            "background": _extract_first_settings(classified_commands, "project", "background"),
            "parameters": _extract_parameters(classified_commands),
        },
        "materials": _extract_materials(classified_commands),
        "geometry_summary": {
            "imported_files": geometry_summary["imported_geometry"],
            "components": geometry_summary["final_components"],
            "solids": geometry_summary["final_solids"],
            "source_history_indices": geometry_summary["source_history_indices"],
            "confidence": geometry_summary["confidence"],
        },
        "boundaries": _extract_boundaries(classified_commands),
        "ports": _extract_ports(classified_commands),
        "mesh": _extract_mesh(classified_commands),
        "solver": _extract_solver(classified_commands),
        "monitors": _extract_list_by_category(classified_commands, "monitors"),
        "postprocessing": _extract_postprocessing(classified_commands),
        "result_exports": _extract_result_exports(classified_commands),
    }
    return manifest


def summarize_geometry_history(classified_commands: Sequence[ClassifiedCommand]) -> dict:
    """Create a compressed geometry summary without reconstructing topology."""
    geometry_commands = [
        command for command in classified_commands if command.category == "geometry"
    ]
    imported_files: List[str] = []
    components: List[str] = []
    solids: List[str] = []
    ignored = []

    for command in geometry_commands:
        body = command.macro_body
        imported_files.extend(_find_imported_files(body))
        components.extend(_find_method_values(body, "Component"))
        components.extend(_find_component_new_values(body))
        if command.subcategory == "primitive_creation":
            solids.extend(_find_method_values(body, "Name"))
        ignored.append(
            {
                "index": command.index,
                "reason": f"{command.subcategory}_not_relevant_to_solver_recipe",
            }
        )

    return {
        "geometry_command_count": len(geometry_commands),
        "final_components": _unique_sorted(components),
        "final_solids": _unique_sorted(solids),
        "imported_geometry": _unique_sorted(imported_files),
        "ignored_geometry_commands": ignored,
        "source_history_indices": [command.index for command in geometry_commands],
        "confidence": 0.55 if geometry_commands else 0.0,
    }


def _extract_units(commands: Sequence[ClassifiedCommand]) -> Optional[dict]:
    unit_commands = [
        command for command in commands
        if command.category == "project" and command.subcategory == "units"
    ]
    if not unit_commands:
        return None

    units: Dict[str, Any] = {}
    for command in unit_commands:
        settings = parse_macro_settings(command.macro_body)
        for key, value in settings.items():
            lower = key.lower()
            if lower == "setunit":
                for pair in _as_list(value):
                    if isinstance(pair, list) and len(pair) >= 2:
                        units[str(pair[0])] = pair[1]
            else:
                units[key] = value

    return {
        "values": units,
        "confidence": max(command.confidence for command in unit_commands),
        "source_history_indices": [command.index for command in unit_commands],
    }


def _extract_parameters(commands: Sequence[ClassifiedCommand]) -> Optional[dict]:
    values: Dict[str, Any] = {}
    source_indices: List[int] = []
    confidence = 0.0
    for command in commands:
        if command.category != "project" or command.subcategory != "parameters":
            continue
        found = False
        for match in _PARAM_RE.finditer(command.macro_body):
            name = _undouble_quotes(match.group("name"))
            value = match.group("value").strip().strip('"')
            values[name] = value
            found = True
        if found:
            source_indices.append(command.index)
            confidence = max(confidence, command.confidence)
    if not values:
        return None
    return {
        "values": values,
        "confidence": confidence,
        "source_history_indices": source_indices,
    }


def _extract_materials(commands: Sequence[ClassifiedCommand]) -> List[dict]:
    materials = []
    for command in commands:
        if command.category != "material":
            continue
        settings = parse_macro_settings(command.macro_body)
        name_value = settings.get("Name")
        materials.append(
            {
                "name": _first_scalar(name_value) or "unknown",
                "subcategory": command.subcategory,
                "settings": settings,
                "confidence": command.confidence,
                "source_history_indices": [command.index],
            }
        )
    return materials


def _extract_boundaries(commands: Sequence[ClassifiedCommand]) -> dict:
    global_boundary = None
    symmetry = []
    local = []
    for command in commands:
        if command.category != "boundary":
            continue
        entry = _command_entry(command)
        if command.subcategory == "global_boundary":
            global_boundary = entry
        elif command.subcategory == "symmetry_boundary":
            symmetry.append(entry)
        else:
            local.append(entry)
    return {
        "global": global_boundary,
        "symmetry": symmetry,
        "local": local,
    }


def _extract_ports(commands: Sequence[ClassifiedCommand]) -> List[dict]:
    ports = []
    for command in commands:
        if command.category != "ports":
            continue
        settings = parse_macro_settings(command.macro_body)
        ports.append(
            {
                "type": command.subcategory,
                "number": _first_scalar(settings.get("PortNumber")),
                "label": _first_scalar(settings.get("Label")),
                "settings": settings,
                "confidence": command.confidence,
                "source_history_indices": [command.index],
            }
        )
    return ports


def _extract_mesh(commands: Sequence[ClassifiedCommand]) -> dict:
    global_mesh = None
    local_refinements = []
    for command in commands:
        if command.category != "mesh":
            continue
        entry = _command_entry(command)
        if command.subcategory == "global_mesh":
            global_mesh = entry
        else:
            local_refinements.append(entry)
    return {
        "global": global_mesh,
        "local_refinements": local_refinements,
    }


def _extract_solver(commands: Sequence[ClassifiedCommand]) -> dict:
    solver_commands = [command for command in commands if command.category == "solver"]
    solver_type = "unknown"
    confidence = 0.0
    source_indices = []
    settings: Dict[str, Any] = {}

    type_precedence = [
        ("eigenmode_solver", "eigenmode"),
        ("frequency_domain_solver", "frequency_domain"),
        ("time_domain_solver", "time_domain"),
        ("wakefield_solver", "wakefield"),
    ]

    for command in solver_commands:
        source_indices.append(command.index)
        confidence = max(confidence, command.confidence)
        for subcategory, value in type_precedence:
            if command.subcategory == subcategory:
                solver_type = value

        changed_solver = _CHANGE_SOLVER_RE.search(command.macro_body)
        if changed_solver:
            settings["cst_solver_type_string"] = _undouble_quotes(
                changed_solver.group("solver")
            )

        frequency_range = _FREQ_RANGE_RE.search(command.macro_body)
        if frequency_range:
            settings["frequency_range"] = {
                "min": frequency_range.group("min"),
                "max": frequency_range.group("max"),
                "unit_assumption": "project frequency unit",
            }

        parsed_settings = parse_macro_settings(command.macro_body)
        if parsed_settings:
            settings.setdefault("raw_settings", []).append(parsed_settings)

    return {
        "type": solver_type,
        "settings": settings,
        "confidence": confidence,
        "source_history_indices": source_indices,
    }


def _extract_postprocessing(commands: Sequence[ClassifiedCommand]) -> List[dict]:
    return [
        _command_entry(command)
        for command in commands
        if command.category == "monitors"
        and command.subcategory == "template_based_postprocessing"
    ] + [
        _command_entry(command)
        for command in commands
        if command.category == "results"
        and command.subcategory == "result_template"
    ]


def _extract_result_exports(commands: Sequence[ClassifiedCommand]) -> List[dict]:
    export_subcategories = {
        "export_1d",
        "export_2d",
        "export_3d",
        "q_factor",
        "r_over_q",
        "shunt_impedance",
        "peak_field",
        "mode_frequency",
    }
    return [
        _command_entry(command)
        for command in commands
        if command.category == "results"
        and command.subcategory in export_subcategories
    ]


def _extract_list_by_category(
    commands: Sequence[ClassifiedCommand],
    category: str,
) -> List[dict]:
    return [_command_entry(command) for command in commands if command.category == category]


def _extract_first_settings(
    commands: Sequence[ClassifiedCommand],
    category: str,
    subcategory: str,
) -> Optional[dict]:
    for command in commands:
        if command.category == category and command.subcategory == subcategory:
            return _command_entry(command)
    return None


def _command_entry(command: ClassifiedCommand) -> dict:
    return {
        "type": command.subcategory,
        "settings": parse_macro_settings(command.macro_body),
        "confidence": command.confidence,
        "source_history_indices": [command.index],
    }


def parse_macro_settings(macro_body: str) -> dict:
    """Extract simple VBA ``.Method "arg"`` settings from a macro body."""
    settings: Dict[str, Any] = {}
    with_match = _WITH_OBJECT_RE.search(macro_body)
    if with_match:
        settings["object"] = with_match.group("object")

    for line in macro_body.splitlines():
        match = _METHOD_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        args = _parse_args(match.group("args"))
        _append_setting(settings, name, args)
    return settings


def _parse_args(arg_text: str) -> Any:
    quoted = [_undouble_quotes(match.group(1)) for match in _QUOTED_RE.finditer(arg_text)]
    if quoted:
        return quoted if len(quoted) > 1 else quoted[0]
    stripped = arg_text.strip().strip("()").strip()
    if stripped:
        return stripped
    return True


def _append_setting(settings: Dict[str, Any], name: str, value: Any) -> None:
    if name not in settings:
        settings[name] = value
        return
    existing = settings[name]
    if not isinstance(existing, list) or _is_arg_list(existing):
        settings[name] = [existing]
    settings[name].append(value)


def _is_arg_list(value: Any) -> bool:
    return isinstance(value, list) and all(not isinstance(item, list) for item in value)


def _find_imported_files(body: str) -> List[str]:
    return [_undouble_quotes(match.group(1)) for match in _FILE_RE.finditer(body)]


def _find_method_values(body: str, method: str) -> List[str]:
    values = []
    pattern = re.compile(r"^\s*\." + re.escape(method) + r"\s+\"((?:[^\"]|\"\")*)\"", re.IGNORECASE)
    for line in body.splitlines():
        match = pattern.match(line)
        if match:
            values.append(_undouble_quotes(match.group(1)))
    return values


def _find_component_new_values(body: str) -> List[str]:
    values = []
    pattern = re.compile(r"\bComponent\.New\s+\"((?:[^\"]|\"\")*)\"", re.IGNORECASE)
    for match in pattern.finditer(body):
        values.append(_undouble_quotes(match.group(1)))
    return values


def _unique_sorted(values: Iterable[str]) -> List[str]:
    return sorted({value for value in values if value})


def _first_scalar(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        first = value[0]
        if isinstance(first, list):
            return str(first[0]) if first else None
        return str(first)
    return str(value)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        if value and all(not isinstance(item, list) for item in value):
            return [value]
        return value
    return [value]


def _undouble_quotes(value: str) -> str:
    return value.replace('""', '"')
