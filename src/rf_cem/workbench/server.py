"""Authenticated loopback-only, read-only HTTP Workbench for W0."""

from __future__ import annotations

from html import escape
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from .registry import RegistryReader, canonical_json


LOOPBACK_HOST = "127.0.0.1"

_PAGES = {
    "/": ("overview", "Overview", ()),
    "/families": ("families", "Families", ("family",)),
    "/instances": ("instances", "Instances", ("instance",)),
    "/semantics": ("semantics", "Semantics", ("semantic",)),
    "/representations": (
        "representations",
        "Representations",
        ("representation",),
    ),
    "/algorithms": ("algorithms", "Algorithms", ("algorithm",)),
    "/reviews": ("reviews", "Reviews", ("review",)),
    "/validation": ("validation", "Validation", ("validation",)),
    "/roadmap": (
        "roadmap",
        "Roadmap / Gates",
        ("roadmap_phase", "roadmap_gate"),
    ),
    "/coverage": ("coverage", "Capability Coverage", ("capability",)),
    "/compile-records": (
        "compile-records",
        "Compile Records",
        ("compile_record",),
    ),
}


class _LoopbackHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class WorkbenchServer:
    """Serve one immutable registry through fixed loopback-only routes."""

    def __init__(
        self,
        database: Path,
        *,
        source_root: Path,
        token: str | None = None,
        port: int = 0,
    ) -> None:
        if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65_535:
            raise ValueError("port must be an integer from 0 through 65535")
        selected_token = secrets.token_urlsafe(32) if token is None else token
        if not isinstance(selected_token, str) or len(selected_token) < 16:
            raise ValueError("token must contain at least 16 characters")
        self.database = database.resolve()
        self.source_root = source_root.resolve()
        self.token = selected_token
        RegistryReader(self.database).metadata()
        handler = create_workbench_handler(
            self.database,
            source_root=self.source_root,
            token=self.token,
        )
        self._httpd = _LoopbackHTTPServer((LOOPBACK_HOST, port), handler)
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        """Return the fixed IPv4 loopback bind address."""
        return LOOPBACK_HOST

    @property
    def port(self) -> int:
        """Return the selected TCP port."""
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        """Return the token-free loopback origin."""
        return f"http://{self.host}:{self.port}"

    @property
    def workbench_url(self) -> str:
        """Return the authenticated initial-document URL."""
        return f"{self.base_url}/?{urlencode({'token': self.token})}"

    @property
    def api_headers(self) -> dict[str, str]:
        """Return headers for authenticated JSON reads."""
        return {"X-Workbench-Token": self.token}

    def start(self) -> "WorkbenchServer":
        """Start the server in one daemon thread."""
        if self._thread is not None:
            raise RuntimeError("Workbench server has already been started")
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="rf-cem-workbench",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop and close the local server."""
        if self._thread is None:
            self._httpd.server_close()
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5.0)
        self._thread = None

    def serve_forever(self) -> None:
        """Serve synchronously until interrupted."""
        try:
            self._httpd.serve_forever()
        finally:
            self._httpd.server_close()

    def __enter__(self) -> "WorkbenchServer":
        return self.start()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()


def create_workbench_handler(
    database: Path,
    *,
    source_root: Path,
    token: str,
) -> type[BaseHTTPRequestHandler]:
    """Create one fixed-route handler backed by read-only SQLite connections."""
    if not isinstance(token, str) or len(token) < 16:
        raise ValueError("token must contain at least 16 characters")
    database = database.resolve()
    source_root = source_root.resolve()

    class WorkbenchRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "RFCEMWorkbench/0"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlsplit(self.path)
            if parsed.path in _PAGES:
                if not self._document_request_is_trusted(parsed.query):
                    return
                _, title, kinds = _PAGES[parsed.path]
                reader = RegistryReader(database)
                body = _render_page(
                    reader,
                    source_root=source_root,
                    title=title,
                    entity_kinds=kinds,
                    token=token,
                    overview=parsed.path == "/",
                    show_sources=parsed.path in {"/", "/validation"},
                ).encode("utf-8")
                self._send(200, body, "text/html; charset=utf-8")
                return
            if parsed.path in {"/api/catalog", "/api/source-status"}:
                if not self._api_request_is_trusted():
                    return
                reader = RegistryReader(database)
                payload: object
                if parsed.path == "/api/catalog":
                    payload = {"ok": True, "catalog": reader.snapshot()}
                else:
                    payload = {
                        "ok": True,
                        "sources": reader.audit_sources(source_root),
                    }
                self._send_json(200, payload)
                return
            self._send_json(
                404,
                {"ok": False, "error": {"code": "not_found", "message": "endpoint not found"}},
            )

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._method_not_allowed()

        def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._method_not_allowed()

        def do_PATCH(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._method_not_allowed()

        def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._method_not_allowed()

        def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._method_not_allowed()

        def _method_not_allowed(self) -> None:
            self._send_json(
                405,
                {
                    "ok": False,
                    "error": {
                        "code": "method_not_allowed",
                        "message": "Workbench W0 is read-only and CORS is disabled",
                    },
                },
            )

        def _api_request_is_trusted(self) -> bool:
            if not self._host_is_allowed():
                self._send_forbidden("invalid_host", "request Host is not allowed")
                return False
            if not self._origin_is_allowed():
                self._send_forbidden("invalid_origin", "request Origin is not allowed")
                return False
            supplied = self.headers.get("X-Workbench-Token", "")
            authorization = self.headers.get("Authorization", "")
            if not supplied and authorization.startswith("Bearer "):
                supplied = authorization[7:]
            if not supplied or not hmac.compare_digest(supplied, token):
                self._send_forbidden("forbidden", "valid Workbench token required")
                return False
            return True

        def _document_request_is_trusted(self, query: str) -> bool:
            if not self._host_is_allowed():
                self._send_forbidden("invalid_host", "request Host is not allowed")
                return False
            if not self._origin_is_allowed():
                self._send_forbidden("invalid_origin", "request Origin is not allowed")
                return False
            try:
                fields = parse_qsl(
                    query,
                    keep_blank_values=True,
                    strict_parsing=True,
                    max_num_fields=2,
                )
            except ValueError:
                fields = []
            supplied = fields[0][1] if len(fields) == 1 and fields[0][0] == "token" else ""
            if not supplied or not hmac.compare_digest(supplied, token):
                self._send_forbidden(
                    "forbidden", "valid initial-document token required"
                )
                return False
            return True

        def _host_is_allowed(self) -> bool:
            port = int(self.server.server_address[1])
            supplied = self.headers.get("Host", "").strip().lower()
            return supplied in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def _origin_is_allowed(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            try:
                parsed = urlsplit(origin)
                port = parsed.port
            except ValueError:
                return False
            return (
                parsed.scheme == "http"
                and parsed.hostname in {"127.0.0.1", "localhost"}
                and port == int(self.server.server_address[1])
                and not parsed.username
                and not parsed.password
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment
            )

        def _send_forbidden(self, code: str, message: str) -> None:
            self._send_json(
                403,
                {"ok": False, "error": {"code": code, "message": message}},
            )

        def _send_json(self, status: int, payload: object) -> None:
            self._send(
                status,
                canonical_json(payload).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'none'; frame-ancestors 'none'",
            )
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def log_message(self, format: str, *args: object) -> None:
            return

    return WorkbenchRequestHandler


def _render_page(
    reader: RegistryReader,
    *,
    source_root: Path,
    title: str,
    entity_kinds: tuple[str, ...],
    token: str,
    overview: bool,
    show_sources: bool,
) -> str:
    counts = reader.entity_counts()
    sources = reader.audit_sources(source_root) if show_sources else []
    entities: list[dict[str, Any]] = []
    for kind in entity_kinds:
        entities.extend(reader.list_entities(kind))
    nav = "".join(
        f'<a href="{escape(path)}?{escape(urlencode({"token": token}))}">{escape(spec[1])}</a>'
        for path, spec in _PAGES.items()
    )
    sections: list[str] = []
    if overview:
        cards = "".join(
            f'<div class="metric"><b>{count}</b><span>{escape(kind)}</span></div>'
            for kind, count in sorted(counts.items())
        )
        sections.append(f'<section><h2>Catalog summary</h2><div class="metrics">{cards}</div></section>')
        overview_entities = reader.list_entities("roadmap_phase")
        sections.append(_entity_table("Roadmap status", overview_entities))
    if entities:
        sections.append(_entity_table(title, entities))
    elif not overview:
        sections.append(
            '<section><p class="empty">No indexed records for this fixed W0 view.</p></section>'
        )
    if show_sources:
        sections.append(_source_table(sources))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RF-CEM Workbench — {escape(title)}</title>
<style>
:root{{--ink:#17202a;--muted:#667085;--line:#d8dee8;--paper:#fff;--wash:#f4f7fb;--accent:#155eef}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);color:var(--ink);font:14px/1.5 system-ui,sans-serif}}
header{{background:#101828;color:#fff;padding:18px 24px}}header h1{{margin:0;font-size:22px}}header p{{margin:4px 0 0;color:#cbd5e1}}
nav{{display:flex;gap:6px;flex-wrap:wrap;padding:10px 18px;background:#fff;border-bottom:1px solid var(--line)}}nav a{{color:#344054;text-decoration:none;padding:7px 9px;border-radius:6px}}nav a:hover{{background:#eef4ff;color:var(--accent)}}
main{{max-width:1500px;margin:0 auto;padding:22px}}section{{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:18px;overflow:auto}}h2{{margin:0 0 12px;font-size:18px}}
.metrics{{display:flex;gap:10px;flex-wrap:wrap}}.metric{{min-width:140px;padding:12px;border:1px solid var(--line);border-radius:8px;background:#fbfcfe}}.metric b{{display:block;font-size:22px}}.metric span{{color:var(--muted)}}
table{{border-collapse:collapse;width:100%;min-width:760px}}th,td{{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}}th{{color:#475467;background:#f8fafc}}code,pre{{font:12px/1.4 ui-monospace,Consolas,monospace}}pre{{white-space:pre-wrap;max-width:780px;margin:0}}.status{{font-weight:650}}.empty{{color:var(--muted)}}
</style></head><body><header><h1>RF-CEM Workbench W0</h1><p>Derived read model · no CST · fixed read-only routes</p></header><nav>{nav}</nav><main><h2>{escape(title)}</h2>{''.join(sections)}</main></body></html>"""


def _entity_table(title: str, entities: list[dict[str, Any]]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(item['entity_kind']))}</td>"
        f"<td><code>{escape(str(item['entity_id']))}</code></td>"
        f"<td>{escape(str(item['label']))}</td>"
        f"<td class=\"status\">{escape(str(item['status']))}</td>"
        f"<td><code>{escape(str(item.get('source_id') or 'derived catalog'))}</code></td>"
        f"<td><details><summary>view</summary><pre>{escape(json.dumps(item.get('payload', {}), ensure_ascii=False, sort_keys=True, indent=2))}</pre></details></td>"
        "</tr>"
        for item in entities
    )
    return (
        f"<section><h2>{escape(title)}</h2><table><thead><tr>"
        "<th>Kind</th><th>ID</th><th>Label</th><th>Status</th><th>Source</th><th>Details</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _source_table(sources: list[dict[str, Any]]) -> str:
    rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(item['source_id']))}</code></td>"
        f"<td><code>{escape(str(item['display_path']))}</code></td>"
        f"<td class=\"status\">{escape(str(item['status']))}</td>"
        f"<td><code>{escape(str(item.get('stored_raw_sha256') or ''))}</code></td>"
        f"<td><code>{escape(str(item.get('actual_raw_sha256') or ''))}</code></td>"
        "</tr>"
        for item in sources
    )
    return (
        "<section><h2>Source status</h2><table><thead><tr>"
        "<th>Source</th><th>Repository-relative path</th><th>Status</th><th>Stored SHA-256</th><th>Current SHA-256</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )


__all__ = [
    "LOOPBACK_HOST",
    "WorkbenchServer",
    "create_workbench_handler",
]
