"""TOON serialization boundary for the Context Bank.

TOON (Token-Oriented Object Notation) is the canonical serialized form of every
context payload. It is a compact encoding of the JSON data model built for
feeding structured data to language models with fewer tokens.

**This module is the only place in the codebase that imports `toon_format`.**
Everything else works with Pydantic models and dicts and calls these functions
at the edges. That keeps TOON from leaking through the repos, services, routers
and UI, and means a future format change touches one file.

Layering:

    ContextContract  ──contract_to_toon──►  TOON text  ──► Postgres (payload_toon)
    ContextContract  ◄──toon_to_contract──  TOON text  ◄── Postgres

Two distinct uses, deliberately separate:
  * `*_to_toon` / `toon_to_*`  — storage round-trip, must be lossless.
  * `entries_to_toon_document` — the agent-facing view, which folds relational
    metadata in beside the payload so an agent gets provenance with the content.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from toon_format import ToonDecodeError, decode, encode

from app.schemas import ContextContract

__all__ = [
    "ToonError",
    "encode_toon",
    "decode_toon",
    "contract_to_toon",
    "toon_to_contract",
    "payload_to_toon",
    "toon_to_payload",
    "entries_to_toon_document",
    "TOON_MEDIA_TYPE",
]

TOON_MEDIA_TYPE = "text/plain; charset=utf-8"


class ToonError(ValueError):
    """Raised when a payload cannot be encoded to, or decoded from, TOON."""


# --- primitive boundary ------------------------------------------------------


def encode_toon(data: Any) -> str:
    """Serialize a JSON-compatible structure to TOON text."""
    try:
        return encode(data)
    except Exception as exc:  # noqa: BLE001 — normalize library errors to one type
        raise ToonError(f"Could not encode payload to TOON: {exc}") from exc


def decode_toon(text: str) -> Any:
    """Parse TOON text back into Python data."""
    if text is None:
        raise ToonError("TOON payload is missing.")
    try:
        return decode(text)
    except ToonDecodeError as exc:
        raise ToonError(f"Malformed TOON payload: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ToonError(f"Could not decode TOON payload: {exc}") from exc


# --- contract round-trip -----------------------------------------------------


def contract_to_toon(contract: ContextContract) -> str:
    """Canonical stored form of a full Context Contract."""
    return encode_toon(contract.model_dump(mode="json"))


def toon_to_contract(text: str) -> ContextContract:
    """Rebuild a Context Contract from stored TOON.

    Raises ToonError for malformed TOON and for TOON that decodes but does not
    satisfy the contract, so callers get one failure type either way.
    """
    data = decode_toon(text)
    if not isinstance(data, Mapping):
        raise ToonError("TOON payload did not decode to an object.")
    try:
        return ContextContract.model_validate(dict(data))
    except Exception as exc:  # noqa: BLE001 — pydantic ValidationError
        raise ToonError(f"TOON payload does not satisfy the Context Contract: {exc}") from exc


# --- per-entry payload round-trip -------------------------------------------


def payload_to_toon(payload: Mapping[str, Any]) -> str:
    """Canonical stored form of a single context entry's payload."""
    return encode_toon(dict(payload))


def toon_to_payload(text: str | None) -> dict[str, Any]:
    """Decode a stored entry payload. Empty/missing text yields an empty dict."""
    if not text or not text.strip():
        return {}
    data = decode_toon(text)
    if not isinstance(data, Mapping):
        raise ToonError("TOON payload did not decode to an object.")
    return dict(data)


# --- agent-facing view -------------------------------------------------------

# Relational metadata an agent needs to judge and trace a statement (§9, §15).
_ENTRY_METADATA_FIELDS = (
    "id",
    "kind",
    "title",
    "version",
    "status",
    "confidence",
    "session_id",
    "author",
    "created_at",
)


def _entry_for_agent(entry: Mapping[str, Any]) -> dict[str, Any]:
    """One entry flattened into metadata + decoded payload."""
    author = entry.get("author")
    author_name = author.get("display_name") if isinstance(author, Mapping) else entry.get("author_user_id")

    out: dict[str, Any] = {
        "id": str(entry.get("id", "")),
        "kind": entry.get("kind"),
        "title": entry.get("title"),
        "version": entry.get("version", 1),
        "status": entry.get("status"),
        "confidence": entry.get("confidence"),
        "session_id": str(entry["session_id"]) if entry.get("session_id") else None,
        "author": author_name,
        "created_at": str(entry.get("created_at", "")),
    }

    payload = entry.get("payload")
    if payload is None and entry.get("payload_toon"):
        payload = toon_to_payload(entry.get("payload_toon"))
    if payload:
        out["payload"] = payload
    return out


def entries_to_toon_document(
    entries: Sequence[Mapping[str, Any]],
    *,
    feature: Mapping[str, Any] | None = None,
    query: Mapping[str, Any] | None = None,
) -> str:
    """Render context entries as one TOON document for an agent.

    Provenance travels with the content: each statement carries its source
    session, author and version, so an agent can answer "where did this come
    from?" without a second call.
    """
    doc: dict[str, Any] = {}
    if feature is not None:
        doc["feature"] = {
            "id": str(feature.get("id", "")),
            "key": feature.get("key"),
            "name": feature.get("name"),
        }
    if query:
        doc["query"] = dict(query)

    doc["count"] = len(entries)
    doc["entries"] = [_entry_for_agent(e) for e in entries]
    return encode_toon(doc)
