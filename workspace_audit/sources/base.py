"""Source interface.

Every source returns the same ``WorkspaceUser`` objects, so the analysis and
reporting layers never learn where the data came from. That is what lets the
tool run against a live tenant or against a local fixture with no code change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from workspace_audit.models import WorkspaceUser


class UserSource(ABC):
    """Anything that can produce Workspace accounts."""

    name: str = "unknown"

    @abstractmethod
    def fetch_users(self) -> Iterator[WorkspaceUser]:
        """Yield every account in the tenant, suspended ones included."""
        raise NotImplementedError
