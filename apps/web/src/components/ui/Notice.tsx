import type { ReactNode } from "react";

// The one shared way LifeFlow tells the user about a state that isn't
// plain success — temporary outages, degraded dependencies, uncertain
// outcomes, rate limiting, validation problems (Stage 10 §13). Replaces
// ad hoc amber/red paragraph blocks scattered across pages. `role` is left
// to the caller: `"status"` for non-urgent updates, `"alert"` for things
// that need immediate attention — this component never guesses.
export type NoticeTone = "info" | "warning" | "danger" | "success";

const TONE_STYLE: Record<NoticeTone, string> = {
  info: "bg-info-bg border-info-border text-info-text",
  warning: "bg-warning-bg border-warning-border text-warning-text",
  danger: "bg-danger-bg border-danger-border text-danger-text",
  success: "bg-success-bg border-success-border text-success-text",
};

// Plain geometric glyphs, not an icon-font/SVG-sprite dependency — each
// shape is also distinct by form (not only colour) so the tone still reads
// under greyscale/high-contrast rendering.
const TONE_GLYPH: Record<NoticeTone, string> = {
  info: "ℹ",
  warning: "▲",
  danger: "✕",
  success: "✓",
};

export function Notice({
  tone,
  role,
  title,
  children,
  testId,
}: {
  tone: NoticeTone;
  role: "status" | "alert";
  title?: string;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <div
      role={role}
      aria-live={role === "alert" ? "assertive" : "polite"}
      data-testid={testId}
      className={`flex gap-2.5 rounded-md border px-3.5 py-3 text-sm ${TONE_STYLE[tone]}`}
    >
      <span aria-hidden="true" className="mt-0.5 shrink-0 font-semibold">
        {TONE_GLYPH[tone]}
      </span>
      <div className="flex flex-col gap-0.5">
        {title ? <p className="font-medium">{title}</p> : null}
        <div className="opacity-95">{children}</div>
      </div>
    </div>
  );
}
