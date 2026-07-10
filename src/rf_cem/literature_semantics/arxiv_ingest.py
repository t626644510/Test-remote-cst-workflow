"""Small, auditable arXiv discovery and pinned-source ingestion helpers.

The module deliberately separates discovery from selection: search results are
metadata candidates only.  Relevance order is not evidence that a paper is
"classic", authoritative, or applicable to an RF-CEM design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tempfile
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"
ATOM = f"{{{ATOM_NS}}}"
ARXIV = f"{{{ARXIV_NS}}}"

_MODERN_ID_RE = re.compile(
    r"^(?P<year>\d{2})(?P<month>\d{2})\.(?P<sequence>\d{4,5})"
    r"(?:v(?P<version>[1-9]\d*))?$",
    re.IGNORECASE,
)
_LEGACY_ID_RE = re.compile(
    r"^(?P<archive>[A-Za-z][A-Za-z0-9.-]*)/"
    r"(?P<year>\d{2})(?P<month>\d{2})(?P<sequence>\d{3})"
    r"(?:v(?P<version>[1-9]\d*))?$",
    re.IGNORECASE,
)


class ArxivIngestError(RuntimeError):
    """Base error for arXiv retrieval, parsing, and immutable writes."""


class ArxivIdentifierError(ValueError):
    """Raised when an arXiv identifier is invalid or insufficiently pinned."""


class ArxivResponseError(ArxivIngestError):
    """Raised when an arXiv response is unsafe, malformed, or unexpected."""


@dataclass(frozen=True)
class ArxivIdentifier:
    """Validated modern or legacy arXiv identifier."""

    base_id: str
    version: Optional[int]
    scheme: str

    @property
    def canonical_id(self) -> str:
        """Return the base identifier with its optional explicit version."""

        suffix = f"v{self.version}" if self.version is not None else ""
        return f"{self.base_id}{suffix}"


@dataclass(frozen=True)
class ArxivMetadata:
    """Stable metadata fields parsed from one arXiv Atom entry."""

    arxiv_id: str
    title: str
    summary: str
    authors: Tuple[str, ...]
    published: str
    updated: str
    categories: Tuple[str, ...]
    primary_category: Optional[str] = None
    comment: Optional[str] = None
    journal_ref: Optional[str] = None
    doi: Optional[str] = None
    license_url: Optional[str] = None


@dataclass(frozen=True)
class PdfArtifact:
    """Verified local copy of one explicitly versioned arXiv PDF."""

    arxiv_id: str
    path: Path
    size_bytes: int
    sha256: str
    source_url: str
    reused_existing: bool = False


def parse_arxiv_id(value: str, *, require_version: bool = False) -> ArxivIdentifier:
    """Validate and canonicalize a modern or legacy arXiv identifier.

    Accepted examples are ``2301.01234v2`` and ``hep-th/9901001v3``.  An
    optional ``arXiv:`` prefix is accepted; URLs are intentionally rejected so
    callers cannot accidentally bypass the fixed official endpoints.
    """

    if not isinstance(value, str):
        raise ArxivIdentifierError("arXiv identifier must be a string")
    candidate = value.strip()
    if candidate.lower().startswith("arxiv:"):
        candidate = candidate[6:].strip()

    match = _MODERN_ID_RE.fullmatch(candidate)
    scheme = "modern"
    if match is None:
        match = _LEGACY_ID_RE.fullmatch(candidate)
        scheme = "legacy"
    if match is None:
        raise ArxivIdentifierError(f"invalid arXiv identifier: {value!r}")

    year = int(match.group("year"))
    month = int(match.group("month"))
    if not 1 <= month <= 12:
        raise ArxivIdentifierError(f"invalid arXiv year-month in {value!r}")
    if scheme == "modern" and (year < 7 or (year == 7 and month < 4)):
        raise ArxivIdentifierError("modern arXiv identifiers start at 0704")
    # Legacy YY spans 1991-1999 and 2000-0703; values 08-90 cannot be
    # interpreted as dates from the legacy identifier era.
    if scheme == "legacy" and (8 <= year <= 90 or (year == 7 and month > 3)):
        raise ArxivIdentifierError("legacy arXiv identifiers end at 0703")

    version_text = match.group("version")
    version = int(version_text) if version_text is not None else None
    if require_version and version is None:
        raise ArxivIdentifierError(
            "an explicit arXiv version (for example v1) is required for PDF ingestion"
        )

    version_suffix = f"v{version_text}" if version_text is not None else ""
    base_id = candidate[: -len(version_suffix)] if version_suffix else candidate
    return ArxivIdentifier(base_id=base_id, version=version, scheme=scheme)


@dataclass
class ArxivClient:
    """HTTPS-only client for arXiv Atom metadata and pinned PDF retrieval."""

    user_agent: str = "rf-cem-literature-semantics/1.0 (human-reviewed research ingestion)"
    timeout_s: float = 30.0
    max_pdf_bytes: int = 64 * 1024 * 1024
    max_metadata_bytes: int = 4 * 1024 * 1024
    opener: Callable[..., Any] = field(default=urlopen, repr=False, compare=False)

    API_URL = "https://export.arxiv.org/api/query"
    PDF_ROOT = "https://arxiv.org/pdf"
    ABS_ROOT = "https://arxiv.org/abs"

    def __post_init__(self) -> None:
        if not self.user_agent.strip():
            raise ValueError("user_agent must not be empty")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if self.max_pdf_bytes <= 0 or self.max_metadata_bytes <= 0:
            raise ValueError("response byte limits must be positive")

    def search(
        self,
        search_query: str,
        *,
        start: int = 0,
        max_results: int = 10,
    ) -> Tuple[ArxivMetadata, ...]:
        """Return Atom metadata for an arXiv API query.

        ``search_query`` uses arXiv's query syntax (for example
        ``all:"accelerating cavity"``).  Results remain discovery candidates;
        this method never assigns a quality or "classic paper" label.
        """

        if not isinstance(search_query, str) or not search_query.strip():
            raise ValueError("search_query must not be empty")
        if start < 0:
            raise ValueError("start must be non-negative")
        if not 1 <= max_results <= 100:
            raise ValueError("max_results must be between 1 and 100")

        query = urlencode(
            {
                "search_query": search_query.strip(),
                "start": start,
                "max_results": max_results,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
        )
        payload = self._request_bytes(
            f"{self.API_URL}?{query}",
            accept="application/atom+xml",
            max_bytes=self.max_metadata_bytes,
        )
        return _parse_atom_feed(payload)

    def fetch_metadata(self, arxiv_id: str) -> ArxivMetadata:
        """Fetch the exact Atom entry requested by modern or legacy ID."""

        requested = parse_arxiv_id(arxiv_id)
        query = urlencode({"id_list": requested.canonical_id, "max_results": 1})
        payload = self._request_bytes(
            f"{self.API_URL}?{query}",
            accept="application/atom+xml",
            max_bytes=self.max_metadata_bytes,
        )
        entries = _parse_atom_feed(payload)
        for entry in entries:
            parsed_entry = parse_arxiv_id(entry.arxiv_id)
            if parsed_entry.base_id != requested.base_id:
                continue
            if requested.version is None or parsed_entry.version == requested.version:
                return entry
        raise ArxivResponseError(
            f"Atom response did not contain requested identifier {requested.canonical_id!r}"
        )

    def download_pdf(self, arxiv_id: str, destination: Path) -> PdfArtifact:
        """Download and immutably store an explicitly versioned arXiv PDF."""

        parsed = parse_arxiv_id(arxiv_id, require_version=True)
        encoded_id = quote(parsed.canonical_id, safe="/.-")
        source_url = f"{self.PDF_ROOT}/{encoded_id}"
        payload = self._request_bytes(
            source_url,
            accept="application/pdf",
            max_bytes=self.max_pdf_bytes,
        )
        if not payload.startswith(b"%PDF-"):
            raise ArxivResponseError("arXiv PDF response is missing the %PDF- header")

        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(payload).hexdigest()
        created = _write_immutable_atomic(target, payload, digest=digest)
        return PdfArtifact(
            arxiv_id=parsed.canonical_id,
            path=target,
            size_bytes=len(payload),
            sha256=digest,
            source_url=source_url,
            reused_existing=not created,
        )

    def _request_bytes(self, url: str, *, accept: str, max_bytes: int) -> bytes:
        if urlsplit(url).scheme.lower() != "https":
            raise ArxivResponseError(f"refusing non-HTTPS request URL: {url!r}")
        request = Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept": accept},
            method="GET",
        )
        try:
            with self.opener(request, timeout=self.timeout_s) as response:
                status = getattr(response, "status", None)
                if status is None and hasattr(response, "getcode"):
                    status = response.getcode()
                if status is not None and not 200 <= int(status) < 300:
                    raise ArxivResponseError(f"arXiv returned HTTP status {status}")

                final_url = response.geturl() if hasattr(response, "geturl") else url
                if urlsplit(final_url).scheme.lower() != "https":
                    raise ArxivResponseError(
                        f"refusing response redirected to non-HTTPS URL: {final_url!r}"
                    )

                content_length = _content_length(getattr(response, "headers", None))
                if content_length is not None and content_length > max_bytes:
                    raise ArxivResponseError(
                        f"arXiv response exceeds byte limit ({content_length} > {max_bytes})"
                    )
                payload = response.read(max_bytes + 1)
        except ArxivIngestError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ArxivResponseError(f"arXiv request failed: {exc}") from exc

        if len(payload) > max_bytes:
            raise ArxivResponseError(
                f"arXiv response exceeds byte limit ({len(payload)} > {max_bytes})"
            )
        return payload


def build_source_manifest(
    metadata: ArxivMetadata,
    pdf: PdfArtifact,
    *,
    pdf_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a deterministic, JSON-serializable manifest for one pinned source."""

    metadata_id = parse_arxiv_id(metadata.arxiv_id, require_version=True)
    pdf_id = parse_arxiv_id(pdf.arxiv_id, require_version=True)
    if metadata_id.canonical_id != pdf_id.canonical_id:
        raise ValueError("metadata and PDF arXiv identifiers do not match")

    relative_pdf_path = _relative_manifest_path(pdf_path or pdf.path.name)
    encoded_id = quote(metadata_id.canonical_id, safe="/.-")
    return {
        "schema_version": "rf_cem.arxiv_source_manifest.v1",
        "source": {
            "provider": "arXiv",
            "arxiv_id": metadata_id.canonical_id,
            "base_id": metadata_id.base_id,
            "version": metadata_id.version,
            "abs_url": f"{ArxivClient.ABS_ROOT}/{encoded_id}",
            "pdf_url": f"{ArxivClient.PDF_ROOT}/{encoded_id}",
        },
        "metadata": {
            "title": metadata.title,
            "summary": metadata.summary,
            "authors": list(metadata.authors),
            "published": metadata.published,
            "updated": metadata.updated,
            "categories": list(metadata.categories),
            "primary_category": metadata.primary_category,
            "comment": metadata.comment,
            "journal_ref": metadata.journal_ref,
            "doi": metadata.doi,
            "license_url": metadata.license_url,
        },
        "pdf": {
            "path": relative_pdf_path,
            "size_bytes": pdf.size_bytes,
            "sha256": pdf.sha256,
        },
    }


def write_source_manifest(destination: Path, manifest: Mapping[str, Any]) -> Path:
    """Write deterministic UTF-8 JSON without replacing different content."""

    payload = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_immutable_atomic(target, payload, digest=hashlib.sha256(payload).hexdigest())
    return target


def _parse_atom_feed(payload: bytes) -> Tuple[ArxivMetadata, ...]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ArxivResponseError(f"invalid arXiv Atom XML: {exc}") from exc

    entries = []
    for element in root.findall(f"{ATOM}entry"):
        arxiv_id = _id_from_atom_entry(element)
        authors = tuple(
            _required_text(author, f"{ATOM}name", "entry/author/name")
            for author in element.findall(f"{ATOM}author")
        )
        categories = tuple(
            sorted(
                {
                    category.attrib["term"].strip()
                    for category in element.findall(f"{ATOM}category")
                    if category.attrib.get("term", "").strip()
                }
            )
        )
        primary = element.find(f"{ARXIV}primary_category")
        entries.append(
            ArxivMetadata(
                arxiv_id=arxiv_id,
                title=_required_normalized_text(element, f"{ATOM}title", "entry/title"),
                summary=_required_normalized_text(
                    element, f"{ATOM}summary", "entry/summary"
                ),
                authors=authors,
                published=_required_text(element, f"{ATOM}published", "entry/published"),
                updated=_required_text(element, f"{ATOM}updated", "entry/updated"),
                categories=categories,
                primary_category=(
                    primary.attrib.get("term", "").strip() or None
                    if primary is not None
                    else None
                ),
                comment=_optional_normalized_text(element, f"{ARXIV}comment"),
                journal_ref=_optional_normalized_text(element, f"{ARXIV}journal_ref"),
                doi=_optional_normalized_text(element, f"{ARXIV}doi"),
                license_url=_optional_text(element, f"{ARXIV}license"),
            )
        )
    return tuple(entries)


def _id_from_atom_entry(element: ET.Element) -> str:
    raw_id = _required_text(element, f"{ATOM}id", "entry/id")
    entry_id = parse_arxiv_id(_id_from_arxiv_url(raw_id))
    if entry_id.version is not None:
        return entry_id.canonical_id
    for link in element.findall(f"{ATOM}link"):
        href = link.attrib.get("href", "").strip()
        if not href:
            continue
        try:
            linked_id = parse_arxiv_id(_id_from_arxiv_url(href))
        except ArxivResponseError:
            continue
        if linked_id.base_id == entry_id.base_id and linked_id.version is not None:
            return linked_id.canonical_id
    return entry_id.canonical_id


def _id_from_arxiv_url(value: str) -> str:
    parsed_url = urlsplit(value)
    identifier = None
    for marker in ("/abs/", "/pdf/"):
        if marker in parsed_url.path:
            identifier = unquote(parsed_url.path.split(marker, 1)[1]).strip("/")
            break
    if identifier is None:
        raise ArxivResponseError(f"unexpected arXiv Atom entry id: {value!r}")
    if identifier.lower().endswith(".pdf"):
        identifier = identifier[:-4]
    try:
        return parse_arxiv_id(identifier).canonical_id
    except ArxivIdentifierError as exc:
        raise ArxivResponseError(f"unexpected arXiv Atom entry id: {value!r}") from exc


def _required_text(element: ET.Element, path: str, label: str) -> str:
    value = _optional_text(element, path)
    if value is None:
        raise ArxivResponseError(f"missing required Atom field {label}")
    return value


def _required_normalized_text(element: ET.Element, path: str, label: str) -> str:
    return _normalize_whitespace(_required_text(element, path, label))


def _optional_text(element: ET.Element, path: str) -> Optional[str]:
    child = element.find(path)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _optional_normalized_text(element: ET.Element, path: str) -> Optional[str]:
    value = _optional_text(element, path)
    return _normalize_whitespace(value) if value is not None else None


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _content_length(headers: Any) -> Optional[int]:
    if headers is None or not hasattr(headers, "get"):
        return None
    value = headers.get("Content-Length")
    if value is None:
        return None
    try:
        length = int(value)
    except (TypeError, ValueError):
        return None
    return length if length >= 0 else None


def _relative_manifest_path(value: str) -> str:
    raw = str(value).replace("\\", "/")
    posix_path = PurePosixPath(raw)
    windows_path = PureWindowsPath(raw)
    if (
        not raw
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in posix_path.parts
    ):
        raise ValueError("manifest PDF path must be a safe relative path")
    return posix_path.as_posix()


def _write_immutable_atomic(target: Path, payload: bytes, *, digest: str) -> bool:
    """Atomically publish complete bytes, never clobbering different content."""

    if os.path.lexists(str(target)):
        _require_matching_file(target, payload_size=len(payload), digest=digest)
        return False

    temporary_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())

        try:
            # A hard-link publishes the already-complete temp file atomically and
            # fails instead of replacing a destination created by another process.
            os.link(temporary_name, target)
        except FileExistsError:
            _require_matching_file(target, payload_size=len(payload), digest=digest)
            return False
        except OSError as exc:
            raise ArxivIngestError(
                "filesystem does not support safe atomic no-clobber publication"
            ) from exc
        return True
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _require_matching_file(target: Path, *, payload_size: int, digest: str) -> None:
    if target.is_symlink() or not target.is_file():
        raise FileExistsError(f"refusing to replace existing path: {target}")
    if target.stat().st_size != payload_size or _sha256_file(target) != digest:
        raise FileExistsError(f"refusing to overwrite different content: {target}")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


__all__: Sequence[str] = (
    "ArxivClient",
    "ArxivIdentifier",
    "ArxivIdentifierError",
    "ArxivIngestError",
    "ArxivMetadata",
    "ArxivResponseError",
    "PdfArtifact",
    "build_source_manifest",
    "parse_arxiv_id",
    "write_source_manifest",
)
