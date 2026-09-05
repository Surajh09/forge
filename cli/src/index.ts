#!/usr/bin/env node
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { ForgeApiError, ForgeClient } from "./api.js";
import { clientId, defaultApiUrl, projectRoot, storeDir } from "./config.js";
import { forget, get as getCredential } from "./credentials.js";
import { collect, isRepository } from "./evidence.js";
import { serve } from "./mcp.js";
import { login } from "./oauth.js";
import * as store from "./store.js";
import { pullFeature, statusFeature, syncFeature } from "./sync.js";

/**
 * The Forge CLI.
 *
 * Deliberately dependency-free argument parsing: this binary is launched by
 * agents over stdio, and every dependency is a supply-chain surface on a
 * developer's machine for a tool whose whole job is handling their credential.
 */

const HELP = `forge — local package for the Forge Context Bank

Usage
  forge login [--api <url>]        Authorize this machine (OAuth in your browser)
  forge logout [--api <url>]       Forget the stored credential
  forge init                       Write .mcp.json so agents use the local Forge server
  forge connect claude             Register the local Forge MCP server with Claude Code
  forge status [FEATURE]           Local vs cloud drift; omit FEATURE for all cached
  forge context pull <FEATURE>     Fetch a feature's context into the local store
  forge context sync [FEATURE]     Push queued statements, then pull; omit for all
  forge context show <FEATURE>     Print what the local store holds
  forge context purge              Delete the local store (the cloud keeps everything)
  forge evidence                   Show the evidence this repo would attach
  forge mcp                        Run the local MCP server on stdio (agents call this)
  forge doctor                     Check credential, server, and store health

Options
  --api <url>    Forge server (default $FORGE_API_URL or http://localhost:8000)
  --full         With pull/sync: ignore the cursor and refetch everything
  --json         Machine-readable output where supported
`;

type Args = { _: string[]; api: string; full: boolean; json: boolean };

function parse(argv: string[]): Args {
  const out: Args = { _: [], api: defaultApiUrl(), full: false, json: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]!;
    if (a === "--api") out.api = argv[++i] ?? out.api;
    else if (a === "--full") out.full = true;
    else if (a === "--json") out.json = true;
    else if (a === "-h" || a === "--help") out._.push("help");
    else out._.push(a);
  }
  return out;
}

const out = (s: string) => process.stdout.write(`${s}\n`);
const err = (s: string) => process.stderr.write(`${s}\n`);

function requireFeature(args: Args, position: number): string {
  const ref = args._[position];
  if (!ref) throw new Error("A feature key is required, e.g. PAYMENT");
  return ref;
}

async function cmdLogin(args: Args): Promise<void> {
  const cred = await login(args.api);
  const client = new ForgeClient(args.api);
  const me = await client.me();
  out(`Connected to ${args.api}`);
  out(`  organization: ${me.organization.name}`);
  out(`  acting as:    ${me.principal.user_id} (${me.principal.role})`);
  out(`  scopes:       ${cred.scopes.join(", ")}`);
  out(`\nNext: forge init   (point agents at the local Forge MCP server)`);
}

function cmdLogout(args: Args): void {
  out(forget(args.api) ? `Forgot the credential for ${args.api}.` : `No credential stored for ${args.api}.`);
}

function cmdInit(args: Args): void {
  const root = projectRoot();
  const path = join(root, ".mcp.json");
  const existing = existsSync(path) ? (JSON.parse(readFileSync(path, "utf8")) as Record<string, any>) : {};
  const servers = (existing.mcpServers ??= {});

  // Point at the local package so reads hit the replica and offline writes queue.
  servers.forge = {
    type: "stdio",
    command: "npx",
    args: ["-y", "@forge/cli", "mcp"],
    env: { FORGE_API_URL: args.api },
  };
  writeFileSync(path, `${JSON.stringify(existing, null, 2)}\n`);
  out(`Wrote ${path}`);
  out("Agents in this project will now reach Forge through the local store.");
  out("Restart your agent to pick it up.");
}

function cmdConnect(args: Args): void {
  const target = args._[1];
  if (target !== "claude") throw new Error("Only 'forge connect claude' is supported today.");
  out("Run this once, from the project root:\n");
  out(`  claude mcp add --scope project --transport stdio forge -- npx -y @forge/cli mcp`);
  out(`\nOr simply: forge init   (writes the same thing into .mcp.json)`);
}

async function cmdStatus(args: Args): Promise<void> {
  const client = new ForgeClient(args.api);
  const root = projectRoot();
  const refs = args._[1] ? [args._[1]] : store.cachedFeatures(root);
  if (refs.length === 0) {
    out("No features cached locally yet. Try: forge context pull PAYMENT");
    return;
  }
  const rows = [];
  for (const ref of refs) rows.push(await statusFeature(client, ref!, root));
  if (args.json) {
    out(JSON.stringify(rows, null, 2));
    return;
  }

  out("FEATURE               LOCAL  CLOUD  BEHIND  QUEUED  LAST PULLED");
  for (const r of rows) {
    out(
      `${r.feature.padEnd(20)}  ${String(r.local).padStart(5)}  ${String(r.cloud).padStart(5)}  ` +
        `${String(r.behind).padStart(6)}  ${String(r.queued).padStart(6)}  ${r.lastPulled ?? "never"}`,
    );
  }
  const behind = rows.reduce((n, r) => n + r.behind, 0);
  const queued = rows.reduce((n, r) => n + r.queued, 0);
  if (behind || queued) out(`\n${behind} entries to pull, ${queued} queued to push. Run: forge context sync`);
}

async function cmdPull(args: Args): Promise<void> {
  const client = new ForgeClient(args.api);
  const root = projectRoot();
  const result = await pullFeature(client, requireFeature(args, 2), { root, full: args.full });
  out(`Pulled ${result.pulled} new (${result.entries.length} cached locally, ${result.total} in the cloud).`);
  out(`Store: ${storeDir(root)}`);
}

async function cmdSync(args: Args): Promise<void> {
  const client = new ForgeClient(args.api);
  const root = projectRoot();
  const refs = args._[2]
    ? [args._[2]!]
    : [...new Set([...store.cachedFeatures(root), ...store.outboxFeatures(root)])];
  if (refs.length === 0) {
    out("Nothing to sync. Try: forge context pull PAYMENT");
    return;
  }
  for (const ref of refs) {
    const r = await syncFeature(client, ref, { root });
    if (r.offline) {
      err(`${r.feature}: offline — ${r.pushed} pushed, queue kept for later.`);
      continue;
    }
    const bits = [`pushed ${r.pushed}`, `pulled ${r.pulled}`, `${r.total} in cloud`];
    if (r.flagged) bits.push(`${r.flagged} flagged for review`);
    out(`${r.feature}: ${bits.join(", ")}`);
    for (const rej of r.rejected) err(`  rejected: ${rej.title ?? "(untitled)"} — ${rej.reason}`);
  }
}

function cmdShow(args: Args): void {
  const root = projectRoot();
  const key = requireFeature(args, 2).toUpperCase();
  const cache = store.readCache(key, root);
  if (!cache) {
    out(`Nothing cached for ${key}. Try: forge context pull ${key}`);
    return;
  }
  if (args.json) {
    out(JSON.stringify(cache, null, 2));
    return;
  }
  const active = cache.entries.filter((e) => e.status === "active");
  out(`${cache.feature_key} — ${active.length} active of ${cache.entries.length} cached`);
  out(`pulled ${cache.pulled_at ?? "never"}\n`);
  for (const e of active) {
    out(`  [${e.kind}] ${e.title}`);
    const detail = Object.entries(e.payload ?? {})
      .filter(([k]) => k !== "objective")
      .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join("|") : String(v)}`)
      .join("  ");
    if (detail) out(`      ${detail.slice(0, 160)}`);
    out(`      v${e.version}  ${e.confidence ?? "-"}  ${e.author?.display_name ?? e.author_user_id ?? "?"}`);
  }
  const queued = store.readOutbox(key, root)?.entries.length ?? 0;
  if (queued) out(`\n${queued} statement(s) queued locally, not yet uploaded.`);
}

function cmdPurge(): void {
  const root = projectRoot();
  const queued = store.outboxFeatures(root).reduce((n, k) => n + (store.readOutbox(k, root)?.entries.length ?? 0), 0);
  if (queued > 0) {
    throw new Error(
      `${queued} statement(s) are queued and not yet uploaded. Run 'forge context sync' first, or you will lose them.`,
    );
  }
  store.purge(root);
  out("Local store deleted. Nothing was lost — the cloud Context Bank is authoritative.");
}

function cmdEvidence(args: Args): void {
  const root = projectRoot();
  if (!isRepository(root)) {
    out("Not a git repository; evidence would be empty.");
    return;
  }
  const evidence = collect(root);
  out(args.json ? JSON.stringify(evidence, null, 2) : JSON.stringify(evidence, null, 2));
}

async function cmdDoctor(args: Args): Promise<void> {
  const root = projectRoot();
  const checks: [string, string][] = [];

  checks.push(["project root", root]);
  checks.push(["local store", existsSync(storeDir(root)) ? storeDir(root) : "not created yet"]);
  checks.push(["client id", clientId()]);
  checks.push(["api url", args.api]);

  const cred = getCredential(args.api);
  checks.push(["credential", cred ? `stored (scopes: ${cred.scopes.join(", ")})` : "MISSING — run: forge login"]);

  try {
    const res = await fetch(`${args.api.replace(/\/$/, "")}/health`);
    checks.push(["server", res.ok ? "reachable" : `unhealthy (${res.status})`]);
  } catch {
    checks.push(["server", "UNREACHABLE — is it running?"]);
  }

  if (cred) {
    try {
      const me = await new ForgeClient(args.api).me();
      checks.push(["authenticated as", `${me.principal.user_id} in ${me.organization.name}`]);
    } catch (e) {
      checks.push(["authenticated as", `FAILED — ${e instanceof Error ? e.message : String(e)}`]);
    }
  }

  const cached = store.cachedFeatures(root);
  checks.push(["cached features", cached.length ? cached.join(", ") : "none"]);
  const queued = store.outboxFeatures(root).reduce((n, k) => n + (store.readOutbox(k, root)?.entries.length ?? 0), 0);
  checks.push(["queued statements", queued ? `${queued} awaiting sync` : "none"]);
  checks.push([".mcp.json", existsSync(join(root, ".mcp.json")) ? "present" : "missing — run: forge init"]);

  for (const [k, v] of checks) out(`${k.padEnd(20)} ${v}`);
}

async function main(): Promise<number> {
  const args = parse(process.argv.slice(2));
  const [cmd, sub] = args._;

  try {
    switch (cmd) {
      case undefined:
      case "help":
        out(HELP);
        return 0;
      case "login":
        await cmdLogin(args);
        return 0;
      case "logout":
        cmdLogout(args);
        return 0;
      case "init":
        cmdInit(args);
        return 0;
      case "connect":
        cmdConnect(args);
        return 0;
      case "status":
        await cmdStatus(args);
        return 0;
      case "evidence":
        cmdEvidence(args);
        return 0;
      case "doctor":
        await cmdDoctor(args);
        return 0;
      case "mcp":
        await serve(args.api);
        return 0;
      case "context":
        if (sub === "pull") await cmdPull(args);
        else if (sub === "sync") await cmdSync(args);
        else if (sub === "show") cmdShow(args);
        else if (sub === "purge") cmdPurge();
        else throw new Error(`Unknown: forge context ${sub ?? ""}. See: forge help`);
        return 0;
      default:
        err(`Unknown command: ${cmd}\n`);
        out(HELP);
        return 1;
    }
  } catch (e) {
    if (e instanceof ForgeApiError) {
      err(`${e.code}: ${e.message}`);
      if (e.status === 401) err("The credential may have been revoked. Run: forge login");
      if (e.code === "SCOPE_REQUIRED") err("This credential was not granted that permission. Re-run: forge login");
    } else {
      err(e instanceof Error ? e.message : String(e));
    }
    return 1;
  }
}

main().then((code) => process.exit(code));
