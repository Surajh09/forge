import Link from "next/link";
import { Check, ShieldQuestion, X } from "lucide-react";

import { KindBadge } from "@/components/badges";
import { ConfidenceBar } from "@/components/context-entry-list";
import { ConfirmButton } from "@/components/forms/confirm-button";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { setContextStatusAction } from "@/lib/actions";
import { get } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import type { ContextEntry } from "@/lib/types";

/**
 * Quarantine review queue.
 *
 * Context that passed structural validation but fell below the confidence
 * threshold is stored `pending_review` instead of being published as trusted
 * knowledge. Without this page that context is written and then invisible.
 */
export default async function ReviewPage() {
  const pending = await get<ContextEntry[]>("/context/pending");

  return (
    <>
      <PageHeader
        eyebrow="Context Bank"
        title="Pending review"
        description="Context held back because it was not confident enough to publish. Approve it to make it active feature context, or reject it to retire it. Nothing here is visible to other readers yet."
      />

      {pending.length === 0 ? (
        <EmptyState
          title="Nothing waiting"
          body="Context generated from session metadata lands here for review. Complete a session with the generator to see the flow."
        />
      ) : (
        <div className="grid gap-4">
          {pending.map((e) => (
            <Card key={e.id}>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                  <KindBadge kind={e.kind} />
                  <Link href={`/context/${e.id}`} className="hover:underline">
                    {e.title}
                  </Link>
                  {e.feature && (
                    <Badge variant="secondary" className="font-mono">
                      {e.feature.key}
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>
                  {e.author?.display_name ?? e.author_user_id ?? "unknown author"} · {formatRelative(e.created_at)}
                  {e.session && (
                    <>
                      {" · from "}
                      <Link href={`/sessions/${e.session.id}`} className="hover:underline">
                        {e.session.goal ?? "session"}
                      </Link>
                    </>
                  )}
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4">
                {e.conflicts_with && (
                  <p className="border-state-pending/35 bg-state-pending/10 text-state-pending rounded-lg border px-3 py-2 text-sm">
                    Held back because it closely resembles{" "}
                    <Link href={`/context/${e.conflicts_with}`} className="font-medium underline">
                      an existing statement
                    </Link>
                    . Approve it only if both should stand; otherwise supersede the original instead.
                  </p>
                )}
                <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[8rem_1fr]">
                  {Object.entries(e.payload)
                    .filter(([, v]) => (Array.isArray(v) ? v.length > 0 : v != null && v !== ""))
                    .map(([k, v]) => (
                      <div key={k} className="contents">
                        <dt className="text-muted-foreground capitalize">{k.replace(/_/g, " ")}</dt>
                        <dd>{Array.isArray(v) ? v.map(String).join(", ") : String(v)}</dd>
                      </div>
                    ))}
                </dl>

                <div className="flex flex-wrap items-center gap-3">
                  <div className="mr-auto">
                    <span className="text-muted-foreground text-xs">Confidence</span>
                    <ConfidenceBar value={e.confidence} />
                  </div>
                  <ConfirmButton
                    action={setContextStatusAction.bind(null, e.id, "active", e.feature_id)}
                    size="sm"
                  >
                    <Check data-icon="inline-start" />
                    Approve
                  </ConfirmButton>
                  <ConfirmButton
                    action={setContextStatusAction.bind(null, e.id, "rejected", e.feature_id)}
                    confirm="Reject this context? It stays recorded but will not be served as active feature context."
                    variant="destructive"
                    size="sm"
                  >
                    <X data-icon="inline-start" />
                    Reject
                  </ConfirmButton>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <p className="text-muted-foreground mt-8 flex items-start gap-2 text-xs">
        <ShieldQuestion className="mt-0.5 size-3.5 shrink-0" />
        Model output is not trusted just because an agent produced it. Context generated without a transcript is
        deliberately low-confidence and lands here rather than entering the Context Bank as fact.
      </p>
    </>
  );
}
