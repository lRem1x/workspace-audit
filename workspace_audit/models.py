"""Domain model for a Google Workspace account."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _parse_ts(value: str | None) -> datetime | None:
    """Parse an Admin SDK RFC 3339 timestamp.

    The API returns the Unix epoch (1970-01-01) for accounts that have never
    signed in, rather than omitting the field. Treat that as "never".
    """
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed.year <= 1970:
        return None
    return parsed


@dataclass
class WorkspaceUser:
    primary_email: str
    full_name: str
    org_unit_path: str
    suspended: bool = False
    archived: bool = False
    is_admin: bool = False
    is_delegated_admin: bool = False
    two_step_enrolled: bool = False
    two_step_enforced: bool = False
    creation_time: datetime | None = None
    last_login_time: datetime | None = None

    # Populated by the analysis layer.
    days_since_login: int | None = None
    flags: list[str] = field(default_factory=list)
    recommendation: str = ""

    @property
    def never_logged_in(self) -> bool:
        return self.last_login_time is None

    @classmethod
    def from_api(cls, payload: dict) -> "WorkspaceUser":
        """Build a user from an Admin SDK ``users.list`` resource."""
        name = payload.get("name") or {}
        return cls(
            primary_email=payload.get("primaryEmail", ""),
            full_name=name.get("fullName", ""),
            org_unit_path=payload.get("orgUnitPath", "/"),
            suspended=bool(payload.get("suspended", False)),
            archived=bool(payload.get("archived", False)),
            is_admin=bool(payload.get("isAdmin", False)),
            is_delegated_admin=bool(payload.get("isDelegatedAdmin", False)),
            two_step_enrolled=bool(payload.get("isEnrolledIn2Sv", False)),
            two_step_enforced=bool(payload.get("isEnforcedIn2Sv", False)),
            creation_time=_parse_ts(payload.get("creationTime")),
            last_login_time=_parse_ts(payload.get("lastLoginTime")),
        )
