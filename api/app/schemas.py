"""Pydantic models: API I/O plus the Session Context contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SessionStatus = Literal["active", "completed", "failed", "abandoned"]
FeatureStatus = Literal["active", "archived"]
ContextKind = Literal["decision", "constraint", "architecture", "change", "known_issue", "open_question"]
ContextStatus = Literal["active", "superseded", "pending_review", "rejected"]

CONTEXT_KINDS: tuple[str, ...] = ("decision", "constraint", "architecture", "change", "known_issue", "open_question")


class _Row(BaseModel):
    """Base for models built straight from DB rows (unknown columns ignored)."""

    model_config = ConfigDict(extra="ignore")


# --- Context contract -------------------------------------------------------


class Decision(BaseModel):
    """A technical decision and why it was taken."""

    decision: str = Field(min_length=1, max_length=1000)
    reason: str | None = Field(default=None, max_length=2000)


class ContextContract(BaseModel):
    """The Context Contract (phase-1-requirements §6).

    The minimum information a completed coding session must yield, whoever or
    whatever produced it. Everything entering the Context Bank passes through
    this shape first — model output is not trusted just because it came from an
    agent (design principle 12).
    """

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=2000)
    changes: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    known_issues: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


# --- Identity ---------------------------------------------------------------


class UserOut(_Row):
    id: str
    clerk_org_id: str
    email: str | None = None
    display_name: str
    avatar_url: str | None = None
    role: str
    is_demo: bool = False


class OrganizationOut(_Row):
    clerk_org_id: str
    name: str
    slug: str | None = None


class PrincipalOut(BaseModel):
    user_id: str
    org_id: str
    role: str
    clerk_role: str


class TeamSummary(_Row):
    id: str
    name: str


class MeOut(BaseModel):
    principal: PrincipalOut
    user: UserOut
    organization: OrganizationOut
    teams: list[TeamSummary]


# --- Teams ------------------------------------------------------------------


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class TeamOut(_Row):
    id: str
    clerk_org_id: str
    name: str
    description: str | None = None
    created_at: datetime
    members: list[UserOut] = Field(default_factory=list)


# --- Features ---------------------------------------------------------------


class FeatureCreate(BaseModel):
    key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$", description="Stable identifier, e.g. LOGIN")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    team_ids: list[str] = Field(default_factory=list)
    assignee_ids: list[str] = Field(default_factory=list)


class FeatureUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    status: FeatureStatus | None = None


class FeatureSummary(_Row):
    id: str
    key: str
    name: str


class FeatureOut(_Row):
    id: str
    clerk_org_id: str
    key: str
    name: str
    description: str | None = None
    status: FeatureStatus
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    access_reason: str | None = None  # admin | assigned | team
    teams: list[TeamSummary] = Field(default_factory=list)
    assignees: list[UserOut] = Field(default_factory=list)
    session_count: int = 0


# --- Sessions ---------------------------------------------------------------


class SessionCreate(BaseModel):
    feature_id: str
    agent: str = Field(default="manual", max_length=60)
    model: str | None = Field(default=None, max_length=80)
    goal: str | None = Field(default=None, max_length=2000)


class SessionUpdate(BaseModel):
    agent: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=80)
    goal: str | None = Field(default=None, max_length=2000)
    summary: str | None = Field(default=None, max_length=4000)
    status: SessionStatus | None = None


class SessionComplete(BaseModel):
    """Body for POST /sessions/{id}/complete.

    `context` is optional: when the caller (the UI form today, a coding agent
    later) supplies a draft it is used as-is; when omitted the Context Generator
    derives one from session metadata. Either way the validator runs before
    anything is persisted (§7).
    """

    context: ContextContract | None = None
    summary: str | None = Field(default=None, max_length=4000)
    status: Literal["completed", "failed", "abandoned"] = "completed"


class SessionOut(_Row):
    id: str
    clerk_org_id: str
    feature_id: str
    user_id: str
    agent: str
    model: str | None = None
    status: SessionStatus
    goal: str | None = None
    summary: str | None = None
    context: dict[str, Any] | None = None
    context_version: int = 0
    started_at: datetime
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    author: UserOut | None = None
    feature: FeatureSummary | None = None
    visibility_reason: str | None = None  # admin | own | team:<name>


# --- Context Bank -----------------------------------------------------------


class ContextEntryOut(_Row):
    id: str
    clerk_org_id: str | None = None
    feature_id: str
    session_id: str | None = None
    author_user_id: str | None = None
    kind: ContextKind
    version: int
    title: str
    payload: dict[str, Any]
    confidence: float | None = None
    status: ContextStatus
    supersedes_id: str | None = None
    # Phase 2 §9: evidence backing the statement (files, tests, commit…), distinct from the payload.
    evidence: dict[str, Any] | None = None
    # Phase 2 §17: the active entry this one was flagged as resembling.
    conflicts_with: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    # Hydrated for provenance: context → source session → author (§9, §15).
    author: UserOut | None = None
    session: SessionOut | None = None
    feature: FeatureSummary | None = None


class Evidence(BaseModel):
    """What a statement rests on (phase-2 §9). All optional; collected automatically in a later slice."""

    model_config = ConfigDict(extra="forbid")

    repository: str | None = None
    branch: str | None = None
    commit: str | None = None
    files: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    test_results: str | None = None
    build_results: str | None = None
    errors: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)


class ContextEntryCreate(BaseModel):
    """Manually authored context (POST /features/{id}/context)."""

    kind: ContextKind
    title: str = Field(min_length=1, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    session_id: str | None = Field(default=None, description="Optional provenance link")
    evidence: Evidence | None = None
    request_id: str | None = Field(
        default=None, max_length=128, description="Idempotency key: the same id returns the first result"
    )


class ContextEntryUpdate(BaseModel):
    """A revision (PATCH /context/{id}).

    Editing content creates a NEW version and marks the current row superseded;
    the old row stays readable. A status-only change is applied in place.
    """

    title: str | None = Field(default=None, min_length=1, max_length=500)
    payload: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    kind: ContextKind | None = None
    status: ContextStatus | None = None
    evidence: Evidence | None = None
    request_id: str | None = Field(default=None, max_length=128)


class SessionCheckpoint(BaseModel):
    """Body for POST /sessions/{id}/checkpoint (phase-2 §13.3).

    Mid-session durable context: the same generate → validate → fan-out as
    completion, but the session stays active so the agent keeps working.
    """

    context: ContextContract | None = None
    summary: str | None = Field(default=None, max_length=4000)
    evidence: Evidence | None = None
    request_id: str | None = Field(default=None, max_length=128)


class AgentGrantOut(_Row):
    """An agent credential (phase-2 §5.1)."""

    id: str
    clerk_org_id: str
    user_id: str
    client_id: str
    client_name: str | None = None
    scopes: list[str]
    feature_ids: list[str] | None = None
    status: Literal["active", "revoked"]
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    creator: UserOut | None = None
    features: list[FeatureSummary] = Field(default_factory=list)


class PendingAuthorizationOut(BaseModel):
    id: str
    client_id: str
    client_name: str
    scopes: list[str]
    redirect_uri: str | None = None
    expires_at: str


# --- Local/cloud synchronization (phase-2 §10, §11) --------------------------


class SyncPullResult(BaseModel):
    feature_id: str
    feature_key: str
    cursor: str | None = Field(default=None, description="Pass back as `since` on the next pull")
    total: int = Field(description="Entries the cloud holds for this feature")
    entries: list[ContextEntryOut] = Field(default_factory=list)


class SyncStatusOut(BaseModel):
    feature_id: str
    feature_key: str
    cloud_total: int
    client_cursor: str | None = None
    behind: int = Field(description="Entries newer than this client's cursor")
    last_synced_at: datetime | None = None


class SyncPushEntry(ContextEntryCreate):
    """A statement captured locally. `request_id` makes the upload idempotent."""

    request_id: str = Field(min_length=1, max_length=128)


class SyncPushRequest(BaseModel):
    client_id: str = Field(min_length=8, max_length=128)
    label: str | None = None
    entries: list[SyncPushEntry] = Field(default_factory=list, max_length=200)


class SyncPushResult(BaseModel):
    accepted: list[ContextEntryOut] = Field(default_factory=list)
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    flagged_for_review: int = 0


class ValidationIssue(BaseModel):
    field: str
    code: str
    message: str


class CompletionResult(BaseModel):
    """What POST /sessions/{id}/complete returns."""

    session: SessionOut
    context_entries: list[ContextEntryOut] = Field(default_factory=list)
    generated: bool = Field(description="True when the Context Generator produced the contract")
    contract: ContextContract | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    quarantined: bool = Field(default=False, description="True when entries were stored as pending_review")
    idempotent_replay: bool = Field(default=False, description="True when the session was already completed")


class FeatureDetail(FeatureOut):
    sessions: list[SessionOut] = Field(default_factory=list)
    hidden_session_count: int = 0
    context_entries: list[ContextEntryOut] = Field(default_factory=list)


# --- Admin ------------------------------------------------------------------


class SeedResult(BaseModel):
    created: dict[str, int]
    message: str


class SyncResult(BaseModel):
    synced: int
    message: str


# --- Stub contracts (documented extension points; endpoints return 501) -----


class NotImplementedOut(BaseModel):
    code: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"
    message: str
    planned_flow: list[str]


class ContextEntryIn(ContextEntryCreate):
    """Entry shape accepted by the (stubbed) sync endpoints."""


class ContextSyncPushRequest(BaseModel):
    """Local Context Store → Cloud Context Bank (async, idempotent)."""

    client_id: str = Field(description="Stable id of the local store instance")
    feature_id: str
    local_version: int
    entries: list[ContextEntryIn]
    idempotency_key: str


class ContextSyncPullRequest(BaseModel):
    """Cache miss on the local store → fetch relevant context from the bank."""

    client_id: str
    feature_ids: list[str]
    since_version: dict[str, int] = Field(default_factory=dict, description="feature_id → last version seen")


class IngestionRequest(BaseModel):
    """Agent submits end-of-session context (validate → normalize → conflict-detect → bank)."""

    agent: str
    model: str
    context: ContextContract
    transcript_ref: str | None = Field(default=None, description="Customer-side pointer; transcripts never leave the customer plane")


class ClaudeWebhookEvent(BaseModel):
    event_type: Literal["session.started", "session.ended", "session.compacted"]
    event_id: str = Field(description="Used for duplicate-delivery protection")
    session_id: str
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class OrchestrationRequest(BaseModel):
    feature_id: str
    agent: str
    model: str
    instructions: str
    scope: dict[str, Any] = Field(default_factory=dict, description="Explicit authorization scope for the agent")
