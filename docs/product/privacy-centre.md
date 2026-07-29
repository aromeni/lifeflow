# Privacy & Connections Control Centre (user guide)

*Stage 9 Delivery Phases 1–3. This guide describes the privacy surface at
`/connections`: the read-only summary (Phase 1), actionable deletion controls
(Phase 2), and its link to the read-only `/audit-history` timeline (Phase 3).*

LifeFlow's **Privacy & Connections** page is the one place to understand what
LifeFlow is connected to, what it can see, what it has stored, and how long it
is ordinarily kept. LifeFlow never sends email or deletes provider content;
its existing calendar-create path still requires exact approval. A LifeFlow
data deletion happens only after you open the distinct control, review its
impact preview, and type the exact confirmation phrase — never on page load.

## What you can see

- **Connected accounts** — whether Google is connected, and its status.
- **Granted access** — plain-language labels for exactly what you allowed
  (e.g. "View Gmail evidence", "Create Gmail drafts"), with an expandable
  "Technical detail" showing the raw scopes. You only ever see what was
  actually granted — never what was merely requested.
- **Evidence freshness** — when your data was last synced (fresh / aging /
  stale), or "never synced". Scheduled briefs only ever use evidence from a
  sync you started; LifeFlow never syncs on its own.
- **Data stored by LifeFlow** — owner-scoped counts of every category
  (imported emails & events, signals, briefs and versions, proposals,
  executions, scheduled runs, preferences, learned-preference items and
  evidence, and audit records). Counts only — never the contents.
- **How long data is kept** — the provisional retention defaults for each
  category.
- **Audit history** — a link to privacy-reviewed plain-language records of
  important activity.

## The four data controls (each is different)

1. **Disconnect a provider** — revokes LifeFlow's access and stops future
   syncing. **The data LifeFlow already imported stays** until you delete it
   separately. *(Available now.)*
2. **Delete imported provider data** — removes LifeFlow's imported copy and
   eligible derived data for one account. It **never deletes anything in your
   Gmail or Google Calendar**. You first see an **impact preview** (what will be
   deleted, and what is kept as content-free history), then type
   `DELETE IMPORTED DATA` to confirm. For a complete clean-out, disconnect
   first — deletion never disconnects for you. *(Available now.)*
3. **Delete learned preferences** — clears what LifeFlow inferred from your own
   actions, without touching imported evidence or your explicit settings.
   *(Managed from Settings.)*
4. **Delete the LifeFlow account** — a distinct, high-risk control. Revokes
   connections and removes your personal product data, keeping only
   privacy-minimised, content-free records needed for integrity. It **never
   deletes your Gmail or Google account** and **cannot be undone**; you type
   `DELETE MY LIFEFLOW ACCOUNT` to confirm, and your session is signed out when
   it finishes. *(Available now.)*

## How deletion works (Phase 2)

- **Preview first.** Every deletion shows exact counts before you confirm, and
  the preview counts equal what actually happens.
- **Snapshot boundary.** A deletion covers only what was imported at the moment
  you previewed — anything you sync afterwards is never silently swept in.
- **Preserved by design.** Actions you already approved or that ran are kept as
  **content-free** history; **pending or uncertain outcomes are always
  preserved**; **confirmed explicit preferences are never deleted**.
- **Durable & resumable.** Deletion runs in the background in safe batches; if it
  is interrupted it resumes exactly where it left off, and it never runs twice.
- **Nothing on this page ever runs on load** — a deletion only starts when you
  preview and then type the exact confirmation phrase.

## Audit history (Phase 3)

The **View audit history** link opens the canonical `/audit-history` page.
Entries contain a fixed plain-language title and summary, the time, closed
actor/category/outcome labels, and — where relevant — a small safe action-type
badge (**Task**, **Gmail draft**, or **Calendar event**), a plain-language
**Reason:** line for a blocked or failed action, and, for a completed or
partly completed deletion/retention operation, plain-language record counts
("36 records deleted", "1 record preserved for reconciliation"). Raw event
metadata, private content, provider identifiers, entity/correlation ids,
rejection reasons, memory or preference values, per-category count
breakdowns, and technical error details are never returned — only these few
closed, pre-validated summaries.

Use the closed activity filters (All activity, Actions, Briefs, Connections,
Privacy, Preferences, Account) and time filters (7/30/90 days or All time).
**Load more** appends an older stable page without moving the current window
when new events arrive. Audit history is owner-only and read-only; it has no
edit or delete control. A new internal event remains hidden until LifeFlow adds
an explicit privacy-reviewed presentation for it.

## Important, honest limitations (for the pilot)

- Retention horizons shown are **provisional product defaults, not legal
  requirements**. Automatic retention enforcement exists (Phase 2) but is
  **off by default in the pilot** and only runs when a deployment enables it and
  runs the worker; when on, it uses the **same preservation rules** as manual
  deletion (pending/uncertain executions and confirmed preferences are never
  swept). The page's retention notice only says "enforced" when it genuinely is.
- Executions that are still **pending or uncertain are always preserved** so an
  external outcome can be reconciled.
- **Confirmed explicit preferences do not expire** just because the older
  inferred-memory evidence behind them ages.
