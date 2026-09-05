"""Assembles access-checked views: repos + the pure access rules in access.py.

Routers call these; nothing here trusts the caller — every function takes the
verified Principal and scopes queries by its org.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app import context_bank
from app.access import Principal, feature_access, visible_sessions
from app.context_generator import get_generator
from app.context_validation import (
    is_publishable,
    normalize_contract,
    validate_contract,
    validate_entry,
)
from app.audit import record_audit
from app.observability import log_context_op
from app.repos import context as context_repo
from app.repos import features as features_repo
from app.repos import idempotency as idempotency_repo
from app.repos import sessions as sessions_repo
from app.repos import teams as teams_repo
from app.repos import users as users_repo
from app.schemas import (
    CompletionResult,
    ContextContract,
    ContextEntryOut,
    FeatureDetail,
    FeatureOut,
    FeatureSummary,
    SessionCheckpoint,
    SessionComplete,
    SessionOut,
    TeamOut,
    TeamSummary,
    UserOut,
)


def err(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def require_scope(p: Principal, scope: str) -> None:
    """Users retain Phase 1 behavior; agent credentials must be explicit."""
    if not p.has_scope(scope):
        raise err("SCOPE_REQUIRED", f"This action requires the '{scope}' scope.", status.HTTP_403_FORBIDDEN)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- small mappers ----------------------------------------------------------


def _user_out(row: dict | None) -> UserOut | None:
    return UserOut.model_validate(row) if row else None


def _team_summaries(team_ids: set[str] | list[str], teams_map: dict[str, dict]) -> list[TeamSummary]:
    out = [TeamSummary.model_validate(teams_map[t]) for t in team_ids if t in teams_map]
    return sorted(out, key=lambda t: t.name)


def _links_by_feature(rows: list[dict], key: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for r in rows:
        out.setdefault(r["feature_id"], set()).add(r[key])
    return out


def session_out(
    row: dict,
    *,
    reason: str | None,
    users_map: dict[str, dict],
    features_map: dict[str, dict] | None = None,
) -> SessionOut:
    s = SessionOut.model_validate(row)
    s.visibility_reason = reason
    s.author = _user_out(users_map.get(row["user_id"]))
    if features_map and row["feature_id"] in features_map:
        s.feature = FeatureSummary.model_validate(features_map[row["feature_id"]])
    return s


def context_entry_out(
    row: dict,
    users_map: dict[str, dict],
    *,
    sessions_map: dict[str, dict] | None = None,
    features_map: dict[str, dict] | None = None,
) -> ContextEntryOut:
    """Hydrate an entry for the API, including the provenance chain (§9).

    context → source session → author, so the UI can render the path without
    extra round trips.
    """
    e = ContextEntryOut.model_validate(row)
    e.author = _user_out(users_map.get(row.get("author_user_id") or ""))

    session_id = row.get("session_id")
    if sessions_map and session_id and session_id in sessions_map:
        s_row = sessions_map[session_id]
        session = SessionOut.model_validate(s_row)
        session.author = _user_out(users_map.get(s_row["user_id"]))
        e.session = session

    if features_map and row.get("feature_id") in features_map:
        e.feature = FeatureSummary.model_validate(features_map[row["feature_id"]])
    return e


# --- teams ------------------------------------------------------------------


def teams_with_members(org_id: str) -> list[TeamOut]:
    teams = teams_repo.list_teams(org_id)
    members = teams_repo.members_by_team(org_id)
    users_map = users_repo.users_by_id(org_id)
    out = []
    for t in teams:
        team = TeamOut.model_validate(t)
        team.members = sorted(
            (UserOut.model_validate(users_map[u]) for u in members.get(t["id"], ()) if u in users_map),
            key=lambda u: u.display_name,
        )
        out.append(team)
    return out


# --- features ---------------------------------------------------------------


def accessible_features(p: Principal) -> list[FeatureOut]:
    org = p.org_id
    feats = features_repo.list_features(org)
    if not feats:
        return []
    ids = [f["id"] for f in feats]
    ft = _links_by_feature(features_repo.feature_teams(org, ids), "team_id")
    fa = _links_by_feature(features_repo.feature_assignments(org, ids), "user_id")
    my_teams = teams_repo.my_team_ids(org, p.user_id)
    teams_map = teams_repo.teams_by_id(org)
    users_map = users_repo.users_by_id(org)
    counts = sessions_repo.count_by_feature(org)

    out: list[FeatureOut] = []
    for f in feats:
        reason = feature_access(
            p,
            feature_team_ids=ft.get(f["id"], set()),
            my_team_ids=my_teams,
            assignee_ids=fa.get(f["id"], set()),
            feature_id=f["id"],
        )
        if not reason:
            continue
        feature = FeatureOut.model_validate(f)
        feature.access_reason = reason
        feature.teams = _team_summaries(ft.get(f["id"], set()), teams_map)
        feature.assignees = sorted(
            (UserOut.model_validate(users_map[u]) for u in fa.get(f["id"], set()) if u in users_map),
            key=lambda u: u.display_name,
        )
        feature.session_count = counts.get(f["id"], 0)
        out.append(feature)
    return out


class FeatureCtx:
    """Everything needed to evaluate access rules for one feature."""

    def __init__(self, p: Principal, feature: dict):
        org = p.org_id
        self.feature = feature
        self.feature_team_ids = {r["team_id"] for r in features_repo.feature_teams(org, [feature["id"]])}
        self.assignee_ids = {r["user_id"] for r in features_repo.feature_assignments(org, [feature["id"]])}
        self.my_team_ids = teams_repo.my_team_ids(org, p.user_id)
        self.reason = feature_access(
            p,
            feature_team_ids=self.feature_team_ids,
            my_team_ids=self.my_team_ids,
            assignee_ids=self.assignee_ids,
            feature_id=feature["id"],
        )


def load_feature(p: Principal, feature_id: str) -> FeatureCtx:
    """404 if the feature isn't in the caller's org, 403 if they can't access it."""
    feature = features_repo.get_feature(p.org_id, feature_id)
    if not feature:
        raise err("FEATURE_NOT_FOUND", "Feature not found.", status.HTTP_404_NOT_FOUND)
    ctx = FeatureCtx(p, feature)
    if not ctx.reason:
        raise err(
            "FEATURE_FORBIDDEN",
            "You are not assigned to this feature and none of your teams own it.",
            status.HTTP_403_FORBIDDEN,
        )
    return ctx


def _visible_session_rows(p: Principal, ctx: FeatureCtx, rows: list[dict]) -> list[tuple[dict, str]]:
    org = p.org_id
    members = teams_repo.members_by_team(org, list(ctx.feature_team_ids))
    names = {t["id"]: t["name"] for t in teams_repo.list_teams(org)}
    return [
        (dict(row), reason)
        for row, reason in visible_sessions(
            p,
            rows,
            feature_team_ids=ctx.feature_team_ids,
            my_team_ids=ctx.my_team_ids,
            team_members=members,
            team_names=names,
        )
    ]


def feature_sessions(p: Principal, ctx: FeatureCtx) -> tuple[list[SessionOut], int]:
    rows = sessions_repo.list_sessions(p.org_id, feature_id=ctx.feature["id"])
    visible = _visible_session_rows(p, ctx, rows)
    users_map = users_repo.users_by_id(p.org_id)
    out = [session_out(row, reason=reason, users_map=users_map) for row, reason in visible]
    return out, len(rows) - len(visible)


def feature_context(
    p: Principal,
    ctx: FeatureCtx,
    *,
    statuses: list[str] | None = None,
    kinds: list[str] | None = None,
) -> list[ContextEntryOut]:
    """Active feature context by default (§11: org + feature + status + authz)."""
    org = p.org_id
    rows = context_repo.list_entries(
        org,
        ctx.feature["id"],
        statuses=statuses if statuses is not None else ("active",),
        kinds=kinds,
    )
    users_map = users_repo.users_by_id(org)
    sessions_map = {s["id"]: s for s in sessions_repo.list_sessions(org, feature_id=ctx.feature["id"])}
    return [context_entry_out(r, users_map, sessions_map=sessions_map) for r in rows]


def feature_detail(p: Principal, feature_id: str) -> FeatureDetail:
    ctx = load_feature(p, feature_id)
    org = p.org_id
    teams_map = teams_repo.teams_by_id(org)
    users_map = users_repo.users_by_id(org)

    detail = FeatureDetail.model_validate(ctx.feature)
    detail.access_reason = ctx.reason
    detail.teams = _team_summaries(ctx.feature_team_ids, teams_map)
    detail.assignees = sorted(
        (UserOut.model_validate(users_map[u]) for u in ctx.assignee_ids if u in users_map),
        key=lambda u: u.display_name,
    )
    detail.sessions, detail.hidden_session_count = feature_sessions(p, ctx)
    detail.session_count = len(detail.sessions) + detail.hidden_session_count
    detail.context_entries = [context_entry_out(r, users_map) for r in context_repo.list_entries(org, feature_id)]
    return detail


# --- sessions ---------------------------------------------------------------


def my_sessions(p: Principal) -> list[SessionOut]:
    org = p.org_id
    rows = sessions_repo.list_sessions(org, user_id=p.user_id)
    users_map = users_repo.users_by_id(org)
    features_map = {f["id"]: f for f in features_repo.list_features(org)}
    return [session_out(r, reason="own", users_map=users_map, features_map=features_map) for r in rows]


def load_visible_session(p: Principal, session_id: str) -> tuple[dict, str, FeatureCtx]:
    """Session + visibility reason; 404 unless the caller may see it."""
    row = sessions_repo.get_session(p.org_id, session_id)
    if not row:
        raise err("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    feature = features_repo.get_feature(p.org_id, row["feature_id"])
    if not feature:
        raise err("SESSION_NOT_FOUND", "Session not found.", status.HTTP_404_NOT_FOUND)
    ctx = FeatureCtx(p, feature)
    if not ctx.reason:
        raise err("SESSION_FORBIDDEN", "You do not have access to this session's feature.", status.HTTP_403_FORBIDDEN)
    visible = _visible_session_rows(p, ctx, [row])
    if not visible:
        raise err("SESSION_FORBIDDEN", "This session is not visible to you.", status.HTTP_403_FORBIDDEN)
    return row, visible[0][1], ctx


def session_with_context(p: Principal, row: dict, reason: str) -> SessionOut:
    org = p.org_id
    users_map = users_repo.users_by_id(org)
    features_map = {f["id"]: f for f in features_repo.list_features(org)}
    return session_out(row, reason=reason, users_map=users_map, features_map=features_map)


def start_session(p: Principal, feature_id: str, *, agent: str, model: str | None, goal: str | None) -> dict:
    """Anyone with access to the feature may start a session on it; the author is always the caller.

    For an agent principal the author is the grant's creator and `agent` names
    the client, so provenance answers both "who" and "through what".
    """
    ctx = load_feature(p, feature_id)
    row = sessions_repo.create_session(
        p.org_id,
        {
            "feature_id": ctx.feature["id"],
            "user_id": p.user_id,
            "agent": agent,
            "model": model,
            "goal": goal,
            "status": "active",
            "started_at": now_iso(),
        },
    )
    record_audit(p, "session.start", "ok", feature_id=ctx.feature["id"], session_id=row["id"], input_meta={"agent": agent})
    return row


def _ingest_contract(
    p: Principal,
    row: dict,
    contract: ContextContract | None,
    *,
    operation: str,
    evidence: dict[str, Any] | None = None,
) -> tuple[list[dict], str, ContextContract, bool]:
    """The shared pipeline: generate → normalize → validate → fan out → persist.

    Used by both checkpoint and completion. Returns (created rows, entry status,
    contract, generated). On validation failure nothing is written: the session
    is preserved and the caller receives a 422 (§8, §13).
    """
    org, session_id, feature_id = p.org_id, row["id"], row["feature_id"]
    generated = contract is None
    contract = normalize_contract(get_generator().generate(row) if generated else contract)

    result = validate_contract(contract)
    feature = features_repo.get_feature(org, feature_id)
    result.merge(
        validate_entry(
            org_id=org, kind="change", feature=feature, session=row, require_session=True, confidence=contract.confidence
        )
    )
    if not result.ok:
        code = result.issues[0].code
        log_context_op(
            operation=operation, status="rejected", organization_id=org, feature_id=feature_id,
            session_id=session_id, user_id=p.user_id, error_type=code, issue_count=len(result.issues),
        )
        record_audit(p, operation, "rejected", feature_id=feature_id, session_id=session_id, input_meta={"error_type": code})
        raise err(
            "CONTEXT_INVALID",
            "; ".join(f"{i.field}: {i.message}" for i in result.issues),
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    # Structurally valid but not confident enough to publish → quarantine.
    entry_status = "active" if is_publishable(contract) else "pending_review"
    entries = context_bank.fan_out(
        contract, feature_id=feature_id, session_id=session_id, author_user_id=row["user_id"], status=entry_status
    )
    if evidence:
        for e in entries:
            e["evidence"] = evidence
    created = context_bank.persist_fan_out(org, entries)
    return created, entry_status, contract, generated


def _replay(p: Principal, row: dict, entry_ids: list[str], *, operation: str) -> CompletionResult:
    org = p.org_id
    rows = [e for e in (context_repo.get_entry(org, i) for i in entry_ids) if e]
    record_audit(p, operation, "replayed", feature_id=row["feature_id"], session_id=row["id"], affected_entry_ids=entry_ids)
    return CompletionResult(
        session=session_with_context(p, row, "own"),
        context_entries=_entries_out(org, rows),
        generated=False,
        quarantined=any(e["status"] == "pending_review" for e in rows),
        idempotent_replay=True,
    )


def checkpoint_session(p: Principal, row: dict, body: SessionCheckpoint) -> CompletionResult:
    """Mid-session durable context (phase-2 §13.3): same pipeline as completion,
    but the session stays active so the agent keeps working. Idempotent by
    `request_id` (§16), so a retried checkpoint never duplicates entries.
    """
    org, session_id, feature_id = p.org_id, row["id"], row["feature_id"]
    if row.get("status") != "active":
        raise err("SESSION_NOT_ACTIVE", "Only an active session can be checkpointed.", status.HTTP_409_CONFLICT)

    if body.request_id:
        cached = idempotency_repo.get_result(org, body.request_id)
        if cached:
            return _replay(p, row, cached["result"].get("entry_ids", []), operation="session.checkpoint")

    evidence = body.evidence.model_dump(exclude_none=True) if body.evidence else None
    created, entry_status, contract, generated = _ingest_contract(
        p, row, body.context, operation="session.checkpoint", evidence=evidence
    )

    version = int(row.get("context_version") or 0) + 1
    updated = sessions_repo.update_session(
        org,
        session_id,
        {
            "summary": body.summary or row.get("summary"),
            "context": contract.model_dump(mode="json"),  # non-authoritative snapshot (§17)
            "context_version": version,
        },
    )
    ids = [c["id"] for c in created]
    if body.request_id:
        idempotency_repo.put_result(org, body.request_id, "session.checkpoint", {"entry_ids": ids})

    outcome = "quarantined" if entry_status == "pending_review" else "ok"
    log_context_op(
        operation="session.checkpoint", status=outcome, organization_id=org, feature_id=feature_id,
        session_id=session_id, user_id=p.user_id, entry_count=len(created), generated=generated,
    )
    record_audit(
        p, "session.checkpoint", outcome, feature_id=feature_id, session_id=session_id,
        input_meta={"generated": generated, "version": version}, affected_entry_ids=ids,
    )
    return CompletionResult(
        session=session_with_context(p, updated or row, "own"),
        context_entries=_entries_out(org, created),
        generated=generated,
        contract=contract,
        quarantined=entry_status == "pending_review",
    )


def complete_session(p: Principal, row: dict, body: SessionComplete) -> CompletionResult:
    """Session completion (§13).

        Complete → Generate → Validate → Persist entries → Mark session completed

    Idempotent: completing an already-completed session returns what was written
    the first time instead of duplicating active context. Completion is the
    final checkpoint plus closing the session.
    """
    org, session_id, feature_id = p.org_id, row["id"], row["feature_id"]

    # --- idempotency: already completed and already produced context ---------
    existing = context_repo.list_by_session(org, session_id)
    if row.get("status") != "active" and existing:
        log_context_op(
            operation="session.complete", status="replayed", organization_id=org, feature_id=feature_id,
            session_id=session_id, user_id=p.user_id, entry_count=len(existing),
        )
        return _replay(p, row, [e["id"] for e in existing], operation="session.complete")

    created, entry_status, contract, generated = _ingest_contract(p, row, body.context, operation="session.complete")

    version = int(row.get("context_version") or 0) + 1
    updated = sessions_repo.update_session(
        org,
        session_id,
        {
            "status": body.status,
            "summary": body.summary or row.get("summary"),
            "context": contract.model_dump(mode="json"),  # non-authoritative snapshot (§17)
            "context_version": version,
            "ended_at": now_iso(),
        },
    )
    ids = [c["id"] for c in created]
    outcome = "quarantined" if entry_status == "pending_review" else "ok"
    log_context_op(
        operation="session.complete", status=outcome, organization_id=org, feature_id=feature_id,
        session_id=session_id, user_id=p.user_id, entry_count=len(created), generated=generated,
        confidence=contract.confidence,
    )
    record_audit(
        p, "session.complete", outcome, feature_id=feature_id, session_id=session_id,
        input_meta={"generated": generated, "status": body.status, "version": version}, affected_entry_ids=ids,
    )
    return CompletionResult(
        session=session_with_context(p, updated or row, "own"),
        context_entries=_entries_out(org, created),
        generated=generated,
        contract=contract,
        quarantined=entry_status == "pending_review",
    )


def _entries_out(org: str, rows: list[dict]) -> list[ContextEntryOut]:
    users_map = users_repo.users_by_id(org)
    session_ids = {r["session_id"] for r in rows if r.get("session_id")}
    sessions_map = {
        s["id"]: s
        for s in sessions_repo.list_sessions(org)
        if s["id"] in session_ids
    }
    return [context_entry_out(r, users_map, sessions_map=sessions_map) for r in rows]


# --- Context Bank reads / writes --------------------------------------------


def load_entry_for_read(p: Principal, entry_id: str) -> tuple[dict, FeatureCtx]:
    """Fetch an entry and prove the caller may access its feature (§12)."""
    entry = context_repo.get_entry(p.org_id, entry_id)
    if not entry:
        raise err("CONTEXT_NOT_FOUND", "Context entry not found.", status.HTTP_404_NOT_FOUND)
    ctx = load_feature(p, entry["feature_id"])
    return entry, ctx


def entry_out(p: Principal, row: dict) -> ContextEntryOut:
    return _entries_out(p.org_id, [row])[0]


def pending_context(p: Principal) -> list[ContextEntryOut]:
    """Quarantined entries across every feature the caller may access."""
    org = p.org_id
    accessible = accessible_features(p)
    if not accessible:
        return []

    features_map = {f.id: features_repo.get_feature(org, f.id) for f in accessible}
    rows: list[dict] = []
    for feature_id in features_map:
        rows.extend(context_repo.list_entries(org, feature_id, statuses=("pending_review",)))
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)

    users_map = users_repo.users_by_id(org)
    sessions_map = {s["id"]: s for s in sessions_repo.list_sessions(org)}
    return [
        context_entry_out(r, users_map, sessions_map=sessions_map, features_map=features_map)
        for r in rows
    ]
