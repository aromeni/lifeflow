"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";

const TIMEZONES = ["Europe/London", "Europe/Dublin", "Europe/Paris", "UTC"];
const SECTIONS = ["Needs attention", "Today & upcoming", "Waiting for", "Suggested actions"];

export default function OnboardingPage() {
  const router = useRouter();
  const [timezone, setTimezone] = useState("Europe/London");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function finish() {
    setSaving(true);
    setError("");
    try {
      await api("/me", {
        method: "PATCH",
        body: JSON.stringify({ timezone, onboarding_state: "complete" }),
      });
      router.push("/today");
    } catch (err) {
      setSaving(false);
      setError(err instanceof ApiError ? err.message : "Could not save your settings.");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center gap-8 px-6 py-16">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Set up your demo</h1>
        <p>
          LifeFlow only prepares actions — nothing is ever sent or changed without your explicit
          approval.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="timezone" className="font-medium">
          Your timezone
        </label>
        <select
          id="timezone"
          value={timezone}
          onChange={(event) => setTimezone(event.target.value)}
          className="w-fit rounded-md border border-current/30 bg-transparent px-3 py-2"
        >
          {TIMEZONES.map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </select>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="font-medium">Brief sections</legend>
        <p className="text-sm opacity-70">
          Your daily brief will include these sections (configurable in Settings from a later
          stage).
        </p>
        <ul className="list-disc pl-5 text-sm">
          {SECTIONS.map((section) => (
            <li key={section}>{section}</li>
          ))}
        </ul>
      </fieldset>

      <div className="flex flex-col gap-2">
        <button
          type="button"
          onClick={finish}
          disabled={saving}
          className="w-fit rounded-md bg-foreground px-5 py-2.5 font-medium text-background transition-opacity hover:opacity-85 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Finish and open Today"}
        </button>
        <p aria-live="polite" className="text-sm text-red-600">
          {error}
        </p>
      </div>
    </main>
  );
}
