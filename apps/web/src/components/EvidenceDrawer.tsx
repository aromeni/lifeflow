import type { BriefEvidence } from "@/lib/types";

function formatWhen(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  }).format(new Date(iso));
}

// Native <details> keeps the disclosure fully keyboard-operable and announced
// without custom ARIA wiring (WCAG 2.2).
export function EvidenceDrawer({
  evidence,
  timezone,
}: {
  evidence: BriefEvidence[];
  timezone: string;
}) {
  return (
    <details className="text-sm">
      <summary className="cursor-pointer underline opacity-80">
        Evidence ({evidence.length} source{evidence.length === 1 ? "" : "s"})
      </summary>
      <ul className="mt-2 flex flex-col gap-2 border-l-2 border-current/20 pl-3">
        {evidence.map((source) => (
          <li key={source.source_ref} className="flex flex-col gap-0.5">
            <span className="font-medium">{source.title}</span>
            <span className="opacity-70">
              {source.source_type === "email" ? "Email" : "Calendar"}
              {source.sender_or_organiser ? ` · ${source.sender_or_organiser}` : ""} ·{" "}
              {formatWhen(source.occurred_at, timezone)} · ref {source.source_ref}
            </span>
            {source.excerpt ? <span className="opacity-80">“{source.excerpt}”</span> : null}
          </li>
        ))}
      </ul>
    </details>
  );
}
