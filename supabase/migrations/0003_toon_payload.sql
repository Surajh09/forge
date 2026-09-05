-- TOON becomes the canonical serialized representation of context payloads.
--
-- Relational metadata (feature_id, session_id, author, kind, version, status,
-- timestamps) stays in normal columns and is still queryable and indexable.
-- Only the payload itself moves from jsonb to TOON text.
--
-- The jsonb column is dropped rather than kept in parallel: two representations
-- of the same payload would mean two sources of truth, and the point of this
-- change is that there is exactly one. Encoding TOON requires the Python codec
-- (app/toon_codec.py), so old rows cannot be backfilled in SQL — re-run
-- `pnpm db:reset` and reseed to regenerate demo content.

alter table context_entries add column if not exists payload_toon text not null default '';
alter table context_entries drop column if exists payload;

comment on column context_entries.payload_toon is
  'Canonical context payload, TOON-encoded. Read/written only via app/toon_codec.py.';

-- search_context scans titles and payload text; TOON is plain text so a trigram
-- index serves ILIKE well without pulling in a vector store (out of scope).
create extension if not exists pg_trgm;

create index if not exists context_entries_title_trgm_idx
  on context_entries using gin (title gin_trgm_ops);

create index if not exists context_entries_payload_toon_trgm_idx
  on context_entries using gin (payload_toon gin_trgm_ops);
