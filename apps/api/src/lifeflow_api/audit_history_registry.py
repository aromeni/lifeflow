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


def _p(
    category: AuditHistoryCategory,
    title: str,
    summary: str,
    tone: AuditHistoryTone = AuditHistoryTone.neutral,
) -> Presentation:
    return Presentation(category=category, title=title, summary=summary, tone=tone)


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
    ),
    "proposal.updated": _p(
        AuditHistoryCategory.actions,
        "Action proposal refreshed",
        "LifeFlow updated an unapproved action proposal.",
    ),
    "proposal.edited": _p(
        AuditHistoryCategory.actions,
        "Action edited",
        "You changed an action before approval.",
    ),
    "proposal.approved": _p(
        AuditHistoryCategory.actions,
        "Action approved",
        "You approved the exact action shown for execution.",
        AuditHistoryTone.success,
    ),
    "proposal.rejected": _p(
        AuditHistoryCategory.actions,
        "Action rejected",
        "You chose not to approve an action.",
        AuditHistoryTone.warning,
    ),
    "proposal.executing": _p(
        AuditHistoryCategory.actions,
        "Action execution started",
        "LifeFlow began the approved action.",
    ),
    "proposal.executed": _p(
        AuditHistoryCategory.actions,
        "Action completed",
        "LifeFlow completed the approved action.",
        AuditHistoryTone.success,
    ),
    "proposal.failed": _p(
        AuditHistoryCategory.actions,
        "Action failed",
        "LifeFlow could not complete the approved action.",
        AuditHistoryTone.failure,
    ),
    "proposal.expired": _p(
        AuditHistoryCategory.actions,
        "Action proposal expired",
        "An uncompleted action proposal expired safely.",
        AuditHistoryTone.warning,
    ),
    "approval.denied": _p(
        AuditHistoryCategory.actions,
        "Approval blocked",
        "LifeFlow blocked an approval that did not pass policy checks.",
        AuditHistoryTone.warning,
    ),
    "approval.invalidated": _p(
        AuditHistoryCategory.actions,
        "Approval invalidated",
        "A change invalidated the earlier approval.",
        AuditHistoryTone.warning,
    ),
    "execution.started": _p(
        AuditHistoryCategory.actions,
        "Execution attempt recorded",
        "LifeFlow durably recorded the approved execution attempt.",
    ),
    "execution.succeeded": _p(
        AuditHistoryCategory.actions,
        "Execution confirmed",
        "The approved action was confirmed complete.",
        AuditHistoryTone.success,
    ),
    "execution.failed": _p(
        AuditHistoryCategory.actions,
        "Execution failed",
        "The approved action was confirmed unsuccessful.",
        AuditHistoryTone.failure,
    ),
    "execution.uncertain": _p(
        AuditHistoryCategory.actions,
        "Execution needs review",
        "LifeFlow could not confirm the outcome and did not retry automatically.",
        AuditHistoryTone.warning,
    ),
    "execution.denied": _p(
        AuditHistoryCategory.actions,
        "Execution blocked",
        "LifeFlow blocked an execution that did not match its approval.",
        AuditHistoryTone.warning,
    ),
    "execution.replayed": _p(
        AuditHistoryCategory.actions,
        "Existing execution returned",
        "LifeFlow safely reused the recorded result instead of executing twice.",
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
    ),
    "data.import_deletion_partially_failed": _p(
        AuditHistoryCategory.privacy,
        "Imported-data deletion partly completed",
        "Some confirmed data was deleted, but the operation needs review.",
        AuditHistoryTone.warning,
    ),
    "data.import_deletion_failed": _p(
        AuditHistoryCategory.privacy,
        "Imported-data deletion failed",
        "LifeFlow could not complete the confirmed deletion.",
        AuditHistoryTone.failure,
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
    ),
    "account.deletion_partially_failed": _p(
        AuditHistoryCategory.privacy,
        "Account deletion partly completed",
        "Some account data was deleted, but the operation needs review.",
        AuditHistoryTone.warning,
    ),
    "account.deletion_failed": _p(
        AuditHistoryCategory.privacy,
        "Account deletion failed",
        "LifeFlow could not complete account deletion.",
        AuditHistoryTone.failure,
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
    ),
    "retention.operation_partially_failed": _p(
        AuditHistoryCategory.privacy,
        "Retention cleanup partly completed",
        "The automatic cleanup needs review.",
        AuditHistoryTone.warning,
    ),
    "retention.operation_failed": _p(
        AuditHistoryCategory.privacy,
        "Retention cleanup failed",
        "LifeFlow could not complete an automatic retention cleanup.",
        AuditHistoryTone.failure,
    ),
}
