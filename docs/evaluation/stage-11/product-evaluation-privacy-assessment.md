# Stage 11 — Independent Product Evaluation Privacy Assessment

**Status:** Draft decision pack — lawful basis and controller identity not yet confirmed by the responsible owner · **Date:** 2026-07-30

Companion: [evaluation-context-decision.md](evaluation-context-decision.md) · [data-governance.md](data-governance.md) · [threat-model.md](../../security/threat-model.md)

**This document applies only if [evaluation-context-decision.md](evaluation-context-decision.md) is resolved as INDEPENDENT PRODUCT EVALUATION.** It does not itself grant approval, confirm legal compliance, or substitute for a professional legal/privacy review — it is a structured decision pack that surfaces every question a responsible owner must actually answer.

## Proposed data controller

_(to be confirmed by the project owner: the individual or entity who determines the purposes and means of processing participant evaluation data — this is not automatically "whoever wrote this document")_

## Purpose of processing

To determine, through structured usability sessions, whether LifeFlow's onboarding, brief, action-proposal, safety-comprehension, and privacy-control experiences are understandable and trustworthy enough to justify Stage 12 investment. See [stage-11-plan.md](../../delivery/stage-11-plan.md) §1.

## Exact personal-data fields

Per [data-governance.md](data-governance.md): pseudonymous participant ID; two screening fields (professional role category, whether the participant personally manages their own Gmail/Calendar); task observation notes; questionnaire answers; a name and contact detail on the signed consent form only (stored separately, never alongside session data).

## Necessity of every field

Every field above maps to a specific hypothesis in [product-hypotheses.md](product-hypotheses.md) or a screening criterion in [participant-screener.md](participant-screener.md); no field is collected speculatively. This must be re-checked by the responsible owner before recruitment, not assumed permanently true as materials evolve.

## Data minimisation

No demographic data beyond the two screening fields; no recording by default; no special-category data solicited; pseudonymous IDs used throughout working data.

## Proposed lawful basis — requires owner/professional confirmation

Under UK GDPR, plausible candidate bases for this kind of evaluation include **consent** (Article 6(1)(a)) or **legitimate interests** (Article 6(1)(f)), depending on exactly how recruitment and consent are structured. **This document does not select one on the owner's behalf.** The responsible owner (or a qualified professional, if engaged) must record:

- Which basis applies: _(not yet decided)_
- Why: _(not yet decided)_
- Decided by: _(not yet decided)_
- Date: _(not yet decided)_

## Distinction between agreement to participate and the lawful basis

A signed consent form (see [consent-form.md](consent-form.md)) records the participant's **agreement to take part** in the session. It is not automatically the same thing as the **UK GDPR Article 6 lawful basis** for processing their data — those are two different concepts that are easy to conflate. If "consent" is chosen as the Article 6 basis, it must meet GDPR's specific consent standard (freely given, specific, informed, unambiguous, withdrawable) — a decision the responsible owner must make deliberately, not by assuming the participation consent form automatically satisfies it.

## Recipients and access

Limited to the facilitator(s) running sessions and, in aggregated/anonymised form, whoever reviews the Stage 11 findings report. No third-party processor is currently proposed.

## Storage location

Outside this Git repository, in a location the facilitator controls — see [data-governance.md](data-governance.md).

## Retention

Evaluation working data: until the findings report and decision are finalised plus a short review window, then deleted. Signed consent forms: retained separately, per a period the responsible owner must set — not yet fixed in this document.

## Deletion

Facilitator-executed at the end of the retention period; confirmed in the findings report's data-handling note (see [findings-template.md](findings-template.md)).

## Withdrawal

Participants may withdraw up to a stated deadline; their data is then deleted — see [data-governance.md](data-governance.md).

## Anonymisation and pseudonymisation

Participant ID format `P-R<round>-<sequence>`; quotes are checked for identifying detail before use in the findings report; the ID-to-identity mapping exists only on the separately-retained consent form.

## Participant rights

Participants can request access to, correction of, or deletion of their own session data (identified by their participant ID) up to the point the findings report has been finalised and their raw data deleted; after deletion, individual-level rights requests are moot since the identifiable record no longer exists in a form that permits attribution.

## Security controls

Working files stored outside version control, access-restricted to the facilitator(s); no participant data is ever committed to this repository (see [round-1-evidence-register.md](round-1-evidence-register.md)).

## Incident handling

If participant data is disclosed, lost, or accessed without authorisation: stop further collection, record what happened, and notify the responsible owner — see [data-governance.md](data-governance.md)'s incident-handling section and the emergency-stop conditions in [round-1-runbook.md](round-1-runbook.md).

## International-transfer status

None currently proposed — all evaluation data is intended to stay within the facilitator's own storage location. If this changes (e.g., a cloud tool with servers outside the UK/EEA), it must be reassessed here before use, not assumed acceptable.

## Processor inventory

None currently — no third-party tool is proposed for storing or processing participant data. If a scheduling tool, survey platform, or similar third-party service is introduced later, it must be added here with its own data-processing terms reviewed first.

## DPIA screening

A full Data Protection Impact Assessment is not obviously required for a small-sample (8–13 participant), non-special-category, non-systematic-profiling usability study, but this is a screening judgement, not a legal conclusion. The responsible owner should confirm this screening view (or seek a professional opinion) before recruitment, and revisit it immediately if the scope changes — e.g., if special-category data, larger-scale recruitment, or automated profiling of participants is later introduced.

## Owner sign-off required

None of the sections above are decisions until the responsible owner has actually reviewed and signed off on them, in writing, with a date. This document does not claim legal compliance or professional review on its own.
