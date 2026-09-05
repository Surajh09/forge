from __future__ import annotations

from datetime import datetime, timezone

from app.db import get_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_features(org_id: str) -> list[dict]:
    return get_db().table("features").select("*").eq("clerk_org_id", org_id).order("key").execute().data


def get_feature(org_id: str, feature_id: str) -> dict | None:
    rows = get_db().table("features").select("*").eq("clerk_org_id", org_id).eq("id", feature_id).limit(1).execute().data
    return rows[0] if rows else None


def get_feature_by_key(org_id: str, key: str) -> dict | None:
    rows = get_db().table("features").select("*").eq("clerk_org_id", org_id).eq("key", key).limit(1).execute().data
    return rows[0] if rows else None


def create_feature(org_id: str, data: dict, created_by: str | None) -> dict:
    row = {**data, "clerk_org_id": org_id, "created_by": created_by}
    return get_db().table("features").insert(row).execute().data[0]


def update_feature(org_id: str, feature_id: str, data: dict) -> dict | None:
    rows = (
        get_db()
        .table("features")
        .update({**data, "updated_at": _now()})
        .eq("clerk_org_id", org_id)
        .eq("id", feature_id)
        .execute()
        .data
    )
    return rows[0] if rows else None


def delete_feature(org_id: str, feature_id: str) -> bool:
    rows = get_db().table("features").delete().eq("clerk_org_id", org_id).eq("id", feature_id).execute().data
    return bool(rows)


# --- feature ↔ team / user links -------------------------------------------


def feature_teams(org_id: str, feature_ids: list[str] | None = None) -> list[dict]:
    q = get_db().table("feature_teams").select("feature_id, team_id").eq("clerk_org_id", org_id)
    if feature_ids is not None:
        if not feature_ids:
            return []
        q = q.in_("feature_id", feature_ids)
    return q.execute().data


def feature_assignments(org_id: str, feature_ids: list[str] | None = None) -> list[dict]:
    q = get_db().table("feature_assignments").select("feature_id, user_id").eq("clerk_org_id", org_id)
    if feature_ids is not None:
        if not feature_ids:
            return []
        q = q.in_("feature_id", feature_ids)
    return q.execute().data


def add_team(org_id: str, feature_id: str, team_id: str) -> None:
    get_db().table("feature_teams").upsert(
        {"clerk_org_id": org_id, "feature_id": feature_id, "team_id": team_id},
        on_conflict="feature_id,team_id",
    ).execute()


def remove_team(org_id: str, feature_id: str, team_id: str) -> None:
    get_db().table("feature_teams").delete().eq("clerk_org_id", org_id).eq("feature_id", feature_id).eq("team_id", team_id).execute()


def add_assignee(org_id: str, feature_id: str, user_id: str) -> None:
    get_db().table("feature_assignments").upsert(
        {"clerk_org_id": org_id, "feature_id": feature_id, "user_id": user_id},
        on_conflict="feature_id,user_id",
    ).execute()


def remove_assignee(org_id: str, feature_id: str, user_id: str) -> None:
    get_db().table("feature_assignments").delete().eq("clerk_org_id", org_id).eq("feature_id", feature_id).eq("user_id", user_id).execute()
