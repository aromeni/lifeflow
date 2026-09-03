"use client";

import { useState, type ReactNode } from "react";

import { Button, type ButtonVariant } from "@/components/ui/Button";

// Stage 11B (condition 5, deletion-choice clarity): a small, reusable
// two-step confirm for actions that are destructive but not high-risk
// enough to warrant the full preview/typed-phrase machinery reserved for
// imported-data and account deletion (`DeletionControls.tsx`). The first
// click only "arms" the control — it names the consequence and asks for an
// explicit second click before anything actually happens. Used at every
// call site that previously fired on a single click with no confirmation
// at all (disconnect, per-item memory delete, delete-all memory).
export function ConfirmButton({
  label,
  confirmLabel,
  cancelLabel = "Cancel",
  explanation,
  onConfirm,
  variant = "secondary",
  disabled = false,
  testId,
}: {
  label: string;
  confirmLabel: string;
  cancelLabel?: string;
  explanation: ReactNode;
  onConfirm: () => void | Promise<void>;
  variant?: ButtonVariant;
  disabled?: boolean;
  testId: string;
}) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!armed) {
    return (
      <Button
        type="button"
        variant={variant}
        data-testid={testId}
        onClick={() => setArmed(true)}
        disabled={disabled}
      >
        {label}
      </Button>
    );
  }

  return (
    <div
      data-testid={`${testId}-armed`}
      className="flex flex-col gap-2 rounded-md border border-border-strong bg-surface-raised p-3"
    >
      <p role="status" aria-live="polite" className="text-sm text-text-secondary">
        {explanation}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant={variant}
          data-testid={`${testId}-confirm`}
          autoFocus
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onConfirm();
            } finally {
              setBusy(false);
              setArmed(false);
            }
          }}
        >
          {busy ? "Working…" : confirmLabel}
        </Button>
        <Button
          type="button"
          variant="secondary"
          data-testid={`${testId}-cancel`}
          disabled={busy}
          onClick={() => setArmed(false)}
        >
          {cancelLabel}
        </Button>
      </div>
    </div>
  );
}
