import Link from "next/link";
import { auth } from "@clerk/nextjs/server";

import { FeatureGrid } from "@/components/feature-grid";
import { CreateFeatureDialog } from "@/components/forms/create-feature-dialog";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { get } from "@/lib/api";
import type { Feature, Team, User } from "@/lib/types";

export default async function FeaturesPage() {
  const { has } = await auth();
  const isAdmin = has({ role: "org:admin" });

  const [features, teams, users] = await Promise.all([
    get<Feature[]>("/features"),
    isAdmin ? get<Team[]>("/teams") : Promise.resolve([]),
    isAdmin ? get<User[]>("/users") : Promise.resolve([]),
  ]);

  return (
    <>
      <PageHeader
        title="Features"
        description={
          isAdmin
            ? "As an admin you see every feature in the organization."
            : "Features you are assigned to, or that one of your teams owns. Everything else is hidden by the server."
        }
        actions={isAdmin ? <CreateFeatureDialog teams={teams} users={users} /> : undefined}
      />
      {features.length === 0 ? (
        <EmptyState
          title="No features visible"
          body={
            isAdmin
              ? "Create a feature, or load the demo data from the Admin page."
              : "You are not assigned to any feature and none of your teams own one. Ask an admin."
          }
          action={
            isAdmin ? (
              <Button variant="outline" nativeButton={false} render={<Link href="/admin" />}>
                Go to Admin
              </Button>
            ) : undefined
          }
        />
      ) : (
        <FeatureGrid features={features} />
      )}
    </>
  );
}
