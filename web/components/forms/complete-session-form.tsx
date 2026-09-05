"use client";

import { useActionState, useState } from "react";
import { Sparkles } from "lucide-react";

import { Field, FormMessage, nativeSelectClass } from "@/components/forms/field";
import { SubmitButton } from "@/components/submit-button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { completeSessionAction } from "@/lib/actions";

const LIST_FIELDS = [
  { name: "changes", label: "Changes", placeholder: "One per line" },
  { name: "affected_components", label: "Affected files / components", placeholder: "One path per line" },
  { name: "dependencies", label: "Dependencies", placeholder: "One per line" },
  { name: "constraints", label: "Constraints", placeholder: "One per line" },
  { name: "known_issues", label: "Known issues", placeholder: "One per line" },
  { name: "open_questions", label: "Open questions", placeholder: "One per line" },
];

export function CompleteSessionForm({ sessionId, defaultGoal }: { sessionId: string; defaultGoal: string }) {
  const [state, formAction] = useActionState(completeSessionAction.bind(null, sessionId), null);
  const [mode, setMode] = useState<"author" | "generate">("author");

  return (
    <form action={formAction} className="grid gap-4">
      <input type="hidden" name="mode" value={mode} />

      <p className="text-muted-foreground text-sm">
        Ending a session runs its context through the <span className="font-medium">Context Contract</span> and a
        validator, then fans it out into typed Context Bank entries: one per decision, constraint, known issue and
        open question, plus one for the objective.
      </p>

      <div className="border-border/60 flex flex-wrap items-center gap-3 rounded-lg border p-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" checked={mode === "author"} onChange={() => setMode("author")} className="accent-primary" />
          Write the context myself
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" checked={mode === "generate"} onChange={() => setMode("generate")} className="accent-primary" />
          <Sparkles className="size-3.5" />
          Generate it from session metadata
        </label>
      </div>

      {mode === "generate" ? (
        <p className="text-muted-foreground border-border/60 rounded-lg border border-dashed p-4 text-sm">
          The Context Generator will derive a contract from this session&apos;s goal and summary. With no transcript to
          read it produces low-confidence context, so the entries are stored as{" "}
          <span className="font-medium">pending review</span> rather than published as trusted knowledge.
        </p>
      ) : (
        <>
          <Field label="Objective" htmlFor="objective">
            <Input id="objective" name="objective" defaultValue={defaultGoal} required />
          </Field>
          <Field
            label="Technical decisions"
            htmlFor="decisions"
            hint="One per line. Add the reason after a dash: Rotate server-side — prevents token reuse"
          >
            <Textarea id="decisions" name="decisions" rows={3} className="font-mono text-xs" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            {LIST_FIELDS.map((f) => (
              <Field key={f.name} label={f.label} htmlFor={f.name}>
                <Textarea id={f.name} name={f.name} rows={3} placeholder={f.placeholder} className="font-mono text-xs" />
              </Field>
            ))}
          </div>
          <Field label="Confidence (0–1)" htmlFor="confidence" hint="Below 0.4 is held for review instead of published.">
            <Input id="confidence" name="confidence" type="number" step="0.05" min="0" max="1" defaultValue="0.8" required />
          </Field>
        </>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Summary" htmlFor="summary">
          <Textarea id="summary" name="summary" rows={2} placeholder="One or two sentences for the session list" />
        </Field>
        <Field label="Outcome" htmlFor="status">
          <select id="status" name="status" className={nativeSelectClass} defaultValue="completed">
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="abandoned">Abandoned</option>
          </select>
        </Field>
      </div>

      <FormMessage state={state} />
      <div>
        <SubmitButton pendingLabel="Validating & writing context…">End session &amp; write context</SubmitButton>
      </div>
    </form>
  );
}
