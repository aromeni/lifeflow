"use client";

import { useEffect, useState } from "react";

import { PipelineDiagram } from "@/components/ui/PipelineDiagram";
import { TryDemoButton } from "@/components/TryDemoButton";
import { API_URL, api } from "@/lib/api";
import type { PublicConfig } from "@/lib/types";

export default function Home() {
  // Fail closed: until (or unless) the API confirms Google sign-in is
  // actually authorised for this deployment (ADR 0003 D23; Stage 11A Phase
  // 6A.1), never render a button that could 404 or 409 — the initial/error
  // state is "not enabled". Deliberately reads only the sign-in capability,
  // never the provider-configured flag alone and never the connector-consent
  // flag — enabling connector consent must never make this button appear.
  const [googleSigninEnabled, setGoogleSigninEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api<PublicConfig>("/config")
      .then((config) => {
        if (!cancelled) setGoogleSigninEnabled(config.google_oidc_signin_enabled);
      })
      .catch(() => {
        // Network/API unavailable: stay in the fail-closed default above.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-12 sm:px-6 sm:py-16">
      <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start lg:gap-16">
        <div className="flex flex-col gap-8">
          <div className="flex flex-col gap-4">
            <p className="text-sm font-semibold tracking-wide text-accent uppercase">
              A personal operations agent
            </p>
            <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
              LifeFlow AI
            </h1>
            <p className="max-w-xl text-lg text-text-secondary">
              Quietly finds what needs attention across your Gmail and Calendar, explains why it
              matters with evidence, and prepares the next step — nothing is ever sent or changed
              without your explicit approval.
            </p>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <TryDemoButton />
            {googleSigninEnabled ? (
              <a
                href={`${API_URL}/auth/google/login`}
                data-testid="sign-in-with-google"
                className="inline-flex w-fit items-center justify-center rounded-md border border-border-strong px-5 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-surface-raised"
              >
                Sign in with Google
              </a>
            ) : (
              <p data-testid="google-sign-in-unavailable" className="text-sm text-text-tertiary">
                Google sign-in is not enabled in this environment (development only).
              </p>
            )}
          </div>

          <section
            aria-labelledby="accounts-heading"
            className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-5 text-sm shadow-xs"
          >
            <h2 id="accounts-heading" className="font-semibold text-foreground">
              Three separate things, never confused
            </h2>
            <ul className="flex flex-col gap-1.5 text-text-secondary">
              <li>
                <strong className="text-foreground">Sign in with Google</strong> only confirms who
                you are — it never reads your mail or calendar.
              </li>
              <li>
                <strong className="text-foreground">Connecting Gmail and Calendar</strong> is a
                separate, later step from the Connections screen, with its own consent screen and
                its own scopes. Disconnect any time.
              </li>
              <li>
                <strong className="text-foreground">Try demo</strong> uses entirely fictional data
                and needs no Google account at all.
              </li>
            </ul>
          </section>

          <section aria-labelledby="privacy-heading" className="flex flex-col gap-2 text-sm">
            <h2 id="privacy-heading" className="font-semibold text-foreground">
              How your data is handled
            </h2>
            <ul className="grid gap-x-6 gap-y-1.5 text-text-secondary sm:grid-cols-2">
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
        </div>

        <div className="lg:sticky lg:top-8">
          <PipelineDiagram />
        </div>
      </div>
    </main>
  );
}
