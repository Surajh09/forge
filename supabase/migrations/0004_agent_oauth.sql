-- Phase 2 slice 1: agent credentials as OAuth 2.1 grants, audit, idempotency.
--
-- Forge is its own OAuth authorization server for MCP (phase-2 §5.2). A grant is
-- the "agent credential" of §5.1: it binds an OAuth client (e.g. Claude Code,
-- dynamically registered) to the user who consented, their organization, the
-- scopes they approved, and an optional feature allow-list. Access tokens and
-- refresh tokens hang off the grant, so revoking the grant kills them all.
--
-- The agent never receives Clerk secrets, the service-role key, or a database
-- credential — only an opaque Forge token, stored here as a SHA-256 hash.

-- Dynamically registered OAuth clients (RFC 7591).
create table if not exists oauth_clients (
  client_id     text primary key,
  client_name   text,
  redirect_uris jsonb not null default '[]'::jsonb,
  client_info   jsonb not null,             -- full registration document, returned verbatim to the SDK
  created_at    timestamptz not null default now()
);

-- Pending authorization requests awaiting user consent (between /authorize and approval).
create table if not exists oauth_pending_authorizations (
  id           uuid primary key default gen_random_uuid(),
  client_id    text not null references oauth_clients(client_id) on delete cascade,
  params       jsonb not null,              -- state, scopes, code_challenge, redirect_uri, resource
  created_at   timestamptz not null default now(),
  expires_at   timestamptz not null,
  consumed_at  timestamptz
);

-- The agent credential (§5.1).
create table if not exists agent_grants (
  id            uuid primary key default gen_random_uuid(),
  clerk_org_id  text not null references organizations(clerk_org_id) on delete cascade,
  user_id       text not null,              -- creator; the agent acts with this user's access, narrowed below
  client_id     text not null references oauth_clients(client_id) on delete cascade,
  client_name   text,
  scopes        text[] not null,            -- context.read | context.write | context.supersede | session.write
  feature_ids   uuid[],                     -- null = no narrowing beyond the creator's own access
  status        text not null default 'active' check (status in ('active', 'revoked')),
  created_at    timestamptz not null default now(),
  expires_at    timestamptz,
  revoked_at    timestamptz,
  last_used_at  timestamptz,
  foreign key (clerk_org_id, user_id) references users(clerk_org_id, id) on delete cascade
);
create index if not exists agent_grants_org_user_idx on agent_grants (clerk_org_id, user_id);

create table if not exists oauth_authorization_codes (
  code_hash                       text primary key,
  client_id                       text not null references oauth_clients(client_id) on delete cascade,
  grant_id                        uuid not null references agent_grants(id) on delete cascade,
  redirect_uri                    text not null,
  redirect_uri_provided_explicitly boolean not null default true,
  code_challenge                  text not null,
  scopes                          text[] not null,
  resource                        text,
  expires_at                      timestamptz not null,
  used_at                         timestamptz
);

create table if not exists oauth_tokens (
  token_hash    text primary key,
  kind          text not null check (kind in ('access', 'refresh')),
  client_id     text not null references oauth_clients(client_id) on delete cascade,
  grant_id      uuid not null references agent_grants(id) on delete cascade,
  scopes        text[] not null,
  expires_at    timestamptz,
  revoked_at    timestamptz,
  created_at    timestamptz not null default now(),
  last_used_at  timestamptz
);
create index if not exists oauth_tokens_grant_idx on oauth_tokens (grant_id);

-- Audit trail for agent (and user) actions on the Context Bank (§15).
create table if not exists audit_log (
  id                    uuid primary key default gen_random_uuid(),
  clerk_org_id          text not null,
  principal_type        text not null check (principal_type in ('user', 'agent')),
  principal_id          text not null,      -- user id (for agents: the creator the grant acts as)
  credential_id         uuid,               -- agent_grants.id when principal_type = 'agent'
  feature_id            uuid,
  session_id            uuid,
  action                text not null,
  outcome               text not null,      -- ok | denied | rejected | failed | replayed
  authorization_result  text not null,      -- allow | deny:<reason>
  input_meta            jsonb not null default '{}'::jsonb,   -- identifiers and counts only, never payloads
  affected_entry_ids    uuid[] not null default '{}',
  created_at            timestamptz not null default now()
);
create index if not exists audit_log_org_created_idx on audit_log (clerk_org_id, created_at desc);
create index if not exists audit_log_credential_idx on audit_log (credential_id);

-- Idempotent writes (§16): the same request_id returns the first result instead of writing again.
create table if not exists idempotency_keys (
  clerk_org_id  text not null,
  request_id    text not null,
  operation     text not null,
  result        jsonb not null,             -- ids only; callers re-read the rows
  created_at    timestamptz not null default now(),
  primary key (clerk_org_id, request_id)
);

-- Evidence stays distinguishable from the durable statement itself (§9).
alter table context_entries add column if not exists evidence jsonb;

alter table oauth_clients                enable row level security;
alter table oauth_pending_authorizations enable row level security;
alter table agent_grants                 enable row level security;
alter table oauth_authorization_codes    enable row level security;
alter table oauth_tokens                 enable row level security;
alter table audit_log                    enable row level security;
alter table idempotency_keys             enable row level security;
