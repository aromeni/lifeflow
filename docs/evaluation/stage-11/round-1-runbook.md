# Stage 11 — Round 1 Operational Runbook

**Status:** Planning document, not yet executed · **Date:** 2026-07-30

Companion: [facilitator-guide.md](facilitator-guide.md) · [task-protocol.md](task-protocol.md) · [recruitment-authorisation-checklist.md](recruitment-authorisation-checklist.md) · [round-1-evidence-register.md](round-1-evidence-register.md)

This runbook governs how a Round 1 session is actually run, once — and only once — [recruitment-authorisation-checklist.md](recruitment-authorisation-checklist.md) shows every applicable item satisfied. Running this runbook against a real participant before that point is not authorised by this document.

## Before each session

- Verify [recruitment-authorisation-checklist.md](recruitment-authorisation-checklist.md) is fully satisfied for this participant and this round.
- Assign the next pseudonymous participant ID (`P-R1-0N`) per [data-governance.md](data-governance.md) — never reuse an ID, never use a name.
- Start the deterministic local demo (`./scripts/demo.sh` or the documented demo-mode startup) — confirm it is running against synthetic data, not any real-account configuration.
- Verify synthetic fixtures are in their expected initial state (see [synthetic-scenario-manifest.md](synthetic-scenario-manifest.md)): demo dataset v1 loaded, no prior session's approvals/rejections/deletions carried over.
- Clear prior session state (reset the demo database/seed) so each participant sees an identical starting point.
- Confirm no real credentials are configured anywhere in the running environment (no `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`ANTHROPIC_API_KEY` pointing at a live account needed for demo mode).
- Prepare [observation-sheet.md](observation-sheet.md), [safety-questionnaire.md](safety-questionnaire.md), and [post-session-questionnaire.md](post-session-questionnaire.md) copies for this participant ID.
- Re-read the withdrawal procedure and the emergency-stop conditions (this document, §Emergency stop) immediately before the session.

## Opening

- Confirm the participant received and read the participant information sheet in advance.
- Confirm the participation process: what will happen, how long it will take, what will be recorded.
- Explain voluntary participation and the right to withdraw at any point, with no consequence.
- Confirm explicitly whether notes are being taken (yes, by default) and that no recording is happening unless a separate, specific consent for recording was obtained (it is not, by default — see [data-governance.md](data-governance.md)).
- State plainly: "we are evaluating the product, not you — there are no wrong answers."
- Do not coach the participant on how the product is supposed to work before or during tasks — that would invalidate the comprehension measurement this evaluation exists to produce.

## During

- Follow [task-protocol.md](task-protocol.md)'s 20 tasks in order.
- Use only the standard neutral prompts defined in [facilitator-guide.md](facilitator-guide.md) — do not improvise explanations of product behaviour.
- Record assistance consistently on the observation sheet for every task, including "none needed."
- Log any unsafe misunderstanding immediately, not retrospectively from memory after the session.
- If a P0-level safety misunderstanding is observed (per [issue-register-template.md](issue-register-template.md)), continue the session to completion (later tasks may still be informative) but flag it for the evaluation-pause process in [stage-11-plan.md](../../delivery/stage-11-plan.md) §3 immediately afterward.
- Do not request real email, calendar, or account information from the participant at any point, including casually ("what does your real inbox look like?").
- Do not improvise new personal-data questions beyond what [participant-screener.md](participant-screener.md), [safety-questionnaire.md](safety-questionnaire.md), and [post-session-questionnaire.md](post-session-questionnaire.md) already specify.

## After

- Administer [safety-questionnaire.md](safety-questionnaire.md).
- Administer [post-session-questionnaire.md](post-session-questionnaire.md).
- Offer withdrawal instructions again, including the deadline, before the participant leaves.
- Verify all records for this session use only the participant ID — check no name, email, or other identifier leaked into free-text fields.
- Record any incident (per the emergency-stop conditions below) in the incident log referenced by [round-1-evidence-register.md](round-1-evidence-register.md).
- Classify any findings into [issue-register-template.md](issue-register-template.md) with a severity.
- Transfer records to the facilitator-controlled storage location outside this repository (see [data-governance.md](data-governance.md)) — never commit them here.
- Destroy any temporary paper or scratch notes once transferred, if the retention plan calls for it.
- Reset the demo environment to a clean state before the next session.

## Emergency stop

The session stops immediately, and is not resumed without the responsible owner's review, if any of the following occurs:

- **Participant distress** — the participant appears upset, anxious, or otherwise negatively affected by the session.
- **Accidental disclosure of real personal data** — the participant reveals real email content, real calendar details, or other real personal data (their own or a third party's), whether or not asked for.
- **Unsafe product misunderstanding observed live** — a participant appears about to act (outside the demo) based on a dangerous misunderstanding of what the product does.
- **Cross-user exposure** — any indication that one participant's session data or fixture state is visible to or affects another participant.
- **Consent or withdrawal concern** — the participant expresses doubt about having agreed to something, or an ambiguous statement about wanting to stop.
- **Recording failure** — any unintended or unauthorised audio/video/screen capture is discovered.
- **Security incident** — any sign of unauthorised access to session data, the demo environment, or facilitator systems.

On any emergency stop: end the session respectfully, do not attempt to complete remaining tasks, record what happened factually (not interpreted) in the incident log, and notify the responsible owner before scheduling any further session.
