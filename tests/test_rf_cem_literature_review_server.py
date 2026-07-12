import copy
import http.client
import json
import os
from pathlib import Path
import sys
from typing import Any, Optional
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rf_cem.literature_semantics.review_server import (
    ReviewServer,
    ReviewSessionError,
    ReviewSessionStore,
    RevisionConflict,
)


pytestmark = pytest.mark.no_cst

TOKEN = "test-token-0123456789abcdef"


def test_store_persists_utf8_decision_atomically_and_appends_event(tmp_path):
    root = tmp_path / "review"
    store = ReviewSessionStore(
        root,
        initial_session={"title": "SLS-2 文献语义审核", "layers": [1, 2, 3]},
    )

    event, session = store.record_review_event(
        expected_revision=0,
        item_id="shape:elliptical-profile",
        status="accepted",
        review_note="轮廓合理；保留为论文近似。",
        reviewer="研究员甲",
    )

    assert session["revision"] == 1
    assert session["title"] == "SLS-2 文献语义审核"
    assert session["review_decisions"]["shape:elliptical-profile"]["status"] == "accepted"
    persisted = json.loads(store.session_path.read_text(encoding="utf-8"))
    assert persisted == session
    assert "轮廓合理" in store.session_path.read_text(encoding="utf-8")
    lines = store.events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == event

    reloaded = ReviewSessionStore(root)
    assert reloaded.get_session() == session
    with pytest.raises(ReviewSessionError, match="initial_session"):
        ReviewSessionStore(root, initial_session={"replace": True})


def test_store_enforces_literature_status_and_optimistic_revision(tmp_path):
    store = ReviewSessionStore(tmp_path / "review")

    with pytest.raises(ReviewSessionError, match="status must be one of"):
        store.record_review_event(
            expected_revision=0,
            item_id="candidate-1",
            status="ok",
        )
    assert store.get_session()["revision"] == 0
    assert store.events_path.read_bytes() == b""

    store.record_review_event(
        expected_revision=0,
        item_id="candidate-1",
        status="needs_more_evidence",
    )
    original_log = store.events_path.read_bytes()

    with pytest.raises(RevisionConflict) as conflict:
        store.record_review_event(
            expected_revision=0,
            item_id="candidate-2",
            status="rejected",
        )
    assert conflict.value.current_revision == 1
    assert store.get_session()["revision"] == 1
    assert store.events_path.read_bytes() == original_log


def test_manual_items_are_pending_overlays_until_separately_reviewed(tmp_path):
    store = ReviewSessionStore(tmp_path / "review")

    item, event, session = store.add_manual_item(
        expected_revision=0,
        item={
            "id": "manual:beam-pipe-radius",
            "section": "parameter_ranges",
            "parameter": "beam_pipe_radius",
            "value_mm": 50.0,
            "review_note": "从图 4 手工补录",
        },
    )

    assert item["origin"] == "manual_overlay"
    assert item["human_review_status"] == "pending"
    assert session["review_decisions"][item["id"]]["status"] == "pending"
    assert event["event_type"] == "manual_item_added"
    assert session["revision"] == 1

    _, reviewed = store.record_review_event(
        expected_revision=1,
        item_id=item["id"],
        status="accepted_as_soft_only",
        review_note="可用于预览，不进入硬约束。",
    )
    assert reviewed["manual_items"][0]["human_review_status"] == "accepted_as_soft_only"
    assert reviewed["revision"] == 2
    assert len(store.events_path.read_text(encoding="utf-8").splitlines()) == 2
    assert ReviewSessionStore(store.session_root).get_session() == reviewed


@pytest.mark.parametrize("bad_section", [None, "geometry", "UDSG"])
def test_manual_item_rejects_non_semantic_section(tmp_path, bad_section):
    store = ReviewSessionStore(tmp_path / "review")

    with pytest.raises(ReviewSessionError, match="item.section"):
        store.add_manual_item(
            expected_revision=0,
            item={"id": "manual:bad", "section": bad_section},
        )


def test_manual_item_cannot_arrive_preaccepted_or_duplicate(tmp_path):
    store = ReviewSessionStore(tmp_path / "review")

    with pytest.raises(ReviewSessionError, match="must start with pending"):
        store.add_manual_item(
            expected_revision=0,
            item={
                "id": "manual:premature",
                "section": "shape_motifs",
                "human_review_status": "accepted",
            },
        )

    store.add_manual_item(
        expected_revision=0,
        item={"id": "manual:same", "section": "shape_motifs"},
    )
    with pytest.raises(ReviewSessionError, match="already exists"):
        store.add_manual_item(
            expected_revision=1,
            item={"id": "manual:same", "section": "shape_motifs"},
        )


def test_store_persists_namespaced_helper2_review(tmp_path):
    store = ReviewSessionStore(tmp_path / "review")
    review = {
        "schema_version": "helper2_review_session.v1",
        "active_tab": "udsg",
        "selected_faces": ["F0004"],
        "geometry": {"F0004": {"status": "accepted"}},
        "candidates": {
            "equator": {
                "status": "modified",
                "type": "EquatorRegion",
                "geometry_refs": ["face:F0004"],
            }
        },
        "bindings": {
            "binding-equator": {
                "status": "accepted",
                "feature_id": "equator",
                "geometry_node_id": "face:F0004",
                "deleted": False,
            }
        },
        "manual_groups": {},
        "notes": "赤道面已人工确认。",
    }

    event, session = store.record_helper2_review(
        expected_revision=0,
        projection_id="sls2.cavity.1",
        review=review,
    )

    assert event["event_type"] == "helper2_review_saved"
    assert event["review_sha256"].startswith("sha256:")
    assert event["review"]["selected_faces"] == ["F0004"]
    saved = session["helper2_reviews"]["sls2.cavity.1"]["review"]
    assert saved["active_tab"] == "udsg"
    assert saved["bindings"]["binding-equator"]["status"] == "accepted"
    assert ReviewSessionStore(store.session_root).get_session() == session

    invalid = copy.deepcopy(review)
    invalid["bindings"]["binding-equator"]["deleted"] = "false"
    with pytest.raises(ReviewSessionError, match="must be a boolean"):
        store.record_helper2_review(
            expected_revision=1,
            projection_id="sls2.cavity.1",
            review=invalid,
        )


def test_server_is_loopback_token_protected_and_has_no_cors(tmp_path):
    store = ReviewSessionStore(tmp_path / "review")
    with ReviewServer(store, token=TOKEN) as server:
        assert server.host == "127.0.0.1"
        assert server.base_url == f"http://127.0.0.1:{server.port}"
        assert server.api_headers == {"X-Review-Token": TOKEN}

        status, payload, headers = _request(server, "GET", "/api/session")
        assert status == 200
        assert payload["session"]["revision"] == 0
        assert "access-control-allow-origin" not in headers

        status, payload, _ = _request(
            server, "GET", "/api/session", include_token=False
        )
        assert status == 403
        assert payload["error"]["code"] == "forbidden"

        status, payload, _ = _request(
            server,
            "GET",
            "/api/session",
            extra_headers={"Origin": "https://attacker.example"},
        )
        assert status == 403
        assert payload["error"]["code"] == "invalid_origin"

        status, payload, _ = _request(
            server,
            "GET",
            "/api/session",
            extra_headers={"Host": "attacker.example"},
        )
        assert status == 403
        assert payload["error"]["code"] == "invalid_host"

        status, payload, headers = _request(
            server,
            "OPTIONS",
            "/api/session",
            include_token=False,
            extra_headers={"Origin": "https://attacker.example"},
        )
        assert status == 405
        assert payload["error"]["code"] == "method_not_allowed"
        assert "access-control-allow-origin" not in headers


def test_server_serves_only_injected_pdf_and_persists_helper2(tmp_path):
    store = ReviewSessionStore(tmp_path / "review")
    pdf = b"%PDF-1.4\n%%EOF\n"
    with ReviewServer(store, token=TOKEN, paper_document=pdf) as server:
        connection = http.client.HTTPConnection(server.host, server.port, timeout=5)
        try:
            connection.request(
                "GET",
                "/api/paper-source",
                headers={"X-Review-Token": TOKEN},
            )
            response = connection.getresponse()
            body = response.read()
            headers = {name.lower(): value for name, value in response.getheaders()}
        finally:
            connection.close()
        assert response.status == 200
        assert body == pdf
        assert headers["content-type"] == "application/pdf"
        assert headers["content-disposition"].startswith("inline")

        status, payload, _ = _request(
            server,
            "POST",
            "/api/helper2-review",
            body={
                "expected_revision": 0,
                "projection_id": "candidate-1",
                "review": {
                    "active_tab": "geometry",
                    "selected_faces": [],
                    "geometry": {},
                    "candidates": {},
                    "bindings": {},
                    "manual_groups": {},
                    "notes": "",
                },
            },
        )
        assert status == 200
        assert payload["session"]["revision"] == 1
        assert "candidate-1" in payload["session"]["helper2_reviews"]


def test_injected_review_html_is_served_same_origin_with_query_token_only(tmp_path):
    store = ReviewSessionStore(tmp_path / "review")
    review_html = "<!doctype html><meta charset='utf-8'><title>三层语义审核</title>"
    with ReviewServer(
        store,
        token=TOKEN,
        review_html=review_html,
        review_path="/review",
    ) as server:
        assert server.review_url is not None
        parsed = urlsplit(server.review_url)
        assert parsed.path == "/review"
        assert parsed.query.startswith("token=")

        connection = http.client.HTTPConnection(server.host, server.port, timeout=5)
        try:
            connection.request("GET", f"{parsed.path}?{parsed.query}")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            headers = {
                name.lower(): value for name, value in response.getheaders()
            }
        finally:
            connection.close()
        assert response.status == 200
        assert body == review_html
        assert headers["content-type"] == "text/html; charset=utf-8"
        assert headers["cache-control"] == "no-store"
        assert headers["referrer-policy"] == "no-referrer"
        assert "access-control-allow-origin" not in headers

        status, payload, _ = _request(
            server,
            "GET",
            "/api/session",
            extra_headers={"Origin": server.base_url},
        )
        assert status == 200
        assert payload["session"]["revision"] == 0

        # A header token cannot replace the initial-document URL gate.
        status, payload, _ = _request(server, "GET", "/review")
        assert status == 403
        assert payload["error"]["code"] == "forbidden"

        # Conversely, an API endpoint never accepts its token from the query.
        status, payload, _ = _request(
            server,
            "GET",
            f"/api/session?{parsed.query}",
            include_token=False,
        )
        assert status == 403
        assert payload["error"]["code"] == "forbidden"


def test_http_review_manual_and_preview_flow_uses_one_revision(tmp_path):
    store = ReviewSessionStore(tmp_path / "review", initial_session={"paper_id": "sls2"})
    callback_calls = []

    def preview_callback(session, request):
        callback_calls.append((session, request))
        return {
            "profile": [[50.0, -340.0], [249.901, 0.0]],
            "Geometry": {"kernel_verified": False},
            "Features": ["equator ellipse"],
            "UDSG": {"candidate": "SLS-2 #1"},
        }

    with ReviewServer(
        store, preview_callback=preview_callback, token=TOKEN
    ) as server:
        status, payload, _ = _request(
            server,
            "POST",
            "/api/review-events",
            body={
                "expected_revision": 0,
                "item_id": "sls2:shape",
                "status": "accepted",
                "review_note": "可生成第一版轮廓",
            },
        )
        assert status == 200
        assert payload["session"]["revision"] == 1

        status, payload, _ = _request(
            server,
            "POST",
            "/api/manual-items",
            body={
                "expected_revision": 1,
                "item": {
                    "section": "physical_constraints",
                    "constraint": "axisymmetric",
                    "review_note": "人工补充",
                },
            },
        )
        assert status == 201
        assert payload["item"]["id"].startswith("manual:")
        assert payload["item"]["human_review_status"] == "pending"
        assert payload["session"]["revision"] == 2

        status, payload, _ = _request(
            server,
            "POST",
            "/api/preview",
            body={
                "expected_revision": 2,
                "candidate_id": "sls2-candidate-1",
                "parameters": {"Req_mm": 249.901},
            },
        )
        assert status == 200
        assert payload["revision"] == 2
        assert payload["preview"]["UDSG"]["candidate"] == "SLS-2 #1"
        assert callback_calls[0][0]["paper_id"] == "sls2"
        assert "expected_revision" not in callback_calls[0][1]
        assert callback_calls[0][1]["parameters"]["Req_mm"] == 249.901
        assert store.get_session()["revision"] == 2


def test_http_stale_revision_returns_current_revision_without_mutation(tmp_path):
    store = ReviewSessionStore(tmp_path / "review")
    store.record_review_event(
        expected_revision=0, item_id="first", status="accepted"
    )

    with ReviewServer(store, token=TOKEN) as server:
        status, payload, _ = _request(
            server,
            "POST",
            "/api/review-events",
            body={
                "expected_revision": 0,
                "item_id": "stale",
                "status": "rejected",
            },
        )

    assert status == 409
    assert payload["error"]["code"] == "revision_conflict"
    assert payload["error"]["current_revision"] == 1
    assert "stale" not in store.get_session()["review_decisions"]
    assert len(store.events_path.read_text(encoding="utf-8").splitlines()) == 1


def test_preview_requires_callback_and_matching_revision(tmp_path):
    store = ReviewSessionStore(tmp_path / "review")
    with ReviewServer(store, token=TOKEN) as server:
        status, payload, _ = _request(
            server,
            "POST",
            "/api/preview",
            body={"expected_revision": 0},
        )

    assert status == 503
    assert payload["error"]["code"] == "preview_unavailable"


def test_http_enforces_json_and_request_size(tmp_path):
    store = ReviewSessionStore(tmp_path / "review")
    with ReviewServer(store, token=TOKEN, max_request_bytes=80) as server:
        status, payload, _ = _raw_request(
            server,
            "POST",
            "/api/review-events",
            payload=b"not-json",
            content_type="text/plain",
        )
        assert status == 415
        assert payload["error"]["code"] == "unsupported_media_type"

        status, payload, _ = _raw_request(
            server,
            "POST",
            "/api/review-events",
            payload=json.dumps(
                {
                    "expected_revision": 0,
                    "item_id": "x" * 100,
                    "status": "pending",
                }
            ).encode("utf-8"),
        )
        assert status == 413
        assert payload["error"]["code"] == "request_too_large"


def test_session_files_cannot_follow_symlinks_outside_root(tmp_path):
    root = tmp_path / "review"
    root.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text("do not touch\n", encoding="utf-8")
    link = root / "review_events.jsonl"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this Windows configuration")

    with pytest.raises(ReviewSessionError, match="outside session root"):
        ReviewSessionStore(root)
    assert outside.read_text(encoding="utf-8") == "do not touch\n"


def _request(
    server: ReviewServer,
    method: str,
    path: str,
    *,
    body: Optional[dict[str, Any]] = None,
    include_token: bool = True,
    extra_headers: Optional[dict[str, str]] = None,
):
    payload = None
    headers = dict(extra_headers or {})
    if include_token:
        headers["X-Review-Token"] = TOKEN
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    return _exchange(server, method, path, payload, headers)


def _raw_request(
    server: ReviewServer,
    method: str,
    path: str,
    *,
    payload: bytes,
    content_type: str = "application/json",
):
    return _exchange(
        server,
        method,
        path,
        payload,
        {"X-Review-Token": TOKEN, "Content-Type": content_type},
    )


def _exchange(
    server: ReviewServer,
    method: str,
    path: str,
    payload: Optional[bytes],
    headers: dict[str, str],
):
    connection = http.client.HTTPConnection(server.host, server.port, timeout=5)
    try:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        response_headers = {name.lower(): value for name, value in response.getheaders()}
        return response.status, json.loads(raw.decode("utf-8")), response_headers
    finally:
        connection.close()
