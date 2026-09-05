"""Context Bank persistence (feature-owned, versioned, with provenance).

Payloads are stored TOON-encoded in `payload_toon`. This module is the storage
boundary: rows go out with a decoded `payload` dict attached, and go in with a
`payload` dict that gets encoded. Callers never see TOON text, and the only
import of the codec is `app.toon_codec`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from app.db import get_db
from app.toon_codec import ToonError, payload_to_toon, toon_to_payload

# Columns callers may set; everything else is derived.
_WRITABLE = (
    "feature_id",
    "session_id",
    "author_user_id",
    "kind",
    "version",
    "title",
    "confidence",
    "status",
    "supersedes_id",
    "created_at",
    "updated_at",
    # Evidence (phase-2 §9) is metadata about the statement, kept apart from
    # the TOON payload so it stays queryable and distinguishable.
    "evidence",
    # Set when a statement was flagged as resembling an existing one (§17).
    "conflicts_with",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hydrate(row: dict) -> dict:
    """Attach a decoded `payload` to a DB row.

    A row whose TOON is corrupt is returned with an empty payload plus a
    `payload_error`, so one bad row cannot break a whole feature's retrieval.
    """
    out = dict(row)
    try:
        out["payload"] = toon_to_payload(row.get("payload_toon"))
    except ToonError as exc:
        out["payload"] = {}
        out["payload_error"] = str(exc)
    return out


def _to_row(data: Mapping[str, Any]) -> dict:
    """Build a DB row from caller data, encoding `payload` to TOON."""
    row = {k: v for k, v in data.items() if k in _WRITABLE}
    row["payload_toon"] = payload_to_toon(data.get("payload") or {})
    return row


def _select(org_id: str):
    return get_db().table("context_entries").select("*").eq("clerk_org_id", org_id)


# --- reads -------------------------------------------------------------------


def list_entries(
    org_id: str,
    feature_id: str,
    *,
    statuses: Iterable[str] | None = ("active",),
    kinds: Iterable[str] | None = None,
) -> list[dict]:
    q = _select(org_id).eq("feature_id", feature_id)
    if statuses is not None:
        q = q.in_("status", list(statuses))
    if kinds:
        q = q.in_("kind", list(kinds))
    rows = q.order("created_at", desc=True).execute().data
    return [_hydrate(r) for r in rows]


def get_entry(org_id: str, entry_id: str) -> dict | None:
    rows = _select(org_id).eq("id", entry_id).limit(1).execute().data
    return _hydrate(rows[0]) if rows else None


def list_by_session(org_id: str, session_id: str) -> list[dict]:
    rows = _select(org_id).eq("session_id", session_id).order("created_at").execute().data
    return [_hydrate(r) for r in rows]


def search_entries(
    org_id: str,
    query: str,
    *,
    feature_ids: Iterable[str] | None = None,
    kinds: Iterable[str] | None = None,
    statuses: Iterable[str] | None = ("active",),
    limit: int = 50,
) -> list[dict]:
    """Substring search over title and TOON payload text.

    Deliberately not semantic: Phase 1 uses metadata filtering plus simple text
    matching. TOON is plain text, so the payload is searchable as stored.
    """
    # PostgREST `or` uses commas as separators; strip them from user input.
    needle = query.replace(",", " ").replace("*", "").replace("(", "").replace(")", "").strip()
    if not needle:
        return []

    q = _select(org_id).or_(f"title.ilike.%{needle}%,payload_toon.ilike.%{needle}%")
    if feature_ids is not None:
        ids = list(feature_ids)
        if not ids:
            return []
        q = q.in_("feature_id", ids)
    if kinds:
        q = q.in_("kind", list(kinds))
    if statuses is not None:
        q = q.in_("status", list(statuses))
    rows = q.order("created_at", desc=True).limit(limit).execute().data
    return [_hydrate(r) for r in rows]


def count_by_feature(org_id: str, *, statuses: Iterable[str] | None = ("active",)) -> dict[str, int]:
    q = get_db().table("context_entries").select("feature_id").eq("clerk_org_id", org_id)
    if statuses is not None:
        q = q.in_("status", list(statuses))
    out: dict[str, int] = {}
    for r in q.execute().data:
        out[r["feature_id"]] = out.get(r["feature_id"], 0) + 1
    return out


def version_chain(org_id: str, entry_id: str) -> list[dict]:
    """Walk `supersedes_id` back to version 1, newest first."""
    chain: list[dict] = []
    current = get_entry(org_id, entry_id)
    seen: set[str] = set()
    while current and current["id"] not in seen:
        seen.add(current["id"])
        chain.append(current)
        prev_id = current.get("supersedes_id")
        current = get_entry(org_id, prev_id) if prev_id else None
    return chain


# --- writes ------------------------------------------------------------------


def create_entry(org_id: str, data: Mapping[str, Any]) -> dict:
    row = {**_to_row(data), "clerk_org_id": org_id}
    created = get_db().table("context_entries").insert(row).execute().data[0]
    return _hydrate(created)


def create_entries(org_id: str, rows: list[Mapping[str, Any]]) -> list[dict]:
    if not rows:
        return []
    payload = [{**_to_row(r), "clerk_org_id": org_id} for r in rows]
    created = get_db().table("context_entries").insert(payload).execute().data
    return [_hydrate(r) for r in created]


def update_entry(org_id: str, entry_id: str, data: Mapping[str, Any]) -> dict | None:
    """In-place update. Used for status changes and for marking rows superseded.

    Content revisions go through `context_bank.revise_entry`, which creates a new
    version instead of overwriting.
    """
    row = {k: v for k, v in data.items() if k in _WRITABLE}
    if "payload" in data:
        row["payload_toon"] = payload_to_toon(data["payload"] or {})
    row["updated_at"] = _now()
    rows = (
        get_db()
        .table("context_entries")
        .update(row)
        .eq("clerk_org_id", org_id)
        .eq("id", entry_id)
        .execute()
        .data
    )
    return _hydrate(rows[0]) if rows else None


def mark_superseded(org_id: str, entry_id: str) -> dict | None:
    return update_entry(org_id, entry_id, {"status": "superseded"})
