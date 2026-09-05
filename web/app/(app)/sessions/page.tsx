import Link from "next/link";

import { SurfaceFrame } from "@/components/ui/surface";
import { EmptyState, PageHeader } from "@/components/page-header";
import { SessionTable } from "@/components/session-table";
import { Button } from "@/components/ui/button";
import { get } from "@/lib/api";
import type { Session } from "@/lib/types";

export default async function SessionsPage() {
  const sessions = await get<Session[]>("/sessions/mine");

  return (
    <>
      <PageHeader
        title="Your sessions"
        description="Every unit of work you (or an agent acting for you) have done, across all features you can access."
      />
      {sessions.length === 0 ? (
        <EmptyState
          title="No sessions yet"
          body="Open a feature and start a session to record work against it."
          action={
            <Button variant="outline" nativeButton={false} render={<Link href="/features" />}>
              Browse features
            </Button>
          }
        />
      ) : (
        <SurfaceFrame>
          <SessionTable sessions={sessions} showFeature />
        </SurfaceFrame>
      )}
    </>
  );
}
