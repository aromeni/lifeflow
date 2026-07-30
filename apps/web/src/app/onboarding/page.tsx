"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { api, ApiError } from "@/lib/api";

const TIMEZONES = ["Europe/London", "Europe/Dublin", "Europe/Paris", "UTC"];
const SECTIONS = ["Needs attention", "Today & upcoming", "Waiting for", "Suggested actions"];

const STEPS = ["Your schedule", "What you'll see"] as const;

function StepIndicator({ current }: { current: number }) {
  return (
    <ol aria-label="Setup progress" className="flex items-center gap-3">
      {STEPS.map((label, index) => {
        const stepNumber = index + 1;
        const state = stepNumber < current ? "done" : stepNumber === current ? "current" : "todo";
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              aria-current={state === "current" ? "step" : undefined}
              className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                state === "todo"
                  ? "border border-border-strong text-text-tertiary"
                  : "bg-accent text-white"
              }`}
            >
              {state === "done" ? "✓" : stepNumber}
            </span>
            <span
              className={`text-sm ${state === "todo" ? "text-text-tertiary" : "font-medium text-foreground"}`}
            >
              {label}
            </span>
            {index < STEPS.length - 1 ? (
              <span aria-hidden="true" className="h-px w-8 bg-border-strong" />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
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
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center gap-8 px-4 py-16 sm:px-6">
      <div className="flex flex-col gap-6 rounded-lg border border-border bg-surface p-6 shadow-sm sm:p-8">
        <StepIndicator current={step} />

        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {step === 1 ? "Set up your demo" : "Before your first brief"}
          </h1>
          <p className="text-sm text-text-secondary">
            LifeFlow only prepares actions — nothing is ever sent or changed without your explicit
            approval.
          </p>
        </div>

        {step === 1 ? (
          <div className="flex flex-col gap-2">
            <label htmlFor="timezone" className="text-sm font-medium text-foreground">
              Your timezone
            </label>
            <select
              id="timezone"
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              className="w-fit rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-foreground"
            >
              {TIMEZONES.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-medium text-foreground">Brief sections</legend>
              <p className="text-sm text-text-secondary">
                Your daily brief will include these sections (configurable in Settings from a later
                stage).
              </p>
              <ul className="flex flex-col gap-1 text-sm text-text-secondary">
                {SECTIONS.map((section) => (
                  <li key={section} className="flex items-center gap-2">
                    <span aria-hidden="true" className="size-1.5 rounded-full bg-accent" />
                    {section}
                  </li>
                ))}
              </ul>
            </fieldset>

            <Notice tone="info" role="status">
              <ul className="flex flex-col gap-1">
                <li>
                  Gmail actions only ever create a <strong>draft</strong> — never sent.
                </li>
                <li>
                  Calendar actions only ever create a <strong>new event</strong> — never edited or
                  deleted.
                </li>
                <li>
                  You can disconnect and delete your data any time from Privacy &amp; Connections.
                </li>
              </ul>
            </Notice>
          </div>
        )}

        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            {step === 2 ? (
              <Button type="button" variant="secondary" onClick={() => setStep(1)}>
                Back
              </Button>
            ) : null}
            {step === 1 ? (
              <Button type="button" variant="primary" onClick={() => setStep(2)}>
                Continue
              </Button>
            ) : (
              <Button type="button" variant="primary" onClick={finish} disabled={saving}>
                {saving ? "Saving…" : "Finish and open Today"}
              </Button>
            )}
          </div>
          {error ? (
            <Notice tone="danger" role="alert">
              {error}
            </Notice>
          ) : null}
        </div>
      </div>
    </main>
  );
}
