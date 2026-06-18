"""Write human-readable CST history extraction reports."""

from __future__ import annotations

from collections import Counter
from typing import Sequence

from .command_classifier import ClassifiedCommand


def build_history_analysis_report(
    project_id: str,
    source: str,
    classified_commands: Sequence[ClassifiedCommand],
    recipe_manifest: dict,
    geometry_summary: dict,
    limitations: Sequence[str],
) -> str:
    """Return a Markdown analysis report."""
    counts = Counter(command.category for command in classified_commands)
    subcounts = Counter(
        f"{command.category}/{command.subcategory}" for command in classified_commands
    )
    unknown = [command for command in classified_commands if command.category == "unknown"]

    lines = [
        f"# CST History Analysis Report: {project_id}",
        "",
        "## Source",
        "",
        f"- Source: `{source}`",
        f"- Parsed history items: {len(classified_commands)}",
        "",
    ]

    if limitations:
        lines.extend(["## CST Access Notes", ""])
        for note in limitations:
            lines.append(f"- {note}")
        lines.append("")

    lines.extend(["## Command Inventory Summary", ""])
    if counts:
        for category, count in sorted(counts.items()):
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- No history commands were parsed.")
    lines.append("")

    if subcounts:
        lines.extend(["## Recognized Command Types", ""])
        for key, count in sorted(subcounts.items()):
            lines.append(f"- {key}: {count}")
        lines.append("")

    lines.extend(["## Key Recipe Findings", ""])
    solver = recipe_manifest.get("solver", {})
    lines.append(f"- Solver type: `{solver.get('type', 'unknown')}`")
    lines.append(f"- Solver confidence: `{solver.get('confidence', 0.0)}`")
    lines.append(f"- Ports: {len(recipe_manifest.get('ports', []))}")
    mesh = recipe_manifest.get("mesh", {})
    lines.append(f"- Global mesh present: {mesh.get('global') is not None}")
    boundaries = recipe_manifest.get("boundaries", {})
    lines.append(f"- Global boundary present: {boundaries.get('global') is not None}")
    lines.append(f"- Monitors: {len(recipe_manifest.get('monitors', []))}")
    lines.append(f"- Result exports/postprocessing: {len(recipe_manifest.get('result_exports', [])) + len(recipe_manifest.get('postprocessing', []))}")
    lines.append("")

    lines.extend(["## Geometry History Summary", ""])
    lines.append(f"- Geometry command count: {geometry_summary.get('geometry_command_count', 0)}")
    lines.append(f"- Imported geometry: {geometry_summary.get('imported_geometry', [])}")
    lines.append(f"- Final components (best effort): {geometry_summary.get('final_components', [])}")
    lines.append(f"- Final solids (best effort): {geometry_summary.get('final_solids', [])}")
    lines.append("")

    lines.extend(["## Unknown Or Unclassified Commands", ""])
    if unknown:
        for command in unknown:
            lines.append(f"- #{command.index} `{command.raw_name}`")
    else:
        lines.append("- None.")
    lines.append("")

    lines.extend(["## Review Guidance", ""])
    lines.append("- Treat this report as a recipe-extraction aid, not as a CST macro validator.")
    lines.append("- Review `source_history_indices` in JSON outputs before promoting settings into CSTTranslator.")
    lines.append("- Unknown commands are preserved for manual inspection instead of being dropped.")
    lines.append("")

    return "\n".join(lines)
