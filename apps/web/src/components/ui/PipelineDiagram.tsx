// A restrained, abstract representation of the daily workflow — plain
// structural HTML/CSS, not an illustration or stock "AI" artwork (Stage 10
// §6). Each step is a labelled node connected by a single line, reading
// top-to-bottom like the real pipeline: sources in, a human decision in
// the middle, a safe action out.
const STEPS = [
  { label: "Gmail + Calendar", detail: "a recent window you authorise" },
  { label: "Evidence", detail: "every item traced to its source" },
  { label: "Daily priorities", detail: "ranked, with plain reasons" },
  { label: "Proposed action", detail: "exact draft or event, nothing sent yet" },
  { label: "Your approval", detail: "review the exact payload first" },
  { label: "Safe execution", detail: "draft-only Gmail, insert-only Calendar" },
  { label: "Audit trail", detail: "what happened, in plain language" },
] as const;

export function PipelineDiagram() {
  return (
    <div
      aria-hidden="true"
      className="rounded-lg border border-border bg-surface p-6 shadow-sm sm:p-8"
    >
      <ol className="relative flex flex-col gap-6 pl-8">
        <div className="absolute top-2 bottom-2 left-[calc(0.75rem-1px)] w-px bg-border-strong" />
        {STEPS.map((step, index) => {
          const isApproval = step.label === "Your approval";
          return (
            <li key={step.label} className="relative flex flex-col gap-0.5">
              <span
                className={`absolute top-0.5 -left-8 flex size-6 items-center justify-center rounded-full border text-[11px] font-semibold ${
                  isApproval
                    ? "border-accent bg-accent text-white"
                    : "border-border-strong bg-surface text-text-secondary"
                }`}
              >
                {index + 1}
              </span>
              <span className="text-sm font-semibold text-foreground">{step.label}</span>
              <span className="text-xs text-text-secondary">{step.detail}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
