# Stage 11 — Evaluation Data Governance

**Status:** Planning document · **Date:** 2026-07-30

Companion: [participant-information.md](participant-information.md) · [consent-form.md](consent-form.md) · [threat-model.md](../../security/threat-model.md)

This document governs data collected *about evaluation participants*, not application data. It follows the same privacy-by-design principle as the product itself ([project-foundation.md](../../project/project-foundation.md) §3).

## What will be collected

- Participant ID (pseudonymous, see convention below).
- Session observation-sheet data (task results, timings, quotes/observations — see [observation-sheet.md](observation-sheet.md)).
- Safety-questionnaire and post-session-questionnaire answers.
- Minimal demographic/screening data needed to confirm target-user fit (see [stage-11-plan.md](../../delivery/stage-11-plan.md) §2): professional role category, whether they personally manage their own Gmail/Calendar. No further demographic detail is collected.
- Signed consent form (retained separately from evaluation working data — see Retention below).

## Why each field is necessary

Every field above ties directly to a hypothesis in [product-hypotheses.md](product-hypotheses.md) or a threshold in [success-criteria.md](success-criteria.md); no field is collected "in case it's useful later."

## What will not be collected

- Real name, email address, or contact details in any evaluation working file (only on the separately-retained consent form).
- Real Gmail or Calendar content of any kind.
- Special-category personal data (health, ethnicity, religion, political opinion, etc.).
- Audio or video recordings, by default.
- Detailed demographic profiling beyond the two screening fields above.

## Where records are stored

Evaluation working files (observation sheets, questionnaire results, issue register, findings report) are stored outside this Git repository, in a location the facilitator controls, access-restricted to people directly running the evaluation. **No participant data, consent form, or evaluation working file is ever committed to this repository** — only the blank templates in `docs/evaluation/stage-11/` are version-controlled.

## Who can access records

Limited to the facilitator(s) running the sessions and, in aggregate/anonymised form only, whoever reviews the Stage 11 findings report and go/no-go decision.

## Participant-ID format

`P-R<round>-<sequence>`, e.g. `P-R1-01`, `P-R2-05`. The mapping from participant ID to real identity exists only on the signed consent form, retained separately per the Retention section below — never in any evaluation working file alongside session data.

## Recordings

None by default (per [participant-information.md](participant-information.md)). If a specific session justifies recording, this requires separate, explicit, written participant consent beyond the standard consent form, and a specific retention/deletion plan agreed in advance — not authorised as a default under this document.

## Transcript handling

Not applicable while no recording is made. If introduced later under the exception above, transcripts follow the same retention and anonymisation rules as observation-sheet notes.

## Quote anonymisation

Any quote used in the findings report is checked for identifying detail (employer names, unique personal circumstances) and edited or generalised before inclusion. Quotes are attributed only to a participant ID, never a name.

## Retention period

- Evaluation working data (observation sheets, questionnaires, issue register): retained until the Stage 11 findings report and go/no-go decision are finalised, plus [30 days] for review, then deleted.
- Signed consent forms: retained for [the minimum period required by applicable institutional/legal policy — to be confirmed before use] and then securely deleted, kept separately from all other evaluation data throughout.

## Deletion procedure

At the end of the retention period, the facilitator deletes all evaluation working files and confirms deletion in the findings report's data-handling note. Consent forms are deleted or securely destroyed per institutional policy once their retention period ends.

## Participant withdrawal procedure

A participant may request withdrawal up to the deadline stated in [participant-information.md](participant-information.md). On request, the facilitator deletes that participant's observation-sheet and questionnaire data and removes any quote attributed to their participant ID from in-progress findings materials.

## Incident handling

If participant data is disclosed, lost, or accessed without authorisation, the facilitator stops further data collection, records what happened, and notifies [contact/role to be confirmed before use] — this mirrors the "never silently ignore failures" guard rail in [project-foundation.md](../../project/project-foundation.md) §4.

## Prohibition on real inbox/Calendar data

No participant's real Gmail or Calendar account is connected during Round 1 or Round 2 under this plan. Any future use of real account data for evaluation requires a separate, explicitly approved plan — it is not authorised here.

## University research flag

If this evaluation is conducted in connection with university research, the relevant university's ethics-approval process and supervisor sign-off must be completed, and an approval reference recorded in [participant-information.md](participant-information.md), before recruitment begins. This document does not itself constitute or claim such approval.
