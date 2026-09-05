from __future__ import annotations

from datetime import datetime, timezone

from app.db import get_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_sessions(org_id: str, *, feature_id: str | None = None, user_id: str | None = None) -> list[dict]:
    q = get_db().table("sessions").select("*").eq("clerk_org_id", org_id)
    if feature_id:
        q = q.eq("feature_id", feature_id)
    if user_id:
        q = q.eq("user_id", user_id)
    return q.order("started_at", desc=True).execute().data


def count_by_feature(org_id: str) -> dict[str, int]:
    rows = get_db().table("sessions").select("feature_id").eq("clerk_org_id", org_id).execute().data
    out: dict[str, int] = {}
    for r in rows:
        out[r["feature_id"]] = out.get(r["feature_id"], 0) + 1
    return out


def get_session(org_id: str, session_id: str) -> dict | None:
    rows = get_db().table("sessions").select("*").eq("clerk_org_id", org_id).eq("id", session_id).limit(1).execute().data
    return rows[0] if rows else None


def create_session(org_id: str, data: dict) -> dict:
    return get_db().table("sessions").insert({**data, "clerk_org_id": org_id}).execute().data[0]


def update_session(org_id: str, session_id: str, data: dict) -> dict | None:
    rows = (
        get_db()
        .table("sessions")
        .update({**data, "updated_at": _now()})
        .eq("clerk_org_id", org_id)
        .eq("id", session_id)
        .execute()
        .data
    )
    return rows[0] if rows else None


def delete_session(org_id: str, session_id: str) -> bool:
    rows = get_db().table("sessions").delete().eq("clerk_org_id", org_id).eq("id", session_id).execute().data
    return bool(rows)
