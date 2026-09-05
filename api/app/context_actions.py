"""Agentic Context Bank actions.

Five operations an agent (or the UI) performs against the Context Bank:

    get_feature_context   — active context for one feature
    get_context_by_kind   — the same, filtered to one or more kinds
    search_context        — text search across features the caller may access
    record_context        — write a new statement, validated first
    supersede_context     — replace a statement with a newer one

Authorization reuses `app.access` through `app.services.load_feature`; no rule
is restated here (§12). Each action first requires its OAuth scope (phase-2
§14): users hold every scope implicitly, agents only what they were granted.
Every call — allowed, denied, rejected or replayed — leaves an audit row
(phase-2 §15). Writes are idempotent by `request_id` (phase-2 §16).

Reads return `(payload_dict, entries)`; writes return the created row. Routers
decide the representation: agent-facing routes render TOON via
`app.toon_codec`, the regular API returns JSON. Serialization lives at the edge.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from fastapi import HTTPException, status

from app import context_bank, services
from app.access import (
    SCOPE_CONTEXT_READ,
    SCOPE_CONTEXT_SUPERSEDE,
    SCOPE_CONTEXT_WRITE,
    Principal,
)
from app.audit import record_audit
from app.conflicts import find_conflict
from app.context_validation import validate_entry
from app.observability import log_context_op
from app.repos import context as context_repo
from app.repos import features as features_repo
from app.repos import idempotency as idempotency_repo
from app.repos import sessions as sessions_repo
from app.schemas import CONTEXT_KINDS


# --- guards that audit their own denials -------------------------------------


def _deny_reason(exc: HTTPException) -> str:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return f"deny:{detail.get('code', exc.status_code)}"


def _authorize(p: Principal, scope: str, action: str, *, feature_id: str | None = None) -> None:
    try:
        services.require_scope(p, scope)
    except HTTPException as exc:
        record_audit(p, action, "denied", feature_id=feature_id, authorization_result=_deny_reason(exc))
        raise


def _feature(p: Principal, feature_id: str, action: str) -> services.FeatureCtx:
    try:
        return services.load_feature(p, feature_id)
    except HTTPException as exc:
        record_audit(p, action, "denied", feature_id=feature_id, authorization_result=_deny_reason(exc))
        raise


def _entry(p: Principal, entry_id: str, action: str) -> tuple[dict, services.FeatureCtx]:
    try:
        return services.load_entry_for_read(p, entry_id)
    except HTTPException as exc:
        record_audit(p, action, "denied", authorization_result=_deny_reason(exc), input_meta={"entry_id": entry_id})
        raise


def _check_kinds(kinds: Sequence[str] | None) -> list[str] | None:
    if not kinds:
        return None
    bad = [k for k in kinds if k not in CONTEXT_KINDS]
    if bad:
        raise services.err(
            "UNSUPPORTED_KIND",
            f"Unsupported kind(s): {', '.join(bad)}. Valid kinds: {', '.join(CONTEXT_KINDS)}.",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return list(kinds)


def _invalid(p: Principal, action: str, result, *, feature_id: str | None, session_id: str | None) -> HTTPException:
    code = result.issues[0].code
    log_context_op(
        operation=action, status="rejected", organization_id=p.org_id, feature_id=feature_id,
        session_id=session_id, user_id=p.user_id, error_type=code,
    )
    record_audit(p, action, "rejected", feature_id=feature_id, session_id=session_id, input_meta={"error_type": code})
    return services.err(
        "CONTEXT_INVALID",
        "; ".join(f"{i.field}: {i.message}" for i in result.issues),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def _replayed(p: Principal, request_id: str, action: str, *, feature_id: str | None, session_id: str | None) -> dict | None:
    """Return the entry a previous call with this request_id produced, if any (§16)."""
    cached = idempotency_repo.get_result(p.org_id, request_id)
    if not cached:
        return None
    existing = context_repo.get_entry(p.org_id, cached["result"].get("entry_id", ""))
    if not existing:
        return None
    record_audit(p, action, "replayed", feature_id=feature_id, session_id=session_id, affected_entry_ids=[existing["id"]])
    return existing


# --- reads -------------------------------------------------------------------


def get_feature_context(
    p: Principal,
    feature_id: str,
    *,
    statuses: Sequence[str] | None = ("active",),
) -> tuple[dict[str, Any], list[dict]]:
    action = "context.get_feature_context"
    _authorize(p, SCOPE_CONTEXT_READ, action, feature_id=feature_id)
    ctx = _feature(p, feature_id, action)
    rows = context_repo.list_entries(p.org_id, ctx.feature["id"], statuses=statuses, kinds=None)
    log_context_op(
        operation=action, status="ok", organization_id=p.org_id, feature_id=feature_id,
        user_id=p.user_id, entry_count=len(rows),
    )
    record_audit(p, action, "ok", feature_id=ctx.feature["id"], input_meta={"entry_count": len(rows)})
    return {"feature": ctx.feature, "query": {"statuses": list(statuses or [])}}, rows


def get_context_by_kind(
    p: Principal,
    feature_id: str,
    kinds: Sequence[str],
    *,
    statuses: Sequence[str] | None = ("active",),
) -> tuple[dict[str, Any], list[dict]]:
    action = "context.get_context_by_kind"
    _authorize(p, SCOPE_CONTEXT_READ, action, feature_id=feature_id)
    checked = _check_kinds(kinds)
    ctx = _feature(p, feature_id, action)
    rows = context_repo.list_entries(p.org_id, ctx.feature["id"], statuses=statuses, kinds=checked)
    log_context_op(
        operation=action, status="ok", organization_id=p.org_id, feature_id=feature_id,
        user_id=p.user_id, entry_count=len(rows),
    )
    record_audit(
        p, action, "ok", feature_id=ctx.feature["id"],
        input_meta={"entry_count": len(rows), "kinds": ",".join(checked or [])},
    )
    return {"feature": ctx.feature, "query": {"kinds": checked or [], "statuses": list(statuses or [])}}, rows


def search_context(
    p: Principal,
    query: str,
    *,
    feature_id: str | None = None,
    kinds: Sequence[str] | None = None,
    limit: int = 50,
) -> tuple[dict[str, Any], list[dict]]:
    """Text search restricted to features the caller can access.

    The accessible-feature set is computed first and passed as a filter, so an
    unauthorized feature's context can never surface in results (§12).
    """
    action = "context.search_context"
    _authorize(p, SCOPE_CONTEXT_READ, action, feature_id=feature_id)
    checked = _check_kinds(kinds)

    if feature_id:
        ctx = _feature(p, feature_id, action)
        feature_ids = [ctx.feature["id"]]
        feature = ctx.feature
    else:
        feature_ids = [f.id for f in services.accessible_features(p)]
        feature = None

    rows = (
        context_repo.search_entries(p.org_id, query, feature_ids=feature_ids, kinds=checked, limit=limit)
        if feature_ids
        else []
    )
    log_context_op(
        operation=action, status="ok", organization_id=p.org_id, feature_id=feature_id,
        user_id=p.user_id, entry_count=len(rows), scope_features=len(feature_ids),
    )
    record_audit(
        p, action, "ok", feature_id=feature_id,
        input_meta={"entry_count": len(rows), "scope_features": len(feature_ids)},
    )
    return {"feature": feature, "query": {"q": query, "kinds": checked or []}}, rows


# --- writes ------------------------------------------------------------------


def record_context(
    p: Principal,
    feature_id: str,
    *,
    kind: str,
    title: str,
    payload: Mapping[str, Any],
    confidence: float | None = None,
    session_id: str | None = None,
    evidence: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> dict:
    """Write one new statement into a feature's Context Bank.

    Validated before it is stored: the feature must exist and belong to the
    caller's organization, and a referenced session must exist, belong to the
    same organization and to the same feature (§8, §18). Idempotent by
    `request_id`: a retry returns the entry the first call created.
    """
    action = "context.record_context"
    _authorize(p, SCOPE_CONTEXT_WRITE, action, feature_id=feature_id)
    ctx = _feature(p, feature_id, action)

    if request_id:
        existing = _replayed(p, request_id, action, feature_id=ctx.feature["id"], session_id=session_id)
        if existing:
            return existing

    session = sessions_repo.get_session(p.org_id, session_id) if session_id else None
    result = validate_entry(
        org_id=p.org_id, kind=kind, feature=ctx.feature, session=session,
        require_session=session_id is not None, confidence=confidence,
    )
    if not result.ok:
        raise _invalid(p, action, result, feature_id=feature_id, session_id=session_id)

    # §17: never silently duplicate or contradict. A statement that closely
    # resembles an active one is quarantined with a link to it, so a human
    # decides supersede-or-keep. Both sides stay readable.
    conflict = find_conflict(
        kind=kind,
        title=title,
        payload=payload,
        existing=context_repo.list_entries(p.org_id, ctx.feature["id"], statuses=("active",), kinds=[kind]),
    )

    created = context_repo.create_entry(
        p.org_id,
        {
            "feature_id": ctx.feature["id"],
            "session_id": session_id,
            "author_user_id": p.user_id,
            "kind": kind,
            "title": title,
            "payload": dict(payload),
            "confidence": confidence,
            "status": "pending_review" if conflict else "active",
            "version": 1,
            "evidence": dict(evidence) if evidence else None,
            "conflicts_with": conflict.entry_id if conflict else None,
        },
    )
    if request_id:
        idempotency_repo.put_result(p.org_id, request_id, action, {"entry_id": created["id"]})

    outcome = "flagged" if conflict else "ok"
    log_context_op(
        operation=action, status=outcome, organization_id=p.org_id, feature_id=feature_id,
        session_id=session_id, user_id=p.user_id, kind=kind,
    )
    record_audit(
        p, action, outcome, feature_id=ctx.feature["id"], session_id=session_id,
        input_meta={
            "kind": kind, "has_evidence": bool(evidence), "request_id": request_id,
            "conflicts_with": conflict.entry_id if conflict else None,
            "similarity": conflict.score if conflict else None,
        },
        affected_entry_ids=[created["id"]] + ([conflict.entry_id] if conflict else []),
    )
    return created


def supersede_context(
    p: Principal,
    entry_id: str,
    *,
    title: str,
    payload: Mapping[str, Any],
    confidence: float | None = None,
    session_id: str | None = None,
    evidence: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> dict:
    """Replace an existing statement with a newer version.

    Never overwrites: a new row is written with version+1 and `supersedes_id`
    pointing at the old row, which becomes `superseded` and stays readable (§10).
    Idempotent by `request_id`.
    """
    action = "context.supersede_context"
    _authorize(p, SCOPE_CONTEXT_SUPERSEDE, action)
    current, _ctx = _entry(p, entry_id, action)
    feature_id = current["feature_id"]

    if request_id:
        existing = _replayed(p, request_id, action, feature_id=feature_id, session_id=session_id)
        if existing:
            return existing

    if current["status"] == "superseded":
        record_audit(
            p, action, "rejected", feature_id=feature_id,
            input_meta={"error_type": "ALREADY_SUPERSEDED"}, affected_entry_ids=[entry_id],
        )
        raise services.err(
            "ALREADY_SUPERSEDED",
            "This entry has already been superseded; supersede the current version instead.",
            status.HTTP_409_CONFLICT,
        )

    if session_id:
        session = sessions_repo.get_session(p.org_id, session_id)
        result = validate_entry(
            org_id=p.org_id, kind=current["kind"], feature=features_repo.get_feature(p.org_id, feature_id),
            session=session, require_session=True, confidence=confidence,
        )
        if not result.ok:
            raise _invalid(p, action, result, feature_id=feature_id, session_id=session_id)

    created = context_bank.supersede_with_statement(
        p.org_id, current, title=title, payload=payload, author_user_id=p.user_id,
        session_id=session_id, confidence=confidence, evidence=evidence,
    )
    if request_id:
        idempotency_repo.put_result(p.org_id, request_id, action, {"entry_id": created["id"]})

    log_context_op(
        operation=action, status="ok", organization_id=p.org_id, feature_id=feature_id,
        session_id=session_id, user_id=p.user_id, superseded_id=str(entry_id), new_version=created["version"],
    )
    record_audit(
        p, action, "ok", feature_id=feature_id, session_id=session_id,
        input_meta={"superseded_id": entry_id, "new_version": created["version"], "request_id": request_id},
        affected_entry_ids=[entry_id, created["id"]],
    )
    return created
