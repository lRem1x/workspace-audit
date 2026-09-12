"""Offline source: a local JSON fixture shaped like an Admin SDK response.

Lets the tool be cloned and run in one command, with no Google project, no
service account and no tenant. The fixture is entirely synthetic.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

from workspace_audit.models import WorkspaceUser
from workspace_audit.sources.base import UserSource

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "data" / "mock_users.json"


class MockSource(UserSource):
    name = "mock"

    def __init__(self, fixture: str | Path | None = None) -> None:
        self.fixture = Path(fixture) if fixture else DEFAULT_FIXTURE

    def fetch_users(self) -> Iterator[WorkspaceUser]:
        if not self.fixture.exists():
            raise SystemExit(f"Fixture not found: {self.fixture}")

        with self.fixture.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        # Timestamps are stored as day offsets so the fixture never goes stale:
        # a "last login 5 days ago" account stays 5 days ago whenever you run it.
        now = datetime.now(timezone.utc)
        for record in payload.get("users", []):
            record = dict(record)
            for key in ("lastLoginTime", "creationTime"):
                offset = record.pop(f"{key}DaysAgo", None)
                if offset is None:
                    continue
                if offset < 0:  # negative means "never signed in"
                    record[key] = "1970-01-01T00:00:00.000Z"
                else:
                    stamp = now - timedelta(days=offset)
                    record[key] = stamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            yield WorkspaceUser.from_api(record)
