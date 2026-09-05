from __future__ import annotations

from typing import Any, Mapping

from app.db import get_db


def get_result(org_id: str, request_id: str) -> dict | None:
    rows = (
        get_db()
        .table("idempotency_keys")
        .select("*")
        .eq("clerk_org_id", org_id)
        .eq("request_id", request_id)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


def put_result(org_id: str, request_id: str, operation: str, result: Mapping[str, Any]) -> None:
    get_db().table("idempotency_keys").upsert(
        {"clerk_org_id": org_id, "request_id": request_id, "operation": operation, "result": dict(result)},
        on_conflict="clerk_org_id,request_id",
    ).execute()
