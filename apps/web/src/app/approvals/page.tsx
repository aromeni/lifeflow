"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ActionProposalPanel } from "@/components/ActionProposalPanel";
import { AppShell, PageHeader } from "@/components/ui/AppShell";
import { api, ApiError } from "@/lib/api";
import type { ActionProposal, ActionProposalList, Me } from "@/lib/types";

type LoadState = "loading" | "ready" | "unauthenticated" | "error";

// A real action must never be presented as simulated (independent-review
// blocker #4) — this header must stay in sync with each proposal's own
// execution_mode, not assume the whole inbox is simulated.
function executionSummary(proposals: ActionProposal[]): string {
  const count = proposals.length;
  const label = `${count} proposal${count === 1 ? "" : "s"}`;
  const realCount = proposals.filter((proposal) => proposal.execution_mode === "real").length;
  if (realCount === 0) {
    return `${label} · simulated execution only`;
  }
  return `${label} · ${realCount} will make a real change to your connected Google account if approved`;
}

export default function ApprovalsPage() {
  const [state, setState] = useState<LoadState>("loading");
  const [timezone, setTimezone] = useState("Europe/London");
  const [proposals, setProposals] = useState<ActionProposal[]>([]);

  const load = useCallback(async () => {
    try {
      const [me, inbox] = await Promise.all([
        api<Me>("/me"),
        api<ActionProposalList>("/action-proposals"),
      ]);
      setTimezone(me.timezone);
      setProposals(inbox.proposals);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiError && error.status === 401 ? "unauthenticated" : "error");
    }
  }, []);

  useEffect(() => {
    // State changes occur only after the external API promises settle.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  function replaceProposal(changed: ActionProposal) {
    setProposals((current) =>
      current.map((proposal) => (proposal.id === changed.id ? changed : proposal)),
    );
  }

  if (state === "unauthenticated") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16">
        <p>
          You are not signed in. <Link href="/">Start the demo</Link> first.
        </p>
      </main>
    );
  }

  let statusText = "";
  if (state === "loading") statusText = "Loading action proposals…";
  else if (state === "error") statusText = "Could not load action proposals. Is the API running?";
  else if (state === "ready") statusText = executionSummary(proposals);

  return (
    <AppShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
        <PageHeader
          title="Approval inbox"
          description={
            <>
              <span className="block">
                Review source evidence and every executor input. Nothing—including internal
                tasks—runs until you approve the exact action type, payload, and proposal version
                shown here.
              </span>
              <span aria-live="polite" className="mt-2 block font-medium text-foreground">
                {statusText}
              </span>
            </>
          }
        />

        {state === "ready" && proposals.length === 0 ? (
          <section className="rounded-lg border border-border bg-surface p-5 shadow-xs">
            <h2 className="font-semibold text-foreground">No proposals to review</h2>
            <p className="mt-1 text-text-secondary">
              Generate a brief first. Only grounded, policy-valid actions appear.
            </p>
          </section>
        ) : null}

        {state === "ready"
          ? proposals.map((proposal) => (
              <ActionProposalPanel
                key={proposal.id}
                proposal={proposal}
                timezone={timezone}
                onChanged={replaceProposal}
              />
            ))
          : null}
      </div>
    </AppShell>
  );
}
