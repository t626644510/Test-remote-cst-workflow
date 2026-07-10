"""Loopback-only persistence and JSON API for literature review sessions.

The server deliberately exposes no filesystem browsing, shell, CST, or CORS
surface.  Review decisions are overlays: source semantic packages remain
immutable, while the current session snapshot and its append-only event log
stay below one caller-selected session directory.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
from typing import Any, Callable, Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit
import uuid

from .types import REVIEW_STATUSES, SEMANTIC_ITEM_SECTIONS


SESSION_SCHEMA_VERSION = "review_session.v1"
EVENT_SCHEMA_VERSION = "review_event.v1"
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_MAX_REQUEST_BYTES = 256 * 1024
MAX_ITEM_ID_LENGTH = 240
MAX_NOTE_LENGTH = 8_000
MAX_REVIEWER_LENGTH = 240

PreviewCallback = Callable[[dict[str, Any], dict[str, Any]], Mapping[str, Any]]


class ReviewSessionError(ValueError):
    """Raised when review-session input or persisted state is invalid."""


class RevisionConflict(ReviewSessionError):
    """Raised when a mutation was based on a stale session revision."""

    def __init__(self, expected_revision: int, current_revision: int) -> None:
        super().__init__(
            f"expected revision {expected_revision}, current revision is {current_revision}"
        )
        self.expected_revision = expected_revision
        self.current_revision = current_revision


class ReviewSessionStore:
    """Persist a review overlay below a single constrained session root.

    ``review_session.v1.json`` is replaced atomically.  Every accepted state
    mutation is also appended to ``review_events.jsonl``.  The source semantic
    package is never edited by this class.
    """

    SESSION_FILENAME = "review_session.v1.json"
    EVENTS_FILENAME = "review_events.jsonl"

    def __init__(
        self,
        session_root: Path,
        *,
        initial_session: Optional[Mapping[str, Any]] = None,
    ) -> None:
        requested_root = Path(session_root).expanduser()
        requested_root.mkdir(parents=True, exist_ok=True)
        if not requested_root.is_dir():
            raise ReviewSessionError(f"session root is not a directory: {requested_root}")
        self.session_root = requested_root.resolve(strict=True)
        self._lock = threading.RLock()
        self.session_path = self._safe_child(self.SESSION_FILENAME)
        self.events_path = self._safe_child(self.EVENTS_FILENAME)

        if self.session_path.exists():
            if initial_session is not None:
                raise ReviewSessionError(
                    "initial_session cannot be supplied when a persisted session exists"
                )
            self._session = self._load_session()
        else:
            self._session = self._new_session(initial_session)
            self._write_session_atomic(self._session)

        # Opening in append mode creates the audit log without ever truncating it.
        self._append_bytes(self.events_path, b"")

    def get_session(self, *, expected_revision: Optional[int] = None) -> dict[str, Any]:
        """Return an isolated snapshot, optionally enforcing its revision."""
        with self._lock:
            if expected_revision is not None:
                self._check_revision(expected_revision)
            return copy.deepcopy(self._session)

    def record_review_event(
        self,
        *,
        expected_revision: int,
        item_id: str,
        status: str,
        review_note: str = "",
        reviewer: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Record one literature-vocabulary review decision."""
        clean_item_id = _bounded_text(item_id, "item_id", MAX_ITEM_ID_LENGTH)
        if status not in REVIEW_STATUSES:
            allowed = ", ".join(sorted(REVIEW_STATUSES))
            raise ReviewSessionError(f"status must be one of: {allowed}")
        clean_note = _bounded_text(
            review_note, "review_note", MAX_NOTE_LENGTH, allow_empty=True
        )
        clean_reviewer = _bounded_text(
            reviewer, "reviewer", MAX_REVIEWER_LENGTH, allow_empty=True
        )

        with self._lock:
            self._check_revision(expected_revision)
            revision = expected_revision + 1
            occurred_at = _utc_now()
            event_id = str(uuid.uuid4())
            event = {
                "schema_version": EVENT_SCHEMA_VERSION,
                "event_id": event_id,
                "event_type": "review_decision",
                "revision": revision,
                "occurred_at": occurred_at,
                "item_id": clean_item_id,
                "status": status,
                "review_note": clean_note,
                "reviewer": clean_reviewer,
            }
            session = copy.deepcopy(self._session)
            session["revision"] = revision
            session["updated_at"] = occurred_at
            session["review_decisions"][clean_item_id] = {
                "item_id": clean_item_id,
                "status": status,
                "review_note": clean_note,
                "reviewer": clean_reviewer,
                "reviewed_at": occurred_at,
                "event_id": event_id,
                "revision": revision,
            }
            for manual_item in session["manual_items"]:
                if manual_item["id"] == clean_item_id:
                    manual_item["human_review_status"] = status
                    manual_item["review_note"] = clean_note
                    manual_item["reviewer"] = clean_reviewer
                    manual_item["reviewed_at"] = occurred_at
                    break
            self._commit(session, event)
            return copy.deepcopy(event), copy.deepcopy(session)

    def add_manual_item(
        self,
        *,
        expected_revision: int,
        item: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Add a manual semantic overlay, always starting at ``pending``."""
        if not isinstance(item, Mapping):
            raise ReviewSessionError("item must be a JSON object")
        candidate = copy.deepcopy(dict(item))
        section = candidate.get("section")
        if section not in SEMANTIC_ITEM_SECTIONS:
            allowed = ", ".join(SEMANTIC_ITEM_SECTIONS)
            raise ReviewSessionError(f"item.section must be one of: {allowed}")

        id_value = candidate.get("id", candidate.get("item_id"))
        if candidate.get("id") and candidate.get("item_id"):
            if candidate["id"] != candidate["item_id"]:
                raise ReviewSessionError("item.id and item.item_id must match")
        if id_value is None:
            id_value = f"manual:{uuid.uuid4()}"
        item_id = _bounded_text(id_value, "item.id", MAX_ITEM_ID_LENGTH)

        supplied_status = candidate.get(
            "human_review_status", candidate.get("status", "pending")
        )
        if supplied_status != "pending":
            raise ReviewSessionError("a manual item must start with pending status")
        note = _bounded_text(
            candidate.get("review_note", ""),
            "item.review_note",
            MAX_NOTE_LENGTH,
            allow_empty=True,
        )

        with self._lock:
            self._check_revision(expected_revision)
            existing_ids = {
                existing["id"] for existing in self._session["manual_items"]
            }
            if item_id in existing_ids:
                raise ReviewSessionError(f"manual item already exists: {item_id}")

            revision = expected_revision + 1
            occurred_at = _utc_now()
            event_id = str(uuid.uuid4())
            for reserved in (
                "origin",
                "created_at",
                "created_revision",
                "reviewer",
                "reviewed_at",
                "event_id",
                "revision",
            ):
                candidate.pop(reserved, None)
            candidate.pop("item_id", None)
            candidate.pop("status", None)
            candidate.update(
                {
                    "id": item_id,
                    "section": section,
                    "origin": "manual_overlay",
                    "human_review_status": "pending",
                    "review_note": note,
                    "created_at": occurred_at,
                    "created_revision": revision,
                }
            )
            _json_bytes(candidate)  # Fail before either persistent file changes.
            event = {
                "schema_version": EVENT_SCHEMA_VERSION,
                "event_id": event_id,
                "event_type": "manual_item_added",
                "revision": revision,
                "occurred_at": occurred_at,
                "item_id": item_id,
                "item": copy.deepcopy(candidate),
            }
            session = copy.deepcopy(self._session)
            session["revision"] = revision
            session["updated_at"] = occurred_at
            session["manual_items"].append(candidate)
            session["review_decisions"][item_id] = {
                "item_id": item_id,
                "status": "pending",
                "review_note": note,
                "reviewer": "",
                "reviewed_at": occurred_at,
                "event_id": event_id,
                "revision": revision,
            }
            self._commit(session, event)
            return (
                copy.deepcopy(candidate),
                copy.deepcopy(event),
                copy.deepcopy(session),
            )

    def _new_session(
        self, initial_session: Optional[Mapping[str, Any]]
    ) -> dict[str, Any]:
        if initial_session is not None and not isinstance(initial_session, Mapping):
            raise ReviewSessionError("initial_session must be a mapping")
        session = copy.deepcopy(dict(initial_session or {}))
        now = _utc_now()
        session.update(
            {
                "schema_version": SESSION_SCHEMA_VERSION,
                "revision": 0,
                "created_at": now,
                "updated_at": now,
                "review_decisions": {},
                "manual_items": [],
            }
        )
        _json_bytes(session)
        return session

    def _load_session(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.session_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ReviewSessionError(f"cannot read persisted review session: {exc}") from exc
        if not isinstance(payload, dict):
            raise ReviewSessionError("persisted review session must be a JSON object")
        if payload.get("schema_version") != SESSION_SCHEMA_VERSION:
            raise ReviewSessionError(
                f"persisted session schema must be {SESSION_SCHEMA_VERSION}"
            )
        if not _is_revision(payload.get("revision")):
            raise ReviewSessionError("persisted session revision must be a non-negative integer")
        if not isinstance(payload.get("review_decisions"), dict):
            raise ReviewSessionError("persisted review_decisions must be an object")
        if not isinstance(payload.get("manual_items"), list):
            raise ReviewSessionError("persisted manual_items must be an array")
        for item_id, decision in payload["review_decisions"].items():
            if (
                not isinstance(item_id, str)
                or not isinstance(decision, dict)
                or decision.get("item_id") != item_id
                or decision.get("status") not in REVIEW_STATUSES
            ):
                raise ReviewSessionError("persisted review decision is invalid")
        manual_ids: set[str] = set()
        for item in payload["manual_items"]:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or item.get("section") not in SEMANTIC_ITEM_SECTIONS
                or item.get("origin") != "manual_overlay"
                or item.get("human_review_status") not in REVIEW_STATUSES
                or item["id"] in manual_ids
            ):
                raise ReviewSessionError("persisted manual item is invalid")
            manual_ids.add(item["id"])
        _json_bytes(payload)
        return payload

    def _check_revision(self, expected_revision: int) -> None:
        if not _is_revision(expected_revision):
            raise ReviewSessionError("expected_revision must be a non-negative integer")
        current = self._session["revision"]
        if expected_revision != current:
            raise RevisionConflict(expected_revision, current)

    def _commit(self, session: dict[str, Any], event: dict[str, Any]) -> None:
        session_bytes = _json_bytes(session)
        event_bytes = _compact_json_bytes(event) + b"\n"
        # The log is write-ahead: a complete event is durable before the
        # corresponding atomic snapshot is published.
        self._append_bytes(self.events_path, event_bytes)
        self._write_bytes_atomic(self.session_path, session_bytes)
        self._session = session

    def _write_session_atomic(self, session: dict[str, Any]) -> None:
        self._write_bytes_atomic(self.session_path, _json_bytes(session))

    def _write_bytes_atomic(self, target: Path, payload: bytes) -> None:
        target = self._safe_child(target.name)
        file_descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(self.session_root)
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(file_descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, target)
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _append_bytes(self, target: Path, payload: bytes) -> None:
        target = self._safe_child(target.name)
        with target.open("ab") as stream:
            if payload:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())

    def _safe_child(self, filename: str) -> Path:
        if filename not in {self.SESSION_FILENAME, self.EVENTS_FILENAME}:
            raise ReviewSessionError(f"unsupported session file: {filename}")
        candidate = self.session_root / filename
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.session_root)
        except ValueError as exc:
            raise ReviewSessionError("session file resolves outside session root") from exc
        return candidate


class _LoopbackHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class ReviewServer:
    """Authenticated loopback HTTP wrapper for a :class:`ReviewSessionStore`."""

    def __init__(
        self,
        store: ReviewSessionStore,
        *,
        preview_callback: Optional[PreviewCallback] = None,
        review_html: Optional[str] = None,
        review_path: str = "/",
        token: Optional[str] = None,
        port: int = 0,
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    ) -> None:
        if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65_535:
            raise ValueError("port must be an integer from 0 through 65535")
        if not isinstance(max_request_bytes, int) or max_request_bytes <= 0:
            raise ValueError("max_request_bytes must be a positive integer")
        selected_token = secrets.token_urlsafe(32) if token is None else token
        if not isinstance(selected_token, str) or len(selected_token) < 16:
            raise ValueError("token must contain at least 16 characters")

        self.store = store
        self.token = selected_token
        self.preview_callback = preview_callback
        self.review_path = _validate_review_path(review_path)
        self._has_review_html = review_html is not None
        self.max_request_bytes = max_request_bytes
        handler = create_review_handler(
            store,
            token=selected_token,
            preview_callback=preview_callback,
            review_html=review_html,
            review_path=self.review_path,
            max_request_bytes=max_request_bytes,
        )
        self._httpd = _LoopbackHTTPServer((LOOPBACK_HOST, port), handler)
        self._thread: Optional[threading.Thread] = None

    @property
    def host(self) -> str:
        """Return the fixed IPv4 loopback bind address."""
        return LOOPBACK_HOST

    @property
    def port(self) -> int:
        """Return the selected port (useful when constructed with ``port=0``)."""
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        """Return the loopback origin without exposing the bearer token."""
        return f"http://{self.host}:{self.port}"

    @property
    def api_headers(self) -> dict[str, str]:
        """Return headers suitable for same-origin JSON requests."""
        return {"X-Review-Token": self.token}

    @property
    def review_url(self) -> Optional[str]:
        """Return the tokenized initial-document URL, if HTML was injected."""
        if not self._has_review_html:
            return None
        return f"{self.base_url}{self.review_path}?{urlencode({'token': self.token})}"

    def start(self) -> "ReviewServer":
        """Run the server in one daemon thread."""
        if self._thread is not None:
            raise RuntimeError("review server has already been started")
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="rf-cem-literature-review",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop and close a server previously started with :meth:`start`."""
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

    def __enter__(self) -> "ReviewServer":
        return self.start()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()


def create_review_handler(
    store: ReviewSessionStore,
    *,
    token: str,
    preview_callback: Optional[PreviewCallback] = None,
    review_html: Optional[str] = None,
    review_path: str = "/",
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
) -> type[BaseHTTPRequestHandler]:
    """Create a handler bound to one store and unguessable session token."""
    if not isinstance(token, str) or len(token) < 16:
        raise ValueError("token must contain at least 16 characters")
    if review_html is not None and not isinstance(review_html, str):
        raise TypeError("review_html must be a string or None")
    selected_review_path = _validate_review_path(review_path)
    review_html_bytes = review_html.encode("utf-8") if review_html is not None else None

    class ReviewRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "RFCEMReview/1"
        sys_version = ""
        _review_html = review_html_bytes

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlsplit(self.path)
            if parsed.path == selected_review_path and review_html_bytes is not None:
                if not self._document_request_is_trusted(parsed.query):
                    return
                self._send_html(review_html_bytes)
                return
            if not self._request_is_trusted():
                return
            if parsed.path != "/api/session":
                self._send_error(404, "not_found", "endpoint not found")
                return
            self._send_json(200, {"ok": True, "session": store.get_session()})

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if not self._request_is_trusted():
                return
            path = urlsplit(self.path).path
            if path not in {
                "/api/review-events",
                "/api/manual-items",
                "/api/preview",
            }:
                self._send_error(404, "not_found", "endpoint not found")
                return
            try:
                body = self._read_json_body()
                expected_revision = body.get("expected_revision")
                if path == "/api/review-events":
                    event, session = store.record_review_event(
                        expected_revision=expected_revision,
                        item_id=body.get("item_id"),
                        status=body.get("status"),
                        review_note=body.get("review_note", ""),
                        reviewer=body.get("reviewer", ""),
                    )
                    self._send_json(
                        200, {"ok": True, "event": event, "session": session}
                    )
                    return
                if path == "/api/manual-items":
                    item, event, session = store.add_manual_item(
                        expected_revision=expected_revision,
                        item=body.get("item"),
                    )
                    self._send_json(
                        201,
                        {
                            "ok": True,
                            "item": item,
                            "event": event,
                            "session": session,
                        },
                    )
                    return

                snapshot = store.get_session(expected_revision=expected_revision)
                if preview_callback is None:
                    self._send_error(
                        503, "preview_unavailable", "preview callback is not configured"
                    )
                    return
                request_payload = copy.deepcopy(body)
                request_payload.pop("expected_revision", None)
                preview = preview_callback(snapshot, request_payload)
                if not isinstance(preview, Mapping):
                    raise ReviewSessionError("preview callback must return a mapping")
                preview_payload = copy.deepcopy(dict(preview))
                _json_bytes(preview_payload)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "revision": snapshot["revision"],
                        "preview": preview_payload,
                    },
                )
            except RevisionConflict as exc:
                self._send_json(
                    409,
                    {
                        "ok": False,
                        "error": {
                            "code": "revision_conflict",
                            "message": str(exc),
                            "current_revision": exc.current_revision,
                        },
                    },
                )
            except ReviewSessionError as exc:
                self._send_error(400, "invalid_request", str(exc))
            except _ResponseAlreadySent:
                return
            except Exception:
                # Callback and persistence internals are intentionally not exposed
                # to the browser; callers can wrap their callback for diagnostics.
                self._send_error(500, "internal_error", "request processing failed")

        def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._send_error(405, "method_not_allowed", "CORS is not enabled")

        def _request_is_trusted(self) -> bool:
            if not self._host_is_allowed():
                self._send_error(403, "invalid_host", "request Host is not allowed")
                return False
            if not self._origin_is_allowed():
                self._send_error(403, "invalid_origin", "request Origin is not allowed")
                return False
            supplied = self.headers.get("X-Review-Token", "")
            authorization = self.headers.get("Authorization", "")
            if not supplied and authorization.startswith("Bearer "):
                supplied = authorization[7:]
            if not supplied or not hmac.compare_digest(supplied, token):
                self._send_error(403, "forbidden", "valid review token required")
                return False
            return True

        def _document_request_is_trusted(self, query: str) -> bool:
            if not self._host_is_allowed():
                self._send_error(403, "invalid_host", "request Host is not allowed")
                return False
            if not self._origin_is_allowed():
                self._send_error(403, "invalid_origin", "request Origin is not allowed")
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
                self._send_error(
                    403, "forbidden", "valid initial-document token required"
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

        def _read_json_body(self) -> dict[str, Any]:
            if self.headers.get("Transfer-Encoding"):
                raise ReviewSessionError("Transfer-Encoding is not supported")
            content_type = self.headers.get("Content-Type", "")
            if content_type.split(";", 1)[0].strip().lower() != "application/json":
                self._send_error(
                    415, "unsupported_media_type", "Content-Type must be application/json"
                )
                raise _ResponseAlreadySent
            length_header = self.headers.get("Content-Length")
            if length_header is None:
                raise ReviewSessionError("Content-Length is required")
            try:
                length = int(length_header)
            except ValueError as exc:
                raise ReviewSessionError("Content-Length must be an integer") from exc
            if length < 0:
                raise ReviewSessionError("Content-Length cannot be negative")
            if length > max_request_bytes:
                self._send_error(413, "request_too_large", "request body exceeds limit")
                raise _ResponseAlreadySent
            payload = self.rfile.read(length)
            try:
                decoded = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ReviewSessionError("request body must be valid UTF-8 JSON") from exc
            if not isinstance(decoded, dict):
                raise ReviewSessionError("request body must be a JSON object")
            return decoded

        def _send_error(self, status: int, code: str, message: str) -> None:
            self._send_json(
                status,
                {"ok": False, "error": {"code": code, "message": message}},
            )

        def _send_json(self, status: int, payload: object) -> None:
            body = _compact_json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def _send_html(self, body: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def log_message(self, format: str, *args: object) -> None:
            # The embedding CLI/app owns logging; bearer-token requests are not
            # echoed to stderr by this low-level transport.
            return

    return ReviewRequestHandler


class _ResponseAlreadySent(Exception):
    pass


def _bounded_text(
    value: object,
    field_name: str,
    maximum_length: int,
    *,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ReviewSessionError(f"{field_name} must be a string")
    clean = value.strip() if not allow_empty else value
    if not clean and not allow_empty:
        raise ReviewSessionError(f"{field_name} cannot be empty")
    if len(clean) > maximum_length:
        raise ReviewSessionError(
            f"{field_name} exceeds the {maximum_length}-character limit"
        )
    return clean


def _is_revision(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_review_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("review_path must be a string")
    parsed = urlsplit(value)
    path = parsed.path
    if (
        not path.startswith("/")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or path == "/api"
        or path.startswith("/api/")
        or any(segment in {".", ".."} for segment in path.split("/"))
    ):
        raise ValueError("review_path must be a local non-API absolute URL path")
    return path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _json_bytes(value: object) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ReviewSessionError(f"value is not JSON serializable: {exc}") from exc
    return (text + "\n").encode("utf-8")


def _compact_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReviewSessionError(f"value is not JSON serializable: {exc}") from exc
