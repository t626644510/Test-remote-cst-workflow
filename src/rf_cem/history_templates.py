"""Extract reusable CST history VBA templates for RF-CEM v0."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from cst_history_extractor.command_classifier import ClassifiedCommand, classify_history_items
from cst_history_extractor.history_reader import read_model_history_json
from cst_history_extractor.recipe_builder import build_recipe_manifest


@dataclass(frozen=True)
class CstHistoryBlock:
    """A reusable CST history block with provenance."""

    action_id: str
    caption: str
    category: str
    subcategory: str
    vba: str
    source_index: int
    confidence: float
    source_kind: str = "history"


@dataclass(frozen=True)
class CstHistoryTemplates:
    """CST setup templates extracted from baseline ModelHistory.json."""

    source: str
    recipe: dict
    units_block: str
    boundary_block: str
    frequency_range_block: str
    solver_blocks: tuple[str, ...]
    source_history_indices: dict[str, list[int]]
    monitor_blocks: tuple[CstHistoryBlock, ...] = ()
    postprocessing_blocks: tuple[CstHistoryBlock, ...] = ()
    result_template_blocks: tuple[CstHistoryBlock, ...] = ()
    result_export_blocks: tuple[CstHistoryBlock, ...] = ()
    macro_fallback_candidates: tuple[CstHistoryBlock, ...] = ()

    @property
    def eigenmode_summary(self) -> dict:
        """Return a compact solver summary used by reports and tests."""
        settings = self.recipe.get("solver", {}).get("settings", {})
        raw_settings = settings.get("raw_settings", [])
        merged: dict = {}
        for item in raw_settings:
            if isinstance(item, dict):
                merged.update(item)
        return {
            "solver_type": self.recipe.get("solver", {}).get("type"),
            "cst_solver_type_string": settings.get("cst_solver_type_string"),
            "frequency_range": settings.get("frequency_range"),
            "mesh_type": merged.get("SetMeshType"),
            "number_of_modes": merged.get("SetNumberOfModes"),
            "accuracy": merged.get("SetAccuracy") or merged.get("AKSAccuracy"),
            "order_tet": merged.get("SetOrderTet"),
            "minimum_passes": merged.get("AKSMinimumPasses"),
            "maximum_passes": merged.get("AKSMaximumPasses"),
            "mesh_increment": merged.get("AKSMeshIncrement"),
        }


def load_cst_history_templates(model_history_json: Path) -> CstHistoryTemplates:
    """Read baseline CST history and extract stable setup VBA blocks."""
    source = read_model_history_json(model_history_json)
    commands = classify_history_items(source.history_items)
    recipe = build_recipe_manifest(
        "500MHz_baseline",
        str(model_history_json),
        commands,
        history_limitations=source.limitations,
    )

    units = _single_block(commands, "project", "units")
    boundary = _single_block(commands, "boundary", "global_boundary")
    frequency = _single_block(commands, "solver", "frequency_range")
    solver = [
        command.macro_body
        for command in commands
        if command.category == "solver" and command.subcategory != "frequency_range"
    ]
    if not solver:
        raise ValueError("No eigenmode solver template block found in CST history")

    monitor_blocks = _blocks_for(commands, "monitors", {"e_field_monitor", "h_field_monitor", "field_on_axis", "probe"})
    postprocessing_blocks = _blocks_for(commands, "monitors", {"template_based_postprocessing"})
    result_template_blocks = _blocks_for(commands, "results", {"result_template"})
    result_export_blocks = _blocks_for(
        commands,
        "results",
        {"export_1d", "export_2d", "export_3d", "q_factor", "r_over_q", "shunt_impedance", "peak_field", "mode_frequency"},
    )

    return CstHistoryTemplates(
        source=str(model_history_json),
        recipe=recipe,
        units_block=units.macro_body,
        boundary_block=boundary.macro_body,
        frequency_range_block=frequency.macro_body,
        solver_blocks=tuple(command for command in solver if command.strip()),
        monitor_blocks=tuple(monitor_blocks),
        postprocessing_blocks=tuple(postprocessing_blocks),
        result_template_blocks=tuple(result_template_blocks),
        result_export_blocks=tuple(result_export_blocks),
        source_history_indices={
            "units": [units.index],
            "boundary": [boundary.index],
            "frequency_range": [frequency.index],
            "solver": [
                command.index
                for command in commands
                if command.category == "solver" and command.subcategory != "frequency_range"
            ],
            "monitors": [block.source_index for block in monitor_blocks],
            "postprocessing": [block.source_index for block in postprocessing_blocks],
            "result_templates": [block.source_index for block in result_template_blocks],
            "result_exports": [block.source_index for block in result_export_blocks],
        },
    )


def load_macro_fallback_candidates(paths: Sequence[Path]) -> tuple[CstHistoryBlock, ...]:
    """Load known macro fallback candidates without treating them as verified templates."""
    blocks: list[CstHistoryBlock] = []
    for index, path in enumerate(paths, start=1):
        if not path.exists() or path.suffix.lower() != ".bas":
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        if not _looks_like_result_macro(body):
            continue
        blocks.append(
            CstHistoryBlock(
                action_id=f"macro_fallback_{index:02d}",
                caption=f"macro fallback candidate: {path.name}",
                category="macro",
                subcategory="result_macro_fallback",
                vba=body,
                source_index=index,
                confidence=0.45,
                source_kind=str(path),
            )
        )
    return tuple(blocks)


def _single_block(
    commands: Sequence[ClassifiedCommand],
    category: str,
    subcategory: str,
) -> ClassifiedCommand:
    matches = [
        command
        for command in commands
        if command.category == category and command.subcategory == subcategory
    ]
    if not matches:
        raise ValueError(f"No CST history block found for {category}:{subcategory}")
    return matches[-1]


def _blocks_for(
    commands: Sequence[ClassifiedCommand],
    category: str,
    subcategories: set[str],
) -> list[CstHistoryBlock]:
    blocks: list[CstHistoryBlock] = []
    for command in commands:
        if command.category != category or command.subcategory not in subcategories:
            continue
        if not command.macro_body.strip():
            continue
        action_id = f"{category}_{command.subcategory}_{command.index:04d}"
        blocks.append(
            CstHistoryBlock(
                action_id=action_id,
                caption=command.raw_name or f"{category}:{command.subcategory}",
                category=command.category,
                subcategory=command.subcategory,
                vba=command.macro_body,
                source_index=command.index,
                confidence=command.confidence,
            )
        )
    return blocks


def _looks_like_result_macro(body: str) -> bool:
    lower = body.lower()
    return any(token in lower for token in ("result1d", "result1dcomplex", "addtotree", "0d results", "1d results"))
