# Forge Phase 1 Requirements — Context MVP

## 1. Purpose

Phase 1 turns Forge from an access-control POC into a working persistent engineering-context system.

The goal is deliberately narrow:

> Convert completed coding-session work into structured, trustworthy feature context that can be consumed by a future developer or coding-agent session.

Phase 1 should establish the foundation for later Claude integration, local context stores, retrieval, synchronization, and multi-agent workflows without implementing those systems yet.

---

## 2. Core Principle

A **session is history**.

A **context entry is engineering knowledge**.

Therefore:

```text
Coding Session
      ↓
Context Extraction
      ↓
Validation / Normalization
      ↓
Context Entry
      ↓
Feature Context Bank
```

The Feature is the ownership boundary for accumulated context.

The user is the actor/author of a session, not the owner of the resulting feature context.

---

## 3. Scope

### 3.1 In Scope

Phase 1 must implement:

1. Session lifecycle and metadata.
2. A standardized Context Contract.
3. Context generation from session information.
4. Context validation and normalization.
5. Context entries associated with features.
6. Session-to-context provenance.
7. Basic context versioning.
8. Context retrieval by feature.
9. Context visibility using the existing Forge access rules.
10. Context CRUD where appropriate.
11. Clear separation between session history and accumulated feature context.

### 3.2 Out of Scope

Do not implement yet:

- Real Claude webhook integration.
- Claude `/compact` integration.
- Local Context Store.
- Local/cloud synchronization.
- Vector database.
- Embedding generation.
- Semantic/vector retrieval.
- Full RAG pipeline.
- Automatic conflict resolution.
- Multi-agent orchestration.
- Jira integration.
- Repository integration.
- Production log ingestion.
- Advanced context quality scoring.
- Enterprise/customer-hosted Context Bank.

Dummy session data may be used to exercise the complete flow.

---

## 4. Existing Architecture

Current stack:

- Next.js 16 App Router
- FastAPI
- Supabase/Postgres
- Clerk Organizations and organization roles

Existing access model:

```text
Feature access =
    admin
    OR directly assigned
    OR member of an owning team

Session visibility =
    own sessions
    +
    sessions by authors on an owning team you share

Context visibility =
    follows feature access
```

Do not change the existing access model unless required by a concrete Phase 1 requirement.

---

## 5. Domain Model

### 5.1 Feature

A Feature is the primary engineering ownership boundary.

Examples:

```text
LOGIN
PAYMENT
DOCUMENT_PROCESSING
USER_CREATION
NOTIFICATION
```

A Feature owns its accumulated engineering context.

### 5.2 Session

A Session represents one unit of developer or coding-agent work against a Feature.

A session contains metadata such as:

```text
id
organization
feature
user
agent
model
status
goal
summary
started_at
ended_at
created_at
updated_at
```

A session is historical and should not be mutated merely because newer context is created.

### 5.3 Context Entry

A Context Entry represents a durable piece of engineering knowledge associated with a Feature.

Suggested fields:

```text
id
organization
feature
source_session
author_user
kind
title
payload
version
status
created_at
updated_at
```

Suggested `kind` values:

```text
decision
constraint
architecture
change
known_issue
open_question
```

Suggested `status` values:

```text
active
superseded
pending_review
rejected
```

The exact implementation may differ if an equivalent model is cleaner.

---

## 6. Context Contract

The Context Contract defines the minimum information that should be produced from a completed coding session.

The contract must support:

```text
Objective
Changes
Technical Decisions
Affected Files / Components
Constraints
Dependencies
Known Issues
Open Questions
Confidence
```

Example:

```json
{
  "objective": "Add refresh-token rotation",
  "changes": [
    "Added refresh token rotation",
    "Updated authentication middleware"
  ],
  "decisions": [
    {
      "decision": "Rotation happens server-side",
      "reason": "Prevents token reuse"
    }
  ],
  "affected_components": [
    "auth/middleware.py",
    "auth/service.py"
  ],
  "constraints": [
    "Existing mobile clients must remain compatible"
  ],
  "dependencies": [
    "Token store"
  ],
  "known_issues": [
    "Old clients do not support token family revocation"
  ],
  "open_questions": [
    "When should old token families expire?"
  ],
  "confidence": 0.92
}
```

The contract should be represented as a typed/schema-validated object rather than an arbitrary JSON blob wherever practical.

---

## 7. Context Generation

Phase 1 should introduce a Context Generator abstraction.

Input:

```text
Session
+
available session information
```

Output:

```text
Context Contract
```

The generator must not directly write to the Context Bank.

Required flow:

```text
Session
  ↓
Context Generator
  ↓
Context Contract
  ↓
Validator
  ↓
Context Bank
```

For the POC/Phase 1 implementation, the generator may use deterministic dummy logic or a simple service abstraction.

The interface should make it possible to replace it later with an LLM-based generator without changing the Context Bank API.

---

## 8. Context Validation

The validator must run before context is persisted as active context.

### Minimum validation

Validate:

- Required fields exist.
- Field types are correct.
- Feature exists.
- Source session exists.
- Source session belongs to the same organization.
- Context belongs to the same organization as the session.
- `confidence` is within its valid range.
- `kind` is supported.
- Payload follows the Context Contract.

Invalid context must not silently become active Context Bank data.

For Phase 1, invalid context may be marked:

```text
pending_review
```

or rejected with a clear API error.

---

## 9. Provenance

Every Context Entry must be traceable to its source.

At minimum:

```text
Context Entry
    ↓
source_session_id
    ↓
Session
    ↓
User
```

The UI should eventually be able to answer:

> "Where did this context come from?"

For Phase 1, displaying the source session and author is sufficient.

Do not discard provenance when updating or versioning context.

---

## 10. Versioning

Context must not be silently overwritten.

A Context Entry should have a version.

Example:

```text
Context C17
    version 1
       ↓
    version 2
       ↓
    version 3
```

When a newer version replaces an older statement, the previous version should remain recoverable.

For Phase 1:

- Store version number.
- Preserve the previous record or equivalent history.
- Mark replaced context as `superseded`.
- Keep the source session for every version.

Full automatic conflict resolution is out of scope.

---

## 11. Context Retrieval

Phase 1 retrieval should be simple.

Given:

```text
organization
feature
authorized user
```

return the active context entries for that Feature that the user is authorized to view.

Do not introduce vector search yet.

The initial retrieval strategy should use:

```text
organization filter
+
feature filter
+
status = active
+
authorization
```

Optional filtering by `kind` is useful.

---

## 12. Access Control

Context follows the existing Feature access boundary.

A user must be authorized to access the Feature before retrieving its context.

The backend must enforce this.

The frontend must not be treated as the security boundary.

A user who cannot access Feature A must not be able to retrieve Feature A's Context Bank entries by directly calling the API.

Context authorization should reuse the existing pure access functions rather than duplicating rules in routers.

---

## 13. Session Completion

Phase 1 should support a logical session-completion operation.

Example:

```text
POST /sessions/{session_id}/complete
```

Expected flow:

```text
Complete Session
      ↓
Generate Context
      ↓
Validate Context
      ↓
Persist Context Entry
      ↓
Mark Session Completed
```

If context generation or validation fails:

- Do not silently publish invalid context.
- Preserve the session.
- Return a meaningful failure state.

The operation should be idempotent where practical.

---

## 14. API Requirements

Exact route naming can follow the existing FastAPI conventions.

Minimum capabilities:

### Sessions

```text
GET    /sessions
GET    /sessions/{id}
POST   /sessions
PATCH  /sessions/{id}
POST   /sessions/{id}/complete
```

### Context

```text
GET    /features/{feature_id}/context
GET    /context/{id}
POST   /features/{feature_id}/context
PATCH  /context/{id}
```

Deletion should be considered carefully because context represents historical engineering knowledge. Prefer status changes such as `rejected` or `superseded` over destructive deletion for persisted context.

All endpoints must enforce organization and feature access.

---

## 15. UI Requirements

Phase 1 UI should expose the concept clearly without attempting to build the final Forge product.

### Feature Detail

Show:

```text
Feature
├── Description
├── Team
├── Members
├── Context
└── Sessions
```

### Context

For each context entry show:

```text
Kind
Title
Summary / payload
Author
Source session
Version
Status
Created at
```

### Session

Show:

```text
Author
Agent / model
Status
Goal
Summary
Started
Ended
Context generated
```

A user should be able to navigate:

```text
Feature
  ↓
Context Entry
  ↓
Source Session
  ↓
Author
```

This provenance path is important to the product concept.

---

## 16. Context Quality

Phase 1 establishes the structure for quality control but does not require sophisticated quality scoring.

The architecture must leave room for:

```text
Completeness
Evidence coverage
Consistency
Freshness
Confidence
```

Future ingestion:

```text
Agent Session
      ↓
Context Generator
      ↓
Validator
      ↓
Evidence checks
      ↓
Conflict detection
      ↓
Context Bank
```

Do not claim that Phase 1 provides full hallucination protection.

---

## 17. Database Changes

The existing `context_entries` table should become the primary representation of Feature Context.

Avoid treating `sessions.context` as the canonical Context Bank.

Preferred conceptual relationship:

```text
Feature
  │
  ├── Sessions
  │     ├── Session A
  │     ├── Session B
  │     └── Session C
  │
  └── Context Entries
        ├── Context A
        ├── Context B
        └── Context C
```

Context entries reference their source session for provenance.

If `sessions.context` remains temporarily for compatibility, it must not be treated as the source of truth.

---

## 18. Error and Failure Handling

The system must handle:

- Missing session
- Missing feature
- Unauthorized feature access
- Cross-organization session/context references
- Invalid context schema
- Duplicate completion requests
- Invalid context version
- Failed context generation
- Failed persistence

No cross-tenant data may be returned in an error response or successful response.

---

## 19. Observability

Phase 1 should log enough information to debug ingestion failures.

At minimum:

```text
organization_id
feature_id
session_id
user_id
operation
status
error_type
timestamp
```

Do not log sensitive session content unnecessarily.

---

## 20. Acceptance Criteria

Phase 1 is complete when all of the following work:

### Session

- A user can create a session for an authorized Feature.
- A user can view authorized sessions.
- A session can be completed.
- Completing a session produces a Context Entry.

### Context

- Context follows the Context Contract.
- Invalid context is rejected or quarantined.
- Every context entry has source-session provenance.
- Context entries are associated with a Feature.
- Context versions are preserved.
- Active context can be retrieved by Feature.

### Access

- Unauthorized users cannot retrieve Feature context.
- Existing Clerk-based organization access continues to work.
- Tenant isolation remains enforced.
- Session visibility rules remain unchanged.

### UI

- Feature context is visible.
- Session history is visible.
- Context provenance is visible.
- A user can navigate from context → source session → author.

### Quality

- Unit tests cover Context validation.
- Unit tests cover authorization.
- Integration tests cover session completion → context creation.
- Duplicate completion does not create unintended duplicate active context.

---

## 21. Future Architecture

Phase 1 should provide extension points for:

```text
Claude / Coding Agent
        ↓
Webhook / Session Collector
        ↓
Context Generator
        ↓
Context Validator
        ↓
Context Quality Layer
        ↓
Cloud Context Bank
        ↕
Local Context Store
```

Future retrieval may become:

```text
Local Context Store
       ↓
cache hit?
   ┌───┴───┐
  YES      NO
   │        │
   ▼        ▼
Context   Cloud Context Bank
             ↓
       Metadata filtering
             ↓
       Semantic retrieval
             ↓
       Local Context Store
```

This future design must not force Phase 1 to introduce unnecessary infrastructure.

---

## 22. Design Principles

1. **Feature owns context.**
2. **User authors sessions; user does not own feature context.**
3. **Session history and feature knowledge are different entities.**
4. **Cloud Context Bank is the long-term source of truth.**
5. **Local Context Store is a cache/replica, not an authority.**
6. **Every context entry has provenance.**
7. **Context is versioned rather than silently overwritten.**
8. **Authorization is enforced server-side.**
9. **Clerk owns identity and organization identity.**
10. **Context generation and context validation are separate responsibilities.**
11. **Do not add vector search until simple retrieval is insufficient.**
12. **Do not treat model output as trustworthy merely because it came from an AI agent.**
