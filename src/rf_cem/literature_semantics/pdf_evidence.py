"""Render selected PDF pages into auditable image evidence using Poppler."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Sequence


class PdfEvidenceError(RuntimeError):
    """Raised when a PDF evidence page cannot be rendered safely."""


def render_pdf_pages(
    pdf_path: Path,
    pages: Sequence[int],
    output_dir: Path,
    *,
    pdftoppm: str | Path = "pdftoppm",
    dpi: int = 150,
    timeout_s: float = 120.0,
) -> list[dict[str, object]]:
    """Render a bounded set of one-based PDF pages to PNG files.

    The function delegates PDF parsing to Poppler. It never executes embedded
    PDF content and does not infer semantic claims from page pixels.
    """
    source = Path(pdf_path).resolve()
    if not source.is_file():
        raise PdfEvidenceError(f"PDF does not exist: {source}")
    with source.open("rb") as handle:
        header = handle.read(5)
    if header != b"%PDF-":
        raise PdfEvidenceError(f"input is not a PDF: {source}")
    selected = sorted(set(int(page) for page in pages))
    if not selected or any(page <= 0 for page in selected):
        raise PdfEvidenceError("pages must contain positive one-based page numbers")
    if len(selected) > 20:
        raise PdfEvidenceError("at most 20 evidence pages may be rendered per call")
    if not 72 <= int(dpi) <= 300:
        raise PdfEvidenceError("dpi must be between 72 and 300")
    if timeout_s <= 0:
        raise PdfEvidenceError("timeout_s must be positive")

    executable = _resolve_executable(pdftoppm)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, object]] = []
    for page in selected:
        prefix = destination / f"page_{page:04d}"
        command = [
            executable,
            "-f",
            str(page),
            "-l",
            str(page),
            "-singlefile",
            "-r",
            str(int(dpi)),
            "-png",
            str(source),
            str(prefix),
        ]
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfEvidenceError(
                f"pdftoppm timed out after {timeout_s:g} s for page {page}"
            ) from exc
        except OSError as exc:
            raise PdfEvidenceError(f"pdftoppm could not run for page {page}: {exc}") from exc
        output = prefix.with_suffix(".png")
        if completed.returncode != 0 or not output.is_file():
            diagnostic = (completed.stdout or "")[-2000:]
            raise PdfEvidenceError(
                f"pdftoppm failed for page {page} with code {completed.returncode}: {diagnostic}"
            )
        artifacts.append(
            {
                "page": page,
                "path": output,
                "size_bytes": output.stat().st_size,
                "dpi": int(dpi),
            }
        )
    return artifacts


def _resolve_executable(value: str | Path) -> str:
    candidate = Path(value)
    if candidate.is_file():
        return str(candidate.resolve())
    resolved = shutil.which(str(value))
    if resolved:
        return resolved
    raise PdfEvidenceError(
        "pdftoppm was not found; install Poppler or pass an explicit --pdftoppm path"
    )
