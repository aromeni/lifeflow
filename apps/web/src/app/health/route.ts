import { NextResponse } from "next/server";

// Liveness endpoint for the web app, mirroring the API's /health.
export function GET(): NextResponse {
  return NextResponse.json({ status: "ok" });
}
