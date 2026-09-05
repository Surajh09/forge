import { X } from "lucide-react";

import { ConfirmButton } from "@/components/forms/confirm-button";
import { nativeSelectClass } from "@/components/forms/field";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { featureLinkFormAction, setFeatureLinkAction } from "@/lib/actions";

type Option = { id: string; label: string };

/** Admin control to attach/detach teams or assignees on a feature (server component). */
export function FeatureLinks({
  kind,
  featureId,
  linked,
  options,
  emptyLabel,
}: {
  kind: "teams" | "assignees";
  featureId: string;
  linked: Option[];
  options: Option[];
  emptyLabel: string;
}) {
  const linkedIds = new Set(linked.map((l) => l.id));
  const candidates = options.filter((o) => !linkedIds.has(o.id));

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-1.5">
        {linked.length === 0 && <span className="text-muted-foreground text-sm">{emptyLabel}</span>}
        {linked.map((l) => (
          <Badge key={l.id} variant="secondary" className="gap-1 pr-1">
            {l.label}
            <ConfirmButton
              action={setFeatureLinkAction.bind(null, kind, featureId, l.id, false)}
              variant="ghost"
              size="icon-xs"
              className="size-4"
              aria-label={`Remove ${l.label}`}
            >
              <X className="size-3" />
            </ConfirmButton>
          </Badge>
        ))}
      </div>
      {candidates.length > 0 && (
        <form action={featureLinkFormAction.bind(null, kind, featureId, true)} className="flex items-center gap-2">
          <select name="target_id" className={nativeSelectClass} defaultValue="" required aria-label={`Add ${kind}`}>
            <option value="" disabled>
              {kind === "teams" ? "Attach a team…" : "Assign a person…"}
            </option>
            {candidates.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
          <SubmitButton variant="outline" size="sm" pendingLabel="Saving…">
            Add
          </SubmitButton>
        </form>
      )}
    </div>
  );
}
