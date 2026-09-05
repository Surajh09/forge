"use client";

import { useFormStatus } from "react-dom";

import { Button } from "@/components/ui/button";

type Props = React.ComponentProps<typeof Button> & { pendingLabel?: string };

export function SubmitButton({ children, pendingLabel = "Working…", disabled, ...props }: Props) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending || disabled} {...props}>
      {pending ? pendingLabel : children}
    </Button>
  );
}
