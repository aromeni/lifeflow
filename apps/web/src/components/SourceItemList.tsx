import type { SourceItem } from "@/lib/types";

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

export function SourceItemList({
  items,
  timezone,
  emptyMessage,
}: {
  items: SourceItem[];
  timezone: string;
  emptyMessage: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm opacity-70">{emptyMessage}</p>;
  }
  return (
    <ul className="flex flex-col divide-y divide-current/10">
      {items.map((item) => (
        <li key={item.id} className="flex flex-col gap-0.5 py-2.5">
          <span className="font-medium">{item.title}</span>
          <span className="text-sm opacity-70">
            {item.sender_or_organiser} · {formatWhen(item.occurred_at, timezone)}
            {item.source_type === "calendar_event" && item.metadata.location
              ? ` · ${String(item.metadata.location)}`
              : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}
