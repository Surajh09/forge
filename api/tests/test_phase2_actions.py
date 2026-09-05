"""Phase 2 slice 1: agent principals, scope enforcement, idempotency, checkpoint, audit, grants, MCP writes."""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from mcp.server.auth.provider import AccessToken


from app import context_actions, oauth, services
from app.access import ALL_SCOPES, SCOPE_CONTEXT_READ, Principal, feature_access
from app.auth import get_principal
from app.main import app
from app.schemas import ContextContract, Decision, SessionCheckpoint, SessionComplete
from tests.conftest import agent

CONTRACT = ContextContract(
    objective="Add refresh-token rotation",
    changes=["Added rotation", "Updated middleware"],
    decisions=[Decision(decision="Rotation happens server-side", reason="Prevents token reuse")],
    affected_components=["auth/middleware.py"],
    constraints=["Mobile clients must remain compatible"],
    known_issues=["Old clients lack family revocation"],
    open_questions=["When should families expire?"],
    confidence=0.9,
)  # fans out to 5 entries: change, decision, constraint, known_issue, open_question


# --- pure access rules ---------------------------------------------------------


def test_allow_list_narrows_even_an_admin():
    narrowed = Principal(
        user_id="u", org_id="o", role="admin", principal_type="agent",
        scopes=frozenset(ALL_SCOPES), feature_ids=frozenset({"f1"}),
    )
    assert feature_access(narrowed, feature_team_ids=[], my_team_ids=[], assignee_ids=[], feature_id="f1") == "admin"
    assert feature_access(narrowed, feature_team_ids=[], my_team_ids=[], assignee_ids=[], feature_id="f2") is None


def test_no_allow_list_means_no_narrowing():
    p = Principal(user_id="u", org_id="o", role="developer", principal_type="agent", scopes=frozenset(ALL_SCOPES))
    assert feature_access(p, feature_team_ids=["t"], my_team_ids=["t"], assignee_ids=[], feature_id="anything") == "team"


def test_users_hold_all_scopes_and_agents_only_granted():
    user = Principal(user_id="u", org_id="o", role="developer")
    assert all(user.has_scope(s) for s in ALL_SCOPES)
    ro = agent(user, scopes=[SCOPE_CONTEXT_READ])
    assert ro.has_scope("context.read") and not ro.has_scope("context.write")


def test_agent_role_is_capped_at_developer_regardless_of_creator():
    tok = AccessToken(
        token="forge_at_x", client_id="c", scopes=list(ALL_SCOPES), expires_at=None, resource=None,
        subject="grant_1", claims={"org_id": "o", "user_id": "user_admin", "feature_ids": None, "client_name": "cc"},
    )
    p = oauth.principal_from_access_token(tok)
    assert p.role == "developer" and p.is_agent and not p.is_admin
    assert p.credential_id == "grant_1" and p.client_name == "cc"


# --- scope enforcement at the service layer -------------------------------------


def test_read_only_agent_cannot_record_and_denial_is_audited(world, infra):
    with pytest.raises(HTTPException) as exc:
        context_actions.record_context(
            world["agent_ro"], world["payment"]["id"], kind="decision", title="x", payload={"decision": "x"}
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "SCOPE_REQUIRED"
    denied = infra.audit_rows(action="context.record_context", outcome="denied")
    assert denied and denied[0]["authorization_result"] == "deny:SCOPE_REQUIRED"
    assert denied[0]["principal_type"] == "agent" and denied[0]["credential_id"] == "grant_ro"
    assert world["store"].entries == []


def test_read_only_agent_can_read(world):
    _payload, rows = context_actions.get_feature_context(world["agent_ro"], world["payment"]["id"])
    assert rows == []  # no context yet, but the call is allowed


def test_narrowed_agent_is_confined_to_its_allow_list(world, infra):
    # alice is directly assigned to LOGIN, but the credential only allows PAYMENT.
    with pytest.raises(HTTPException) as exc:
        context_actions.get_feature_context(world["agent_narrow"], world["login"]["id"])
    assert exc.value.status_code == 403
    assert infra.audit_rows(action="context.get_feature_context", outcome="denied")
    context_actions.get_feature_context(world["agent_narrow"], world["payment"]["id"])  # allowed


# --- idempotency ----------------------------------------------------------------


def test_record_with_request_id_replays_instead_of_duplicating(world, infra):
    p = world["agent_rw"]
    kwargs = dict(kind="constraint", title="Amounts are minor units", payload={"constraint": "minor units"}, request_id="req-1")
    first = context_actions.record_context(p, world["payment"]["id"], **kwargs)
    second = context_actions.record_context(p, world["payment"]["id"], **kwargs)
    assert first["id"] == second["id"]
    assert len(world["store"].entries) == 1
    assert infra.audit_rows(action="context.record_context", outcome="replayed")


def test_supersede_with_request_id_replays(world):
    p = world["agent_rw"]
    original = context_actions.record_context(p, world["payment"]["id"], kind="decision", title="v1", payload={"decision": "v1"})
    a = context_actions.supersede_context(p, original["id"], title="v2", payload={"decision": "v2"}, request_id="req-2")
    b = context_actions.supersede_context(p, original["id"], title="v2", payload={"decision": "v2"}, request_id="req-2")
    assert a["id"] == b["id"] and a["version"] == 2
    assert len(world["store"].entries) == 2  # v1 (superseded) + v2, not v3


def test_evidence_is_stored_apart_from_the_payload(world):
    p = world["agent_rw"]
    created = context_actions.record_context(
        p, world["payment"]["id"], kind="decision", title="Idempotency keys", payload={"decision": "Use keys"},
        evidence={"files": ["payment_service.py"], "tests": ["test_payment_retry"], "commit": "91af"},
    )
    stored = world["store"].entries[-1]
    assert stored["evidence"]["files"] == ["payment_service.py"]
    assert "files" not in created["payload"]


# --- checkpoint ------------------------------------------------------------------


def test_checkpoint_writes_entries_and_keeps_the_session_active(world, infra):
    store, p = world["store"], world["agent_rw"]
    session = store.add_session(world["payment"], p.user_id)
    result = services.checkpoint_session(p, session, SessionCheckpoint(context=CONTRACT, request_id="cp-1"))
    assert len(result.context_entries) == 5
    assert not result.quarantined and not result.idempotent_replay
    live = next(s for s in store.sessions if s["id"] == session["id"])
    assert live["status"] == "active" and live["context_version"] == 1 and live["ended_at"] is None
    assert all(e.session_id == session["id"] for e in result.context_entries)
    assert infra.audit_rows(action="session.checkpoint", outcome="ok")

    replay = services.checkpoint_session(p, live, SessionCheckpoint(context=CONTRACT, request_id="cp-1"))
    assert replay.idempotent_replay and len(store.entries) == 5

    done = services.complete_session(p, live, SessionComplete(context=CONTRACT))
    assert done.session.status == "completed" and len(store.entries) == 10


def test_checkpoint_rejects_a_closed_session(world):
    store, p = world["store"], world["agent_rw"]
    session = store.add_session(world["payment"], p.user_id, status="completed")
    with pytest.raises(HTTPException) as exc:
        services.checkpoint_session(p, session, SessionCheckpoint(context=CONTRACT))
    assert exc.value.detail["code"] == "SESSION_NOT_ACTIVE"


def test_reads_and_session_start_are_audited(world, infra):
    p = world["agent_rw"]
    row = services.start_session(p, world["payment"]["id"], agent="claude-code", model=None, goal="g")
    context_actions.get_feature_context(p, world["payment"]["id"])
    assert infra.audit_rows(action="session.start", outcome="ok")[0]["session_id"] == row["id"]
    read = infra.audit_rows(action="context.get_feature_context", outcome="ok")[0]
    assert read["credential_id"] == "grant_rw" and read["principal_id"] == "user_alice"


# --- scope enforcement over REST (the audit-found gap) -------------------------------


@pytest.fixture
def rest(http, world):
    """The shared client, with `get_principal` overridden per test."""

    def as_principal(p: Principal):
        app.dependency_overrides[get_principal] = lambda: p
        return http

    try:
        yield as_principal
    finally:
        app.dependency_overrides.clear()


def test_read_only_grant_cannot_write_over_rest(world, rest):
    c = rest(world["agent_ro"])
    assert c.get("/api/v1/features").status_code == 200
    r = c.post("/api/v1/sessions", json={"feature_id": world["payment"]["id"], "goal": "g"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "SCOPE_REQUIRED"

    entry = context_actions.record_context(world["alice"], world["payment"]["id"], kind="decision", title="t", payload={"decision": "t"})
    r = c.patch(f"/api/v1/context/{entry['id']}", json={"title": "changed"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "SCOPE_REQUIRED"


def test_full_grant_can_write_over_rest_and_checkpoint(world, rest):
    c = rest(world["agent_rw"])
    created = c.post("/api/v1/sessions", json={"feature_id": world["payment"]["id"], "goal": "g"})
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    cp = c.post(f"/api/v1/sessions/{sid}/checkpoint", json={"context": CONTRACT.model_dump(), "request_id": "r1"})
    assert cp.status_code == 200 and cp.json()["session"]["status"] == "active"
    assert len(cp.json()["context_entries"]) == 5
    entry_id = cp.json()["context_entries"][0]["id"]
    revised = c.patch(f"/api/v1/context/{entry_id}", json={"title": "revised", "request_id": "r2"})
    assert revised.status_code == 200 and revised.json()["version"] == 2
    again = c.patch(f"/api/v1/context/{entry_id}", json={"title": "revised", "request_id": "r2"})
    assert again.json()["id"] == revised.json()["id"]


def test_unknown_api_path_keeps_forge_error_envelope(world, rest):
    r = rest(world["alice"]).get("/api/v1/does-not-exist")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "NOT_FOUND"


# --- grants: list, revoke, and the MCP write tools end to end ------------------------


def _pkce():
    verifier = "v" * 48
    return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def _oauth_token(client, *, scope: str, feature_ids=None) -> tuple[str, dict]:
    registered = client.post(
        "/register",
        json={
            "client_name": "Claude Code (test)", "redirect_uris": ["http://localhost:3001/callback"],
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
            "token_endpoint_auth_method": "none", "scope": scope,
        },
    )
    assert registered.status_code == 201, registered.text
    info = registered.json()
    verifier, challenge = _pkce()
    authorize = client.get(
        "/authorize",
        params={
            "response_type": "code", "client_id": info["client_id"], "redirect_uri": "http://localhost:3001/callback",
            "code_challenge": challenge, "code_challenge_method": "S256", "scope": scope, "state": "s",
            "resource": "http://localhost:8000/mcp",
        },
        follow_redirects=False,
    )
    txn = parse_qs(urlparse(authorize.headers["location"]).query)["txn"][0]
    approved = client.post(f"/api/v1/oauth/consents/{txn}/approve", json={"feature_ids": feature_ids})
    assert approved.status_code == 200, approved.text
    code = parse_qs(urlparse(approved.json()["redirect_url"]).query)["code"][0]
    token = client.post(
        "/token",
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": "http://localhost:3001/callback",
              "client_id": info["client_id"], "code_verifier": verifier},
    )
    assert token.status_code == 200, token.text
    return token.json()["access_token"], info


def _mcp(client, headers, name, arguments, rid):
    r = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_grants_are_listed_and_revocation_kills_live_tokens(world, oauth_repo, infra, rest):
    c = rest(world["alice"])
    token, _info = _oauth_token(c, scope="context.read")
    assert oauth.principal_for_bearer(token) is not None

    grants = c.get("/api/v1/oauth/grants").json()
    assert len(grants) == 1 and grants[0]["scopes"] == ["context.read"] and grants[0]["status"] == "active"
    assert grants[0]["creator"]["display_name"] == "Alice"

    assert c.delete(f"/api/v1/oauth/grants/{grants[0]['id']}").status_code == 204
    assert oauth.principal_for_bearer(token) is None, "revoking the grant must kill its tokens"
    assert c.get("/api/v1/oauth/grants").json()[0]["status"] == "revoked"
    assert infra.audit_rows(action="oauth.grant.revoke", outcome="ok")


def test_agent_cannot_manage_credentials(world, oauth_repo, rest):
    r = rest(world["agent_rw"]).get("/api/v1/oauth/grants")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "HUMAN_REQUIRED"


def test_mcp_write_tools_complete_the_loop(world, oauth_repo, infra, rest):
    """§21: an agent starts a session, records, checkpoints, supersedes, completes — and a later read sees it."""
    store = world["store"]
    c = rest(world["alice"])
    token, _ = _oauth_token(c, scope=" ".join(ALL_SCOPES))
    headers = {"authorization": f"Bearer {token}", "accept": "application/json"}
    init = c.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
    headers["mcp-protocol-version"] = init.json()["result"]["protocolVersion"]

    # Features are addressed by key.
    feat = _mcp(c, headers, "forge_feature_get", {"feature": "payment"}, 1)["structuredContent"]
    assert feat["key"] == "PAYMENT"

    sid = _mcp(c, headers, "forge_session_start", {"feature": "PAYMENT", "goal": "Retry policy"}, 2)["structuredContent"]["id"]

    rec = _mcp(c, headers, "forge_context_record", {
        "feature": "PAYMENT", "kind": "decision", "title": "Payment retries use idempotency keys",
        "payload": {"decision": "Payment retries use idempotency keys", "reason": "Safe retries"},
        "session_id": sid, "confidence": 0.9, "request_id": "mcp-1",
        "evidence": {"files": ["payment_service.py"], "tests": ["test_payment_retry"]},
    }, 3)
    assert rec.get("isError") is not True, rec
    n_after_first = len(store.entries)
    _mcp(c, headers, "forge_context_record", {
        "feature": "PAYMENT", "kind": "decision", "title": "Payment retries use idempotency keys",
        "payload": {"decision": "Payment retries use idempotency keys"}, "session_id": sid, "request_id": "mcp-1",
    }, 4)
    assert len(store.entries) == n_after_first, "same request_id must not duplicate"

    cp = _mcp(c, headers, "forge_session_checkpoint", {"session_id": sid, "contract": CONTRACT.model_dump(), "request_id": "mcp-cp"}, 5)
    assert "checkpoint: ok" in cp["content"][0]["text"]
    assert next(s for s in store.sessions if s["id"] == sid)["status"] == "active"

    decision_id = next(e["id"] for e in store.entries if e["kind"] == "decision" and e["status"] == "active" and e["title"].startswith("Payment retries"))
    sup = _mcp(c, headers, "forge_context_supersede", {"entry_id": decision_id, "title": "Payment retries use idempotency keys per charge", "payload": {"decision": "per charge"}, "session_id": sid}, 6)
    assert sup.get("isError") is not True, sup

    done = _mcp(c, headers, "forge_session_complete", {"session_id": sid, "contract": CONTRACT.model_dump(), "summary": "done"}, 7)
    assert "session: completed" in done["content"][0]["text"]

    # A "second session" reads what the first left behind.
    found = _mcp(c, headers, "forge_context_search", {"query": "idempotency keys per charge"}, 8)["content"][0]["text"]
    assert "per charge" in found
    ctx = _mcp(c, headers, "forge_context_get", {"feature": "PAYMENT", "kinds": ["decision"]}, 9)["content"][0]["text"]
    assert "Payment retries use idempotency keys per charge" in ctx

    # Bad input is a readable tool error, not a stack trace.
    bad = _mcp(c, headers, "forge_context_record", {"feature": "NOPE", "kind": "decision", "title": "t", "payload": {}}, 10)
    assert bad["isError"] is True and "No feature with key 'NOPE'" in bad["content"][0]["text"]

    actions = {r["action"] for r in infra.audit if r["principal_type"] == "agent"}
    assert {"session.start", "context.record_context", "session.checkpoint", "context.supersede_context", "session.complete"} <= actions
