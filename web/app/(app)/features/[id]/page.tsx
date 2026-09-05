import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { notFound } from "next/navigation";
import { ArrowLeft, Archive, ArchiveRestore, EyeOff, Trash2 } from "lucide-react";

import { AccessBadge } from "@/components/badges";
import { ContextEntryList } from "@/components/context-entry-list";
import { ContextFilters } from "@/components/context-filters";
import { ConfirmButton } from "@/components/forms/confirm-button";
import { RecordContextDialog } from "@/components/forms/record-context-dialog";
import { FeatureLinks } from "@/components/forms/feature-links";
import { StartSessionDialog } from "@/components/forms/start-session-dialog";
import { SurfaceFrame } from "@/components/ui/surface";
import { EmptyState, PageHeader } from "@/components/page-header";
import { SessionTable } from "@/components/session-table";
import { TeamAvatars } from "@/components/team-avatars";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { deleteFeatureAction, updateFeatureAction } from "@/lib/actions";
import { get, getOrNull } from "@/lib/api";
import type { ContextEntry, ContextKind, FeatureDetail, Team, User } from "@/lib/types";

export default async function FeaturePage({ params, searchParams }: PageProps<"/features/[id]">) {
  const { id } = await params;
  const sp = await searchParams;
  const kindFilter = typeof sp.kind === "string" ? sp.kind : "";
  const statusFilter = typeof sp.status === "string" ? sp.status : "";
  const [{ data: feature, error }, { has }] = await Promise.all([getOrNull<FeatureDetail>(`/features/${id}`), auth()]);

  if (error?.status === 404) notFound();
  if (!feature) {
    return (
      <Card className="mx-auto max-w-lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <EyeOff className="size-4" />
            No access to this feature
          </CardTitle>
          <CardDescription>{error?.message}</CardDescription>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          The API enforces this server-side (403): you must be assigned to the feature or belong to a team that owns
          it. An organization admin can grant either.
        </CardContent>
      </Card>
    );
  }

  const isAdmin = has({ role: "org:admin" });
  const [teams, users] = isAdmin ? await Promise.all([get<Team[]>("/teams"), get<User[]>("/users")]) : [[], []];

  // The feature payload carries active context; other statuses are fetched on demand.
  const contextEntries = statusFilter
    ? await get<ContextEntry[]>(`/features/${id}/context?status=${encodeURIComponent(statusFilter)}`)
    : feature.context_entries;

  const kindCounts = contextEntries.reduce<Partial<Record<ContextKind, number>>>((acc, e) => {
    acc[e.kind] = (acc[e.kind] ?? 0) + 1;
    return acc;
  }, {});
  const visibleContext = kindFilter ? contextEntries.filter((e) => e.kind === kindFilter) : contextEntries;

  const archived = feature.status === "archived";

  return (
    <>
      <Link href="/features" className="text-muted-foreground mb-4 inline-flex items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-3.5" />
        Features
      </Link>
      <PageHeader
        eyebrow={feature.key}
        title={
          <span className="flex items-center gap-3">
            {feature.name}
            {archived && <Badge variant="outline">archived</Badge>}
            <AccessBadge reason={feature.access_reason} />
          </span>
        }
        description={feature.description}
        actions={
          <>
            {!archived && <StartSessionDialog featureId={feature.id} featureKey={feature.key} />}
            {isAdmin && (
              <>
                <ArchiveToggle featureId={feature.id} archived={archived} name={feature.name} description={feature.description} />
                <ConfirmButton
                  action={deleteFeatureAction.bind(null, feature.id)}
                  confirm={`Delete ${feature.key} and all of its sessions and context? This cannot be undone.`}
                  variant="destructive"
                  size="sm"
                >
                  <Trash2 data-icon="inline-start" />
                  Delete
                </ConfirmButton>
              </>
            )}
          </>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-3 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Owned by</span>
          {feature.teams.length === 0 && <span className="text-muted-foreground">no team</span>}
          {feature.teams.map((t) => (
            <Badge key={t.id} variant="secondary">
              {t.name}
            </Badge>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Assigned</span>
          <TeamAvatars users={feature.assignees} designation="assigned" />
        </div>
      </div>

      <Tabs defaultValue="sessions">
        <TabsList>
          <TabsTrigger value="sessions">Sessions ({feature.sessions.length})</TabsTrigger>
          <TabsTrigger value="context">Context Bank ({contextEntries.length})</TabsTrigger>
          <TabsTrigger value="people">Teams &amp; people</TabsTrigger>
        </TabsList>

        <TabsContent value="sessions" className="mt-4">
          {feature.hidden_session_count > 0 && (
            <p className="text-muted-foreground mb-3 flex items-center gap-1.5 text-xs">
              <EyeOff className="size-3.5" />
              {feature.hidden_session_count} session{feature.hidden_session_count === 1 ? "" : "s"} on this feature{" "}
              {feature.hidden_session_count === 1 ? "is" : "are"} hidden: their authors are not on a team you share.
            </p>
          )}
          {feature.sessions.length === 0 ? (
            <EmptyState title="No visible sessions" body="Start one, or wait for a teammate's session to appear here." />
          ) : (
            <SurfaceFrame>
              <SessionTable sessions={feature.sessions} />
            </SurfaceFrame>
          )}
        </TabsContent>

        <TabsContent value="context" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center justify-between gap-2">
                Feature context
                <RecordContextDialog featureId={feature.id} sessions={feature.sessions} />
              </CardTitle>
              <CardDescription>
                Owned by the feature, authored by people and agents. Each entry keeps provenance back to its session
                and is versioned rather than overwritten.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ContextFilters counts={kindCounts} />
              {visibleContext.length === 0 ? (
                <EmptyState
                  title={
                    feature.context_entries.length === 0
                      ? "The Context Bank is empty for this feature"
                      : "Nothing matches these filters"
                  }
                  body={
                    feature.context_entries.length === 0
                      ? "Completing a session writes typed entries here: one per decision, constraint, known issue and open question."
                      : "Clear the kind or status filter to see the rest."
                  }
                />
              ) : (
                <ContextEntryList entries={visibleContext} />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="people" className="mt-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Owning teams</CardTitle>
                <CardDescription>Members of these teams can access the feature and see each other&apos;s sessions.</CardDescription>
              </CardHeader>
              <CardContent>
                {isAdmin ? (
                  <FeatureLinks
                    kind="teams"
                    featureId={feature.id}
                    linked={feature.teams.map((t) => ({ id: t.id, label: t.name }))}
                    options={teams.map((t) => ({ id: t.id, label: t.name }))}
                    emptyLabel="No team owns this feature."
                  />
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {feature.teams.length === 0 && <span className="text-muted-foreground text-sm">No team owns this feature.</span>}
                    {feature.teams.map((t) => (
                      <Badge key={t.id} variant="secondary">
                        {t.name}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Directly assigned</CardTitle>
                <CardDescription>Assignment grants feature access; session visibility still follows shared teams.</CardDescription>
              </CardHeader>
              <CardContent>
                {isAdmin ? (
                  <FeatureLinks
                    kind="assignees"
                    featureId={feature.id}
                    linked={feature.assignees.map((u) => ({ id: u.id, label: u.display_name }))}
                    options={users.map((u) => ({ id: u.id, label: u.display_name }))}
                    emptyLabel="Nobody is directly assigned."
                  />
                ) : (
                  <ul className="grid gap-1 text-sm">
                    {feature.assignees.length === 0 && <li className="text-muted-foreground">Nobody is directly assigned.</li>}
                    {feature.assignees.map((u) => (
                      <li key={u.id}>{u.display_name}</li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </>
  );
}

function ArchiveToggle({
  featureId,
  archived,
  name,
  description,
}: {
  featureId: string;
  archived: boolean;
  name: string;
  description: string | null;
}) {
  const toggle = async () => {
    "use server";
    const fd = new FormData();
    fd.set("name", name);
    if (description) fd.set("description", description);
    fd.set("status", archived ? "active" : "archived");
    await updateFeatureAction(featureId, null, fd);
  };
  return (
    <ConfirmButton action={toggle} variant="outline" size="sm">
      {archived ? <ArchiveRestore data-icon="inline-start" /> : <Archive data-icon="inline-start" />}
      {archived ? "Restore" : "Archive"}
    </ConfirmButton>
  );
}
