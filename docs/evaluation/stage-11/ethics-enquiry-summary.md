# Stage 11 — Ethics Enquiry Summary (university-linked pathway)

**Status:** Draft enquiry pack — no approval has been sought or granted · **Date:** 2026-07-30

Companion: [evaluation-context-decision.md](evaluation-context-decision.md) · [participant-information.md](participant-information.md) · [consent-form.md](consent-form.md)

**This document is a summary to send to a supervisor or the relevant ethics contact if — and only if — [evaluation-context-decision.md](evaluation-context-decision.md) is resolved as UNIVERSITY-LINKED.** It does not itself constitute, claim, or imply any ethics approval. No ethics reference number, supervisor name, or module code is stated here because none has been confirmed — every such placeholder below must be filled in with real information before this pack is sent, not fabricated to make the document look complete.

## Project title

LifeFlow AI — Stage 11 product evaluation (working title; confirm the title to use for any ethics submission with the supervisor/ethics contact).

## Project owner

_(name to be filled in by the project owner)_

## Programme / module

_(placeholder — to be filled in only if applicable; leave blank and say so explicitly if this work is not tied to a specific programme or module)_

## Supervisor

_(placeholder — to be filled in only with a real, confirmed supervisor name; do not invent one)_

## Purpose

To evaluate, with representative participants, whether LifeFlow (a permissioned, human-in-the-loop personal-operations assistant for Gmail and Google Calendar) is understandable, trustworthy, and useful enough to justify further investment in packaging and deployment — see [stage-11-plan.md](../../delivery/stage-11-plan.md) §1 for the full purpose statement.

## Participant profile

Busy UK-based professionals, consultants, postgraduate students, or freelancers who personally manage their own Gmail and Google Calendar — see [stage-11-plan.md](../../delivery/stage-11-plan.md) §2 for the full target-user hypothesis and exclusion criteria.

## Expected sample size

Round 1: 3–5 participants. Round 2: 5–8 participants. Total expected: 8–13 across both rounds.

## Design

A two-round formative usability/trust/safety-comprehension evaluation — see [stage-11-plan.md](../../delivery/stage-11-plan.md) §3 and [task-protocol.md](task-protocol.md) for the full 20-task script.

## Environment

Deterministic local demo mode against a wholly fictional synthetic dataset (`apps/api/src/lifeflow_api/demo/data/v1/`) — no real Gmail or Calendar account is connected at any point in either round.

## Data collection

No recording by default. Written observation notes and questionnaire answers, recorded against a pseudonymous participant ID (`P-R<round>-<sequence>`), never a name. See [data-governance.md](data-governance.md) for the full data-minimisation and retention plan.

## Retention and deletion

Evaluation working data is retained until the findings report and go/no-go decision are finalised, plus a short review window, then deleted. Signed consent forms are retained separately, per whatever period the applicable ethics process requires — this has not yet been confirmed and must be set by the ethics reviewer/supervisor, not assumed here.

## Participant withdrawal

Participants may withdraw up to a stated deadline with no consequence; their data is then deleted. See [data-governance.md](data-governance.md).

## Potential risks

Minimal-risk usability study: participants interact with a demo product using fictional data. Foreseeable risks are limited to: mild frustration or time pressure during tasks; a participant misremembering or misreporting their own workflow; incidental disclosure of unrelated personal information during think-aloud commentary.

## Risk mitigations

Fictional data only; no real account connection; voluntary participation with a clear stop-at-any-time policy; no special-category data solicited; facilitator trained to redirect if a participant starts describing their own real inbox/calendar content; incident-handling procedure defined in [data-governance.md](data-governance.md) and [round-1-runbook.md](round-1-runbook.md).

## Incentives

None proposed by default. If incentives are later considered, they require separate, explicit approval from the project owner and, if applicable, the ethics reviewer — not assumed or authorised by this pack.

## Intended use of findings

Internal decision-making: a findings report and a GO / CONDITIONAL GO / NO-GO decision on whether to proceed to Stage 12 (packaging). See [findings-template.md](findings-template.md) and [go-no-go-template.md](go-no-go-template.md).

## Publication intentions

None currently planned. If publication, conference presentation, or inclusion in an academic submission is later intended, this must be disclosed to and cleared by the relevant ethics process — this pack does not assume or authorise that outcome.

## Attached templates

- [participant-information.md](participant-information.md)
- [consent-form.md](consent-form.md)

Both are explicitly marked as unreviewed templates pending this ethics review.

## Question for the ethics contact / supervisor

Which ethics-review route applies to this project (e.g., low-risk/expedited review, full committee review, or another applicable University of Kent process), and what changes, if any, are required to the attached templates and this summary before recruitment can begin?
