# Stage 11A Phase 4C — Disposable Google Test Environment Creation

**Status:** In execution · **Date:** 2026-08-01

Companion: [Phase 4C evidence pack](../evaluation/stage-11/owner-validation/phase-4c/) · [Phase 4B plan](stage-11a-phase-4b-plan.md) · [Engineering Acceptance Contract](engineering-acceptance-contract.md)

## Objective

> Create a dedicated, disposable and securely isolated Google test environment for LifeFlow while keeping OAuth consent, provider connection, token storage and Google API access completely blocked.

## Authorised scope

- Create two new owner-controlled disposable Google accounts, labelled only `ACCOUNT_A` and `ACCOUNT_B` in repository evidence.
- Create one dedicated Google Cloud project, labelled only `LIFEFLOW_TEST_PROJECT` in repository evidence.
- Enable only Gmail API and Google Calendar API.
- Configure an External Google Auth Platform audience in Testing status.
- Add `ACCOUNT_A` as the sole Phase 4C OAuth test user.
- Configure exactly the four approved connector scopes.
- Create one web-application OAuth client, labelled only `LIFEFLOW_TEST_OAUTH_CLIENT`.
- Install that client's configuration in the existing ignored local `.env`, with presence-only validation.
- Add and prove a default-deny application guard that prevents Google OAuth initiation and callback processing during Phase 4C.
- Run repository, security, evaluation, boundary, commit, push, pull-request, and required-check work specified by the phase instruction.

## Prohibited scope

Phase 4C must not:

- start or complete Google OAuth consent;
- connect a Google account to LifeFlow;
- receive, store, refresh, revoke, or display an OAuth token or authorisation code;
- call a Gmail or Calendar API through LifeFlow;
- import Google data or create a Gmail draft/Calendar event through Google;
- use any existing personal, business, academic, client, or participant account/project;
- start or choose the soak-period option;
- recruit/contact participants or begin participant evaluation;
- deploy production or begin Stage 12;
- mark Stage 11A complete, merge, or create a Stage 11/11A tag.

## Owner-operated actions

The owner alone operates Google Account and Cloud Console UI, chooses and stores passwords/recovery/MFA data, records real identifiers outside Git, and downloads/copies the OAuth client secret directly into the local secret mechanism. Owner confirmations are content-free. Codex never requests an account address, password, recovery detail, MFA value, project identifier, client identifier/secret, authorisation code, access/refresh token, session cookie, or screenshot containing one.

## Codex-operated actions

Codex inspects and changes the repository, maintains the acceptance matrix/evidence, provides one exact owner action at each checkpoint, performs official-source research, adds the OAuth-initiation block, runs local tests/validators/scans, performs presence-only local configuration validation, creates commits, pushes only the Phase 4C branch, opens a pull request, waits for checks, and stops without merge/tag/OAuth.

## Account-creation sequence

1. Install and verify the repository-level OAuth-initiation block before any Google action.
2. Give the owner the exact `ACCOUNT_A` creation checklist and wait only for `ACCOUNT A CREATED — MFA STATUS RECORDED OUTSIDE GIT`.
3. Record only the content-free state.
4. Give the owner the exact `ACCOUNT_B` creation checklist and wait only for `ACCOUNT B CREATED — MFA STATUS RECORDED OUTSIDE GIT`.
5. Record only the content-free state.

Both accounts are new, neutral, owner-only, password-manager protected, isolated from existing accounts, devoid of historical/real/confidential data, contacts, forwarding, and personal imagery, and use MFA when Google permits it. `ACCOUNT_B` remains a synthetic correspondent/attendee and is never connected during the first connection test.

## Cloud-project sequence

1. Owner creates one neutral, dedicated, non-production project using an owner-controlled identity.
2. Owner adds no unnecessary collaborator or service account and deliberately enables no paid product or billing attachment.
3. If Google presents an unexpected paid prerequisite: `STOP — OWNER DECISION REQUIRED`.
4. Owner confirms only `DEDICATED GOOGLE CLOUD PROJECT CREATED`.
5. Owner enables Gmail API, confirms only `GMAIL API ENABLED`, then enables Google Calendar API, confirms only `CALENDAR API ENABLED`.
6. No unrelated API is enabled and no project identifier enters Git/chat.

## OAuth-configuration sequence

1. Configure Google Auth Platform Branding with application name `LifeFlow AI (Owner Testing)`, truthful approved copy, and owner-entered monitored support/developer contact details.
2. Configure the Audience as External and keep publishing status Testing.
3. Add `ACCOUNT_A` only as a test user. `ACCOUNT_B` is not added in Phase 4C.
4. Add exactly the four scope strings in the approved scope matrix. If any unexpected scope appears: `EMERGENCY STOP — DO NOT SAVE`.
5. Create exactly one private web-application client. This current phase instruction supersedes Phase 4B's earlier two-physical-client plan. The one physical client carries the implementation's two exact server callbacks:
   - `http://localhost:8010/auth/google/callback`
   - `http://localhost:8010/connected-accounts/google/callback`
6. Configure no wildcard, alternate, public, personal-development, or production callback. No authorised JavaScript origin is required because LifeFlow's browser does not call Google APIs directly; if the current Console unexpectedly requires one, stop for an owner decision rather than adding one speculatively.
7. Owner confirms only the exact content-free strings specified in the phase checkpoints.

The implementation retains two logical configurations so the OIDC identity request (`openid email profile`) and connector data request (the four approved scopes) remain separate flows with separate routes, state purpose, and redirect URI. For Phase 4C's one physical web client, the owner installs the same physical client values into both logical client field pairs; the flows remain scope- and state-separated even though their Phase 4C client credential is shared.

## Approved scope checklist

| Exact scope | LifeFlow operation | Current Google classification | Application-level restriction |
|---|---|---|---|
| `https://www.googleapis.com/auth/gmail.readonly` | Bounded Gmail message/history reads for ingestion | Restricted | Narrow Gmail read-path allowlist plus bounded ingestion/retention |
| `https://www.googleapis.com/auth/gmail.compose` | Create a Gmail draft after exact approval | Restricted | No send action/method/path; write allowlist is `drafts` only |
| `https://www.googleapis.com/auth/calendar.readonly` | Read events for ingestion/conflict evidence | Sensitive | Bounded ingestion/retention; no write through this scope |
| `https://www.googleapis.com/auth/calendar.events` | Insert a new event after exact approval | Sensitive | No update/patch/delete method; `sendUpdates=none` |

The Gmail and Calendar classifications were rechecked on official Google sources on 2026-08-01. Google exposes broader provider permissions than LifeFlow's product contract; the closed client/action surfaces remain the controlling boundary.

## Local-secret installation

The approved local mechanism is the repository-root `.env`, already ignored by Git and loaded by `Settings` from an absolute repository-relative path. The owner directly replaces the existing pre-Phase-4C local Google client configuration; Codex does not inspect, print, copy, or type any value. Required fields are:

- `GOOGLE_OIDC_CLIENT_ID`
- `GOOGLE_OIDC_CLIENT_SECRET`
- `GOOGLE_OIDC_REDIRECT_URI`
- `GOOGLE_CONNECTOR_CLIENT_ID`
- `GOOGLE_CONNECTOR_CLIENT_SECRET`
- `GOOGLE_CONNECTOR_REDIRECT_URI`
- `GOOGLE_OAUTH_ENABLED=true`
- `GOOGLE_OAUTH_INITIATION_ENABLED=false` *(superseded 2026-08-05 by Stage 11A Phase 6A — see that ADR 0003 addendum: this single flag is replaced by two independent flags, `GOOGLE_OIDC_SIGNIN_ENABLED`/`GOOGLE_CONNECTOR_OAUTH_ENABLED`, both false by default, after a real incident showed the shared flag armed both OAuth flows at once)*

Validation reports configured/unset and approved/unapproved states only. It never reports value length, prefix, suffix, project/client identifiers, or secret material. `.env.example` contains safe placeholders and the block remains false by default.

## Owner-only operator record

The owner maintains this record in a password manager secure note or other owner-only store outside the repository:

- `ACCOUNT_A` actual address, creation date, purpose, planned deletion date, MFA yes/no, recovery configured yes/no;
- `ACCOUNT_B` actual address, creation date, purpose, planned deletion date, MFA yes/no, recovery configured yes/no;
- `LIFEFLOW_TEST_PROJECT` project ID, project number, creation date, purpose, planned deletion date;
- `LIFEFLOW_TEST_OAUTH_CLIENT` client ID, creation date, local secret-file location;
- Account A test-user status;
- cleanup status for each object.

Passwords, recovery values, MFA secrets/codes, backup codes, OAuth client secret, tokens, and authorisation codes are never copied into this record's repository-facing evidence or the task conversation.

## Verification requirements

- Official Google requirements are freshly rechecked and dated, with Phase 4B evidence retained as the minimum baseline.
- The OAuth-initiation block returns safe operator-facing guidance for both initiation routes and refuses both callback routes before state consumption/code exchange.
- Demo/synthetic mode remains functional.
- Local configuration parses without initiating OAuth.
- Credential gate: zero stored, unversioned, legacy-known, legacy-unknown, and missing-key credential fields; `clear_to_connect=true`.
- One Alembic head at migration `0012`; active v2 key ring valid.
- Dangerous test controls are disabled; no-live-network and production guards pass.
- Logs, fake-provider state, database, Redis, browser storage, and Audit History contain no Phase 4C OAuth/provider activity or secret residue.
- All automated, evaluation, security, exact-boundary, commit, PR, and remote-check gates in the acceptance matrix pass.

## Emergency-stop rules

Stop immediately on an unexpected scope, wrong/personal account or project, real data/import/synchronisation, secret/identifier leakage, token/code creation, OAuth initiation/callback, Google API traffic, blocked credential gate, active unsafe test control, unexpected paid commitment, redirect mismatch, non-Testing publishing status, or unauthorised test user. Preserve only content-free evidence, classify the event in the defect register, remediate before closure, and never continue an external checkpoint merely to finish the sequence.

The existing non-placeholder local Google configuration found at the starting boundary is treated as finding `F-P4C-01`; it is never displayed or silently reused. Repository-level OAuth initiation is blocked before the first owner action, and the owner later replaces the values directly during the approved local-install checkpoint.

## Evidence rules

- Use content-free confirmations and written state summaries.
- Repository evidence contains labels and safe counts/statuses only.
- No raw screenshots, logs, database/Redis dumps, browser traces, HAR files, callback URLs, absolute local paths, or provider/private content are committed.
- Every automated claim cites a current-boundary command/result; external Google state requires the exact owner confirmation and safe independent verification where possible.
- Historical Stage 7 activity and Phase 4B's rejected unauthenticated outbound attempt remain accurately recorded; Phase 4C reports zero activity for this phase/environment, never a false lifetime-zero claim.

## Cleanup rules

At programme end, revoke/delete OAuth credentials, delete the dedicated Cloud project, delete both disposable accounts, remove local client configuration, confirm zero stored tokens/credential rows and zero residual secrets, and mark the owner-only record's cleanup statuses. Phase 4C prepares but does not execute programme-end cleanup.

## Seven-day constraint

Testing status permits up to 100 named test users, and non-identity authorisations/refresh tokens expire after seven days. Phase 4C chooses neither Option A (Testing-status reauthorisation) nor Option B (separately reviewed production publishing). `SOAK PERIOD REMAINS BLOCKED`. This constraint does not block environment creation or a later separately authorised first controlled connection.

## Exit decision

Exactly one verdict is recorded:

- `PASS — READY FOR FIRST OAUTH CONNECTION AUTHORISATION` only if every mandatory repository and owner checkpoint is verified, OAuth initiation remains blocked, zero credentials/tokens/API interactions exist, and every required check is green;
- `CONDITIONAL PASS` only for an explicit non-safety P2 allowed by the phase specification; or
- `FAIL — ENVIRONMENT OR CONNECTION REMAINS BLOCKED` for any listed safety failure.

Even PASS does not authorise OAuth. The next owner decision is limited to the exact wording defined by the Phase 4C instruction.
