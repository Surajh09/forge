from __future__ import annotations

from datetime import datetime, timezone

from app.db import get_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_client(org_id: str, client_id: str, *, user_id: str, label: str | None) -> dict:
    return (
        get_db()
        .table("sync_clients")
        .upsert(
            {
                "clerk_org_id": org_id,
                "client_id": client_id,
                "user_id": user_id,
                "label": label,
                "last_seen_at": _now(),
            },
            on_conflict="clerk_org_id,client_id",
        )
        .execute()
        .data[0]
    )


def get_state(org_id: str, client_id: str, feature_id: str) -> dict | None:
    rows = (
        get_db()
        .table("sync_state")
        .select("*")
        .eq("clerk_org_id", org_id)
        .eq("client_id", client_id)
        .eq("feature_id", feature_id)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


def set_state(org_id: str, client_id: str, feature_id: str, *, cursor: str, entry_count: int) -> dict:
    return (
        get_db()
        .table("sync_state")
        .upsert(
            {
                "clerk_org_id": org_id,
                "client_id": client_id,
                "feature_id": feature_id,
                "cursor": cursor,
                "entry_count": entry_count,
                "updated_at": _now(),
            },
            on_conflict="clerk_org_id,client_id,feature_id",
        )
        .execute()
        .data[0]
    )
