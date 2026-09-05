# Forge Phase 2 Requirements

## Agent Integration, Local Package, MCP, Skill, and Autonomous Context Sync

**Status:** Proposed\
**Phase:** 2\
**Depends on:** Phase 1 Context MVP\
**Primary goal:** Make Forge usable by real coding agents during real
engineering work.

------------------------------------------------------------------------

## 1. Purpose

Phase 1 established the Context Bank lifecycle:

``` text
Session
  ↓
Context Generator
  ↓
Context Validator
  ↓
Typed Context Entries
  ↓
Context Bank
```

Phase 2 turns that backend capability into an agent-facing product.

The core outcome is:

> An engineer installs Forge once, connects an AI coding agent, and the
> agent can retrieve, contribute, and act on feature-scoped Forge
> context without requiring manual context maintenance.

Forge should work across multiple coding agents and should not depend on
one specific agent vendor.

------------------------------------------------------------------------

# 2. Product Model

Forge Phase 2 consists of four cooperating components:

``` text
Developer Machine
┌──────────────────────────────────────────────┐
│                                              │
│  Claude / Codex / Cursor / Other Agents      │
│                 │                            │
│            Forge Skill                       │
│                 │                            │
│            Forge MCP                         │
│                 │                            │
│        Forge Local Package                   │
│                 │                            │
│        Local Context Store                   │
│                                              │
└──────────────────┬───────────────────────────┘
                   │
                   │ authenticated API
                   ▼
            Forge Cloud
        ┌────────────────────┐
        │ Context Bank       │
        │ Features           │
        │ Sessions           │
        │ Authorization      │
        │ Validation         │
        │ Agent Actions      │
        └────────────────────┘
```

Each component has a distinct responsibility.

------------------------------------------------------------------------

# 3. Component Responsibilities

## 3.1 Forge Local Package

The local package handles developer-machine operations.

Responsibilities:

-   CLI
-   local configuration
-   local Context Store
-   context pull/push/sync
-   Git/evidence collection
-   local lifecycle hooks
-   agent installation/configuration
-   credential management
-   diagnostics
-   offline/local operation where practical

The package may access local resources that Forge Cloud should not
directly access, including:

-   repository files
-   Git history
-   Git diff
-   changed files
-   test output
-   build output
-   local agent state
-   local context cache

The package must not expose the user's service/admin credentials to an
AI agent.

------------------------------------------------------------------------

## 3.2 Forge MCP

Forge MCP is the standardized agent-facing interface.

MCP should be treated as the integration boundary between Forge and
coding agents.

The server should expose focused tools rather than a large tool catalog.

Initial tools:

``` text
forge_context_get
forge_context_search
forge_context_record
forge_context_supersede

forge_feature_get

forge_session_start
forge_session_checkpoint
forge_session_complete
```

Future action tools may be added separately.

MCP should remain independent of any particular coding agent.

The current MCP ecosystem supports tools, resources, and prompts, and
the 2026-07-28 specification provides a stateless protocol core suitable
for ordinary HTTP infrastructure. citeturn0search1turn0search2

------------------------------------------------------------------------

## 3.3 Forge Skill

The Forge Skill provides behavioral instructions to the coding agent.

The skill must explain:

1.  Identify the current Forge Feature.
2.  Retrieve relevant Forge context before beginning independent
    investigation.
3.  Use existing context when it is relevant.
4.  If relevant context is missing or insufficient, perform local
    discovery.
5.  Use evidence from discovery to generate durable context.
6.  Submit durable context through Forge.
7.  Do not upload temporary observations or raw transcripts as durable
    knowledge.
8.  When existing knowledge is contradicted, use the supersede/conflict
    flow.
9.  At checkpoints and session completion, preserve durable engineering
    knowledge.

The Skill is guidance, not the sole security or enforcement mechanism.

MCP server instructions/prompts can help clients and models understand
how a server should be used, but authorization and important lifecycle
guarantees must remain in application logic.
citeturn0search6turn0search8

------------------------------------------------------------------------

# 4. Agent-Agnostic Requirement

Forge must support multiple coding agents.

Initial target clients may include:

-   Claude Code
-   Codex
-   Cursor
-   other MCP-compatible coding agents

Forge must not contain agent-specific business logic in the Context Bank
or core authorization layer.

The intended model is:

``` text
Claude ──┐
Codex ───┤
Cursor ──┼──→ Forge MCP → Forge
Other ───┘
```

The MCP boundary should allow new agents to integrate without changing
Forge's core domain model.

------------------------------------------------------------------------

# 5. Authentication

Forge must provide credentials suitable for local packages and agent
integrations.

## 5.1 Agent Credential

A Forge agent credential is a scoped credential created by an authorized
user.

It should contain or resolve to:

-   organization
-   creator
-   principal type
-   scopes
-   optional feature restrictions
-   expiration
-   revocation state
-   creation time
-   last-used time

Example conceptual credential:

``` text
organization: acme
principal: agent
features:
  - PAYMENT
  - CHECKOUT
scopes:
  - context.read
  - context.write
  - session.write
expires: 2026-10-05
```

Credentials must follow least privilege.

An agent must never receive:

-   Forge service-role credentials
-   database credentials
-   unrestricted administrative credentials
-   Clerk backend secrets

## 5.2 MCP Authorization

Remote HTTP MCP should use the MCP-compatible authorization model rather
than inventing a proprietary transport-level authentication mechanism.

The current MCP specification aligns authorization with OAuth/OIDC
practices and has hardened token issuer/audience handling. MCP also has
an extension for machine-to-machine client credentials.
citeturn0search0turn0search12

For the local developer package, Forge may provide a simpler
login/configuration flow that stores credentials securely on the
machine.

Example:

``` text
forge login
forge connect claude
forge init
```

------------------------------------------------------------------------

# 6. Feature Context Boundary

Feature remains the primary engineering ownership boundary.

An agent should operate against a feature such as:

``` text
PAYMENT
LOGIN
DOCUMENT_PROCESSING
USER_CREATION
NOTIFICATION
```

Context retrieval must be feature-scoped.

The agent should not receive unrelated organization-wide context merely
because it has a valid Forge credential.

Authorization must continue to use the existing Phase 1 Forge access
model.

------------------------------------------------------------------------

# 7. Context Retrieval Workflow

Before independent investigation:

``` text
Agent
  ↓
Identify Feature
  ↓
Forge context_search / context_get
  ↓
Relevant context?
 ┌───────────────┴───────────────┐
 │                               │
YES                             NO
 │                               │
 ▼                               ▼
Use context               Local code discovery
                                 │
                                 ▼
                              Evidence
                                 │
                                 ▼
                         Context Generator
                                 │
                                 ▼
                          Context Validator
                                 │
                                 ▼
                          Forge Context Bank
```

The agent should not be required to call Forge before every low-level
filesystem operation.

Forge should sit before **independent engineering investigation**, not
become a network toll booth for every `grep`, file read, or directory
listing.

------------------------------------------------------------------------

# 8. Autonomous Context Contribution

When Forge lacks relevant context, the agent may discover useful
information locally.

The discovered information must go through the existing Phase 1
pipeline.

``` text
Local discovery
      ↓
Evidence
      ↓
Context Generator
      ↓
Context Validator
      ↓
Typed Context Entries
      ↓
Forge Context Bank
```

The agent must not bypass validation by writing arbitrary context
directly to the database.

------------------------------------------------------------------------

# 9. Evidence

Phase 2 should begin attaching stronger evidence to context.

Potential evidence:

-   source session
-   author/agent
-   repository
-   branch
-   commit
-   changed files
-   relevant symbols
-   tests
-   test results
-   build results
-   errors
-   tool observations

Example:

``` text
Decision:
"Payment retries use idempotency keys."

Evidence:
  session: abc123
  files:
    payment_service.py
    stripe.py
  tests:
    test_payment_retry
  commit:
    91af...
```

Evidence must remain distinguishable from the durable statement itself.

------------------------------------------------------------------------

# 10. Local Context Store

Each developer machine may maintain a feature-scoped local Context
Store.

The local store is a cache/replica.

``` text
Forge Cloud Context Bank
          │
          │ sync
          ▼
Local Context Store
```

The cloud Context Bank remains authoritative.

The local store must be:

-   feature-scoped
-   authorized
-   disposable
-   recoverable
-   syncable
-   version-aware

Deleting the local store must not delete canonical Forge context.

Example:

``` text
forge context pull PAYMENT
forge context status PAYMENT
forge context sync PAYMENT
```

------------------------------------------------------------------------

# 11. Autonomous Synchronization

The local package should support autonomous synchronization.

Desired lifecycle:

``` text
Session starts
     ↓
Pull/reconcile relevant feature context
     ↓
Agent works
     ↓
Local evidence collected
     ↓
Checkpoint / session end
     ↓
Generate durable context
     ↓
Validate
     ↓
Upload asynchronously
     ↓
Cloud Context Bank
     ↓
Local cache reconciled
```

Synchronization should be resilient to:

-   temporary network failure
-   duplicate uploads
-   concurrent updates
-   version conflicts
-   stale local cache

The local cache must not become a competing source of truth.

------------------------------------------------------------------------

# 12. Context Serialization

Forge Context uses the Phase 1 TOON decision.

The Context Bank stores TOON as the canonical serialized representation
of context payloads.

Relational metadata remains queryable:

``` text
feature_id
session_id
author_user_id
kind
version
timestamps
lifecycle state
```

The payload is represented using TOON.

For agent delivery:

``` text
Context Bank
    ↓
Context selection
    ↓
TOON serialization
    ↓
MCP response
    ↓
Agent
```

MCP's own protocol messages remain MCP messages. TOON is the
representation of Forge context, not a replacement for the MCP protocol
itself.

------------------------------------------------------------------------

# 13. Agentic Actions

Phase 2 introduces an explicit action surface.

## 13.1 Read Actions

``` text
forge_context_get
forge_context_search
forge_feature_get
```

## 13.2 Context Actions

``` text
forge_context_record
forge_context_supersede
```

## 13.3 Session Actions

``` text
forge_session_start
forge_session_checkpoint
forge_session_complete
```

## 13.4 Future Action Model

Forge may eventually expose actions beyond context:

``` text
propose
  ↓
authorize
  ↓
execute
  ↓
verify
  ↓
record outcome
```

Phase 2 should establish the action boundary without attempting to build
a general autonomous engineering execution platform.

MCP tools are explicitly intended to let models invoke application
actions, while tool annotations can communicate properties such as
read-only, destructive, or idempotent behavior.
citeturn0search8turn0search6

------------------------------------------------------------------------

# 14. Permissions

Every Forge action must resolve authorization using the existing Forge
authorization model.

At minimum:

``` text
Agent credential
      ↓
Organization
      ↓
Feature access
      ↓
Action scope
      ↓
Allow / deny
```

Examples:

``` text
context.read
context.write
session.write
context.supersede
action.execute
```

A credential with `context.read` must not be able to modify context.

A credential limited to PAYMENT must not retrieve LOGIN context.

Authorization must be enforced server-side.

------------------------------------------------------------------------

# 15. Audit

Agent actions should be auditable.

Record:

-   credential/principal
-   organization
-   feature
-   session
-   action
-   timestamp
-   input metadata
-   outcome
-   affected context entries
-   authorization result

The audit trail should make it possible to answer:

> Which agent changed this engineering statement, when, and based on
> what session/evidence?

------------------------------------------------------------------------

# 16. Idempotency and Reliability

Agent operations can be retried.

Writes must therefore support idempotency.

For example:

``` text
context_record
request_id = abc123
```

Repeated submission of the same request should not create duplicate
durable entries.

Synchronization must tolerate:

-   retries
-   process restarts
-   offline operation
-   duplicate events
-   delayed uploads

------------------------------------------------------------------------

# 17. Conflict Handling

Concurrent agents may update the same feature.

Phase 2 must preserve the Phase 1 rule:

> Never silently overwrite durable engineering knowledge.

If Agent A records:

``` text
decision v1
```

and Agent B records a contradictory decision:

``` text
decision v2
```

Forge should detect or flag the conflict and preserve both versions
until resolution.

Automatic conflict resolution is not required for Phase 2.

------------------------------------------------------------------------

# 18. Installation Experience

Target experience:

``` text
forge install
forge login
forge connect claude
forge init
```

The installation should configure:

-   Forge local package
-   Forge MCP
-   Forge Skill
-   agent credential
-   local Context Store
-   feature configuration

The exact commands may change during implementation.

The important requirement is that the developer should not need to
manually configure multiple independent systems.

------------------------------------------------------------------------

# 19. Package / MCP / Skill Boundary

This boundary must remain explicit.

  -----------------------------------------------------------------------
  Component                           Responsibility
  ----------------------------------- -----------------------------------
  Forge Package                       Local machine, CLI, Git/evidence,
                                      sync, hooks, local cache

  Forge MCP                           Agent-facing tools/resources

  Forge Skill                         Agent behavior/instructions

  Forge Cloud                         Canonical context, authorization,
                                      validation, persistence, audit
  -----------------------------------------------------------------------

Do not move responsibilities between these layers merely for
implementation convenience.

------------------------------------------------------------------------

# 20. Phase 2 Scope

## Required

1.  Forge local package
2.  Local Context Store
3.  Forge MCP server
4.  Agent credentials
5.  Forge Skill
6.  Claude Code integration
7.  Context retrieval
8.  Context recording
9.  Context superseding
10. Session lifecycle integration
11. Feature-scoped authorization
12. TOON agent-facing context
13. Evidence capture
14. Local/cloud synchronization
15. Idempotent writes
16. Audit trail
17. Tests
18. Documentation

## Explicitly out of scope

-   vector database
-   embeddings
-   full RAG pipeline
-   autonomous multi-agent orchestration
-   automatic conflict resolution
-   general-purpose remote code execution
-   Jira integration
-   replacing Git
-   replacing CI/CD
-   production observability platform
-   enterprise SSO redesign
-   arbitrary external tool execution

------------------------------------------------------------------------

# 21. Phase 2 Success Criteria

Phase 2 is successful when the following scenario works end-to-end.

### Session A

``` text
Developer
  ↓
Claude
  ↓
Forge context lookup
  ↓
No useful PAYMENT context
  ↓
Local discovery
  ↓
Implementation
  ↓
Evidence
  ↓
Context Generator
  ↓
Validator
  ↓
Forge Context Bank
```

### Session B

``` text
Developer
  ↓
Claude
  ↓
Forge context lookup
  ↓
Previous PAYMENT knowledge
  ↓
Agent uses it
  ↓
Agent continues work
```

The critical product test is:

> Can a second agent continue meaningful work on the same feature
> without the developer manually explaining what the previous agent
> discovered and decided?

If not, Phase 2 is not done.

------------------------------------------------------------------------

# 22. Recommended Evaluation

Measure a small set of practical outcomes:

  Metric                                  Baseline   With Forge
  ------------------------------------- ---------- ------------
  Time to understand feature               measure      measure
  Repeated discovery work                  measure      measure
  Repeated mistakes                        measure      measure
  Context supplied to agent                measure      measure
  Useful context retained                  measure      measure
  Successful cross-agent continuation      measure      measure

Do not optimize token count alone.

The primary value is **reduced repeated engineering discovery and better
continuity across sessions and agents**.

------------------------------------------------------------------------

# 23. Architectural Principle

Forge should not be positioned as another coding agent.

It is the shared engineering context and action hub used by agents.

``` text
Claude ──┐
Codex ───┤
Cursor ──┤
Humans ──┼──→ Forge ──→ Context + Actions
CI/CD ───┤
Git ─────┘
```

Forge should connect to the engineering workflow rather than replace it.

------------------------------------------------------------------------

# 24. Reference Principle

Existing agent-memory and engineering-context systems may be studied as
reference implementations.

They are **not Forge specifications**.

When an architectural problem appears:

1.  Check whether an existing system has solved something similar.
2.  Understand its mechanism.
3.  Understand its trade-offs.
4.  Determine whether the problem exists in Forge.
5.  Implement the smallest Forge-specific solution.
6.  Preserve Forge's Feature boundary, authorization, provenance, and
    agent-agnostic design.

> Use the ecosystem as a compass, not as a blueprint.

------------------------------------------------------------------------

# 25. Implementation Order

Recommended implementation sequence:

``` text
1. Agent credential model
        ↓
2. Forge MCP server
        ↓
3. context_get / context_search
        ↓
4. Forge Skill
        ↓
5. Claude Code integration
        ↓
6. context_record / supersede
        ↓
7. Local Context Store
        ↓
8. Package CLI
        ↓
9. Git/evidence collection
        ↓
10. Autonomous sync
        ↓
11. Audit + idempotency
        ↓
12. End-to-end cross-session test
```

Do not build the local cache and synchronization machinery before
proving the basic agent → Forge → context → agent loop.

------------------------------------------------------------------------

# 26. External Reference Notes

The current MCP ecosystem is relevant to this phase:

-   MCP defines a standard interface for applications to expose tools,
    resources, and prompts to AI applications.
    citeturn0search2turn0search11
-   The July 2026 MCP specification introduced a stateless protocol
    core, cacheable list results, stronger authorization, and updated
    SDKs. citeturn0search1
-   MCP authorization is based around OAuth/OIDC-compatible patterns,
    with additional support for machine-to-machine authorization.
    citeturn0search12turn0search14
-   MCP tools are intended to let models invoke application actions,
    making them appropriate for Forge's future action layer.
    citeturn0search8

These references inform the implementation but do not override Forge
requirements.

------------------------------------------------------------------------

# 27. Definition of Done

Phase 2 is complete when:

-   A developer can install Forge locally.
-   An agent can authenticate to Forge.
-   An agent can identify a Feature.
-   An agent can retrieve Feature context through MCP.
-   Context is delivered in the Forge-approved TOON representation.
-   An agent can record durable context.
-   Context passes the existing generator/validator lifecycle.
-   Multiple typed Context Entries can be produced from one session.
-   An agent can supersede a specific prior statement.
-   Local context can be synchronized with Cloud Context Bank.
-   Missing context can be discovered locally and contributed back to
    Forge.
-   Concurrent updates do not silently overwrite knowledge.
-   Agent actions are authorized and auditable.
-   Claude Code can complete the full workflow.
-   A second session can successfully use knowledge produced by the
    first session.
-   Existing Phase 1 tests remain green.
-   Phase 2 tests cover the complete agent integration path.

**Final Phase 2 outcome:**

``` text
                    ENGINEERING WORK

                         Agent
                           │
                           ▼
                     Forge MCP
                           │
                           ▼
                 ┌─────────────────┐
                 │      Forge      │
                 │                 │
                 │ Context         │
                 │ Validation      │
                 │ Authorization   │
                 │ Actions         │
                 └────────┬────────┘
                          │
                     Context Bank
                          │
                          ▼
                    Next Agent
```

Forge moves from **"a place where context is stored"** to **"the
infrastructure agents use to understand and continue engineering
work."**
