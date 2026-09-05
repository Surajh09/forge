"use client";

import { useActionState, useState } from "react";
import { Plus } from "lucide-react";

import { Field, FormMessage, nativeSelectClass } from "@/components/forms/field";
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
import { recordContextAction } from "@/lib/actions";
import { CONTEXT_KINDS, type ContextKind, type Session } from "@/lib/types";

const BODY_LABEL: Record<ContextKind, string> = {
  decision: "The decision",
  constraint: "The constraint",
  architecture: "The note",
  change: "What changed",
  known_issue: "The issue",
  open_question: "The question",
};

export function RecordContextDialog({ featureId, sessions }: { featureId: string; sessions: Session[] }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<ContextKind>("decision");
  const [state, formAction] = useActionState(recordContextAction.bind(null, featureId), null);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <Plus data-icon="inline-start" />
        Add context
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Record a context statement</DialogTitle>
          <DialogDescription>
            Knowledge the feature should carry forward. It becomes active context immediately, so link a source
            session where one applies.
          </DialogDescription>
        </DialogHeader>
        <form action={formAction} className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-[10rem_1fr]">
            <Field label="Kind" htmlFor="kind">
              <select
                id="kind"
                name="kind"
                className={nativeSelectClass}
                value={kind}
                onChange={(e) => setKind(e.target.value as ContextKind)}
              >
                {CONTEXT_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k.replace("_", " ")}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Title" htmlFor="title" hint="A short, quotable statement.">
              <Input id="title" name="title" required placeholder="Amounts are integer minor units" />
            </Field>
          </div>

          <Field label={BODY_LABEL[kind]} htmlFor="body">
            <Textarea id="body" name="body" rows={3} placeholder="Leave blank to reuse the title." />
          </Field>

          {kind === "decision" && (
            <Field label="Reason" htmlFor="reason" hint="Why this was decided.">
              <Input id="reason" name="reason" placeholder="Prevents double refunds on webhook retries" />
            </Field>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Confidence" htmlFor="confidence" hint="Optional, 0–1.">
              <Input id="confidence" name="confidence" type="number" step="0.05" min="0" max="1" defaultValue="0.9" />
            </Field>
            <Field label="Source session" htmlFor="session_id" hint="Optional provenance link.">
              <select id="session_id" name="session_id" className={nativeSelectClass} defaultValue="">
                <option value="">None</option>
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {(s.goal ?? s.id.slice(0, 8)).slice(0, 60)}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <FormMessage state={state} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <SubmitButton pendingLabel="Validating…">Record context</SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
