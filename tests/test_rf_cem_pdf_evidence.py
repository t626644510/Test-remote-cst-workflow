import json
from pathlib import Path
import subprocess

import pytest

from rf_cem.literature_semantics import pdf_evidence
from rf_cem.literature_semantics import cli
from rf_cem.literature_semantics.pdf_evidence import PdfEvidenceError, render_pdf_pages


pytestmark = pytest.mark.no_cst


class _Completed:
    returncode = 0
    stdout = ""


def test_render_selected_pages_is_deterministic(tmp_path, monkeypatch):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.4\nfixture")
    executable = tmp_path / "pdftoppm.exe"
    executable.write_bytes(b"fixture")

    def fake_run(command, **kwargs):
        Path(command[-1]).with_suffix(".png").write_bytes(b"PNG")
        return _Completed()

    monkeypatch.setattr(pdf_evidence.subprocess, "run", fake_run)
    artifacts = render_pdf_pages(source, [3, 1, 3], tmp_path / "images", pdftoppm=executable)

    assert [item["page"] for item in artifacts] == [1, 3]
    assert [Path(item["path"]).name for item in artifacts] == ["page_0001.png", "page_0003.png"]


@pytest.mark.parametrize("pages", [[], [0], [-1], list(range(1, 22))])
def test_render_rejects_invalid_page_selection(tmp_path, pages):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.4\nfixture")
    executable = tmp_path / "pdftoppm.exe"
    executable.write_bytes(b"fixture")

    with pytest.raises(PdfEvidenceError):
        render_pdf_pages(source, pages, tmp_path / "images", pdftoppm=executable)


def test_render_rejects_non_pdf(tmp_path):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"not a pdf")

    with pytest.raises(PdfEvidenceError, match="not a PDF"):
        render_pdf_pages(source, [1], tmp_path / "images")


def test_render_wraps_poppler_timeout(tmp_path, monkeypatch):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.4\nfixture")
    executable = tmp_path / "pdftoppm.exe"
    executable.write_bytes(b"fixture")

    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(pdf_evidence.subprocess, "run", fake_run)
    with pytest.raises(PdfEvidenceError, match="timed out"):
        render_pdf_pages(source, [1], tmp_path / "images", pdftoppm=executable)


def test_render_cli_writes_portable_manifest(tmp_path, monkeypatch):
    output_dir = tmp_path / "images"
    rendered = output_dir / "page_0004.png"

    def fake_render(*args, **kwargs):
        output_dir.mkdir()
        rendered.write_bytes(b"PNG")
        return [{"page": 4, "path": rendered, "size_bytes": 3, "dpi": 150}]

    monkeypatch.setattr(cli, "render_pdf_pages", fake_render)
    exit_code = cli.main(
        [
            "render-evidence",
            "--pdf",
            str(tmp_path / "paper.pdf"),
            "--pages",
            "4",
            "--out-dir",
            str(output_dir),
        ]
    )

    manifest = json.loads((output_dir / "render_manifest.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert manifest == [
        {"dpi": 150, "page": 4, "path": "page_0004.png", "size_bytes": 3}
    ]
