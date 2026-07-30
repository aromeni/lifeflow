import type { ReactNode } from "react";

// A closed, small vocabulary of semantic tones — never an arbitrary colour
// literal at a call site (Stage 10 design system, ADR 0006). Every badge
// keeps a visible text label; colour is reinforcement, never the only
// signal (WCAG 1.4.1).
export type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

const TONE_STYLE: Record<BadgeTone, string> = {
  neutral: "bg-surface-raised border-border-strong text-text-secondary",
  info: "bg-info-bg border-info-border text-info-text",
  success: "bg-success-bg border-success-border text-success-text",
  warning: "bg-warning-bg border-warning-border text-warning-text",
  danger: "bg-danger-bg border-danger-border text-danger-text",
};

// A small filled dot beside the label — a non-colour-dependent shape cue
// that still differs visibly across tones once rendered (size/position is
// identical; screen readers ignore it via aria-hidden, since the adjacent
// text already carries the meaning).
function ToneDot({ tone }: { tone: BadgeTone }) {
  if (tone === "neutral") return null;
  const dotColor: Record<Exclude<BadgeTone, "neutral">, string> = {
    info: "bg-info-icon",
    success: "bg-success-icon",
    warning: "bg-warning-icon",
    danger: "bg-danger-icon",
  };
  return <span aria-hidden="true" className={`size-1.5 rounded-full ${dotColor[tone]}`} />;
}

export function Badge({
  tone = "neutral",
  children,
  testId,
  uppercase = true,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  testId?: string;
  uppercase?: boolean;
}) {
  return (
    <span
      data-testid={testId}
      className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${
        uppercase ? "uppercase tracking-wide" : ""
      } ${TONE_STYLE[tone]}`}
    >
      <ToneDot tone={tone} />
      {children}
    </span>
  );
}

const PRIORITY_TONE: Record<"high" | "medium" | "low", BadgeTone> = {
  high: "danger",
  medium: "warning",
  low: "info",
};

// The Today brief's priority_band is a free-form string from the API
// (contract: "high" | "medium" | "low"); anything unrecognised must fail
// safe to a neutral, still-labelled badge rather than silently losing the
// signal or throwing.
export function PriorityBadge({ band, testId }: { band: string; testId?: string }) {
  const tone = PRIORITY_TONE[band as "high" | "medium" | "low"] ?? "neutral";
  return (
    <Badge tone={tone} testId={testId}>
      {band} priority
    </Badge>
  );
}

export function RiskBadge({ level }: { level: string }) {
  const tone = PRIORITY_TONE[level as "high" | "medium" | "low"] ?? "neutral";
  return (
    <Badge tone={tone} uppercase={false}>
      Risk: {level}
    </Badge>
  );
}
