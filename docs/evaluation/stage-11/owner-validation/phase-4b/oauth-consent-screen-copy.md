# OAuth Consent-Screen Copy (Proposed, Factual)

**Status:** Draft wording only; not configured anywhere · **Date:** 2026-08-01

Companion: [google-cloud-project-plan.md](google-cloud-project-plan.md) · [oauth-scope-matrix.md](oauth-scope-matrix.md)

These are proposed values for the future dedicated Google Cloud project's OAuth consent screen. No consent screen exists yet — nothing here has been configured, submitted, or reviewed by Google.

| Field | Proposed value |
|---|---|
| Application name | "LifeFlow AI (Owner Testing)" |
| User-support email | *(the owner's own monitored address — a placeholder, not filled in here since no project exists)* |
| Developer-contact email | *(same as support email for a single-owner testing project)* |
| Application description | "A personal operations assistant, currently in disposable-account owner testing. Reads recent Gmail and Calendar data to prepare a daily summary and propose draft actions; every action requires explicit approval before it is taken." |
| Privacy-policy URL | *(the repository's existing draft privacy notice, once a stable public URL exists — not yet published; left as a placeholder)* |
| Terms-of-service URL | *(not required for Testing-status External apps with fewer than 100 test users per current Google requirements; left blank unless Google's own flow requires it)* |
| Authorised domain | *(not applicable — no custom domain is used; redirect URIs are `localhost`-only per [redirect-uri-and-origin-plan.md](redirect-uri-and-origin-plan.md))* |

## Scope justifications (shown to Google, and to test users on the consent screen)

- `gmail.readonly` — "Read recent email metadata and content to identify deadlines, requests, and follow-ups for the daily summary."
- `gmail.compose` — "Create draft replies for the user to review and send manually; LifeFlow never sends email on its own."
- `calendar.readonly` — "Read upcoming calendar events to identify meetings, preparation needs, and scheduling conflicts."
- `calendar.events` — "Add new calendar events the user has explicitly approved; LifeFlow never edits or deletes existing events."

## What this copy must never claim

- **Google verification.** No verification has been requested or granted.
- **Google approval.** Google has not reviewed this application in any capacity.
- **Production status.** The consent screen's publishing status is, and will remain through Phase 4B and the eventual soak period, **Testing**.
- **Legal certification.** No claim of GDPR, SOC2, or any other compliance certification is made anywhere in this copy.
- **External-user readiness.** This application is not ready for, and does not request, general external users.

## Required environment statement

Every version of this copy, wherever it is eventually configured or referenced, must state or otherwise make clear that the current environment is:

**OWNER-ONLY DISPOSABLE-ACCOUNT TESTING**

not a production service, not available to the public, and not evaluated by any participant.
