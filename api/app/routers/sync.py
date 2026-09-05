"""Local Context Store ↔ Cloud Context Bank synchronization (phase-2 §10, §11).

The cloud bank is authoritative. A local store is a disposable, feature-scoped
replica, so these endpoints are deliberately simple:

    pull  — everything in a feature newer than the client's cursor
    push  — statements captured locally (possibly offline), through the same
            validation, conflict and idempotency path as any other write
    status — what the cloud thinks a client has, so `forge context status` can
            report drift without transferring anything

Nothing here can make the local copy authoritative: push routes through
`context_actions.record_context`, so an offline agent's statement still gets
validated, conflict-flagged and audited exactly like an online one.
"""

from fastapi import APIRouter, Depends, Query

from app import context_actions, services
from app.access import SCOPE_CONTEXT_READ, SCOPE_CONTEXT_WRITE, Principal
from app.audit import record_audit
from app.auth import scoped
from app.repos import context as context_repo
from app.repos import sync as sync_repo
from app.schemas import (
    ContextEntryOut,
    SyncPullResult,
    SyncPushRequest,
    SyncPushResult,
    SyncStatusOut,
)

router = APIRouter(prefix="/sync", tags=["context sync"])


def _key(row: dict) -> tuple[str, str]:
    """Sort key for the sync cursor: timestamp first, entry id as tiebreak.

    A timestamp alone is not a safe cursor. Clocks are coarse — Windows ticks
    at ~15ms — so several entries can share `created_at`, and a strict `>`
    comparison would skip every one after the first. Pairing it with the id
    makes the cursor strictly increasing, so nothing is lost and nothing is
    re-sent.
    """
    return (str(row.get("created_at") or ""), str(row.get("id") or ""))


def _parse_cursor(cursor: str | None) -> tuple[str, str]:
    if not cursor:
        return ("", "")
    ts, _, entry_id = cursor.partition("|")
    return (ts, entry_id)


def _cursor(rows: list[dict]) -> str | None:
    if not rows:
        return None
    ts, entry_id = max(_key(r) for r in rows)
    return f"{ts}|{entry_id}"


@router.get("/features/{feature_id}", response_model=SyncPullResult)
def pull(
    feature_id: str,
    client_id: str = Query(..., min_length=8, max_length=128, description="Stable id of the local store"),
    since: str | None = Query(default=None, description="ISO timestamp cursor from the previous pull"),
    label: str | None = Query(default=None),
    p: Principal = Depends(scoped(SCOPE_CONTEXT_READ)),
) -> SyncPullResult:
    """Everything in this feature the client has not seen. Authorization is unchanged."""
    ctx = services.load_feature(p, feature_id)
    sync_repo.register_client(p.org_id, client_id, user_id=p.user_id, label=label)

    rows = context_repo.list_entries(p.org_id, ctx.feature["id"], statuses=("active", "pending_review"))
    fresh = [r for r in rows if _key(r) > _parse_cursor(since)]
    cursor = _cursor(rows) or since

    if cursor:
        sync_repo.set_state(p.org_id, client_id, ctx.feature["id"], cursor=cursor, entry_count=len(rows))
    record_audit(
        p, "sync.pull", "ok", feature_id=ctx.feature["id"],
        input_meta={"client_id": client_id, "returned": len(fresh), "total": len(rows)},
    )
    return SyncPullResult(
        feature_id=ctx.feature["id"],
        feature_key=ctx.feature["key"],
        cursor=cursor or None,
        total=len(rows),
        entries=services._entries_out(p.org_id, fresh),
    )


@router.get("/features/{feature_id}/status", response_model=SyncStatusOut)
def status(
    feature_id: str,
    client_id: str = Query(..., min_length=8, max_length=128),
    p: Principal = Depends(scoped(SCOPE_CONTEXT_READ)),
) -> SyncStatusOut:
    """Drift between a local replica and the cloud, without transferring entries."""
    ctx = services.load_feature(p, feature_id)
    rows = context_repo.list_entries(p.org_id, ctx.feature["id"], statuses=("active", "pending_review"))
    state = sync_repo.get_state(p.org_id, client_id, ctx.feature["id"])
    cursor = state["cursor"] if state else None
    behind = len([r for r in rows if _key(r) > _parse_cursor(cursor)])
    return SyncStatusOut(
        feature_id=ctx.feature["id"],
        feature_key=ctx.feature["key"],
        cloud_total=len(rows),
        client_cursor=cursor,
        behind=behind,
        last_synced_at=state["updated_at"] if state else None,
    )


@router.post("/features/{feature_id}", response_model=SyncPushResult)
def push(
    feature_id: str,
    body: SyncPushRequest,
    p: Principal = Depends(scoped(SCOPE_CONTEXT_WRITE)),
) -> SyncPushResult:
    """Upload statements captured locally.

    Each entry carries its own `request_id`, so a retried or duplicated push is
    a no-op rather than a duplicate statement (§16). Entries that fail
    validation are reported per-item instead of failing the whole batch, so one
    bad statement cannot block an offline queue from draining.
    """
    ctx = services.load_feature(p, feature_id)
    sync_repo.register_client(p.org_id, body.client_id, user_id=p.user_id, label=body.label)

    accepted: list[ContextEntryOut] = []
    rejected: list[dict] = []
    flagged = 0

    for item in body.entries:
        try:
            created = context_actions.record_context(
                p,
                ctx.feature["id"],
                kind=item.kind,
                title=item.title,
                payload=item.payload,
                confidence=item.confidence,
                session_id=item.session_id,
                evidence=item.evidence.model_dump(exclude_none=True) if item.evidence else None,
                request_id=item.request_id,
            )
        except Exception as exc:  # noqa: BLE001 — one bad item must not block the queue
            detail = exc.detail if hasattr(exc, "detail") else {"message": str(exc)}
            message = detail.get("message") if isinstance(detail, dict) else str(detail)
            rejected.append({"request_id": item.request_id, "title": item.title, "reason": message or str(exc)})
            continue
        if created.get("status") == "pending_review":
            flagged += 1
        accepted.append(services.entry_out(p, created))

    record_audit(
        p, "sync.push", "ok" if not rejected else "partial", feature_id=ctx.feature["id"],
        input_meta={"client_id": body.client_id, "accepted": len(accepted), "rejected": len(rejected), "flagged": flagged},
        affected_entry_ids=[e.id for e in accepted],
    )
    return SyncPushResult(accepted=accepted, rejected=rejected, flagged_for_review=flagged)
