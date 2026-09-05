"use client";

import { useActionState, useState } from "react";
import { Play } from "lucide-react";

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
import { startSessionAction } from "@/lib/actions";

const AGENTS = [
  { value: "claude-code", label: "Claude Code", model: "claude-opus-5" },
  { value: "cursor", label: "Cursor", model: "" },
  { value: "manual", label: "Manual (no agent)", model: "" },
];

export function StartSessionDialog({ featureId, featureKey }: { featureId: string; featureKey: string }) {
  const [open, setOpen] = useState(false);
  const [agent, setAgent] = useState(AGENTS[0]);
  const [state, formAction] = useActionState(startSessionAction.bind(null, featureId), null);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>
        <Play data-icon="inline-start" />
        Start session
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Start a session on {featureKey}</DialogTitle>
          <DialogDescription>
            In production the agent runtime creates this automatically; here you record it by hand.
          </DialogDescription>
        </DialogHeader>
        <form action={formAction} className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Agent" htmlFor="agent">
              <select
                id="agent"
                name="agent"
                className={nativeSelectClass}
                value={agent.value}
                onChange={(e) => setAgent(AGENTS.find((a) => a.value === e.target.value) ?? AGENTS[2])}
              >
                {AGENTS.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Model" htmlFor="model">
              <Input id="model" name="model" key={agent.value} defaultValue={agent.model} placeholder="optional" className="font-mono" />
            </Field>
          </div>
          <Field label="Goal" htmlFor="goal">
            <Textarea id="goal" name="goal" rows={3} placeholder="What is this session trying to achieve?" required />
          </Field>
          <FormMessage state={state} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <SubmitButton pendingLabel="Starting…">Start session</SubmitButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
