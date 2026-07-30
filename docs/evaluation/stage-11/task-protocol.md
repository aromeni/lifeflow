# Stage 11 — Participant Task Protocol

**Status:** Planning document, draft for Round 1, expected to be revised after Round 1 · **Date:** 2026-07-30

Companion: [facilitator-guide.md](facilitator-guide.md) · [observation-sheet.md](observation-sheet.md) · [product-hypotheses.md](product-hypotheses.md)

All tasks run against demo mode with synthetic data. No real Gmail or Calendar account is connected at any point.

For **every** task, the facilitator records on [observation-sheet.md](observation-sheet.md): success / partial success / failure; time taken; assistance required (and what kind); errors made; any unsafe misunderstanding observed; participant's stated confidence (1–5); a representative quote or observation; assigned severity if an issue was found; and the follow-up action, if any.

## T1 — Landing page comprehension

Show the landing page. Ask: "Without clicking anything yet, what do you think this product does?"
Neutral prompt if stuck: "What's your first impression?"
Maps to: P-H1, P-H4 (product-hypotheses.md).

## T2 — Onboarding

Ask the participant to complete onboarding using "Try demo."
Neutral prompt if stuck: "What would you try next?"
Maps to: U-H1.

## T3 — Permissions understanding

Ask: "Based on what you just saw, what is LifeFlow allowed to do with your Gmail and Calendar?"
Maps to: S-H1, S-H2 (early comprehension check, reinforced later by the safety questionnaire).

## T4 — Today summary interpretation

Ask the participant to look at the Today dashboard and summarise, in their own words, what it's telling them.
Maps to: V-H1.

## T5 — Identify the highest-priority item

Ask: "Which item here would you deal with first, and why?"
Record time to identification.
Maps to: U-H2, U-H3, V-H2.

## T6 — Explain why that item matters

Ask the participant to read the reason code / evidence shown and restate, in their own words, why the system ranked it highly.
Maps to: U-H3, V-H2.

## T7 — Inspect supporting evidence

Ask the participant to find and open the evidence behind the top item.
Maps to: U-H4, V-H2.

## T8 — Interpret a Waiting For item

Point to a Waiting For entry. Ask: "What does this mean, and what happens next?"
Maps to: V-H3.

## T9 — Review a proposed Gmail draft

Ask the participant to open a proposed draft and explain what they see.
Maps to: U-H5, V-H4, S-H1.

## T10 — Explain what approval will and will not do

Before approving, ask: "If you click approve right now, exactly what will happen?"
This is a safety-comprehension checkpoint, not a task-completion checkpoint — record the answer verbatim.
Maps to: U-H5, S-H4.

## T11 — Review a Calendar event proposal

Ask the participant to open a proposed calendar event and explain what they see, then ask the same "what happens if you approve" question as T10.
Maps to: V-H4, S-H2, S-H3.

## T12 — Reject or edit a proposal

Ask the participant to either reject a proposal or edit it before approving, participant's choice. Ask why they chose that action.
Maps to: V-H6.

## T13 — Interpret an uncertain execution outcome

Present the uncertain-execution-outcome UI state (per Stage 10's resilience fixtures). Ask: "What do you think happened, and what would you do next?"
Do not prompt toward retrying — observe whether the participant proposes an unsafe blind retry.
Maps to: S-H5 (behavioural safety observation, not just self-report).

## T14 — Respond to a temporary provider outage

Present the outage-notice UI state. Ask: "What does this mean for your data, and what would you do?"
Maps to: safety/outage-comprehension criterion in success-criteria.md.

## T15 — Inspect Audit History

Ask the participant to find the audit trail and explain what it shows. Ask: "Can you change anything from here?"
Maps to: V-H5, S-H8.

## T16 — Disconnect an account

Ask the participant to locate and explain (without necessarily completing) the account-disconnect control.
Maps to: U-H6.

## T17 — Distinguish disconnect from imported-data deletion

Ask: "If you disconnect your account, does that delete the emails and events LifeFlow already imported? What's the difference between disconnecting and deleting imported data?"
Maps to: U-H6, S-H6.

## T18 — Distinguish learned-preference deletion from account deletion

Show the memory/preferences control. Ask: "What's the difference between deleting a learned preference and deleting your whole account?"
Maps to: U-H6, S-H7.

## T19 — Locate and interpret the permanent account-deletion confirmation

Ask the participant to locate (without completing) the account-deletion flow and describe what the confirmation step tells them.
Maps to: U-H6, S-H7.

## T20 — Overall reflection

Ask: "Would you use this product? Why or why not?" followed by the standard post-session questionnaire ([post-session-questionnaire.md](post-session-questionnaire.md)).
Maps to: P-H1–P-H4, all V-H hypotheses.

## Round 1 → Round 2 revision rule

After Round 1, this document is revised only to fix a demonstrated defect in the script itself (ambiguous wording, a task that cannot be completed as written, a missing neutral prompt) — never to make a task easier to pass. Revisions are dated and logged at the bottom of this file.

## Revision log

- 2026-07-30 — Initial Round 1 draft. No revisions yet.
