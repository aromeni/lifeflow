// Stage 9 Delivery Phase 4 (ADR 0005 D64/D81): the one shared way every page
// tells the user a request was throttled, never shown as a provider failure
// or an "uncertain" outcome. Retry-After is rounded to a friendly duration —
// never shown as a live countdown, so it can't invite tight polling.

function formatRetryAfter(seconds: number): string {
  if (seconds < 60) {
    return `about ${seconds} second${seconds === 1 ? "" : "s"}`;
  }
  const minutes = Math.round(seconds / 60);
  return `about ${minutes} minute${minutes === 1 ? "" : "s"}`;
}

export function rateLimitMessage(retryAfterSeconds: number): string {
  return `Too many requests. Try again in ${formatRetryAfter(retryAfterSeconds)}.`;
}

export function RateLimitNotice({ retryAfterSeconds }: { retryAfterSeconds: number }) {
  return (
    <p
      role="alert"
      data-testid="rate-limit-notice"
      className="rounded border border-current/30 px-3 py-2 text-sm"
    >
      {rateLimitMessage(retryAfterSeconds)}
    </p>
  );
}
