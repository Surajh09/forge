import "server-only";

import { auth } from "@clerk/nextjs/server";

// Server-side client for the Forge control plane. The Clerk session token is
// forwarded as a bearer token; the API verifies it and derives user/org/role.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { getToken } = await auth();
  const token = await getToken();

  const res = await fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init.headers ?? {}),
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    cache: "no-store",
  });

  if (res.status === 204) return undefined as T;

  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const code = typeof detail === "object" && detail?.code ? detail.code : "ERROR";
    const message =
      typeof detail === "object" && detail?.message
        ? detail.message
        : typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string }) => d.msg).join("; ")
            : `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, code, message);
  }
  return body as T;
}

export const get = <T>(path: string) => api<T>(path);

/** Fetch a route that returns TOON (or any plain text) rather than JSON. */
export async function getText(path: string): Promise<{ text: string; status: number }> {
  const { getToken } = await auth();
  const token = await getToken();
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    headers: { ...(token ? { authorization: `Bearer ${token}` } : {}) },
    cache: "no-store",
  });
  return { text: await res.text(), status: res.status };
}
export const post = <T>(path: string, data?: unknown) =>
  api<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });
export const patch = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(data) });
export const del = (path: string) => api<void>(path, { method: "DELETE" });

/** Resolves to null instead of throwing for 403/404 so pages can render an access message. */
export async function getOrNull<T>(path: string): Promise<{ data: T; error: null } | { data: null; error: ApiError }> {
  try {
    return { data: await get<T>(path), error: null };
  } catch (e) {
    if (e instanceof ApiError && (e.status === 403 || e.status === 404)) return { data: null, error: e };
    throw e;
  }
}
