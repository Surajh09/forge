# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Forge: a Clerk-authenticated, organization-scoped app for engineering **features**, **sessions** and a
**Context Bank**. Specs: `phase-1-requirements.md` (current work, authoritative) and `requirement.md` (the
original POC scope) + `system-design.png`. Three parts: `web/` (Next.js 16), `api/` (FastAPI), `supabase/` (local
Postgres via Supabase CLI). Jira was removed from the requirements — don't reintroduce it. Phase 1 out-of-scope
list is real: no vector DB, embeddings, RAG, multi-agent orchestration, or Claude webhooks.

## Commands

```bash
pnpm install                # pnpm workspace: root (Supabase CLI) + web/
pnpm db:start | db:stop | db:reset | db:status   # Supabase (Docker); migrations in supabase/migrations
pnpm api                    # uv --directory api run uvicorn app.main:app --reload --port 8000
pnpm web                    # next dev in web/
pnpm api:test               # access-rule tests; single test: cd api && uv run pytest tests/test_access.py -k name
pnpm web:lint && pnpm --filter web exec tsc --noEmit && pnpm web:build
```

Node deps use **pnpm** (`pnpm-workspace.yaml`; `allowBuilds` whitelists the Supabase CLI postinstall and the
`unrs-resolver` native build — pnpm blocks dependency build scripts by default).
Python deps are managed with **uv** (`api/pyproject.toml`, `uv.lock`) — not pip. `uv` lives at `~/.local/bin/uv.exe`
on this machine and is not on PATH in Claude's shell.

Env: repo-root `.env` holds the Clerk keys (`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`); both apps
read it as a fallback (`api/app/config.py` env_file tuple, `web/next.config.ts` loader). `api/.env` adds the Supabase
URL + service-role key (from `pnpm exec supabase status -o env`); `web/.env.local` adds `API_URL`. Examples live next
to them. Schema changes go in a new `supabase/migrations/NNNN_*.sql`; apply with `pnpm db:reset` (destroys local data).

## Architecture

**Request path:** browser → Next.js server component → `web/lib/api.ts` (attaches the Clerk session JWT as a bearer
token) → FastAPI `/api/v1` → `app/auth.py` verifies the JWT with `clerk-backend-api` and builds a `Principal`
(user_id, org_id, role) from the token's org claims (v2 `o.id`/`o.rol`, v1 fallback) → routers → `app/services.py`
→ `app/repos/*` (supabase-py, every query filtered by `clerk_org_id`). Mutations from the UI are server actions in
`web/lib/actions.ts`, which call the same API and `revalidatePath`.

**Access rules live in one place:** `api/app/access.py` (pure functions, unit-tested in `api/tests/test_access.py`).
Feature access = admin | directly assigned | member of an owning team. Session visibility = own + authors on an
owning team the viewer shares. Context follows feature access. Admin-only writes use `require_admin`. When changing
rules, change `access.py` and its tests, not the routers.

**Identity:** Clerk owns users/orgs/roles. Forge stores per-org user snapshots (`users` PK = org + Clerk user id),
upserted on first authenticated request (`app/repos/identity.py`); no webhooks. Seeded demo users use
`user_demo_*` ids and never log in. Roles map via `CLERK_ROLE_MAP` in `access.py` (`member` → `developer`).

**Context Bank (Phase 1):** `context_entries` is the primary representation of feature context — feature-owned,
versioned, with `session_id`/`author_user_id` provenance. `sessions.context` is a non-authoritative snapshot only.

Pipeline, kept as separate responsibilities: `app/context_generator.py` (session → `ContextContract`, never writes)
→ `app/context_validation.py` (normalize + validate; pure functions) → `app/context_bank.py` (fan-out, versioning,
supersede) → `app/repos/context.py`. `POST /sessions/{id}/complete` runs it and is idempotent; omit `context` in the
body to use the generator. Completion **fans out** one contract into typed entries: one `change` for the objective,
plus one per decision / constraint / known issue / open question. Kinds are `decision, constraint, architecture,
change, known_issue, open_question`; statuses `active, superseded, pending_review, rejected`. Context below
confidence 0.4 is stored `pending_review`, never published as active. Revisions never overwrite: a new row gets
`version+1` and `supersedes_id`, and the old row becomes `superseded`.

**TOON:** payloads are stored TOON-encoded in `context_entries.payload_toon` (text), not JSON. Relational metadata
stays in normal columns. **`app/toon_codec.py` is the only module that imports `toon_format`** — everything else
passes dicts and Pydantic models; keep it that way. Agent-facing routes under `/api/v1/agent/context/*` return
`text/plain` TOON with provenance folded in; the regular API returns JSON. The five agent actions live in
`app/context_actions.py` and reuse `services.load_feature` for authorization rather than restating rules.

`app/routers/stubs/*` document the future pipeline (context sync, ingestion, webhooks, orchestration) and return 501.

**Phase 2 — agents over MCP:** Forge is its own OAuth 2.1 authorization server. The `mcp` SDK owns the protocol
routes (`/register`, `/authorize`, `/token`, `/revoke`, RFC 8414/9728 metadata); `app/oauth.py` is only the
provider behind it, and `app/routers/oauth.py` is the Clerk-authenticated consent bridge plus grant management.
The MCP app is mounted at `/mcp` from `app/mcp_server.py` (eight tools, `ToolAnnotations`, server `instructions`).
Note the SDK rename: `mcp.server.fastmcp` no longer exists — it is `mcp.server.mcpserver.MCPServer`.

An OAuth grant *is* the agent credential: an agent acts as the consenting user, capped at developer role, then
narrowed by scopes (`context.read`, `context.write`, `context.supersede`, `session.write`) and an optional
feature allow-list applied inside `feature_access()` **before** the admin bypass. Users hold all scopes
implicitly. **Agent tokens are accepted on the whole REST API, so every route must declare its scope** via
`scoped()` in `app/auth.py` — a route without one is a hole. Writes take an optional `request_id` and are
idempotent through `repos/idempotency.py`; every context action and session lifecycle call writes an
`audit_log` row via `app/audit.py`, including denials. `forge_session_checkpoint` writes durable context
mid-session and leaves it active; complete is the final checkpoint plus close.

Claude Code wiring lives at `.mcp.json` and `.claude/skills/forge/SKILL.md` (behaviour only — never the
security boundary).

**Conflicts (§17):** `app/conflicts.py` compares a new statement against active entries of the same feature
**and kind**. Above the similarity threshold the newcomer is stored `pending_review` with `conflicts_with`
set, so it lands in the review queue instead of silently duplicating. Nothing is auto-merged or overwritten.
Tune the rule in that one file; it is pure and unit-tested.

**Local package — `cli/` (`@suhe09/forge-cli`, TypeScript):** the developer-machine half. `forge login` runs the same
OAuth flow an agent does; `forge init` points `.mcp.json` at the local stdio server; `forge context
pull/sync/show/status/purge` drive the Local Context Store; `forge doctor` diagnoses. The store is plain JSON
under `.forge/` (gitignored, disposable — the cloud is authoritative): `features/<KEY>.json` is the replica,
`outbox/<KEY>.json` holds statements captured offline.

`cli/src/mcp.ts` is a **local stdio MCP server** that proxies the cloud: reads come from the replica when
fresh, writes go to the cloud and queue locally when offline. This is what makes the cache worth having — the
remote HTTP server at `/mcp` still serves agents without the package installed.

**The sync cursor is `"<created_at>|<entry_id>"`, not a timestamp.** Clocks are coarse enough that entries
share a `created_at`, and a bare `>` comparison would skip all but the first. `sync_state.cursor` is therefore
`text` (migration 0006 fixed it after Postgres tried to parse an entry id as a time zone).

**Demo data:** `POST /admin/seed` (`api/app/seed.py`) is idempotent per org and deliberately shapes team/feature
links so the access rules are visible (see README table). Keep that shape if you edit it.

## Frontend conventions

- Next.js 16: `proxy.ts` (not `middleware.ts`) runs `clerkMiddleware` and forces an active org; `params` is a
  Promise; use `PageProps<"/route">` / `LayoutProps` generated types (`pnpm --filter web exec next typegen`).
- shadcn/ui is the **base-nova** style on Base UI: triggers/buttons take `render={<Link … />}` instead of `asChild`.
  A `Button` that renders a non-`<button>` (i.e. any `render={<Link …>}`) must also set `nativeButton={false}`, or
  Base UI logs an accessibility warning on every render.
  Aceternity components are in `components/ui/` (`background-beams`, `bento-grid`, `animated-tooltip`); the feature
  grid is a local adaptation of `card-hover-effect`. Native `<select>` is used inside forms on purpose.
- Admin gating in the UI is `has({ role: "org:admin" })` from `auth()`; the API re-checks everything.
