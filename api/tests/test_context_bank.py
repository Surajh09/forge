"""Session completion → typed entries, versioning/superseding, and provenance."""

import pytest
from fastapi import HTTPException

from app import context_actions, services
from app.context_bank import fan_out
from app.schemas import ContextContract, Decision, SessionComplete

CONTRACT = ContextContract(
    objective="Add refresh-token rotation",
    changes=["Added rotation", "Updated middleware"],
    decisions=[
        Decision(decision="Rotation happens server-side", reason="Prevents token reuse"),
        Decision(decision="Token families expire after 30 days", reason="Bounds blast radius"),
    ],
    affected_components=["auth/middleware.py"],
    constraints=["Mobile clients must remain compatible"],
    dependencies=["Token store"],
    known_issues=["Old clients lack family revocation"],
    open_questions=["When should families expire?"],
    confidence=0.92,
)


def complete(world, principal_key="alice", feature_key="payment", contract=CONTRACT, **kw):
    store = world["store"]
    p = world[principal_key]
    session = store.add_session(world[feature_key], p.user_id, **kw)
    return session, services.complete_session(p, session, SessionComplete(context=contract))


# --- fan-out ----------------------------------------------------------------


def test_fan_out_produces_one_entry_per_statement():
    entries = fan_out(CONTRACT, feature_id="f1", session_id="s1", author_user_id="u1")
    kinds = [e["kind"] for e in entries]
    assert kinds.count("change") == 1          # objective + changes
    assert kinds.count("decision") == 2
    assert kinds.count("constraint") == 1
    assert kinds.count("known_issue") == 1
    assert kinds.count("open_question") == 1
    assert len(entries) == 6


def test_fan_out_is_pure_and_carries_provenance():
    entries = fan_out(CONTRACT, feature_id="f1", session_id="s1", author_user_id="u1")
    assert all(e["session_id"] == "s1" and e["author_user_id"] == "u1" for e in entries)
    assert all(e["version"] == 1 and e["status"] == "active" for e in entries)


def test_fan_out_change_entry_holds_objective_and_components():
    change = next(e for e in fan_out(CONTRACT, feature_id="f1", session_id=None, author_user_id=None) if e["kind"] == "change")
    assert change["title"] == CONTRACT.objective
    assert change["payload"]["affected_components"] == ["auth/middleware.py"]


def test_fan_out_of_minimal_contract_still_yields_change_entry():
    minimal = ContextContract(objective="Explored options", changes=["Read the code"], confidence=0.6)
    entries = fan_out(minimal, feature_id="f1", session_id="s1", author_user_id="u1")
    assert [e["kind"] for e in entries] == ["change"]


# --- completion -------------------------------------------------------------


def test_completion_creates_multiple_typed_entries(world):
    _session, result = complete(world)
    assert len(result.context_entries) == 6
    assert result.session.status == "completed"
    assert not result.quarantined
    assert {e.kind for e in result.context_entries} == {
        "change", "decision", "constraint", "known_issue", "open_question",
    }


def test_completion_round_trips_payload_through_toon(world):
    _session, result = complete(world)
    decision = next(e for e in result.context_entries if e.kind == "decision")
    assert decision.payload["reason"] in {"Prevents token reuse", "Bounds blast radius"}


def test_completion_records_provenance_to_session_and_author(world):
    session, result = complete(world)
    for e in result.context_entries:
        assert e.session_id == session["id"]
        assert e.author_user_id == "user_alice"
        assert e.author is not None and e.author.display_name == "Alice"
        assert e.session is not None and e.session.id == session["id"]


def test_completion_without_contract_uses_generator_and_quarantines(world):
    store = world["store"]
    p = world["alice"]
    session = store.add_session(world["payment"], p.user_id, goal="Investigate flaky test", summary="Looked into it.")
    result = services.complete_session(p, session, SessionComplete())

    assert result.generated is True
    assert result.quarantined is True, "metadata-derived context must not publish as trusted"
    assert all(e.status == "pending_review" for e in result.context_entries)


def test_completion_is_idempotent(world):
    store = world["store"]
    p = world["alice"]
    session = store.add_session(world["payment"], p.user_id)

    first = services.complete_session(p, session, SessionComplete(context=CONTRACT))
    reloaded = next(s for s in store.sessions if s["id"] == session["id"])
    second = services.complete_session(p, reloaded, SessionComplete(context=CONTRACT))

    assert second.idempotent_replay is True
    assert len(store.entries) == len(first.context_entries), "replay must not duplicate active context"
    assert {e.id for e in second.context_entries} == {e.id for e in first.context_entries}


def test_invalid_contract_is_rejected_and_publishes_nothing(world):
    store = world["store"]
    p = world["alice"]
    session = store.add_session(world["payment"], p.user_id)
    empty = ContextContract(objective="Nothing to report", confidence=0.9)

    with pytest.raises(HTTPException) as exc:
        services.complete_session(p, session, SessionComplete(context=empty))

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "CONTEXT_INVALID"
    assert store.entries == [], "no context may be written when validation fails"
    assert session["status"] == "active", "the session must be preserved"


# --- versioning / superseding ------------------------------------------------


def test_supersede_creates_new_version_and_keeps_the_old(world):
    _session, result = complete(world)
    original = next(e for e in result.context_entries if e.kind == "decision")

    replacement = context_actions.supersede_context(
        world["alice"],
        original.id,
        title="Rotation happens at the edge",
        payload={"decision": "Rotation happens at the edge", "reason": "Cheaper"},
        confidence=0.8,
    )

    assert replacement["version"] == original.version + 1
    assert replacement["supersedes_id"] == original.id
    assert replacement["status"] == "active"

    old = context_actions.context_repo.get_entry(world["alice"].org_id, original.id)
    assert old["status"] == "superseded", "the old statement must remain recoverable"
    assert old["payload"]["decision"] == "Rotation happens server-side"


def test_superseded_entry_drops_out_of_active_retrieval(world):
    _session, result = complete(world)
    original = next(e for e in result.context_entries if e.kind == "decision")
    context_actions.supersede_context(
        world["alice"], original.id, title="New decision", payload={"decision": "New decision"}
    )

    _payload, rows = context_actions.get_feature_context(world["alice"], world["payment"]["id"])
    ids = {r["id"] for r in rows}
    assert original.id not in ids
    assert len(rows) == 6, "one replaced, one added"


def test_supersede_twice_is_rejected(world):
    _session, result = complete(world)
    original = next(e for e in result.context_entries if e.kind == "constraint")
    context_actions.supersede_context(world["alice"], original.id, title="v2", payload={"constraint": "v2"})

    with pytest.raises(HTTPException) as exc:
        context_actions.supersede_context(world["alice"], original.id, title="v3", payload={"constraint": "v3"})
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "ALREADY_SUPERSEDED"


def test_version_chain_reaches_the_original(world):
    _session, result = complete(world)
    v1 = next(e for e in result.context_entries if e.kind == "constraint")
    v2 = context_actions.supersede_context(world["alice"], v1.id, title="v2", payload={"constraint": "v2"})
    v3 = context_actions.supersede_context(world["alice"], v2["id"], title="v3", payload={"constraint": "v3"})

    chain = context_actions.context_repo.version_chain(world["alice"].org_id, v3["id"])
    assert [c["version"] for c in chain] == [3, 2, 1]
    assert chain[-1]["id"] == v1.id


def test_supersede_preserves_source_session_when_none_given(world):
    session, result = complete(world)
    original = next(e for e in result.context_entries if e.kind == "known_issue")
    replacement = context_actions.supersede_context(
        world["alice"], original.id, title="Fixed", payload={"issue": "Fixed"}
    )
    assert replacement["session_id"] == session["id"], "provenance must not be discarded on revision"
