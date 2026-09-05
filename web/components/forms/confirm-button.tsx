"use client";

import { SubmitButton } from "@/components/submit-button";
import type { Button } from "@/components/ui/button";

type Props = React.ComponentProps<typeof Button> & {
  action: () => Promise<void>;
  confirm?: string;
};

/** A one-button form for a bound server action, with an optional confirm prompt. */
export function ConfirmButton({ action, confirm, children, ...props }: Props) {
  return (
    <form
      action={action}
      onSubmit={(e) => {
        if (confirm && !window.confirm(confirm)) e.preventDefault();
      }}
      className="inline"
    >
      <SubmitButton {...props}>{children}</SubmitButton>
    </form>
  );
}
