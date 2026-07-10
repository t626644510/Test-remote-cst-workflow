"""Scan CST Online Help for automation and scripting pages.

This script is intentionally read-only. It searches local CST help files for
automation-related terms and prints page-level matches so a new CST release can
be audited without manually browsing thousands of HTML files.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_HELP_ROOT = Path(r"D:\CST2026\CST Studio Suite 2026\Online Help")

TEXT_EXTENSIONS = {
    ".htm",
    ".html",
    ".js",
    ".xml",
    ".txt",
    ".py",
    ".json",
}

SKIP_PARTS = {
    "mathjax",
    "_static",
    "icon_images",
    "image",
    "resource",
}

KEYWORD_GROUPS = {
    "automation_scripting": [
        "Automation and Scripting",
        "scripting",
        "automation",
        "user scripts",
    ],
    "vba_macro": [
        "VBA",
        "Visual Basic",
        "macro",
        "macros",
        "RunMacro",
        "RunScript",
        "AddToHistory",
        "OLE automation",
        "CSTStudio.Application",
    ],
    "python": [
        "Python",
        "cst.interface",
        "DesignEnvironment",
        "execute_vba_code",
        "get_current_project",
        "Python/scripts",
        "Macros/Python",
    ],
    "command_line": [
        "Command Line Options",
        "batch mode",
        ".bas",
        "Model.run",
        "-hide",
        "-b",
        "-as",
    ],
    "com_ole": [
        "COM",
        "OLE",
        "CreateObject",
        "CSTStudio.Application",
    ],
}


def term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if re.fullmatch(r"[A-Za-z0-9_]+", term):
        return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.I)
    if re.fullmatch(r"-[A-Za-z0-9_]+", term):
        return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.I)
    if re.fullmatch(r"\.[A-Za-z0-9_]+", term):
        return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.I)
    return re.compile(escaped, re.I)


def iter_help_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        lower_parts = {part.lower() for part in path.parts}
        if lower_parts & SKIP_PARTS:
            continue
        yield path


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def strip_html(text: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text, flags=re.I)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&amp;", "&", text)
    return re.sub(r"\s+", " ", text).strip()


def title_for(text: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.I | re.S)
    if not match:
        match = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.I | re.S)
    if not match:
        return fallback
    return strip_html(match.group(1)) or fallback


def snippets(clean_text: str, terms: list[str], limit: int) -> list[str]:
    found: list[str] = []
    for term in terms:
        pattern = term_pattern(term)
        match = pattern.search(clean_text)
        if not match:
            continue
        start = max(0, match.start() - 120)
        end = min(len(clean_text), match.end() + 180)
        snippet = clean_text[start:end].strip()
        if snippet not in found:
            found.append(snippet)
        if len(found) >= limit:
            break
    return found


def scan(root: Path, snippet_limit: int) -> dict[str, object]:
    results: dict[str, list[dict[str, object]]] = {
        group: [] for group in KEYWORD_GROUPS
    }
    total_files = 0

    for path in iter_help_files(root):
        total_files += 1
        raw = read_text(path)
        clean = strip_html(raw)
        for group, terms in KEYWORD_GROUPS.items():
            matched_terms = [
                term for term in terms if term_pattern(term).search(clean)
            ]
            if not matched_terms:
                continue
            results[group].append(
                {
                    "path": str(path),
                    "title": title_for(raw, path.name),
                    "terms": matched_terms,
                    "snippets": snippets(clean, matched_terms, snippet_limit),
                }
            )

    return {
        "root": str(root),
        "scanned_text_files": total_files,
        "groups": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("help_root", nargs="?", type=Path, default=DEFAULT_HELP_ROOT)
    parser.add_argument("--snippet-limit", type=int, default=2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = scan(args.help_root, args.snippet_limit)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print(f"Root: {report['root']}")
    print(f"Scanned text files: {report['scanned_text_files']}")
    for group, matches in report["groups"].items():
        print(f"\n[{group}] {len(matches)} page matches")
        for item in matches[:40]:
            terms = ", ".join(item["terms"])
            print(f"- {item['title']} :: {item['path']} :: {terms}")
        if len(matches) > 40:
            print(f"  ... {len(matches) - 40} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
