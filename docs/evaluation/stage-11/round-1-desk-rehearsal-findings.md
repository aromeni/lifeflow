# Stage 11 — Round 1 Desk-Based Protocol Rehearsal Findings

**Status:** Rehearsal complete — no participant session was run · **Date:** 2026-07-30

Companion: [task-protocol.md](task-protocol.md) · [facilitator-guide.md](facilitator-guide.md) · [safety-questionnaire.md](safety-questionnaire.md) · [success-criteria.md](success-criteria.md)

**This rehearsal used no participant.** It is a structured desk review conducted by re-reading every Round 1 material end to end and, separately, an automated/researcher-operated walkthrough of the underlying fixtures (the demo dataset and the two Stage 10 resilience specs, re-run and confirmed passing — see the Stage 11 Round 1 readiness report's verification section). Nothing here is participant evidence and must never be treated as such in [findings-template.md](findings-template.md).

## Scope reviewed

All 20 tasks ([task-protocol.md](task-protocol.md)), facilitator instructions ([facilitator-guide.md](facilitator-guide.md)), observation fields ([observation-sheet.md](observation-sheet.md)), safety questions ([safety-questionnaire.md](safety-questionnaire.md)), the post-session questionnaire ([post-session-questionnaire.md](post-session-questionnaire.md)), issue logging ([issue-register-template.md](issue-register-template.md)), GO/NO-GO threshold traceability ([success-criteria.md](success-criteria.md), [go-no-go-template.md](go-no-go-template.md)), the demo reset process, the outage fixture, the uncertain-execution fixture, and the four deletion/disconnect distinctions (T16–T19).

## Defects found and corrected

| # | Category | Finding | Fix applied |
|---|---|---|---|
| 1 | Inconsistent scoring | `success-criteria.md`'s "Priority relevance" and "Proposed-action usefulness" rows specified a "%" threshold, but the only instrument measuring them ([post-session-questionnaire.md](post-session-questionnaire.md) Q2/Q4) is a 1–5 Likert rating with no stated conversion rule — the threshold and the instrument could not agree on what counts as a pass | Added a footnote to `success-criteria.md` defining "agreeing"/"useful" as a rating ≥ 4/5; no threshold *value* changed, only the missing conversion rule |
| 2 | Leading question | `safety-questionnaire.md` Q2 was phrased as a yes/no question ("...could it ever change or delete...") that hinted at "no" as the expected answer | Rephrased to an open form ("What could happen to the events already on your calendar if you approve...") that doesn't presuppose the answer shape |
| 3 | Excessive session length (underestimated) | `participant-information.md` stated "45–60 minutes," but summing realistic per-task time for 20 tasks plus the safety questionnaire (7 items), post-session questionnaire (7 ratings + 10-item SUS + 4 open questions), and closing interview plausibly exceeds that window | Revised the stated duration to "60–75 minutes," explicitly labelled as a rehearsal estimate pending actual Round 1 timing data |
| 4 | Facilitator-bias risk / ambiguous instructions | `task-protocol.md` defined an explicit neutral fallback prompt for only T1 and T2; `facilitator-guide.md` told facilitators to "use only the standard neutral prompts listed in task-protocol.md" for every task, but no such list existed for tasks T3–T20, risking inconsistent, ad hoc, potentially leading facilitator improvisation | Added a "Standard neutral prompts (usable for any task)" section to `facilitator-guide.md` with four generic, non-leading prompts, explicitly usable wherever `task-protocol.md` doesn't define a task-specific one |
| 5 | Privacy risk (minor) | `participant-screener.md`'s open-text question (Q6, "how do you currently keep track of what needs your attention?") could surface an employer name or other identifying detail, but the screener didn't say the same anonymisation rule as session quotes applies to it | Added an explicit cross-reference to `data-governance.md`'s quote-anonymisation rule in `participant-screener.md` |

## Reviewed and found sound (no change needed)

- **Duplicated questions:** T10/T11 both ask "what happens if you approve," once for email and once for calendar — this is deliberate (different action types being tested), not a true duplicate, and safety-questionnaire Q1 revisiting the same construct at session end is intentional test-retest triangulation, not redundant.
- **Impossible tasks:** all 20 tasks were checked against real, existing application routes (`apps/web/src/app/{today,approvals,connections,audit-history,settings,onboarding}`) and real demo-dataset fixtures — none requires a state that doesn't exist.
- **Missing fixture states:** every task maps to an entry in [synthetic-scenario-manifest.md](synthetic-scenario-manifest.md), grounded in the existing demo dataset and the two Stage 10 resilience specs, both re-run and confirmed passing during this rehearsal (see the readiness report's verification section).
- **Demo reset process:** relies on the existing, already-documented demo-mode restart/re-seed behaviour — no new mechanism was needed or built.
- **Q3 and Q4 in `safety-questionnaire.md`:** Q3's forced-choice framing ("the general idea, or the exact text/details") and Q4's use of the word "safe" were reviewed for leading bias; both were judged appropriate to their construct (testing a genuine binary distinction, and testing safety-behaviour knowledge respectively) rather than defects, since the alternative — a fully open question — would not reliably surface the specific comprehension gap each is designed to catch.
- **GO/NO-GO threshold traceability:** every number in `product-hypotheses.md` and `go-no-go-template.md` was confirmed to trace back to `success-criteria.md` without independent restatement (beyond the conversion-rule fix in finding #1 above).

## Session-duration estimate (rehearsal, not observed)

Approximately 60–75 minutes: ~35–45 minutes for the 20 tasks (a handful — T1, T3, T8, T15–T19 — are quick lookups of ~1–2 minutes each; onboarding (T2) and the proposal-review tasks (T9–T12) run longer, ~3–5 minutes each), ~5 minutes for the safety questionnaire, ~10–15 minutes for the post-session questionnaire and SUS, and ~5–10 minutes for the closing interview. This is a desk estimate; actual Round 1 timing data will confirm or correct it, and may itself become a Round 1 → Round 2 script-revision input per [task-protocol.md](task-protocol.md)'s revision rule.

## Conclusion

No P0-equivalent defect (a defect that would make the evaluation unsafe or invalid to run) was found. All five findings above were ordinary readiness defects, corrected in place during this rehearsal. This rehearsal's outcome feeds [round-1-readiness-decision.md](round-1-readiness-decision.md).
