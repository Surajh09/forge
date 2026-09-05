"""Auth & Access Layer — pure access-rule functions.

These take plain data (ids, sets, dicts) so they can be unit-tested without a
database. Routers gather the inputs from the repos and call these.

Rules (requirement.md §6, phase-2 §6/§14):
  - Feature access: admin, OR directly assigned, OR member of a team attached
    to the feature. An agent credential can only *narrow* this with a feature
    allow-list; it can never widen it.
  - Session visibility inside an accessible feature: own sessions, plus
    sessions authored by users on a feature-attached team that the viewer is
    also on. Admin sees everything in the org.
  - Context entries follow feature access.
  - Agents additionally need the right OAuth scope for each action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping

Role = str  # "admin" | "developer" | "qa"
PrincipalType = Literal["user", "agent"]

# Clerk org roles (token v2 `o.rol`, without the `org:` prefix) → Forge roles.
CLERK_ROLE_MAP: dict[str, Role] = {
    "admin": "admin",
    "member": "developer",
    "developer": "developer",
    "qa": "qa",
}

# OAuth scopes an agent credential can hold (phase-2 §14).
SCOPE_CONTEXT_READ = "context.read"
SCOPE_CONTEXT_WRITE = "context.write"
SCOPE_CONTEXT_SUPERSEDE = "context.supersede"
SCOPE_SESSION_WRITE = "session.write"
ALL_SCOPES: tuple[str, ...] = (
    SCOPE_CONTEXT_READ,
    SCOPE_CONTEXT_WRITE,
    SCOPE_CONTEXT_SUPERSEDE,
    SCOPE_SESSION_WRITE,
)
SCOPE_DESCRIPTIONS: dict[str, str] = {
    SCOPE_CONTEXT_READ: "Read feature context and search the Context Bank",
    SCOPE_CONTEXT_WRITE: "Record new context statements",
    SCOPE_CONTEXT_SUPERSEDE: "Replace existing statements with newer versions",
    SCOPE_SESSION_WRITE: "Start, checkpoint and complete sessions",
}

# Agents never inherit admin; least privilege by construction (phase-2 §5.1).
AGENT_ROLE_CAP: Role = "developer"


def normalize_role(clerk_role: str | None) -> Role:
    if not clerk_role:
        return "developer"
    raw = clerk_role.removeprefix("org:").lower()
    return CLERK_ROLE_MAP.get(raw, "developer")


@dataclass(frozen=True)
class Principal:
    user_id: str
    org_id: str
    role: Role
    clerk_role: str = ""
    # Phase 2: who is acting. Agents act as `user_id` (the grant's creator) but
    # are narrowed by scopes and an optional feature allow-list.
    principal_type: PrincipalType = "user"
    scopes: frozenset[str] = field(default_factory=frozenset)
    feature_ids: frozenset[str] | None = None
    credential_id: str | None = None
    client_name: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_agent(self) -> bool:
        return self.principal_type == "agent"

    def has_scope(self, scope: str) -> bool:
        """Users hold every scope implicitly; agents only what they were granted."""
        return not self.is_agent or scope in self.scopes

    def may_touch_feature(self, feature_id: str) -> bool:
        """Credential allow-list check. None means no narrowing beyond the creator's access."""
        return self.feature_ids is None or feature_id in self.feature_ids


def feature_access(
    p: Principal,
    *,
    feature_team_ids: Iterable[str],
    my_team_ids: Iterable[str],
    assignee_ids: Iterable[str],
    feature_id: str | None = None,
) -> str | None:
    """Return the reason the principal may access the feature, or None.

    The credential allow-list is applied first and applies to everyone,
    including admins, so a narrowed credential can never be widened by role.
    """
    if feature_id is not None and not p.may_touch_feature(feature_id):
        return None
    if p.is_admin:
        return "admin"
    if p.user_id in set(assignee_ids):
        return "assigned"
    if set(feature_team_ids) & set(my_team_ids):
        return "team"
    return None


def visible_sessions(
    p: Principal,
    sessions: Iterable[Mapping[str, Any]],
    *,
    feature_team_ids: Iterable[str],
    my_team_ids: Iterable[str],
    team_members: Mapping[str, Iterable[str]],
    team_names: Mapping[str, str] | None = None,
) -> list[tuple[Mapping[str, Any], str]]:
    """Filter sessions of one feature down to what the principal may see.

    Returns (session, reason) pairs; reason is "admin", "own" or "team:<name>".
    """
    sessions = list(sessions)
    if p.is_admin:
        return [(s, "admin") for s in sessions]

    names = dict(team_names or {})
    shared = set(feature_team_ids) & set(my_team_ids)
    author_reason: dict[str, str] = {}
    for team_id in sorted(shared, key=lambda t: names.get(t, t)):
        for uid in team_members.get(team_id, ()):
            author_reason.setdefault(uid, f"team:{names.get(team_id, team_id)}")

    out: list[tuple[Mapping[str, Any], str]] = []
    for s in sessions:
        author = s.get("user_id")
        if author == p.user_id:
            out.append((s, "own"))
        elif author in author_reason:
            out.append((s, author_reason[author]))
    return out


def can_edit_session(p: Principal, session: Mapping[str, Any]) -> bool:
    return p.is_admin or session.get("user_id") == p.user_id
