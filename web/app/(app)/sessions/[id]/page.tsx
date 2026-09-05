import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { notFound } from "next/navigation";
import { ArrowLeft, Trash2 } from "lucide-react";

import { AgentBadge, StatusBadge, VisibilityBadge } from "@/components/badges";
import { ContextEntryList, ContextView } from "@/components/context-entry-list";
import { CompleteSessionForm } from "@/components/forms/complete-session-form";
import { ConfirmButton } from "@/components/forms/confirm-button";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { deleteSessionAction } from "@/lib/actions";
import { get, getOrNull } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/format";
import type { ContextEntry, Session } from "@/lib/types";

export default async function SessionPage({ params }: PageProps<"/sessions/[id]">) {
  const { id } = await params;
  const [{ data: session, error }, { userId, has }] = await Promise.all([getOrNull<Session>(`/sessions/${id}`), auth()]);
  const produced = session ? await get<ContextEntry[]>(`/sessions/${id}/context`) : [];

  if (error?.status === 404) notFound();
  if (!session) {
    return (
      <Card className="mx-auto max-w-lg">
        <CardHeader>
          <CardTitle>Not visible to you</CardTitle>
          <CardDescription>{error?.message}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const canEdit = session.user_id === userId || has({ role: "org:admin" });
  const isActive = session.status === "active";

  return (
    <>
      <Link href={session.feature ? `/features/${session.feature.id}` : "/sessions"} className="text-muted-foreground mb-4 inline-flex items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-3.5" />
        {session.feature ? session.feature.key : "Sessions"}
      </Link>
      <PageHeader
        eyebrow={`Session · ${session.id.slice(0, 8)}`}
        title={session.goal ?? "Untitled session"}
        description={session.summary}
        actions={
          canEdit ? (
            <ConfirmButton
              action={deleteSessionAction.bind(null, session.id, session.feature_id)}
              confirm="Delete this session? Context Bank entries derived from it keep their provenance but lose the link."
              variant="destructive"
              size="sm"
            >
              <Trash2 data-icon="inline-start" />
              Delete
            </ConfirmButton>
          ) : null
        }
      />

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="grid gap-6">
          {produced.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Context this session produced</CardTitle>
                <CardDescription>
                  {produced.length} {produced.length === 1 ? "entry" : "entries"} in the Context Bank for{" "}
                  {session.feature?.key ?? "this feature"}. The feature owns them; this session is their provenance.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ContextEntryList entries={produced} />
              </CardContent>
            </Card>
          )}

          {session.context ? (
            <Card>
              <CardHeader>
                <CardTitle>Session contract</CardTitle>
                <CardDescription>
                  Version {session.context_version} — the validated contract this session yielded. A snapshot for
                  history; the Context Bank entries above are the source of truth.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ContextView context={session.context} />
              </CardContent>
            </Card>
          ) : isActive && canEdit ? (
            <Card>
              <CardHeader>
                <CardTitle>End session</CardTitle>
              </CardHeader>
              <CardContent>
                <CompleteSessionForm sessionId={session.id} defaultGoal={session.goal ?? ""} />
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>No context yet</CardTitle>
                <CardDescription>
                  {isActive ? "This session is still running." : "This session ended without producing context."}
                </CardDescription>
              </CardHeader>
            </Card>
          )}
        </div>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm">
              <Row label="Status">
                <StatusBadge status={session.status} />
              </Row>
              <Row label="Visible because">
                <VisibilityBadge reason={session.visibility_reason} />
              </Row>
              <Row label="Author">{session.author?.display_name ?? session.user_id}</Row>
              <Row label="Agent">
                <AgentBadge agent={session.agent} model={session.model} />
              </Row>
              <Row label="Feature">
                {session.feature ? (
                  <Link href={`/features/${session.feature.id}`} className="font-mono hover:underline">
                    {session.feature.key}
                  </Link>
                ) : (
                  "—"
                )}
              </Row>
              <Row label="Started">{formatDate(session.started_at)}</Row>
              <Row label="Ended">{formatDate(session.ended_at)}</Row>
              <Row label="Duration">{formatDuration(session.started_at, session.ended_at)}</Row>
              <Row label="Context version">
                <span className="font-mono">v{session.context_version}</span>
              </Row>
            </dl>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] items-center gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
