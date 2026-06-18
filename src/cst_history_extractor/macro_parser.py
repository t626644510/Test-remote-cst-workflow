"""Parse exported CST history macro text into ordered history items.

The parser is intentionally conservative.  It does not execute VBA and does not
try to prove that a command is valid CST syntax.  It only extracts reviewable
history-like blocks from text exported or copied from CST.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Optional


_ADD_TO_HISTORY_RE = re.compile(
    r"\bAddToHistory\s+\"(?P<name>(?:[^\"]|\"\")*)\"\s*,?",
    re.IGNORECASE,
)
_PY_ADD_TO_HISTORY_RE = re.compile(
    r"\.add_to_history\(\s*[rubfRUBF]*\"(?P<name>(?:[^\"]|\\\")*)\"",
    re.IGNORECASE,
)
_COMMENT_BLOCK_RE = re.compile(
    r"^\s*'\s*(?:[-=]+\s*)?(?:history\s*(?:item|block)|name)\s*[:=-]\s*(?P<name>.+?)\s*(?:[-=]+\s*)?$",
    re.IGNORECASE,
)
_WITH_RE = re.compile(r"^\s*With\s+(?P<object>[A-Za-z_][A-Za-z0-9_]*)\b", re.IGNORECASE)
_END_WITH_RE = re.compile(r"^\s*End\s+With\b", re.IGNORECASE)


@dataclass(frozen=True)
class HistoryItem:
    """One parsed history item or fallback macro block."""

    index: int
    raw_name: str
    macro_body: str
    source_line_start: int
    source_line_end: int
    parser_strategy: str
    raw_macro_excerpt: str

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        return {
            "index": self.index,
            "raw_name": self.raw_name,
            "macro_body": self.macro_body,
            "source_line_start": self.source_line_start,
            "source_line_end": self.source_line_end,
            "parser_strategy": self.parser_strategy,
            "raw_macro_excerpt": self.raw_macro_excerpt,
        }


def parse_history_text(text: str, source_name: str = "") -> List[HistoryItem]:
    """Parse CST history or macro text into ordered :class:`HistoryItem` objects.

    The strategy order matches the extractor v0 design:

    1. explicit ``AddToHistory "name", ...`` blocks,
    2. comment-delimited exported history blocks,
    3. top-level ``With ... End With`` blocks,
    4. one whole-file fallback block.
    """
    normalized = _normalize_newlines(text)
    if not normalized.strip():
        return []

    lines = normalized.splitlines()

    items = _parse_add_to_history_blocks(lines)
    if items:
        return _renumber(items)

    items = _parse_comment_delimited_blocks(lines)
    if items:
        return _renumber(items)

    items = _parse_with_blocks(lines)
    if items:
        return _renumber(items)

    name = source_name or "whole_macro"
    return [
        HistoryItem(
            index=1,
            raw_name=name,
            macro_body=normalized.strip(),
            source_line_start=1,
            source_line_end=len(lines),
            parser_strategy="whole_file_fallback",
            raw_macro_excerpt=_excerpt(normalized),
        )
    ]


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _renumber(items: Iterable[HistoryItem]) -> List[HistoryItem]:
    return [
        HistoryItem(
            index=i,
            raw_name=item.raw_name,
            macro_body=item.macro_body,
            source_line_start=item.source_line_start,
            source_line_end=item.source_line_end,
            parser_strategy=item.parser_strategy,
            raw_macro_excerpt=item.raw_macro_excerpt,
        )
        for i, item in enumerate(items, start=1)
    ]


def _parse_add_to_history_blocks(lines: List[str]) -> List[HistoryItem]:
    items: List[HistoryItem] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = _ADD_TO_HISTORY_RE.search(line)
        py_match = _PY_ADD_TO_HISTORY_RE.search(line)
        if not match and not py_match:
            i += 1
            continue

        name = _undouble_quotes((match or py_match).group("name"))
        start = i
        block_lines = [line]
        j = i + 1
        while j < len(lines) and _continues_vba_statement(block_lines[-1]):
            block_lines.append(lines[j])
            j += 1

        block_text = "\n".join(block_lines)
        body = _extract_add_to_history_body(block_text)
        if not body.strip():
            body = block_text.strip()

        items.append(
            HistoryItem(
                index=len(items) + 1,
                raw_name=name,
                macro_body=body.strip(),
                source_line_start=start + 1,
                source_line_end=start + len(block_lines),
                parser_strategy="add_to_history",
                raw_macro_excerpt=_excerpt(block_text),
            )
        )
        i = max(j, i + 1)
    return items


def _continues_vba_statement(line: str) -> bool:
    stripped = line.rstrip()
    return stripped.endswith("_")


def _extract_add_to_history_body(block_text: str) -> str:
    comma_index = block_text.find(",")
    if comma_index == -1:
        return ""
    argument_text = block_text[comma_index + 1 :]
    fragments = _parse_vba_string_literals(argument_text)
    if not fragments:
        return ""
    return "\n".join(fragment for fragment in fragments if fragment)


def _parse_vba_string_literals(text: str) -> List[str]:
    fragments: List[str] = []
    i = 0
    while i < len(text):
        if text[i] != '"':
            i += 1
            continue

        i += 1
        chars: List[str] = []
        while i < len(text):
            char = text[i]
            if char == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    chars.append('"')
                    i += 2
                    continue
                i += 1
                break
            chars.append(char)
            i += 1
        fragments.append("".join(chars))
    return fragments


def _parse_comment_delimited_blocks(lines: List[str]) -> List[HistoryItem]:
    delimiters = []
    for i, line in enumerate(lines):
        match = _COMMENT_BLOCK_RE.match(line)
        if match:
            name = match.group("name").strip(" -")
            delimiters.append((i, name or "history_item"))

    if not delimiters:
        return []

    items: List[HistoryItem] = []
    for pos, (start, name) in enumerate(delimiters):
        body_start = start + 1
        body_end_exclusive = delimiters[pos + 1][0] if pos + 1 < len(delimiters) else len(lines)
        body_lines = lines[body_start:body_end_exclusive]
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        block_text = "\n".join(lines[start:body_end_exclusive])
        items.append(
            HistoryItem(
                index=len(items) + 1,
                raw_name=name,
                macro_body=body,
                source_line_start=start + 1,
                source_line_end=body_end_exclusive,
                parser_strategy="comment_delimited",
                raw_macro_excerpt=_excerpt(block_text),
            )
        )
    return items


def _parse_with_blocks(lines: List[str]) -> List[HistoryItem]:
    items: List[HistoryItem] = []
    i = 0
    while i < len(lines):
        start_match = _WITH_RE.match(lines[i])
        if not start_match:
            i += 1
            continue

        start = i
        depth = 0
        j = i
        while j < len(lines):
            if _WITH_RE.match(lines[j]):
                depth += 1
            if _END_WITH_RE.match(lines[j]):
                depth -= 1
                if depth <= 0:
                    break
            j += 1

        end = min(j, len(lines) - 1)
        block_lines = lines[start : end + 1]
        block_text = "\n".join(block_lines).strip()
        object_name = start_match.group("object")
        items.append(
            HistoryItem(
                index=len(items) + 1,
                raw_name=f"With {object_name}",
                macro_body=block_text,
                source_line_start=start + 1,
                source_line_end=end + 1,
                parser_strategy="with_block",
                raw_macro_excerpt=_excerpt(block_text),
            )
        )
        i = end + 1
    return items


def _undouble_quotes(value: Optional[str]) -> str:
    return (value or "").replace('""', '"')


def _excerpt(text: str, max_chars: int = 500) -> str:
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 3].rstrip() + "..."
