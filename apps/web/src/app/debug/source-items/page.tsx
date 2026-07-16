"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { SourceItemList } from "@/lib/types";

// Developer/debug view: raw normalised source items. Deliberately not part of
// the main experience (Stage 3 requirement).
export default function DebugSourceItemsPage() {
  const [data, setData] = useState<SourceItemList | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<SourceItemList>("/source-items?limit=500")
      .then(setData)
      .catch(() => setError("Could not load source items (are you signed in?)."));
  }, []);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-4 px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">Debug: raw source items</h1>
      <p className="text-sm opacity-70">
        Developer view of normalised records.{" "}
        <Link href="/today" className="underline">
          Back to Today
        </Link>
      </p>
      <p aria-live="polite" className="text-sm text-red-600">
        {error}
      </p>
      {data && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Normalised source items</caption>
            <thead>
              <tr className="border-b border-current/20">
                <th scope="col" className="py-2 pr-4">
                  Type
                </th>
                <th scope="col" className="py-2 pr-4">
                  External id
                </th>
                <th scope="col" className="py-2 pr-4">
                  Title
                </th>
                <th scope="col" className="py-2 pr-4">
                  Sender/organiser
                </th>
                <th scope="col" className="py-2 pr-4">
                  Occurred (UTC)
                </th>
                <th scope="col" className="py-2">
                  Metadata
                </th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.id} className="border-b border-current/10 align-top">
                  <td className="py-2 pr-4">{item.source_type}</td>
                  <td className="py-2 pr-4 font-mono">{item.external_id}</td>
                  <td className="py-2 pr-4">{item.title}</td>
                  <td className="py-2 pr-4">{item.sender_or_organiser}</td>
                  <td className="py-2 pr-4 font-mono">{item.occurred_at}</td>
                  <td className="py-2 font-mono text-xs">{JSON.stringify(item.metadata)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
