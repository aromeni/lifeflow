# Naming Conventions

**Purpose:** one vocabulary across 500+ future files. When naming anything, find the rule here first; if a genuinely new kind of thing appears, add its rule here in the same change. Companion to [tree.md](tree.md) (where things go) — this page covers what they are called.

## The golden rule: capability first, vendor last

Interfaces and domain code are named for **what they do**, never for who provides it. Vendor names appear only in adapter implementations, at the edge.

| ✅ Correct | ❌ Wrong | Why |
|---|---|---|
| `EmailConnector` (interface) | `GmailManager`, `MailAPI`, `GoogleMailConnector` | Domain depends on capability, not vendor |
| `CalendarConnector` (interface) | `GCalService`, `CalendarAPIHelper` | Same |
| `TaskConnector` (interface) | `TodoManager`, `TaskUtil` | Same |
| `GoogleEmailConnector` (adapter) | `GmailImpl`, `EmailConnectorV2` | Vendor prefix + interface name, only in adapters |
| `SyntheticEmailConnector` (adapter) | `FakeMail`, `DemoGmail` | Demo adapters follow the same pattern |
| `LLMProvider` (interface) / `AnthropicProvider`, `MockProvider` (adapters) | `ClaudeClient`, `AIHelper` | Provider neutrality is a permanent principle |

## Domain entities (nouns, singular)

Exactly the names from the domain model — never synonyms, never abbreviations:

`User` · `ConnectedAccount` · `SourceItem` · `Signal` · `Brief` · `ActionProposal` · `ActionExecution` · `Preference` · `AuditEvent`

- ❌ Never: `Msg`, `Task2`, `BriefData`, `SignalInfo`, `ProposalObj`, `AuditLog` (the entity is `AuditEvent`; the collection is "the audit log" in prose only).
- Database tables: snake_case plural of the entity — `users`, `connected_accounts`, `source_items`, `signals`, `briefs`, `action_proposals`, `action_executions`, `preferences`, `audit_events`.

## Services and pipeline components (agent noun or `<Entity><Role>`)

One class per pipeline responsibility, named `<What><Role>`:

| Role suffix | Use for | Examples |
|---|---|---|
| `…Connector` | External-capability interfaces + adapters | `EmailConnector`, `GoogleCalendarConnector` |
| `…Extractor` | Turning source items into signals | `SignalExtractor`, `DeadlineExtractor` |
| `…Detector` | Deterministic rule checks | `ConflictDetector`, `StaleFollowUpDetector` |
| `…Scorer` | Producing a score with reason codes | `PriorityScorer` |
| `…Service` | Orchestration/use-case entry points | `ActionProposalService`, `BriefService` |
| `…Repository` | Data access for one entity | `SignalRepository`, `AuditEventRepository` |
| `…Executor` | Performing one approved action type | `GmailDraftExecutor`, `CalendarEventExecutor` |
| `…PolicyEngine` / `…Policy` | Deterministic pre-execution checks | `ActionPolicyEngine`, `ExpiryPolicy` |
| `…Provider` | Pluggable external capability (LLM, notifications) | `AnthropicProvider`, `InAppNotificationProvider` |
| `…Cipher` | Encryption helpers | `TokenCipher` |

- ❌ Never: `…Manager`, `…Helper`, `…Util(s)`, `…Handler`, `…Processor`, `…Impl`, `…V2`, `My…`, `…Wrapper`. If none of the suffixes above fits, the class probably has an unclear job — fix the design, not the name.

## Python (apps/api, workers)

- Modules/packages: short snake_case nouns — `signals.py`, `priority.py`, `audit.py`; not `signal_stuff.py`, `helpers.py`, `misc.py`.
- Functions: verb phrases — `extract_signals()`, `score_priority()`, `record_audit_event()`; booleans read as predicates — `is_expired`, `has_approval`.
- Pydantic schemas: `<Entity><Purpose>` — `SignalCreate`, `BriefResponse`, `ProposalApprovalRequest`; never bare `Model`/`Data`/`Payload` suffixes alone.
- Constants: `UPPER_SNAKE_CASE`; enums are singular class names with lower_snake values (`ProposalStatus.approved`).
- Tests: `test_<module>.py`, test names state behaviour — `test_edited_payload_requires_fresh_approval`, not `test_edit_2`.
- Alembic revisions: `NNNN_short_description.py` continuing the zero-padded sequence (`0002_domain_tables.py`).

## TypeScript (apps/web, packages)

- Components: PascalCase named for what the user sees — `ApprovalInbox.tsx`, `EvidenceDrawer.tsx`, `BriefSection.tsx`; not `Card2.tsx`, `NewComponent.tsx`.
- Hooks: `use<Thing>` — `useBrief`, `useApprovalQueue`.
- Route directories: kebab-case matching the screen names — `today/`, `approvals/`, `connections/`, `audit/`, `settings/`.
- Non-component modules: kebab-case files, camelCase exports — `format-date.ts` exporting `formatRelativeDate`.
- Generated contract types are used as generated — never renamed or hand-aliased "for convenience".

## API routes

- Plural kebab-case resources, nested only for true ownership: `/briefs`, `/action-proposals/{id}/approve`, `/connected-accounts/{id}`.
- Verbs only for state transitions that aren't CRUD (`/approve`, `/reject`), matching the proposal state machine.

## Prompts and evals

- Prompts: `<task>_v<N>.md` in `prompts/` — `signal_extraction_v1.md`, `brief_composition_v2.md`. New behaviour = new version, never edit-in-place after release.
- Their output schemas: `<Task>Output` — `SignalExtractionOutput`.
- Eval cases: `case-NNN` ids as in the evaluation framework; fixture files describe their scenario — `prompt_injection_forwarding.json`, not `test1.json`.

## Events, audit, and reason codes

- Audit `event_type`: past-tense dotted lowercase — `proposal.approved`, `sync.completed`, `account.disconnected`.
- Reason codes: stable snake_case identifiers with a UI string elsewhere — `explicit_request`, `due_within_24h`, `calendar_conflict`, `no_reply_5d`. Codes are contracts: renaming one is a breaking change.

## Editions and future packs (naming reserved now)

- Edition packs: `<audience>-edition` config namespaces — `student-edition`, `freelancer-edition`.
- New connectors keep the capability rule: `MicrosoftEmailConnector`, `SlackMessageConnector` — never `TeamsHelper`, `SlackAPI`.
