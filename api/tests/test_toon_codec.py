"""TOON serialization boundary: encoding, decoding, round-trip, malformed input."""

import pytest

from app.schemas import ContextContract, Decision
from app.toon_codec import (
    ToonError,
    contract_to_toon,
    entries_to_toon_document,
    payload_to_toon,
    toon_to_contract,
    toon_to_payload,
)

FULL = ContextContract(
    objective="Add refresh-token rotation",
    changes=["Added refresh token rotation", "Updated authentication middleware"],
    decisions=[Decision(decision="Rotation happens server-side", reason="Prevents token reuse")],
    affected_components=["auth/middleware.py", "auth/service.py"],
    constraints=["Existing mobile clients must remain compatible"],
    dependencies=["Token store"],
    known_issues=["Old clients do not support token family revocation"],
    open_questions=["When should old token families expire?"],
    confidence=0.92,
)


def test_contract_round_trip_is_lossless():
    assert toon_to_contract(contract_to_toon(FULL)) == FULL


def test_encoded_output_is_toon_not_json():
    toon = contract_to_toon(FULL)
    assert not toon.lstrip().startswith("{")
    # Tabular header for the array of decision objects, and inline array form.
    assert "decisions[1]{decision,reason}:" in toon
    assert "changes[2]:" in toon
    assert "objective: Add refresh-token rotation" in toon


def test_round_trip_preserves_empty_collections():
    minimal = ContextContract(objective="Only an objective", confidence=0.5)
    assert toon_to_contract(contract_to_toon(minimal)) == minimal


def test_round_trip_preserves_types():
    back = toon_to_contract(contract_to_toon(FULL))
    assert isinstance(back.confidence, float)
    assert back.confidence == 0.92
    assert isinstance(back.decisions[0], Decision)
    assert back.decisions[0].reason == "Prevents token reuse"


def test_round_trip_survives_delimiters_and_newlines():
    tricky = ContextContract(
        objective="Handle commas, colons: and \"quotes\" in text",
        changes=["a, b, c", "key: value", "trailing space "],
        constraints=["100% of requests < 5s"],
        confidence=0.4,
    )
    back = toon_to_contract(contract_to_toon(tricky))
    assert back.objective == tricky.objective
    assert back.changes == tricky.changes
    assert back.constraints == tricky.constraints


def test_payload_round_trip():
    payload = {"decision": "Rotate server-side", "reason": "Prevents reuse"}
    assert toon_to_payload(payload_to_toon(payload)) == payload


def test_empty_payload_decodes_to_empty_dict():
    assert toon_to_payload("") == {}
    assert toon_to_payload(None) == {}
    assert toon_to_payload("   ") == {}


def test_malformed_toon_raises_toon_error():
    with pytest.raises(ToonError):
        toon_to_payload("items[3]{a,b}:\n  1,2\n")  # declares 3 rows, supplies 1


def test_toon_that_decodes_but_violates_contract_raises_toon_error():
    with pytest.raises(ToonError) as exc:
        toon_to_contract("objective: Missing confidence field")
    assert "Context Contract" in str(exc.value)


def test_non_object_toon_raises_toon_error():
    with pytest.raises(ToonError):
        toon_to_payload("just a scalar")


def test_agent_document_carries_provenance():
    entries = [
        {
            "id": "e1",
            "kind": "decision",
            "title": "Rotate server-side",
            "version": 2,
            "status": "active",
            "confidence": 0.9,
            "session_id": "s1",
            "author": {"display_name": "Asha Raman"},
            "created_at": "2026-09-05T10:00:00Z",
            "payload": {"decision": "Rotate server-side", "reason": "Prevents reuse"},
        }
    ]
    doc = entries_to_toon_document(
        entries, feature={"id": "f1", "key": "LOGIN", "name": "Login"}, query={"kinds": "decision"}
    )
    assert "LOGIN" in doc
    assert "Asha Raman" in doc  # author travels with the statement
    assert "s1" in doc  # source session travels with the statement
    assert "count: 1" in doc
    assert not doc.lstrip().startswith("{")


def test_agent_document_decodes_payload_toon_when_needed():
    entries = [
        {
            "id": "e1",
            "kind": "constraint",
            "title": "Amounts are integers",
            "version": 1,
            "status": "active",
            "payload_toon": payload_to_toon({"constraint": "Amounts are integers"}),
        }
    ]
    assert "Amounts are integers" in entries_to_toon_document(entries)


def test_empty_entry_list_produces_valid_document():
    doc = entries_to_toon_document([])
    assert "count: 0" in doc
