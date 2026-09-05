"use client";

import { useActionState } from "react";
import { DatabaseZap, RefreshCw } from "lucide-react";

import { FormMessage } from "@/components/forms/field";
import { SubmitButton } from "@/components/submit-button";
import { seedDemoAction, syncMembersAction } from "@/lib/actions";

export function AdminActions() {
  const [seedState, seed] = useActionState(seedDemoAction, null);
  const [syncState, sync] = useActionState(syncMembersAction, null);

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <form action={seed} className="border-border/60 bg-card grid gap-3 rounded-xl border p-4">
        <div>
          <h3 className="font-medium">Load demo data</h3>
          <p className="text-muted-foreground mt-1 text-sm">
            Seeds teams, features, six demo users, their sessions and Context Bank entries into{" "}
            <span className="font-medium">this organization</span>, adds you to the Payments team and assigns you to
            LOGIN. Safe to re-run.
          </p>
        </div>
        <FormMessage state={seedState} />
        <div>
          <SubmitButton pendingLabel="Seeding…">
            <DatabaseZap data-icon="inline-start" />
            Load demo data
          </SubmitButton>
        </div>
      </form>

      <form action={sync} className="border-border/60 bg-card grid gap-3 rounded-xl border p-4">
        <div>
          <h3 className="font-medium">Sync members from Clerk</h3>
          <p className="text-muted-foreground mt-1 text-sm">
            Pulls the organization&apos;s Clerk members into Forge so real teammates can be added to teams and
            features. (Production would use Clerk webhooks.)
          </p>
        </div>
        <FormMessage state={syncState} />
        <div>
          <SubmitButton variant="outline" pendingLabel="Syncing…">
            <RefreshCw data-icon="inline-start" />
            Sync members
          </SubmitButton>
        </div>
      </form>
    </div>
  );
}
