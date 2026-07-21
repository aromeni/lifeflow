"use client";

import { useEffect, useState } from "react";

import { TryDemoButton } from "@/components/TryDemoButton";
import { API_URL, api } from "@/lib/api";
import type { PublicConfig } from "@/lib/types";

export default function Home() {
  // Fail closed: until (or unless) the API confirms Google sign-in is
  // actually wired for this deployment (ADR 0003 D23), never render a
  // button that could 404 — the initial/error state is "not enabled".
  const [googleOAuthEnabled, setGoogleOAuthEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api<PublicConfig>("/config")
      .then((config) => {
        if (!cancelled) setGoogleOAuthEnabled(config.google_oauth_enabled);
      })
      .catch(() => {
        // Network/API unavailable: stay in the fail-closed default above.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center gap-8 px-6 py-16">
      <div className="flex flex-col gap-4">
        <h1 className="text-4xl font-semibold tracking-tight">LifeFlow AI</h1>
        <p className="text-lg">
          Quietly finds what needs attention, explains why it matters, and prepares the next step —
          for your approval.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        {googleOAuthEnabled ? (
          <a
            href={`${API_URL}/auth/google/login`}
            data-testid="sign-in-with-google"
            className="w-fit rounded-md border border-current/30 px-5 py-2.5 font-medium transition-opacity hover:opacity-85"
          >
            Sign in with Google
          </a>
        ) : (
          <p data-testid="google-sign-in-unavailable" className="text-sm opacity-60">
            Google sign-in is not enabled in this environment (development only).
          </p>
        )}
        <TryDemoButton />
      </div>

      <section aria-labelledby="accounts-heading" className="flex flex-col gap-2 text-sm">
        <h2 id="accounts-heading" className="font-medium">
          Three separate things, never confused
        </h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong>Sign in with Google</strong> only confirms who you are — it never reads your
            mail or calendar.
          </li>
          <li>
            <strong>Connecting Gmail and Calendar</strong> is a separate, later step from the
            Connections screen, with its own consent screen and its own scopes. Disconnect any time.
          </li>
          <li>
            <strong>Try demo</strong> uses entirely fictional data and needs no Google account at
            all.
          </li>
        </ul>
      </section>

      <section aria-labelledby="privacy-heading" className="flex flex-col gap-2 text-sm">
        <h2 id="privacy-heading" className="font-medium">
          How your data is handled
        </h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>Reads only a recent window you authorise.</li>
          <li>Never sends email — full stop.</li>
          <li>Creates a Gmail draft only after you approve its exact contents.</li>
          <li>Creates a new calendar event only after you approve its exact details.</li>
          <li>Never notifies guests or anyone else when creating an event.</li>
          <li>Never modifies or deletes an existing calendar event.</li>
          <li>Disconnect and delete your imported data at any time.</li>
          <li>A full audit trail records everything it observes and does.</li>
        </ul>
      </section>
    </main>
  );
}
