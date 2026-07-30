# Stage 11 — Safety-Comprehension Questionnaire (template)

**Status:** Planning document · **Date:** 2026-07-30

Companion: [product-hypotheses.md](product-hypotheses.md) (safety hypotheses S-H1–S-H8) · [success-criteria.md](success-criteria.md)

Administered verbally or in writing at the end of the session, after all tasks. Answers are recorded verbatim where practical, then scored correct/incorrect against the answer key below. Critical items require 100% correct across all participants for a GO decision (see [go-no-go-template.md](go-no-go-template.md)); this is a hard safety gate, not an average.

## Questions

1. "If you approve a proposed email, what actually happens?" *(Critical — maps to S-H1)*
   Correct answer: a draft is created in Gmail; nothing is sent automatically.

2. "If you approve a proposed calendar action, could it ever change or delete an event that was already on your calendar?" *(Critical — maps to S-H2, S-H3)*
   Correct answer: no — approved calendar actions only create new events; existing events are never edited or deleted by LifeFlow.

3. "When you click approve, are you approving the general idea, or the exact text/details shown on screen?" *(Maps to S-H4)*
   Correct answer: the exact payload shown — if the details change, a fresh approval would be needed.

4. "If LifeFlow shows you an 'uncertain outcome' after an action, what's the safe thing to do?" *(Critical — maps to S-H5)*
   Correct answer: check the audit trail / status rather than immediately retrying, since a blind retry could risk a duplicate action.

5. "If you disconnect your Google account from LifeFlow, does that delete the emails and events it already imported?" *(Maps to S-H6)*
   Correct answer: no — disconnect and imported-data deletion are separate actions.

6. "If you delete a 'learned preference,' does that delete your account?" *(Maps to S-H7)*
   Correct answer: no — these are separate, and account deletion is a distinct, more permanent action.

7. "Can you take any action — approve, reject, edit — from the Audit History screen?" *(Critical — maps to S-H8)*
   Correct answer: no — Audit History is read-only.

## Scoring

Record each answer as Correct / Incorrect / Partially correct (with note) per participant. Any Incorrect answer on a critical item (Q1, Q2, Q4, Q7) is logged immediately as a P0 finding in [issue-register-template.md](issue-register-template.md) and triggers the evaluation-pause process in [stage-11-plan.md](../../delivery/stage-11-plan.md) §3.

| Participant ID | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Critical items all correct? |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |
