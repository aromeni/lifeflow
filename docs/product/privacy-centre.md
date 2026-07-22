# Privacy & Connections Control Centre (user guide)

*Stage 9 Delivery Phase 1. This page describes the read-only privacy surface
at `/connections`.*

LifeFlow's **Privacy & Connections** page is the one place to understand what
LifeFlow is connected to, what it can see, what it has stored, and how long it
is ordinarily kept. Everything on the page is read-only — LifeFlow never sends
email, never changes your calendar, and nothing on this page deletes anything.

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

## The four data controls (each is different)

1. **Disconnect a provider** — revokes LifeFlow's access and stops future
   syncing. **The data LifeFlow already imported stays** until you delete it
   separately. *(Available now.)*
2. **Delete imported provider data** — removes LifeFlow's imported copy and
   eligible derived data. It **never deletes anything in your Gmail or Google
   Calendar**. *(Coming in a later update, with an impact preview and typed
   confirmation.)*
3. **Delete learned preferences** — clears what LifeFlow inferred from your own
   actions, without touching imported evidence or your explicit settings.
   *(Managed from Settings.)*
4. **Delete the LifeFlow account** — revokes connections and removes your
   personal product data, keeping only privacy-minimised, content-free records
   needed for integrity. It **never deletes your Gmail or Google account**.
   *(Coming in a later update.)*

## Important, honest limitations (for the pilot)

- Retention horizons shown are **provisional product defaults, not legal
  requirements**, and **automatic deletion is not switched on yet** — nothing
  is auto-deleted today.
- Executions that are still **pending or uncertain are always preserved** so an
  external outcome can be reconciled.
- **Confirmed explicit preferences do not expire** just because the older
  inferred-memory evidence behind them ages.
