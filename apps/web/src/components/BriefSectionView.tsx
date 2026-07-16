import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import type { BriefItem, BriefSection } from "@/lib/types";

function formatDue(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  }).format(new Date(iso));
}

const REASON_LABELS: Record<string, string> = {
  explicit_request: "Explicit request from sender",
  weak_request_cue: "Possible request",
  commitment_made: "You promised this",
  deadline_phrase: "Deadline mentioned",
  deadline_detected: "Deadline detected",
  due_within_24h: "Due within 24 hours",
  due_within_72h: "Due within 3 days",
  due_this_week: "Due this week",
  overdue: "Overdue",
  calendar_conflict: "Calendar conflict detected",
  frequent_contact: "Frequent contact",
  meeting_upcoming: "Upcoming meeting",
};

function reasonLabel(code: string): string {
  const noReply = /^no_reply_(\d+)d$/.exec(code);
  if (noReply) {
    return `No reply for ${noReply[1]} days`;
  }
  return REASON_LABELS[code] ?? code.replaceAll("_", " ");
}

function BriefItemView({ item, timezone }: { item: BriefItem; timezone: string }) {
  return (
    <li className="flex flex-col gap-1 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-medium">{item.title}</span>
        <span className="shrink-0 rounded border border-current/30 px-1.5 py-0.5 text-xs uppercase tracking-wide opacity-80">
          {item.priority_band} priority
        </span>
      </div>
      <p className="text-sm opacity-80">{item.summary}</p>
      {item.due_at ? <p className="text-sm">Due {formatDue(item.due_at, timezone)}</p> : null}
      <ul className="flex flex-wrap gap-1.5 text-xs" aria-label="Why this matters">
        {item.reason_codes.map((code) => (
          <li key={code} className="rounded-full border border-current/20 px-2 py-0.5 opacity-80">
            {reasonLabel(code)}
          </li>
        ))}
        <li className="rounded-full border border-current/20 px-2 py-0.5 opacity-80">
          confidence {Math.round(item.confidence * 100)}%
        </li>
      </ul>
      {item.suggested_action ? (
        <p className="text-sm">
          <span className="font-medium">Suggested next step:</span> {item.suggested_action}{" "}
          <span className="opacity-70">(nothing happens without your approval)</span>
        </p>
      ) : null}
      <EvidenceDrawer evidence={item.evidence} timezone={timezone} />
    </li>
  );
}

export function BriefSectionView({
  section,
  timezone,
}: {
  section: BriefSection;
  timezone: string;
}) {
  const headingId = `section-${section.key}`;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-xl font-medium">
        {section.label}
        <span className="ml-2 text-sm font-normal opacity-70">({section.items.length})</span>
      </h2>
      {section.items.length === 0 ? (
        <p className="text-sm opacity-70">Nothing here right now.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-current/10">
          {section.items.map((item) => (
            <BriefItemView key={item.signal_id} item={item} timezone={timezone} />
          ))}
        </ul>
      )}
    </section>
  );
}
