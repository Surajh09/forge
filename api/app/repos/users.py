from __future__ import annotations

from app.db import get_db


def list_users(org_id: str) -> list[dict]:
    return get_db().table("users").select("*").eq("clerk_org_id", org_id).order("display_name").execute().data


def get_user(org_id: str, user_id: str) -> dict | None:
    rows = get_db().table("users").select("*").eq("clerk_org_id", org_id).eq("id", user_id).limit(1).execute().data
    return rows[0] if rows else None


def users_by_id(org_id: str) -> dict[str, dict]:
    return {u["id"]: u for u in list_users(org_id)}


def upsert_users(org_id: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    payload = [{**r, "clerk_org_id": org_id} for r in rows]
    get_db().table("users").upsert(payload, on_conflict="clerk_org_id,id").execute()
    return len(payload)
