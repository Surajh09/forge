import { Bot, KeyRound, Terminal, XCircle } from "lucide-react";

import { ConfirmButton } from "@/components/forms/confirm-button";
import { nativeSelectClass } from "@/components/forms/field";
import { EmptyState, PageHeader, SectionHeader } from "@/components/page-header";
import { ToonBlock } from "@/components/toon-block";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Surface } from "@/components/ui/surface";
import { revokeGrantAction } from "@/lib/actions";
import { get, getText } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { AGENT_SCOPE_LABELS, CONTEXT_KINDS, type AgentGrant, type AgentScope, type Feature } from "@/lib/types";

const READ_ACTIONS = [
  { id: "get_feature_context", label: "forge_context_get" },
  { id: "get_context_by_kind", label: "forge_context_get (by kind)" },
  { id: "search_context", label: "forge_context_search" },
] as const;

type ActionId = (typeof READ_ACTIONS)[number]["id"];

const MCP_URL = process.env.NEXT_PUBLIC_FORGE_MCP_URL ?? "http://localhost:8000/mcp";

/**
 * Agents hub: connected agent credentials (OAuth grants) with revocation, the
 * connect instructions, and a read-only console showing the TOON an agent
 * receives. Write actions are exercised through the normal UI.
 */
export default async function AgentPage({ searchParams }: PageProps<"/agent">) {
  const sp = await searchParams;
  const action = (typeof sp.action === "string" ? sp.action : "get_feature_context") as ActionId;
  const featureId = typeof sp.feature_id === "string" ? sp.feature_id : "";
  const kind = typeof sp.kind === "string" ? sp.kind : "decision";
  const q = typeof sp.q === "string" ? sp.q : "";

  const [features, grants] = await Promise.all([get<Feature[]>("/features"), get<AgentGrant[]>("/oauth/grants")]);
  const selected = featureId || features[0]?.id || "";
  const active = grants.filter((g) => g.status === "active");
  const revoked = grants.filter((g) => g.status !== "active");

  let result: { text: string; status: number } | null = null;
  let requestPath = "";
  if (features.length > 0) {
    if (action === "search_context" && q.trim().length >= 2) {
      requestPath = `/agent/context/search?q=${encodeURIComponent(q.trim())}`;
    } else if (action === "get_context_by_kind" && selected) {
      requestPath = `/agent/context/features/${selected}/kinds?kind=${kind}`;
    } else if (action === "get_feature_context" && selected) {
      requestPath = `/agent/context/features/${selected}`;
    }
    if (requestPath) result = await getText(requestPath);
  }

  return (
    <>
      <PageHeader
        eyebrow="Agents"
        title={
          <span className="flex items-center gap-2">
            <Bot className="size-5" />
            Connected agents
          </span>
        }
        description="Coding agents reach Forge over MCP with a scoped credential you approve once. An agent acts with your feature access, narrowed to the scopes and features you allowed — never with your Clerk session or any Forge backend secret."
      />

      <section className="mb-10">
        <SectionHeader
          title="Connect Claude Code"
          description="Forge is its own OAuth server for MCP. Registration, PKCE and token refresh are automatic; you only approve the consent screen."
        />
        <Surface tone="knowledge" padding="lg">
          <ol className="grid gap-2 text-sm">
            <li>
              <span className="text-muted-foreground mr-2 font-mono text-xs">1</span>
              In a repo with the Forge skill, run <code className="bg-muted rounded px-1 py-0.5 font-mono text-xs">claude mcp add --transport http forge {MCP_URL}</code>
              <span className="text-muted-foreground"> (or open this repo, which ships a project-scoped <code className="font-mono text-xs">.mcp.json</code>).</span>
            </li>
            <li>
              <span className="text-muted-foreground mr-2 font-mono text-xs">2</span>
              Inside Claude Code type <code className="bg-muted rounded px-1 py-0.5 font-mono text-xs">/mcp</code>, choose <span className="font-medium">forge</span>, and sign in. The browser lands on the Forge consent page.
            </li>
            <li>
              <span className="text-muted-foreground mr-2 font-mono text-xs">3</span>
              Approve the scopes and optionally restrict the credential to specific features. It appears below and can be revoked at any time.
            </li>
          </ol>
        </Surface>
      </section>

      <section className="mb-10">
        <SectionHeader
          title="Credentials"
          description={`${active.length} active${revoked.length ? `, ${revoked.length} revoked` : ""}. Revoking stops every token bound to the credential immediately.`}
        />
        {grants.length === 0 ? (
          <EmptyState
            icon={<KeyRound className="size-5" />}
            title="No agent has connected yet"
            body="Follow the steps above. The credential created when you approve access will be listed here."
          />
        ) : (
          <div className="grid gap-3">
            {grants.map((g) => (
              <Surface key={g.id} tone={g.status === "active" ? "default" : "muted"}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="grid gap-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{g.client_name ?? g.client_id}</span>
                      {g.status === "revoked" ? (
                        <Badge variant="outline" className="bg-state-rejected/12 text-state-rejected border-state-rejected/35">revoked</Badge>
                      ) : (
                        <Badge variant="outline" className="bg-state-active/12 text-state-active border-state-active/35">active</Badge>
                      )}
                      {g.creator && <span className="text-muted-foreground text-xs">acts as {g.creator.display_name}</span>}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {g.scopes.map((s) => (
                        <Badge key={s} variant="secondary" className="font-mono" title={AGENT_SCOPE_LABELS[s as AgentScope]}>
                          {s}
                        </Badge>
                      ))}
                    </div>
                    <div className="text-muted-foreground flex flex-wrap gap-x-3 text-xs">
                      <span>
                        {g.feature_ids === null
                          ? "all features the creator can access"
                          : g.features.length
                            ? `limited to ${g.features.map((f) => f.key).join(", ")}`
                            : "limited to no features"}
                      </span>
                      <span>· created {formatRelative(g.created_at)}</span>
                      <span>· last used {g.last_used_at ? formatRelative(g.last_used_at) : "never"}</span>
                      {g.expires_at && <span>· expires {formatRelative(g.expires_at)}</span>}
                    </div>
                  </div>
                  {g.status === "active" && (
                    <ConfirmButton
                      action={revokeGrantAction.bind(null, g.id)}
                      confirm={`Revoke ${g.client_name ?? "this credential"}? The agent will need to reconnect and be approved again.`}
                      variant="destructive"
                      size="sm"
                    >
                      <XCircle data-icon="inline-start" />
                      Revoke
                    </ConfirmButton>
                  )}
                </div>
              </Surface>
            ))}
          </div>
        )}
      </section>

      <section className="mb-10">
        <SectionHeader
          title="What an agent receives"
          description="Run a read action and see the exact TOON document, with provenance folded in beside each statement."
        />
        {features.length === 0 ? (
          <EmptyState title="No features you can access" body="Load the demo data from Admin, or ask an admin for access." />
        ) : (
          <div className="grid gap-4">
            <Card>
              <CardContent className="pt-4">
                <form className="grid gap-4">
                  <div className="flex flex-wrap gap-3">
                    {READ_ACTIONS.map((a) => (
                      <label key={a.id} className="flex items-center gap-2 text-sm">
                        <input type="radio" name="action" value={a.id} defaultChecked={action === a.id} className="accent-primary" />
                        <span className="font-mono text-xs">{a.label}</span>
                      </label>
                    ))}
                  </div>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="grid gap-1.5">
                      <label htmlFor="feature_id" className="text-sm font-medium">Feature</label>
                      <select id="feature_id" name="feature_id" defaultValue={selected} className={nativeSelectClass}>
                        {features.map((f) => (
                          <option key={f.id} value={f.id}>{f.key}</option>
                        ))}
                      </select>
                    </div>
                    <div className="grid gap-1.5">
                      <label htmlFor="kind" className="text-sm font-medium">Kind</label>
                      <select id="kind" name="kind" defaultValue={kind} className={nativeSelectClass}>
                        {CONTEXT_KINDS.map((k) => (
                          <option key={k} value={k}>{k.replace("_", " ")}</option>
                        ))}
                      </select>
                    </div>
                    <div className="grid gap-1.5">
                      <label htmlFor="q" className="text-sm font-medium">Search query</label>
                      <Input id="q" name="q" defaultValue={q} placeholder="rotation" />
                    </div>
                  </div>
                  <div>
                    <Button type="submit">
                      <Terminal data-icon="inline-start" />
                      Run
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            {result && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    <span className="font-mono text-sm">GET /api/v1{requestPath}</span>
                    <Badge variant={result.status === 200 ? "secondary" : "destructive"}>{result.status}</Badge>
                  </CardTitle>
                  <CardDescription>The same authorization rules apply: features you cannot access are never returned.</CardDescription>
                </CardHeader>
                <CardContent>
                  <ToonBlock text={result.text} />
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </section>

      <section>
        <SectionHeader title="MCP tools" description="Eight focused tools; scopes are enforced server-side on every call." />
        <Surface>
          <dl className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[14rem_1fr]">
            {[
              ["forge_feature_get", "context.read", "resolve a feature by key and confirm access"],
              ["forge_context_get", "context.read", "active context for a feature, as TOON"],
              ["forge_context_search", "context.read", "text search across accessible features"],
              ["forge_context_record", "context.write", "record one durable statement (idempotent)"],
              ["forge_context_supersede", "context.supersede", "replace a statement; old version kept"],
              ["forge_session_start", "session.write", "start a session on a feature"],
              ["forge_session_checkpoint", "session.write", "durable context mid-session (idempotent)"],
              ["forge_session_complete", "session.write", "final contract and close (idempotent)"],
            ].map(([name, scope, what]) => (
              <div key={name} className="contents">
                <dt className="font-mono text-xs">{name}</dt>
                <dd className="text-muted-foreground text-xs">
                  <span className="text-foreground font-mono">{scope}</span> · {what}
                </dd>
              </div>
            ))}
          </dl>
        </Surface>
      </section>
    </>
  );
}
