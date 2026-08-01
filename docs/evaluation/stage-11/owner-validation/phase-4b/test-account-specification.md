# Dedicated Test-Account Specification

**Status:** Designed, not created · **Date:** 2026-08-01

Companion: [google-cloud-project-plan.md](google-cloud-project-plan.md) · [google-platform-requirements.md](google-platform-requirements.md) · [real-provider-data-boundary.md](real-provider-data-boundary.md)

This document specifies the minimum account set for Phase 4B and the eventual soak period. **Neither account is created by this task.**

## Account A — primary LifeFlow owner test account

**Purpose:** the account connected to LifeFlow; receives synthetic emails; contains synthetic calendar events; owns any Gmail drafts LifeFlow creates; owns any Calendar events LifeFlow inserts.

## Account B — synthetic correspondent and attendee

**Purpose:** sends fictional emails to Account A; receives fictional replies only when manually sent by the owner; appears as a synthetic meeting attendee where safe; enables realistic waiting-for, follow-up, and scheduling scenarios. **Account B is never connected to LifeFlow.**

## Prohibited account sources (either account)

Neither account may be: the owner's personal account; an existing business account; an academic account; a client account; a participant account; or an account containing any historical personal information. Both must be created fresh, specifically for this purpose.

## Naming rules

- Neutral naming: no use of the owner's full legal name where unnecessary. Suggested pattern: `lifeflow.test.a.<random-suffix>@gmail.com` / `lifeflow.test.b.<random-suffix>@gmail.com`, or an equivalent neutral, purpose-indicating local part.
- No reused local-part pattern from any other account the owner controls.

## Recovery-email policy

Recovery email, if set at all, must point to an address the owner controls that is itself not a primary personal inbox (e.g. a dedicated testing-programme alias), never to Account B (to avoid a circular recovery dependency between the two disposable accounts) and never to a real personal or business address that would tie the disposable account back to the owner's identity in a discoverable way beyond what account ownership already requires.

## Recovery-phone policy

A recovery phone number is optional per Google's own account-creation flow; where used, it should not be a number already associated with another account the owner controls, to keep the disposable accounts independently revocable/deletable without affecting other accounts. Where Google requires a phone number for account creation risk-scoring, that is accepted as an external constraint and recorded, not solved, here.

## Multi-factor authentication

Both accounts must have 2-Step Verification enabled once created, using an authenticator app or hardware key rather than SMS where practical, consistent with normal account-security hygiene — not a LifeFlow-specific requirement, but a baseline expectation for any account holding even synthetic OAuth-connected data.

## Password-manager requirement

Both accounts' credentials must be generated and stored only in the owner's existing password manager (never in a plaintext file, a chat transcript, a shared document, or this repository). No credential for either account may ever be pasted into an AI assistant conversation, a commit, an issue, or a screenshot.

## Account-ownership record

Maintained by the owner outside this repository (per [evidence-handling-plan.md](evidence-handling-plan.md)): which account is A vs. B, creation date, and the password-manager entry name — never the password or recovery details themselves.

## Account-purpose label

Each account's Google Account "About me" / display name should include a short marker (e.g. "LifeFlow disposable test account — do not use for real correspondence") so anyone who later encounters it (support staff, a shared password manager, an audit) can immediately identify its purpose and disposability.

## Creation date / planned deletion date

To be recorded at actual creation time (this task does not create either account). Per [test-account-cleanup-plan.md](test-account-cleanup-plan.md), both accounts are deleted at the end of the testing programme, not retained indefinitely.

## Data-classification label

Both accounts are classified **SYNTHETIC / DISPOSABLE — OWNER-ONLY TESTING**. No real, confidential, participant, or production data may ever be placed in either account (see [real-provider-data-boundary.md](real-provider-data-boundary.md)).

## Authorised users

The project owner only. No other person is authorised to access, log into, or receive credentials for either account.

## Prohibited uses

Neither account may be used for: real personal or business correspondence; storing or receiving real contacts; participant communication of any kind; any activity unrelated to LifeFlow testing; any activity that would make the account's continued existence matter beyond this testing programme (which would complicate clean deletion).

## Credential handling

Account credentials (passwords, recovery codes, 2FA secrets) must never enter Git, documentation, screenshots, logs, Slack, issue trackers, or chat transcripts — including this conversation. This specification intentionally contains no credential value of any kind, real or placeholder-shaped, for either account.
