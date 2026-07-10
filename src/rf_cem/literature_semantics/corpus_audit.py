"""Build a self-contained audit report for a literature semantic corpus."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
import hashlib
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

import yaml

from .prior_mapper import immutable_draft_sha256
from .types import (
    DRAFT_PRIOR_SCHEMA_VERSION,
    SEMANTIC_ITEM_SECTIONS,
    ValidationIssue,
    canonical_sha256,
)
from .validator import validate_semantic_package


CORPUS_SCHEMA_VERSION = "literature_corpus_audit.v0"
DEFAULT_MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_STRUCTURED_BYTES = 4 * 1024 * 1024
MAX_SOURCE_PDF_BYTES = 64 * 1024 * 1024


class CorpusAuditError(ValueError):
    """Raised when a corpus manifest or resource is unsafe to consume."""


@dataclass(frozen=True)
class _ResourceAudit:
    label: str
    reference: str
    status: str
    size_bytes: Optional[int] = None
    sha256: str = ""
    detail: str = ""


@dataclass(frozen=True)
class _ImageAudit:
    reference: str
    status: str
    page: object
    figure_id: str
    caption: str
    evidence_refs: tuple[str, ...]
    size_bytes: Optional[int] = None
    sha256: str = ""
    data_uri: str = ""
    detail: str = ""


@dataclass(frozen=True)
class _PaperAudit:
    manifest: Mapping[str, Any]
    summary: Mapping[str, Any]
    semantics: Mapping[str, Any]
    draft: Mapping[str, Any]
    resources: tuple[_ResourceAudit, ...]
    images: tuple[_ImageAudit, ...]
    validation_issues: tuple[ValidationIssue, ...]


ManifestInput = Union[Path, str, Mapping[str, Any]]


def build_corpus_audit_html(
    bundle_root: Path,
    corpus_manifest: ManifestInput,
    *,
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> str:
    """Return a self-contained, escaped HTML audit for a literature bundle.

    Every referenced resource must resolve below ``bundle_root``. PNG/JPEG
    evidence is embedded as a base64 data URI only after its type and size are
    checked; malformed or missing non-security resources remain visible as
    integrity failures in the report.
    """
    root = _resolved_root(bundle_root)
    if max_image_bytes <= 0:
        raise CorpusAuditError("max_image_bytes must be positive")
    manifest = _load_manifest(root, corpus_manifest)
    papers_value = manifest.get("papers")
    if not isinstance(papers_value, list):
        raise CorpusAuditError("corpus manifest papers must be a list")
    papers: list[_PaperAudit] = []
    for index, item in enumerate(papers_value):
        if not isinstance(item, Mapping):
            raise CorpusAuditError(f"corpus manifest papers[{index}] must be a mapping")
        papers.append(_load_paper(root, item, index=index, max_image_bytes=max_image_bytes))
    return _render_document(manifest, papers)


def write_corpus_audit_html(
    output_path: Path,
    bundle_root: Path,
    corpus_manifest: ManifestInput,
    *,
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> None:
    """Write a self-contained corpus audit HTML file using UTF-8."""
    html = build_corpus_audit_html(
        bundle_root,
        corpus_manifest,
        max_image_bytes=max_image_bytes,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def _resolved_root(bundle_root: Path) -> Path:
    root = Path(bundle_root).resolve()
    if not root.is_dir():
        raise CorpusAuditError(f"bundle root is not a directory: {bundle_root}")
    return root


def _load_manifest(root: Path, source: ManifestInput) -> dict[str, Any]:
    if isinstance(source, Mapping):
        manifest = dict(source)
    else:
        path = _resource_path(root, source, "corpus manifest")
        manifest, _ = _read_structured(path, allowed_suffixes={".json"})
    if manifest.get("schema_version") != CORPUS_SCHEMA_VERSION:
        raise CorpusAuditError(
            f"unsupported corpus schema_version: {manifest.get('schema_version')!r}; "
            f"expected {CORPUS_SCHEMA_VERSION!r}"
        )
    return manifest


def _load_paper(
    root: Path,
    paper: Mapping[str, Any],
    *,
    index: int,
    max_image_bytes: int,
) -> _PaperAudit:
    paper_id = str(paper.get("id") or paper.get("arxiv_id") or f"paper-{index + 1}")
    resources: list[_ResourceAudit] = []

    source_manifest, source_audit = _load_structured_resource(
        root,
        paper.get("source_manifest"),
        label="source manifest",
        allowed_suffixes={".json", ".yaml", ".yml"},
    )
    if paper.get("source_manifest") is not None:
        resources.append(source_audit)
    if source_manifest:
        source_pdf_audit = _load_source_pdf(
            root,
            paper,
            source_manifest,
            source_manifest_reference=paper.get("source_manifest"),
        )
        resources.append(source_pdf_audit)
        resources.append(
            _source_contract_audit(
                paper,
                source_manifest,
                source_pdf_audit,
                source_manifest_reference=source_audit.reference,
            )
        )

    summary, summary_audit = _load_structured_resource(
        root,
        paper.get("paper_summary") or paper.get("summary"),
        label="paper summary",
        allowed_suffixes={".json"},
    )
    resources.append(summary_audit)

    semantics, semantics_audit = _load_structured_resource(
        root,
        paper.get("literature_semantics") or paper.get("semantic_package"),
        label="literature semantics",
        allowed_suffixes={".json", ".yaml", ".yml"},
    )
    resources.append(semantics_audit)

    draft, draft_audit = _load_structured_resource(
        root,
        paper.get("draft_prior") or paper.get("draft"),
        label="draft prior",
        allowed_suffixes={".json", ".yaml", ".yml"},
    )
    draft_audit = _with_draft_status(draft_audit, draft)
    draft_audit = _with_draft_binding_status(draft_audit, draft, semantics)
    resources.append(draft_audit)

    expected_checksums = {
        "paper summary": paper.get("paper_summary_sha256"),
        "literature semantics": paper.get("literature_semantics_sha256"),
        "draft prior": paper.get("draft_prior_sha256") or paper.get("draft_sha256"),
        "source manifest": paper.get("source_manifest_sha256"),
    }
    resources = [
        _with_checksum_status(resource, expected_checksums.get(resource.label))
        for resource in resources
    ]

    images_value = paper.get("evidence_images", [])
    images: list[_ImageAudit] = []
    if not isinstance(images_value, list):
        resources.append(
            _ResourceAudit(
                label="evidence images",
                reference="",
                status="error",
                detail="evidence_images must be a list",
            )
        )
    else:
        for image_index, image in enumerate(images_value):
            images.append(
                _load_image(
                    root,
                    image,
                    label=f"{paper_id} evidence_images[{image_index}]",
                    max_image_bytes=max_image_bytes,
                )
            )
    known_evidence_refs = _known_evidence_refs(semantics)
    images = [_with_evidence_ref_status(image, known_evidence_refs) for image in images]

    validation_issues: tuple[ValidationIssue, ...] = ()
    if semantics:
        try:
            validation_issues = tuple(validate_semantic_package(semantics))
        except (TypeError, ValueError, yaml.YAMLError) as exc:
            validation_issues = (
                ValidationIssue("error", "literature_semantics", f"validator failed: {exc}"),
            )

    enriched_manifest = dict(paper)
    if source_manifest:
        metadata = source_manifest.get("metadata", {})
        source = source_manifest.get("source", {})
        if isinstance(metadata, Mapping):
            for key in ("title", "authors"):
                enriched_manifest.setdefault(key, metadata.get(key))
        if isinstance(source, Mapping):
            enriched_manifest.setdefault("arxiv_id", source.get("arxiv_id"))
            enriched_manifest.setdefault("version", source.get("version"))
            enriched_manifest.setdefault("source_url", source.get("abs_url"))
        pdf = source_manifest.get("pdf", {})
        if isinstance(pdf, Mapping):
            enriched_manifest.setdefault("pdf_sha256", pdf.get("sha256"))

    return _PaperAudit(
        manifest=enriched_manifest,
        summary=summary,
        semantics=semantics,
        draft=draft,
        resources=tuple(resources),
        images=tuple(images),
        validation_issues=validation_issues,
    )


def _load_structured_resource(
    root: Path,
    reference: object,
    *,
    label: str,
    allowed_suffixes: set[str],
) -> tuple[dict[str, Any], _ResourceAudit]:
    if not isinstance(reference, (str, Path)) or not str(reference).strip():
        return {}, _ResourceAudit(label, "", "error", detail=f"missing {label} reference")
    path = _resource_path(root, reference, label)
    relative = _relative_display(path, root)
    try:
        payload, raw = _read_structured(path, allowed_suffixes=allowed_suffixes)
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError, CorpusAuditError) as exc:
        return {}, _ResourceAudit(label, relative, "error", detail=str(exc))
    return payload, _ResourceAudit(
        label,
        relative,
        "ok",
        size_bytes=len(raw),
        sha256=_sha256(raw),
    )


def _read_structured(path: Path, *, allowed_suffixes: set[str]) -> tuple[dict[str, Any], bytes]:
    if path.suffix.lower() not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        raise CorpusAuditError(f"unsupported structured resource extension {path.suffix!r}; expected {allowed}")
    if not path.is_file():
        raise CorpusAuditError(f"resource is not a file: {path.name}")
    size = path.stat().st_size
    if size > MAX_STRUCTURED_BYTES:
        raise CorpusAuditError(
            f"structured resource exceeds {MAX_STRUCTURED_BYTES} bytes: {path.name} ({size} bytes)"
        )
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        payload = yaml.safe_load(text) or {}
    if not isinstance(payload, dict):
        raise CorpusAuditError(f"structured resource must contain a mapping: {path.name}")
    return payload, raw


def _load_source_pdf(
    root: Path,
    paper: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    *,
    source_manifest_reference: object,
) -> _ResourceAudit:
    pdf_metadata = source_manifest.get("pdf", {})
    if not isinstance(pdf_metadata, Mapping):
        return _ResourceAudit("source PDF", "", "error", detail="source manifest pdf must be a mapping")
    explicit_reference = paper.get("source_pdf")
    manifest_pdf_path = pdf_metadata.get("path")
    if explicit_reference:
        reference = explicit_reference
    elif manifest_pdf_path and source_manifest_reference:
        reference = Path(str(source_manifest_reference)).parent / str(manifest_pdf_path)
    else:
        return _ResourceAudit(
            "source PDF",
            "",
            "error",
            detail="source manifest does not identify a source PDF path",
        )

    path = _resource_path(root, reference, "source PDF")
    relative = _relative_display(path, root)
    try:
        if path.suffix.lower() != ".pdf" or not path.is_file():
            raise CorpusAuditError(f"source PDF is not a .pdf file: {path.name}")
        size = path.stat().st_size
        if size > MAX_SOURCE_PDF_BYTES:
            raise CorpusAuditError(
                f"source PDF exceeds {MAX_SOURCE_PDF_BYTES} bytes: {path.name} ({size} bytes)"
            )
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise CorpusAuditError(f"source PDF is missing the %PDF- header: {path.name}")
        digest = _sha256_file(path)
    except (OSError, CorpusAuditError) as exc:
        return _ResourceAudit("source PDF", relative, "error", detail=str(exc))

    errors = []
    expected_size = pdf_metadata.get("size_bytes")
    if expected_size is not None and expected_size != size:
        errors.append(f"size mismatch: expected {expected_size}, calculated {size}")
    for label, expected in (
        ("source manifest", pdf_metadata.get("sha256")),
        ("corpus manifest", paper.get("pdf_sha256")),
    ):
        if expected and _normalise_digest(expected) != digest:
            errors.append(f"{label} checksum mismatch: expected {expected}, calculated {digest}")
    return _ResourceAudit(
        "source PDF",
        relative,
        "error" if errors else "ok",
        size_bytes=size,
        sha256=digest,
        detail="; ".join(errors),
    )


def _source_contract_audit(
    paper: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    source_pdf: _ResourceAudit,
    *,
    source_manifest_reference: str,
) -> _ResourceAudit:
    source = source_manifest.get("source", {})
    metadata = source_manifest.get("metadata", {})
    errors = []
    if not isinstance(source, Mapping):
        errors.append("source manifest source must be a mapping")
        source = {}
    if not isinstance(metadata, Mapping):
        errors.append("source manifest metadata must be a mapping")
        metadata = {}
    comparisons = (
        ("arxiv_id", paper.get("arxiv_id"), source.get("arxiv_id")),
        ("version", paper.get("version"), source.get("version")),
        ("title", paper.get("title"), metadata.get("title")),
        ("source_url", paper.get("source_url"), source.get("abs_url")),
    )
    for label, declared, pinned in comparisons:
        if declared not in (None, "") and pinned not in (None, "") and declared != pinned:
            errors.append(f"{label} mismatch: corpus={declared!r}, source_manifest={pinned!r}")
    if source_pdf.status != "ok":
        errors.append("source PDF integrity failed")
    return _ResourceAudit(
        "source contract",
        source_manifest_reference,
        "error" if errors else "ok",
        detail="; ".join(errors),
    )


def _load_image(
    root: Path,
    value: object,
    *,
    label: str,
    max_image_bytes: int,
) -> _ImageAudit:
    if isinstance(value, (str, Path)):
        entry: Mapping[str, Any] = {"path": value}
    elif isinstance(value, Mapping):
        entry = value
    else:
        return _ImageAudit("", "error", "", "", "", (), detail=f"{label} must be a mapping")

    reference = entry.get("path")
    if not isinstance(reference, (str, Path)) or not str(reference).strip():
        return _ImageAudit("", "error", entry.get("page", ""), "", "", (), detail=f"{label} missing path")
    path = _resource_path(root, reference, label)
    relative = _relative_display(path, root)
    evidence_refs = tuple(str(ref) for ref in entry.get("evidence_refs", []) or [])
    common = {
        "reference": relative,
        "page": entry.get("page", ""),
        "figure_id": str(entry.get("figure_id", "")),
        "caption": str(entry.get("caption", "")),
        "evidence_refs": evidence_refs,
    }
    try:
        if not path.is_file():
            raise CorpusAuditError(f"image is not a file: {path.name}")
        size = path.stat().st_size
        if size > max_image_bytes:
            raise CorpusAuditError(
                f"image exceeds max_image_bytes={max_image_bytes}: {path.name} ({size} bytes)"
            )
        raw = path.read_bytes()
        mime = _image_mime(path, raw)
    except (OSError, CorpusAuditError) as exc:
        return _ImageAudit(status="error", detail=str(exc), **common)

    digest = _sha256(raw)
    expected = entry.get("sha256")
    status = "ok"
    detail = ""
    if expected and _normalise_digest(expected) != digest:
        status = "error"
        detail = f"checksum mismatch: expected {expected}, calculated {digest}"
    return _ImageAudit(
        status=status,
        size_bytes=len(raw),
        sha256=digest,
        data_uri=f"data:{mime};base64,{b64encode(raw).decode('ascii')}",
        detail=detail,
        **common,
    )


def _image_mime(path: Path, raw: bytes) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png" and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if suffix in {".jpg", ".jpeg"} and raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise CorpusAuditError(f"image must be a valid PNG or JPEG matching its extension: {path.name}")


def _resource_path(root: Path, reference: object, label: str) -> Path:
    raw = Path(str(reference))
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CorpusAuditError(f"{label} path escapes bundle root: {reference}") from exc
    return resolved


def _with_checksum_status(resource: _ResourceAudit, expected: object) -> _ResourceAudit:
    if not expected or resource.status != "ok":
        return resource
    if _normalise_digest(expected) == resource.sha256:
        return resource
    return _ResourceAudit(
        resource.label,
        resource.reference,
        "error",
        resource.size_bytes,
        resource.sha256,
        f"checksum mismatch: expected {expected}, calculated {resource.sha256}",
    )


def _with_draft_status(resource: _ResourceAudit, draft: Mapping[str, Any]) -> _ResourceAudit:
    if resource.status != "ok":
        return resource
    errors = []
    if draft.get("schema_version") != DRAFT_PRIOR_SCHEMA_VERSION:
        errors.append(f"expected schema_version {DRAFT_PRIOR_SCHEMA_VERSION!r}")
    review = draft.get("review")
    if not isinstance(review, Mapping):
        errors.append("review must be a mapping")
    elif not isinstance(review.get("patch_items"), list):
        errors.append("review.patch_items must be a list")
    if not errors:
        return resource
    return _ResourceAudit(
        resource.label,
        resource.reference,
        "error",
        resource.size_bytes,
        resource.sha256,
        "; ".join(errors),
    )


def _with_draft_binding_status(
    resource: _ResourceAudit,
    draft: Mapping[str, Any],
    semantics: Mapping[str, Any],
) -> _ResourceAudit:
    if resource.status != "ok":
        return resource
    errors = []
    integrity = draft.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("algorithm") != "sha256":
        errors.append("draft is missing supported integrity metadata")
    else:
        expected_semantics = canonical_sha256(dict(semantics))
        if integrity.get("semantic_package_sha256") != expected_semantics:
            errors.append("draft semantic_package_sha256 does not match literature semantics")
        if not integrity.get("base_prior_sha256"):
            errors.append("draft base_prior_sha256 is missing")
        expected_draft = immutable_draft_sha256(draft)
        if integrity.get("immutable_draft_sha256") != expected_draft:
            errors.append("draft immutable_draft_sha256 does not match draft content")
    if not errors:
        return resource
    detail = "; ".join(part for part in (resource.detail, *errors) if part)
    return _ResourceAudit(
        resource.label,
        resource.reference,
        "error",
        resource.size_bytes,
        resource.sha256,
        detail,
    )


def _with_evidence_ref_status(image: _ImageAudit, known_refs: set[str]) -> _ImageAudit:
    unknown = sorted(set(image.evidence_refs) - known_refs)
    if not unknown:
        return image
    detail = "; ".join(
        part for part in (image.detail, f"unknown semantic evidence refs: {', '.join(unknown)}") if part
    )
    return _ImageAudit(
        image.reference,
        "error",
        image.page,
        image.figure_id,
        image.caption,
        image.evidence_refs,
        image.size_bytes,
        image.sha256,
        image.data_uri,
        detail,
    )


def _known_evidence_refs(semantics: Mapping[str, Any]) -> set[str]:
    refs: set[str] = set()
    for section in ("evidence_sources", "text_evidence", "image_evidence"):
        for item in semantics.get(section, []) or []:
            if isinstance(item, Mapping) and item.get("id"):
                refs.add(str(item["id"]))
    return refs


def _normalise_digest(value: object) -> str:
    text = str(value).strip().lower()
    if text.startswith("sha256:"):
        text = text[7:]
    return f"sha256:{text}"


def _sha256(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _relative_display(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _render_document(manifest: Mapping[str, Any], papers: Sequence[_PaperAudit]) -> str:
    title = str(manifest.get("title") or "RF-CEM Literature Corpus Audit")
    conflicts = _detect_conflicts(papers)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            f"<title>{_h(title)}</title>",
            "<style>",
            "body{font-family:Segoe UI,Arial,sans-serif;margin:0;color:#1f2933;background:#f4f7fa}",
            "main{max-width:1240px;margin:0 auto;padding:28px}",
            "section,article{background:#fff;border:1px solid #d9e2ec;border-radius:8px;margin:16px 0;padding:18px}",
            "article>section{background:#fbfdff;margin:14px 0}",
            "h1,h2,h3{margin:0 0 12px}h2{border-bottom:2px solid #d9e2ec;padding-bottom:8px}",
            "table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}",
            "th,td{border:1px solid #bcccdc;padding:7px;text-align:left;vertical-align:top}",
            "th{background:#eaf0f6}pre{white-space:pre-wrap;word-break:break-word;margin:0}",
            ".ok{color:#047857;font-weight:600}.warning{color:#a16207;font-weight:600}.error{color:#b91c1c;font-weight:600}",
            ".muted{color:#52606d}.pill{border:1px solid #bcccdc;border-radius:999px;padding:2px 7px;display:inline-block}",
            ".gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}",
            "figure{border:1px solid #d9e2ec;border-radius:6px;margin:0;padding:10px;background:#fff}",
            "figure img{display:block;max-width:100%;max-height:420px;margin:0 auto 8px}figcaption{font-size:13px}",
            "</style>",
            "</head>",
            "<body><main>",
            f"<h1>{_h(title)}</h1>",
            _render_corpus_integrity(manifest, papers),
            _render_cross_paper(manifest, papers, conflicts),
            "".join(_render_paper(paper, index) for index, paper in enumerate(papers)),
            "</main></body></html>",
        ]
    )


def _render_corpus_integrity(manifest: Mapping[str, Any], papers: Sequence[_PaperAudit]) -> str:
    resources = [resource for paper in papers for resource in paper.resources]
    images = [image for paper in papers for image in paper.images]
    manifest_issues = _manifest_integrity_issues(manifest, papers)
    errors = sum(item.status == "error" for item in [*resources, *images]) + len(manifest_issues)
    validation_errors = sum(
        issue.severity == "error" for paper in papers for issue in paper.validation_issues
    )
    warnings = manifest.get("warnings", []) or []
    return (
        "<section><h2>Corpus / integrity / validation</h2>"
        "<table>"
        f"<tr><th>Schema</th><td>{_h(manifest.get('schema_version', ''))}</td></tr>"
        f"<tr><th>Generated at</th><td>{_h(manifest.get('generated_at', ''))}</td></tr>"
        f"<tr><th>Papers</th><td>{len(papers)}</td></tr>"
        f"<tr><th>Resource integrity errors</th><td class=\"{'error' if errors else 'ok'}\">{errors}</td></tr>"
        f"<tr><th>Semantic validation errors</th><td class=\"{'error' if validation_errors else 'ok'}\">{validation_errors}</td></tr>"
        "</table>"
        "<h3>Manifest integrity</h3>"
        + _render_list(manifest_issues, empty="Manifest contract complete")
        + "<h3>Corpus warnings</h3>"
        + _render_list(warnings, empty="None declared")
        + "</section>"
    )


def _render_cross_paper(
    manifest: Mapping[str, Any],
    papers: Sequence[_PaperAudit],
    conflicts: Sequence[str],
) -> str:
    rows = []
    for paper in papers:
        context = paper.semantics.get("request_context", {})
        classification = paper.semantics.get("classification", {})
        review = paper.draft.get("review", {})
        patch_items = review.get("patch_items", []) if isinstance(review, Mapping) else []
        statuses = sorted(
            {
                str(item.get("human_review_status", ""))
                for item in patch_items or []
                if isinstance(item, Mapping)
            }
        )
        rows.append(
            "<tr>"
            f"<td>{_h(_paper_id(paper))}</td>"
            f"<td>{_h(context.get('operating_regime', ''))}</td>"
            f"<td>{_h(classification.get('cavity_family', ''))}</td>"
            f"<td>{_h(context.get('frequency_target_mhz', ''))}</td>"
            f"<td>{sum(issue.severity == 'error' for issue in paper.validation_issues)}</td>"
            f"<td>{_h(', '.join(statuses))}</td>"
            "</tr>"
        )
    findings = manifest.get("cross_paper_findings", []) or []
    return (
        "<section><h2>Cross-paper comparison and conflicts</h2>"
        "<table><tr><th>Paper</th><th>Regime</th><th>Family</th><th>Target MHz</th>"
        "<th>Validation errors</th><th>Patch states</th></tr>"
        + "".join(rows)
        + "</table><h3>Declared cross-paper findings</h3>"
        + _render_list(findings, empty="None declared")
        + "<h3>Automatically detected semantic conflicts</h3>"
        + _render_list(conflicts, empty="No same-slot conflicts detected")
        + "</section>"
    )


def _render_paper(paper: _PaperAudit, index: int) -> str:
    title = paper.manifest.get("title") or paper.summary.get("title") or _paper_id(paper)
    metadata = {
        "id": _paper_id(paper),
        "arxiv_id": paper.manifest.get("arxiv_id", ""),
        "version": paper.manifest.get("version", ""),
        "title": title,
        "authors": paper.manifest.get("authors", []),
        "source_url": paper.manifest.get("source_url", ""),
        "pdf_sha256 (declared; PDF not read by this audit)": paper.manifest.get("pdf_sha256", ""),
    }
    return (
        f"<article><h2>Paper {index + 1}: {_h(title)}</h2>"
        + _mapping_table(metadata)
        + _render_resource_integrity(paper)
        + _render_validation(paper)
        + _render_summary(paper.summary)
        + _render_semantics(paper.semantics)
        + _render_patch_provenance(paper.draft)
        + _render_gallery(paper.images)
        + "</article>"
    )


def _render_resource_integrity(paper: _PaperAudit) -> str:
    rows = []
    for item in paper.resources:
        rows.append(
            "<tr>"
            f"<td>{_h(item.label)}</td><td>{_h(item.reference)}</td>"
            f"<td class=\"{_status_class(item.status)}\">{_h(item.status)}</td>"
            f"<td>{_h(item.size_bytes if item.size_bytes is not None else '')}</td>"
            f"<td>{_h(item.sha256)}</td><td>{_h(item.detail)}</td>"
            "</tr>"
        )
    for item in paper.images:
        rows.append(
            "<tr>"
            f"<td>evidence image</td><td>{_h(item.reference)}</td>"
            f"<td class=\"{_status_class(item.status)}\">{_h(item.status)}</td>"
            f"<td>{_h(item.size_bytes if item.size_bytes is not None else '')}</td>"
            f"<td>{_h(item.sha256)}</td><td>{_h(item.detail)}</td>"
            "</tr>"
        )
    return (
        "<section><h3>Resource integrity</h3>"
        "<table><tr><th>Resource</th><th>Reference</th><th>Status</th><th>Bytes</th>"
        "<th>Calculated SHA-256</th><th>Detail</th></tr>"
        + "".join(rows)
        + "</table></section>"
    )


def _render_validation(paper: _PaperAudit) -> str:
    if not paper.semantics:
        content = '<p class="error">Semantic package unavailable; validation not run.</p>'
    elif not paper.validation_issues:
        content = '<p class="ok">Semantic package validation passed without issues.</p>'
    else:
        rows = [
            "<tr>"
            f"<td class=\"{_status_class(issue.severity)}\">{_h(issue.severity)}</td>"
            f"<td>{_h(issue.path)}</td><td>{_h(issue.message)}</td>"
            "</tr>"
            for issue in paper.validation_issues
        ]
        content = (
            "<table><tr><th>Severity</th><th>Path</th><th>Message</th></tr>"
            + "".join(rows)
            + "</table>"
        )
    return f"<section><h3>Semantic validation</h3>{content}</section>"


def _render_summary(summary: Mapping[str, Any]) -> str:
    summary_text = _first_present(summary, "summary", "executive_summary", "abstract_summary", "abstract")
    citation = _first_present(summary, "citation", "recommended_citation", default="")
    selection = _first_present(summary, "selection_rationale", "selection_reason", default="")
    methodology = _first_present(summary, "methodology", "methods", default=[])
    findings = _first_present(summary, "key_findings", "findings", "rf_cem_findings", default=[])
    limitations = _first_present(summary, "limitations", "caveats", "scope_limitations", default=[])
    relevance = _first_present(summary, "rf_cem_relevance", "design_relevance", "relevance", default="")
    return (
        "<section><h3>Paper summary</h3>"
        "<h4>Citation</h4>"
        + _render_value(citation, empty="Citation unavailable")
        + "<h4>Selection rationale</h4>"
        + _render_value(selection, empty="Selection rationale unavailable")
        + "<h4>Methodology</h4>"
        + _render_list(methodology, empty="Methodology unavailable")
        + "<h4>Executive summary</h4>"
        + _render_value(summary_text, empty="Summary unavailable")
        + "<h3>Key findings</h3>"
        + _render_list(findings, empty="None recorded")
        + "<h3>Limitations</h3>"
        + _render_list(limitations, empty="None recorded")
        + "<h3>RF-CEM relevance</h3>"
        + _render_value(relevance, empty="Not explicitly recorded")
        + "<details><summary>Full paper summary record</summary><pre>"
        + _dump(summary)
        + "</pre></details>"
        + "</section>"
    )


def _render_semantics(semantics: Mapping[str, Any]) -> str:
    blocks = [
        "<h4>Request context</h4><pre>" + _dump(semantics.get("request_context", {})) + "</pre>",
        "<h4>Classification</h4><pre>" + _dump(semantics.get("classification", {})) + "</pre>",
        _render_semantic_evidence(semantics),
    ]
    for section in SEMANTIC_ITEM_SECTIONS:
        values = semantics.get(section, []) or []
        if not isinstance(values, list):
            blocks.append(f"<h4>{_h(section)}</h4><p class=\"error\">Expected a list.</p>")
            continue
        rows = []
        for item in values:
            if not isinstance(item, Mapping):
                rows.append(f"<tr><td colspan=\"5\">{_h(item)}</td></tr>")
                continue
            rows.append(
                "<tr>"
                f"<td>{_h(_semantic_label(section, item))}</td>"
                f"<td>{_h(item.get('confidence', ''))}</td>"
                f"<td>{_h(item.get('human_review_status', ''))}</td>"
                f"<td>{_h(', '.join(str(ref) for ref in item.get('source_refs', []) or []))}</td>"
                f"<td><pre>{_dump(item)}</pre></td>"
                "</tr>"
            )
        blocks.append(
            f"<h4>{_h(section)} <span class=\"pill\">{len(values)}</span></h4>"
            "<table><tr><th>Item</th><th>Confidence</th><th>Review</th><th>Evidence refs</th><th>Details</th></tr>"
            + "".join(rows)
            + "</table>"
        )
    return "<section><h3>Semantic groups</h3>" + "".join(blocks) + "</section>"


def _render_semantic_evidence(semantics: Mapping[str, Any]) -> str:
    rows = []
    for section in ("evidence_sources", "text_evidence", "image_evidence"):
        values = semantics.get(section, []) or []
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, Mapping):
                continue
            excerpt = item.get("short_excerpt") or item.get("caption") or item.get("title") or ""
            rows.append(
                "<tr>"
                f"<td>{_h(item.get('id', ''))}</td><td>{_h(section)}</td>"
                f"<td>{_h(item.get('paper_id', item.get('source_id', '')))}</td>"
                f"<td>{_h(item.get('page', ''))}</td>"
                f"<td>{_h(item.get('figure_id', item.get('section', '')))}</td>"
                f"<td>{_h(excerpt)}</td>"
                "</tr>"
            )
    return (
        "<h4>Semantic evidence provenance</h4>"
        "<table><tr><th>ID</th><th>Type</th><th>Paper</th><th>Page</th>"
        "<th>Figure/section</th><th>Excerpt/caption/title</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _render_patch_provenance(draft: Mapping[str, Any]) -> str:
    review = draft.get("review", {})
    patches = review.get("patch_items", []) if isinstance(review, Mapping) else []
    rows = []
    for patch in patches or []:
        if not isinstance(patch, Mapping):
            rows.append(f"<tr><td colspan=\"7\">{_h(patch)}</td></tr>")
            continue
        rows.append(
            "<tr>"
            f"<td>{_h(patch.get('id', ''))}</td>"
            f"<td>{_h(patch.get('target_path', ''))}</td>"
            f"<td><pre>{_dump(patch.get('value'))}</pre></td>"
            f"<td>{_h(', '.join(str(ref) for ref in patch.get('source_refs', []) or []))}</td>"
            f"<td>{_h(patch.get('confidence', ''))}</td>"
            f"<td>{_h(patch.get('human_review_status', ''))}</td>"
            f"<td>{_h(patch.get('rationale', ''))}</td>"
            "</tr>"
        )
    return (
        "<section><h3>Patch provenance</h3>"
        "<table><tr><th>ID</th><th>Target</th><th>Value</th><th>Evidence refs</th>"
        "<th>Confidence</th><th>Review</th><th>Rationale</th></tr>"
        + "".join(rows)
        + "</table></section>"
    )


def _render_gallery(images: Sequence[_ImageAudit]) -> str:
    figures = []
    for image in images:
        if image.data_uri:
            visual = f'<img src="{image.data_uri}" alt="Evidence image">'
        else:
            visual = f'<p class="error">Image unavailable: {_h(image.detail)}</p>'
        figures.append(
            "<figure>"
            + visual
            + "<figcaption>"
            f"<strong>{_h(image.figure_id or image.reference)}</strong><br>"
            f"Page: {_h(image.page)}<br>Caption: {_h(image.caption)}<br>"
            f"Evidence refs: {_h(', '.join(image.evidence_refs))}<br>"
            f"Integrity: <span class=\"{_status_class(image.status)}\">{_h(image.status)}</span>"
            "</figcaption></figure>"
        )
    return (
        "<section><h3>Evidence gallery</h3><div class=\"gallery\">"
        + ("".join(figures) if figures else '<p class="muted">No evidence images declared.</p>')
        + "</div></section>"
    )


def _manifest_integrity_issues(
    manifest: Mapping[str, Any],
    papers: Sequence[_PaperAudit],
) -> list[str]:
    issues = []
    for key in ("title", "generated_at", "cross_paper_findings", "warnings"):
        if key not in manifest:
            issues.append(f"top-level field is missing: {key}")
    for key in ("cross_paper_findings", "warnings"):
        if key in manifest and not isinstance(manifest[key], list):
            issues.append(f"top-level {key} must be a list")
    seen_ids: set[str] = set()
    for index, paper in enumerate(papers):
        paper_id = _paper_id(paper)
        if paper_id in seen_ids:
            issues.append(f"duplicate paper id: {paper_id}")
        seen_ids.add(paper_id)
        for key in ("id", "arxiv_id", "version", "title", "authors", "source_url", "pdf_sha256"):
            if paper.manifest.get(key) in (None, "", []):
                issues.append(f"papers[{index}] ({paper_id}) is missing {key}")
        if paper.manifest.get("authors") is not None and not isinstance(paper.manifest.get("authors"), list):
            issues.append(f"papers[{index}] ({paper_id}) authors must be a list")
    return issues


def _detect_conflicts(papers: Sequence[_PaperAudit]) -> list[str]:
    slots: dict[tuple[str, str], dict[str, set[str]]] = {}
    for paper in papers:
        paper_id = _paper_id(paper)
        for section, identity_key, value_keys in (
            ("named_features", "feature_name", ("presence",)),
            ("curve_priors", "curve_region", ("allowed_curve_types", "preferred_forms", "forbidden_forms")),
            ("parameter_ranges", "parameter_name", ("range", "unit", "range_type")),
            ("physical_constraints", "constraint_id", ("constraint_type", "statement")),
        ):
            for item in paper.semantics.get(section, []) or []:
                if not isinstance(item, Mapping) or not item.get(identity_key):
                    continue
                slot = (section, str(item[identity_key]))
                value = json.dumps(
                    {key: item.get(key) for key in value_keys},
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                slots.setdefault(slot, {}).setdefault(value, set()).add(paper_id)
    conflicts = []
    for (section, identity), values in sorted(slots.items()):
        if len(values) <= 1:
            continue
        variants = "; ".join(
            f"{', '.join(sorted(paper_ids))}: {value}"
            for value, paper_ids in sorted(values.items())
        )
        conflicts.append(f"{section}.{identity} has different claims — {variants}")
    return conflicts


def _paper_id(paper: _PaperAudit) -> str:
    return str(paper.manifest.get("id") or paper.manifest.get("arxiv_id") or "unknown-paper")


def _semantic_label(section: str, item: Mapping[str, Any]) -> str:
    keys = {
        "named_features": ("feature_name", "name"),
        "shape_motifs": ("name",),
        "curve_priors": ("curve_region",),
        "parameter_ranges": ("parameter_name",),
        "optimization_objectives": ("objective_name", "name"),
        "physical_constraints": ("constraint_id", "statement"),
    }.get(section, ("id", "name"))
    return str(next((item[key] for key in keys if item.get(key) is not None), ""))


def _mapping_table(mapping: Mapping[str, Any]) -> str:
    rows = "".join(
        f"<tr><th>{_h(key)}</th><td>{_h(_plain(value))}</td></tr>"
        for key, value in mapping.items()
    )
    return f"<table>{rows}</table>"


def _render_list(value: object, *, empty: str) -> str:
    if value in (None, "", [], {}):
        return f'<p class="muted">{_h(empty)}</p>'
    values = value if isinstance(value, list) else [value]
    return "<ul>" + "".join(f"<li>{_render_value(item)}</li>" for item in values) + "</ul>"


def _render_value(value: object, *, empty: str = "") -> str:
    if value in (None, "", [], {}):
        return f'<span class="muted">{_h(empty)}</span>' if empty else ""
    if isinstance(value, (Mapping, list, tuple)):
        return f"<pre>{_dump(value)}</pre>"
    return _h(value)


def _first_present(mapping: Mapping[str, Any], *keys: str, default: object = "") -> object:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _dump(value: object) -> str:
    return _h(yaml.safe_dump(value, sort_keys=False, allow_unicode=True).strip())


def _plain(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def _h(value: object) -> str:
    return escape(str(value), quote=True)


def _status_class(status: str) -> str:
    return status if status in {"ok", "warning", "error"} else "muted"
