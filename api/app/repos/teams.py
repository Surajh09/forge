from __future__ import annotations

from app.db import get_db


def list_teams(org_id: str) -> list[dict]:
    return get_db().table("teams").select("*").eq("clerk_org_id", org_id).order("name").execute().data


def teams_by_id(org_id: str) -> dict[str, dict]:
    return {t["id"]: t for t in list_teams(org_id)}


def get_team(org_id: str, team_id: str) -> dict | None:
    rows = get_db().table("teams").select("*").eq("clerk_org_id", org_id).eq("id", team_id).limit(1).execute().data
    return rows[0] if rows else None


def get_team_by_name(org_id: str, name: str) -> dict | None:
    rows = get_db().table("teams").select("*").eq("clerk_org_id", org_id).eq("name", name).limit(1).execute().data
    return rows[0] if rows else None


def create_team(org_id: str, data: dict) -> dict:
    return get_db().table("teams").insert({**data, "clerk_org_id": org_id}).execute().data[0]


def update_team(org_id: str, team_id: str, data: dict) -> dict | None:
    rows = get_db().table("teams").update(data).eq("clerk_org_id", org_id).eq("id", team_id).execute().data
    return rows[0] if rows else None


def delete_team(org_id: str, team_id: str) -> bool:
    rows = get_db().table("teams").delete().eq("clerk_org_id", org_id).eq("id", team_id).execute().data
    return bool(rows)


def list_members(org_id: str, team_ids: list[str] | None = None) -> list[dict]:
    q = get_db().table("team_members").select("team_id, user_id").eq("clerk_org_id", org_id)
    if team_ids is not None:
        if not team_ids:
            return []
        q = q.in_("team_id", team_ids)
    return q.execute().data


def members_by_team(org_id: str, team_ids: list[str] | None = None) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for row in list_members(org_id, team_ids):
        out.setdefault(row["team_id"], set()).add(row["user_id"])
    return out


def my_team_ids(org_id: str, user_id: str) -> set[str]:
    rows = get_db().table("team_members").select("team_id").eq("clerk_org_id", org_id).eq("user_id", user_id).execute().data
    return {r["team_id"] for r in rows}


def add_member(org_id: str, team_id: str, user_id: str) -> None:
    get_db().table("team_members").upsert(
        {"clerk_org_id": org_id, "team_id": team_id, "user_id": user_id},
        on_conflict="team_id,user_id",
    ).execute()


def remove_member(org_id: str, team_id: str, user_id: str) -> None:
    get_db().table("team_members").delete().eq("clerk_org_id", org_id).eq("team_id", team_id).eq("user_id", user_id).execute()
