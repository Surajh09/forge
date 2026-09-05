"""Context generation, normalization and validation."""

import pytest
from pydantic import ValidationError

from app.context_generator import DERIVED_CONFIDENCE, DeterministicGenerator
from app.context_validation import (
    MIN_PUBLISHABLE_CONFIDENCE,
    is_publishable,
    normalize_contract,
    validate_contract,
    validate_entry,
)
from app.schemas import ContextContract, Decision

ORG = "org_1"
FEATURE = {"id": "f1", "clerk_org_id": ORG, "key": "LOGIN"}
SESSION = {"id": "s1", "clerk_org_id": ORG, "feature_id": "f1"}


def contract(**kw) -> ContextContract:
    base = {"objective": "Do a thing", "changes": ["Did the thing"], "confidence": 0.8}
    return ContextContract(**{**base, **kw})


# --- contract schema --------------------------------------------------------


def test_confidence_out_of_range_rejected_by_schema():
    with pytest.raises(ValidationError):
        contract(confidence=1.5)
    with pytest.raises(ValidationError):
        contract(confidence=-0.1)


def test_empty_objective_rejected_by_schema():
    with pytest.raises(ValidationError):
        contract(objective="")


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        ContextContract(objective="x", confidence=0.5, sneaky="value")


# --- normalization ----------------------------------------------------------


def test_normalize_trims_dedupes_and_drops_blanks():
    c = contract(changes=["  Added rotation ", "Added rotation", "", "   ", "Updated middleware"])
    assert normalize_contract(c).changes == ["Added rotation", "Updated middleware"]


def test_normalize_collapses_internal_whitespace():
    assert normalize_contract(contract(objective="Add    refresh\n\ttoken")).objective == "Add refresh token"


def test_normalize_dedupes_decisions_case_insensitively():
    c = contract(
        decisions=[
            Decision(decision="Rotate server-side", reason="Safety"),
            Decision(decision="rotate SERVER-side", reason="Duplicate"),
        ]
    )
    assert len(normalize_contract(c).decisions) == 1


def test_normalize_is_idempotent():
    once = normalize_contract(contract(changes=["  a  ", "a", "b"]))
    assert normalize_contract(once) == once


# --- contract validation ----------------------------------------------------


def test_valid_contract_passes():
    assert validate_contract(contract()).ok


def test_contract_with_no_substance_is_rejected():
    result = validate_contract(ContextContract(objective="Nothing happened", confidence=0.9))
    assert not result.ok
    assert result.issues[0].code == "EMPTY_CONTRACT"


def test_contract_with_only_open_questions_has_substance():
    assert validate_contract(
        ContextContract(objective="Explored options", open_questions=["Which store?"], confidence=0.5)
    ).ok


def test_publishable_threshold():
    assert is_publishable(contract(confidence=MIN_PUBLISHABLE_CONFIDENCE))
    assert not is_publishable(contract(confidence=MIN_PUBLISHABLE_CONFIDENCE - 0.01))


# --- referential / tenancy validation ---------------------------------------


def test_valid_entry_passes():
    assert validate_entry(org_id=ORG, kind="decision", feature=FEATURE, session=SESSION).ok


def test_unsupported_kind_rejected():
    result = validate_entry(org_id=ORG, kind="session_summary", feature=FEATURE, session=SESSION)
    assert not result.ok
    assert any(i.code == "UNSUPPORTED_KIND" for i in result.issues)


def test_missing_feature_rejected():
    result = validate_entry(org_id=ORG, kind="decision", feature=None, session=SESSION)
    assert any(i.code == "FEATURE_NOT_FOUND" for i in result.issues)


def test_cross_org_feature_rejected():
    other = {**FEATURE, "clerk_org_id": "org_2"}
    result = validate_entry(org_id=ORG, kind="decision", feature=other, session=SESSION)
    assert any(i.code == "CROSS_ORG_FEATURE" for i in result.issues)


def test_cross_org_session_rejected():
    other = {**SESSION, "clerk_org_id": "org_2"}
    result = validate_entry(org_id=ORG, kind="decision", feature=FEATURE, session=other)
    assert any(i.code == "CROSS_ORG_SESSION" for i in result.issues)


def test_session_from_another_feature_rejected():
    other = {**SESSION, "feature_id": "f2"}
    result = validate_entry(org_id=ORG, kind="decision", feature=FEATURE, session=other)
    assert any(i.code == "SESSION_FEATURE_MISMATCH" for i in result.issues)


def test_missing_required_session_rejected():
    result = validate_entry(
        org_id=ORG, kind="decision", feature=FEATURE, session=None, require_session=True
    )
    assert any(i.code == "SESSION_NOT_FOUND" for i in result.issues)


def test_missing_optional_session_allowed():
    assert validate_entry(org_id=ORG, kind="decision", feature=FEATURE, session=None).ok


# --- generator --------------------------------------------------------------


def test_generator_never_writes_and_returns_a_contract():
    session = {"goal": "Add rotation", "summary": "Rotated tokens. Updated middleware.", "agent": "claude-code"}
    c = DeterministicGenerator().generate(session)
    assert isinstance(c, ContextContract)
    assert c.objective == "Add rotation"
    assert c.changes == ["Rotated tokens.", "Updated middleware."]


def test_generator_is_deterministic():
    session = {"goal": "Add rotation", "summary": "Did it.", "agent": "cursor"}
    g = DeterministicGenerator()
    assert g.generate(session) == g.generate(session)


def test_generated_context_is_low_confidence_and_flags_itself():
    c = DeterministicGenerator().generate({"goal": "Something", "agent": "manual"})
    assert c.confidence == DERIVED_CONFIDENCE
    assert not is_publishable(c)  # quarantined rather than published
    assert c.open_questions, "generated context should declare its own uncertainty"


def test_generator_handles_session_with_no_goal_or_summary():
    c = DeterministicGenerator().generate({"agent": "claude-code", "model": "claude-opus-5"})
    assert c.objective
    assert validate_contract(c).ok  # open_questions give it substance
