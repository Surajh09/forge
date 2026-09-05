"use client";

import { useActionState, useState } from "react";
import { GitCommitVertical } from "lucide-react";

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
import { supersedeContextAction } from "@/lib/actions";
import type { ContextEntry } from "@/lib/types";

/** Revise a statement: writes version+1 and marks the current row superseded. */
export function SupersedeContextDialog({ entry }: { entry: ContextEntry }) {
  const [open, setOpen] = useState(false);
  const [state, formAction] = useActionState(supersedeContextAction.bind(null, entry.id), null);

  const fields = Object.entries(entry.payload).filter(([, v]) => typeof v === "string" || typeof v === "number");
  const keys = fields.map(([k]) => k);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <GitCommitVertical data-icon="inline-start" />
        Supersede
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Supersede this statement</DialogTitle>
          <DialogDescription>
            Writes version {entry.version + 1}. The current version stays readable and is marked superseded, so
            nothing is lost and the source session is carried forward.
          </DialogDescription>
        </DialogHeader>
        <form action={formAction} className="grid gap-4">
          <input type="hidden" name="payload_keys" value={keys.join(",")} />

          <Field label="Title" htmlFor="title">
            <Input id="title" name="title" defaultValue={entry.title} required />
          </Field>

          {fields.map(([key, value]) => (
            <Field key={key} label={key.replace(/_/g, " ")} htmlFor={`payload__${key}`} className="capitalize">
              <Textarea id={`payload__${key}`} name={`payload__${key}`} rows={3} defaultValue={String(value)} />
            </Field>
          ))}

          <Field label="Confidence" htmlFor="confidence" hint="Optional, 0–1.">
            <Input
              id="confidence"
              name="confidence"
              type="number"
              step="0.05"
              min="0"
              max="1"
              defaultValue={entry.confidence ?? 0.9}
            />
          </Field>

          <FormMessage state={state} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <SubmitButton pendingLabel="Writing new version…">Supersede</SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
