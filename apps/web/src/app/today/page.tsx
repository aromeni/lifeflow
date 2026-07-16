"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { SourceItemList } from "@/components/SourceItemList";
import { api, ApiError } from "@/lib/api";
import type { Me, SourceItem, SourceItemList as ItemList } from "@/lib/types";

type LoadState = "loading" | "ready" | "unauthenticated" | "error";

export default function TodayPage() {
  const [state, setState] = useState<LoadState>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [events, setEvents] = useState<SourceItem[]>([]);
  const [emails, setEmails] = useState<SourceItem[]>([]);

  const load = useCallback(async () => {
    try {
      const profile = await api<Me>("/me");
      const nowIso = new Date().toISOString();
      const [upcoming, recent] = await Promise.all([
        api<ItemList>(
          `/source-items?source_type=calendar_event&occurring_after=${encodeURIComponent(nowIso)}&limit=12`,
        ),
        api<ItemList>("/source-items?source_type=email&limit=12"),
      ]);
      setMe(profile);
      setEvents([...upcoming.items].reverse()); // soonest first
      setEmails(recent.items);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiError && error.status === 401 ? "unauthenticated" : "error");
    }
  }, []);

  // Legitimate fetch-on-mount: setState only runs after awaited responses,
  // not synchronously in the effect body.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  function refresh() {
    setState("loading");
    void load();
  }

  if (state === "unauthenticated") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16">
        <p>
          You are not signed in.{" "}
          <Link href="/" className="underline">
            Start the demo
          </Link>{" "}
          first.
        </p>
      </main>
    );
  }

  const timezone = me?.timezone ?? "Europe/London";

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-1">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="text-3xl font-semibold tracking-tight">Today</h1>
          <button type="button" onClick={refresh} className="text-sm underline">
            Refresh
          </button>
        </div>
        <p aria-live="polite" className="text-sm opacity-70">
          {state === "loading" && "Loading your information…"}
          {state === "ready" &&
            `${events.length} upcoming events · ${emails.length} recent messages · timezone ${timezone}`}
          {state === "error" && "Could not load your information. Is the API running?"}
        </p>
        <p className="text-sm opacity-70">
          This is the dashboard shell: normalised information only. Signals, priorities, and the
          daily brief arrive in the next stages.
        </p>
      </header>

      <section aria-labelledby="upcoming-heading" className="flex flex-col gap-2">
        <h2 id="upcoming-heading" className="text-xl font-medium">
          Today &amp; upcoming
        </h2>
        <SourceItemList items={events} timezone={timezone} emptyMessage="No upcoming events." />
      </section>

      <section aria-labelledby="recent-heading" className="flex flex-col gap-2">
        <h2 id="recent-heading" className="text-xl font-medium">
          Recent messages
        </h2>
        <SourceItemList items={emails} timezone={timezone} emptyMessage="No recent messages." />
      </section>

      <footer className="text-sm opacity-70">
        <Link href="/debug/source-items" className="underline">
          Developer view: raw normalised items
        </Link>
      </footer>
    </main>
  );
}
