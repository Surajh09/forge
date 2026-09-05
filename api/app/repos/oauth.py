"""Persistence for the OAuth authorization server and agent grants.

Secrets (codes, access tokens, refresh tokens) are stored only as SHA-256
hashes; the plaintext exists once, in the response that issued it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.db import get_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- clients (RFC 7591 dynamic registration) --------------------------------


def get_client(client_id: str) -> dict | None:
    rows = get_db().table("oauth_clients").select("*").eq("client_id", client_id).limit(1).execute().data
    return rows[0] if rows else None


def save_client(client_id: str, *, client_name: str | None, redirect_uris: list[str], client_info: Mapping[str, Any]) -> dict:
    row = {
        "client_id": client_id,
        "client_name": client_name,
        "redirect_uris": list(redirect_uris),
        "client_info": dict(client_info),
    }
    return get_db().table("oauth_clients").upsert(row, on_conflict="client_id").execute().data[0]


# --- pending authorizations (awaiting consent) --------------------------------


def create_pending(client_id: str, params: Mapping[str, Any], expires_at: datetime) -> dict:
    row = {"client_id": client_id, "params": dict(params), "expires_at": expires_at.isoformat()}
    return get_db().table("oauth_pending_authorizations").insert(row).execute().data[0]


def get_pending(pending_id: str) -> dict | None:
    rows = (
        get_db().table("oauth_pending_authorizations").select("*").eq("id", pending_id).limit(1).execute().data
    )
    return rows[0] if rows else None


def consume_pending(pending_id: str) -> dict | None:
    """Claim a pending authorization exactly once.

    The conditional update is the concurrency boundary for browser approval and
    denial.  A second request receives no row rather than creating a second
    grant or redirect.
    """
    rows = (
        get_db()
        .table("oauth_pending_authorizations")
        .update({"consumed_at": _now()})
        .eq("id", pending_id)
        .is_("consumed_at", "null")
        .execute()
        .data
    )
    return rows[0] if rows else None


# --- agent grants (the §5.1 credential) ---------------------------------------


def create_grant(
    org_id: str,
    *,
    user_id: str,
    client_id: str,
    client_name: str | None,
    scopes: list[str],
    feature_ids: list[str] | None,
    expires_at: datetime | None,
) -> dict:
    row = {
        "clerk_org_id": org_id,
        "user_id": user_id,
        "client_id": client_id,
        "client_name": client_name,
        "scopes": list(scopes),
        "feature_ids": list(feature_ids) if feature_ids is not None else None,
        "status": "active",
        "expires_at": expires_at.isoformat() if expires_at else None,
    }
    return get_db().table("agent_grants").insert(row).execute().data[0]


def get_grant(grant_id: str) -> dict | None:
    rows = get_db().table("agent_grants").select("*").eq("id", grant_id).limit(1).execute().data
    return rows[0] if rows else None


def list_grants(org_id: str, *, user_id: str | None = None) -> list[dict]:
    q = get_db().table("agent_grants").select("*").eq("clerk_org_id", org_id)
    if user_id:
        q = q.eq("user_id", user_id)
    return q.order("created_at", desc=True).execute().data


def revoke_grant(org_id: str, grant_id: str) -> dict | None:
    rows = (
        get_db()
        .table("agent_grants")
        .update({"status": "revoked", "revoked_at": _now()})
        .eq("clerk_org_id", org_id)
        .eq("id", grant_id)
        .execute()
        .data
    )
    if rows:
        get_db().table("oauth_tokens").update({"revoked_at": _now()}).eq("grant_id", grant_id).is_("revoked_at", "null").execute()
    return rows[0] if rows else None


def touch_grant(grant_id: str) -> None:
    get_db().table("agent_grants").update({"last_used_at": _now()}).eq("id", grant_id).execute()


# --- authorization codes ------------------------------------------------------


def save_code(code_hash: str, data: Mapping[str, Any]) -> dict:
    return get_db().table("oauth_authorization_codes").insert({**dict(data), "code_hash": code_hash}).execute().data[0]


def get_code(code_hash: str) -> dict | None:
    rows = get_db().table("oauth_authorization_codes").select("*").eq("code_hash", code_hash).limit(1).execute().data
    return rows[0] if rows else None


def consume_code(code_hash: str, client_id: str) -> dict | None:
    """Claim an authorization code exactly once before issuing tokens."""
    rows = (
        get_db()
        .table("oauth_authorization_codes")
        .update({"used_at": _now()})
        .eq("code_hash", code_hash)
        .eq("client_id", client_id)
        .is_("used_at", "null")
        .execute()
        .data
    )
    return rows[0] if rows else None


# --- tokens -------------------------------------------------------------------


def save_token(token_hash: str, data: Mapping[str, Any]) -> dict:
    return get_db().table("oauth_tokens").insert({**dict(data), "token_hash": token_hash}).execute().data[0]


def get_token(token_hash: str) -> dict | None:
    rows = get_db().table("oauth_tokens").select("*").eq("token_hash", token_hash).limit(1).execute().data
    return rows[0] if rows else None


def revoke_token(token_hash: str) -> None:
    get_db().table("oauth_tokens").update({"revoked_at": _now()}).eq("token_hash", token_hash).execute()


def touch_token(token_hash: str) -> None:
    get_db().table("oauth_tokens").update({"last_used_at": _now()}).eq("token_hash", token_hash).execute()
