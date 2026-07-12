"""Integrated no-CST literature review application for the SLS-2 pilot.

The application binds an immutable corpus, a literature geometry candidate,
the interactive HTML renderer, and the authenticated loopback review server.
Generated STEP/model artifacts are content-addressed below the session root.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading
from typing import Any, Mapping, Optional

from step_feature_assistant.cadquery_reader import build_geometry_manifest_for_backend
from step_feature_assistant.feature_candidate_generator import generate_feature_graph_draft
from step_feature_assistant.layer_builders import (
    build_feature_candidates,
    build_geometry_graph,
    build_udsg_geometry_layer,
    detect_review_issues,
)
from step_feature_assistant.topology_analyzer import build_adjacency_graph
from step_feature_assistant.reviewer import build_reviewer_payload

from .geometry_candidate import (
    LiteratureGeometryCandidateError,
    Sls2GeometryParameters,
    build_sls2_geometry_candidate,
    build_sls2_preview_variant,
    candidate_snapshot_sha256,
    generate_sls2_step,
    validate_geometry_candidate,
)
from .interactive_reviewer import build_interactive_review_html
from .review_bundle import ManifestInput, ReviewBundleLoader
from .review_server import ReviewServer, ReviewSessionError, ReviewSessionStore
from .types import canonical_sha256


DEFAULT_SLS2_PARAMETERS_MM = {
    "L": 680.0,
    "l": 188.671,
    "r": 50.0,
    "R": 249.901,
    "a": 125.232,
    "b": 70.2322,
}
DEFAULT_SLS2_EVIDENCE_REFS = ("sls2_p8_spline", "sls2_p9_material_table")
DEFAULT_SLS2_SEMANTIC_PATHS = (
    "classification",
    "text_evidence[0]",
    "text_evidence[1]",
    "text_evidence[2]",
    "parameter_ranges[0]",
    "parameter_ranges[1]",
)
DEFAULT_CANDIDATE_ID = "sls2.cavity_1.paper_approximation"


class LiteratureReviewAppError(RuntimeError):
    """Raised when the integrated literature review app cannot be prepared."""


@dataclass(frozen=True)
class ReviewLaunch:
    """Prepared loopback service and browser launch metadata."""

    server: ReviewServer
    review_url: str
    html_path: Path
    launch_info_path: Path
    initial_step_path: Path


class Sls2LiteratureReviewApp:
    """Build and serve the SLS-2 literature-to-geometry review loop."""

    def __init__(
        self,
        *,
        bundle_root: Path,
        corpus_manifest: ManifestInput,
        session_root: Path,
        paper_id: str = "sls2",
        candidate: Optional[Mapping[str, Any]] = None,
        deflection_mm: float = 0.5,
    ) -> None:
        self.loader = ReviewBundleLoader(bundle_root)
        source_payload = self.loader.build_payload(corpus_manifest, paper_id=paper_id)
        paper = next(
            item for item in source_payload["papers"] if item.get("id") == paper_id
        )
        self.semantic_package = copy.deepcopy(paper["literature_semantics"])
        request_context = self.semantic_package.get("request_context", {})
        operating_regime = (
            request_context.get("operating_regime")
            if isinstance(request_context, Mapping)
            else None
        )
        if operating_regime != "normal_conducting":
            raise LiteratureReviewAppError(
                "SLS-2 geometry review requires a normal_conducting paper; "
                "superconducting papers must use a separate semantic-only session"
            )
        self.corpus_manifest = corpus_manifest
        self.paper_id = paper_id
        self.bundle_root = self.loader.root
        self.paper_pdf = self.loader.read_paper_pdf(
            corpus_manifest, paper_id=paper_id
        )
        self.session_root = Path(session_root).expanduser().resolve(strict=False)
        self.session_root.mkdir(parents=True, exist_ok=True)
        if not self.session_root.is_dir():
            raise LiteratureReviewAppError(
                f"session root is not a directory: {self.session_root}"
            )
        self.artifacts_root = self._session_child("geometry_previews")
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        if (
            isinstance(deflection_mm, bool)
            or not math.isfinite(float(deflection_mm))
            or float(deflection_mm) <= 0.0
        ):
            raise LiteratureReviewAppError("deflection_mm must be positive")
        self.deflection_mm = float(deflection_mm)
        self.base_candidate = copy.deepcopy(
            dict(candidate)
            if candidate is not None
            else build_default_sls2_candidate(self.semantic_package)
        )
        validate_geometry_candidate(self.base_candidate, self.semantic_package)
        self._lock = threading.RLock()
        self._latest_candidate = copy.deepcopy(self.base_candidate)
        self._latest_model: Optional[dict[str, Any]] = None
        self._baseline_model: Optional[dict[str, Any]] = None

    def prepare_server(
        self,
        *,
        port: int = 0,
        token: Optional[str] = None,
    ) -> ReviewLaunch:
        """Generate the initial model and return a bound, not-yet-running server."""
        with self._lock:
            initial_report = self._materialize_candidate(
                self.base_candidate, parent_candidate=None
            )
            current = copy.deepcopy(initial_report["preview"]["current"])
            current["provenance"] = "published_candidate"
            self._baseline_model = copy.deepcopy(current)
            self._latest_model = copy.deepcopy(current)
            initial_report["preview"]["baseline"] = copy.deepcopy(current)
            initial_report["preview"]["previous"] = None
            initial_report["id"] = self.base_candidate["candidate_id"]
            initial_report["candidate"] = copy.deepcopy(self.base_candidate)
            initial_report["review_items"] = [
                self._geometry_review_item(self.base_candidate, initial_report)
            ]
            payload = self.loader.build_payload(
                self.corpus_manifest,
                paper_id=self.paper_id,
                geometry_projection=initial_report,
            )

        selected_token = token or secrets.token_urlsafe(32)
        html = build_interactive_review_html(payload, selected_token)
        safe_paper_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.paper_id).strip("._")
        if not safe_paper_id:
            raise LiteratureReviewAppError("paper_id cannot form a safe HTML filename")
        html_path = self._session_child(
            f"rf_cem_literature_review_{safe_paper_id}.html"
        )
        _write_text_atomic(html_path, html)
        store = self._open_session_store(payload)
        server = ReviewServer(
            store,
            preview_callback=self.preview,
            review_html=html,
            paper_document=self.paper_pdf,
            token=selected_token,
            port=port,
        )
        if server.review_url is None:  # defensive; review_html was supplied above
            server.stop()
            raise LiteratureReviewAppError("review server did not expose a review URL")
        launch_info_path = self._session_child("review_launch.json")
        _write_json_atomic(
            launch_info_path,
            {
                "schema_version": "literature_review_launch.v1",
                "review_url": server.review_url,
                "base_url": server.base_url,
                "paper_id": self.paper_id,
                "session_root": str(self.session_root),
                "html_path": str(html_path),
                "pid": os.getpid(),
                "preview_only": True,
                "live_cst": False,
            },
        )
        initial_step = Path(initial_report["geometry"]["step_path"])
        return ReviewLaunch(
            server=server,
            review_url=server.review_url,
            html_path=html_path,
            launch_info_path=launch_info_path,
            initial_step_path=initial_step,
        )

    def preview(
        self,
        session: Mapping[str, Any],
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Build a current/previous/baseline preview for one browser request."""
        try:
            parameters = _preview_parameters(
                request.get("parameters"), self._latest_candidate["parameter_tuple"]["values"]
            )
            with self._lock:
                parent = copy.deepcopy(self._latest_candidate)
                parent_values = parent["parameter_tuple"]["values"]
                is_variant = parameters != parent_values
                if not is_variant:
                    candidate = parent
                else:
                    variant_id = _variant_id(parent, parameters)
                    candidate = build_sls2_preview_variant(
                        parent,
                        self.semantic_package,
                        candidate_id=variant_id,
                        parameters=parameters,
                    )

                item_id = self._geometry_item_id(candidate)
                decision = _decision_for(session, item_id)
                requested_item_id = str(request.get("item_id") or "")
                if decision is None and requested_item_id == item_id:
                    decision = _decision_for(session, requested_item_id)
                candidate = _candidate_with_review(candidate, decision)
                if candidate["review"]["human_review_status"] == "rejected":
                    return self._rejected_preview(candidate)

                previous = copy.deepcopy(self._latest_model)
                report = self._materialize_candidate(
                    candidate,
                    parent_candidate=parent if is_variant else None,
                )
                if self._baseline_model is not None:
                    report["preview"]["baseline"] = copy.deepcopy(self._baseline_model)
                if previous is not None:
                    report["preview"]["previous"] = previous
                report["id"] = candidate["candidate_id"]
                report["candidate"] = copy.deepcopy(candidate)
                report["review_items"] = [
                    self._geometry_review_item(candidate, report)
                ]
                self._latest_candidate = copy.deepcopy(candidate)
                self._latest_model = copy.deepcopy(report["preview"]["current"])
                return report
        except (LiteratureGeometryCandidateError, TypeError, ValueError) as exc:
            raise ReviewSessionError(str(exc)) from exc

    def _materialize_candidate(
        self,
        candidate: Mapping[str, Any],
        *,
        parent_candidate: Optional[Mapping[str, Any]],
    ) -> dict[str, Any]:
        digest = str(candidate["integrity"]["candidate_content_sha256"]).split(":", 1)[-1]
        artifact_dir = self._session_child("geometry_previews", digest[:20])
        artifact_dir.mkdir(parents=True, exist_ok=True)
        report_path = artifact_dir / "generation.core.json"
        output_step = artifact_dir / "cavity.step"
        if report_path.is_file() and output_step.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if not report.get("helper2", {}).get("review_payload"):
                self._enrich_helper2(report, output_step, artifact_dir)
                _write_json_atomic(report_path, report)
        else:
            report = generate_sls2_step(
                candidate,
                self.semantic_package,
                output_step=output_step,
                parent_candidate=parent_candidate,
                deflection_mm=self.deflection_mm,
            )
            self._enrich_helper2(report, output_step, artifact_dir)
            _write_json_atomic(report_path, report)
        report = copy.deepcopy(report)
        report["review_status"] = candidate["review"]["human_review_status"]
        report["integrity"]["candidate_snapshot_sha256"] = candidate_snapshot_sha256(
            candidate
        )
        report["candidate"] = copy.deepcopy(candidate)
        snapshot_name = (
            candidate_snapshot_sha256(candidate).split(":", 1)[-1][:20]
            + ".review_snapshot.json"
        )
        _write_json_atomic(artifact_dir / snapshot_name, report)
        return report

    def _enrich_helper2(
        self, report: dict[str, Any], output_step: Path, artifact_dir: Path
    ) -> None:
        mesh_path = artifact_dir / "helper2_face_mesh.json"
        geometry_manifest = build_geometry_manifest_for_backend(
            output_step,
            "z",
            "cadquery",
            mesh_output=mesh_path,
        )
        adjacency = build_adjacency_graph(geometry_manifest)
        geometry_graph = build_geometry_graph(geometry_manifest, adjacency)
        feature_draft = generate_feature_graph_draft(
            geometry_manifest,
            "normal_conducting_500mhz",
            "z",
        )
        feature_candidates = build_feature_candidates(feature_draft)
        for item in feature_candidates.get("feature_candidates", []):
            item["status"] = "requires_review"
            item["requires_human_review"] = True
        udsg = build_udsg_geometry_layer(
            geometry_graph,
            feature_candidates,
            feature_draft.get("face_groups", []),
        )
        issues = detect_review_issues(feature_candidates, udsg)
        mesh_faces = json.loads(mesh_path.read_text(encoding="utf-8"))
        report["geometry"].update(
            {
                "manifest": geometry_manifest,
                "geometry_graph": geometry_graph,
                "face_mesh": mesh_faces,
                "helper2_review_required": True,
            }
        )
        report["features"] = feature_candidates
        report["udsg"] = udsg
        report["helper2"] = {
            "schema_version": "literature_helper2_enrichment.v1",
            "feature_graph_draft": feature_draft,
            "review_issues": issues,
            "model_profile": "normal_conducting_500mhz",
            "all_mappings_require_human_review": True,
            "review_payload": build_reviewer_payload(
                mesh_faces,
                geometry_manifest,
                feature_draft,
                {},
                geometry_graph,
                feature_candidates,
                udsg,
                issues,
                {},
                include_traces=False,
            ),
        }
        report["validation"]["helper2"] = {
            "status": udsg.get("validation", {}).get("status"),
            "feature_candidate_count": len(
                feature_candidates.get("feature_candidates", [])
            ),
            "binding_count": len(udsg.get("bindings", [])),
            "warnings": copy.deepcopy(udsg.get("validation", {}).get("warnings", [])),
        }

    def _open_session_store(self, payload: Mapping[str, Any]) -> ReviewSessionStore:
        session_path = self.session_root / ReviewSessionStore.SESSION_FILENAME
        if session_path.exists():
            store = ReviewSessionStore(self.session_root)
            existing_scope = store.get_session().get("review_scope", {})
            expected_scope = self.loader.session_seed(payload)["review_scope"]
            if existing_scope.get("payload_sha256") != expected_scope["payload_sha256"]:
                raise LiteratureReviewAppError(
                    "persisted review session is bound to a different source payload"
                )
            return store
        return ReviewSessionStore(
            self.session_root, initial_session=self.loader.session_seed(payload)
        )

    def _rejected_preview(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        current = copy.deepcopy(self._latest_model)
        return {
            "schema_version": "literature_geometry_generation.v0",
            "mode": "preview_only",
            "candidate_id": candidate["candidate_id"],
            "review_status": "rejected",
            "parameter_tuple": copy.deepcopy(candidate["parameter_tuple"]),
            "preview": {
                "baseline": copy.deepcopy(self._baseline_model),
                "previous": current,
                "current": current,
            },
            "geometry": {
                "blocked": True,
                "reason": "Rejected geometry projection was not regenerated.",
            },
            "features": [],
            "udsg": {},
            "validation": {
                "pass": False,
                "blocking_errors": [
                    "Candidate is rejected; exact STEP generation is disabled."
                ],
                "warnings": [
                    "The last generated model remains visible only for comparison."
                ],
            },
            "review_items": [self._geometry_review_item(candidate, {})],
        }

    def _geometry_review_item(
        self, candidate: Mapping[str, Any], report: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {
            "id": self._geometry_item_id(candidate),
            "original_id": candidate["candidate_id"],
            "paper_id": self.paper_id,
            "layer": "geometry",
            "section": "geometry_projection",
            "label": f"{candidate['candidate_id']} / 几何投影",
            "human_review_status": candidate["review"]["human_review_status"],
            "review_note": candidate["review"].get("review_note", ""),
            "content": {
                "candidate_id": candidate["candidate_id"],
                "parameter_tuple": copy.deepcopy(candidate["parameter_tuple"]),
                "lineage": copy.deepcopy(candidate.get("lineage")),
                "validation": copy.deepcopy(report.get("validation", {})),
                "claim": "geometry hypothesis / paper approximation, not RF performance reproduction",
            },
        }

    def _geometry_item_id(self, candidate: Mapping[str, Any]) -> str:
        return (
            f"{self.paper_id}::geometry::geometry_projection::"
            f"{candidate['candidate_id']}"
        )

    def _session_child(self, *parts: str) -> Path:
        candidate = self.session_root.joinpath(*parts)
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.session_root)
        except ValueError as exc:
            raise LiteratureReviewAppError("session artifact escapes session root") from exc
        return resolved


def build_default_sls2_candidate(
    semantic_package: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the pinned published SLS-2 cavity #1 geometry hypothesis."""
    return build_sls2_geometry_candidate(
        semantic_package,
        candidate_id=DEFAULT_CANDIDATE_ID,
        parameters=DEFAULT_SLS2_PARAMETERS_MM,
        evidence_refs=DEFAULT_SLS2_EVIDENCE_REFS,
        semantic_paths=DEFAULT_SLS2_SEMANTIC_PATHS,
    )


def _preview_parameters(
    supplied: object, fallback: Mapping[str, Any]
) -> dict[str, float]:
    values = fallback if supplied is None or supplied == "" else supplied
    if not isinstance(values, Mapping):
        raise LiteratureGeometryCandidateError("parameters must be a JSON object")
    return Sls2GeometryParameters.from_mapping(values).as_values()


def _variant_id(parent: Mapping[str, Any], parameters: Mapping[str, float]) -> str:
    digest = canonical_sha256(
        {
            "parent_candidate_content_sha256": parent["integrity"][
                "candidate_content_sha256"
            ],
            "parameters_mm": dict(parameters),
        }
    ).split(":", 1)[-1]
    return f"{DEFAULT_CANDIDATE_ID}.preview_{digest[:12]}"


def _decision_for(
    session: Mapping[str, Any], item_id: str
) -> Optional[Mapping[str, Any]]:
    decisions = session.get("review_decisions", {})
    if not isinstance(decisions, Mapping):
        return None
    value = decisions.get(item_id)
    return value if isinstance(value, Mapping) else None


def _candidate_with_review(
    candidate: Mapping[str, Any], decision: Optional[Mapping[str, Any]]
) -> dict[str, Any]:
    result = copy.deepcopy(dict(candidate))
    if decision is None:
        return result
    review = result["review"]
    review["human_review_status"] = str(decision.get("status") or "pending")
    review["review_note"] = str(decision.get("review_note") or "")
    if decision.get("reviewer"):
        review["reviewer"] = str(decision["reviewer"])
    if decision.get("reviewed_at"):
        review["reviewed_at"] = str(decision["reviewed_at"])
    return result


def _write_text_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_json_atomic(path: Path, value: object) -> None:
    _write_text_atomic(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


__all__ = [
    "DEFAULT_CANDIDATE_ID",
    "DEFAULT_SLS2_PARAMETERS_MM",
    "LiteratureReviewAppError",
    "ReviewLaunch",
    "Sls2LiteratureReviewApp",
    "build_default_sls2_candidate",
]
