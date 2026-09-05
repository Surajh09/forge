import { accessToken } from "./credentials.js";

/** Typed client for the Forge REST API. Mirrors api/app/schemas.py. */

export type ContextEntry = {
  id: string;
  feature_id: string;
  session_id: string | null;
  author_user_id: string | null;
  kind: string;
  version: number;
  title: string;
  payload: Record<string, unknown>;
  confidence: number | null;
  status: "active" | "superseded" | "pending_review" | "rejected";
  supersedes_id: string | null;
  conflicts_with: string | null;
  evidence: Record<string, unknown> | null;
  created_at: string;
  updated_at: string | null;
  author?: { display_name: string } | null;
  session?: { id: string; goal: string | null } | null;
  feature?: { id: string; key: string; name: string } | null;
};

export type Feature = { id: string; key: string; name: string; description: string | null; status: string };

export type PullResult = {
  feature_id: string;
  feature_key: string;
  cursor: string | null;
  total: number;
  entries: ContextEntry[];
};

export type SyncStatus = {
  feature_id: string;
  feature_key: string;
  cloud_total: number;
  client_cursor: string | null;
  behind: number;
  last_synced_at: string | null;
};

export type PushEntry = {
  kind: string;
  title: string;
  payload: Record<string, unknown>;
  confidence?: number | null;
  session_id?: string | null;
  evidence?: Record<string, unknown> | null;
  request_id: string;
};

export type PushResult = {
  accepted: ContextEntry[];
  rejected: { request_id?: string; title?: string; reason: string }[];
  flagged_for_review: number;
};

export class ForgeApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ForgeApiError";
  }
}

export class ForgeClient {
  constructor(private readonly apiUrl: string) {
    this.apiUrl = apiUrl.replace(/\/$/, "");
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = await accessToken(this.apiUrl);
    const res = await fetch(`${this.apiUrl}/api/v1${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${token}`,
        ...(init.headers ?? {}),
      },
    });
    if (res.status === 204) return undefined as T;
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const detail = (body as { detail?: unknown } | null)?.detail;
      const code =
        typeof detail === "object" && detail !== null && "code" in detail
          ? String((detail as { code: unknown }).code)
          : "ERROR";
      const message =
        typeof detail === "object" && detail !== null && "message" in detail
          ? String((detail as { message: unknown }).message)
          : `${res.status} ${res.statusText}`;
      throw new ForgeApiError(res.status, code, message);
    }
    return body as T;
  }

  features(): Promise<Feature[]> {
    return this.request<Feature[]>("/features");
  }

  async resolveFeature(ref: string): Promise<Feature> {
    const all = await this.features();
    const key = ref.trim().toUpperCase();
    const found = all.find((f) => f.key === key) ?? all.find((f) => f.id === ref.trim());
    if (!found) {
      throw new ForgeApiError(
        404,
        "FEATURE_NOT_FOUND",
        `No feature '${ref}' you can access. Available: ${all.map((f) => f.key).join(", ") || "none"}`,
      );
    }
    return found;
  }

  pull(featureId: string, clientId: string, since?: string | null, label?: string): Promise<PullResult> {
    const q = new URLSearchParams({ client_id: clientId });
    if (since) q.set("since", since);
    if (label) q.set("label", label);
    return this.request<PullResult>(`/sync/features/${featureId}?${q}`);
  }

  status(featureId: string, clientId: string): Promise<SyncStatus> {
    return this.request<SyncStatus>(`/sync/features/${featureId}/status?client_id=${encodeURIComponent(clientId)}`);
  }

  push(featureId: string, clientId: string, entries: PushEntry[], label?: string): Promise<PushResult> {
    return this.request<PushResult>(`/sync/features/${featureId}`, {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, label, entries }),
    });
  }

  featureContext(featureId: string): Promise<ContextEntry[]> {
    return this.request<ContextEntry[]>(`/features/${featureId}/context`);
  }

  searchContext(q: string, limit = 25): Promise<ContextEntry[]> {
    return this.request<ContextEntry[]>(`/context/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  }

  me(): Promise<{ principal: { user_id: string; org_id: string; role: string }; organization: { name: string } }> {
    return this.request("/me");
  }
}
