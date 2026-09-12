"""Live source: Google Admin SDK Directory API.

Requires a service account with domain-wide delegation and the read-only
directory scope, plus a super-admin address to impersonate. Nothing here is
executed in mock mode, so the tool runs end to end without credentials.

Scope needed (read-only on purpose -- this tool never writes):
    https://www.googleapis.com/auth/admin.directory.user.readonly
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from workspace_audit.models import WorkspaceUser
from workspace_audit.sources.base import UserSource

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/admin.directory.user.readonly"]
PAGE_SIZE = 500  # Admin SDK maximum.

# Only the fields the audit actually uses. Narrowing the projection keeps the
# response small and avoids pulling personal data the tool has no use for.
FIELDS = (
    "nextPageToken,users("
    "primaryEmail,name/fullName,orgUnitPath,suspended,archived,"
    "isAdmin,isDelegatedAdmin,isEnrolledIn2Sv,isEnforcedIn2Sv,"
    "creationTime,lastLoginTime)"
)


class GoogleDirectorySource(UserSource):
    name = "google-admin-sdk"

    def __init__(
        self,
        credentials_file: str,
        admin_email: str,
        customer_id: str = "my_customer",
    ) -> None:
        self.credentials_file = credentials_file
        self.admin_email = admin_email
        self.customer_id = customer_id

    def _build_service(self):
        # Imported lazily so mock mode has no third-party dependency at all.
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "Live mode needs the Google client libraries:\n"
                "    pip install -r requirements.txt"
            ) from exc

        creds = service_account.Credentials.from_service_account_file(
            self.credentials_file, scopes=SCOPES
        )
        # Domain-wide delegation: the service account acts as a real admin.
        delegated = creds.with_subject(self.admin_email)
        return build("admin", "directory_v1", credentials=delegated, cache_discovery=False)

    def fetch_users(self) -> Iterator[WorkspaceUser]:
        service = self._build_service()
        request = service.users().list(
            customer=self.customer_id,
            maxResults=PAGE_SIZE,
            orderBy="email",
            projection="full",
            showDeleted="false",
            fields=FIELDS,
        )

        page = 0
        while request is not None:
            response = request.execute()
            page += 1
            users = response.get("users", [])
            log.debug("page %s: %s accounts", page, len(users))
            for payload in users:
                yield WorkspaceUser.from_api(payload)
            # list_next returns None once the last page has been consumed.
            request = service.users().list_next(request, response)
