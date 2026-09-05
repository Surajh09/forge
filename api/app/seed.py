"""Idempotent demo data for one organization.

Called by POST /admin/seed with the caller's Principal, so the Clerk org id and
the caller's user id are real; everyone else is a seeded demo user.

The layout is chosen to demonstrate the access rules:
  - caller joins the Payments team and is directly assigned to LOGIN
  - PAYMENT is owned by Payments + QA  → caller sees Payments teammates' sessions, not QA's
  - LOGIN is owned by Platform         → caller (assigned, not on Platform) sees only own sessions
  - NOTIFICATION is owned by DevOps    → hidden from a non-admin caller entirely
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import context_bank
from app.access import Principal
from app.repos import context as context_repo
from app.repos import features as features_repo
from app.repos import sessions as sessions_repo
from app.repos import teams as teams_repo
from app.repos import users as users_repo
from app.schemas import ContextContract

TEAMS = [
    ("Payments", "Checkout, billing and payment-provider integrations"),
    ("Platform", "Identity, core services and shared infrastructure"),
    ("QA", "Quality engineering and release verification"),
    ("DevOps", "CI/CD, observability and delivery pipelines"),
]

DEMO_USERS = [
    ("user_demo_asha", "Asha Raman", "asha@demo.forge", "developer", ["Payments"]),
    ("user_demo_ben", "Ben Okafor", "ben@demo.forge", "developer", ["Payments", "Platform"]),
    ("user_demo_chen", "Chen Wei", "chen@demo.forge", "developer", ["Platform"]),
    ("user_demo_dana", "Dana Kowalski", "dana@demo.forge", "qa", ["QA"]),
    ("user_demo_eli", "Eli Novak", "eli@demo.forge", "developer", ["DevOps"]),
    ("user_demo_farah", "Farah Siddiqui", "farah@demo.forge", "developer", ["Platform", "DevOps"]),
]

FEATURES = [
    ("LOGIN", "Login", "Authentication flows: password, magic link, SSO and session handling.", ["Platform"]),
    ("DOCUMENT_PROCESSING", "Document Processing", "Upload, OCR and extraction pipeline for customer documents.", ["Platform", "QA"]),
    ("USER_CREATION", "User Creation", "Onboarding, invitations and account provisioning.", ["Platform"]),
    ("PAYMENT", "Payments", "Checkout, Stripe integration, refunds and settlement reconciliation.", ["Payments", "QA"]),
    ("NOTIFICATION", "Notifications", "Email, SMS and push delivery plus per-channel preferences.", ["DevOps"]),
]


def _ctx(goal, changes, decisions, files, dependencies=(), constraints=(), known_issues=(), open_questions=(), confidence=0.85):
    """Build a Context Contract for seeded sessions.

    `decisions` is written as plain strings for brevity here and widened to the
    contract's {decision, reason} shape.
    """
    return {
        "objective": goal,
        "changes": list(changes),
        "decisions": [d if isinstance(d, dict) else {"decision": d, "reason": None} for d in decisions],
        "affected_components": list(files),
        "dependencies": list(dependencies),
        "constraints": list(constraints),
        "known_issues": list(known_issues),
        "open_questions": list(open_questions),
        "confidence": confidence,
    }


# (feature, user, agent, model, status, goal, summary, days_ago, hours, context)
DEMO_SESSIONS = [
    (
        "PAYMENT", "user_demo_asha", "claude-code", "claude-opus-5", "completed",
        "Add idempotency handling for Stripe webhooks",
        "Webhook handler now dedupes by Stripe event id; replays are acknowledged without side effects.",
        6, 2.5,
        _ctx(
            "Add idempotency handling for Stripe webhooks",
            ["Store processed event ids in payment_events with a unique index", "Return 200 on duplicate event"],
            ["Idempotency key is the Stripe event id, not our internal order id"],
            ["services/payments/webhooks.py", "migrations/0042_payment_events.sql"],
            dependencies=["stripe>=9"],
            constraints=["Webhook handler must finish under 5s or Stripe retries"],
            open_questions=["Should we archive payment_events older than 90 days?"],
            confidence=0.92,
        ),
    ),
    (
        "PAYMENT", "user_demo_ben", "cursor", "gpt-5", "completed",
        "Partial refunds with ledger entries",
        "Refund API accepts an amount; each refund posts a reversing ledger entry.",
        4, 3,
        _ctx(
            "Partial refunds with ledger entries",
            ["POST /refunds accepts amount_minor", "Ledger posts REFUND entries linked to the charge"],
            ["Amounts are integers in minor units end-to-end"],
            ["services/payments/refunds.py", "services/ledger/post.py"],
            known_issues=["Ledger double-posts when two webhook retries overlap — needs a lock on charge_id"],
            confidence=0.7,
        ),
    ),
    (
        "PAYMENT", "user_demo_dana", "manual", None, "completed",
        "QA pass on the checkout regression suite",
        "All 48 checkout scenarios green; two flaky 3DS tests quarantined.",
        3, 1.5,
        _ctx(
            "QA pass on the checkout regression suite",
            ["Quarantined tests/checkout/test_3ds_redirect.py::test_timeout"],
            [],
            ["tests/checkout/"],
            known_issues=["3DS redirect tests time out on CI runners without a browser sandbox"],
            confidence=0.8,
        ),
    ),
    (
        "PAYMENT", "user_demo_asha", "claude-code", "claude-opus-5", "active",
        "Reconcile settlement reports with the ledger", None, 0.2, 0, None,
    ),
    (
        "LOGIN", "user_demo_chen", "claude-code", "claude-sonnet-5", "completed",
        "Magic-link sign-in with 15-minute token expiry",
        "Magic links are single-use, hashed at rest and expire after 15 minutes.",
        8, 2,
        _ctx(
            "Magic-link sign-in with 15-minute token expiry",
            ["Added magic_link_tokens table", "Token hashed with SHA-256 before storage"],
            ["Single-use tokens; a second click shows an 'expired' page rather than re-issuing"],
            ["auth/magic_link.py", "templates/auth/magic_link_email.html"],
            constraints=["Email provider rate limit: 100 sends/min"],
            confidence=0.9,
        ),
    ),
    (
        "LOGIN", "user_demo_ben", "claude-code", "claude-opus-5", "failed",
        "Migrate session cookies to SameSite=Strict",
        "Reverted: Strict broke the OAuth callback because the provider redirect is cross-site.",
        5, 1,
        _ctx(
            "Migrate session cookies to SameSite=Strict",
            ["Attempted SameSite=Strict on the session cookie; reverted"],
            ["Stay on SameSite=Lax until the OAuth callback is same-site"],
            ["auth/session_cookie.py"],
            known_issues=["OAuth callback loses the session under SameSite=Strict"],
            confidence=0.8,
        ),
    ),
    (
        "LOGIN", "user_demo_farah", "cursor", "gpt-5", "completed",
        "SSO: harden SAML assertion validation",
        "Assertions now require signed responses and a 2-minute clock-skew window.",
        2, 4,
        _ctx(
            "SSO: harden SAML assertion validation",
            ["Reject unsigned SAML responses", "Clock skew tolerance set to 120s"],
            ["Signature required on the Response element, not only the Assertion"],
            ["auth/saml/validate.py"],
            dependencies=["python3-saml>=1.16"],
            known_issues=["Customers with >2 min clock drift get rejected; needs a support runbook"],
            confidence=0.75,
        ),
    ),
    (
        "DOCUMENT_PROCESSING", "user_demo_chen", "claude-code", "claude-opus-5", "completed",
        "Move OCR onto an async worker queue",
        "Upload API returns 202 + job id; OCR runs on the worker pool.",
        7, 3,
        _ctx(
            "Move OCR onto an async worker queue",
            ["POST /documents returns 202 with job_id", "Worker consumes ocr_jobs queue"],
            ["API never blocks on OCR; clients poll GET /documents/{id}"],
            ["documents/api.py", "workers/ocr.py"],
            dependencies=["celery>=5", "redis"],
            confidence=0.9,
        ),
    ),
    (
        "DOCUMENT_PROCESSING", "user_demo_dana", "manual", None, "completed",
        "Verify extraction accuracy on scanned invoices",
        "Accuracy 96.4% on the 200-invoice sample; totals field is the weak spot.",
        1, 2,
        _ctx(
            "Verify extraction accuracy on scanned invoices",
            [],
            [],
            ["qa/datasets/invoices_200/"],
            known_issues=["'Total' field mis-read when the invoice uses a comma decimal separator"],
            open_questions=["What is the retention policy for raw uploads?"],
            confidence=0.85,
        ),
    ),
    (
        "USER_CREATION", "user_demo_farah", "claude-code", "claude-sonnet-5", "completed",
        "Org-scoped invitation tokens",
        "Invites are bound to an organization and expire after 7 days.",
        9, 2,
        _ctx(
            "Org-scoped invitation tokens",
            ["invitations table gains org_id + expires_at"],
            ["Invite tokens are org-scoped and expire in 7 days"],
            ["users/invitations.py"],
            confidence=0.9,
        ),
    ),
    (
        "USER_CREATION", "user_demo_chen", "claude-code", "claude-opus-5", "abandoned",
        "Bulk CSV user import",
        "Parked: the naive parser loads the whole file into memory.",
        3, 1,
        _ctx(
            "Bulk CSV user import",
            ["Prototype endpoint POST /users/import (not merged)"],
            [],
            ["users/import_csv.py"],
            known_issues=["Needs a streaming parser before it can handle >50k rows"],
            confidence=0.6,
        ),
    ),
    (
        "NOTIFICATION", "user_demo_eli", "claude-code", "claude-opus-5", "completed",
        "Retry policy for SMS provider outages",
        "SMS sends retry 3x with exponential backoff, then fail over to the secondary provider.",
        4, 2,
        _ctx(
            "Retry policy for SMS provider outages",
            ["Added backoff (1s, 4s, 16s) and provider failover"],
            ["Fail over after 3 retries"],
            ["notifications/sms.py"],
            confidence=0.85,
        ),
    ),
    (
        "NOTIFICATION", "user_demo_farah", "cursor", "gpt-5", "active",
        "Per-channel notification preferences", None, 0.5, 0, None,
    ),
]

# Feature-level context that isn't tied to one session (kind, feature, author, title, payload, confidence)
DEMO_CONTEXT = [
    ("decision", "PAYMENT", "user_demo_asha", "Stripe is the only PSP; every webhook must be idempotent by event id",
     {"rationale": "Stripe retries aggressively; duplicate processing caused double refunds in staging."}, 0.95),
    ("constraint", "PAYMENT", "user_demo_ben", "Amounts are stored as integer minor units — never floats",
     {"applies_to": ["ledger", "refunds", "invoices"]}, 0.98),
    ("known_issue", "PAYMENT", "user_demo_ben", "Refund ledger double-posts when webhook retries overlap",
     {"workaround": "Manual reversal", "proposed_fix": "Advisory lock on charge_id"}, 0.7),
    ("open_question", "PAYMENT", "user_demo_dana", "Do we need multi-currency settlement before the EU launch?",
     {"owner": "Payments"}, None),
    ("decision", "LOGIN", "user_demo_chen", "Magic-link tokens: single-use, 15-minute expiry, hashed at rest",
     {"rationale": "Limits replay if an email is forwarded."}, 0.9),
    ("constraint", "LOGIN", "user_demo_ben", "Session cookies stay SameSite=Lax until the OAuth callback is same-site",
     {"blocked_by": "Provider redirect is cross-site"}, 0.8),
    ("known_issue", "LOGIN", "user_demo_farah", "SAML assertions rejected when customer clock drift exceeds 2 minutes",
     {"next_step": "Support runbook + configurable skew per connection"}, 0.75),
    ("decision", "DOCUMENT_PROCESSING", "user_demo_chen", "OCR runs on an async worker queue; API returns 202 + job id",
     {"queue": "ocr_jobs"}, 0.9),
    ("open_question", "DOCUMENT_PROCESSING", "user_demo_dana", "Retention policy for raw uploads?",
     {}, None),
    ("decision", "USER_CREATION", "user_demo_farah", "Invite tokens are org-scoped and expire in 7 days",
     {}, 0.9),
    ("known_issue", "USER_CREATION", "user_demo_chen", "Bulk CSV import needs a streaming parser",
     {"status": "parked"}, 0.6),
    ("decision", "NOTIFICATION", "user_demo_eli", "SMS fails over to the secondary provider after 3 retries",
     {"backoff": "1s, 4s, 16s"}, 0.85),
    ("constraint", "NOTIFICATION", "user_demo_farah", "Push notifications require a per-device opt-in",
     {"stores": "device_push_consent"}, 0.9),
]

CALLER_SESSIONS = [
    ("LOGIN", "claude-code", "claude-opus-5", "active", "Review session-timeout UX and idle warning", None, 0.1, 0, None),
    (
        "PAYMENT", "manual", None, "completed",
        "Add currency formatting helper for invoices",
        "format_minor_units() handles 0- and 3-decimal currencies.",
        1, 1,
        _ctx(
            "Add currency formatting helper for invoices",
            ["Added format_minor_units(amount, currency)"],
            ["Formatting lives in the ledger package so refunds and invoices share it"],
            ["services/ledger/format.py"],
            confidence=0.9,
        ),
    ),
]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def run_seed(p: Principal) -> dict[str, int]:
    org = p.org_id
    created = {"teams": 0, "users": 0, "features": 0, "sessions": 0, "context_entries": 0}
    now = datetime.now(timezone.utc)

    # Teams
    team_ids: dict[str, str] = {}
    for name, description in TEAMS:
        existing = teams_repo.get_team_by_name(org, name)
        if existing:
            team_ids[name] = existing["id"]
        else:
            team_ids[name] = teams_repo.create_team(org, {"name": name, "description": description})["id"]
            created["teams"] += 1

    # Demo users + team membership
    existing_users = users_repo.users_by_id(org)
    new_users = [
        {"id": uid, "email": email, "display_name": name, "avatar_url": None, "role": role, "is_demo": True}
        for uid, name, email, role, _ in DEMO_USERS
        if uid not in existing_users
    ]
    created["users"] = users_repo.upsert_users(org, new_users)
    for uid, _, _, _, teams in DEMO_USERS:
        for t in teams:
            teams_repo.add_member(org, team_ids[t], uid)

    # Features + owning teams
    feature_ids: dict[str, str] = {}
    for key, name, description, teams in FEATURES:
        existing = features_repo.get_feature_by_key(org, key)
        if existing:
            feature_ids[key] = existing["id"]
        else:
            feature_ids[key] = features_repo.create_feature(
                org, {"key": key, "name": name, "description": description}, created_by=p.user_id
            )["id"]
            created["features"] += 1
        for t in teams:
            features_repo.add_team(org, feature_ids[key], team_ids[t])

    # Caller: Payments team + direct assignment to LOGIN
    teams_repo.add_member(org, team_ids["Payments"], p.user_id)
    features_repo.add_assignee(org, feature_ids["LOGIN"], p.user_id)

    # Sessions (skip entirely if demo sessions already exist in this org)
    demo_user_ids = {u[0] for u in DEMO_USERS}
    have_demo_sessions = any(s["user_id"] in demo_user_ids for s in sessions_repo.list_sessions(org))
    summary_entries: list[dict] = []
    if not have_demo_sessions:
        for feature_key, uid, agent, model, status_, goal, summary, days_ago, hours, ctx in DEMO_SESSIONS:
            summary_entries.extend(
                _insert_session(org, feature_ids[feature_key], uid, agent, model, status_, goal, summary, now, days_ago, hours, ctx)
            )
            created["sessions"] += 1

    if not sessions_repo.list_sessions(org, user_id=p.user_id):
        for feature_key, agent, model, status_, goal, summary, days_ago, hours, ctx in CALLER_SESSIONS:
            summary_entries.extend(
                _insert_session(org, feature_ids[feature_key], p.user_id, agent, model, status_, goal, summary, now, days_ago, hours, ctx)
            )
            created["sessions"] += 1

    # Context Bank: feature-level entries once per org, plus session summaries for the sessions just created
    entries: list[dict] = []
    if not context_repo.count_by_feature(org):
        for kind, feature_key, author, title, payload, confidence in DEMO_CONTEXT:
            entries.append(
                {
                    "feature_id": feature_ids[feature_key],
                    "session_id": None,
                    "author_user_id": author,
                    "kind": kind,
                    "version": 1,
                    "title": title,
                    "payload": payload,
                    "confidence": confidence,
                    "status": "active",
                }
            )
    entries.extend(summary_entries)
    created["context_entries"] = len(context_repo.create_entries(org, entries))
    return created


def _insert_session(org, feature_id, user_id, agent, model, status_, goal, summary, now, days_ago, hours, ctx) -> list[dict]:
    started = now - timedelta(days=days_ago)
    ended = started + timedelta(hours=hours) if status_ != "active" else None
    row = sessions_repo.create_session(
        org,
        {
            "feature_id": feature_id,
            "user_id": user_id,
            "agent": agent,
            "model": model,
            "status": status_,
            "goal": goal,
            "summary": summary,
            "context": ctx,
            "context_version": 1 if ctx else 0,
            "started_at": _iso(started),
            "ended_at": _iso(ended) if ended else None,
            "created_at": _iso(started),
            "updated_at": _iso(ended or started),
        },
    )
    if not ctx:
        return []

    # Same fan-out the real completion path uses, so seeded data is shaped like
    # data the product actually produces.
    contract = ContextContract.model_validate(ctx)
    entries = context_bank.fan_out(
        contract,
        feature_id=feature_id,
        session_id=row["id"],
        author_user_id=user_id,
    )
    stamp = _iso(ended or started)
    for e in entries:
        e["created_at"] = stamp
        e["updated_at"] = stamp
    return entries
