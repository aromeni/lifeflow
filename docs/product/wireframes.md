# Low-fidelity Text Wireframes

**Status:** Stage 0 draft · **Date:** 2026-07-15

Low-fi text wireframes for the seven required screens. Layout intent only — visual design comes later. Accessibility applies to every screen: full keyboard operation, visible focus states, semantic labels and status announcements, no meaning by colour alone (WCAG 2.2 AA where practical).

Journeys exercising each screen are listed in [user-journeys.md](user-journeys.md#journey-to-screen-coverage).

---

## 1. Landing / demo screen (J1)

```text
┌──────────────────────────────────────────────────────────────┐
│ LifeFlow AI                                    [Sign in]     │
├──────────────────────────────────────────────────────────────┤
│  Quietly finds what needs attention, explains why it         │
│  matters, and prepares the next step — for YOUR approval.    │
│                                                              │
│  [ Try demo (no account needed) ]   [ Connect Google ]      │
│                                                              │
│  How your data is handled                                    │
│  • Reads only a recent window you authorise                  │
│  • Never sends email or changes your calendar by itself      │
│  • Disconnect and delete your data at any time               │
│  • Full audit trail of everything it observes and does       │
└──────────────────────────────────────────────────────────────┘
```

## 2. Onboarding (J1, J2)

```text
Step 1 of 3 — Permissions                    Step 2 — You        Step 3 — Your brief
┌────────────────────────────────┐   ┌───────────────────┐  ┌─────────────────────┐
│ What LifeFlow will access      │   │ Timezone           │  │ Choose sections     │
│ ☐ Gmail: read recent messages  │   │ [Europe/London ▾]  │  │ ☑ Needs attention   │
│   + create drafts you approve  │   │ Working hours      │  │ ☑ Today & upcoming  │
│ ☐ Calendar: read events        │   │ [09:00]–[17:30]    │  │ ☑ Waiting for       │
│   + create events you approve  │   │                    │  │ ☑ Suggested actions │
│ Nothing is ever sent or        │   │                    │  │                     │
│ changed without your approval. │   │                    │  │                     │
│ [Connect Google] [Skip → demo] │   │ [Back]  [Next]     │  │ [Back]  [Finish]    │
└────────────────────────────────┘   └───────────────────┘  └─────────────────────┘
```

## 3. Today dashboard (J1, J3, J8)

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Today · Tue 15 Jul   [Refresh brief]   status: generated 08:00 ✓     │
│ "Two client requests need replies; proposal deadline tomorrow;       │
│  Thursday has a scheduling conflict."                                │
├──────────────────────────────────────────────────────────────────────┤
│ NEEDS ATTENTION (3)                                                  │
│ ▸ Reply to Dana re: contract terms      conf: high                   │
│   why: Explicit request from sender · Due within 24 hours [evidence] │
│   [Draft reply]                                                      │
│ ▸ Proposal for Northgate due tomorrow   conf: high    [evidence]     │
├──────────────────────────────────────────────────────────────────────┤
│ TODAY & UPCOMING          │ WAITING FOR                              │
│ 10:00 Client stand-up     │ ▸ Sam — invoice query, no reply 5 days   │
│ 14:00 ⚠ overlaps 14:30    │   [Nudge draft]              [evidence]  │
├──────────────────────────────────────────────────────────────────────┤
│ SUGGESTED ACTIONS (2 awaiting review → Approval inbox)               │
│ LOW-CONFIDENCE ITEMS (1) — needs your judgement                      │
└──────────────────────────────────────────────────────────────────────┘
Evidence drawer (opens from any [evidence] link):
┌────────────────────────────────────┐
│ Source: email from Dana, 14 Jul    │
│ "Could you confirm the terms by    │
│  Wednesday?"                       │
│ Detected: explicit request, dead-  │
│ line 16 Jul · confidence high      │
└────────────────────────────────────┘
```

## 4. Approval inbox (J4, J5, J7)

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Approval inbox (2)                                                   │
├──────────────────────────────────────────────────────────────────────┤
│ ▸ Gmail draft — reply to Dana                     risk: MEDIUM       │
│   To: dana@example-client.co.uk                                      │
│   Subject: Re: Contract terms                                        │
│   ┌ exact body preview (editable) ────────────────────────────┐      │
│   │ Hi Dana, confirming the terms by Wednesday…               │      │
│   └───────────────────────────────────────────────────────────┘      │
│   Why: explicit request, due 16 Jul            [evidence]            │
│   [Edit] [Approve — creates a DRAFT only] [Reject]                   │
│   note: editing invalidates any earlier approval                     │
├──────────────────────────────────────────────────────────────────────┤
│ ▸ Calendar event — "Proposal work block" Thu 09:00–10:30             │
│   risk: MEDIUM   [Edit] [Approve] [Reject]         [evidence]        │
├──────────────────────────────────────────────────────────────────────┤
│ Executed today: 1 ✓ draft created 09:12 → view in Audit history      │
└──────────────────────────────────────────────────────────────────────┘
```

## 5. Connections & privacy (J2, J6)

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Connections & privacy                                                │
├──────────────────────────────────────────────────────────────────────┤
│ Google — connected ✓            last sync: 08:00 today               │
│ Scopes granted:                                                      │
│  • gmail.readonly     — read recent messages (14-day window)         │
│  • gmail.compose      — create drafts you approve                    │
│  • calendar.readonly  — read events                                  │
│  • calendar.events    — create events you approve                    │
│ [Disconnect Google]  [Delete imported data]                          │
├──────────────────────────────────────────────────────────────────────┤
│ Retention: imported items kept N days after last sync, then removed. │
│ Audit history keeps non-sensitive records of actions.                │
└──────────────────────────────────────────────────────────────────────┘
```

## 6. Audit history (J4–J7)

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Audit history      filter: [All actions ▾] [Last 7 days ▾]           │
├──────────────────────────────────────────────────────────────────────┤
│ 15 Jul 09:12  You approved a Gmail draft to dana@… — draft created ✓ │
│ 15 Jul 09:10  You edited the proposed draft (approval reset)         │
│ 15 Jul 08:00  Brief generated from 42 emails, 9 events               │
│ 14 Jul 18:03  You rejected a proposed calendar event                 │
│ 14 Jul 08:00  Sync completed: Gmail (38 new), Calendar (2 new)       │
├──────────────────────────────────────────────────────────────────────┤
│ Plain-language entries only. No message bodies or secrets shown.     │
└──────────────────────────────────────────────────────────────────────┘
```

## 7. Settings (J8)

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Settings                                                             │
├──────────────────────────────────────────────────────────────────────┤
│ Timezone          [Europe/London ▾]                                  │
│ Briefing time     [08:00] daily   (respects daylight saving)         │
│ Working hours     [09:00]–[17:30]  Mon–Fri                           │
│ Priority rules    ☑ Deprioritise newsletters                         │
│                   ☑ Boost known client domains  [manage list]        │
│ Memory            2 inferred preferences  [review / delete]          │
│                   note: explicit settings always win; critical       │
│                   deadlines are never hidden by learned preferences  │
└──────────────────────────────────────────────────────────────────────┘
```
