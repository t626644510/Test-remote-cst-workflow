"""Read a literature corpus into a safe, browser-ready review payload.

The source bundle is immutable input.  Review decisions are stored separately
by :mod:`rf_cem.literature_semantics.review_server`; this module never edits a
semantic package, draft prior, PDF, or evidence image.
"""

from __future__ import annotations

from base64 import b64encode
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Union

import yaml

from .types import SEMANTIC_ITEM_SECTIONS, canonical_sha256
from .validator import validate_semantic_package


CORPUS_SCHEMA_VERSION = "literature_corpus_audit.v0"
REVIEW_PAYLOAD_SCHEMA_VERSION = "literature_review_payload.v1"
MAX_STRUCTURED_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class ReviewBundleError(ValueError):
    """Raised when a literature review bundle is unsafe or malformed."""


ManifestInput = Union[Path, str, Mapping[str, Any]]


class ReviewBundleLoader:
    """Load a corpus and its evidence below a confined bundle root."""

    def __init__(self, bundle_root: Path, *, max_image_bytes: int = MAX_IMAGE_BYTES) -> None:
        root = Path(bundle_root).expanduser().resolve()
        if not root.is_dir():
            raise ReviewBundleError(f"bundle root is not a directory: {bundle_root}")
        if max_image_bytes <= 0:
            raise ReviewBundleError("max_image_bytes must be positive")
        self.root = root
        self.max_image_bytes = int(max_image_bytes)

    def build_payload(
        self,
        corpus_manifest: ManifestInput,
        *,
        paper_id: str,
        geometry_projection: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Return a detached payload for the interactive literature reviewer."""
        manifest = self._load_manifest(corpus_manifest)
        self._select_paper(manifest, paper_id)
        projection = deepcopy(dict(geometry_projection or {}))
        papers: list[dict[str, Any]] = []
        review_items: list[dict[str, Any]] = []
        paper_bindings: dict[str, dict[str, str]] = {}
        active_semantics: dict[str, Any] = {}
        seen_ids: set[str] = set()
        for index, raw_manifest in enumerate(manifest["papers"]):
            if not isinstance(raw_manifest, Mapping):
                raise ReviewBundleError(f"corpus papers[{index}] must be a mapping")
            entry = deepcopy(dict(raw_manifest))
            entry_id = str(entry.get("id") or "").strip()
            if not entry_id or entry_id in seen_ids:
                raise ReviewBundleError(
                    f"corpus paper id must be non-empty and unique: {entry_id!r}"
                )
            seen_ids.add(entry_id)
            loaded = self._load_paper_payload(entry_id, entry)
            papers.append(loaded["paper"])
            review_items.extend(
                self._review_items(
                    entry_id,
                    loaded["semantics"],
                    loaded["draft"],
                    loaded["gallery"],
                    projection if entry_id == paper_id else {},
                )
            )
            paper_bindings[entry_id] = {
                "semantics_sha256": canonical_sha256(loaded["semantics"]),
                "draft_sha256": canonical_sha256(loaded["draft"]),
            }
            if entry_id == paper_id:
                active_semantics = loaded["semantics"]
        payload: dict[str, Any] = {
            "schema_version": REVIEW_PAYLOAD_SCHEMA_VERSION,
            "title": str(manifest.get("title") or "RF-CEM Literature Review"),
            "generated_at": manifest.get("generated_at"),
            "active_paper_id": paper_id,
            "corpus": {
                "cross_paper_findings": deepcopy(manifest.get("cross_paper_findings", [])),
                "warnings": deepcopy(manifest.get("warnings", [])),
            },
            "papers": papers,
            "semantic_candidates": self._semantic_candidates(active_semantics),
            "geometry_projection": projection,
            "review_items": review_items,
            "safety": {
                "preview_only": True,
                "live_cst": False,
                "production_prior_mutated": False,
                "claim": "geometry hypothesis / paper approximation, not RF performance reproduction",
            },
        }
        payload["source_binding"] = {
            "active_paper_id": paper_id,
            "papers": paper_bindings,
            "geometry_projection_sha256": canonical_sha256(projection),
        }
        payload["payload_sha256"] = canonical_sha256(payload)
        return payload

    def _load_paper_payload(
        self, paper_id: str, paper_manifest: Mapping[str, Any]
    ) -> dict[str, Any]:
        source_manifest = self._read_reference(
            paper_manifest.get("source_manifest"), {".json", ".yaml", ".yml"}
        )
        summary = self._read_reference(
            paper_manifest.get("paper_summary") or paper_manifest.get("summary"),
            {".json"},
        )
        semantics = self._read_reference(
            paper_manifest.get("literature_semantics")
            or paper_manifest.get("semantic_package"),
            {".json", ".yaml", ".yml"},
        )
        draft = self._read_reference(
            paper_manifest.get("draft_prior") or paper_manifest.get("draft"),
            {".json", ".yaml", ".yml"},
        )
        validation = [
            {"severity": issue.severity, "path": issue.path, "message": issue.message}
            for issue in validate_semantic_package(semantics)
        ]
        gallery = [
            self._load_gallery_image(entry, index=index)
            for index, entry in enumerate(paper_manifest.get("evidence_images", []))
            if isinstance(entry, Mapping)
        ]
        evidence_layers = {
            "text": deepcopy(semantics.get("text_evidence", [])),
            "images": deepcopy(semantics.get("image_evidence", [])),
            "gallery": gallery,
        }
        evidence_cards = [
            *deepcopy(evidence_layers["text"]),
            *deepcopy(evidence_layers["images"]),
            *deepcopy(gallery),
        ]
        return {
            "semantics": semantics,
            "draft": draft,
            "gallery": gallery,
            "paper": {
                "id": paper_id,
                "paper_id": paper_id,
                "title": paper_manifest.get("title") or summary.get("title"),
                "authors": deepcopy(paper_manifest.get("authors", [])),
                "arxiv_id": paper_manifest.get("arxiv_id"),
                "manifest": deepcopy(dict(paper_manifest)),
                "source_manifest": source_manifest,
                "paper_summary": summary,
                "literature_semantics": semantics,
                "draft_prior": draft,
                "evidence": evidence_cards,
                "evidence_layers": evidence_layers,
                "validation": validation,
            },
        }

    def session_seed(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return the small immutable binding stored with mutable review state."""
        paper_id = str(payload.get("active_paper_id") or "")
        item_ids = [
            str(item.get("id"))
            for item in payload.get("review_items", [])
            if isinstance(item, Mapping) and item.get("id")
        ]
        return {
            "review_scope": {
                "paper_id": paper_id,
                "payload_sha256": payload.get("payload_sha256"),
                "source_binding": deepcopy(payload.get("source_binding", {})),
                "review_item_ids": item_ids,
                "preview_only": True,
            }
        }

    def _load_manifest(self, source: ManifestInput) -> dict[str, Any]:
        if isinstance(source, Mapping):
            manifest = deepcopy(dict(source))
        else:
            manifest = self._read_path(
                self._safe_path(source, "corpus manifest"), {".json"}
            )
        if manifest.get("schema_version") != CORPUS_SCHEMA_VERSION:
            raise ReviewBundleError(
                f"unsupported corpus schema_version: {manifest.get('schema_version')!r}"
            )
        if not isinstance(manifest.get("papers"), list):
            raise ReviewBundleError("corpus manifest papers must be a list")
        return manifest

    @staticmethod
    def _select_paper(manifest: Mapping[str, Any], paper_id: str) -> dict[str, Any]:
        matches = [
            item
            for item in manifest.get("papers", [])
            if isinstance(item, Mapping) and str(item.get("id")) == paper_id
        ]
        if len(matches) != 1:
            raise ReviewBundleError(
                f"paper id must identify exactly one corpus entry: {paper_id!r}"
            )
        return deepcopy(dict(matches[0]))

    def _read_reference(self, reference: object, suffixes: set[str]) -> dict[str, Any]:
        if reference is None or reference == "":
            raise ReviewBundleError("required structured resource reference is missing")
        return self._read_path(self._safe_path(reference, "structured resource"), suffixes)

    @staticmethod
    def _read_path(path: Path, suffixes: set[str]) -> dict[str, Any]:
        if path.suffix.lower() not in suffixes:
            raise ReviewBundleError(f"unsupported structured resource extension: {path}")
        if not path.is_file():
            raise ReviewBundleError(f"structured resource is not a file: {path.name}")
        if path.stat().st_size > MAX_STRUCTURED_BYTES:
            raise ReviewBundleError(f"structured resource exceeds size limit: {path.name}")
        try:
            text = path.read_text(encoding="utf-8")
            value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
        except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
            raise ReviewBundleError(f"cannot read structured resource {path.name}: {exc}") from exc
        if not isinstance(value, dict):
            raise ReviewBundleError(f"structured resource must contain a mapping: {path.name}")
        return value

    def _safe_path(self, reference: object, label: str) -> Path:
        if not isinstance(reference, (str, Path)):
            raise ReviewBundleError(f"{label} path must be a string")
        path = Path(reference)
        candidate = path if path.is_absolute() else self.root / path
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ReviewBundleError(f"{label} path escapes bundle root: {reference}") from exc
        return resolved

    def _load_gallery_image(self, entry: Mapping[str, Any], *, index: int) -> dict[str, Any]:
        result = deepcopy(dict(entry))
        result.setdefault("id", f"evidence:gallery:{index + 1}")
        result.setdefault("human_review_status", "pending")
        result["integrity_status"] = "ok"
        try:
            path = self._safe_path(entry.get("path"), f"evidence image {index}")
            raw = path.read_bytes()
            if len(raw) > self.max_image_bytes:
                raise ReviewBundleError(
                    f"evidence image exceeds max_image_bytes={self.max_image_bytes}"
                )
            mime = _image_mime(path, raw)
            actual = hashlib.sha256(raw).hexdigest()
            expected = str(entry.get("sha256") or "").removeprefix("sha256:")
            if expected and expected.lower() != actual:
                raise ReviewBundleError("evidence image checksum mismatch")
            result["sha256"] = actual
            result["data_uri"] = f"data:{mime};base64,{b64encode(raw).decode('ascii')}"
        except (OSError, ReviewBundleError) as exc:
            result["integrity_status"] = "error"
            result["integrity_detail"] = str(exc)
            result["data_uri"] = ""
        return result

    @staticmethod
    def _semantic_candidates(semantics: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "classification": deepcopy(semantics.get("classification", {})),
            "sections": {
                section: deepcopy(semantics.get(section, []))
                for section in SEMANTIC_ITEM_SECTIONS
            },
        }

    def _review_items(
        self,
        paper_id: str,
        semantics: Mapping[str, Any],
        draft: Mapping[str, Any],
        gallery: list[dict[str, Any]],
        geometry_projection: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for section in ("text_evidence", "image_evidence"):
            for index, value in enumerate(semantics.get(section, [])):
                if isinstance(value, Mapping):
                    items.append(
                        self._review_item(paper_id, "evidence", section, index, value)
                    )
        for index, value in enumerate(gallery):
            items.append(
                self._review_item(paper_id, "evidence", "gallery", index, value)
            )
        classification = semantics.get("classification")
        if isinstance(classification, Mapping):
            items.append(
                self._review_item(
                    paper_id, "semantics", "classification", 0, classification
                )
            )
        for section in SEMANTIC_ITEM_SECTIONS:
            for index, value in enumerate(semantics.get(section, [])):
                if isinstance(value, Mapping):
                    items.append(
                        self._review_item(paper_id, "semantics", section, index, value)
                    )
        patch_items = draft.get("review", {}).get("patch_items", [])
        for index, value in enumerate(patch_items):
            if isinstance(value, Mapping):
                items.append(
                    self._review_item(
                        paper_id, "semantics", "draft_prior_patch", index, value
                    )
                )
        if geometry_projection:
            projection_review = {
                "id": geometry_projection.get("id")
                or geometry_projection.get("candidate_id")
                or "geometry_projection",
                "title": "SLS-2 geometry hypothesis / 论文近似",
                "candidate_id": geometry_projection.get("candidate_id"),
                "parameter_tuple": deepcopy(geometry_projection.get("parameter_tuple", {})),
                "review_status": geometry_projection.get("review_status", "pending"),
                "claim": "geometry hypothesis / paper approximation, not RF performance reproduction",
                "validation": deepcopy(geometry_projection.get("validation", {})),
            }
            items.append(
                self._review_item(
                    paper_id, "geometry", "geometry_projection", 0, projection_review
                )
            )
        return items

    @staticmethod
    def _review_item(
        paper_id: str,
        layer: str,
        section: str,
        index: int,
        value: Mapping[str, Any],
    ) -> dict[str, Any]:
        supplied_id = value.get("id") or value.get("item_id")
        original_id = str(supplied_id or f"item-{index + 1}")
        item_id = f"{paper_id}::{layer}::{section}::{original_id}"
        if section == "classification":
            label = "classification: " + " / ".join(
                str(value.get(key) or "?")
                for key in ("cavity_family", "cell_count", "beta_class")
            )
            semantic_path = "classification"
        else:
            label = _first_label(value) or original_id
            semantic_path = f"{section}[{index}]"
        return {
            "id": item_id,
            "original_id": original_id,
            "paper_id": paper_id,
            "layer": layer,
            "section": section,
            "semantic_path": semantic_path,
            "label": label,
            "human_review_status": str(value.get("human_review_status") or "pending"),
            "review_note": str(value.get("review_note") or ""),
            "source_refs": deepcopy(
                value.get("source_refs") or value.get("evidence_refs") or []
            ),
            "content": deepcopy(dict(value)),
        }


def _first_label(value: Mapping[str, Any]) -> str:
    for key in (
        "title",
        "feature_name",
        "motif_name",
        "name",
        "curve_region",
        "parameter_name",
        "objective_name",
        "constraint_id",
        "target_path",
        "figure_id",
        "id",
    ):
        if value.get(key) not in {None, ""}:
            return str(value[key])
    return ""


def _image_mime(path: Path, raw: bytes) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png" and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if suffix in {".jpg", ".jpeg"} and raw.startswith(b"\xff\xd8"):
        return "image/jpeg"
    raise ReviewBundleError(f"unsupported or malformed evidence image: {path.name}")
