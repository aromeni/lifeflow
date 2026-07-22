"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { EvidenceFreshness, MemoryItem, MemoryList, ScheduledBriefStatus } from "@/lib/types";

type LoadState = "loading" | "ready" | "unauthenticated" | "error";

type PreferenceItem = {
  key: string;
  value: Record<string, unknown>;
  provenance: string;
  is_default: boolean;
  updated_at: string | null;
};

type PreferencesResponse = { preferences: PreferenceItem[] };
type MeResponse = { timezone: string };

const SECTION_LABELS: Record<string, string> = {
  today_upcoming: "Today and upcoming",
  waiting_for: "Waiting for",
  suggested_actions: "Suggested actions",
  low_confidence_review: "Low-confidence review",
};

const RUN_STATUS_LABELS: Record<string, string> = {
  pending: "queued",
  running: "in progress",
  succeeded: "succeeded",
  failed: "failed",
  skipped: "skipped",
};

const FRESHNESS_LABELS: Record<string, string> = {
  fresh: "up to date",
  aging: "a little old",
  stale: "old — consider syncing again from Connections",
};

const BAND_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

function memoryStatusLabel(item: MemoryItem): string {
  if (item.applied) return "Applied to your future drafts";
  if (item.overridden_by_explicit) return "Overridden by your explicit sign-off";
  switch (item.status) {
    case "candidate":
      return "Suggested — not applied until you confirm it";
    case "confirmed":
      return "Confirmed";
    case "superseded":
      return "Overridden — no longer applied";
    case "dismissed":
      return "Dismissed";
    case "expired":
      return "Expired";
    default:
      return item.status;
  }
}

const PROVIDER_LABELS: Record<string, string> = {
  google: "Google (Gmail + Calendar)",
};

function formatInTimezone(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  }).format(new Date(iso));
}

export default function SettingsPage() {
  const [state, setState] = useState<LoadState>("loading");
  const [timezone, setTimezone] = useState("");
  const [briefingTime, setBriefingTime] = useState("07:30");
  const [workStart, setWorkStart] = useState("09:00");
  const [workEnd, setWorkEnd] = useState("17:30");
  const [sections, setSections] = useState<string[]>(Object.keys(SECTION_LABELS));
  const [scheduledEnabled, setScheduledEnabled] = useState(false);
  const [scheduleStatus, setScheduleStatus] = useState<ScheduledBriefStatus | null>(null);
  const [evidenceFreshness, setEvidenceFreshness] = useState<EvidenceFreshness | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [memoryEnabled, setMemoryEnabled] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [memoryMessage, setMemoryMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [me, prefs, status, freshness, memoryList] = await Promise.all([
        api<MeResponse>("/me"),
        api<PreferencesResponse>("/preferences"),
        api<ScheduledBriefStatus>("/scheduled-briefs/status"),
        api<EvidenceFreshness>("/evidence-freshness"),
        api<MemoryList>("/memories"),
      ]);
      setTimezone(me.timezone);
      setScheduleStatus(status);
      setEvidenceFreshness(freshness);
      setMemories(memoryList.memories);
      setMemoryEnabled(memoryList.inference_enabled);
      for (const item of prefs.preferences) {
        if (item.key === "briefing_time") {
          setBriefingTime(String(item.value.value ?? "07:30"));
        }
        if (item.key === "working_hours") {
          setWorkStart(String(item.value.start ?? "09:00"));
          setWorkEnd(String(item.value.end ?? "17:30"));
        }
        if (item.key === "brief_sections" && Array.isArray(item.value.sections)) {
          setSections(item.value.sections as string[]);
        }
        if (item.key === "scheduled_briefs_enabled") {
          setScheduledEnabled(Boolean(item.value.enabled));
        }
      }
      setState("ready");
    } catch (err) {
      setState(err instanceof ApiError && err.status === 401 ? "unauthenticated" : "error");
    }
  }, []);

  useEffect(() => {
    // State changes occur only after the external API promise settles.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function save() {
    if (saving) return;
    setSaving(true);
    setMessage("");
    setError("");
    try {
      await api("/me", { method: "PATCH", body: JSON.stringify({ timezone }) });
      await api("/preferences/briefing_time", {
        method: "PUT",
        body: JSON.stringify({ value: { value: briefingTime } }),
      });
      await api("/preferences/working_hours", {
        method: "PUT",
        body: JSON.stringify({ value: { start: workStart, end: workEnd } }),
      });
      await api("/preferences/brief_sections", {
        method: "PUT",
        body: JSON.stringify({ value: { sections } }),
      });
      await api("/preferences/scheduled_briefs_enabled", {
        method: "PUT",
        body: JSON.stringify({ value: { enabled: scheduledEnabled } }),
      });
      const freshStatus = await api<ScheduledBriefStatus>("/scheduled-briefs/status");
      setScheduleStatus(freshStatus);
      setMessage("Settings saved. The next brief you generate will reflect them.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Settings could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  function toggleSection(key: string) {
    setSections((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
    );
  }

  const reloadMemories = useCallback(async () => {
    const list = await api<MemoryList>("/memories");
    setMemories(list.memories);
    setMemoryEnabled(list.inference_enabled);
  }, []);

  async function toggleMemoryInference(enabled: boolean) {
    setMemoryMessage("");
    setError("");
    try {
      await api("/preferences/memory_inference_enabled", {
        method: "PUT",
        body: JSON.stringify({ value: { enabled } }),
      });
      setMemoryEnabled(enabled);
      setMemoryMessage(
        enabled
          ? "Learning turned on. LifeFlow will only learn from actions you take here."
          : "Learning paused. Existing memory is kept until you delete it.",
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update memory learning.");
    }
  }

  async function runMemoryAction(action: () => Promise<unknown>, successCopy: string) {
    setMemoryMessage("");
    setError("");
    try {
      await action();
      await reloadMemories();
      setMemoryMessage(successCopy);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "That memory action could not be completed.",
      );
    }
  }

  function confirmMemory(item: MemoryItem) {
    void runMemoryAction(
      () =>
        api(`/memories/${item.id}/confirm`, {
          method: "POST",
          body: JSON.stringify({ expected_version: item.version }),
        }),
      "Confirmed. Your future draft replies will use this sign-off.",
    );
  }

  function saveEditedMemory(item: MemoryItem) {
    const value = editValue.trim();
    void runMemoryAction(
      () =>
        api(`/memories/${item.id}`, {
          method: "PUT",
          body: JSON.stringify({ expected_version: item.version, value }),
        }),
      "Saved and confirmed.",
    ).then(() => {
      setEditingId(null);
      setEditValue("");
    });
  }

  function dismissMemory(item: MemoryItem) {
    void runMemoryAction(
      () =>
        api(`/memories/${item.id}/dismiss`, {
          method: "POST",
          body: JSON.stringify({ expected_version: item.version }),
        }),
      "Dismissed. LifeFlow won't suggest this again unless your behaviour clearly changes.",
    );
  }

  function deleteMemory(item: MemoryItem) {
    void runMemoryAction(
      () => api(`/memories/${item.id}`, { method: "DELETE" }),
      "Deleted. This did not delete anything in Gmail or Calendar.",
    );
  }

  function deleteAllMemories() {
    void runMemoryAction(
      () => api("/memories", { method: "DELETE" }),
      "All inferred memory deleted. Your Gmail, Calendar, and history are untouched.",
    );
  }

  if (state === "unauthenticated") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p>
          Sign in first from the <Link href="/">home page</Link>.
        </p>
      </main>
    );
  }
  if (state === "error") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p role="alert">Settings could not be loaded. Try again shortly.</p>
      </main>
    );
  }
  if (state === "loading") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p aria-busy="true">Loading settings…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="flex items-baseline justify-between gap-4">
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <Link href="/today" className="text-sm underline">
          Back to Today
        </Link>
      </header>
      <p className="text-sm text-neutral-600 dark:text-neutral-300">
        Everything here is explicit: LifeFlow only adapts in ways you set yourself, each change is
        recorded in your audit history, and none of these settings can approve or execute anything
        on your behalf.
      </p>

      <section aria-labelledby="settings-time" className="flex flex-col gap-3">
        <h2 id="settings-time" className="text-xl font-medium">
          Time
        </h2>
        <label className="flex flex-col gap-1 text-sm">
          Timezone (IANA name)
          <input
            data-testid="settings-timezone"
            className="w-64 rounded border px-2 py-1"
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Daily briefing time
          <span className="text-neutral-600 dark:text-neutral-300">
            {scheduleStatus?.enabled
              ? "Used by scheduled daily briefs below."
              : "Saved now, but not yet in use: briefs are currently generated on demand. This " +
                "time takes effect once you enable scheduled daily briefs below."}
          </span>
          <input
            data-testid="settings-briefing-time"
            type="time"
            className="w-32 rounded border px-2 py-1"
            value={briefingTime}
            onChange={(event) => setBriefingTime(event.target.value)}
          />
        </label>
        <div className="flex items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Working hours start
            <input
              data-testid="settings-work-start"
              type="time"
              className="w-32 rounded border px-2 py-1"
              value={workStart}
              onChange={(event) => setWorkStart(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Working hours end
            <input
              data-testid="settings-work-end"
              type="time"
              className="w-32 rounded border px-2 py-1"
              value={workEnd}
              onChange={(event) => setWorkEnd(event.target.value)}
            />
          </label>
        </div>
      </section>

      <section aria-labelledby="settings-schedule" className="flex flex-col gap-3">
        <h2 id="settings-schedule" className="text-xl font-medium">
          Scheduled daily briefs
        </h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            data-testid="settings-schedule-enabled"
            checked={scheduledEnabled}
            onChange={(event) => setScheduledEnabled(event.target.checked)}
          />
          Automatically generate my daily brief at my briefing time above
        </label>
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          A scheduled brief uses the same evidence as your last sync — it never contacts Gmail or
          Calendar on its own. It never approves or executes anything: any suggested actions still
          wait for you in the approval inbox, exactly like a brief you generate yourself.
        </p>
        {evidenceFreshness ? (
          <div data-testid="settings-evidence-freshness" className="flex flex-col gap-1 text-sm">
            {evidenceFreshness.accounts.length === 0 ? (
              <p>No accounts connected yet — connect Google from Connections to add evidence.</p>
            ) : (
              evidenceFreshness.accounts.map((account) => (
                <p key={account.provider} data-testid={`evidence-freshness-${account.provider}`}>
                  {PROVIDER_LABELS[account.provider] ?? account.provider}
                  {": "}
                  {!account.connected ? "disconnected" : null}
                  {account.connected && account.sync_state === "never_synced"
                    ? "connected, never synced yet — sync from Connections to give the scheduled brief real evidence"
                    : null}
                  {account.last_synced_at
                    ? `${account.connected ? "" : "disconnected; "}last synced ${formatInTimezone(account.last_synced_at, scheduleStatus?.timezone ?? timezone)}${
                        account.freshness_band
                          ? ` (${FRESHNESS_LABELS[account.freshness_band]})`
                          : ""
                      }`
                    : null}
                </p>
              ))
            )}
          </div>
        ) : null}
        {scheduleStatus?.enabled ? (
          <div
            data-testid="settings-schedule-status"
            className="flex flex-col gap-1 rounded border border-current/20 px-3 py-2 text-sm"
          >
            {scheduleStatus.scheduler_available ? null : (
              <p role="status" data-testid="settings-schedule-unavailable">
                The scheduler is not currently reachable — scheduled briefs may be delayed until it
                is back.
              </p>
            )}
            {scheduleStatus.next_run_at ? (
              <p>
                Next scheduled brief:{" "}
                {formatInTimezone(scheduleStatus.next_run_at, scheduleStatus.timezone)}
              </p>
            ) : null}
            {scheduleStatus.latest_run_status ? (
              <p>
                Last scheduled run:{" "}
                {RUN_STATUS_LABELS[scheduleStatus.latest_run_status] ??
                  scheduleStatus.latest_run_status}
                {scheduleStatus.latest_run_completed_at
                  ? ` (${formatInTimezone(scheduleStatus.latest_run_completed_at, scheduleStatus.timezone)})`
                  : ""}
                {scheduleStatus.latest_brief_version
                  ? ` · brief version ${scheduleStatus.latest_brief_version}`
                  : ""}
              </p>
            ) : (
              <p>No scheduled brief has run yet.</p>
            )}
          </div>
        ) : null}
      </section>

      <section aria-labelledby="settings-sections" className="flex flex-col gap-3">
        <h2 id="settings-sections" className="text-xl font-medium">
          Brief sections
        </h2>
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          Choose which sections your brief shows. <strong>Needs attention</strong> is always shown —
          high-priority items can never be hidden. Hiding a section only changes the display:
          signals are still detected and any suggested actions still appear in the approval inbox.
        </p>
        {Object.entries(SECTION_LABELS).map(([key, label]) => (
          <label key={key} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              data-testid={`settings-section-${key}`}
              checked={sections.includes(key)}
              onChange={() => toggleSection(key)}
            />
            {label}
          </label>
        ))}
      </section>

      <section aria-labelledby="settings-memory" className="flex flex-col gap-3">
        <h2 id="settings-memory" className="text-xl font-medium">
          Learned preferences (memory)
        </h2>
        <div className="flex flex-col gap-1 text-sm text-neutral-600 dark:text-neutral-300">
          <p>
            LifeFlow can learn small preferences from actions you take here — like the sign-off you
            use when you edit and approve a draft reply. It learns <strong>only</strong> from your
            own deliberate actions inside LifeFlow.
          </p>
          <ul className="list-disc pl-5">
            <li>Content of emails you receive is never treated as your preference.</li>
            <li>Your explicit settings always take priority over anything learned.</li>
            <li>
              Inferred memory never approves or sends anything — you still review every draft.
            </li>
            <li>Deleting memory here does not delete anything in Gmail or Calendar.</li>
            <li>Pausing stops new learning; it does not delete what was already learned.</li>
          </ul>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            data-testid="settings-memory-enabled"
            checked={memoryEnabled}
            onChange={(event) => void toggleMemoryInference(event.target.checked)}
          />
          Let LifeFlow learn preferences from my actions here
        </label>

        {memories.length === 0 ? (
          <p
            data-testid="settings-memory-empty"
            className="text-sm text-neutral-600 dark:text-neutral-300"
          >
            Nothing learned yet.
            {memoryEnabled
              ? " Edit and approve a few draft replies with the same sign-off and it will appear here for review."
              : " Turn on learning above to let LifeFlow suggest preferences from your actions."}
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {memories.map((item) => (
              <li
                key={item.id}
                data-testid={`memory-item-${item.id}`}
                className="flex flex-col gap-2 rounded border border-current/20 px-3 py-2 text-sm"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium" data-testid={`memory-value-${item.id}`}>
                    Sign-off: “{String((item.value as { value?: string }).value ?? "")}”
                  </span>
                  <span
                    data-testid={`memory-status-${item.id}`}
                    className="text-neutral-600 dark:text-neutral-300"
                  >
                    {memoryStatusLabel(item)}
                  </span>
                </div>
                <p data-testid={`memory-explanation-${item.id}`}>{item.explanation}</p>
                <p className="text-neutral-600 dark:text-neutral-300">
                  Confidence: {BAND_LABELS[item.confidence_band] ?? item.confidence_band} (
                  {item.confidence.toFixed(2)}) · based on {item.evidence_count}{" "}
                  {item.evidence_count === 1 ? "action" : "actions"} you took
                  {item.last_observed_at
                    ? ` · last seen ${formatInTimezone(item.last_observed_at, timezone)}`
                    : ""}
                </p>

                {editingId === item.id ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="flex items-center gap-2">
                      <span className="sr-only">New sign-off</span>
                      <input
                        data-testid={`memory-edit-input-${item.id}`}
                        className="w-48 rounded border px-2 py-1"
                        value={editValue}
                        onChange={(event) => setEditValue(event.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      data-testid={`memory-save-${item.id}`}
                      onClick={() => saveEditedMemory(item)}
                      className="rounded bg-neutral-900 px-3 py-1 text-white dark:bg-white dark:text-neutral-900"
                    >
                      Save &amp; confirm
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(null);
                        setEditValue("");
                      }}
                      className="rounded border px-3 py-1"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {(item.status === "candidate" || item.status === "superseded") && (
                      <>
                        <button
                          type="button"
                          data-testid={`memory-confirm-${item.id}`}
                          onClick={() => confirmMemory(item)}
                          className="rounded bg-neutral-900 px-3 py-1 text-white dark:bg-white dark:text-neutral-900"
                        >
                          Use this sign-off
                        </button>
                        <button
                          type="button"
                          data-testid={`memory-edit-${item.id}`}
                          onClick={() => {
                            setEditingId(item.id);
                            setEditValue(String((item.value as { value?: string }).value ?? ""));
                          }}
                          className="rounded border px-3 py-1"
                        >
                          Edit &amp; confirm
                        </button>
                        <button
                          type="button"
                          data-testid={`memory-dismiss-${item.id}`}
                          onClick={() => dismissMemory(item)}
                          className="rounded border px-3 py-1"
                        >
                          Dismiss
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      data-testid={`memory-delete-${item.id}`}
                      onClick={() => deleteMemory(item)}
                      className="rounded border border-red-700/40 px-3 py-1 text-red-700 dark:text-red-400"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        {memories.length > 0 ? (
          <button
            type="button"
            data-testid="settings-memory-delete-all"
            onClick={deleteAllMemories}
            className="self-start rounded border border-red-700/40 px-3 py-1 text-sm text-red-700 dark:text-red-400"
          >
            Delete all inferred memory
          </button>
        ) : null}

        {memoryMessage ? (
          <p
            role="status"
            data-testid="settings-memory-message"
            className="text-sm text-green-700 dark:text-green-400"
          >
            {memoryMessage}
          </p>
        ) : null}
      </section>

      <div className="flex items-center gap-4">
        <button
          type="button"
          data-testid="settings-save"
          onClick={save}
          disabled={saving}
          className="rounded bg-neutral-900 px-4 py-2 text-sm text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
        >
          {saving ? "Saving…" : "Save settings"}
        </button>
        {message ? (
          <p role="status" className="text-sm text-green-700 dark:text-green-400">
            {message}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            {error}
          </p>
        ) : null}
      </div>
    </main>
  );
}
