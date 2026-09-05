import { ShieldCheck } from "lucide-react";

import { approveAgentConsentAction, denyAgentConsentAction } from "@/lib/actions";
import { get, getOrNull } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, PageHeader } from "@/components/page-header";
import { AGENT_SCOPE_LABELS, type AgentScope, type Feature, type PendingAuthorization as PendingConsent } from "@/lib/types";

/** Clerk-protected approval screen reached from the MCP SDK's OAuth redirect. */
export default async function AgentAuthorizePage({ searchParams }: PageProps<"/agent/authorize">) {
  const sp = await searchParams;
  const txn = typeof sp.txn === "string" ? sp.txn : "";
  if (!txn) {
    return <EmptyState title="Missing authorization request" body="Return to your coding agent and start the connection again." />;
  }

  const pending = await getOrNull<PendingConsent>(`/oauth/consents/${encodeURIComponent(txn)}`);
  if (!pending.data) {
    return <EmptyState title="Authorization request unavailable" body={pending.error.message} />;
  }
  const features = await get<Feature[]>("/features");

  return (
    <>
      <PageHeader
        eyebrow="Agent connection"
        title="Approve Forge access"
        description="You are approving an agent credential, not sharing your Clerk session or any Forge backend credential."
      />

      <Card className="mx-auto max-w-2xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="size-5" />
            {pending.data.client_name}
          </CardTitle>
          <CardDescription>
            This client is requesting a Forge credential for your current organization. It expires on {new Date(pending.data.expires_at).toLocaleString()}.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <section className="grid gap-2">
            <h2 className="text-sm font-medium">Callback</h2>
            <p className="text-muted-foreground break-all font-mono text-xs">{pending.data.redirect_uri}</p>
          </section>

          <form action={approveAgentConsentAction.bind(null, pending.data.id)} className="grid gap-5">
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-sm font-medium">Permissions to grant</legend>
              <p className="text-muted-foreground mb-1 text-xs">
                Untick anything this agent should not have. The credential can only ever be narrower than your own access.
              </p>
              {pending.data.scopes.map((scope) => (
                <label key={scope} className="flex items-start gap-2 text-sm">
                  <input type="checkbox" name="scopes" value={scope} defaultChecked className="mt-1 accent-primary" />
                  <span>
                    <span className="font-mono text-xs">{scope}</span>
                    <span className="text-muted-foreground ml-2">
                      {AGENT_SCOPE_LABELS[scope as AgentScope] ?? "Unrecognized permission"}
                    </span>
                  </span>
                </label>
              ))}
            </fieldset>

            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" name="restrict_features" className="mt-0.5 accent-primary" />
              <span>
                Restrict this credential to selected features. Leave unchecked to allow only the features you can ordinarily access.
              </span>
            </label>
            {features.length > 0 && (
              <fieldset className="grid gap-2 rounded-lg border p-3">
                <legend className="px-1 text-sm font-medium">Allowed features when restricted</legend>
                {features.map((feature) => (
                  <label key={feature.id} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" name="feature_ids" value={feature.id} className="accent-primary" />
                    <span className="font-mono text-xs">{feature.key}</span>
                    <span className="text-muted-foreground">{feature.name}</span>
                  </label>
                ))}
              </fieldset>
            )}
            <div className="flex flex-wrap gap-2 pt-2">
              <Button type="submit">Approve access</Button>
              <Button type="submit" formAction={denyAgentConsentAction.bind(null, pending.data.id)} variant="outline">Deny</Button>
            </div>
          </form>
        </CardContent>
        <CardFooter className="text-muted-foreground text-xs">
          Forge grants an opaque, scoped agent token. It never gives this client your Clerk secret, Forge service-role key, or database credentials.
        </CardFooter>
      </Card>
    </>
  );
}
