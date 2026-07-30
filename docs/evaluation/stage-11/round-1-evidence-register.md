# Stage 11 — Round 1 Evidence Register

**Status:** Planning document, no evidence yet exists — no session has run · **Date:** 2026-07-30

Companion: [round-1-runbook.md](round-1-runbook.md) · [data-governance.md](data-governance.md) · [findings-template.md](findings-template.md)

Defines what evidence each session is expected to produce and where it lives. This is a register of expected artefacts, not the artefacts themselves — none exist yet.

## Expected evidence per session

| Artefact | Source | Storage |
|---|---|---|
| Participant ID | Assigned per [data-governance.md](data-governance.md)'s `P-R<round>-<sequence>` convention | Evaluation working files (outside Git) |
| Eligibility confirmation | [participant-screener.md](participant-screener.md) result | Evaluation working files (outside Git) |
| Applicable consent/participation record | Signed [consent-form.md](consent-form.md) (once the evaluation context and any required approval are resolved) | Retained separately from all other evaluation data, per [data-governance.md](data-governance.md) |
| Task observation sheet | [observation-sheet.md](observation-sheet.md), one per participant | Evaluation working files (outside Git) |
| Safety questionnaire | [safety-questionnaire.md](safety-questionnaire.md) results | Evaluation working files (outside Git) |
| Post-session questionnaire | [post-session-questionnaire.md](post-session-questionnaire.md) results | Evaluation working files (outside Git) |
| Issue entries | [issue-register-template.md](issue-register-template.md) rows raised during the session | Evaluation working files (outside Git); aggregated counts may later appear in [findings-template.md](findings-template.md) |
| Incident record, where applicable | [round-1-runbook.md](round-1-runbook.md)'s emergency-stop procedure | Evaluation working files (outside Git) |
| Withdrawal or deletion request, where applicable | Participant request per [data-governance.md](data-governance.md) | Evaluation working files (outside Git), then deleted per the withdrawal procedure |
| Session summary | Facilitator's same-day transfer into the findings format ([findings-template.md](findings-template.md)) | Evaluation working files (outside Git) until the findings report is finalised |

## What never enters this repository

- Participant records of any kind (names, contact details, real demographic detail beyond the two screening fields).
- Signed consent forms.
- Raw observation-sheet or questionnaire notes.
- Recordings or transcripts (none are made by default; see [data-governance.md](data-governance.md)).
- Anything that would let a reader re-identify a specific participant.

## What may eventually enter this repository

Only the aggregated, anonymised findings report ([findings-template.md](findings-template.md), filled in) and the go/no-go decision ([go-no-go-template.md](go-no-go-template.md), filled in) — both after the facilitator has reviewed them for identifying detail, per [data-governance.md](data-governance.md)'s quote-anonymisation rule. This register's own content (this file) is a blank template describing the process; it is not itself evidence.

## Register status

No row above has any evidence yet. This register becomes populated only once [recruitment-authorisation-checklist.md](recruitment-authorisation-checklist.md) shows every applicable item satisfied and at least one session has actually run — neither has happened as of this document's creation.
