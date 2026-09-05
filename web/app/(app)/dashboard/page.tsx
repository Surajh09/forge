import Link from "next/link";
import { Activity, Building2, Layers, ShieldCheck } from "lucide-react";

import { RoleBadge, StatusBadge } from "@/components/badges";
import { SurfaceFrame } from "@/components/ui/surface";
import { EmptyState, PageHeader, SectionHeader } from "@/components/page-header";
import { SessionTable } from "@/components/session-table";
import { Badge } from "@/components/ui/badge";
import { BentoGrid, BentoGridItem } from "@/components/ui/bento-grid";
import { Button } from "@/components/ui/button";
import { get } from "@/lib/api";
import type { Feature, Me, Session } from "@/lib/types";

// BentoGridItem now uses Forge tokens directly, so no per-call-site patching.
const bentoClass = "";

export default async function DashboardPage() {
  const [me, features, sessions] = await Promise.all([
    get<Me>("/me"),
    get<Feature[]>("/features"),
    get<Session[]>("/sessions/mine"),
  ]);

  const isAdmin = me.principal.role === "admin";
  const active = sessions.filter((s) => s.status === "active");
  const withContext = sessions.filter((s) => s.context_version > 0);

  return (
    <>
      <PageHeader
        title={`Hello, ${me.user.display_name.split(" ")[0]}`}
        description={`${me.organization.name} · signed in through Clerk as ${me.principal.clerk_role || me.principal.role}.`}
      />

      <BentoGrid className="mx-0 max-w-none md:auto-rows-[12rem]">
        <BentoGridItem
          className={bentoClass}
          icon={<Building2 className="text-muted-foreground size-4" />}
          title="Your identity"
          description={
            <div className="grid gap-1.5">
              <div className="flex items-center gap-2">
                <RoleBadge role={me.principal.role} />
                <span className="text-muted-foreground font-mono text-[11px]">{me.principal.user_id}</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {me.teams.length === 0 && <span className="text-muted-foreground">Not on any team yet.</span>}
                {me.teams.map((t) => (
                  <Badge key={t.id} variant="secondary">
                    {t.name}
                  </Badge>
                ))}
              </div>
            </div>
          }
        />
        <BentoGridItem
          className={bentoClass}
          icon={<Layers className="text-muted-foreground size-4" />}
          title={
            <span className="flex items-baseline gap-2">
              <span className="text-3xl font-semibold">{features.length}</span> features you can access
            </span>
          }
          description={
            <div className="flex flex-wrap gap-1">
              {features.slice(0, 6).map((f) => (
                <Link key={f.id} href={`/features/${f.id}`}>
                  <Badge variant="outline" className="font-mono hover:bg-muted">
                    {f.key}
                  </Badge>
                </Link>
              ))}
              {features.length > 6 && <span className="text-muted-foreground">+{features.length - 6} more</span>}
            </div>
          }
        />
        <BentoGridItem
          className={bentoClass}
          icon={<Activity className="text-muted-foreground size-4" />}
          title={
            <span className="flex items-baseline gap-2">
              <span className="text-3xl font-semibold">{sessions.length}</span> sessions of yours
            </span>
          }
          description={
            <span>
              {active.length} active · {withContext.length} wrote context to the bank
            </span>
          }
        />
        <BentoGridItem
          className={`${bentoClass} md:col-span-3 md:auto-rows-auto md:row-span-1`}
          icon={<ShieldCheck className="text-muted-foreground size-4" />}
          title="How access works here"
          description={
            <div className="grid gap-1 sm:grid-cols-3">
              <span>
                <span className="text-foreground font-medium">Feature access</span> — you are assigned to it, or a team you
                belong to owns it. Admins see all.
              </span>
              <span>
                <span className="text-foreground font-medium">Session visibility</span> — your own, plus sessions by people on
                a feature-owning team you share.
              </span>
              <span>
                <span className="text-foreground font-medium">Context</span> — follows feature access. Every entry is versioned
                with provenance to its session.
              </span>
            </div>
          }
        />
      </BentoGrid>

      <section className="mt-10">
        <SectionHeader
          title="Recent sessions"
          description="What happened. Durable knowledge lives in each feature's Context Bank."
          actions={
            <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/sessions" />}>
              View all
            </Button>
          }
        />
        {sessions.length === 0 ? (
          <EmptyState
            title={features.length === 0 ? "Nothing here yet" : "No sessions yet"}
            body={
              features.length === 0
                ? isAdmin
                  ? "Load the demo data from the Admin page to see the access model in action."
                  : "You have no feature access yet. Ask an admin to assign you or add you to a team."
                : "Open a feature and start a session."
            }
            action={
              features.length === 0 && isAdmin ? (
                <Button nativeButton={false} render={<Link href="/admin" />}>Go to Admin</Button>
              ) : features.length > 0 ? (
                <Button variant="outline" nativeButton={false} render={<Link href="/features" />}>
                  Browse features
                </Button>
              ) : undefined
            }
          />
        ) : (
          <SurfaceFrame>
            <SessionTable sessions={sessions.slice(0, 8)} showFeature />
          </SurfaceFrame>
        )}
      </section>

      {active.length > 0 && (
        <p className="text-muted-foreground mt-4 text-xs">
          Active now:{" "}
          {active.map((s) => (
            <Link key={s.id} href={`/sessions/${s.id}`} className="mr-2 inline-flex items-center gap-1 hover:underline">
              <StatusBadge status="active" /> {s.goal ?? s.id.slice(0, 8)}
            </Link>
          ))}
        </p>
      )}
    </>
  );
}
