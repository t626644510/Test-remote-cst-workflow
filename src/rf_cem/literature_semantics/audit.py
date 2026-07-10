"""HTML audit report generation for RF-CEM literature semantics."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from .types import REVIEW_STATUSES


def build_audit_html(package: Mapping[str, Any], draft_prior: Mapping[str, Any]) -> str:
    """Build a self-contained audit HTML report."""
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            "<title>RF-CEM Literature Semantics Audit</title>",
            "<style>",
            "body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1f2933;background:#f7f9fb}",
            "main{max-width:1180px;margin:0 auto}",
            "section{background:white;border:1px solid #d9e2ec;border-radius:6px;margin:16px 0;padding:16px}",
            "h1,h2{margin:0 0 12px}",
            "table{border-collapse:collapse;width:100%;font-size:14px}",
            "th,td{border:1px solid #d9e2ec;padding:6px;text-align:left;vertical-align:top}",
            "pre{white-space:pre-wrap;background:#f0f4f8;padding:10px;border-radius:4px;overflow:auto}",
            ".status{font-family:Consolas,monospace}",
            ".warn{color:#b45309}.ok{color:#047857}",
            "</style>",
            "</head>",
            "<body><main>",
            "<h1>RF-CEM Literature Semantics Audit</h1>",
            _corpus_summary(package),
            _evidence_cards(package),
            _prior_diff(draft_prior),
            _candidate_gallery(draft_prior),
            _review_controls(draft_prior),
            "</main></body></html>",
        ]
    )


def write_audit_html(path: Path, package: Mapping[str, Any], draft_prior: Mapping[str, Any]) -> None:
    """Write the audit report to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_audit_html(package, draft_prior), encoding="utf-8")


def _corpus_summary(package: Mapping[str, Any]) -> str:
    rows = []
    for source in package.get("evidence_sources", []) or []:
        if not isinstance(source, Mapping):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(str(source.get('id', '')))}</td>"
            f"<td>{escape(str(source.get('title', '')))}</td>"
            f"<td>{escape(str(source.get('year', '')))}</td>"
            f"<td>{escape(str(source.get('source_type', '')))}</td>"
            f"<td>{escape(str(source.get('venue', '')))}</td>"
            f"<td>{escape(str(source.get('license', source.get('license_status', ''))))}</td>"
            "</tr>"
        )
    return (
        "<section><h2>Corpus summary</h2>"
        f"<pre>{escape(json.dumps(package.get('request_context', {}), indent=2, ensure_ascii=False))}</pre>"
        "<table><tr><th>ID</th><th>Title</th><th>Year</th><th>Type</th><th>Venue</th><th>License/version</th></tr>"
        + "".join(rows)
        + "</table></section>"
    )


def _evidence_cards(package: Mapping[str, Any]) -> str:
    cards = []
    for section in ("text_evidence", "image_evidence"):
        for evidence in package.get(section, []) or []:
            if not isinstance(evidence, Mapping):
                continue
            summary = evidence.get("short_excerpt") or evidence.get("caption") or evidence.get("excerpt_hash") or ""
            cards.append(
                "<tr>"
                f"<td>{escape(str(evidence.get('id', '')))}</td>"
                f"<td>{escape(section)}</td>"
                f"<td>{escape(str(evidence.get('paper_id', evidence.get('source_id', ''))))}</td>"
                f"<td>{escape(str(evidence.get('page', '')))}</td>"
                f"<td>{escape(str(evidence.get('figure_id', '')))}</td>"
                f"<td>{escape(str(evidence.get('bbox', '')))}</td>"
                f"<td>{escape(str(summary))}</td>"
                "</tr>"
            )
    return (
        "<section><h2>Evidence cards</h2>"
        "<table><tr><th>ID</th><th>Mode</th><th>Paper</th><th>Page</th><th>Figure</th><th>BBox</th><th>Excerpt/caption</th></tr>"
        + "".join(cards)
        + "</table></section>"
    )


def _prior_diff(draft_prior: Mapping[str, Any]) -> str:
    rows = []
    for item in draft_prior.get("review", {}).get("patch_items", []) or []:
        if not isinstance(item, Mapping):
            continue
        value = yaml.safe_dump(item.get("value"), sort_keys=False, allow_unicode=True).strip()
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('id', '')))}</td>"
            f"<td>{escape(str(item.get('target_path', '')))}</td>"
            f"<td><pre>{escape(value)}</pre></td>"
            f"<td>{escape(', '.join(str(ref) for ref in item.get('source_refs', []) or []))}</td>"
            f"<td class=\"status\">{escape(str(item.get('human_review_status', '')))}</td>"
            "</tr>"
        )
    return (
        "<section><h2>Prior diff</h2>"
        "<table><tr><th>Patch</th><th>Target path</th><th>Proposed value</th><th>Evidence refs</th><th>Review</th></tr>"
        + "".join(rows)
        + "</table></section>"
    )


def _candidate_gallery(draft_prior: Mapping[str, Any]) -> str:
    rows = []
    for candidate in draft_prior.get("candidate_shape_priors", []) or []:
        if not isinstance(candidate, Mapping):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(str(candidate.get('id', '')))}</td>"
            f"<td>{escape(str(candidate.get('variant', '')))}</td>"
            f"<td>{escape(str(candidate.get('summary', '')))}</td>"
            f"<td>{escape(str(candidate.get('confidence', '')))}</td>"
            f"<td class=\"status\">{escape(str(candidate.get('human_review_status', '')))}</td>"
            "</tr>"
        )
    validation_state = "not_run_no_cst_validation_in_semantics_mvp"
    return (
        "<section><h2>Candidate gallery</h2>"
        f"<p>No-CST validation status: <span class=\"warn\">{validation_state}</span></p>"
        "<table><tr><th>ID</th><th>Variant</th><th>Summary</th><th>Confidence</th><th>Review</th></tr>"
        + "".join(rows)
        + "</table></section>"
    )


def _review_controls(draft_prior: Mapping[str, Any]) -> str:
    statuses = sorted(REVIEW_STATUSES - {"pending"})
    controls = " ".join(f"<code>{escape(status)}</code>" for status in statuses)
    return (
        "<section><h2>Review controls</h2>"
        f"<p>Allowed manual decisions: {controls}</p>"
        f"<pre>{escape(json.dumps(draft_prior.get('review', {}), indent=2, ensure_ascii=False))}</pre>"
        "</section>"
    )
