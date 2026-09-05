-- Phase 1: the Context Bank becomes the primary representation of feature context.
--
-- Changes:
--   * kind values move to the Phase 1 set. The old 'session_summary' rows become
--     'change', which is the closest Phase 1 meaning for "what this session did".
--   * status gains 'pending_review' and 'rejected' so invalid context can be
--     quarantined instead of silently becoming active (phase-1-requirements §8).
--   * supersedes_id links a new version to the one it replaces, so history is
--     recoverable rather than overwritten (§10).
--   * updated_at, plus indexes for the retrieval path (§11: org + feature + status).
--
-- sessions.context is kept as a non-authoritative snapshot of the generated
-- contract (§17). Nothing reads it as source of truth.

alter table context_entries add column if not exists updated_at timestamptz not null default now();
alter table context_entries add column if not exists supersedes_id uuid references context_entries(id) on delete set null;

-- Rewrite the kind constraint, migrating existing rows first.
alter table context_entries drop constraint if exists context_entries_kind_check;
update context_entries set kind = 'change' where kind = 'session_summary';
alter table context_entries add constraint context_entries_kind_check
  check (kind in ('decision', 'constraint', 'architecture', 'change', 'known_issue', 'open_question'));

-- Rewrite the status constraint to allow quarantine states.
alter table context_entries drop constraint if exists context_entries_status_check;
alter table context_entries add constraint context_entries_status_check
  check (status in ('active', 'superseded', 'pending_review', 'rejected'));

-- Retrieval path: organization + feature + status (§11).
create index if not exists context_entries_org_feature_status_idx
  on context_entries (clerk_org_id, feature_id, status);

-- Provenance lookups: "which context came from this session?" (§9).
create index if not exists context_entries_session_idx
  on context_entries (clerk_org_id, session_id);

-- Version chain lookups (§10).
create index if not exists context_entries_supersedes_idx
  on context_entries (supersedes_id);
