"""Authenticated loopback-only, read-only HTTP Workbench for W0-W3."""

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
    "/semantic-graphs": (
        "semantic-graphs",
        "Semantic Graphs / W1",
        (
            "family_grammar",
            "semantic_region_ontology",
            "semantic_landmark_ontology",
            "semantic_motif",
            "instance_graph",
            "semantic_region",
            "semantic_landmark",
            "boundary_interface",
            "graph_diff",
        ),
    ),
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
        "Compile Records / W2",
        (
            "compile_record",
            "region_geometry",
            "geometry_patch",
            "landmark_geometry_binding",
            "continuity_check",
            "geometry_validation",
            "baseline_comparison",
            "geometry_artifact",
        ),
    ),
    "/family-induction": (
        "family-induction",
        "Family Induction / W3",
        (
            "family_induction_bundle",
            "graph_alignment",
            "common_backbone_slot",
            "alignment_residual",
            "family_extension_proposal",
            "proposal_review",
            "grammar_patch",
            "grammar_patch_application",
            "grammar_diff",
            "blind_instance_graph",
            "blind_validation",
        ),
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
                    semantic_graphs=parsed.path == "/semantic-graphs",
                    compile_records=parsed.path == "/compile-records",
                    family_induction=parsed.path == "/family-induction",
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
                        "message": "Workbench W0-W3 is read-only and CORS is disabled",
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
    semantic_graphs: bool,
    compile_records: bool,
    family_induction: bool,
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
    if semantic_graphs:
        sections.extend(_semantic_graph_sections(entities))
    elif compile_records:
        sections.extend(_compile_record_sections(entities))
    elif family_induction:
        sections.extend(_family_induction_sections(entities))
    elif entities:
        sections.append(_entity_table(title, entities))
    elif not overview:
        sections.append(
            '<section><p class="empty">No indexed records for this fixed read-only view.</p></section>'
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
.graph-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px}}.graph-card{{border:1px solid var(--line);border-radius:9px;padding:14px;background:#fbfcfe}}.graph-card h3{{margin:0 0 5px;font-size:16px}}.nose{{display:inline-block;padding:3px 8px;border-radius:999px;background:#eaf2ff;color:#1849a9;font-weight:700}}.sequence{{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-top:12px}}.chip{{display:inline-block;border:1px solid #b9c5d8;border-radius:6px;background:#fff;padding:4px 7px;font:12px ui-monospace,Consolas,monospace}}.arrow{{color:var(--muted)}}.facts{{color:var(--muted);margin:7px 0 0}}
.compile-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px}}.compile-card{{border:1px solid var(--line);border-radius:9px;padding:14px;background:#fbfcfe}}.compile-card h3{{margin:0 0 5px;font-size:16px}}.pass-pill{{display:inline-block;padding:3px 8px;border-radius:999px;background:#eafaf0;color:#067647;font-weight:700}}.trace-list{{display:grid;gap:8px}}.trace-row{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:8px;border-bottom:1px solid var(--line)}}.owner{{border-color:#84adff;background:#eef4ff}}.patch-sequence{{display:flex;align-items:center;gap:5px;flex-wrap:wrap}}
.induction-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}}.induction-card{{border:1px solid var(--line);border-radius:9px;padding:14px;background:#fbfcfe}}.induction-card h3{{margin:0 0 7px;font-size:16px}}.pending-pill{{display:inline-block;padding:3px 8px;border-radius:999px;background:#fff4e5;color:#b54708;font-weight:700}}.held-out{{border-left:5px solid #12b76a}}.backbone{{display:flex;align-items:center;gap:5px;flex-wrap:wrap}}
</style></head><body><header><h1>RF-CEM Workbench W0 / W1 / W2 / W3</h1><p>Derived read model · no CST · fixed read-only routes</p></header><nav>{nav}</nav><main><h2>{escape(title)}</h2>{''.join(sections)}</main></body></html>"""


def _semantic_graph_sections(entities: list[dict[str, Any]]) -> list[str]:
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_kind.setdefault(str(entity["entity_kind"]), []).append(entity)
    sections: list[str] = []
    graphs = by_kind.get("instance_graph", [])
    if graphs:
        cards: list[str] = []
        for graph in graphs:
            payload = graph.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            nose_presence = str(payload.get("nose_presence") or "unknown")
            nose_label = (
                "Nose: present (paired motif)"
                if nose_presence == "present"
                else "Nose: absent (reviewed topology)"
            )
            raw_types = payload.get("ordered_region_types", [])
            region_types = raw_types if isinstance(raw_types, list) else []
            sequence = '<span class="arrow">→</span>'.join(
                f'<span class="chip">{escape(str(region_type))}</span>'
                for region_type in region_types
            )
            cards.append(
                '<article class="graph-card">'
                f'<h3>{escape(str(graph["label"]))}</h3>'
                f'<span class="nose">{escape(nose_label)}</span>'
                f'<p class="facts">{escape(str(payload.get("region_count", 0)))} regions · '
                f'{escape(str(graph["status"]))}</p>'
                f'<div class="sequence">{sequence}</div>'
                '</article>'
            )
        sections.append(
            '<section><h2>Validated instance topologies</h2>'
            f'<div class="graph-grid">{"".join(cards)}</div></section>'
        )
    for kind, label in (
        ("family_grammar", "Family grammar"),
        ("semantic_motif", "Optional semantic motifs"),
        ("graph_diff", "Semantic topology diff"),
        ("semantic_region_ontology", "Semantic region ontology"),
        ("semantic_landmark_ontology", "Semantic landmark ontology"),
        ("semantic_region", "Instance semantic regions"),
        ("semantic_landmark", "Instance semantic landmarks"),
        ("boundary_interface", "Boundary interfaces"),
    ):
        values = by_kind.get(kind, [])
        if values:
            sections.append(_entity_table(label, values))
    if not sections:
        sections.append(
            '<section><p class="empty">No W1 semantic graph proof set was supplied at rebuild.</p></section>'
        )
    return sections


def _compile_record_sections(entities: list[dict[str, Any]]) -> list[str]:
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_kind.setdefault(str(entity["entity_kind"]), []).append(entity)
    records = by_kind.get("compile_record", [])
    r2_records = [
        item
        for item in records
        if isinstance(item.get("payload"), dict)
        and item["payload"].get("schema_version") == "compile_record.v0"
    ]
    if not r2_records:
        return [
            '<section><p class="empty">No W2 compile_record.v0 proof set was supplied at rebuild.</p></section>'
        ]

    sections: list[str] = []
    cards: list[str] = []
    for item in sorted(r2_records, key=lambda value: str(value["entity_id"])):
        payload = item["payload"]
        validation = payload.get("geometry_validation", {})
        if not isinstance(validation, dict):
            validation = {}
        warnings = payload.get("warnings", [])
        warning_values = warnings if isinstance(warnings, list) else []
        warning_html = (
            "".join(f"<li>{escape(str(value))}</li>" for value in warning_values)
            if warning_values
            else "<li>None</li>"
        )
        brep_label = "BRep valid" if validation.get("brep_valid") is True else "BRep invalid"
        cards.append(
            '<article class="compile-card">'
            f'<h3>{escape(str(payload.get("instance_id") or item["label"]))}</h3>'
            f'<p><span class="pass-pill">{escape(str(item["status"]))}</span></p>'
            f'<p class="facts"><b>{escape(str(payload.get("region_count", 0)))}</b> regions · '
            f'<b>{escape(str(payload.get("patch_count", 0)))}</b> patches · '
            f'{escape(brep_label)}</p>'
            f'<p class="facts">Compiler: <code>{escape(str(payload.get("compiler_version") or ""))}</code></p>'
            f'<p class="facts">No live CST: <b>{escape(str(payload.get("live_cst_status") == "not_run"))}</b> · '
            f'RF physical acceptance: <b>{escape(str(payload.get("physical_acceptance_status") or ""))}</b></p>'
            '<details><summary>Warnings / reviewed limitations</summary>'
            f'<ul>{warning_html}</ul></details>'
            '</article>'
        )
    sections.append(
        '<section><h2>Validated no-CST compiles</h2>'
        f'<div class="compile-grid">{"".join(cards)}</div></section>'
    )

    region_traces: list[str] = []
    for item in sorted(
        by_kind.get("region_geometry", []),
        key=lambda value: (
            str(value.get("payload", {}).get("instance_id", "")),
            int(value.get("payload", {}).get("region_order", 0)),
        ),
    ):
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            continue
        representation = payload.get("representation", {})
        if not isinstance(representation, dict):
            representation = {}
        patches = payload.get("patches", [])
        patch_values = patches if isinstance(patches, list) else []
        patch_chips = '<span class="arrow">→</span>'.join(
            '<span class="chip">'
            f'{escape(str(patch.get("patch_id") or "patch"))}: '
            f'{escape(str((patch.get("representation") or {}).get("representation_type") or "unknown"))}'
            '</span>'
            for patch in patch_values
            if isinstance(patch, dict)
        )
        region_traces.append(
            '<article class="trace-row">'
            f'<span class="chip owner">{escape(str(payload.get("owner_region_id") or item["entity_id"]))}</span>'
            '<span class="arrow">→</span>'
            f'<span class="chip">{escape(str(representation.get("representation_type") or "CompositeRegionRepresentation"))}</span>'
            '<span class="arrow">→</span>'
            f'<span class="patch-sequence">{patch_chips}</span>'
            '</article>'
        )
    sections.append(
        '<section><h2>Region → representation → patches</h2>'
        f'<div class="trace-list">{"".join(region_traces)}</div></section>'
    )

    for kind, label in (
        ("landmark_geometry_binding", "Landmark geometry bindings"),
        ("continuity_check", "C0 / G1 / G2 continuity checks"),
        ("geometry_validation", "Closed profile and BRep / STEP validation"),
        ("baseline_comparison", "Accepted baseline comparisons and warnings"),
        ("geometry_artifact", "Hash-verified compiled artifacts"),
        ("geometry_patch", "Geometry patch ownership details"),
        ("compile_record", "Raw compile_record.v0 contracts"),
    ):
        values = by_kind.get(kind, [])
        if kind == "compile_record":
            values = r2_records
        if values:
            sections.append(_entity_table(label, values))
    return sections


def _family_induction_sections(entities: list[dict[str, Any]]) -> list[str]:
    """Render the complete W3 alignment-to-blind-validation audit chain."""

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_kind.setdefault(str(entity["entity_kind"]), []).append(entity)
    alignments = by_kind.get("graph_alignment", [])
    if not alignments:
        return [
            '<section><p class="empty">No W3 family-induction proof bundle was supplied at rebuild.</p></section>'
        ]

    alignment = alignments[0]
    alignment_payload = alignment.get("payload", {})
    if not isinstance(alignment_payload, dict):
        alignment_payload = {}
    proposal = _first_entity_payload(by_kind, "family_extension_proposal")
    review = _first_entity_payload(by_kind, "proposal_review")
    application = _first_entity_payload(by_kind, "grammar_patch_application")
    blind = _first_entity_payload(by_kind, "blind_validation")
    blind_graph = _first_entity_payload(by_kind, "blind_instance_graph")

    slots = sorted(
        by_kind.get("common_backbone_slot", []),
        key=lambda item: int(
            (item.get("payload") or {}).get("slot_index", 0)
            if isinstance(item.get("payload"), dict)
            else 0
        ),
    )
    backbone_chips = '<span class="arrow">&rarr;</span>'.join(
        f'<span class="chip">{escape(str((item.get("payload") or {}).get("semantic_key") or item["label"]))}</span>'
        for item in slots
        if isinstance(item.get("payload"), dict)
    )
    residuals = by_kind.get("alignment_residual", [])
    confidence = proposal.get("confidence", "")
    parameter_names_read = alignment_payload.get("parameter_names_read")
    training_ids = alignment_payload.get("graph_refs", [])
    training_count = len(training_ids) if isinstance(training_ids, list) else 0
    review_decision = str(review.get("decision") or "missing")
    patch_applied = application.get("applied") is True
    grammar_diff = application.get("grammar_diff", [])
    grammar_diff_count = len(grammar_diff) if isinstance(grammar_diff, list) else 0
    blind_instance_id = str(
        blind.get("blind_instance_id")
        or blind_graph.get("instance_id")
        or "unknown"
    )

    cards = (
        '<article class="induction-card">'
        '<h3>Reviewed semantic-graph alignment</h3>'
        f'<p><span class="pass-pill">{escape(str(alignment["status"]))}</span></p>'
        f'<p class="facts"><b>{training_count}</b> training graphs · '
        f'<b>{len(slots)}</b> common slots · <b>{len(residuals)}</b> residuals</p>'
        f'<p class="facts">Algorithm: <code>{escape(str(alignment_payload.get("algorithm_version") or ""))}</code></p>'
        f'<p class="facts">Parameter names read: <b>{escape(str(parameter_names_read))}</b></p>'
        '</article>'
        '<article class="induction-card">'
        '<h3>Optional motif proposal</h3>'
        '<p><span class="pending-pill">pending · non-mutating</span></p>'
        f'<p class="facts">Kind: <b>{escape(str(proposal.get("proposal_kind") or ""))}</b> · '
        f'confidence: <b>{escape(str(confidence))}</b></p>'
        f'<p class="facts">Region: <code>{escape(str(proposal.get("region_type") or ""))}</code> · '
        f'counts: <code>{escape(json.dumps(proposal.get("allowed_counts", [])))}</code></p>'
        '<p class="facts">Pending proposal does not mutate grammar.</p>'
        '</article>'
        '<article class="induction-card">'
        '<h3>Manual review and explicit patch</h3>'
        f'<p><span class="pass-pill">{escape(review_decision)}</span></p>'
        f'<p class="facts">Accepted manual review: <b>{escape(str(review_decision == "accepted"))}</b> · '
        f'patch applied: <b>{escape(str(patch_applied))}</b></p>'
        f'<p class="facts">Grammar diff entries: <b>{grammar_diff_count}</b> · '
        f'all training instances valid: <b>{escape(str(application.get("all_instances_valid")))}</b></p>'
        '</article>'
        '<article class="induction-card held-out">'
        '<h3>Held-out real instance: LEReC 704 MHz</h3>'
        f'<p><span class="pass-pill">{escape(str(blind.get("status") or ""))}</span></p>'
        f'<p class="facts">Instance: <code>{escape(blind_instance_id)}</code></p>'
        f'<p class="facts">Classification: <b>{escape(str(blind.get("classification") or ""))}</b></p>'
        f'<p class="facts">Used for induction: <b>{escape(str(blind.get("blind_instance_used_for_induction")))}</b></p>'
        f'<p class="facts">Representation contract: <b>{escape(str(blind.get("representation_contract") or ""))}</b> · No live CST</p>'
        '</article>'
    )
    sections = [
        '<section><h2>W3 hard-gate chain</h2>'
        f'<div class="induction-grid">{cards}</div></section>',
        '<section><h2>Common semantic backbone</h2>'
        f'<div class="backbone">{backbone_chips}</div></section>',
    ]
    if residuals:
        sections.append(_entity_table("Alignment residuals / motif evidence", residuals))
    for kind, label in (
        ("family_extension_proposal", "Evidence-bound extension proposal"),
        ("proposal_review", "Explicit proposal review"),
        ("grammar_patch", "Authorized grammar patch"),
        ("grammar_diff", "Grammar before / after diff"),
        ("blind_instance_graph", "Held-out LEReC reviewed semantic graph"),
        ("blind_validation", "Post-induction blind validation"),
        ("family_induction_bundle", "R3 source-bound proof bundle"),
    ):
        values = by_kind.get(kind, [])
        if values:
            sections.append(_entity_table(label, values))
    return sections


def _first_entity_payload(
    by_kind: dict[str, list[dict[str, Any]]], kind: str
) -> dict[str, Any]:
    values = by_kind.get(kind, [])
    if not values:
        return {}
    payload = values[0].get("payload", {})
    return payload if isinstance(payload, dict) else {}


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
