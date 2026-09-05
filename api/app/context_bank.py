"""Context Bank write logic: fan-out, versioning, supersede.

Sits between the validator and the repos. Pure enough to test with a fake repo:
`fan_out` takes a contract and returns entry dicts without touching a database.

Fan-out (phase-1-requirements §5.3): a completed session's contract becomes
several typed entries rather than one blob, so a later session can supersede a
single statement instead of replacing everything:

    contract.objective + changes  → one `change` entry
    contract.decisions[]          → one `decision` entry each
    contract.constraints[]        → one `constraint` entry each
    contract.known_issues[]       → one `known_issue` entry each
    contract.open_questions[]     → one `open_question` entry each

`architecture` is available for manually authored entries; the generator does
not infer it.

Versioning (§10): revising an entry writes a NEW row with version+1 and
`supersedes_id` pointing at the old one, and marks the old row `superseded`.
Nothing is overwritten and provenance is carried forward.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.repos import context as context_repo
from app.schemas import ContextContract

# Titles are indexed and displayed; keep them short and stable.
_TITLE_MAX = 300


def _title(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _TITLE_MAX else text[: _TITLE_MAX - 1] + "…"


def fan_out(
    contract: ContextContract,
    *,
    feature_id: str,
    session_id: str | None,
    author_user_id: str | None,
    status: str = "active",
    version: int = 1,
) -> list[dict[str, Any]]:
    """Contract → typed context entries. Pure; performs no I/O."""
    common = {
        "feature_id": feature_id,
        "session_id": session_id,
        "author_user_id": author_user_id,
        "status": status,
        "version": version,
        "confidence": contract.confidence,
    }
    entries: list[dict[str, Any]] = []

    # One `change` entry carrying the objective and what was done.
    entries.append(
        {
            **common,
            "kind": "change",
            "title": _title(contract.objective),
            "payload": {
                "objective": contract.objective,
                "changes": contract.changes,
                "affected_components": contract.affected_components,
                "dependencies": contract.dependencies,
            },
        }
    )

    for d in contract.decisions:
        entries.append(
            {
                **common,
                "kind": "decision",
                "title": _title(d.decision),
                "payload": {"decision": d.decision, "reason": d.reason or ""},
            }
        )

    for c in contract.constraints:
        entries.append({**common, "kind": "constraint", "title": _title(c), "payload": {"constraint": c}})

    for issue in contract.known_issues:
        entries.append({**common, "kind": "known_issue", "title": _title(issue), "payload": {"issue": issue}})

    for q in contract.open_questions:
        entries.append({**common, "kind": "open_question", "title": _title(q), "payload": {"question": q}})

    return entries


def persist_fan_out(org_id: str, entries: list[dict[str, Any]]) -> list[dict]:
    return context_repo.create_entries(org_id, entries)


def revise_entry(
    org_id: str,
    current: Mapping[str, Any],
    *,
    title: str | None = None,
    payload: Mapping[str, Any] | None = None,
    kind: str | None = None,
    confidence: float | None = None,
    author_user_id: str | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> dict:
    """Write a new version of an entry and supersede the old one.

    The new row keeps the original entry's source session, so provenance is not
    lost when context is revised (§9, §10).
    """
    new_row = {
        "feature_id": current["feature_id"],
        "session_id": current.get("session_id"),
        "author_user_id": author_user_id or current.get("author_user_id"),
        "kind": kind or current["kind"],
        "title": title if title is not None else current["title"],
        "payload": dict(payload) if payload is not None else dict(current.get("payload") or {}),
        "confidence": confidence if confidence is not None else current.get("confidence"),
        "status": "active",
        "version": int(current.get("version") or 1) + 1,
        "supersedes_id": current["id"],
        "evidence": dict(evidence) if evidence is not None else current.get("evidence"),
    }
    created = context_repo.create_entry(org_id, new_row)
    context_repo.mark_superseded(org_id, current["id"])
    return created


def supersede_with_statement(
    org_id: str,
    current: Mapping[str, Any],
    *,
    title: str,
    payload: Mapping[str, Any],
    author_user_id: str | None,
    session_id: str | None = None,
    confidence: float | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> dict:
    """Replace a statement with a newer one (the `supersede_context` action).

    Unlike `revise_entry`, the replacement may come from a different session, so
    the new row records that session while the chain still reaches the original.
    """
    new_row = {
        "feature_id": current["feature_id"],
        "session_id": session_id if session_id is not None else current.get("session_id"),
        "author_user_id": author_user_id,
        "kind": current["kind"],
        "title": _title(title),
        "payload": dict(payload),
        "confidence": confidence if confidence is not None else current.get("confidence"),
        "status": "active",
        "version": int(current.get("version") or 1) + 1,
        "supersedes_id": current["id"],
        "evidence": dict(evidence) if evidence is not None else None,
    }
    created = context_repo.create_entry(org_id, new_row)
    context_repo.mark_superseded(org_id, current["id"])
    return created
