# Forge

Centralized engineering context for developers and coding agents. Clerk-authenticated, organization-scoped
**features**, **sessions** and a **Context Bank**, with server-side access rules.

Specs: [`phase-1-requirements.md`](./phase-1-requirements.md) is the current, authoritative scope (Context MVP);
[`requirement.md`](./requirement.md) and [`system-design.png`](./system-design.png) describe the original POC.
[`CONTEXT.md`](./CONTEXT.md) is the working record of decisions and gotchas.

Phase 1 turns a completed coding session into structured, versioned feature context that a future developer or
coding agent can consume:

```
Session → Context Generator → Validator → Context Bank (typed entries, TOON-encoded)
```

```
web/        Next.js 16 · Clerk · shadcn/ui + Aceternity UI   → Forge UI
api/        FastAPI · clerk-backend-api · supabase-py         → Forge Cloud Control Plane
supabase/   local Supabase project (Postgres schema + RLS)   → Forge Database / Cloud Context Bank
```

## Prerequisites

- Node 22+, **pnpm** 11 (`packageManager` is pinned), Docker Desktop (running),
  [uv](https://docs.astral.sh/uv/) (`irm https://astral.sh/uv/install.ps1 | iex`)
- A Clerk application with **Organizations enabled** (Dashboard → Organizations → Settings). Optional custom org roles
  `org:developer` and `org:qa`; the default `org:admin` / `org:member` work out of the box.

## Run it

```bash
# 0. Clerk keys live once, in the repo-root .env (both apps read it as a fallback)
printf 'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...\nCLERK_SECRET_KEY=sk_test_...\n' > .env

# 1. Database (first run pulls images) — applies supabase/migrations automatically
pnpm install                # workspace: root (Supabase CLI) + web/
pnpm db:start               # supabase start
pnpm exec supabase status -o env   # copy SERVICE_ROLE_KEY

# 2. API
cp api/.env.example api/.env   # fill SUPABASE_SERVICE_ROLE_KEY (Clerk key comes from the root .env)
cd api && uv sync && cd ..
pnpm api                    # http://localhost:8000  (docs at /docs)

# 3. UI
cp web/.env.example web/.env.local   # API_URL + sign-in URLs; Clerk keys are optional here (override only)
pnpm web                    # http://localhost:3000
```

Then: sign up → create an organization → **Admin → Load demo data**. The demo puts you on the *Payments* team and
assigns you to *LOGIN*, so you can see the access rules work:

| Feature      | Owned by         | You (non-admin) see…                                 |
|--------------|------------------|------------------------------------------------------|
| PAYMENT      | Payments, QA     | your sessions + Payments teammates'; QA's are hidden |
| LOGIN        | Platform         | only your own sessions (assigned, not on Platform)   |
| NOTIFICATION | DevOps           | nothing — 403 from the API, absent from the list     |

As `org:admin` you see everything; change your role to `member` in the Clerk dashboard to try the restricted view.

## Tests

```bash
pnpm api:test               # 77 tests, no DB needed (repos are faked in tests/conftest.py)
pnpm web:lint && pnpm --filter web exec tsc --noEmit
pnpm web:build
```

Covers TOON round-trips, the Context Contract and validator, generator determinism, fan-out into typed entries,
session completion and idempotency, versioning/superseding, agent retrieval, and authorization including
cross-tenant and cross-feature attempts.

## How it maps to the design

| Diagram box                          | Implementation                                                     |
|--------------------------------------|--------------------------------------------------------------------|
| Forge UI                             | `web/` (server components call the API with the Clerk session JWT) |
| API Gateway                          | `api/app/main.py` (`/api/v1`)                                       |
| Auth & Access Layer                  | `api/app/auth.py` (Clerk JWT → principal), `api/app/access.py` (pure rules) |
| Feature / Session / Context Service  | `api/app/routers/*`, `api/app/services.py`                          |
| Forge Database, Cloud Context Bank   | `supabase/migrations/0001_init.sql` (`context_entries` is the bank) |
| Context Sync, Ingestion, Webhooks, Orchestration | `api/app/routers/stubs/*` — contracts in OpenAPI, respond 501 |
| Local Context Store, Local Agent Runtime | not in the POC                                                  |

**Access model.** Feature access = org admin, or directly assigned, or member of a team that owns the feature.
Session visibility inside a feature = own sessions + sessions by people on an owning team you share. Context follows
feature access. Every query is scoped by `clerk_org_id`; RLS is enabled with no policies so only the service-role key
used by the API can read anything.

## The Context Bank

**Contract.** `ContextContract` — objective, changes, decisions (each with a reason), affected components,
constraints, dependencies, known issues, open questions, confidence.

**Completion.** `POST /sessions/{id}/complete` runs generate → validate → fan out → mark the session completed.
Send a `context` object to use an authored contract, or omit it and the Context Generator derives one from session
metadata. The call is idempotent: completing twice returns the first result rather than duplicating context.

**Fan-out.** One contract becomes several typed entries, so a later session can supersede a single statement
instead of replacing everything:

| Contract field | Becomes |
|---|---|
| objective + changes + affected components | one `change` entry |
| each decision | a `decision` entry |
| each constraint | a `constraint` entry |
| each known issue | a `known_issue` entry |
| each open question | an `open_question` entry |

`architecture` is available for manually authored entries.

**Quality gate.** Structurally invalid context is rejected with 422 and nothing is written. Valid but
low-confidence context (below 0.4, which is what the metadata-only generator produces) is stored `pending_review`
rather than published as active. Model output is not trusted just because an agent produced it.

**Versioning.** Nothing is overwritten. A revision writes a new row with `version + 1` and `supersedes_id`
pointing at the old one, which becomes `superseded` and stays readable at `GET /context/{id}/history`.

**Provenance.** Every entry keeps its source session and author. The UI navigates
feature → context entry → source session → author.

## TOON

Context payloads are stored as [TOON](https://github.com/toon-format/toon) (Token-Oriented Object Notation) text in
`context_entries.payload_toon`, not JSON. It is a compact encoding of the JSON data model built for passing
structured data to language models with fewer tokens. Relational metadata stays in ordinary, queryable columns.

`api/app/toon_codec.py` is the only module that imports `toon_format`; everything else works with dicts and Pydantic
models. The dependency is pinned to `toon-format==0.9.0b1` because the stable 0.1.0 release on PyPI is only a
namespace reservation.

### Agent actions

Five actions, served as `text/plain` TOON with provenance folded in beside each statement. They reuse the same
authorization as the rest of the API, so a caller can never retrieve context for a feature they cannot access.

```
GET  /api/v1/agent/context/features/{id}              get_feature_context
GET  /api/v1/agent/context/features/{id}/kinds?kind=  get_context_by_kind
GET  /api/v1/agent/context/search?q=                  search_context
POST /api/v1/agent/context/features/{id}              record_context
POST /api/v1/agent/context/entries/{id}/supersede     supersede_context
```

## Connect a coding agent (MCP)

Forge speaks [MCP](https://modelcontextprotocol.io) over streamable HTTP at `/mcp` and is its own OAuth 2.1
authorization server, so any MCP-capable agent connects without an API key and without ever seeing a Clerk or
Supabase secret.

```bash
claude mcp add --transport http forge http://localhost:8000/mcp
# then, inside Claude Code:
/mcp     # choose "forge", sign in, approve the consent screen
```

This repo ships a project-scoped [`.mcp.json`](./.mcp.json), so opening it in Claude Code offers the server
automatically. Dynamic client registration, PKCE and token refresh are handled by the agent; you only approve
the consent page. [`.claude/skills/forge/SKILL.md`](./.claude/skills/forge/SKILL.md) tells the agent *when* to
use Forge — retrieve before investigating, contribute durable knowledge back, supersede rather than contradict.

**The credential.** Approving creates an agent credential (an OAuth grant). It acts as **you**, capped at the
developer role, and can only be narrower than your own access:

| Scope | Allows |
|---|---|
| `context.read` | read feature context, search the Context Bank |
| `context.write` | record new statements |
| `context.supersede` | replace statements with newer versions |
| `session.write` | start, checkpoint and complete sessions |

You may also restrict a credential to specific features. Manage and revoke credentials at `/agent`; revoking
kills every token bound to it immediately. An agent can never manage credentials, and never inherits admin.

### Tools

| Tool | Scope | Does |
|---|---|---|
| `forge_feature_get` | context.read | resolve a feature by key (`PAYMENT`) and confirm access |
| `forge_context_get` | context.read | active context for a feature, as TOON |
| `forge_context_search` | context.read | text search across accessible features |
| `forge_context_record` | context.write | record one durable statement |
| `forge_context_supersede` | context.supersede | replace a statement; the old version is kept |
| `forge_session_start` | session.write | start a session on a feature |
| `forge_session_checkpoint` | session.write | durable context mid-session, session stays open |
| `forge_session_complete` | session.write | final contract and close |

Writes accept a `request_id` and are idempotent — retries return the first result rather than duplicating.
Every action, including denials, is recorded in the audit log with principal, credential, feature, session and
outcome.

## Install the local package

The CLI gives a developer machine a Local Context Store, evidence collection, and a local MCP server that
serves agents from the replica instead of the network.

```bash
pnpm --filter @suhe09/forge-cli build
node cli/dist/index.js login      # OAuth in your browser, same flow an agent uses
node cli/dist/index.js init       # point .mcp.json at the local server
node cli/dist/index.js doctor     # credential, server and store health
```

Then work with context:

```bash
forge context pull PAYMENT        # fetch into the local store
forge status                      # local vs cloud drift, and anything queued
forge context sync                # push what was captured offline, then pull
forge context show PAYMENT        # what this machine holds
forge context purge               # delete the store; the cloud keeps everything
```

**The store is disposable.** It lives in `.forge/` as plain JSON, is gitignored, and holds only a replica plus
an outbox. `purge` refuses to run while statements are still queued, so nothing unsynced is lost.

**Offline works.** Reads fall back to the replica; writes queue in the outbox and upload on the next sync.
Evidence — branch, commit, changed files — is collected from the repository automatically, because Forge Cloud
cannot see your machine.

## Conflicts

Forge never silently overwrites knowledge, and never auto-merges. When a new statement closely resembles an
active one of the same kind, it is stored `pending_review` with a link to what it resembles and surfaced in
the review queue at `/review`, where you approve it or supersede the original. Similarity is title plus the
claim itself; supporting prose like a decision's `reason` is excluded so two different claims that share a
rationale are not mistaken for duplicates.

## Out of scope (by design)

Real Claude/agent integration, local↔cloud context sync, vector search / embeddings / RAG, automatic conflict
resolution, advanced quality scoring, multi-agent orchestration, Jira, repository integration, Clerk webhooks
(users are upserted on first authenticated request), production infrastructure.
