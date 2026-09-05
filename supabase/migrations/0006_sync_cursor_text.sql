-- The sync cursor is not a timestamp.
--
-- A bare `created_at` is unsafe as a cursor: clocks are coarse (Windows ticks
-- at ~15ms), so several entries can share one timestamp and a strict `>`
-- comparison would silently skip every entry after the first. The cursor is
-- therefore a composite `"<created_at>|<entry_id>"`, which is strictly
-- increasing.
--
-- Declaring the column `timestamptz` made Postgres try to parse the entry id as
-- a time zone: `time zone "e46b6738-…" not recognized`.

alter table sync_state
  alter column cursor type text using cursor::text;

comment on column sync_state.cursor is
  'Composite sync cursor "<created_at>|<entry_id>" — strictly increasing, so no entry is skipped when timestamps collide.';
