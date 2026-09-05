# Forge — Working Context

Living record of **what was decided, why, what is actually built, and what is still open**.
Written for a human picking this up cold. For terse agent-facing rules see `CLAUDE.md`;
for the product spec see `requirement.md`.

Last updated: 2026-09-05.

---

## 0. Phase 1: Context MVP (current work)

`phase-1-requirements.md` is now the authoritative spec. It turns Forge from an access-control POC into a
persistent engineering-context system: a completed session becomes structured, trustworthy feature context.

**What Phase 1 added**

| Piece | Where |
|---|---|
| Context Contract (objective, changes, decisions, affected components, constraints, dependencies, known issues, open questions, confidence) | `api/app/schemas.py` |
| Context Generator — session → contract, never writes | `api/app/context_generator.py` |
| Validator — normalize, structural checks, tenancy/referential checks | `api/app/context_validation.py` |
| Fan-out, versioning, supersede | `api/app/context_bank.py` |
| Five agent actions | `api/app/context_actions.py` |
| TOON serialization boundary | `api/app/toon_codec.py` |
| Structured ingestion logging | `api/app/observability.py` |

**Three decisions worth knowing**

1. **A completed session fans out into several typed entries**, not one blob. One `change` entry for the
   objective, plus one per decision, constraint, known issue and open question. This is what makes the `kind`
   vocabulary meaningful and lets a later session supersede a single statement instead of replacing everything.
   The spec's "produces a Context Entry" (singular) was ambiguous; granular was confirmed as the intent.
2. **The generator fills gaps rather than replacing authorship.** `POST /sessions/{id}/complete` accepts an
   optional contract. Supplied, it is used; omitted, the deterministic generator derives one from session
   metadata. Both paths go through the same validator. Since there is no transcript to read, generated context
   gets confidence 0.3 and is stored `pending_review` — it never publishes itself as trusted knowledge.
3. **TOON is the canonical payload format.** See §0.1.

### 0.05 Phase 2 slice 1: agents reach Forge over MCP

`phase-2-requirements.md` is now the authoritative spec. This slice is steps 1–6 of its §25 order: an agent
authenticates, retrieves feature context, contributes durable knowledge back, and a later session uses it.
Steps 7–10 — the TypeScript local package, local Context Store, CLI, Git evidence collection and autonomous
sync — are deliberately not built yet, because §25 says to prove the loop first.

**Forge is its own OAuth 2.1 authorization server.** Clerk's OAuth-server docs were unreachable when this was
designed, so whether it supports dynamic client registration and custom scopes could not be confirmed. Forge
therefore issues its own credentials and uses Clerk only to identify the human on the consent page. This turns
out to be the better fit anyway: the OAuth grant *is* the §5.1 agent credential — organization, creator,
principal type, scopes, feature allow-list, expiry, revocation, last use — with no parallel concept.

The `mcp` 2.1.1 SDK supplies the entire protocol surface (`/register`, `/authorize`, `/token`, `/revoke`, RFC
8414 + RFC 9728 metadata, PKCE verification, bearer middleware). `api/app/oauth.py` supplies only the provider
behind it. Note the SDK renamed things: `mcp.server.fastmcp` is gone, the class is
`mcp.server.mcpserver.MCPServer`.

**How an agent is authorized.** An agent acts as the user who consented, capped at the developer role, then
narrowed by the credential's scopes and optional feature allow-list. The allow-list is applied inside
`feature_access()` *before* the admin bypass, so a narrowed credential can never be widened by role. Scopes:
`context.read`, `context.write`, `context.supersede`, `session.write`. Users hold all of them implicitly.

**A gap this slice closed.** Agent tokens are accepted on the whole REST API, but scope checks originally lived
only inside `context_actions`. That meant a `context.read`-only grant could still create sessions and revise
context over REST, and `session.write` had no enforcement site at all. Every route now declares its scope via
the `scoped()` dependency in `api/app/auth.py`. **If you add a route, give it a scope** — the default is not
safe.

**Checkpoint.** §13.3 names `forge_session_checkpoint` but never defines it. It means: mid-session durable
context. Same generate → validate → fan-out pipeline as completion, but the session stays active so the agent
keeps working, e.g. before compaction. Completion is the final checkpoint plus closing the session. Both are
idempotent by `request_id`, which is why `idempotency_keys` is keyed on the request rather than a unique column
on `context_entries` — one checkpoint fans out to several rows.

**Where things live.** `oauth.py` (provider + consent), `mcp_server.py` (eight tools, `ToolAnnotations`,
server `instructions`), `context_actions.py` (the five actions, each auditing its own denials), `audit.py`,
`repos/{oauth,audit,idempotency}.py`, `routers/oauth.py` (consent + grants). The UI: `/agent` lists and revokes
credentials, `/agent/authorize` is the consent screen. `.mcp.json` and `.claude/skills/forge/SKILL.md` wire up
Claude Code.

**Evidence** (§9) is a jsonb column on `context_entries`, deliberately separate from the TOON payload so a
statement stays distinguishable from what backs it. Agents may pass it; automatic collection is step 9.

Two lessons from the test fakes, both of which hid real defects: the fake context repo silently dropped
`evidence` because it predated the column, and it generated ids like `feat_23` which read as feature *keys* to
code that accepts either. Fakes now generate UUIDs. **When a fake and the real repo disagree, the fake is
usually the thing that is wrong.**

---

## 0.06 Phase 2 slice 2: the local package, sync, and conflicts

Steps 7–11 of §25, completing Phase 2. Decisions: a **local stdio MCP that proxies the cloud** (so the replica
actually serves agents, per the §2 diagram), the store as **JSON under `.forge/`** (no native deps, genuinely
disposable), and conflicts **flagged on write with the newcomer quarantined**.

`cli/` is `@forge/cli`, TypeScript, dependency-light on purpose: it handles the user's credential, so every
dependency is supply-chain surface. Argument parsing is hand-rolled for that reason.

**Four bugs that only running it could find**, all worth remembering:

1. **The sync cursor was a timestamp.** Clocks are coarse — Windows ticks at ~15ms — so entries share a
   `created_at`, and a strict `>` comparison silently skips all but the first. The cursor is now
   `"<created_at>|<entry_id>"`, strictly increasing. It also had to be stored as `text`: declaring it
   `timestamptz` made Postgres parse the entry id as a time zone (`time zone "e46b6738-…" not recognized`).
2. **The stdio server exited before answering.** `connect()` resolves as soon as the transport is wired, so
   the CLI fell through to `process.exit(0)`. It now blocks on signals — deliberately *not* on stdin closing,
   which truncates in-flight replies.
3. **Offline resolution failed first.** `resolveFeature` asks the cloud, so it threw before any offline
   fallback further down could run. It now falls back to the replica, which already knows the feature id.
4. **Evidence was empty on a repo with no commits.** Every collector was `HEAD`-relative. It now falls back to
   `git branch --show-current` and `git status --porcelain`, neither of which needs a commit.

**Conflict detection** (`api/app/conflicts.py`) compares same-kind active entries using token overlap blended
with sequence similarity, taking the larger so paraphrasing does not slip past. Supporting prose (`reason`,
`rationale`, `impact`) is excluded from the comparison, so two different claims sharing a rationale are not
flagged. Light plural folding was needed: `keys`/`key` is a four-letter word, so a single length guard either
missed it or mangled short words.

Also fixed: `similarity` and the fakes. The conftest fake dropped `conflicts_with` exactly as it once dropped
`evidence` — the same lesson a third time. **When a fake and the real repo disagree, the fake is wrong.**

---

## 0.1 TOON

Context payloads are stored as TOON (Token-Oriented Object Notation) text in `context_entries.payload_toon`,
not as JSON. TOON is a compact encoding of the JSON data model designed for feeding structured data to language
models with fewer tokens. Relational metadata (feature, session, author, kind, version, status, timestamps) stays
in ordinary columns and is still indexed and queryable.

**The boundary is one file.** `api/app/toon_codec.py` is the only module that imports `toon_format`. Repos take
and return plain dicts; services and routers never see TOON text. A future format change touches that one file.
Keep it that way.

Three things to know before touching this:

- **The library is a pre-release.** `toon-format` 0.1.0 on PyPI is only a namespace reservation, so the pin is
  `0.9.0b1`, the sole released implementation, by TOON's own author. Revisit when a stable version ships.
- **The jsonb `payload` column was dropped**, not kept alongside, so there is exactly one representation. TOON
  can only be encoded by the Python codec, so old rows cannot be backfilled in SQL. Regenerate demo content with
  `pnpm db:reset` and reseed.
- **Search is plain text over TOON**, using trigram indexes on title and payload. That is deliberate: Phase 1
  forbids vector search until simple retrieval proves insufficient.

Agent-facing routes under `/api/v1/agent/context/*` return `text/plain` TOON with provenance folded in beside each
statement, so an agent can answer "where did this come from?" without a second call. The regular JSON API is
unchanged for the UI.

---

## 0.2 Design foundation

The UI was built utilitarian, one screen at a time, with colours hardcoded per component. A foundation pass
established tokens, a type scale, motion and shared surfaces in an **expressive** direction (gradients, glass,
motion), so pages inherit the look rather than each being restyled.

**Two foundations were silently broken and had never been noticed:**

1. **Dark mode never activated.** `globals.css` declared `@custom-variant dark (&:is(.dark *))` — class-based —
   but nothing anywhere added the `.dark` class, and `next-themes` is not installed. The entire `.dark` token
   block was dead, and **61 `dark:` utilities across 12 files were inert**. The app was permanently light. Fixed
   by switching the variant to `@custom-variant dark (@media (prefers-color-scheme: dark))` and moving the token
   block into that media query. This is now genuinely system-driven, with no toggle by choice.
2. **Geist was loaded but never applied.** `@theme inline` had `--font-sans: var(--font-sans)`, a circular
   self-reference, while `next/font` exposed the real variable as `--font-geist-sans`. The font downloaded on
   every page and never rendered. Fixed by pointing `--font-sans` at `--font-geist-sans`.

**What the foundation now provides** (`web/app/globals.css`):

- A brand hue (`--brand-h: 285`, the violet already in the landing beams) so the palette is no longer entirely
  achromatic. Previously `--card` and `--background` were both `oklch(1 0 0)` — identical, so cards had zero fill
  contrast and relied on a 1px 8%-grey border.
- **One token per meaning** for the Context Bank taxonomy: `--kind-*` and `--state-*`. `components/badges.tsx`
  collapsed from 17 hardcoded palette strings to one class per meaning, and the tokens flip with the scheme.
- Glass, elevation, gradient and easing tokens, plus a `glass-surface` and `gradient-text` utility.
- A type scale (`text-display`, `text-title`, `text-section`, `text-caption`) replacing ad-hoc per-page sizes.

**Shared components**: `components/ui/surface.tsx` (`Surface`/`SurfaceFrame`) is now the single card treatment,
replacing three that had drifted apart. Its `tone` prop carries a product idea worth keeping —
`tone="knowledge"` for durable context versus plain for session history — because *memory is not history* and the
two should not look alike. Also added `ui/stat-tile.tsx`, `motion-primitives.tsx` (reduced-motion aware) and
`nav-link.tsx` (the header had no current-route indicator at all).

**Not done in this pass**: per-page layout redesign, table density, and the raw `<select>` elements in search and
agent that bypass the styled `ui/select.tsx`.

---

## 1. Where we stand

**Status: the skeleton is built, wired end to end, and running locally. No demo data has been seeded yet.**

| Layer | State |
|---|---|
| Database (local Supabase) | 9 tables created, RLS on, migration applied |
| API (FastAPI) | 23 routes live, Clerk JWT verification working, 9 unit tests green |
| Web (Next.js 16) | 11 routes build and render, Clerk sign-in working |
| Demo data | **Not loaded.** Sign in, go to `/admin`, click "Load demo data" |
| Root README | Present — setup and run steps |

Running services during development:

| Service | Address | Started by |
|---|---|---|
| FastAPI | http://localhost:8000 (`/docs` for OpenAPI) | `pnpm api` |
| Next.js | http://localhost:3000 | `pnpm web` |
| Supabase API / DB / Studio | 54321 / 54322 / 54323 | `pnpm db:start` (needs Docker) |

---

## 2. Decisions and the reasoning behind them

Decisions the user made are marked **[user]**. The rest were judgment calls I made and flagged.

### 2.1 Stack

**Next.js 16 (App Router) + FastAPI, as two separate processes. [user]**

The alternative was a single Next.js app using Route Handlers as the backend. Two processes cost
more setup but map directly onto the system design, where the *API Gateway* and the control-plane
services are their own box. It also keeps the access rules in Python, where they can be unit-tested
without a browser or a running server.

**Node packages via pnpm; Python via uv. [user]**

Both replaced earlier npm/pip setups mid-build. See §4.3 for the migration trap.

**shadcn/ui (base-nova style, built on Base UI) + Aceternity components. [user]**

Worth knowing: this shadcn style is **not** Radix-based. Composition uses a `render` prop instead of
`asChild`, which is a real behavioural difference and the source of the bug in §4.4. Aceternity
components in use are `background-beams` (landing), `bento-grid` (dashboard) and `animated-tooltip`
(assignee avatars). `card-hover-effect` was not used as shipped; its hover-highlight technique was
adapted into `components/feature-grid.tsx` so feature cards could carry real data and badges.

### 2.2 Data and tenancy

**Local Supabase via the CLI, not a hosted project. [user]**

Started as hosted, switched to `supabase start` during the build. The schema lives in
`supabase/migrations/0001_init.sql` and is applied automatically on `pnpm db:start`.

**Access through supabase-py with the service-role key. Tenant isolation enforced in FastAPI, not in RLS policies. [user]**

This is the single most important thing to understand about the data layer, and the easiest to get
wrong later.

RLS is **enabled on every table with zero policies**. That is deliberate. It means the anon and
authenticated keys can read nothing at all, so the only path to data is the service-role key held by
the API. Isolation then depends entirely on every repo function filtering by `clerk_org_id`.

The consequence: **a repo function that forgets its `clerk_org_id` filter leaks across tenants, and
no database policy will stop it.** That is the tradeoff we accepted for speed. If this ever moves
toward production, the natural hardening step is real RLS policies driven by a Clerk-issued JWT, at
which point the service-role key stops being the only gate.

**Clerk owns identity; Forge stores per-org snapshots.**

Forge never becomes the identity provider. The `users` table is keyed on organization plus Clerk user
id, and rows are upserted lazily on a user's first authenticated request (`app/repos/identity.py`).
There are no Clerk webhooks in the POC, which is why `/admin/sync-members` exists as a manual pull.
Seeded demo users use `user_demo_*` ids and can never sign in, which is what lets one real account
demonstrate multi-user visibility rules.

### 2.3 Scope

**Jira was removed from the requirements entirely. [user]**

`requirement.md` was rewritten and renumbered. Originally Jira tasks were both a domain entity and an
input to the access rules. The user's reasoning was that Jira is "just another context bank", i.e. a
source of context rather than an authority on who may see what. Do not reintroduce it.

One loose end: `system-design.png` still shows a Jira box. The image cannot be edited here, so it
needs regenerating if the diagram is to match the spec.

**Non-POC services are stub routers returning 501, with full Pydantic contracts. [user]**

`app/routers/stubs/` covers context sync, ingestion, the webhook layer and orchestration. They appear
in `/docs` with documented request bodies and a `planned_flow` list. The point is that the
architecture is legible and has landing spots, without pretending the pipeline exists.

### 2.4 The access model

This is the heart of the POC and the thing most worth understanding.

All rules live as **pure functions** in `api/app/access.py`, unit-tested in `api/tests/test_access.py`
with no database. Routers gather inputs and call them. **When rules change, change `access.py` and its
tests, not the routers.**

```
Feature access     = admin  OR  directly assigned  OR  member of an owning team
Session visibility = own sessions  +  sessions by authors on an owning team you share
Context visibility = follows feature access
Writes             = features/teams/assignments: admin only
                     sessions: create if you can access the feature; edit/complete/delete: author or admin
```

Two subtleties that are easy to miss:

1. **Direct assignment grants feature access but not broad session visibility.** If you are assigned
   to LOGIN but not on the Platform team that owns it, you can open the feature and see its context,
   yet you will see only *your own* sessions. That asymmetry is intentional: the feature is the
   ownership boundary for context, while sessions stay closer to the team that produced them.
2. **Roles come from the Clerk token, not the database.** `o.rol` in a v2 token, with a v1
   `org_role` fallback. `CLERK_ROLE_MAP` maps `member` to `developer`, and anything unrecognised
   falls back to `developer` rather than failing closed to no access.

The seed data is shaped to make all of this visible rather than theoretical:

| Feature | Owning team | What the seeded caller sees |
|---|---|---|
| PAYMENT | Payments + QA | Own sessions plus Payments teammates'. QA-authored sessions stay hidden |
| LOGIN | Platform | Directly assigned, so full context but only own sessions |
| NOTIFICATION | DevOps | Nothing. Absent from the feature list entirely for a non-admin |

**Keep that shape if you edit `api/app/seed.py`**, otherwise the demo stops demonstrating anything.

---

## 3. How a request actually flows

```
browser
  → Next.js server component
  → web/lib/api.ts          attaches the Clerk session JWT as a bearer token
  → FastAPI /api/v1
  → app/auth.py             verifies the JWT, builds Principal(user_id, org_id, role)
  → routers                 thin; no rules here
  → app/services.py         gathers data, calls access.py, shapes the response
  → app/repos/*             supabase-py, every query filtered by clerk_org_id
```

Mutations from the UI are server actions in `web/lib/actions.ts` that call the same API and then
`revalidatePath`. The browser never talks to FastAPI directly and never holds the service-role key.

Two implementation details in `app/auth.py` worth knowing before you touch it:

- Verified tokens are cached in-process keyed on the raw token until `exp`, capped at five minutes.
  Clerk session tokens live about 60 seconds, so this mainly avoids a JWKS round trip per request.
- A request with a valid token but **no active organization** is rejected with 403 `ORG_REQUIRED`
  rather than being allowed through with a null tenant. The UI's `proxy.ts` prevents this by
  redirecting to `/select-org`, but the API does not rely on that.

---

## 4. Problems hit, and how they were diagnosed

This section is the real knowledge transfer. Each of these cost time and none are obvious.

### 4.1 Clerk Core 3 removed `<SignedIn>` and `<SignedOut>`

**Symptom:** every page returned HTTP 500 in dev.

**Why it was missed:** `tsc --noEmit` and `next build` both passed. The components are still exported
as types; they throw only when rendered. **A green build did not mean a working app**, and this was
only caught by actually requesting a page.

**Fix:** `components/app-header.tsx` is an async server component that already calls `auth()`, so it
now branches on `userId` directly. Clerk's own replacement is `<Show when="signed-in">`, which is the
right choice in a client component.

**Lesson:** smoke-test a real request after any auth-library upgrade. Type checks cannot see this
class of failure.

### 4.2 "Failed to load JWKS from Clerk Backend API"

**Symptom:** the dashboard failed with a JWKS error suggesting a Clerk outage or a bad key.

**Diagnosis:** the key was fine. Calling `https://api.clerk.com/v1/jwks` with the same secret returned
200 and a valid signing key. So the problem had to be the *process*, not the credential.

**Root cause:** the API had been started while `api/.env` still held a placeholder key. Uvicorn's
`--reload` watches `.py` files, **not `.env` files**, and `get_settings()` is `lru_cache`d. The real
key added later was never read.

**Fix:** restart the API. The proof was the error changing to "Unable to find a signing key in JWKS
that matches the kid", which is the correct response to a deliberately fake test token, meaning JWKS
now loads.

**Standing rule: after editing any `.env`, restart the API by hand.**

Also worth recording: a JWKS **URL** is not a thing this SDK accepts.
`AuthenticateRequestOptions` takes only `secret_key`, `machine_secret_key`, `jwt_key`, `audience`,
`authorized_parties`, `clock_skew_in_ms` and `accepts_token`. The endpoint is derived from the secret
key. If you want verification without a network call, the supported route is `jwt_key` with the PEM
public key.

### 4.3 pnpm 11 renamed the build-script allowlist

**Symptom:** `ERR_PNPM_IGNORED_BUILDS: unrs-resolver`, a non-zero exit that would fail CI.

**Root cause:** pnpm 11 replaced the `onlyBuiltDependencies` array with an `allowBuilds` map of
explicit true/false decisions. My first workspace file used the old name, so pnpm rewrote it into a
stub reading `set this to true or false`.

**Fix:** `allowBuilds: {supabase: true, unrs-resolver: true}` in `pnpm-workspace.yaml`.
`supabase` needs it to download the CLI binary; `unrs-resolver` is a native build used by
`eslint-config-next`.

**Verification trap:** `pnpm install` answers "Already up to date" and skips the build check entirely,
so it cannot confirm this fix. Only a clean install proves it. Deleting both `node_modules` trees and
reinstalling showed `unrs-resolver postinstall: Done` and exit 0.

Incidentally the ignored build was never actually breaking anything, because `unrs-resolver` ships a
prebuilt binding for this platform. The real cost was purely the non-zero exit code.

### 4.4 Base UI buttons that render as links

**Symptom:** an accessibility warning on every page, from `AppHeader` and elsewhere.

**Root cause:** in Base UI, a `Button` given `render={<Link …/>}` still claims native button
semantics unless told otherwise, which breaks forms and assistive technology.

**Fix:** every `Button` with `render={<Link …/>}` also sets `nativeButton={false}`. Nine call sites.
The rule is now recorded in `CLAUDE.md` so it survives.

### 4.5 Hydration mismatch on `<body>` that was not our bug

**Symptom:** React hydration mismatch on every page, pointing at `<body>` in `app/layout.tsx`.

**Root cause:** a browser extension. The diff showed a single offending attribute,
`cz-shortcut-listen="true"`, which **ColorZilla** injects into `<body>` before React hydrates.
Grammarly and password managers do the same thing with their own attributes.

**Fix:** `suppressHydrationWarning` on the `<body>` element. It applies to that element's own
attributes only, one level deep, so genuine mismatches inside the tree are still reported.

**Lesson:** read the `-`/`+` diff in a hydration error before touching code. If the only difference
is an unfamiliar vendor-prefixed attribute on `<html>` or `<body>`, it is an extension, and the
answer is a targeted suppression rather than a hunt through the render path.

### 4.6 Smaller traps

- **Next.js 16 renamed `middleware.ts` to `proxy.ts`.** The Clerk middleware lives in `web/proxy.ts`.
- **Next.js 16 blocks a second dev server for the same directory**, which silently invalidated one of
  my verification attempts. The running server logs to `web/.next/dev/logs/next-development.log`,
  which is the reliable place to check for render warnings.
- **`params` is a Promise** in Next 16. Use the generated `PageProps<"/route">` types.
- **Corepack could not install pnpm** on this machine (permission denied writing to
  `C:\Program Files\nodejs`). pnpm came from `npm i -g pnpm` instead.

---

## 5. What is verified, and what is not

Verified by actually running it:

| Check | Result |
|---|---|
| `pnpm api:test` | 9 passed (access rules) |
| `pnpm --filter web exec tsc --noEmit` | exit 0 |
| `pnpm web:lint` | exit 0 |
| `pnpm web:build` | 11 routes |
| Clean `pnpm install` from empty `node_modules` | exit 0, postinstall ran |
| API without a token | 401 `UNAUTHENTICATED` |
| API with a malformed token | 401, not 500 |
| API JWKS load | working (correct "no matching kid" for a fake token) |
| Web `/` and `/sign-in` | 200 |
| Web `/dashboard` unauthenticated | 307 to sign-in |
| Supabase schema | 9 tables, RLS enabled on all |

**Not yet verified, because it needs a signed-in session and seeded data:**

- The access rules end to end in the UI. The logic is unit-tested, but nobody has watched
  NOTIFICATION disappear for a non-admin, or seen the "via Payments team" visibility badges.
- `POST /sessions/{id}/complete` writing a Context Bank entry with provenance.
- Tenant isolation across two Clerk organizations.
- The admin flows: seeding, syncing Clerk members, attaching teams to features.

That gap is the single most valuable thing to close next.

---

## 6. Open items

1. **Seed and walk the demo.** `/admin` → "Load demo data", then verify the table in §2.4 by eye.
   This is the POC's entire point and it has not been demonstrated once.
2. **Regenerate `system-design.png`** without the Jira box.
3. **Confirm the non-admin experience.** Everything so far has been exercised as an org admin, who
   bypasses most of the interesting rules. Changing your own Clerk org role, or inviting a second
   account, is the only way to see the restrictive path.
4. **Consider real RLS policies** if this outlives the POC (see §2.2).

---

## 7. Environment notes specific to this machine

- `uv` is at `C:\Users\SURAJ\.local\bin\uv.exe` and is **not on PATH** in the agent shell, so it gets
  called by absolute path there. `pnpm api` and `pnpm api:test` work normally in a user terminal.
- Docker Desktop must be running before `pnpm db:start`. It was not, and had to be launched.
- The local Supabase keys in `api/.env` are the fixed, publicly known development keys. They are not
  secrets. The real Clerk keys live in the repo-root `.env`, which both apps read as a fallback.
- Two Supabase containers (`imgproxy`, `pooler`) report as stopped. Neither is used here.
