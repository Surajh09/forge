"""End-to-end smoke test against a running Forge API using real Clerk tokens.

Provisions temporary users + organizations in the Clerk *dev* instance named by
CLERK_SECRET_KEY (all named forge-e2e-…, emails use the +clerk_test suffix so no
mail is sent), mints org-scoped session tokens through the Backend API, drives
the API through the demo scenario, and deletes everything it created — in Clerk
and in the local database.

Run:  cd api && uv run python scripts/e2e.py        (API must be up on :8000)
"""

from __future__ import annotations

import os
import sys
import traceback
import uuid

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings  # noqa: E402
from app.db import get_db  # noqa: E402
from clerk_backend_api import Clerk  # noqa: E402

API = os.environ.get("FORGE_API", "http://localhost:8000") + "/api/v1"
settings = get_settings()
clerk = Clerk(bearer_auth=settings.clerk_secret_key)
tag = uuid.uuid4().hex[:6]

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  — {detail}" if detail else ""))


def mk_user(label: str):
    return clerk.users.create(
        email_address=[f"forge-e2e-{label}-{tag}+clerk_test@example.com"],
        password=f"Forge-{tag}-Passw0rd!",
        skip_password_checks=True,
        first_name=label.title(),
        last_name="E2E",
    )


def token_for(user_id: str, org_id: str | None) -> str:
    body = {"user_id": user_id}
    if org_id:
        body["active_organization_id"] = org_id
    session = clerk.sessions.create(request=body)
    tok = clerk.sessions.create_token(session_id=session.id)
    return tok.jwt  # type: ignore[union-attr]


class Api:
    def __init__(self, jwt: str | None):
        self.c = httpx.Client(base_url=API, timeout=30, headers={"authorization": f"Bearer {jwt}"} if jwt else {})

    def get(self, p, **kw):
        return self.c.get(p, **kw)

    def post(self, p, json=None):
        return self.c.post(p, json=json)

    def patch(self, p, json=None):
        return self.c.patch(p, json=json)

    def delete(self, p):
        return self.c.delete(p)


created = {"users": [], "orgs": []}


def main() -> int:
    admin = mk_user("admin")
    member = mk_user("member")
    created["users"] += [admin.id, member.id]
    org = clerk.organizations.create(request={"name": f"Forge E2E {tag}", "created_by": admin.id})
    org2 = clerk.organizations.create(request={"name": f"Forge E2E Other {tag}", "created_by": admin.id})
    created["orgs"] += [org.id, org2.id]
    clerk.organization_memberships.create(organization_id=org.id, user_id=member.id, role="org:member")
    print(f"provisioned org={org.id} admin={admin.id} member={member.id}")

    a = Api(token_for(admin.id, org.id))
    m = Api(token_for(member.id, org.id))
    anon = Api(None)
    no_org = Api(token_for(member.id, None))

    # --- auth envelope --------------------------------------------------------
    r = anon.get("/me")
    check("no token → 401 UNAUTHENTICATED", r.status_code == 401 and r.json()["detail"]["code"] == "UNAUTHENTICATED")
    r = no_org.get("/me")
    check("token without active org → 403 ORG_REQUIRED", r.status_code == 403 and r.json()["detail"]["code"] == "ORG_REQUIRED", r.text[:120])

    r = a.get("/me")
    me = r.json()
    check("admin /me", r.status_code == 200 and me["principal"]["role"] == "admin" and me["principal"]["org_id"] == org.id, f"role={me.get('principal', {}).get('role')} clerk_role={me.get('principal', {}).get('clerk_role')}")
    r = m.get("/me")
    me_m = r.json()
    check("member /me → developer", r.status_code == 200 and me_m["principal"]["role"] == "developer", f"clerk_role={me_m.get('principal', {}).get('clerk_role')}")

    # --- seed -----------------------------------------------------------------
    r = a.post("/admin/seed")
    seed = r.json()
    check("admin seed", r.status_code == 200, str(seed.get("created")))
    r = m.post("/admin/seed")
    check("member seed → 403 ADMIN_REQUIRED", r.status_code == 403 and r.json()["detail"]["code"] == "ADMIN_REQUIRED")
    r = a.post("/admin/seed")
    check("seed is idempotent", r.status_code == 200 and all(v == 0 for v in r.json()["created"].values()), str(r.json().get("created")))

    feats = a.get("/features").json()
    by_key = {f["key"]: f for f in feats}
    check("admin sees all 5 features", len(feats) == 5, ",".join(sorted(by_key)))
    payment, login, notif = by_key["PAYMENT"], by_key["LOGIN"], by_key["NOTIFICATION"]

    # --- member before enrollment ------------------------------------------------
    r = m.get("/features")
    check("member with no team/assignment sees 0 features", r.status_code == 200 and r.json() == [])

    teams = {t["name"]: t for t in a.get("/teams").json()}
    r1 = a.post(f"/teams/{teams['Payments']['id']}/members/{member.id}")
    r2 = a.post(f"/features/{login['id']}/assignees/{member.id}")
    check("admin enrolls member (Payments team + LOGIN assignee)", r1.status_code == 204 and r2.status_code == 204, f"{r1.status_code},{r2.status_code}")

    # --- feature access -----------------------------------------------------------
    mf = {f["key"]: f for f in m.get("/features").json()}
    check("member sees LOGIN (assigned) + PAYMENT (team) only", set(mf) == {"LOGIN", "PAYMENT"}, ",".join(sorted(mf)))
    check("access reasons", mf.get("LOGIN", {}).get("access_reason") == "assigned" and mf.get("PAYMENT", {}).get("access_reason") == "team")
    r = m.get(f"/features/{notif['id']}")
    check("member GET NOTIFICATION → 403 FEATURE_FORBIDDEN", r.status_code == 403 and r.json()["detail"]["code"] == "FEATURE_FORBIDDEN")

    # --- session visibility -------------------------------------------------------
    d = m.get(f"/features/{payment['id']}").json()
    authors = {s["author"]["display_name"] for s in d["sessions"]}
    reasons = {s["visibility_reason"] for s in d["sessions"]}
    check(
        "PAYMENT as member: Payments teammates visible, QA hidden",
        "Dana Kowalski" not in authors and {"Asha Raman", "Ben Okafor"} <= authors and d["hidden_session_count"] >= 1,
        f"visible={sorted(authors)} hidden={d['hidden_session_count']} reasons={sorted(reasons)}",
    )
    check("visibility reasons are team:Payments", reasons <= {"team:Payments", "own"}, str(reasons))
    d = m.get(f"/features/{login['id']}").json()
    check("LOGIN as member (assigned, not on Platform): 0 visible, rest hidden", d["sessions"] == [] and d["hidden_session_count"] >= 3, f"hidden={d['hidden_session_count']}")
    d = a.get(f"/features/{payment['id']}").json()
    check("admin sees every PAYMENT session", d["hidden_session_count"] == 0 and all(s["visibility_reason"] == "admin" for s in d["sessions"]), f"n={len(d['sessions'])}")

    # --- session lifecycle ---------------------------------------------------------
    r = m.post("/sessions", json={"feature_id": payment["id"], "agent": "claude-code", "model": "claude-opus-5", "goal": "E2E: add settlement export"})
    s = r.json()
    check("member starts session on PAYMENT", r.status_code == 201 and s["status"] == "active" and s["user_id"] == member.id, r.text[:100] if r.status_code != 201 else s["id"])
    r = m.post("/sessions", json={"feature_id": notif["id"], "agent": "manual", "goal": "should fail"})
    check("member cannot start session on NOTIFICATION", r.status_code == 403)
    r = m.post(f"/sessions/{s['id']}/complete", json={"context": {"goal": "x", "confidence": 1.5}})
    check("invalid context (confidence 1.5) → 422", r.status_code == 422)
    ctx = {
        "goal": "E2E: add settlement export",
        "changes": ["Added GET /settlements/export"],
        "decisions": ["CSV, not XLSX"],
        "files": ["services/payments/export.py"],
        "dependencies": [],
        "constraints": ["Max 10k rows per export"],
        "known_issues": [],
        "open_questions": ["Do finance need a scheduled export?"],
        "confidence": 0.8,
    }
    r = m.post(f"/sessions/{s['id']}/complete", json={"context": ctx, "summary": "Export endpoint shipped."})
    s2 = r.json()
    check("complete session → completed, ctx v1", r.status_code == 200 and s2["status"] == "completed" and s2["context_version"] == 1 and s2["ended_at"], r.text[:120])
    entries = m.get(f"/features/{payment['id']}/context").json()
    check("Context Bank has session_summary with provenance", any(e["session_id"] == s["id"] and e["kind"] == "session_summary" and e["author_user_id"] == member.id for e in entries), f"entries={len(entries)}")
    other = next(x for x in a.get(f"/features/{payment['id']}").json()["sessions"] if x["user_id"] != member.id)
    r = m.patch(f"/sessions/{other['id']}", json={"goal": "hijack"})
    check("member cannot edit someone else's session", r.status_code == 403 and r.json()["detail"]["code"] == "SESSION_READ_ONLY", str(r.status_code))
    r = m.post("/features", json={"key": "HACK", "name": "x"})
    check("member cannot create features", r.status_code == 403)
    r = m.get("/sessions/mine")
    check("/sessions/mine lists own session", any(x["id"] == s["id"] for x in r.json()))

    # --- stubs ---------------------------------------------------------------------
    r = m.post("/context-sync/push", json={"client_id": "c1", "feature_id": payment["id"], "local_version": 1, "entries": [], "idempotency_key": "k1"})
    check("context-sync stub → 501", r.status_code == 501 and r.json()["detail"]["code"] == "NOT_IMPLEMENTED")

    # --- tenant isolation ---------------------------------------------------------
    o2 = Api(token_for(admin.id, org2.id))
    r = o2.get("/features")
    check("other org sees no features", r.status_code == 200 and r.json() == [])
    r = o2.get(f"/features/{payment['id']}")
    check("other org cannot fetch org-1 feature (404)", r.status_code == 404)

    return 0


def cleanup() -> None:
    print("cleaning up…")
    for oid in created["orgs"]:
        try:
            clerk.organizations.delete(organization_id=oid)
        except Exception as e:  # noqa: BLE001
            print("  clerk org delete failed", oid, e)
    for uid in created["users"]:
        try:
            clerk.users.delete(user_id=uid)
        except Exception as e:  # noqa: BLE001
            print("  clerk user delete failed", uid, e)
    if created["orgs"]:
        try:
            get_db().table("organizations").delete().in_("clerk_org_id", created["orgs"]).execute()
        except Exception as e:  # noqa: BLE001
            print("  db cleanup failed", e)


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    finally:
        cleanup()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(code or (1 if failed else 0))
