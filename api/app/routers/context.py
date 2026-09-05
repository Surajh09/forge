"""Context Bank REST API (phase-1-requirements §14).

Deletion is deliberately absent. Context is historical engineering knowledge, so
a statement is retired by status (`rejected`) or replaced by a new version
(`superseded`), never destroyed.

Every route declares its OAuth scope (phase-2 §14) because agent tokens are
accepted on the whole API. Users hold all scopes implicitly.
"""

from fastapi import APIRouter, Depends, Query, status as http_status

from app import context_actions, services
from app.access import (
    SCOPE_CONTEXT_READ,
    SCOPE_CONTEXT_SUPERSEDE,
    SCOPE_CONTEXT_WRITE,
    Principal,
)
from app.audit import record_audit
from app.auth import get_principal, scoped
from app.context_bank import revise_entry
from app.repos import context as context_repo
from app.repos import idempotency as idempotency_repo
from app.schemas import ContextEntryCreate, ContextEntryOut, ContextEntryUpdate, ContextStatus

router = APIRouter(prefix="/context", tags=["context bank"])
read = Depends(scoped(SCOPE_CONTEXT_READ))


# Declared before /{entry_id} so these literal paths are not swallowed by it.


@router.get("/search", response_model=list[ContextEntryOut])
def search(
    q: str = Query(..., min_length=2, description="Text to match in titles and payloads"),
    feature_id: str | None = Query(default=None),
    kind: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    p: Principal = read,
) -> list[ContextEntryOut]:
    """JSON counterpart of the `search_context` agent action, for the UI.

    Restricted to features the caller can access, so unauthorized context can
    never appear in results.
    """
    _payload, rows = context_actions.search_context(
        p, q, feature_id=feature_id, kinds=list(kind) if kind else None, limit=limit
    )
    return [services.entry_out(p, r) for r in rows]


@router.get("/pending", response_model=list[ContextEntryOut])
def pending_review(p: Principal = read) -> list[ContextEntryOut]:
    """Quarantined context awaiting review, across every feature the caller can access.

    Context that failed the confidence gate is held here rather than published,
    so it needs somewhere to be seen and approved or rejected (§8).
    """
    return services.pending_context(p)


@router.get("/{entry_id}", response_model=ContextEntryOut)
def get_entry(entry_id: str, p: Principal = read) -> ContextEntryOut:
    """One entry, with its provenance (source session and author) hydrated."""
    entry, _ctx = services.load_entry_for_read(p, entry_id)
    return services.entry_out(p, entry)


@router.get("/{entry_id}/history", response_model=list[ContextEntryOut])
def get_history(entry_id: str, p: Principal = read) -> list[ContextEntryOut]:
    """Version chain for an entry, newest first (§10)."""
    _entry, _ctx = services.load_entry_for_read(p, entry_id)
    chain = context_repo.version_chain(p.org_id, entry_id)
    return [services.entry_out(p, row) for row in chain]


@router.patch("/{entry_id}", response_model=ContextEntryOut)
def update_entry(
    entry_id: str,
    body: ContextEntryUpdate,
    p: Principal = Depends(get_principal),
) -> ContextEntryOut:
    """Revise or re-status an entry.

    Changing content writes a new version and supersedes the current row
    (requires `context.supersede`). Changing only `status` — for example
    quarantined → active after review, or → rejected — is applied in place
    and requires `context.write`, since no statement is being restated.
    """
    data = body.model_dump(exclude_unset=True, exclude={"request_id", "evidence"})
    content_changed = any(k in data for k in ("title", "payload", "kind", "confidence"))
    services.require_scope(p, SCOPE_CONTEXT_SUPERSEDE if content_changed else SCOPE_CONTEXT_WRITE)

    current, _ctx = services.load_entry_for_read(p, entry_id)

    if not content_changed:
        if "status" not in data:
            return services.entry_out(p, current)
        updated = context_repo.update_entry(p.org_id, entry_id, {"status": data["status"]})
        record_audit(
            p, "context.set_status", "ok", feature_id=current["feature_id"],
            input_meta={"status": data["status"]}, affected_entry_ids=[entry_id],
        )
        return services.entry_out(p, updated or current)

    if body.request_id:
        cached = idempotency_repo.get_result(p.org_id, body.request_id)
        if cached and (existing := context_repo.get_entry(p.org_id, cached["result"]["entry_id"])):
            record_audit(p, "context.revise", "replayed", feature_id=current["feature_id"], affected_entry_ids=[existing["id"]])
            return services.entry_out(p, existing)

    if current["status"] == "superseded":
        raise services.err(
            "ALREADY_SUPERSEDED",
            "This entry is superseded; revise the current version instead.",
            http_status.HTTP_409_CONFLICT,
        )

    created = revise_entry(
        p.org_id,
        current,
        title=data.get("title"),
        payload=data.get("payload"),
        kind=data.get("kind"),
        confidence=data.get("confidence"),
        author_user_id=p.user_id,
        evidence=body.evidence.model_dump(exclude_none=True) if body.evidence else None,
    )
    if data.get("status") and data["status"] != "active":
        created = context_repo.update_entry(p.org_id, created["id"], {"status": data["status"]}) or created
    if body.request_id:
        idempotency_repo.put_result(p.org_id, body.request_id, "context.revise", {"entry_id": created["id"]})
    record_audit(
        p, "context.revise", "ok", feature_id=current["feature_id"],
        input_meta={"new_version": created["version"], "request_id": body.request_id},
        affected_entry_ids=[entry_id, created["id"]],
    )
    return services.entry_out(p, created)


# --- feature-scoped collection ----------------------------------------------

feature_router = APIRouter(prefix="/features/{feature_id}/context", tags=["context bank"])


@feature_router.get("", response_model=list[ContextEntryOut])
def list_feature_context(
    feature_id: str,
    kind: list[str] | None = Query(default=None, description="Filter by context kind"),
    status: list[ContextStatus] | None = Query(default=None, description="Defaults to active only"),
    p: Principal = read,
) -> list[ContextEntryOut]:
    """Active context for a feature (§11). Visibility follows feature access."""
    ctx = services.load_feature(p, feature_id)
    return services.feature_context(
        p,
        ctx,
        statuses=list(status) if status else None,
        kinds=list(kind) if kind else None,
    )


@feature_router.post("", response_model=ContextEntryOut, status_code=http_status.HTTP_201_CREATED)
def create_feature_context(
    feature_id: str,
    body: ContextEntryCreate,
    p: Principal = Depends(scoped(SCOPE_CONTEXT_WRITE)),
) -> ContextEntryOut:
    """Manually author a context statement (the `record_context` action)."""
    created = context_actions.record_context(
        p,
        feature_id,
        kind=body.kind,
        title=body.title,
        payload=body.payload,
        confidence=body.confidence,
        session_id=body.session_id,
        evidence=body.evidence.model_dump(exclude_none=True) if body.evidence else None,
        request_id=body.request_id,
    )
    return services.entry_out(p, created)
