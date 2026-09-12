"""Analysis layer: turn raw accounts into findings.

Rules live here and nowhere else, so adding a check never means touching the
source or the report code.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from workspace_audit.models import WorkspaceUser

DEFAULT_INACTIVE_DAYS = 90

# Flags, roughly in order of how urgently they need a human to look.
FLAG_ADMIN_NO_2SV = "ADMIN_WITHOUT_2SV"
FLAG_NEVER_LOGGED_IN = "NEVER_LOGGED_IN"
FLAG_INACTIVE = "INACTIVE"
FLAG_NO_2SV = "NO_2SV"
FLAG_SUSPENDED_ACTIVE_LICENSE = "SUSPENDED_NOT_ARCHIVED"

# Accounts created recently have not had a fair chance to sign in yet.
GRACE_PERIOD_DAYS = 14


@dataclass
class AuditSummary:
    total: int = 0
    active: int = 0
    suspended: int = 0
    admins: int = 0
    inactive: int = 0
    never_logged_in: int = 0
    without_2sv: int = 0
    admins_without_2sv: int = 0
    flag_counts: Counter = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.flag_counts is None:
            self.flag_counts = Counter()


def _days_since(moment: datetime | None, now: datetime) -> int | None:
    if moment is None:
        return None
    return max((now - moment).days, 0)


def evaluate(user: WorkspaceUser, inactive_days: int, now: datetime) -> WorkspaceUser:
    """Attach days_since_login, flags and a recommendation to one account."""
    user.days_since_login = _days_since(user.last_login_time, now)
    age_days = _days_since(user.creation_time, now)
    flags: list[str] = []

    is_new = age_days is not None and age_days <= GRACE_PERIOD_DAYS

    if user.never_logged_in and not is_new:
        flags.append(FLAG_NEVER_LOGGED_IN)
    elif user.days_since_login is not None and user.days_since_login >= inactive_days:
        flags.append(FLAG_INACTIVE)

    if not user.two_step_enrolled and not user.suspended:
        flags.append(FLAG_NO_2SV)
        if user.is_admin or user.is_delegated_admin:
            flags.append(FLAG_ADMIN_NO_2SV)

    # A suspended account keeps consuming its license until it is archived or
    # deleted. This is the quietest line item on most Workspace invoices.
    if user.suspended and not user.archived:
        flags.append(FLAG_SUSPENDED_ACTIVE_LICENSE)

    user.flags = flags
    user.recommendation = _recommend(user, flags)
    return user


def _recommend(user: WorkspaceUser, flags: list[str]) -> str:
    if FLAG_ADMIN_NO_2SV in flags:
        return "Enforce 2SV before anything else - privileged account is unprotected"
    if FLAG_SUSPENDED_ACTIVE_LICENSE in flags:
        return "Archive or delete - suspended account still holds a paid license"
    if FLAG_NEVER_LOGGED_IN in flags:
        return "Confirm the account is still needed - never signed in"
    if FLAG_INACTIVE in flags:
        if user.is_admin or user.is_delegated_admin:
            return "Review admin role - privileged account is dormant"
        return "Candidate for license reclaim - confirm with the manager first"
    if FLAG_NO_2SV in flags:
        return "Enrol in 2-step verification"
    return ""


def analyze(
    users: list[WorkspaceUser],
    inactive_days: int = DEFAULT_INACTIVE_DAYS,
    now: datetime | None = None,
) -> tuple[list[WorkspaceUser], AuditSummary]:
    now = now or datetime.now(timezone.utc)
    evaluated = [evaluate(user, inactive_days, now) for user in users]

    summary = AuditSummary(total=len(evaluated))
    for user in evaluated:
        if user.suspended:
            summary.suspended += 1
        else:
            summary.active += 1
        if user.is_admin or user.is_delegated_admin:
            summary.admins += 1
        for flag in user.flags:
            summary.flag_counts[flag] += 1

    counts = summary.flag_counts
    summary.inactive = counts[FLAG_INACTIVE]
    summary.never_logged_in = counts[FLAG_NEVER_LOGGED_IN]
    summary.without_2sv = counts[FLAG_NO_2SV]
    summary.admins_without_2sv = counts[FLAG_ADMIN_NO_2SV]

    # Worst findings first, then longest dormant, so the top of the CSV is the
    # part worth acting on today.
    evaluated.sort(
        key=lambda u: (
            FLAG_ADMIN_NO_2SV not in u.flags,
            not u.flags,
            -(u.days_since_login if u.days_since_login is not None else 10**6),
        )
    )
    return evaluated, summary
