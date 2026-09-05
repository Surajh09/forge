"""Authorization on the Context Bank and the agent actions.

The rule under test (phase-1-requirements §12): a user who cannot access a
feature must not be able to retrieve its context by calling the API directly.
"""

import pytest
from fastapi import HTTPException

from app import context_actions, services
from app.access import Principal
from app.schemas import ContextContract, SessionComplete
from app.toon_codec import entries_to_toon_document
from tests.conftest import OTHER_ORG

CONTRACT = ContextContract(
    objective="Ship the payment reconciler",
    changes=["Added reconciliation job"],
    constraints=["Amounts are integer minor units"],
    confidence=0.9,
)

SECRET_CONTRACT = ContextContract(
    objective="Classified platform work",
    changes=["Touched the vault"],
    constraints=["Do not disclose"],
    confidence=0.9,
)


def seed_context(world, feature_key, principal_key):
    store, p = world["store"], world[principal_key]
    session = store.add_session(world[feature_key], p.user_id)
    contract = SECRET_CONTRACT if feature_key == "secret" else CONTRACT
    return services.complete_session(p, session, SessionComplete(context=contract))


# --- feature-scoped reads ---------------------------------------------------


def test_member_of_owning_team_can_read_context(world):
    seed_context(world, "payment", "bob")
    _payload, rows = context_actions.get_feature_context(world["alice"], world["payment"]["id"])
    assert rows, "alice is on the Payments team that owns PAYMENT"


def test_directly_assigned_user_can_read_context(world):
    seed_context(world, "login", "carol")
    _payload, rows = context_actions.get_feature_context(world["alice"], world["login"]["id"])
    assert rows, "alice is directly assigned to LOGIN"


def test_unauthorized_user_cannot_read_feature_context(world):
    seed_context(world, "secret", "carol")
    with pytest.raises(HTTPException) as exc:
        context_actions.get_feature_context(world["alice"], world["secret"]["id"])
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "FEATURE_FORBIDDEN"


def test_unauthorized_user_cannot_read_by_kind(world):
    seed_context(world, "secret", "carol")
    with pytest.raises(HTTPException) as exc:
        context_actions.get_context_by_kind(world["alice"], world["secret"]["id"], ["constraint"])
    assert exc.value.status_code == 403


def test_admin_can_read_any_feature_in_the_org(world):
    seed_context(world, "secret", "carol")
    _payload, rows = context_actions.get_feature_context(world["admin"], world["secret"]["id"])
    assert rows


# --- direct entry access ----------------------------------------------------


def test_unauthorized_user_cannot_fetch_an_entry_by_id(world):
    """Guessing a context id must not bypass the feature boundary."""
    result = seed_context(world, "secret", "carol")
    entry_id = result.context_entries[0].id

    with pytest.raises(HTTPException) as exc:
        services.load_entry_for_read(world["alice"], entry_id)
    assert exc.value.status_code == 403


def test_unauthorized_user_cannot_supersede_an_entry(world):
    result = seed_context(world, "secret", "carol")
    entry_id = result.context_entries[0].id

    with pytest.raises(HTTPException) as exc:
        context_actions.supersede_context(
            world["alice"], entry_id, title="Injected", payload={"constraint": "Injected"}
        )
    assert exc.value.status_code == 403


def test_unauthorized_user_cannot_record_context(world):
    with pytest.raises(HTTPException) as exc:
        context_actions.record_context(
            world["alice"],
            world["secret"]["id"],
            kind="decision",
            title="Injected",
            payload={"decision": "Injected"},
        )
    assert exc.value.status_code == 403


# --- search -----------------------------------------------------------------


def test_search_never_returns_unauthorized_context(world):
    seed_context(world, "secret", "carol")
    seed_context(world, "payment", "bob")

    _payload, rows = context_actions.search_context(world["alice"], "Do not disclose")
    assert rows == [], "SECRET context must not surface for a user without access"

    _payload, rows = context_actions.search_context(world["alice"], "integer minor units")
    assert rows, "PAYMENT context is searchable by an authorized user"


def test_search_scoped_to_an_unauthorized_feature_is_forbidden(world):
    seed_context(world, "secret", "carol")
    with pytest.raises(HTTPException) as exc:
        context_actions.search_context(world["alice"], "vault", feature_id=world["secret"]["id"])
    assert exc.value.status_code == 403


def test_search_matches_payload_text_not_just_titles(world):
    seed_context(world, "payment", "bob")
    _payload, rows = context_actions.search_context(world["alice"], "reconciliation job")
    assert rows, "payload contents are searchable through the stored TOON"


# --- tenancy ----------------------------------------------------------------


def test_other_organization_cannot_reach_context(world):
    """Same ids, different tenant: every lookup is org-scoped."""
    result = seed_context(world, "payment", "alice")
    intruder = Principal(user_id="user_alice", org_id=OTHER_ORG, role="admin")

    with pytest.raises(HTTPException) as exc:
        context_actions.get_feature_context(intruder, world["payment"]["id"])
    assert exc.value.status_code == 404, "a foreign feature is invisible, not merely forbidden"

    with pytest.raises(HTTPException) as exc:
        services.load_entry_for_read(intruder, result.context_entries[0].id)
    assert exc.value.status_code == 404


def test_cross_org_session_reference_is_rejected(world):
    """A context entry may not cite a session from another organization (§18)."""
    store = world["store"]
    foreign_feature = store.add_feature("FOREIGN", org=OTHER_ORG)
    store.add_user("user_ghost", "Ghost", org=OTHER_ORG)
    foreign_session = store.add_session(foreign_feature, "user_ghost")

    with pytest.raises(HTTPException) as exc:
        context_actions.record_context(
            world["alice"],
            world["payment"]["id"],
            kind="decision",
            title="Cross-tenant reference",
            payload={"decision": "x"},
            session_id=foreign_session["id"],
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "CONTEXT_INVALID"


# --- agent retrieval --------------------------------------------------------


def test_agent_document_is_toon_and_authorized(world):
    seed_context(world, "payment", "bob")
    payload, rows = context_actions.get_feature_context(world["alice"], world["payment"]["id"])
    doc = entries_to_toon_document(rows, feature=payload["feature"], query=payload["query"])

    assert not doc.lstrip().startswith("{"), "agents receive TOON, not JSON"
    assert "PAYMENT" in doc
    assert "Ship the payment reconciler" in doc


def test_agent_kind_filter_narrows_results(world):
    seed_context(world, "payment", "bob")
    _payload, all_rows = context_actions.get_feature_context(world["alice"], world["payment"]["id"])
    _payload, only = context_actions.get_context_by_kind(
        world["alice"], world["payment"]["id"], ["constraint"]
    )
    assert 0 < len(only) < len(all_rows)
    assert {r["kind"] for r in only} == {"constraint"}


def test_unsupported_kind_is_rejected(world):
    with pytest.raises(HTTPException) as exc:
        context_actions.get_context_by_kind(world["alice"], world["payment"]["id"], ["session_summary"])
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "UNSUPPORTED_KIND"


def test_record_context_then_agent_can_read_it_back(world):
    created = context_actions.record_context(
        world["alice"],
        world["payment"]["id"],
        kind="architecture",
        title="Ledger is append-only",
        payload={"note": "Never mutate posted entries"},
        confidence=0.95,
    )
    _payload, rows = context_actions.get_context_by_kind(
        world["alice"], world["payment"]["id"], ["architecture"]
    )
    assert [r["id"] for r in rows] == [created["id"]]
    assert rows[0]["payload"]["note"] == "Never mutate posted entries"
