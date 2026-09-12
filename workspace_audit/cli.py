"""Command line entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from workspace_audit.analyze import DEFAULT_INACTIVE_DAYS, analyze
from workspace_audit.report import print_summary, write_csv
from workspace_audit.sources.base import UserSource
from workspace_audit.sources.mock import MockSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace-audit",
        description=(
            "Audit Google Workspace accounts for dormant licences and missing "
            "2-step verification."
        ),
    )
    parser.add_argument(
        "--source",
        choices=("mock", "api"),
        default="mock",
        help="mock reads a local fixture (default); api queries a live tenant",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_INACTIVE_DAYS,
        metavar="N",
        help=f"days without a sign-in before an account counts as inactive (default: {DEFAULT_INACTIVE_DAYS})",
    )
    parser.add_argument(
        "--output",
        default="reports/workspace-audit.csv",
        metavar="PATH",
        help="where to write the CSV (default: reports/workspace-audit.csv)",
    )
    parser.add_argument(
        "--fixture",
        metavar="PATH",
        help="alternative JSON fixture for mock mode",
    )
    parser.add_argument(
        "--credentials",
        default=os.environ.get("WORKSPACE_AUDIT_CREDENTIALS"),
        metavar="PATH",
        help="service account JSON key (api mode); or set WORKSPACE_AUDIT_CREDENTIALS",
    )
    parser.add_argument(
        "--admin-email",
        default=os.environ.get("WORKSPACE_AUDIT_ADMIN"),
        metavar="EMAIL",
        help="super admin to impersonate (api mode); or set WORKSPACE_AUDIT_ADMIN",
    )
    parser.add_argument(
        "--customer-id",
        default="my_customer",
        metavar="ID",
        help="Workspace customer ID (api mode, default: my_customer)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser


def build_source(args: argparse.Namespace) -> UserSource:
    if args.source == "mock":
        return MockSource(args.fixture)

    if not args.credentials or not args.admin_email:
        raise SystemExit(
            "api mode needs --credentials and --admin-email "
            "(or WORKSPACE_AUDIT_CREDENTIALS / WORKSPACE_AUDIT_ADMIN).\n"
            "Run with --source mock to try the tool without a tenant."
        )

    from workspace_audit.sources.google_api import GoogleDirectorySource

    return GoogleDirectorySource(
        credentials_file=args.credentials,
        admin_email=args.admin_email,
        customer_id=args.customer_id,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    source = build_source(args)
    users = list(source.fetch_users())
    if not users:
        print("No accounts returned.", file=sys.stderr)
        return 1

    users, summary = analyze(users, inactive_days=args.days)
    path = write_csv(users, args.output)
    print_summary(summary, args.days, source.name)
    print(f"CSV written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
