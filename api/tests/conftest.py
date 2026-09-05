"""In-memory repo fakes.

Lets the service layer, Context Bank and agent actions be exercised end to end
without Postgres. The fake context repo stores payloads as TOON exactly like the
real one, so these tests also cover the serialization boundary in situ.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

import pytest

from app.access import Principal
from app.toon_codec import ToonError, payload_to_toon, toon_to_payload

ORG = "org_forge"
OTHER_ORG = "org_other"

_ids = itertools.count(1)


def _uid(prefix: str) -> str:
    """A UUID, like the real tables use.

    Not `prefix_1`: those read as feature *keys* to code that accepts either a
    key or an id, so synthetic ids would take the wrong branch and hide bugs.
    The prefix is kept in the first field purely so failures stay readable.
    """
    tag = f"{abs(hash(prefix)) % 0xFFFFFFFF:08x}"
    rest = uuid.uuid4().hex[8:]
    return f"{tag}-{rest[:4]}-{rest[4:8]}-{rest[8:12]}-{rest[12:24]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Mutable in-memory tables."""

    def __init__(self) -> None:
        self.features: list[dict] = []
        self.sessions: list[dict] = []
        self.entries: list[dict] = []
        self.teams: list[dict] = []
        self.team_members: list[dict] = []
        self.users: list[dict] = []
        self.feature_teams: list[dict] = []
        self.feature_assignments: list[dict] = []

    # -- builders ----------------------------------------------------------
    def add_user(self, user_id: str, name: str, org: str = ORG, role: str = "developer") -> dict:
        u = {
            "id": user_id,
            "clerk_org_id": org,
            "display_name": name,
            "email": f"{user_id}@demo",
            "avatar_url": None,
            "role": role,
            "is_demo": True,
        }
        self.users.append(u)
        return u

    def add_team(self, name: str, org: str = ORG) -> dict:
        t = {"id": _uid("team"), "clerk_org_id": org, "name": name, "description": None, "created_at": _now()}
        self.teams.append(t)
        return t

    def join_team(self, team: dict, user_id: str, org: str = ORG) -> None:
        self.team_members.append({"clerk_org_id": org, "team_id": team["id"], "user_id": user_id})

    def add_feature(self, key: str, org: str = ORG) -> dict:
        f = {
            "id": _uid("feat"),
            "clerk_org_id": org,
            "key": key,
            "name": key.title(),
            "description": None,
            "status": "active",
            "created_by": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.features.append(f)
        return f

    def own_feature(self, feature: dict, team: dict) -> None:
        self.feature_teams.append(
            {"clerk_org_id": feature["clerk_org_id"], "feature_id": feature["id"], "team_id": team["id"]}
        )

    def assign_feature(self, feature: dict, user_id: str) -> None:
        self.feature_assignments.append(
            {"clerk_org_id": feature["clerk_org_id"], "feature_id": feature["id"], "user_id": user_id}
        )

    def add_session(self, feature: dict, user_id: str, **kw) -> dict:
        s = {
            "id": _uid("sess"),
            "clerk_org_id": feature["clerk_org_id"],
            "feature_id": feature["id"],
            "user_id": user_id,
            "agent": kw.get("agent", "claude-code"),
            "model": kw.get("model", "claude-opus-5"),
            "status": kw.get("status", "active"),
            "goal": kw.get("goal", "Do the work"),
            "summary": kw.get("summary"),
            "context": None,
            "context_version": 0,
            "started_at": _now(),
            "ended_at": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.sessions.append(s)
        return s


def _hydrate(row: dict) -> dict:
    out = dict(row)
    try:
        out["payload"] = toon_to_payload(row.get("payload_toon"))
    except ToonError as exc:
        out["payload"] = {}
        out["payload_error"] = str(exc)
    return out


def install(monkeypatch: pytest.MonkeyPatch, store: Store) -> Store:
    """Point every repo module at the in-memory store."""
    from app.repos import context as context_repo
    from app.repos import features as features_repo
    from app.repos import sessions as sessions_repo
    from app.repos import teams as teams_repo
    from app.repos import users as users_repo

    scoped = lambda rows, org: [r for r in rows if r["clerk_org_id"] == org]  # noqa: E731

    # --- users ---
    monkeypatch.setattr(users_repo, "list_users", lambda org: scoped(store.users, org))
    monkeypatch.setattr(users_repo, "users_by_id", lambda org: {u["id"]: u for u in scoped(store.users, org)})
    monkeypatch.setattr(
        users_repo,
        "get_user",
        lambda org, uid: next((u for u in scoped(store.users, org) if u["id"] == uid), None),
    )

    # --- teams ---
    monkeypatch.setattr(teams_repo, "list_teams", lambda org: scoped(store.teams, org))
    monkeypatch.setattr(teams_repo, "teams_by_id", lambda org: {t["id"]: t for t in scoped(store.teams, org)})
    monkeypatch.setattr(
        teams_repo,
        "get_team",
        lambda org, tid: next((t for t in scoped(store.teams, org) if t["id"] == tid), None),
    )
    monkeypatch.setattr(
        teams_repo,
        "my_team_ids",
        lambda org, uid: {m["team_id"] for m in scoped(store.team_members, org) if m["user_id"] == uid},
    )

    def members_by_team(org: str, team_ids: list[str] | None = None) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for m in scoped(store.team_members, org):
            if team_ids is not None and m["team_id"] not in team_ids:
                continue
            out.setdefault(m["team_id"], set()).add(m["user_id"])
        return out

    monkeypatch.setattr(teams_repo, "members_by_team", members_by_team)

    # --- features ---
    monkeypatch.setattr(features_repo, "list_features", lambda org: scoped(store.features, org))
    monkeypatch.setattr(
        features_repo,
        "get_feature",
        lambda org, fid: next((f for f in scoped(store.features, org) if f["id"] == fid), None),
    )
    monkeypatch.setattr(
        features_repo,
        "get_feature_by_key",
        lambda org, key: next((f for f in scoped(store.features, org) if f["key"] == key), None),
    )

    def feature_links(rows, org, feature_ids):
        out = scoped(rows, org)
        if feature_ids is not None:
            out = [r for r in out if r["feature_id"] in set(feature_ids)]
        return out

    monkeypatch.setattr(
        features_repo,
        "feature_teams",
        lambda org, feature_ids=None: feature_links(store.feature_teams, org, feature_ids),
    )
    monkeypatch.setattr(
        features_repo,
        "feature_assignments",
        lambda org, feature_ids=None: feature_links(store.feature_assignments, org, feature_ids),
    )

    # --- sessions ---
    def list_sessions(org, *, feature_id=None, user_id=None):
        rows = scoped(store.sessions, org)
        if feature_id:
            rows = [r for r in rows if r["feature_id"] == feature_id]
        if user_id:
            rows = [r for r in rows if r["user_id"] == user_id]
        return list(rows)

    monkeypatch.setattr(sessions_repo, "list_sessions", list_sessions)
    monkeypatch.setattr(
        sessions_repo,
        "get_session",
        lambda org, sid: next((s for s in scoped(store.sessions, org) if s["id"] == sid), None),
    )

    def update_session(org, sid, data):
        for s in store.sessions:
            if s["clerk_org_id"] == org and s["id"] == sid:
                s.update(data)
                return dict(s)
        return None

    def create_session(org, data):
        row = {
            "id": _uid("sess"), "clerk_org_id": org, "context": None, "context_version": 0,
            "summary": None, "ended_at": None, "created_at": _now(), "updated_at": _now(), **dict(data),
        }
        store.sessions.append(row)
        return dict(row)

    def delete_session(org, sid):
        before = len(store.sessions)
        store.sessions[:] = [s for s in store.sessions if not (s["clerk_org_id"] == org and s["id"] == sid)]
        return len(store.sessions) < before

    monkeypatch.setattr(sessions_repo, "update_session", update_session)
    monkeypatch.setattr(sessions_repo, "create_session", create_session)
    monkeypatch.setattr(sessions_repo, "delete_session", delete_session)
    monkeypatch.setattr(
        sessions_repo,
        "count_by_feature",
        lambda org: {f["id"]: len(list_sessions(org, feature_id=f["id"])) for f in scoped(store.features, org)},
    )

    # --- context entries (TOON in, TOON out, like the real repo) ---
    def create_entry(org, data: Mapping[str, Any]) -> dict:
        row = {
            "id": _uid("ctx"),
            "clerk_org_id": org,
            "feature_id": data["feature_id"],
            "session_id": data.get("session_id"),
            "author_user_id": data.get("author_user_id"),
            "kind": data["kind"],
            "version": data.get("version", 1),
            "title": data["title"],
            "payload_toon": payload_to_toon(data.get("payload") or {}),
            "confidence": data.get("confidence"),
            "status": data.get("status", "active"),
            "supersedes_id": data.get("supersedes_id"),
            # Evidence is a column of its own, kept apart from the TOON payload (§9).
            "evidence": data.get("evidence"),
            # Set when the statement was flagged as resembling an active one (§17).
            "conflicts_with": data.get("conflicts_with"),
            "created_at": data.get("created_at") or _now(),
            "updated_at": data.get("updated_at") or _now(),
        }
        store.entries.append(row)
        return _hydrate(row)

    def create_entries(org, rows):
        return [create_entry(org, r) for r in rows]

    def get_entry(org, eid):
        row = next((e for e in scoped(store.entries, org) if e["id"] == eid), None)
        return _hydrate(row) if row else None

    def list_entries(org, feature_id, *, statuses=("active",), kinds=None):
        rows = [e for e in scoped(store.entries, org) if e["feature_id"] == feature_id]
        if statuses is not None:
            rows = [e for e in rows if e["status"] in set(statuses)]
        if kinds:
            rows = [e for e in rows if e["kind"] in set(kinds)]
        return [_hydrate(e) for e in rows]

    def list_by_session(org, session_id):
        return [_hydrate(e) for e in scoped(store.entries, org) if e.get("session_id") == session_id]

    def search_entries(org, query, *, feature_ids=None, kinds=None, statuses=("active",), limit=50):
        needle = query.lower().strip()
        if not needle:
            return []
        rows = scoped(store.entries, org)
        if feature_ids is not None:
            rows = [e for e in rows if e["feature_id"] in set(feature_ids)]
        if kinds:
            rows = [e for e in rows if e["kind"] in set(kinds)]
        if statuses is not None:
            rows = [e for e in rows if e["status"] in set(statuses)]
        rows = [
            e
            for e in rows
            if needle in e["title"].lower() or needle in (e.get("payload_toon") or "").lower()
        ]
        return [_hydrate(e) for e in rows[:limit]]

    def update_entry(org, eid, data):
        for e in store.entries:
            if e["clerk_org_id"] == org and e["id"] == eid:
                row = {k: v for k, v in data.items() if k != "payload"}
                if "payload" in data:
                    row["payload_toon"] = payload_to_toon(data["payload"] or {})
                e.update(row)
                e["updated_at"] = _now()
                return _hydrate(e)
        return None

    def version_chain(org, eid):
        chain: list[dict] = []
        current = get_entry(org, eid)
        seen: set[str] = set()
        while current and current["id"] not in seen:
            seen.add(current["id"])
            chain.append(current)
            prev = current.get("supersedes_id")
            current = get_entry(org, prev) if prev else None
        return chain

    monkeypatch.setattr(context_repo, "create_entry", create_entry)
    monkeypatch.setattr(context_repo, "create_entries", create_entries)
    monkeypatch.setattr(context_repo, "get_entry", get_entry)
    monkeypatch.setattr(context_repo, "list_entries", list_entries)
    monkeypatch.setattr(context_repo, "list_by_session", list_by_session)
    monkeypatch.setattr(context_repo, "search_entries", search_entries)
    monkeypatch.setattr(context_repo, "update_entry", update_entry)
    monkeypatch.setattr(context_repo, "version_chain", version_chain)
    monkeypatch.setattr(
        context_repo, "mark_superseded", lambda org, eid: update_entry(org, eid, {"status": "superseded"})
    )
    monkeypatch.setattr(
        context_repo,
        "count_by_feature",
        lambda org, statuses=("active",): {
            f["id"]: len(list_entries(org, f["id"], statuses=statuses)) for f in scoped(store.features, org)
        },
    )
    return store


@pytest.fixture(scope="session")
def http():
    """One TestClient for the whole run.

    The MCP session manager can only be started once per process, and entering
    the app's lifespan is what starts it — so a per-test client would fail on
    the second one. Per-test isolation still works: repos are monkeypatched on
    their modules, and dependency overrides are set inside each test.
    """
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app, base_url="http://localhost:8000") as client:
        yield client


class Infra:
    """In-memory audit log and idempotency keys (Phase 2)."""

    def __init__(self) -> None:
        self.audit: list[dict] = []
        self.idem: dict[tuple[str, str], dict] = {}
        self.sync_clients: dict[tuple[str, str], dict] = {}
        self.sync_state: dict[tuple[str, str, str], dict] = {}

    def audit_rows(self, action: str | None = None, outcome: str | None = None) -> list[dict]:
        return [
            r for r in self.audit
            if (action is None or r["action"] == action) and (outcome is None or r["outcome"] == outcome)
        ]


@pytest.fixture(autouse=True)
def infra(monkeypatch: pytest.MonkeyPatch) -> Infra:
    """Every test gets fake audit/idempotency repos, so no code path can reach the real DB through them."""
    from app.repos import audit as audit_repo
    from app.repos import idempotency as idempotency_repo

    store = Infra()

    def insert(row):
        record = {**dict(row), "id": _uid("audit"), "created_at": _now()}
        store.audit.append(record)
        return record

    monkeypatch.setattr(audit_repo, "insert", insert)
    monkeypatch.setattr(
        audit_repo, "list_for_org",
        lambda org, *, limit=100, credential_id=None: [
            r for r in reversed(store.audit)
            if r["clerk_org_id"] == org and (credential_id is None or r.get("credential_id") == credential_id)
        ][:limit],
    )
    # Sync client/state tables (phase-2 §10, §11).
    from app.repos import sync as sync_repo

    monkeypatch.setattr(
        sync_repo, "register_client",
        lambda org, cid, *, user_id, label: store.sync_clients.__setitem__((org, cid), {"user_id": user_id, "label": label}) or {"client_id": cid},
    )
    monkeypatch.setattr(sync_repo, "get_state", lambda org, cid, fid: store.sync_state.get((org, cid, fid)))
    monkeypatch.setattr(
        sync_repo, "set_state",
        lambda org, cid, fid, *, cursor, entry_count: store.sync_state.__setitem__(
            (org, cid, fid), {"cursor": cursor, "entry_count": entry_count, "updated_at": _now()}
        ) or store.sync_state[(org, cid, fid)],
    )

    monkeypatch.setattr(idempotency_repo, "get_result", lambda org, rid: store.idem.get((org, rid)))
    monkeypatch.setattr(
        idempotency_repo, "put_result",
        lambda org, rid, op, result: store.idem.__setitem__((org, rid), {"clerk_org_id": org, "request_id": rid, "operation": op, "result": dict(result)}),
    )
    return store


class FakeOAuthRepo:
    """In-memory OAuth persistence that preserves the conditional consume semantics."""

    def __init__(self) -> None:
        self.clients: dict[str, dict] = {}
        self.pending: dict[str, dict] = {}
        self.grants: dict[str, dict] = {}
        self.codes: dict[str, dict] = {}
        self.tokens: dict[str, dict] = {}

    def get_client(self, client_id):
        return self.clients.get(client_id)

    def save_client(self, client_id, *, client_name, redirect_uris, client_info):
        row = {"client_id": client_id, "client_name": client_name, "redirect_uris": redirect_uris, "client_info": dict(client_info)}
        self.clients[client_id] = row
        return row

    def create_pending(self, client_id, params, expires_at):
        row = {"id": _uid("pending"), "client_id": client_id, "params": dict(params), "expires_at": expires_at.isoformat(), "consumed_at": None}
        self.pending[row["id"]] = row
        return row

    def get_pending(self, pending_id):
        return self.pending.get(pending_id)

    def consume_pending(self, pending_id):
        row = self.pending.get(pending_id)
        if not row or row["consumed_at"] is not None:
            return None
        row["consumed_at"] = _now()
        return dict(row)

    def create_grant(self, org_id, *, user_id, client_id, client_name, scopes, feature_ids, expires_at):
        row = {
            "id": _uid("grant"), "clerk_org_id": org_id, "user_id": user_id, "client_id": client_id,
            "client_name": client_name, "scopes": list(scopes), "feature_ids": feature_ids, "status": "active",
            "created_at": _now(), "expires_at": expires_at.isoformat() if expires_at else None,
            "revoked_at": None, "last_used_at": None,
        }
        self.grants[row["id"]] = row
        return row

    def get_grant(self, grant_id):
        return self.grants.get(grant_id)

    def list_grants(self, org_id, *, user_id=None):
        return [
            g for g in self.grants.values()
            if g["clerk_org_id"] == org_id and (user_id is None or g["user_id"] == user_id)
        ]

    def revoke_grant(self, org_id, grant_id):
        g = self.grants.get(grant_id)
        if not g or g["clerk_org_id"] != org_id:
            return None
        g["status"], g["revoked_at"] = "revoked", _now()
        for t in self.tokens.values():
            if t["grant_id"] == grant_id and t["revoked_at"] is None:
                t["revoked_at"] = _now()
        return g

    def touch_grant(self, grant_id):
        if g := self.grants.get(grant_id):
            g["last_used_at"] = _now()

    def save_code(self, code_hash, data):
        row = {**dict(data), "code_hash": code_hash, "used_at": None}
        self.codes[code_hash] = row
        return row

    def get_code(self, code_hash):
        return self.codes.get(code_hash)

    def consume_code(self, code_hash, client_id):
        row = self.codes.get(code_hash)
        if not row or row["client_id"] != client_id or row["used_at"] is not None:
            return None
        row["used_at"] = _now()
        return dict(row)

    def save_token(self, token_hash, data):
        row = {**dict(data), "token_hash": token_hash, "revoked_at": None, "last_used_at": None}
        self.tokens[token_hash] = row
        return row

    def get_token(self, token_hash):
        return self.tokens.get(token_hash)

    def revoke_token(self, token_hash):
        if row := self.tokens.get(token_hash):
            row["revoked_at"] = _now()

    def touch_token(self, token_hash):
        if row := self.tokens.get(token_hash):
            row["last_used_at"] = _now()


@pytest.fixture
def oauth_repo(monkeypatch: pytest.MonkeyPatch) -> FakeOAuthRepo:
    from app import oauth

    fake = FakeOAuthRepo()
    monkeypatch.setattr(oauth, "repo", fake)
    # The grants router reads the repo module directly.
    from app.routers import oauth as oauth_router

    monkeypatch.setattr(oauth_router, "oauth_repo", fake)
    return fake


def agent(base: Principal, *, scopes: Iterable[str], feature_ids: Iterable[str] | None = None, credential_id: str = "grant_x") -> Principal:
    """An agent principal acting as `base`, narrowed by scopes and an optional allow-list."""
    return Principal(
        user_id=base.user_id,
        org_id=base.org_id,
        role="developer",
        principal_type="agent",
        scopes=frozenset(scopes),
        feature_ids=frozenset(feature_ids) if feature_ids is not None else None,
        credential_id=credential_id,
        client_name="test-agent",
    )


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A small organization exercising the access rules.

    payments team: alice (caller), bob      platform team: carol
    PAYMENT  owned by payments   → alice can access, sees bob's sessions
    LOGIN    owned by platform, alice directly assigned → access, own sessions only
    SECRET   owned by platform   → alice cannot access at all
    """
    store = Store()
    install(monkeypatch, store)

    payments = store.add_team("Payments")
    platform = store.add_team("Platform")

    store.add_user("user_alice", "Alice")
    store.add_user("user_bob", "Bob")
    store.add_user("user_carol", "Carol")
    store.add_user("user_admin", "Admin", role="admin")

    store.join_team(payments, "user_alice")
    store.join_team(payments, "user_bob")
    store.join_team(platform, "user_carol")

    payment = store.add_feature("PAYMENT")
    login = store.add_feature("LOGIN")
    secret = store.add_feature("SECRET")

    store.own_feature(payment, payments)
    store.own_feature(login, platform)
    store.own_feature(secret, platform)
    store.assign_feature(login, "user_alice")

    alice = Principal(user_id="user_alice", org_id=ORG, role="developer")
    from app.access import ALL_SCOPES, SCOPE_CONTEXT_READ

    return {
        "store": store,
        "alice": alice,
        "bob": Principal(user_id="user_bob", org_id=ORG, role="developer"),
        "carol": Principal(user_id="user_carol", org_id=ORG, role="developer"),
        "admin": Principal(user_id="user_admin", org_id=ORG, role="admin"),
        # Phase 2 agent principals, all acting as alice.
        "agent_ro": agent(alice, scopes=[SCOPE_CONTEXT_READ], credential_id="grant_ro"),
        "agent_rw": agent(alice, scopes=ALL_SCOPES, credential_id="grant_rw"),
        "agent_narrow": agent(alice, scopes=ALL_SCOPES, feature_ids=[payment["id"]], credential_id="grant_narrow"),
        "payment": payment,
        "login": login,
        "secret": secret,
        "payments_team": payments,
        "platform_team": platform,
    }
