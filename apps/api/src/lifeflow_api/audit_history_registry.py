"""Closed, privacy-reviewed presentation registry for audit history (ADR 0005).

The append-only `AuditEvent` log is an internal safety record with a raw
`event_type` vocabulary that spans account/session lifecycle, connections and
imported evidence, briefs and scheduled processing, action proposals and
executions, preferences and inferred memory, and user-requested/retention
deletion operations. None of that raw vocabulary is public.

This module is the single source of truth for what becomes visible: a closed
dict maps each reviewed internal event type to fixed, privacy-safe
title/summary/category/tone values. An internal event with no entry here is,
by construction, not renderable — callers must treat the registry as an
allowlist (fail closed), never as a best-effort lookup with a raw fallback.
"""

import re
from dataclasses import dataclass
from enum import StrEnum


class AuditHistoryCategory(StrEnum):
    all = "all"
    actions = "actions"
    briefs = "briefs"
    connections = "connections"
    privacy = "privacy"
    preferences = "preferences"
    account = "account"


class AuditHistoryTone(StrEnum):
    neutral = "neutral"
    success = "success"
    warning = "warning"
    failure = "failure"


@dataclass(frozen=True)
class Presentation:
    category: AuditHistoryCategory
    title: str
    summary: str
    tone: AuditHistoryTone = AuditHistoryTone.neutral
    # Declares which typed detail(s), if any, this event type may show. Each
    # flag only permits looking up specific, pre-validated metadata keys
    # through the closed functions below — it never permits rendering the raw
    # metadata value, or any key not on that closed list.
    show_action_type: bool = False
    show_reason: bool = False
    show_counts: bool = False


def _p(
    category: AuditHistoryCategory,
    title: str,
    summary: str,
    tone: AuditHistoryTone = AuditHistoryTone.neutral,
    *,
    show_action_type: bool = False,
    show_reason: bool = False,
    show_counts: bool = False,
) -> Presentation:
    return Presentation(
        category=category,
        title=title,
        summary=summary,
        tone=tone,
        show_action_type=show_action_type,
        show_reason=show_reason,
        show_counts=show_counts,
    )


# --- Typed, closed detail projection -----------------------------------------
#
# The registry above never touches safe_metadata_json. These two functions are
# the only place that does, and only for the two narrow, already-safe fields
# confirmed present at the actual audit call sites (grep-verified against
# every _audit()/record_audit_event() call in action_proposal_service.py,
# deletion.py, and deletion_ops.py): a closed 3-value action type, and a
# closed reason/error code. Both fail closed: an absent, malformed, or
# unregistered value produces None (omitted), never a raw fallback. Record
# counts are deliberately NOT projected here — see ADR 0005 D79 for why.

# lifeflow_api.models.ActionType's three closed values, mapped to a safe label
# (never the raw enum value, which is an internal wire format).
_SAFE_ACTION_TYPE_LABELS: dict[str, str] = {
    "create_task": "Task",
    "create_gmail_draft": "Gmail draft",
    "create_calendar_event": "Calendar event",
}

# lifeflow_api.action_policy.PolicyViolationError's closed codes, plus the
# small number of additional closed codes raised directly in
# action_proposal_service.py and action_executors.py's FinalExecutionError,
# plus lifeflow_api.deletion_ops's closed deletion/retention error codes.
# Every value here was confirmed at its raise/assignment site to be a fixed
# literal, never interpolated raw text, an exception message, or a provider
# response body.
_SAFE_REASON_LABELS: dict[str, str] = {
    # action_policy.PolicyViolationError.
    "proposal_expired": "The proposal had expired",
    "payload_hash_mismatch": "The proposal's content had changed",
    "invalid_due_at": "The due time had passed",
    "invalid_transition": "The proposal was not in an approvable state",
    "stale_preview": "The displayed preview was no longer current",
    "stale_version": "The displayed version was no longer current",
    "approval_mismatch": "The proposal changed after approval",
    # action_proposal_service.py (raised directly, not via PolicyViolationError).
    "stale_pending_attempt": "A previous attempt was still in progress",
    # action_executors.FinalExecutionError.
    "executor_not_registered": "No executor was available for this action",
    "payload_type_mismatch": "The action payload did not match its type",
    "approved_authorization_missing": "The stored approval could not be verified",
    "approval_context_changed": "The approval context had changed",
    "google_reauthorisation_required": "The connected account needs to be reauthorised",
    "google_auth_rejected": "The connected account rejected the request",
    "google_execution_unavailable": "The connected service was unavailable",
    # deletion_ops.py closed deletion/retention/account-deletion error codes.
    "worker_stale_timeout": "The operation took too long and was recovered",
    "max_attempts_exhausted": "The operation reached its retry limit",
    "provider_revoke_failed": "Provider access could not be revoked",
    "database_unavailable": "A temporary storage issue occurred",
    "internal_error": "An internal error occurred",
}

# action_executors.py's one parametrized code: f"google_client_error_{status}".
# The interpolated value is an HTTP status code integer (never a message body
# or header), so this is bounded and safe to match structurally rather than
# as a literal — restricted to the 4xx/5xx range actually used by the client.
_GOOGLE_CLIENT_ERROR_RE = re.compile(r"^google_client_error_[45]\d\d$")


def safe_action_type_label(value: object) -> str | None:
    """Return the fixed safe label for a closed ActionType value, or None."""
    if not isinstance(value, str):
        return None
    return _SAFE_ACTION_TYPE_LABELS.get(value)


def safe_reason_label(value: object) -> str | None:
    """Return the fixed safe label for a closed reason/error code, or None."""
    if not isinstance(value, str):
        return None
    label = _SAFE_REASON_LABELS.get(value)
    if label is not None:
        return label
    if _GOOGLE_CLIENT_ERROR_RE.match(value):
        return "The connected service returned an error"
    return None


# The exact three approved presentation-safe count keys. Any other key in
# metadata — a category breakdown, an id, a scope descriptor — is ignored,
# never promoted to an API field. Bound matches the writer's own bound
# (deletion.py's _MAX_SAFE_AGGREGATE_COUNT); kept independent here rather than
# imported, so this module has no dependency on the deletion engine, and the
# presentation layer validates its own inputs rather than trusting the writer.
_SAFE_COUNT_KEYS = ("deleted_count", "preserved_count", "failed_count")
_MAX_SAFE_COUNT = 1_000_000


def _safe_count(value: object) -> int | None:
    """Validate one count value: a plain non-negative bounded int, nothing
    else. Booleans are rejected explicitly — `bool` is a subclass of `int` in
    Python, so `isinstance(True, int)` is true and would otherwise slip
    through."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > _MAX_SAFE_COUNT:
        return None
    return value


def safe_counts(metadata: object) -> dict[str, int]:
    """Extract only the closed, validated count fields from raw metadata.
    Malformed or out-of-range values are silently omitted (never raised,
    never echoed); keys other than the three approved ones are always
    ignored, however they are spelled. There is currently no writer that
    produces `failed_count` — see ADR 0005 D79 — so it is always omitted in
    practice, but the extraction path supports it like the other two."""
    if not isinstance(metadata, dict):
        return {}
    result: dict[str, int] = {}
    for key in _SAFE_COUNT_KEYS:
        validated = _safe_count(metadata.get(key))
        if validated is not None:
            result[key] = validated
    return result


# Closed by design. Adding a new internal event does not make it public: it
# must receive an explicit, privacy-reviewed presentation here first.
AUDIT_EVENT_PRESENTATIONS: dict[str, Presentation] = {
    # Account and sessions.
    "user.created": _p(
        AuditHistoryCategory.account,
        "Account created",
        "Your LifeFlow account was created.",
        AuditHistoryTone.success,
    ),
    "session.created": _p(
        AuditHistoryCategory.account,
        "Signed in",
        "A LifeFlow session was started.",
        AuditHistoryTone.success,
    ),
    "session.ended": _p(
        AuditHistoryCategory.account,
        "Signed out",
        "A LifeFlow session was ended.",
    ),
    "demo.started": _p(
        AuditHistoryCategory.account,
        "Demo data prepared",
        "LifeFlow prepared the private demo workspace.",
        AuditHistoryTone.success,
    ),
    "user.settings_updated": _p(
        AuditHistoryCategory.preferences,
        "Profile settings updated",
        "Your profile settings were changed.",
        AuditHistoryTone.success,
    ),
    # Connections and imported evidence.
    "account.connected": _p(
        AuditHistoryCategory.connections,
        "Connection added",
        "A provider connection was authorised.",
        AuditHistoryTone.success,
    ),
    "account.disconnected": _p(
        AuditHistoryCategory.connections,
        "Connection removed",
        "A provider connection was disconnected.",
        AuditHistoryTone.warning,
    ),
    "account.revoked": _p(
        AuditHistoryCategory.connections,
        "Connection access expired",
        "A provider rejected the saved connection access.",
        AuditHistoryTone.warning,
    ),
    "account.tokens_refreshed": _p(
        AuditHistoryCategory.connections,
        "Connection access refreshed",
        "Authorised provider access was refreshed.",
        AuditHistoryTone.success,
    ),
    "sync.completed": _p(
        AuditHistoryCategory.connections,
        "Connection sync completed",
        "LifeFlow refreshed imported evidence.",
        AuditHistoryTone.success,
    ),
    # Briefs and scheduled processing.
    "extraction.completed": _p(
        AuditHistoryCategory.briefs,
        "Evidence reviewed",
        "LifeFlow reviewed imported evidence for useful signals.",
        AuditHistoryTone.success,
    ),
    "brief.generated": _p(
        AuditHistoryCategory.briefs,
        "Brief generated",
        "LifeFlow prepared a new daily brief.",
        AuditHistoryTone.success,
    ),
    "scheduled_brief.enqueued": _p(
        AuditHistoryCategory.briefs,
        "Scheduled brief queued",
        "A scheduled brief was queued for preparation.",
    ),
    "scheduled_brief.succeeded": _p(
        AuditHistoryCategory.briefs,
        "Scheduled brief completed",
        "LifeFlow prepared the scheduled brief.",
        AuditHistoryTone.success,
    ),
    "scheduled_brief.skipped": _p(
        AuditHistoryCategory.briefs,
        "Scheduled brief skipped",
        "LifeFlow safely skipped a scheduled brief.",
        AuditHistoryTone.warning,
    ),
    "scheduled_brief.failed": _p(
        AuditHistoryCategory.briefs,
        "Scheduled brief failed",
        "LifeFlow could not prepare the scheduled brief.",
        AuditHistoryTone.failure,
    ),
    # Action proposals, approvals, and executions.
    "proposal.candidates_skipped": _p(
        AuditHistoryCategory.actions,
        "Unsafe action candidates skipped",
        "LifeFlow excluded action suggestions that did not pass composition rules.",
        AuditHistoryTone.warning,
    ),
    "proposal.created": _p(
        AuditHistoryCategory.actions,
        "Action proposed",
        "LifeFlow prepared an action for your review.",
        show_action_type=True,
    ),
    "proposal.updated": _p(
        AuditHistoryCategory.actions,
        "Action proposal refreshed",
        "LifeFlow updated an unapproved action proposal.",
        show_action_type=True,
    ),
    "proposal.edited": _p(
        AuditHistoryCategory.actions,
        "Action edited",
        "You changed an action before approval.",
        show_action_type=True,
    ),
    "proposal.approved": _p(
        AuditHistoryCategory.actions,
        "Action approved",
        "You approved the exact action shown for execution.",
        AuditHistoryTone.success,
        show_action_type=True,
    ),
    "proposal.rejected": _p(
        AuditHistoryCategory.actions,
        "Action rejected",
        "You chose not to approve an action.",
        AuditHistoryTone.warning,
        show_action_type=True,
    ),
    "proposal.executing": _p(
        AuditHistoryCategory.actions,
        "Action execution started",
        "LifeFlow began the approved action.",
        show_action_type=True,
    ),
    "proposal.executed": _p(
        AuditHistoryCategory.actions,
        "Action completed",
        "LifeFlow completed the approved action.",
        AuditHistoryTone.success,
        show_action_type=True,
    ),
    "proposal.failed": _p(
        AuditHistoryCategory.actions,
        "Action failed",
        "LifeFlow could not complete the approved action.",
        AuditHistoryTone.failure,
        show_action_type=True,
    ),
    "proposal.expired": _p(
        AuditHistoryCategory.actions,
        "Action proposal expired",
        "An uncompleted action proposal expired safely.",
        AuditHistoryTone.warning,
        show_action_type=True,
    ),
    "approval.denied": _p(
        AuditHistoryCategory.actions,
        "Approval blocked",
        "LifeFlow blocked an approval that did not pass policy checks.",
        AuditHistoryTone.warning,
        show_action_type=True,
        show_reason=True,
    ),
    "approval.invalidated": _p(
        AuditHistoryCategory.actions,
        "Approval invalidated",
        "A change invalidated the earlier approval.",
        AuditHistoryTone.warning,
        show_action_type=True,
    ),
    "execution.started": _p(
        AuditHistoryCategory.actions,
        "Execution attempt recorded",
        "LifeFlow durably recorded the approved execution attempt.",
        show_action_type=True,
    ),
    "execution.succeeded": _p(
        AuditHistoryCategory.actions,
        "Execution confirmed",
        "The approved action was confirmed complete.",
        AuditHistoryTone.success,
        show_action_type=True,
    ),
    "execution.failed": _p(
        AuditHistoryCategory.actions,
        "Execution failed",
        "The approved action was confirmed unsuccessful.",
        AuditHistoryTone.failure,
        show_action_type=True,
        show_reason=True,
    ),
    "execution.uncertain": _p(
        AuditHistoryCategory.actions,
        "Execution needs review",
        "LifeFlow could not confirm the outcome and did not retry automatically.",
        AuditHistoryTone.warning,
        show_action_type=True,
        show_reason=True,
    ),
    "execution.denied": _p(
        AuditHistoryCategory.actions,
        "Execution blocked",
        "LifeFlow blocked an execution that did not match its approval.",
        AuditHistoryTone.warning,
        show_action_type=True,
        show_reason=True,
    ),
    "execution.replayed": _p(
        AuditHistoryCategory.actions,
        "Existing execution returned",
        "LifeFlow safely reused the recorded result instead of executing twice.",
        show_action_type=True,
    ),
    # Preferences and inferred memory.
    "preference.updated": _p(
        AuditHistoryCategory.preferences,
        "Preference updated",
        "A LifeFlow preference was changed.",
        AuditHistoryTone.success,
    ),
    "memory.candidate_created": _p(
        AuditHistoryCategory.preferences,
        "Memory suggestion created",
        "LifeFlow suggested a preference for your review.",
    ),
    "memory.candidate_updated": _p(
        AuditHistoryCategory.preferences,
        "Memory suggestion updated",
        "LifeFlow refreshed an unconfirmed preference suggestion.",
    ),
    "memory.edited": _p(
        AuditHistoryCategory.preferences,
        "Memory suggestion edited",
        "You edited a preference suggestion.",
    ),
    "memory.confirmed": _p(
        AuditHistoryCategory.preferences,
        "Memory suggestion confirmed",
        "You confirmed a preference suggestion.",
        AuditHistoryTone.success,
    ),
    "memory.dismissed": _p(
        AuditHistoryCategory.preferences,
        "Memory suggestion dismissed",
        "You dismissed a preference suggestion.",
        AuditHistoryTone.warning,
    ),
    "memory.deleted": _p(
        AuditHistoryCategory.preferences,
        "Saved memory deleted",
        "A saved preference memory was deleted.",
        AuditHistoryTone.warning,
    ),
    "memory.expired": _p(
        AuditHistoryCategory.preferences,
        "Memory suggestion expired",
        "An unconfirmed preference suggestion expired.",
    ),
    "memory.superseded": _p(
        AuditHistoryCategory.preferences,
        "Memory suggestion replaced",
        "A newer preference suggestion replaced an earlier one.",
    ),
    # User-requested and retention deletion operations. Fixed text deliberately
    # omits counts, scope identifiers, error details, and deletion metadata.
    "data.import_deletion_previewed": _p(
        AuditHistoryCategory.privacy,
        "Imported-data deletion reviewed",
        "You reviewed what an imported-data deletion would remove.",
    ),
    "data.import_deletion_requested": _p(
        AuditHistoryCategory.privacy,
        "Imported-data deletion requested",
        "You confirmed an imported-data deletion.",
        AuditHistoryTone.warning,
    ),
    "data.import_deletion_cancelled": _p(
        AuditHistoryCategory.privacy,
        "Imported-data deletion cancelled",
        "You cancelled an imported-data deletion before it began.",
    ),
    "data.import_deletion_started": _p(
        AuditHistoryCategory.privacy,
        "Imported-data deletion started",
        "LifeFlow started the confirmed deletion.",
        AuditHistoryTone.warning,
    ),
    "data.import_deletion_completed": _p(
        AuditHistoryCategory.privacy,
        "Imported-data deletion completed",
        "LifeFlow completed the confirmed deletion.",
        AuditHistoryTone.success,
        show_counts=True,
    ),
    "data.import_deletion_partially_failed": _p(
        AuditHistoryCategory.privacy,
        "Imported-data deletion partly completed",
        "Some confirmed data was deleted, but the operation needs review.",
        AuditHistoryTone.warning,
        show_reason=True,
        show_counts=True,
    ),
    "data.import_deletion_failed": _p(
        AuditHistoryCategory.privacy,
        "Imported-data deletion failed",
        "LifeFlow could not complete the confirmed deletion.",
        AuditHistoryTone.failure,
        show_reason=True,
        show_counts=True,
    ),
    "account.deletion_previewed": _p(
        AuditHistoryCategory.privacy,
        "Account deletion reviewed",
        "You reviewed what deleting your account would remove.",
    ),
    "account.deletion_requested": _p(
        AuditHistoryCategory.privacy,
        "Account deletion requested",
        "You confirmed account deletion.",
        AuditHistoryTone.warning,
    ),
    "account.deletion_cancelled": _p(
        AuditHistoryCategory.privacy,
        "Account deletion cancelled",
        "You cancelled account deletion before it began.",
    ),
    "account.deletion_started": _p(
        AuditHistoryCategory.privacy,
        "Account deletion started",
        "LifeFlow started the confirmed account deletion.",
        AuditHistoryTone.warning,
    ),
    "account.deletion_completed": _p(
        AuditHistoryCategory.privacy,
        "Account deletion completed",
        "LifeFlow completed account deletion.",
        AuditHistoryTone.success,
        show_counts=True,
    ),
    "account.deletion_partially_failed": _p(
        AuditHistoryCategory.privacy,
        "Account deletion partly completed",
        "Some account data was deleted, but the operation needs review.",
        AuditHistoryTone.warning,
        show_reason=True,
        show_counts=True,
    ),
    "account.deletion_failed": _p(
        AuditHistoryCategory.privacy,
        "Account deletion failed",
        "LifeFlow could not complete account deletion.",
        AuditHistoryTone.failure,
        show_reason=True,
        show_counts=True,
    ),
    "retention.operation_cancelled": _p(
        AuditHistoryCategory.privacy,
        "Retention cleanup cancelled",
        "You cancelled an automatic retention cleanup before it began.",
    ),
    "retention.operation_started": _p(
        AuditHistoryCategory.privacy,
        "Retention cleanup started",
        "LifeFlow started an automatic retention cleanup.",
    ),
    "retention.operation_completed": _p(
        AuditHistoryCategory.privacy,
        "Retention cleanup completed",
        "LifeFlow completed an automatic retention cleanup.",
        AuditHistoryTone.success,
        show_counts=True,
    ),
    "retention.operation_partially_failed": _p(
        AuditHistoryCategory.privacy,
        "Retention cleanup partly completed",
        "The automatic cleanup needs review.",
        AuditHistoryTone.warning,
        show_reason=True,
        show_counts=True,
    ),
    "retention.operation_failed": _p(
        AuditHistoryCategory.privacy,
        "Retention cleanup failed",
        "LifeFlow could not complete an automatic retention cleanup.",
        AuditHistoryTone.failure,
        show_reason=True,
        show_counts=True,
    ),
}
