"use client";

import { useActionState, useState } from "react";
import { Plus } from "lucide-react";

import { Field, FormMessage } from "@/components/forms/field";
import { SubmitButton } from "@/components/submit-button";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createFeatureAction } from "@/lib/actions";
import type { TeamSummary, User } from "@/lib/types";

export function CreateFeatureDialog({ teams, users }: { teams: TeamSummary[]; users: User[] }) {
  const [open, setOpen] = useState(false);
  const [state, formAction] = useActionState(createFeatureAction, null);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>
        <Plus data-icon="inline-start" />
        New feature
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New feature</DialogTitle>
          <DialogDescription>
            A feature is the ownership boundary for sessions and context. Attach the teams that own it and any
            directly assigned people.
          </DialogDescription>
        </DialogHeader>
        <form action={formAction} className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-[1fr_2fr]">
            <Field label="Key" htmlFor="key" hint="UPPER_SNAKE_CASE">
              <Input id="key" name="key" placeholder="PAYMENT" required pattern="[A-Za-z][A-Za-z0-9_\-\s]{1,63}" className="font-mono uppercase" />
            </Field>
            <Field label="Name" htmlFor="name">
              <Input id="name" name="name" placeholder="Payments" required />
            </Field>
          </div>
          <Field label="Description" htmlFor="description">
            <Textarea id="description" name="description" rows={3} placeholder="Checkout, Stripe integration, refunds…" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <fieldset className="grid gap-1.5">
              <legend className="mb-1.5 text-sm font-medium">Owning teams</legend>
              {teams.length === 0 && <p className="text-muted-foreground text-xs">No teams yet — create them in Admin.</p>}
              {teams.map((t) => (
                <label key={t.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" name="team_ids" value={t.id} className="accent-primary" />
                  {t.name}
                </label>
              ))}
            </fieldset>
            <fieldset className="grid max-h-40 gap-1.5 overflow-y-auto">
              <legend className="mb-1.5 text-sm font-medium">Assigned people</legend>
              {users.map((u) => (
                <label key={u.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" name="assignee_ids" value={u.id} className="accent-primary" />
                  {u.display_name}
                </label>
              ))}
            </fieldset>
          </div>
          <FormMessage state={state} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <SubmitButton pendingLabel="Creating…">Create feature</SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
