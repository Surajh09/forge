import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { storeDir } from "./config.js";
import type { ContextEntry, PushEntry } from "./api.js";

/**
 * The Local Context Store (phase-2 §10).
 *
 * A cache and an offline outbox — never an authority. The cloud Context Bank
 * is the source of truth, so this is deliberately plain JSON on disk: one file
 * per feature, trivially inspectable, and safe to delete. Deleting it can lose
 * nothing that has already been pushed.
 *
 *   .forge/features/<KEY>.json   pulled entries + the sync cursor
 *   .forge/outbox/<KEY>.json     statements captured locally, awaiting push
 */

export type FeatureCache = {
  feature_id: string;
  feature_key: string;
  cursor: string | null;
  pulled_at: string | null;
  entries: ContextEntry[];
};

export type Outbox = {
  feature_id: string;
  feature_key: string;
  entries: PushEntry[];
};

function featuresDir(root?: string): string {
  return join(storeDir(root), "features");
}

function outboxDir(root?: string): string {
  return join(storeDir(root), "outbox");
}

function readJsonFile<T>(path: string): T | null {
  try {
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function writeJsonFile(path: string, value: unknown): void {
  mkdirSync(join(path, ".."), { recursive: true });
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

export function readCache(key: string, root?: string): FeatureCache | null {
  return readJsonFile<FeatureCache>(join(featuresDir(root), `${key.toUpperCase()}.json`));
}

/**
 * Merge freshly pulled entries into the cache.
 *
 * Merge by id rather than append: the sync cursor pairs a timestamp with an
 * entry id so nothing is skipped, but a boundary entry can still legitimately
 * arrive twice, and a superseded entry arrives again with a new status.
 */
export function mergeCache(
  key: string,
  incoming: ContextEntry[],
  meta: { feature_id: string; feature_key: string; cursor: string | null },
  root?: string,
): FeatureCache {
  const existing = readCache(key, root);
  const byId = new Map<string, ContextEntry>();
  for (const e of existing?.entries ?? []) byId.set(e.id, e);
  for (const e of incoming) byId.set(e.id, e);

  const cache: FeatureCache = {
    feature_id: meta.feature_id,
    feature_key: meta.feature_key,
    cursor: meta.cursor ?? existing?.cursor ?? null,
    pulled_at: new Date().toISOString(),
    entries: [...byId.values()].sort((a, b) => a.created_at.localeCompare(b.created_at)),
  };
  writeJsonFile(join(featuresDir(root), `${meta.feature_key.toUpperCase()}.json`), cache);
  return cache;
}

export function cachedFeatures(root?: string): string[] {
  const dir = featuresDir(root);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.replace(/\.json$/, ""));
}

// --- outbox ------------------------------------------------------------------

export function readOutbox(key: string, root?: string): Outbox | null {
  return readJsonFile<Outbox>(join(outboxDir(root), `${key.toUpperCase()}.json`));
}

export function queue(
  key: string,
  featureId: string,
  entry: PushEntry,
  root?: string,
): Outbox {
  const existing = readOutbox(key, root) ?? { feature_id: featureId, feature_key: key.toUpperCase(), entries: [] };
  // request_id is the idempotency key; queueing the same one twice is a no-op.
  if (!existing.entries.some((e) => e.request_id === entry.request_id)) {
    existing.entries.push(entry);
  }
  writeJsonFile(join(outboxDir(root), `${key.toUpperCase()}.json`), existing);
  return existing;
}

/** Drop entries the server accepted, keeping any it rejected for inspection. */
export function clearQueued(key: string, acceptedRequestIds: string[], root?: string): Outbox | null {
  const existing = readOutbox(key, root);
  if (!existing) return null;
  const done = new Set(acceptedRequestIds);
  existing.entries = existing.entries.filter((e) => !done.has(e.request_id));
  const path = join(outboxDir(root), `${key.toUpperCase()}.json`);
  if (existing.entries.length === 0) {
    rmSync(path, { force: true });
    return null;
  }
  writeJsonFile(path, existing);
  return existing;
}

export function outboxFeatures(root?: string): string[] {
  const dir = outboxDir(root);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.replace(/\.json$/, ""));
}

/** Delete the whole store. Safe by construction: the cloud keeps everything. */
export function purge(root?: string): void {
  rmSync(storeDir(root), { recursive: true, force: true });
}
