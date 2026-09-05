"""Context validation and normalization (phase-1-requirements §8).

Runs before context becomes active Context Bank data. Two responsibilities kept
apart from generation on purpose (design principle 10):

  * `validate_contract`  — is this contract structurally usable?
  * `validate_entry`     — does this entry belong here (org, feature, session)?

Invalid context never silently becomes active. The caller either rejects the
request or stores the entries as `pending_review`.

Pure functions over plain data, so they unit-test without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.schemas import CONTEXT_KINDS, ContextContract, ValidationIssue

# A contract this weak is not worth publishing as trusted context.
MIN_PUBLISHABLE_CONFIDENCE = 0.4


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add(self, field_name: str, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(field=field_name, code=code, message=message))

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.issues.extend(other.issues)
        return self


def _clean_list(values: list[str]) -> list[str]:
    """Trim, drop blanks, de-duplicate, preserve order."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        s = " ".join(str(v).split())
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def normalize_contract(contract: ContextContract) -> ContextContract:
    """Whitespace, blanks and duplicates removed so entries compare cleanly.

    Different models phrase and pad things differently; normalizing here keeps
    the Context Bank consistent regardless of which produced the contract.
    """
    decisions = []
    seen: set[str] = set()
    for d in contract.decisions:
        text = " ".join(d.decision.split())
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        reason = " ".join(d.reason.split()) if d.reason else None
        decisions.append(d.model_copy(update={"decision": text, "reason": reason or None}))

    return contract.model_copy(
        update={
            "objective": " ".join(contract.objective.split()),
            "changes": _clean_list(contract.changes),
            "decisions": decisions,
            "affected_components": _clean_list(contract.affected_components),
            "constraints": _clean_list(contract.constraints),
            "dependencies": _clean_list(contract.dependencies),
            "known_issues": _clean_list(contract.known_issues),
            "open_questions": _clean_list(contract.open_questions),
        }
    )


def validate_contract(contract: ContextContract) -> ValidationResult:
    """Structural checks on a normalized contract.

    Pydantic already enforced types and the confidence range; this catches the
    semantic emptiness it cannot, such as a contract that carries no knowledge.
    """
    result = ValidationResult()

    if not contract.objective.strip():
        result.add("objective", "REQUIRED", "Objective must not be empty.")

    if not (0.0 <= contract.confidence <= 1.0):  # defensive; Pydantic bounds this
        result.add("confidence", "OUT_OF_RANGE", "Confidence must be between 0 and 1.")

    has_substance = any(
        [
            contract.changes,
            contract.decisions,
            contract.constraints,
            contract.known_issues,
            contract.open_questions,
            contract.affected_components,
        ]
    )
    if not has_substance:
        result.add(
            "payload",
            "EMPTY_CONTRACT",
            "Contract carries no changes, decisions, constraints, issues or questions.",
        )

    for i, d in enumerate(contract.decisions):
        if not d.decision.strip():
            result.add(f"decisions[{i}].decision", "REQUIRED", "Decision text must not be empty.")

    return result


def is_publishable(contract: ContextContract) -> bool:
    """Whether validated context is confident enough to go straight to active."""
    return contract.confidence >= MIN_PUBLISHABLE_CONFIDENCE


def validate_entry(
    *,
    org_id: str,
    kind: str,
    feature: Mapping[str, Any] | None,
    session: Mapping[str, Any] | None,
    require_session: bool = False,
    confidence: float | None = None,
) -> ValidationResult:
    """Referential and tenancy checks (§8, §18).

    Enforces that the feature exists, the source session exists, and that both
    belong to the caller's organization. Cross-organization references are
    rejected rather than silently accepted.
    """
    result = ValidationResult()

    if kind not in CONTEXT_KINDS:
        result.add("kind", "UNSUPPORTED_KIND", f"kind must be one of: {', '.join(CONTEXT_KINDS)}.")

    if feature is None:
        result.add("feature_id", "FEATURE_NOT_FOUND", "Feature does not exist.")
    elif feature.get("clerk_org_id") != org_id:
        result.add("feature_id", "CROSS_ORG_FEATURE", "Feature belongs to another organization.")

    if session is None:
        if require_session:
            result.add("session_id", "SESSION_NOT_FOUND", "Source session does not exist.")
    else:
        if session.get("clerk_org_id") != org_id:
            result.add("session_id", "CROSS_ORG_SESSION", "Session belongs to another organization.")
        if feature is not None and session.get("feature_id") != feature.get("id"):
            result.add("session_id", "SESSION_FEATURE_MISMATCH", "Session belongs to a different feature.")

    if confidence is not None and not (0.0 <= confidence <= 1.0):
        result.add("confidence", "OUT_OF_RANGE", "Confidence must be between 0 and 1.")

    return result
