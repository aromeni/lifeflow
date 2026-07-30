import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { Badge, PriorityBadge } from "@/components/ui/Badge";
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

// A thin left-edge colour bar reinforces priority at a glance without
// relying on colour alone — the text badge alongside it still names the
// band explicitly (Stage 10 §8).
const PRIORITY_EDGE: Record<string, string> = {
  high: "border-l-[var(--color-danger-icon)]",
  medium: "border-l-[var(--color-warning-icon)]",
  low: "border-l-[var(--color-info-icon)]",
};

function BriefItemView({ item, timezone }: { item: BriefItem; timezone: string }) {
  const edgeColor = PRIORITY_EDGE[item.priority_band] ?? "border-l-border-strong";
  return (
    <li
      className={`flex flex-col gap-2 rounded-lg border border-border border-l-4 bg-surface p-4 shadow-xs ${edgeColor}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <span className="font-medium text-foreground">{item.title}</span>
        <PriorityBadge band={item.priority_band} />
      </div>
      <p className="text-sm text-text-secondary">{item.summary}</p>
      {item.due_at ? (
        <p className="text-sm text-foreground" data-testid="brief-item-due">
          Due {formatDue(item.due_at, timezone)}
        </p>
      ) : null}
      <ul className="flex flex-wrap gap-1.5" aria-label="Why this matters">
        {item.reason_codes.map((code) => (
          <li key={code}>
            <Badge tone="neutral" uppercase={false}>
              {reasonLabel(code)}
            </Badge>
          </li>
        ))}
        <li>
          <Badge tone="neutral" uppercase={false}>
            confidence {Math.round(item.confidence * 100)}%
          </Badge>
        </li>
      </ul>
      {item.suggested_action ? (
        <p className="text-sm text-foreground">
          <span className="font-medium">Suggested next step:</span> {item.suggested_action}{" "}
          <span className="text-text-tertiary">(nothing happens without your approval)</span>
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
    <section
      id={headingId}
      aria-labelledby={headingId}
      className="flex scroll-mt-20 flex-col gap-3"
    >
      <h2 id={headingId} className="text-lg font-semibold text-foreground">
        {section.label}
        <span className="ml-2 text-sm font-normal text-text-tertiary">
          ({section.items.length})
        </span>
      </h2>
      {section.items.length === 0 ? (
        <p className="text-sm text-text-tertiary">Nothing here right now.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {section.items.map((item) => (
            <BriefItemView key={item.signal_id} item={item} timezone={timezone} />
          ))}
        </ul>
      )}
    </section>
  );
}
