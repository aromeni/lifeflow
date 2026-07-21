"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ActionProposalPanel } from "@/components/ActionProposalPanel";
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

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-3">
        <Link href="/today" className="text-sm underline">
          ← Back to Today
        </Link>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Approval inbox</h1>
          <p className="mt-2 max-w-2xl">
            Review source evidence and every executor input. Nothing—including internal tasks—runs
            until you approve the exact action type, payload, and proposal version shown here.
          </p>
        </div>
        <p aria-live="polite" className="text-sm opacity-70">
          {state === "loading" && "Loading action proposals…"}
          {state === "error" && "Could not load action proposals. Is the API running?"}
          {state === "ready" && executionSummary(proposals)}
        </p>
      </header>

      {state === "ready" && proposals.length === 0 ? (
        <section className="rounded-lg border border-current/25 p-5">
          <h2 className="font-semibold">No proposals to review</h2>
          <p className="mt-1">
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
    </main>
  );
}
