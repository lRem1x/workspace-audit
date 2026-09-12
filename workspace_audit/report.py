"""Reporting layer: CSV on disk, summary on screen."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from workspace_audit.analyze import AuditSummary
from workspace_audit.models import WorkspaceUser

COLUMNS = [
    "email",
    "full_name",
    "org_unit",
    "status",
    "admin",
    "two_step_verification",
    "last_login",
    "days_since_login",
    "flags",
    "recommendation",
]


def _fmt_date(moment: datetime | None) -> str:
    return moment.strftime("%Y-%m-%d") if moment else "never"


def write_csv(users: list[WorkspaceUser], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # utf-8-sig so Excel on Windows opens the file with the right encoding
    # instead of mangling non-ASCII names.
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for user in users:
            if user.suspended:
                status = "archived" if user.archived else "suspended"
            else:
                status = "active"
            writer.writerow(
                [
                    user.primary_email,
                    user.full_name,
                    user.org_unit_path,
                    status,
                    "yes" if (user.is_admin or user.is_delegated_admin) else "no",
                    "on" if user.two_step_enrolled else "off",
                    _fmt_date(user.last_login_time),
                    user.days_since_login if user.days_since_login is not None else "",
                    ";".join(user.flags),
                    user.recommendation,
                ]
            )
    return path


def print_summary(summary: AuditSummary, inactive_days: int, source: str) -> None:
    line = "-" * 46
    print()
    print(f"Workspace audit  ({source})")
    print(line)
    print(f"{'Accounts total':<32}{summary.total:>12}")
    print(f"{'  active':<32}{summary.active:>12}")
    print(f"{'  suspended':<32}{summary.suspended:>12}")
    print(f"{'  with admin privileges':<32}{summary.admins:>12}")
    print(line)
    print(f"{f'Inactive (>= {inactive_days} days)':<32}{summary.inactive:>12}")
    print(f"{'Never signed in':<32}{summary.never_logged_in:>12}")
    print(f"{'Without 2SV':<32}{summary.without_2sv:>12}")
    print(f"{'Admins without 2SV':<32}{summary.admins_without_2sv:>12}")
    print(line)

    if summary.admins_without_2sv:
        print(f"!! {summary.admins_without_2sv} privileged account(s) have no 2SV - fix first")
    reclaimable = summary.inactive + summary.never_logged_in
    if reclaimable:
        print(f"-> {reclaimable} licence(s) worth reviewing for reclaim")
    print()
