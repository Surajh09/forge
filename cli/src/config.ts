import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";

/**
 * Where things live on a developer machine.
 *
 *   ~/.forge/credentials.json   OAuth tokens (per Forge server)
 *   ~/.forge/client.json        this machine's stable sync client id
 *   <project>/.forge/           the Local Context Store — disposable, gitignored
 *
 * The store sits in the project because context is feature-scoped and features
 * belong to a repository's work, not to the user account.
 */

export const FORGE_HOME = join(homedir(), ".forge");
export const STORE_DIRNAME = ".forge";

export function defaultApiUrl(): string {
  return process.env.FORGE_API_URL ?? "http://localhost:8000";
}

/** Walk up from cwd looking for a project marker; fall back to cwd. */
export function projectRoot(from: string = process.cwd()): string {
  let dir = resolve(from);
  for (;;) {
    if (
      existsSync(join(dir, ".git")) ||
      existsSync(join(dir, ".mcp.json")) ||
      existsSync(join(dir, STORE_DIRNAME))
    ) {
      return dir;
    }
    const parent = dirname(dir);
    if (parent === dir) return resolve(from);
    dir = parent;
  }
}

export function storeDir(root: string = projectRoot()): string {
  return join(root, STORE_DIRNAME);
}

function readJson<T>(path: string): T | null {
  try {
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function writeJson(path: string, value: unknown, mode = 0o600): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, { mode });
}

export { readJson, writeJson };

/**
 * A stable id for this machine's local store, so the server can track what this
 * replica has already seen. Not a credential — it identifies a cache, not a user.
 */
export function clientId(): string {
  const path = join(FORGE_HOME, "client.json");
  const existing = readJson<{ client_id: string }>(path);
  if (existing?.client_id) return existing.client_id;
  const id = `local-${randomUUID()}`;
  writeJson(path, { client_id: id });
  return id;
}
