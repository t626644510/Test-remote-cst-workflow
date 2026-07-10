import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rf_cem.literature_semantics.arxiv_ingest import (
    ArxivClient,
    ArxivIdentifierError,
    ArxivResponseError,
    PdfArtifact,
    build_source_manifest,
    parse_arxiv_id,
    write_source_manifest,
)
from rf_cem.literature_semantics import cli


pytestmark = pytest.mark.no_cst


ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2301.01234</id>
    <updated>2023-01-05T00:00:00Z</updated>
    <published>2023-01-03T00:00:00Z</published>
    <title>  RF cavity\n design  </title>
    <summary>A reproducible   cavity study.</summary>
    <author><name>First Author</name></author>
    <author><name>Second Author</name></author>
    <category term="physics.acc-ph"/>
    <category term="physics.class-ph"/>
    <arxiv:primary_category term="physics.acc-ph"/>
    <link href="http://arxiv.org/abs/2301.01234v2" rel="alternate" type="text/html"/>
    <link href="http://arxiv.org/pdf/2301.01234v2" rel="related" type="application/pdf" title="pdf"/>
    <arxiv:comment> 12 pages, 4 figures </arxiv:comment>
    <arxiv:journal_ref>Example Journal 1 (2023)</arxiv:journal_ref>
    <arxiv:doi>10.0000/example</arxiv:doi>
    <arxiv:license>https://arxiv.org/licenses/nonexclusive-distrib/1.0/</arxiv:license>
  </entry>
</feed>
"""


class FakeResponse:
    def __init__(self, payload, url, *, status=200, headers=None):
        self._payload = payload
        self._url = url
        self.status = status
        self.headers = headers or {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit=-1):
        return self._payload if limit < 0 else self._payload[:limit]

    def geturl(self):
        return self._url


class FakeOpener:
    def __init__(self, payload, *, final_url=None, status=200, headers=None):
        self.payload = payload
        self.final_url = final_url
        self.status = status
        self.headers = headers
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append((request, timeout))
        return FakeResponse(
            self.payload,
            self.final_url or request.full_url,
            status=self.status,
            headers=self.headers,
        )


@pytest.mark.parametrize(
    ("raw", "canonical", "scheme", "version"),
    [
        ("2301.01234v2", "2301.01234v2", "modern", 2),
        (" arXiv:0704.0001v1 ", "0704.0001v1", "modern", 1),
        ("hep-th/9901001v3", "hep-th/9901001v3", "legacy", 3),
        ("math.GT/0309136", "math.GT/0309136", "legacy", None),
    ],
)
def test_parse_arxiv_id_accepts_modern_and_legacy(raw, canonical, scheme, version):
    parsed = parse_arxiv_id(raw)

    assert parsed.canonical_id == canonical
    assert parsed.scheme == scheme
    assert parsed.version == version


@pytest.mark.parametrize(
    "raw",
    [
        "https://arxiv.org/abs/2301.01234v1",
        "2300.01234v1",
        "0703.0001v1",
        "hep-th/0713001v1",
        "2301.01234v0",
        "not-an-id",
    ],
)
def test_parse_arxiv_id_rejects_invalid_forms(raw):
    with pytest.raises(ArxivIdentifierError):
        parse_arxiv_id(raw)


def test_pinned_ingestion_requires_explicit_version():
    with pytest.raises(ArxivIdentifierError, match="explicit arXiv version"):
        parse_arxiv_id("2301.01234", require_version=True)


def test_search_uses_https_user_agent_timeout_and_parses_atom_metadata():
    opener = FakeOpener(ATOM_FEED)
    client = ArxivClient(user_agent="rf-cem-test/1.0", timeout_s=7.5, opener=opener)

    results = client.search('all:"RF cavity"', start=2, max_results=3)

    assert len(results) == 1
    metadata = results[0]
    assert metadata.arxiv_id == "2301.01234v2"
    assert metadata.title == "RF cavity design"
    assert metadata.summary == "A reproducible cavity study."
    assert metadata.authors == ("First Author", "Second Author")
    assert metadata.categories == ("physics.acc-ph", "physics.class-ph")
    assert metadata.primary_category == "physics.acc-ph"
    request, timeout = opener.calls[0]
    assert urlsplit(request.full_url).scheme == "https"
    assert request.get_header("User-agent") == "rf-cem-test/1.0"
    assert request.get_header("Accept") == "application/atom+xml"
    assert timeout == 7.5
    query = parse_qs(urlsplit(request.full_url).query)
    assert query["search_query"] == ['all:"RF cavity"']
    assert query["start"] == ["2"]
    assert query["max_results"] == ["3"]


def test_fetch_metadata_requires_exact_requested_version():
    client = ArxivClient(opener=FakeOpener(ATOM_FEED))

    metadata = client.fetch_metadata("2301.01234v2")

    assert metadata.arxiv_id == "2301.01234v2"
    with pytest.raises(ArxivResponseError, match="did not contain requested"):
        client.fetch_metadata("2301.01234v1")


def test_download_pdf_is_pinned_verified_hashed_and_idempotent(tmp_path):
    payload = b"%PDF-1.7\nmock pinned paper\n%%EOF\n"
    opener = FakeOpener(payload)
    target = tmp_path / "paper.pdf"
    client = ArxivClient(opener=opener)

    artifact = client.download_pdf("2301.01234v2", target)
    reused = client.download_pdf("2301.01234v2", target)

    assert target.read_bytes() == payload
    assert artifact.sha256 == hashlib.sha256(payload).hexdigest()
    assert artifact.size_bytes == len(payload)
    assert artifact.reused_existing is False
    assert reused.reused_existing is True
    request, _ = opener.calls[0]
    assert request.full_url == "https://arxiv.org/pdf/2301.01234v2"
    assert request.get_header("Accept") == "application/pdf"


def test_download_refuses_to_overwrite_different_existing_content(tmp_path):
    target = tmp_path / "paper.pdf"
    original = b"%PDF-1.4\noriginal\n"
    target.write_bytes(original)
    client = ArxivClient(opener=FakeOpener(b"%PDF-1.7\ndifferent\n"))

    with pytest.raises(FileExistsError, match="different content"):
        client.download_pdf("2301.01234v2", target)

    assert target.read_bytes() == original


@pytest.mark.parametrize(
    ("payload", "kwargs", "message"),
    [
        (b"<html>not a PDF</html>", {}, "%PDF-"),
        (b"%PDF-1.7\n0123456789", {"max_pdf_bytes": 8}, "byte limit"),
    ],
)
def test_download_rejects_non_pdf_and_oversized_payload(tmp_path, payload, kwargs, message):
    client = ArxivClient(opener=FakeOpener(payload), **kwargs)

    with pytest.raises(ArxivResponseError, match=message):
        client.download_pdf("2301.01234v2", tmp_path / "paper.pdf")


def test_download_rejects_oversized_content_length_before_read(tmp_path):
    opener = FakeOpener(
        b"%PDF-1.7\n",
        headers={"Content-Length": "1000"},
    )
    client = ArxivClient(opener=opener, max_pdf_bytes=32)

    with pytest.raises(ArxivResponseError, match="byte limit"):
        client.download_pdf("2301.01234v2", tmp_path / "paper.pdf")


def test_client_rejects_redirect_to_insecure_transport():
    client = ArxivClient(
        opener=FakeOpener(ATOM_FEED, final_url="http://export.arxiv.org/api/query")
    )

    with pytest.raises(ArxivResponseError, match="non-HTTPS"):
        client.search("all:cavity")


def test_source_manifest_is_deterministic_relative_and_immutable(tmp_path):
    metadata = ArxivClient(opener=FakeOpener(ATOM_FEED)).fetch_metadata("2301.01234v2")
    pdf = PdfArtifact(
        arxiv_id="2301.01234v2",
        path=tmp_path / "paper.pdf",
        size_bytes=123,
        sha256="a" * 64,
        source_url="https://arxiv.org/pdf/2301.01234v2",
    )

    first = build_source_manifest(metadata, pdf, pdf_path="papers/2301.01234v2.pdf")
    second = build_source_manifest(metadata, pdf, pdf_path="papers\\2301.01234v2.pdf")
    target = tmp_path / "source_manifest.json"
    write_source_manifest(target, first)
    original_bytes = target.read_bytes()
    write_source_manifest(target, second)

    assert first == second
    assert first["source"]["version"] == 2
    assert first["pdf"]["path"] == "papers/2301.01234v2.pdf"
    assert "downloaded_at" not in json.dumps(first)
    assert "classic" not in json.dumps(first).lower()
    assert target.read_bytes() == original_bytes
    assert json.loads(original_bytes) == first

    changed = dict(first)
    changed["schema_version"] = "changed"
    with pytest.raises(FileExistsError, match="different content"):
        write_source_manifest(target, changed)


def test_source_manifest_rejects_absolute_or_parent_paths(tmp_path):
    metadata = ArxivClient(opener=FakeOpener(ATOM_FEED)).fetch_metadata("2301.01234v2")
    pdf = PdfArtifact(
        arxiv_id="2301.01234v2",
        path=tmp_path / "paper.pdf",
        size_bytes=1,
        sha256="0" * 64,
        source_url="https://arxiv.org/pdf/2301.01234v2",
    )

    with pytest.raises(ValueError, match="safe relative"):
        build_source_manifest(metadata, pdf, pdf_path="../paper.pdf")
    with pytest.raises(ValueError, match="safe relative"):
        build_source_manifest(metadata, pdf, pdf_path="C:\\papers\\paper.pdf")
    with pytest.raises(ValueError, match="safe relative"):
        build_source_manifest(metadata, pdf, pdf_path="C:paper.pdf")


def test_arxiv_fetch_cli_reports_no_clobber_error_without_traceback(tmp_path, monkeypatch, capsys):
    class FailingClient:
        def fetch_metadata(self, arxiv_id):
            return object()

        def download_pdf(self, arxiv_id, destination):
            raise FileExistsError("refusing to overwrite different content")

    monkeypatch.setattr(cli, "ArxivClient", FailingClient)
    exit_code = cli.main(
        [
            "arxiv-fetch",
            "--id",
            "2301.01234v2",
            "--out-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 1
    assert "refusing to overwrite different content" in capsys.readouterr().out
