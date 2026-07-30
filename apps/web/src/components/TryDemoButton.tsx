"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
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
      <Button type="button" variant="primary" onClick={startDemo} disabled={status === "starting"}>
        {status === "starting" ? "Preparing your demo…" : "Try demo (no account needed)"}
      </Button>
      {/* Always mounted (not conditionally rendered) so screen readers that
          require a live region to exist before its content changes still
          announce this reliably — only the visible styling reacts to tone. */}
      <p
        aria-live="polite"
        className={status === "error" ? "text-sm text-danger-text" : "text-sm text-text-secondary"}
      >
        {message}
      </p>
    </div>
  );
}
