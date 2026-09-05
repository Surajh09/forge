"use client";

import { useActionState } from "react";

import { Field, FormMessage } from "@/components/forms/field";
import { SubmitButton } from "@/components/submit-button";
import { Input } from "@/components/ui/input";
import { createTeamAction } from "@/lib/actions";

export function CreateTeamForm() {
  const [state, formAction] = useActionState(createTeamAction, null);
  return (
    <form action={formAction} className="grid gap-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end">
      <Field label="Team name" htmlFor="team-name">
        <Input id="team-name" name="name" placeholder="Payments" required />
      </Field>
      <Field label="Description" htmlFor="team-description">
        <Input id="team-description" name="description" placeholder="What this team owns" />
      </Field>
      <SubmitButton pendingLabel="Creating…">Create team</SubmitButton>
      <div className="sm:col-span-3">
        <FormMessage state={state} />
      </div>
    </form>
  );
}
