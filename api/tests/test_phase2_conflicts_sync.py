"""Conflict flagging (§17) and Local Context Store synchronization (§10, §11)."""

from __future__ import annotations

import pytest

from app import context_actions
from app.auth import get_principal
from app.conflicts import SIMILARITY_THRESHOLD, find_conflict, similarity
from app.main import app

# --- the similarity rule, as pure functions -----------------------------------


def test_reworded_claim_is_similar_and_unrelated_one_is_not():
    a = "Payment retries use idempotency keys"
    assert similarity(a, "Retries for payments use an idempotency key") >= SIMILARITY_THRESHOLD
    assert similarity(a, "Magic-link sign-in tokens expire after 15 minutes") < SIMILARITY_THRESHOLD


def test_conflict_only_compares_the_same_kind():
    existing = [
        {"id": "e1", "kind": "constraint", "status": "active",
         "title": "Amounts are integer minor units", "payload": {"constraint": "Amounts are integer minor units"}},
    ]
    same_words_other_kind = find_conflict(
        kind="decision", title="Amounts are integer minor units",
        payload={"decision": "Amounts are integer minor units"}, existing=existing,
    )
    assert same_words_other_kind is None, "a decision and the constraint it implies are not a conflict"

    same_kind = find_conflict(
        kind="constraint", title="Amounts are stored as integer minor units",
        payload={"constraint": "Amounts are stored as integer minor units"}, existing=existing,
    )
    assert same_kind is not None and same_kind.entry_id == "e1"


def test_superseded_entries_are_not_conflict_candidates():
    existing = [{"id": "old", "kind": "decision", "status": "superseded",
                 "title": "Rotate tokens server-side", "payload": {"decision": "Rotate tokens server-side"}}]
    assert find_conflict(kind="decision", title="Rotate tokens server-side",
                         payload={"decision": "Rotate tokens server-side"}, existing=existing) is None


def test_supporting_detail_does_not_drive_the_match():
    """Two different claims that happen to share a long rationale are not conflicts."""
    shared = "Because Stripe retries aggressively and duplicate processing caused double refunds in staging"
    existing = [{"id": "e1", "kind": "decision", "status": "active",
                 "title": "Webhooks must be idempotent by event id",
                 "payload": {"decision": "Webhooks must be idempotent by event id", "reason": shared}}]
    assert find_conflict(kind="decision", title="Settlement reports reconcile nightly",
                         payload={"decision": "Settlement reports reconcile nightly", "reason": shared},
                         existing=existing) is None


# --- flagging on the write path -------------------------------------------------


def test_duplicate_statement_is_quarantined_and_linked(world, infra):
    p = world["agent_rw"]
    first = context_actions.record_context(
        p, world["payment"]["id"], kind="known_issue",
        title="Refund ledger double-posts when webhook retries overlap",
        payload={"issue": "Refund ledger double-posts when webhook retries overlap"}, confidence=0.7,
    )
    assert first["status"] == "active" and first["conflicts_with"] is None

    second = context_actions.record_context(
        p, world["payment"]["id"], kind="known_issue",
        title="The refund ledger double-posts when two webhook retries overlap",
        payload={"issue": "The refund ledger double-posts when two webhook retries overlap"}, confidence=0.7,
    )
    # Never silently duplicated, never auto-merged, both readable.
    assert second["status"] == "pending_review"
    assert second["conflicts_with"] == first["id"]
    assert len(world["store"].entries) == 2

    flagged = infra.audit_rows(action="context.record_context", outcome="flagged")
    assert flagged and flagged[0]["input_meta"]["conflicts_with"] == first["id"]


def test_a_genuinely_new_statement_publishes_normally(world):
    p = world["agent_rw"]
    context_actions.record_context(
        p, world["payment"]["id"], kind="decision", title="Stripe is the only payment provider",
        payload={"decision": "Stripe is the only payment provider"},
    )
    other = context_actions.record_context(
        p, world["payment"]["id"], kind="decision", title="Settlement files are archived for seven years",
        payload={"decision": "Settlement files are archived for seven years"},
    )
    assert other["status"] == "active" and other["conflicts_with"] is None


def test_flagged_entry_reaches_the_review_queue(world):
    from app import services

    p = world["agent_rw"]
    context_actions.record_context(p, world["payment"]["id"], kind="constraint",
                                   title="Webhook handler must finish under five seconds",
                                   payload={"constraint": "Webhook handler must finish under five seconds"})
    context_actions.record_context(p, world["payment"]["id"], kind="constraint",
                                   title="The webhook handler must finish in under 5 seconds",
                                   payload={"constraint": "The webhook handler must finish in under 5 seconds"})
    pending = services.pending_context(world["alice"])
    assert len(pending) == 1 and pending[0].conflicts_with is not None


# --- sync ------------------------------------------------------------------------


@pytest.fixture
def rest(http, world):
    def as_principal(p):
        app.dependency_overrides[get_principal] = lambda: p
        return http

    try:
        yield as_principal
    finally:
        app.dependency_overrides.clear()


CLIENT = "local-store-0001"


def test_pull_is_incremental_and_push_is_idempotent(world, rest):
    c = rest(world["agent_rw"])
    fid = world["payment"]["id"]

    context_actions.record_context(world["alice"], fid, kind="decision", title="Seeded before first pull",
                                   payload={"decision": "Seeded before first pull"})

    first = c.get(f"/api/v1/sync/features/{fid}", params={"client_id": CLIENT, "label": "laptop"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["total"] == 1 and len(body["entries"]) == 1
    cursor = body["cursor"]
    assert cursor

    # Nothing new: an incremental pull transfers nothing but still reports the total.
    again = c.get(f"/api/v1/sync/features/{fid}", params={"client_id": CLIENT, "since": cursor}).json()
    assert again["entries"] == [] and again["total"] == 1

    # Offline capture, then drain the queue.
    payload = {
        "client_id": CLIENT,
        "label": "laptop",
        "entries": [
            {"kind": "constraint", "title": "Captured while offline",
             "payload": {"constraint": "Captured while offline"}, "request_id": "off-1"},
            {"kind": "open_question", "title": "Is nightly reconciliation enough?",
             "payload": {"question": "Is nightly reconciliation enough?"}, "request_id": "off-2"},
        ],
    }
    pushed = c.post(f"/api/v1/sync/features/{fid}", json=payload)
    assert pushed.status_code == 200, pushed.text
    assert len(pushed.json()["accepted"]) == 2 and pushed.json()["rejected"] == []

    # A retried push (same request_ids) must not duplicate.
    before = len(world["store"].entries)
    replay = c.post(f"/api/v1/sync/features/{fid}", json=payload)
    assert len(replay.json()["accepted"]) == 2
    assert len(world["store"].entries) == before, "retried push created duplicates"


def test_status_reports_drift_without_transferring(world, rest):
    c = rest(world["agent_rw"])
    fid = world["payment"]["id"]
    context_actions.record_context(world["alice"], fid, kind="decision", title="Known before sync",
                                   payload={"decision": "Known before sync"})
    c.get(f"/api/v1/sync/features/{fid}", params={"client_id": CLIENT})

    context_actions.record_context(world["alice"], fid, kind="architecture", title="Added after the client synced",
                                   payload={"note": "Added after the client synced"})

    status = c.get(f"/api/v1/sync/features/{fid}/status", params={"client_id": CLIENT}).json()
    assert status["cloud_total"] == 2 and status["behind"] == 1 and status["client_cursor"]


def test_push_rejects_one_bad_entry_without_blocking_the_queue(world, rest):
    c = rest(world["agent_rw"])
    fid = world["payment"]["id"]
    result = c.post(
        f"/api/v1/sync/features/{fid}",
        json={"client_id": CLIENT, "entries": [
            {"kind": "decision", "title": "Good one", "payload": {"decision": "Good one"}, "request_id": "ok-1"},
            {"kind": "decision", "title": "Cites a foreign session", "payload": {"decision": "x"},
             "session_id": "11111111-1111-1111-1111-111111111111", "request_id": "bad-1"},
        ]},
    ).json()
    assert len(result["accepted"]) == 1
    assert len(result["rejected"]) == 1 and result["rejected"][0]["request_id"] == "bad-1"


def test_sync_requires_the_right_scopes(world, rest):
    fid = world["payment"]["id"]
    ro = rest(world["agent_ro"])
    assert ro.get(f"/api/v1/sync/features/{fid}", params={"client_id": CLIENT}).status_code == 200
    denied = ro.post(f"/api/v1/sync/features/{fid}", json={"client_id": CLIENT, "entries": []})
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "SCOPE_REQUIRED"


def test_sync_cannot_reach_an_unauthorized_feature(world, rest):
    denied = rest(world["agent_narrow"]).get(
        f"/api/v1/sync/features/{world['login']['id']}", params={"client_id": CLIENT}
    )
    assert denied.status_code == 403
