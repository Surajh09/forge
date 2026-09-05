from __future__ import annotations

from typing import Any, Mapping

from app.db import get_db


def insert(row: Mapping[str, Any]) -> dict:
    return get_db().table("audit_log").insert(dict(row)).execute().data[0]


def list_for_org(org_id: str, *, limit: int = 100, credential_id: str | None = None) -> list[dict]:
    q = get_db().table("audit_log").select("*").eq("clerk_org_id", org_id)
    if credential_id:
        q = q.eq("credential_id", credential_id)
    return q.order("created_at", desc=True).limit(limit).execute().data
