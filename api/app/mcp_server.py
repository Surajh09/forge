"""Forge MCP server (phase-2 §3.2, §13).

The standardized agent-facing boundary: eight focused tools over the same
services and access rules the REST API uses. No rule is restated here — each
tool resolves the bearer token into a Principal, requires the tool's scope,
and delegates. TOON is the representation of context; MCP messages stay MCP.

Served over streamable HTTP from the FastAPI app (mounted in app/main.py) and
protected by Forge's own OAuth authorization server (app/oauth.py).
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from app import context_actions, services
from app.access import (
    ALL_SCOPES,
    SCOPE_CONTEXT_READ,
    SCOPE_CONTEXT_SUPERSEDE,
    SCOPE_CONTEXT_WRITE,
    SCOPE_SESSION_WRITE,
    Principal,
)
from app.audit import record_audit
from app.config import get_settings
from app.oauth import ForgeOAuthProvider, principal_for_bearer
from app.repos import features as features_repo
from app.repos import sessions as sessions_repo
from app.schemas import ContextContract, Evidence, SessionCheckpoint, SessionComplete
from app.toon_codec import entries_to_toon_document

# A feature key is a bare word like PAYMENT or DOCUMENT_PROCESSING — no dashes,
# which is what distinguishes it from an id.
_KEY_SHAPED = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

INSTRUCTIONS = """Forge is the shared engineering Context Bank for this organization.

Before independent investigation of a feature, call forge_context_get (or
forge_context_search) for that feature and use what is relevant. Features are
addressed by key, e.g. PAYMENT. If context is missing or insufficient, do local
discovery, then contribute durable knowledge back: start a session with
forge_session_start, record statements with forge_context_record, checkpoint
with forge_session_checkpoint before compaction, and forge_session_complete
when done. Record durable engineering statements — decisions, constraints,
known issues, open questions — never raw transcripts or temporary
observations. If existing context is contradicted by what you find, use
forge_context_supersede rather than recording a competing statement."""

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE_IDEMPOTENT = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


# --- plumbing ----------------------------------------------------------------


def _principal(scope: str) -> Principal:
    """Resolve the SDK-authenticated bearer into a Forge Principal and require a scope."""
    token = get_access_token()
    p = principal_for_bearer(token.token) if token else None
    if not p:
        raise ToolError("Agent credential is invalid, expired, or revoked. Re-authenticate with Forge.")
    if not p.has_scope(scope):
        record_audit(p, "mcp.tool", "denied", authorization_result=f"deny:scope:{scope}")
        raise ToolError(f"This action requires the '{scope}' scope; the credential was not granted it.")
    return p


def _message(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return f"{detail.get('code', 'ERROR')}: {detail.get('message', '')}"
    return str(detail)


def _feature_id(p: Principal, feature: str) -> str:
    """Accept a feature key (PAYMENT) or a feature id.

    Keys are tried first because that is what an agent naturally has. Anything
    that is not a known key and does not look like a key is passed through as an
    id, so `load_feature` can answer with the proper 404/403.
    """
    ref = feature.strip()
    row = features_repo.get_feature_by_key(p.org_id, ref.upper())
    if row:
        return row["id"]
    if _KEY_SHAPED.match(ref):
        raise ToolError(
            f"No feature with key '{ref.upper()}' in this organization. "
            "Call forge_feature_get with a valid key, or pass a feature id."
        )
    return ref


def _contract(data: dict[str, Any] | None) -> ContextContract | None:
    if data is None:
        return None
    try:
        return ContextContract.model_validate(data)
    except ValidationError as exc:
        raise ToolError(f"Context contract is invalid: {exc.errors()[0]['msg']} at {'.'.join(str(x) for x in exc.errors()[0]['loc'])}") from exc


def _evidence(data: dict[str, Any] | None) -> Evidence | None:
    if data is None:
        return None
    try:
        return Evidence.model_validate(data)
    except ValidationError as exc:
        raise ToolError(f"Evidence is invalid: {exc.errors()[0]['msg']}") from exc


def _session_row(p: Principal, session_id: str) -> dict:
    row = sessions_repo.get_session(p.org_id, session_id)
    if not row or row["user_id"] != p.user_id:
        raise ToolError("Session not found, or it was not started by this credential's user.")
    return row


def _entries_doc(rows: list[dict], *, feature: dict | None, query: dict) -> str:
    return entries_to_toon_document(rows, feature=feature, query=query)


def _session_summary(row: dict) -> dict[str, Any]:
    return {
        "id": row["id"],
        "feature_id": row["feature_id"],
        "status": row["status"],
        "goal": row.get("goal"),
        "agent": row.get("agent"),
        "model": row.get("model"),
        "context_version": row.get("context_version", 0),
        "started_at": str(row.get("started_at")),
        "ended_at": str(row["ended_at"]) if row.get("ended_at") else None,
    }


def build_mcp_server() -> MCPServer[Any]:
    settings = get_settings()
    server = MCPServer(
        "forge",
        title="Forge Context Bank",
        description="Feature-scoped engineering context for coding agents: retrieve, record, supersede.",
        instructions=INSTRUCTIONS,
        version="0.3.0",
        auth_server_provider=ForgeOAuthProvider(),
        auth=AuthSettings(
            issuer_url=settings.forge_public_url,
            resource_server_url=settings.mcp_resource_url,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=list(ALL_SCOPES),
                # Clients such as Claude Code omit `scope` and rely on the
                # server's default. An empty default made every connection fail
                # with invalid_scope. The default asks for the full set; least
                # privilege is exercised by the human on the consent screen,
                # who ticks the scopes and may restrict features (§5.1).
                default_scopes=list(ALL_SCOPES),
            ),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )

    # --- read actions ---------------------------------------------------------

    @server.tool(
        name="forge_feature_get",
        description="Resolve a Forge feature by key (e.g. PAYMENT) or id and confirm you are authorized on it. Returns its metadata and why you have access.",
        annotations=READ,
    )
    def forge_feature_get(feature: str) -> dict[str, Any]:
        p = _principal(SCOPE_CONTEXT_READ)
        try:
            ctx = services.load_feature(p, _feature_id(p, feature))
        except HTTPException as exc:
            raise ToolError(_message(exc)) from exc
        f = ctx.feature
        return {
            "id": f["id"],
            "key": f["key"],
            "name": f["name"],
            "description": f.get("description"),
            "status": f["status"],
            "access_reason": ctx.reason,
        }

    @server.tool(
        name="forge_context_get",
        description=(
            "Get the active, authorized Context Bank for one feature as a TOON document. Each statement carries "
            "its kind, version, confidence, source session and author. Optionally filter by kinds "
            "(decision, constraint, architecture, change, known_issue, open_question) and include pending-review entries."
        ),
        annotations=READ,
    )
    def forge_context_get(feature: str, kinds: list[str] | None = None, include_pending: bool = False) -> str:
        p = _principal(SCOPE_CONTEXT_READ)
        statuses = ("active", "pending_review") if include_pending else ("active",)
        try:
            fid = _feature_id(p, feature)
            if kinds:
                payload, rows = context_actions.get_context_by_kind(p, fid, kinds, statuses=statuses)
            else:
                payload, rows = context_actions.get_feature_context(p, fid, statuses=statuses)
        except HTTPException as exc:
            raise ToolError(_message(exc)) from exc
        return _entries_doc(rows, feature=payload.get("feature"), query=payload.get("query") or {})

    @server.tool(
        name="forge_context_search",
        description=(
            "Search Context Bank titles and payloads across every feature you can access (or one feature). "
            "Plain-text matching, not semantic. Returns matching statements as TOON with provenance."
        ),
        annotations=READ,
    )
    def forge_context_search(query: str, feature: str | None = None, kinds: list[str] | None = None, limit: int = 25) -> str:
        p = _principal(SCOPE_CONTEXT_READ)
        try:
            fid = _feature_id(p, feature) if feature else None
            payload, rows = context_actions.search_context(p, query, feature_id=fid, kinds=kinds, limit=max(1, min(limit, 100)))
        except HTTPException as exc:
            raise ToolError(_message(exc)) from exc
        return _entries_doc(rows, feature=payload.get("feature"), query=payload.get("query") or {})

    # --- context actions ------------------------------------------------------

    @server.tool(
        name="forge_context_record",
        description=(
            "Record one durable engineering statement for a feature: a decision, constraint, architecture note, "
            "change, known_issue or open_question. Give a short quotable title and a payload with the statement "
            "(and a reason for decisions). Link the session it came from. Pass the same request_id on retries; "
            "the first result is returned instead of a duplicate. Do not record raw transcripts or temporary observations."
        ),
        annotations=WRITE_IDEMPOTENT,
    )
    def forge_context_record(
        feature: str,
        kind: str,
        title: str,
        payload: dict[str, Any],
        confidence: float | None = None,
        session_id: str | None = None,
        evidence: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> str:
        p = _principal(SCOPE_CONTEXT_WRITE)
        ev = _evidence(evidence)
        try:
            fid = _feature_id(p, feature)
            created = context_actions.record_context(
                p, fid, kind=kind, title=title, payload=payload, confidence=confidence, session_id=session_id,
                evidence=ev.model_dump(exclude_none=True) if ev else None, request_id=request_id,
            )
            feature_row = services.load_feature(p, fid).feature
        except HTTPException as exc:
            raise ToolError(_message(exc)) from exc
        return _entries_doc([created], feature=feature_row, query={"action": "record_context"})

    @server.tool(
        name="forge_context_supersede",
        description=(
            "Replace an existing statement with a newer version when what you found contradicts it. The old "
            "version is kept and marked superseded; nothing is deleted. Use the entry id from forge_context_get. "
            "Pass the same request_id on retries."
        ),
        annotations=WRITE_IDEMPOTENT,
    )
    def forge_context_supersede(
        entry_id: str,
        title: str,
        payload: dict[str, Any],
        confidence: float | None = None,
        session_id: str | None = None,
        evidence: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> str:
        p = _principal(SCOPE_CONTEXT_SUPERSEDE)
        ev = _evidence(evidence)
        try:
            created = context_actions.supersede_context(
                p, entry_id, title=title, payload=payload, confidence=confidence, session_id=session_id,
                evidence=ev.model_dump(exclude_none=True) if ev else None, request_id=request_id,
            )
        except HTTPException as exc:
            raise ToolError(_message(exc)) from exc
        return _entries_doc([created], feature=None, query={"action": "supersede_context", "superseded": entry_id})

    # --- session actions ------------------------------------------------------

    @server.tool(
        name="forge_session_start",
        description=(
            "Start a Forge session for a feature before doing engineering work on it. Returns the session id to "
            "pass to forge_context_record, forge_session_checkpoint and forge_session_complete."
        ),
        annotations=WRITE,
    )
    def forge_session_start(feature: str, goal: str, agent: str = "claude-code", model: str | None = None) -> dict[str, Any]:
        p = _principal(SCOPE_SESSION_WRITE)
        try:
            row = services.start_session(p, _feature_id(p, feature), agent=agent or (p.client_name or "agent"), model=model, goal=goal)
        except HTTPException as exc:
            raise ToolError(_message(exc)) from exc
        return _session_summary(row)

    @server.tool(
        name="forge_session_checkpoint",
        description=(
            "Preserve durable knowledge mid-session (for example before context compaction) without ending the "
            "session. Supply a Context Contract: objective, changes, decisions [{decision, reason}], "
            "affected_components, constraints, dependencies, known_issues, open_questions, confidence (0-1). "
            "It is validated and fanned out into typed entries with this session as provenance. Omit the contract "
            "to let Forge derive low-confidence context from session metadata. Pass the same request_id on retries."
        ),
        annotations=WRITE_IDEMPOTENT,
    )
    def forge_session_checkpoint(
        session_id: str,
        contract: dict[str, Any] | None = None,
        summary: str | None = None,
        evidence: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> str:
        p = _principal(SCOPE_SESSION_WRITE)
        if contract is not None:
            _principal(SCOPE_CONTEXT_WRITE)
        row = _session_row(p, session_id)
        body = SessionCheckpoint(context=_contract(contract), summary=summary, evidence=_evidence(evidence), request_id=request_id)
        try:
            result = services.checkpoint_session(p, row, body)
        except HTTPException as exc:
            raise ToolError(_message(exc)) from exc
        header = f"checkpoint: {'replayed' if result.idempotent_replay else 'ok'}\nquarantined: {str(result.quarantined).lower()}\ncontext_version: {result.session.context_version}\n"
        rows = [e.model_dump(mode="json") for e in result.context_entries]
        return header + _entries_doc(rows, feature=None, query={"action": "session_checkpoint", "session_id": session_id})

    @server.tool(
        name="forge_session_complete",
        description=(
            "End a Forge session. Supply the final Context Contract (same shape as checkpoint) so the work becomes "
            "durable feature context; omit it to derive low-confidence context from metadata. Idempotent: completing "
            "an already-completed session returns what was written the first time."
        ),
        annotations=WRITE_IDEMPOTENT,
    )
    def forge_session_complete(
        session_id: str,
        contract: dict[str, Any] | None = None,
        summary: str | None = None,
        status: str = "completed",
    ) -> str:
        p = _principal(SCOPE_SESSION_WRITE)
        if contract is not None:
            _principal(SCOPE_CONTEXT_WRITE)
        row = _session_row(p, session_id)
        if status not in ("completed", "failed", "abandoned"):
            raise ToolError("status must be one of: completed, failed, abandoned")
        body = SessionComplete(context=_contract(contract), summary=summary, status=status)  # type: ignore[arg-type]
        try:
            result = services.complete_session(p, row, body)
        except HTTPException as exc:
            raise ToolError(_message(exc)) from exc
        header = (
            f"session: {result.session.status}\n"
            f"replayed: {str(result.idempotent_replay).lower()}\n"
            f"quarantined: {str(result.quarantined).lower()}\n"
            f"context_version: {result.session.context_version}\n"
        )
        rows = [e.model_dump(mode="json") for e in result.context_entries]
        return header + _entries_doc(rows, feature=None, query={"action": "session_complete", "session_id": session_id})

    return server
