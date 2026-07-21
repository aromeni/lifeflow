"""Approval-bound execution context (Stage 7 remediation, independent-review
blocker #1).

`ExecutionContext` is the complete, provenance-bound description of what
approving/executing a proposal actually means: which path runs
(`simulation`/`real`/`unavailable`), which Google account (if any) it is
bound to, and which evidence it originated from. It is computed fresh from
live state for every preview, persisted verbatim (with its hash) at
approval time, and recomputed again immediately before execution — the two
computations must match exactly or execution is refused. Execution mode is
never chosen merely by "is any Google account connected"; it is bound to the
exact `ConnectedAccount` the proposal's evidence (`SourceItem.
source_account_id`) actually originated from:

- synthetic/no-account evidence -> permanently `simulation`, regardless of
  what the user later connects;
- Google-sourced evidence -> `real` only if that *exact* account is still
  active and holds the required scope; a different Google account is never
  substituted, and if the source account is unavailable the mode is
  `unavailable` rather than falling back to simulation;
- ambiguous evidence spanning more than one external account -> fail closed
  (`unavailable`) rather than guessing.

`create_task` is a closed exception: task creation is always local/simulated
regardless of evidence source (skill §5.1/§10) — there is no Google call for
this action type to bind to.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from enum import StrEnum

from lifeflow_api.google_scopes import CALENDAR_EVENTS_SCOPE, GMAIL_COMPOSE_SCOPE
from lifeflow_api.models import (
    AccountStatus,
    ActionProposal,
    ActionType,
    ConnectedAccount,
    ExecutionMode,
    SourceItem,
)

SIMULATED_PROVIDER = "synthetic"
SIMULATED_SCOPE = "demo"
GOOGLE_PROVIDER = "google"

REQUIRED_GOOGLE_SCOPE: dict[ActionType, str] = {
    ActionType.create_gmail_draft: GMAIL_COMPOSE_SCOPE,
    ActionType.create_calendar_event: CALENDAR_EVENTS_SCOPE,
}


class SourceMode(StrEnum):
    """Where the proposal's evidence originated. Fixed once the proposal is
    composed — `source_refs` never change afterwards — independent of what
    the user later connects or disconnects."""

    synthetic = "synthetic"
    google = "google"
    # Evidence spans more than one distinct external account (or a Google
    # account mixed with a non-Google one) — never guessed, always resolved
    # to `ExecutionMode.unavailable`.
    incompatible = "incompatible"


@dataclass(frozen=True)
class ExecutionContext:
    mode: ExecutionMode
    provider: str
    connected_account_id: uuid.UUID | None
    account_authorisation_revision: int | None
    required_scope: str | None
    source_mode: SourceMode
    source_account_id: uuid.UUID | None


def _distinct_account_ids(evidence_sources: list[SourceItem]) -> set[uuid.UUID]:
    return {
        item.source_account_id for item in evidence_sources if item.source_account_id is not None
    }


def _has_simulated_capability(accounts: list[ConnectedAccount]) -> bool:
    """Whether the demo/synthetic path itself is still usable. Degrading
    this (removing its scope, disconnecting it) is not a real user-facing
    action in this product today — there is no UI/route for it — but the
    policy engine still fails closed defensively rather than assuming the
    capability always exists."""
    return any(
        account.provider == SIMULATED_PROVIDER
        and account.status == AccountStatus.active
        and SIMULATED_SCOPE in account.granted_scopes
        for account in accounts
    )


def resolve_execution_context(
    action_type: ActionType,
    *,
    accounts: list[ConnectedAccount],
    evidence_sources: list[SourceItem],
) -> ExecutionContext:
    """The single source of truth for "what would/does executing this
    proposal actually do?" — decided from the proposal's own evidence
    provenance plus the user's *currently* connected accounts, never from
    accounts alone."""
    accounts_by_id = {account.id: account for account in accounts}
    account_ids = _distinct_account_ids(evidence_sources)
    google_ids = {
        account_id
        for account_id in account_ids
        if accounts_by_id.get(account_id) is not None
        and accounts_by_id[account_id].provider == GOOGLE_PROVIDER
    }
    non_google_ids = account_ids - google_ids
    single_account_id = next(iter(account_ids)) if len(account_ids) == 1 else None

    if action_type == ActionType.create_task:
        # Internal tasks keep their existing local/simulated behaviour
        # unconditionally — there is no Google call to bind for this action
        # type, regardless of what the evidence happens to reference.
        return ExecutionContext(
            mode=ExecutionMode.simulation,
            provider=SIMULATED_PROVIDER,
            connected_account_id=None,
            account_authorisation_revision=None,
            required_scope=None,
            source_mode=SourceMode.google if google_ids else SourceMode.synthetic,
            source_account_id=single_account_id,
        )

    required_scope = REQUIRED_GOOGLE_SCOPE[action_type]

    if len(google_ids) > 1 or (google_ids and non_google_ids):
        return ExecutionContext(
            mode=ExecutionMode.unavailable,
            provider=GOOGLE_PROVIDER,
            connected_account_id=None,
            account_authorisation_revision=None,
            required_scope=required_scope,
            source_mode=SourceMode.incompatible,
            source_account_id=None,
        )

    if google_ids:
        (account_id,) = google_ids
        account = accounts_by_id[account_id]
        if account.status == AccountStatus.active and required_scope in account.granted_scopes:
            return ExecutionContext(
                mode=ExecutionMode.real,
                provider=GOOGLE_PROVIDER,
                connected_account_id=account.id,
                account_authorisation_revision=account.authorisation_revision,
                required_scope=required_scope,
                source_mode=SourceMode.google,
                source_account_id=account.id,
            )
        # The exact source account is unavailable (disconnected/revoked) or
        # missing the required scope — never substitute a different Google
        # account; fail closed instead.
        return ExecutionContext(
            mode=ExecutionMode.unavailable,
            provider=GOOGLE_PROVIDER,
            connected_account_id=None,
            account_authorisation_revision=None,
            required_scope=required_scope,
            source_mode=SourceMode.google,
            source_account_id=account.id,
        )

    # No Google evidence at all: synthetic or unlinked evidence — permanently
    # simulation, and connecting Google later never upgrades this proposal.
    # Still fails closed if the simulated capability itself is entirely
    # gone (defensive; not a reachable user action today).
    simulation_available = _has_simulated_capability(accounts)
    return ExecutionContext(
        mode=ExecutionMode.simulation if simulation_available else ExecutionMode.unavailable,
        provider=SIMULATED_PROVIDER,
        connected_account_id=None,
        account_authorisation_revision=None,
        required_scope=None,
        source_mode=SourceMode.synthetic,
        source_account_id=single_account_id,
    )


@dataclass(frozen=True)
class ApprovedExecutionAuthorization:
    """The immutable, approval-time snapshot of exactly which Google
    account/authorisation/scope executing a proposal is bound to (Stage 7
    focused remediation: post-commit TOCTOU fix).

    Built ONLY from `ActionProposal.approved_*` columns — never from the
    current account list — and threaded explicitly through
    `ActionProposalService.execute() -> registry.execute() -> Google
    executor -> GoogleTokenService.get_valid_access_token_for_execution`, so
    the token layer re-verifies the exact approved identity atomically with
    token acquisition (under the same row lock), instead of trusting a check
    that ran before the durability commit released every lock. `None` for a
    simulated proposal — synthetic executors and `create_task` never receive
    a Google authorisation to use."""

    connected_account_id: uuid.UUID
    provider: str
    authorisation_revision: int
    required_scope: str
    execution_context_hash: str


class ApprovedExecutionContextChangedError(Exception):
    """Raised by `GoogleTokenService.get_valid_access_token_for_execution`
    when the row-locked, freshly-read account no longer matches the exact
    approved snapshot (missing/different account, wrong provider, inactive,
    authorisation revision changed, required scope no longer granted).
    Always raised strictly before any Gmail/Calendar API call. The caller
    must translate this into a durable `failed` outcome with
    `error_code="approval_context_changed"` — never `uncertain`, since
    LifeFlow knows it refused to act; it did not fail to observe an
    outcome."""


def approved_execution_authorization(
    proposal: ActionProposal,
) -> ApprovedExecutionAuthorization | None:
    """Builds the authorisation snapshot `execute()` must pass to a Google
    executor, straight from the immutable columns `approve()` persisted —
    never from a fresh read of the current account list. Returns `None` for
    a simulated approval (nothing to bind); callers must not construct a
    Google executor call at all in that case."""
    if proposal.approved_execution_mode != ExecutionMode.real:
        return None
    assert proposal.approved_connected_account_id is not None  # noqa: S101 — real implies bound
    assert proposal.approved_provider is not None  # noqa: S101
    assert proposal.approved_authorisation_revision is not None  # noqa: S101
    assert proposal.approved_required_scope is not None  # noqa: S101
    assert proposal.approved_execution_context_hash is not None  # noqa: S101
    return ApprovedExecutionAuthorization(
        connected_account_id=proposal.approved_connected_account_id,
        provider=proposal.approved_provider,
        authorisation_revision=proposal.approved_authorisation_revision,
        required_scope=proposal.approved_required_scope,
        execution_context_hash=proposal.approved_execution_context_hash,
    )


def execution_context_hash(context: ExecutionContext) -> str:
    """Canonical hash of the execution-context fields that are actually
    persisted on `ActionProposal` (`source_mode` is derivable from
    `provider` and is intentionally not part of the persisted snapshot or
    this hash). Never includes tokens or other account content — only
    opaque identifiers and a revision counter (skill §4.3)."""
    document = {
        "mode": str(context.mode),
        "provider": context.provider,
        "connected_account_id": (
            str(context.connected_account_id) if context.connected_account_id else None
        ),
        "account_authorisation_revision": context.account_authorisation_revision,
        "required_scope": context.required_scope,
        "source_account_id": (
            str(context.source_account_id) if context.source_account_id else None
        ),
    }
    encoded = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "GOOGLE_PROVIDER",
    "REQUIRED_GOOGLE_SCOPE",
    "SIMULATED_PROVIDER",
    "SIMULATED_SCOPE",
    "ApprovedExecutionAuthorization",
    "ApprovedExecutionContextChangedError",
    "ExecutionContext",
    "SourceMode",
    "approved_execution_authorization",
    "execution_context_hash",
    "resolve_execution_context",
]
