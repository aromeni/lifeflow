"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { DemoStart } from "@/lib/types";

export function TryDemoButton() {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "starting" | "error">("idle");
  const [message, setMessage] = useState("");

  async function startDemo() {
    setStatus("starting");
    try {
      await api("/auth/dev-login", { method: "POST", body: "{}" });
      const summary = await api<DemoStart>("/demo/start", { method: "POST" });
      setMessage(`Imported ${summary.imported + summary.skipped} items.`);
      router.push("/onboarding");
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof ApiError
          ? `Could not start the demo (${error.code}). Is the API running on port 8010?`
          : "Could not reach the API. Start it with scripts/demo.sh.",
      );
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={startDemo}
        disabled={status === "starting"}
        className="w-fit rounded-md bg-foreground px-5 py-2.5 font-medium text-background transition-opacity hover:opacity-85 disabled:opacity-50"
      >
        {status === "starting" ? "Preparing your demo…" : "Try demo (no account needed)"}
      </button>
      <p aria-live="polite" className={status === "error" ? "text-sm text-red-600" : "text-sm"}>
        {message}
      </p>
    </div>
  );
}
