"""Audit trail for Context Bank actions (phase-2 §15).

Answers: which principal changed which engineering statement, when, under what
authorization, based on what session. Records identifiers and counts only —
never payload content, matching the observability rule in §19 of Phase 1.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from app.access import Principal
from app.repos import audit as audit_repo


def record_audit(
    p: Principal,
    action: str,
    outcome: str,
    *,
    feature_id: str | None = None,
    session_id: str | None = None,
    authorization_result: str = "allow",
    input_meta: Mapping[str, Any] | None = None,
    affected_entry_ids: Iterable[str] = (),
) -> None:
    meta = {k: v for k, v in (input_meta or {}).items() if isinstance(v, (str, int, float, bool, type(None)))}
    audit_repo.insert(
        {
            "clerk_org_id": p.org_id,
            "principal_type": p.principal_type,
            "principal_id": p.user_id,
            "credential_id": p.credential_id,
            "feature_id": feature_id,
            "session_id": session_id,
            "action": action,
            "outcome": outcome,
            "authorization_result": authorization_result,
            "input_meta": meta,
            "affected_entry_ids": [str(e) for e in affected_entry_ids],
        }
    )
