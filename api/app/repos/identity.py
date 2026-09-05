"""Organization + user rows, created lazily on first authenticated request.

The POC has no Clerk webhooks, so the first time we see a (org, user) pair we
pull the profile from Clerk and persist a snapshot. Role changes in Clerk are
picked up because the cached value is the role, not just "seen".
"""

from __future__ import annotations

from threading import Lock

from app.access import Principal
from app.clerk import fetch_org_profile, fetch_user_profile
from app.db import get_db

_seen_roles: dict[tuple[str, str], str] = {}
_lock = Lock()


def ensure_identity(p: Principal) -> None:
    key = (p.org_id, p.user_id)
    with _lock:
        if _seen_roles.get(key) == p.role:
            return

    db = get_db()

    org = db.table("organizations").select("clerk_org_id").eq("clerk_org_id", p.org_id).limit(1).execute().data
    if not org:
        profile = fetch_org_profile(p.org_id)
        db.table("organizations").upsert(
            {"clerk_org_id": p.org_id, "name": profile["name"], "slug": profile["slug"]},
            on_conflict="clerk_org_id",
        ).execute()

    user = (
        db.table("users")
        .select("id, role")
        .eq("clerk_org_id", p.org_id)
        .eq("id", p.user_id)
        .limit(1)
        .execute()
        .data
    )
    if not user:
        profile = fetch_user_profile(p.user_id)
        db.table("users").upsert(
            {
                "clerk_org_id": p.org_id,
                "id": p.user_id,
                "email": profile["email"],
                "display_name": profile["display_name"],
                "avatar_url": profile["avatar_url"],
                "role": p.role,
                "is_demo": False,
            },
            on_conflict="clerk_org_id,id",
        ).execute()
    elif user[0]["role"] != p.role:
        db.table("users").update({"role": p.role}).eq("clerk_org_id", p.org_id).eq("id", p.user_id).execute()

    with _lock:
        _seen_roles[key] = p.role


def get_org(org_id: str) -> dict | None:
    rows = get_db().table("organizations").select("*").eq("clerk_org_id", org_id).limit(1).execute().data
    return rows[0] if rows else None
