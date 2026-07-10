"""Minimal design-package defaults for the 500 MHz baseline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BaselinePaths:
    """Resolved input paths for the imported 500 MHz baseline package."""

    appendix: Path
    step_file: Path
    model_history_json: Path
    helper2_dir: Path
    geometry_graph: Path
    feature_graph_draft: Path
    geometry_manifest: Path
    reviewed_feature_labels: Path
    review_session: Path | None

    @classmethod
    def from_appendix(cls, appendix: Path) -> "BaselinePaths":
        """Resolve the expected Appendix/500MHz_baseline input layout."""
        root = appendix.resolve()
        helper2_dir = root / "step_feature_assistant"
        review_session = helper2_dir / "review_session.json"
        return cls(
            appendix=root,
            step_file=root / "500MHz.stp",
            model_history_json=root / "500MHz" / "Model" / "3D" / "ModelHistory.json",
            helper2_dir=helper2_dir,
            geometry_graph=helper2_dir / "geometry_graph.json",
            feature_graph_draft=helper2_dir / "feature_graph_draft.json",
            geometry_manifest=helper2_dir / "geometry_manifest.json",
            reviewed_feature_labels=helper2_dir / "reviewed_feature_labels.yaml",
            review_session=review_session if review_session.exists() else None,
        )

    def validate(self) -> None:
        """Raise when a required baseline input is missing."""
        missing = [
            path
            for path in (
                self.step_file,
                self.model_history_json,
                self.geometry_graph,
                self.feature_graph_draft,
                self.geometry_manifest,
                self.reviewed_feature_labels,
            )
            if not path.exists()
        ]
        if missing:
            joined = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"Missing 500 MHz baseline input(s): {joined}")


@dataclass(frozen=True)
class BaselineDesignPackage:
    """Small v0 package descriptor for the imported 500 MHz RF cavity.

    Units are CST project units from the baseline history: millimetres for
    geometry, MHz for frequency, and ns for time.
    """

    package_id: str = "500MHz_baseline"
    case_type: str = "bare_cavity_500mhz"
    axis: str = "z"
    length_unit: str = "mm"
    frequency_unit: str = "MHz"
    time_unit: str = "ns"
    frequency_min: str = "498"
    frequency_max: str = "530"

    def to_dict(self) -> dict:
        """Return a JSON-safe package descriptor."""
        return {
            "schema_version": "design_package.v0",
            "package_id": self.package_id,
            "case_type": self.case_type,
            "axis": self.axis,
            "units": {
                "length": self.length_unit,
                "frequency": self.frequency_unit,
                "time": self.time_unit,
            },
            "frequency_range": {
                "min": self.frequency_min,
                "max": self.frequency_max,
                "unit": self.frequency_unit,
            },
        }
