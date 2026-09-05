import { randomUUID } from "node:crypto";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { ForgeApiError, ForgeClient, type ContextEntry } from "./api.js";
import { clientId, defaultApiUrl, projectRoot } from "./config.js";
import { collect } from "./evidence.js";
import * as store from "./store.js";
import { pullFeature, resolveFeature } from "./sync.js";

/**
 * The local Forge MCP server (phase-2 §2, §10).
 *
 * Agents talk to this over stdio instead of reaching the cloud directly, which
 * is what makes the Local Context Store worth having:
 *
 *   read   → serve from the local replica when it is fresh, else pull and cache
 *   write  → send to the cloud; if the machine is offline, queue in the outbox
 *            so the statement survives and syncs later
 *
 * The cloud stays authoritative. Nothing here decides authorization — every
 * call carries the user's grant-bound token and the server applies the same
 * rules it applies to any other client.
 */

const KINDS = ["decision", "constraint", "architecture", "change", "known_issue", "open_question"] as const;

/** How long a cached feature is served without re-checking the cloud. */
const FRESH_MS = 5 * 60 * 1000;

const EvidenceShape = z
  .object({
    repository: z.string().optional(),
    branch: z.string().optional(),
    commit: z.string().optional(),
    files: z.array(z.string()).optional(),
    symbols: z.array(z.string()).optional(),
    tests: z.array(z.string()).optional(),
    test_results: z.string().optional(),
    build_results: z.string().optional(),
    errors: z.array(z.string()).optional(),
    observations: z.array(z.string()).optional(),
  })
  .optional();

function offline(err: unknown): boolean {
  return err instanceof TypeError || (err instanceof Error && /fetch failed|ECONNREFUSED|ENOTFOUND/i.test(err.message));
}

function fail(err: unknown): { content: { type: "text"; text: string }[]; isError: true } {
  const message =
    err instanceof ForgeApiError ? `${err.code}: ${err.message}` : err instanceof Error ? err.message : String(err);
  return { content: [{ type: "text", text: message }], isError: true };
}

function text(value: string) {
  return { content: [{ type: "text" as const, text: value }] };
}

/** Render entries the way the cloud does, so agents see one shape either way. */
function render(entries: ContextEntry[], header: Record<string, unknown>): string {
  const lines: string[] = [];
  for (const [k, v] of Object.entries(header)) lines.push(`${k}: ${v}`);
  lines.push(`count: ${entries.length}`);
  lines.push(`entries[${entries.length}]:`);
  for (const e of entries) {
    lines.push(`  - id: ${e.id}`);
    lines.push(`    kind: ${e.kind}`);
    lines.push(`    title: ${JSON.stringify(e.title)}`);
    lines.push(`    version: ${e.version}`);
    lines.push(`    status: ${e.status}`);
    if (e.confidence !== null) lines.push(`    confidence: ${e.confidence}`);
    if (e.session_id) lines.push(`    session_id: ${e.session_id}`);
    if (e.author?.display_name ?? e.author_user_id) {
      lines.push(`    author: ${e.author?.display_name ?? e.author_user_id}`);
    }
    if (e.conflicts_with) lines.push(`    conflicts_with: ${e.conflicts_with}`);
    lines.push(`    created_at: ${JSON.stringify(e.created_at)}`);
    const payload = Object.entries(e.payload ?? {}).filter(([, v]) => v !== null && v !== "");
    if (payload.length) {
      lines.push(`    payload:`);
      for (const [k, v] of payload) {
        lines.push(`      ${k}: ${Array.isArray(v) ? `[${v.length}]: ${v.join(",")}` : JSON.stringify(String(v))}`);
      }
    }
  }
  return lines.join("\n");
}

function isFresh(pulledAt: string | null | undefined): boolean {
  if (!pulledAt) return false;
  return Date.now() - new Date(pulledAt).getTime() < FRESH_MS;
}

export async function serve(apiUrl = defaultApiUrl()): Promise<void> {
  const client = new ForgeClient(apiUrl);
  const root = projectRoot();
  const label = `${root.split(/[\\/]/).pop() ?? "workspace"}`;

  const server = new McpServer(
    { name: "forge-local", version: "0.1.0" },
    {
      instructions:
        "Forge is the shared engineering Context Bank, served through this machine's local replica. " +
        "Before independent investigation of a feature, call forge_context_get for it and use what is " +
        "relevant. Record durable statements — decisions, constraints, known issues, open questions — " +
        "never raw transcripts. Reads are served from the local cache when fresh; writes go to the cloud, " +
        "or queue locally when offline and sync later.",
    },
  );

  server.registerTool(
    "forge_context_get",
    {
      title: "Get feature context",
      description:
        "Active Forge context for a feature, addressed by key (e.g. PAYMENT). Served from the local " +
        "replica when fresh, otherwise pulled from the cloud and cached.",
      inputSchema: {
        feature: z.string().describe("Feature key such as PAYMENT, or a feature id"),
        kinds: z.array(z.enum(KINDS)).optional(),
        refresh: z.boolean().optional().describe("Force a pull even if the cache is fresh"),
      },
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
    },
    async ({ feature, kinds, refresh }) => {
      try {
        const key = feature.trim().toUpperCase();
        const cached = store.readCache(key, root);
        let entries = cached?.entries ?? [];
        let source = "local-cache";

        if (refresh || !isFresh(cached?.pulled_at)) {
          try {
            const pulled = await pullFeature(client, feature, { root, label });
            entries = pulled.entries;
            source = "cloud";
          } catch (err) {
            if (!offline(err) || !cached) throw err;
            source = "local-cache (offline)";
          }
        }

        const visible = entries.filter(
          (e) => e.status === "active" && (!kinds?.length || kinds.includes(e.kind as (typeof KINDS)[number])),
        );
        return text(render(visible, { feature: key, source }));
      } catch (err) {
        return fail(err);
      }
    },
  );

  server.registerTool(
    "forge_context_search",
    {
      title: "Search context",
      description:
        "Text search across the Context Bank. Uses the cloud when reachable, and falls back to searching " +
        "this machine's cached features when offline.",
      inputSchema: { query: z.string().min(2), limit: z.number().int().min(1).max(100).optional() },
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
    },
    async ({ query, limit }) => {
      try {
        const hits = await client.searchContext(query, limit ?? 25);
        return text(render(hits, { query, source: "cloud" }));
      } catch (err) {
        if (!offline(err)) return fail(err);
        const needle = query.toLowerCase();
        const local = store
          .cachedFeatures(root)
          .flatMap((k) => store.readCache(k, root)?.entries ?? [])
          .filter(
            (e) =>
              e.status === "active" &&
              (e.title.toLowerCase().includes(needle) || JSON.stringify(e.payload).toLowerCase().includes(needle)),
          )
          .slice(0, limit ?? 25);
        return text(render(local, { query, source: "local-cache (offline)" }));
      }
    },
  );

  server.registerTool(
    "forge_context_record",
    {
      title: "Record durable context",
      description:
        "Record one durable engineering statement. Evidence (branch, commit, changed files) is collected " +
        "from this repository automatically. If the machine is offline the statement is queued locally and " +
        "uploaded on the next sync — it is never lost. Do not record transcripts or temporary observations.",
      inputSchema: {
        feature: z.string(),
        kind: z.enum(KINDS),
        title: z.string().min(1).max(500),
        payload: z.record(z.unknown()),
        confidence: z.number().min(0).max(1).optional(),
        session_id: z.string().optional(),
        evidence: EvidenceShape,
        request_id: z.string().optional().describe("Idempotency key; a retry with the same id is a no-op"),
      },
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    },
    async ({ feature, kind, title, payload, confidence, session_id, evidence, request_id }) => {
      const requestId = request_id ?? randomUUID();
      const withEvidence = collect(root, (evidence ?? {}) as Record<string, never>);
      try {
        const resolved = await resolveFeature(client, feature, root);
        const result = await client.push(
          resolved.id,
          clientId(),
          [
            {
              kind,
              title,
              payload: payload as Record<string, unknown>,
              confidence: confidence ?? null,
              session_id: session_id ?? null,
              evidence: withEvidence,
              request_id: requestId,
            },
          ],
          label,
        );
        if (result.rejected.length) {
          return fail(new Error(result.rejected[0]?.reason ?? "Statement rejected"));
        }
        const stored = result.accepted[0];
        const flagged =
          stored?.status === "pending_review"
            ? `\nflagged: this resembles an existing statement (${stored.conflicts_with}) and is held for review rather than published.`
            : "";
        return text(`recorded: ${stored?.id}\nstatus: ${stored?.status}\nsource: cloud${flagged}`);
      } catch (err) {
        if (!offline(err)) return fail(err);
        // Offline: keep the knowledge rather than losing it.
        const key = feature.trim().toUpperCase();
        const cached = store.readCache(key, root);
        store.queue(
          key,
          cached?.feature_id ?? key,
          {
            kind,
            title,
            payload: payload as Record<string, unknown>,
            confidence: confidence ?? null,
            session_id: session_id ?? null,
            evidence: withEvidence,
            request_id: requestId,
          },
          root,
        );
        return text(
          `queued: ${requestId}\nsource: local-outbox (offline)\nThe statement is stored on this machine and will upload on the next 'forge sync'.`,
        );
      }
    },
  );

  await server.connect(new StdioServerTransport());

  // connect() resolves as soon as the transport is wired up. Block until the
  // agent signals us to stop; otherwise the CLI falls through, exits, and kills
  // the server before its first request.
  //
  // Deliberately NOT keyed on stdin closing: a request can still be in flight
  // when the pipe ends, and exiting there truncates the reply. The transport
  // ends on its own once stdin closes, and Node exits when the loop drains.
  await new Promise<void>((resolve) => {
    process.once("SIGINT", () => resolve());
    process.once("SIGTERM", () => resolve());
    process.stdin.once("end", () => setTimeout(resolve, 250).unref());
  });
}
