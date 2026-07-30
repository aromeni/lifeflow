# Stage 11 — Facilitator Guide

**Status:** Planning document · **Date:** 2026-07-30

Companion: [task-protocol.md](task-protocol.md) · [observation-sheet.md](observation-sheet.md) · [safety-questionnaire.md](safety-questionnaire.md) · [post-session-questionnaire.md](post-session-questionnaire.md)

## Before the session

- Confirm the participant matches the target-user profile and no exclusion criterion applies (see [stage-11-plan.md](../../delivery/stage-11-plan.md) §2).
- Confirm demo mode is running against synthetic data only, with no real Google account connected.
- Have ready: participant-information.md (shared in advance), consent-form.md (signed at session start), task-protocol.md, observation-sheet.md, safety-questionnaire.md, post-session-questionnaire.md.
- Assign the participant ID per [data-governance.md](data-governance.md)'s convention before the session starts — never use the participant's name in any working document.

## Opening script (read to participant)

> "Thank you for taking part. Today I'll ask you to try out a demo of LifeFlow and think out loud as you go — tell me what you're looking at, what you expect to happen, and anything that confuses you. There are no wrong answers; if something doesn't make sense, that's useful information for us, not a failure on your part. Everything you see today is fictional demo data — no real email or calendar account of yours is involved. You can stop at any point. Do you have any questions before we start?"

Then complete the consent form ([consent-form.md](consent-form.md)) before proceeding.

## During the session

- Follow [task-protocol.md](task-protocol.md) in order; do not skip the safety-comprehension checks even if the participant appears to understand.
- Use minimal prompting. If a participant is stuck, wait, then use only the standard neutral prompts listed in task-protocol.md (e.g., "what would you try next?") — do not explain the feature to them, since that would invalidate the comprehension measurement.
- Record every intervention on the observation sheet, however small — "assistance required" is a scored field, not a facilitator judgement call to omit.
- If a participant demonstrates a P0-level safety misunderstanding (see [issue-register-template.md](issue-register-template.md)) or attempts an unsafe action pattern (e.g., blindly retrying an uncertain outcome), note it immediately and continue the session to completion — do not correct the participant mid-session, since later tasks may still yield useful data, but flag the finding for the P0 pause process in [stage-11-plan.md](../../delivery/stage-11-plan.md) §3 immediately after the session ends.
- Keep timing notes per task using a simple start/stop note, not exact-second precision.

## After each task

Ask the two standard follow-up questions before moving on:

1. "What did you expect to happen when you did that?"
2. "How confident are you that you understood what just happened?" (1–5)

## Closing the session

- Administer [safety-questionnaire.md](safety-questionnaire.md) and [post-session-questionnaire.md](post-session-questionnaire.md).
- Run the closing interview using the interview guide questions embedded in [findings-template.md](findings-template.md)'s qualitative-theme section.
- Remind the participant of the withdrawal window and contact details from participant-information.md.
- Thank the participant and end the session.

## Immediately after the session

- Transfer observation-sheet and questionnaire data into the session-summary format (see [findings-template.md](findings-template.md)) within the same day, while memory is fresh.
- Log any P0/P1/P2/P3 issue in [issue-register-template.md](issue-register-template.md).
- Store no participant-identifying information alongside session data beyond the participant ID, per [data-governance.md](data-governance.md).
