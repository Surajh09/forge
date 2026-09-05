import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowUpRight, Check, History, X } from "lucide-react";

import { AgentBadge, ContextStatusBadge, KindBadge, StatusBadge } from "@/components/badges";
import { ConfidenceBar } from "@/components/context-entry-list";
import { ConfirmButton } from "@/components/forms/confirm-button";
import { SupersedeContextDialog } from "@/components/forms/supersede-context-dialog";
import { PageHeader } from "@/components/page-header";
import { setContextStatusAction } from "@/lib/actions";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getOrNull, get } from "@/lib/api";
import { formatDate, formatRelative } from "@/lib/format";
import type { ContextEntry } from "@/lib/types";

/**
 * Provenance page: context entry → source session → author.
 * This path is the core of the product concept (phase-1-requirements §15).
 */
export default async function ContextEntryPage({ params }: PageProps<"/context/[id]">) {
  const { id } = await params;
  const { data: entry, error } = await getOrNull<ContextEntry>(`/context/${id}`);

  if (error?.status === 404) notFound();
  if (!entry) {
    return (
      <Card className="mx-auto max-w-lg">
        <CardHeader>
          <CardTitle>No access to this context</CardTitle>
          <CardDescription>{error?.message}</CardDescription>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          Context visibility follows access to its feature, enforced by the API.
        </CardContent>
      </Card>
    );
  }

  const history = await get<ContextEntry[]>(`/context/${id}/history`);
  const olderVersions = history.filter((h) => h.id !== entry.id);
  const payload = Object.entries(entry.payload).filter(([, v]) =>
    Array.isArray(v) ? v.length > 0 : v != null && v !== "",
  );

  return (
    <>
      {entry.feature && (
        <Link
          href={`/features/${entry.feature.id}`}
          className="text-muted-foreground mb-4 inline-flex items-center gap-1 text-sm hover:underline"
        >
          <ArrowLeft className="size-3.5" />
          {entry.feature.key}
        </Link>
      )}

      <PageHeader
        eyebrow={`Context entry · v${entry.version}`}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {entry.title}
            <KindBadge kind={entry.kind} />
            <ContextStatusBadge status={entry.status} />
          </span>
        }
        actions={
          <>
            {entry.status === "pending_review" && (
              <>
                <ConfirmButton
                  action={setContextStatusAction.bind(null, entry.id, "active", entry.feature_id)}
                  size="sm"
                >
                  <Check data-icon="inline-start" />
                  Approve
                </ConfirmButton>
                <ConfirmButton
                  action={setContextStatusAction.bind(null, entry.id, "rejected", entry.feature_id)}
                  confirm="Reject this context? It stays recorded but will not be served as active feature context."
                  variant="destructive"
                  size="sm"
                >
                  <X data-icon="inline-start" />
                  Reject
                </ConfirmButton>
              </>
            )}
            {entry.status === "active" && <SupersedeContextDialog entry={entry} />}
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="grid gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Statement</CardTitle>
              <CardDescription>Stored TOON-encoded; shown decoded.</CardDescription>
            </CardHeader>
            <CardContent>
              {payload.length === 0 ? (
                <p className="text-muted-foreground text-sm">No payload recorded.</p>
              ) : (
                <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
                  {payload.map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-muted-foreground capitalize">{k.replace(/_/g, " ")}</dt>
                      <dd>{Array.isArray(v) ? v.map(String).join(", ") : String(v)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </CardContent>
          </Card>

          {olderVersions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <History className="size-4" />
                  Earlier versions
                </CardTitle>
                <CardDescription>
                  Superseded statements are kept, never overwritten.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ol className="divide-border/60 divide-y">
                  {olderVersions.map((v) => (
                    <li key={v.id} className="flex items-center gap-3 py-2 text-sm">
                      <span className="text-muted-foreground font-mono text-xs">v{v.version}</span>
                      <Link href={`/context/${v.id}`} className="hover:underline">
                        {v.title}
                      </Link>
                      <ContextStatusBadge status={v.status} />
                      <span className="text-muted-foreground ml-auto text-xs">
                        {formatRelative(v.created_at)}
                      </span>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          )}
        </div>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Provenance</CardTitle>
            <CardDescription>Where this context came from.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm">
              <Row label="Author">{entry.author?.display_name ?? entry.author_user_id ?? "—"}</Row>
              <Row label="Confidence">
                <ConfidenceBar value={entry.confidence} />
              </Row>
              <Row label="Version">
                <span className="font-mono">v{entry.version}</span>
              </Row>
              <Row label="Created">{formatDate(entry.created_at)}</Row>
              <Row label="Feature">
                {entry.feature ? (
                  <Link href={`/features/${entry.feature.id}`} className="font-mono hover:underline">
                    {entry.feature.key}
                  </Link>
                ) : (
                  "—"
                )}
              </Row>
            </dl>

            {entry.session ? (
              <div className="border-border/60 mt-4 rounded-lg border p-3">
                <div className="text-muted-foreground mb-2 text-xs font-medium uppercase">Source session</div>
                <Link
                  href={`/sessions/${entry.session.id}`}
                  className="inline-flex items-center gap-1 font-medium hover:underline"
                >
                  {entry.session.goal ?? "Untitled session"}
                  <ArrowUpRight className="size-3.5" />
                </Link>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <StatusBadge status={entry.session.status} />
                  <AgentBadge agent={entry.session.agent} model={entry.session.model} />
                </div>
                <p className="text-muted-foreground mt-2 text-xs">
                  by {entry.session.author?.display_name ?? entry.session.user_id} ·{" "}
                  {formatRelative(entry.session.started_at)}
                </p>
              </div>
            ) : (
              <p className="text-muted-foreground mt-4 text-xs">
                Manually authored; no source session.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] items-center gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
