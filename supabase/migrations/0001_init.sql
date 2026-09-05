-- Forge POC schema (Supabase / Postgres)
--
-- Apply once: Supabase Dashboard → SQL Editor → paste → Run
-- (or `pnpm exec supabase db push` if you link the project with the CLI).
--
-- Tenant model: every table carries clerk_org_id. Users are stored per org
-- (PK = clerk_org_id + Clerk user id) so seeded demo users (user_demo_*) can
-- coexist with real Clerk users without a Clerk account.
--
-- Security: RLS is enabled on every table with NO policies. The anon and
-- authenticated keys therefore read nothing; only the service-role key used by
-- the FastAPI control plane can access data, and it scopes every query by org.

create table if not exists organizations (
  clerk_org_id text primary key,
  name         text not null,
  slug         text,
  created_at   timestamptz not null default now()
);

create table if not exists users (
  clerk_org_id text not null references organizations(clerk_org_id) on delete cascade,
  id           text not null,                        -- Clerk user id, or user_demo_* for seeded users
  email        text,
  display_name text not null,
  avatar_url   text,
  role         text not null default 'developer',    -- snapshot of Clerk org role: admin | developer | qa
  is_demo      boolean not null default false,
  created_at   timestamptz not null default now(),
  primary key (clerk_org_id, id)
);

create table if not exists teams (
  id           uuid primary key default gen_random_uuid(),
  clerk_org_id text not null references organizations(clerk_org_id) on delete cascade,
  name         text not null,
  description  text,
  created_at   timestamptz not null default now(),
  unique (clerk_org_id, name)
);
create index if not exists teams_org_idx on teams(clerk_org_id);

create table if not exists team_members (
  clerk_org_id text not null,
  team_id      uuid not null references teams(id) on delete cascade,
  user_id      text not null,
  created_at   timestamptz not null default now(),
  primary key (team_id, user_id),
  foreign key (clerk_org_id, user_id) references users(clerk_org_id, id) on delete cascade
);
create index if not exists team_members_org_user_idx on team_members(clerk_org_id, user_id);

create table if not exists features (
  id           uuid primary key default gen_random_uuid(),
  clerk_org_id text not null references organizations(clerk_org_id) on delete cascade,
  key          text not null,                        -- e.g. LOGIN, PAYMENT
  name         text not null,
  description  text,
  status       text not null default 'active' check (status in ('active', 'archived')),
  created_by   text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (clerk_org_id, key)
);
create index if not exists features_org_idx on features(clerk_org_id);

create table if not exists feature_teams (
  clerk_org_id text not null,
  feature_id   uuid not null references features(id) on delete cascade,
  team_id      uuid not null references teams(id) on delete cascade,
  primary key (feature_id, team_id)
);
create index if not exists feature_teams_org_idx on feature_teams(clerk_org_id);

create table if not exists feature_assignments (
  clerk_org_id text not null,
  feature_id   uuid not null references features(id) on delete cascade,
  user_id      text not null,
  primary key (feature_id, user_id),
  foreign key (clerk_org_id, user_id) references users(clerk_org_id, id) on delete cascade
);
create index if not exists feature_assignments_org_user_idx on feature_assignments(clerk_org_id, user_id);

create table if not exists sessions (
  id              uuid primary key default gen_random_uuid(),
  clerk_org_id    text not null references organizations(clerk_org_id) on delete cascade,
  feature_id      uuid not null references features(id) on delete cascade,
  user_id         text not null,
  agent           text not null default 'manual',    -- claude-code | cursor | manual | ...
  model           text,
  status          text not null default 'active' check (status in ('active', 'completed', 'failed', 'abandoned')),
  goal            text,
  summary         text,
  context         jsonb,                              -- SessionContext contract (see app/schemas.py)
  context_version integer not null default 0,
  started_at      timestamptz not null default now(),
  ended_at        timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  foreign key (clerk_org_id, user_id) references users(clerk_org_id, id) on delete cascade
);
create index if not exists sessions_org_feature_idx on sessions(clerk_org_id, feature_id);
create index if not exists sessions_org_user_idx on sessions(clerk_org_id, user_id);

-- Context Bank: feature-owned, versioned, with provenance back to a session/user.
create table if not exists context_entries (
  id             uuid primary key default gen_random_uuid(),
  clerk_org_id   text not null references organizations(clerk_org_id) on delete cascade,
  feature_id     uuid not null references features(id) on delete cascade,
  session_id     uuid references sessions(id) on delete set null,
  author_user_id text,
  kind           text not null check (kind in ('session_summary', 'decision', 'constraint', 'known_issue', 'open_question')),
  version        integer not null default 1,
  title          text not null,
  payload        jsonb not null default '{}'::jsonb,
  confidence     numeric(3, 2),
  status         text not null default 'active' check (status in ('active', 'superseded')),
  created_at     timestamptz not null default now()
);
create index if not exists context_entries_org_feature_idx on context_entries(clerk_org_id, feature_id);

alter table organizations      enable row level security;
alter table users              enable row level security;
alter table teams              enable row level security;
alter table team_members       enable row level security;
alter table features           enable row level security;
alter table feature_teams      enable row level security;
alter table feature_assignments enable row level security;
alter table sessions           enable row level security;
alter table context_entries    enable row level security;
