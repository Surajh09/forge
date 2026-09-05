import { join } from "node:path";

import { FORGE_HOME, readJson, writeJson } from "./config.js";

/**
 * OAuth tokens for a Forge server, stored at ~/.forge/credentials.json with
 * owner-only permissions. Keyed by server URL so one machine can talk to a
 * local Forge and a hosted one without them colliding.
 *
 * Access tokens are short-lived by design (the server issues one-hour tokens),
 * so `accessToken()` refreshes transparently and persists the rotated refresh
 * token — the server rotates it on every use.
 */

export type StoredCredential = {
  client_id: string;
  access_token: string;
  refresh_token?: string;
  expires_at?: number; // epoch seconds
  scopes: string[];
};

type CredentialFile = Record<string, StoredCredential>;

const PATH = join(FORGE_HOME, "credentials.json");

function load(): CredentialFile {
  return readJson<CredentialFile>(PATH) ?? {};
}

export function save(apiUrl: string, cred: StoredCredential): void {
  const all = load();
  all[apiUrl] = cred;
  writeJson(PATH, all);
}

export function get(apiUrl: string): StoredCredential | null {
  return load()[apiUrl] ?? null;
}

export function forget(apiUrl: string): boolean {
  const all = load();
  if (!(apiUrl in all)) return false;
  delete all[apiUrl];
  writeJson(PATH, all);
  return true;
}

function expired(cred: StoredCredential): boolean {
  // Refresh a minute early rather than racing the expiry.
  return cred.expires_at !== undefined && cred.expires_at - 60 <= Math.floor(Date.now() / 1000);
}

/** A usable access token, refreshing if needed. Throws if not logged in. */
export async function accessToken(apiUrl: string): Promise<string> {
  const cred = get(apiUrl);
  if (!cred) {
    throw new Error(`Not logged in to ${apiUrl}. Run: forge login`);
  }
  if (!expired(cred)) return cred.access_token;
  if (!cred.refresh_token) {
    throw new Error(`Credential for ${apiUrl} has expired. Run: forge login`);
  }

  const res = await fetch(`${apiUrl.replace(/\/$/, "")}/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: cred.refresh_token,
      client_id: cred.client_id,
    }),
  });
  if (!res.ok) {
    throw new Error(
      `Could not refresh the Forge credential (${res.status}). It may have been revoked. Run: forge login`,
    );
  }
  const body = (await res.json()) as {
    access_token: string;
    refresh_token?: string;
    expires_in?: number;
    scope?: string;
  };
  const updated: StoredCredential = {
    client_id: cred.client_id,
    access_token: body.access_token,
    // The server rotates refresh tokens: the old one dies on use, so persist the new one.
    refresh_token: body.refresh_token ?? cred.refresh_token,
    expires_at: body.expires_in ? Math.floor(Date.now() / 1000) + body.expires_in : undefined,
    scopes: body.scope ? body.scope.split(" ") : cred.scopes,
  };
  save(apiUrl, updated);
  return updated.access_token;
}
