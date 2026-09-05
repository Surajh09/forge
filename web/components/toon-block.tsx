"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Raw TOON output with a copy button — exactly what an agent receives. */
export function ToonBlock({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked; the text is selectable either way.
    }
  };

  return (
    <div className="border-border/60 relative overflow-hidden rounded-lg border">
      <div className="border-border/60 bg-muted/40 flex items-center gap-2 border-b px-3 py-1.5">
        <span className="text-muted-foreground font-mono text-xs">{label ?? "text/plain · TOON"}</span>
        <Button type="button" variant="ghost" size="xs" className="ml-auto" onClick={copy}>
          {copied ? <Check data-icon="inline-start" /> : <Copy data-icon="inline-start" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      {/* Wraps rather than scrolling sideways: TOON lines are long, and a
          document meant to be read should not need horizontal scrubbing. */}
      <pre className="p-3 font-mono text-xs leading-relaxed break-words whitespace-pre-wrap">{text}</pre>
    </div>
  );
}
