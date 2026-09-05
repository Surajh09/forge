import { ForgeApiError, type ContextEntry, type ForgeClient } from "./api.js";
import { clientId } from "./config.js";
import * as store from "./store.js";

/**
 * Reconciling the Local Context Store with the cloud (phase-2 §11).
 *
 * Ordering matters: push before pull. Draining the outbox first means the
 * following pull returns the server's canonical version of what we just sent —
 * including a `pending_review` status if the server flagged it as conflicting
 * with existing knowledge — so the local copy never disagrees with the bank
 * about work this machine produced.
 *
 * Everything is resilient to being run twice: pushes carry a `request_id`, and
 * pulls are cursor-based and merged by entry id.
 */

export type SyncOutcome = {
  feature: string;
  pushed: number;
  rejected: { title?: string; reason: string }[];
  flagged: number;
  pulled: number;
  total: number;
  offline: boolean;
};

export function isOffline(err: unknown): boolean {
  // A transport failure, not a refusal: worth retrying later, unlike a 4xx.
  return err instanceof TypeError || (err instanceof Error && /fetch failed|ECONNREFUSED|ENOTFOUND/i.test(err.message));
}

/**
 * Resolve a feature key to an id, falling back to the local replica.
 *
 * Resolution normally asks the cloud, which means it is the first thing to fail
 * when the network is gone — and it would fail *before* any offline handling
 * further down. The cache already knows the id of every feature it holds, so
 * offline work continues for features this machine has pulled.
 */
export async function resolveFeature(
  client: ForgeClient,
  ref: string,
  root?: string,
): Promise<{ id: string; key: string; offline: boolean }> {
  try {
    const f = await client.resolveFeature(ref);
    return { id: f.id, key: f.key, offline: false };
  } catch (err) {
    if (!isOffline(err)) throw err;
    const cached = store.readCache(ref.trim().toUpperCase(), root);
    if (!cached) {
      throw new Error(
        `Offline, and '${ref}' has never been pulled onto this machine. Connect and run: forge context pull ${ref.toUpperCase()}`,
      );
    }
    return { id: cached.feature_id, key: cached.feature_key, offline: true };
  }
}

export async function pullFeature(
  client: ForgeClient,
  ref: string,
  opts: { root?: string; label?: string; full?: boolean } = {},
): Promise<{ entries: ContextEntry[]; total: number; pulled: number }> {
  const feature = await resolveFeature(client, ref, opts.root);
  const cached = store.readCache(feature.key, opts.root);
  const since = opts.full ? null : (cached?.cursor ?? null);

  const result = await client.pull(feature.id, clientId(), since, opts.label);
  const merged = store.mergeCache(
    feature.key,
    result.entries,
    { feature_id: result.feature_id, feature_key: result.feature_key, cursor: result.cursor },
    opts.root,
  );
  return { entries: merged.entries, total: result.total, pulled: result.entries.length };
}

export async function syncFeature(
  client: ForgeClient,
  ref: string,
  opts: { root?: string; label?: string } = {},
): Promise<SyncOutcome> {
  const feature = await resolveFeature(client, ref, opts.root);
  const outcome: SyncOutcome = {
    feature: feature.key,
    pushed: 0,
    rejected: [],
    flagged: 0,
    pulled: 0,
    total: 0,
    offline: false,
  };

  // 1. Drain the outbox first, so the pull reflects what we just contributed.
  const outbox = store.readOutbox(feature.key, opts.root);
  if (outbox?.entries.length) {
    try {
      const pushed = await client.push(feature.id, clientId(), outbox.entries, opts.label);
      outcome.pushed = pushed.accepted.length;
      outcome.flagged = pushed.flagged_for_review;
      outcome.rejected = pushed.rejected.map((r) => ({ title: r.title, reason: r.reason }));
      // Clear accepted *and* rejected: a rejected statement will never be
      // accepted on retry, so leaving it would block the queue forever. It is
      // reported to the caller instead.
      const settled = [
        ...pushed.accepted.map((_, i) => outbox.entries[i]?.request_id).filter((v): v is string => Boolean(v)),
        ...pushed.rejected.map((r) => r.request_id).filter((v): v is string => Boolean(v)),
      ];
      store.clearQueued(feature.key, settled, opts.root);
    } catch (err) {
      if (!isOffline(err)) throw err;
      outcome.offline = true;
      return outcome; // Keep the queue intact; try again when the network returns.
    }
  }

  // 2. Pull whatever is new.
  try {
    const pulled = await pullFeature(client, feature.key, opts);
    outcome.pulled = pulled.pulled;
    outcome.total = pulled.total;
  } catch (err) {
    if (!isOffline(err)) throw err;
    outcome.offline = true;
  }
  return outcome;
}

export async function statusFeature(
  client: ForgeClient,
  ref: string,
  root?: string,
): Promise<{
  feature: string;
  local: number;
  cloud: number;
  behind: number;
  queued: number;
  lastPulled: string | null;
}> {
  const feature = await resolveFeature(client, ref, root);
  const cached = store.readCache(feature.key, root);
  const queued = store.readOutbox(feature.key, root)?.entries.length ?? 0;

  let cloud = cached?.entries.length ?? 0;
  let behind = 0;
  try {
    const remote = await client.status(feature.id, clientId());
    cloud = remote.cloud_total;
    behind = remote.behind;
  } catch (err) {
    if (!(err instanceof ForgeApiError) && !isOffline(err)) throw err;
    // Offline: report what the local replica knows rather than failing.
  }
  return {
    feature: feature.key,
    local: cached?.entries.length ?? 0,
    cloud,
    behind,
    queued,
    lastPulled: cached?.pulled_at ?? null,
  };
}
