"""Tests for the analysis rules.

Run with:  python -m pytest -q
"""

from datetime import datetime, timedelta, timezone

from workspace_audit.analyze import (
    FLAG_ADMIN_NO_2SV,
    FLAG_INACTIVE,
    FLAG_NEVER_LOGGED_IN,
    FLAG_NO_2SV,
    FLAG_SUSPENDED_ACTIVE_LICENSE,
    analyze,
    evaluate,
)
from workspace_audit.models import WorkspaceUser, _parse_ts

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def make_user(**kwargs) -> WorkspaceUser:
    defaults = dict(
        primary_email="user@example.com",
        full_name="Test User",
        org_unit_path="/Employees",
        two_step_enrolled=True,
        creation_time=NOW - timedelta(days=500),
        last_login_time=NOW - timedelta(days=1),
    )
    defaults.update(kwargs)
    return WorkspaceUser(**defaults)


def test_recent_login_is_clean():
    user = evaluate(make_user(), inactive_days=90, now=NOW)
    assert user.flags == []
    assert user.recommendation == ""


def test_dormant_account_is_flagged():
    user = evaluate(
        make_user(last_login_time=NOW - timedelta(days=120)), inactive_days=90, now=NOW
    )
    assert FLAG_INACTIVE in user.flags
    assert user.days_since_login == 120


def test_threshold_is_inclusive():
    user = evaluate(
        make_user(last_login_time=NOW - timedelta(days=90)), inactive_days=90, now=NOW
    )
    assert FLAG_INACTIVE in user.flags


def test_new_account_gets_a_grace_period():
    """A hire from last week has not had a chance to sign in yet."""
    user = evaluate(
        make_user(last_login_time=None, creation_time=NOW - timedelta(days=3)),
        inactive_days=90,
        now=NOW,
    )
    assert FLAG_NEVER_LOGGED_IN not in user.flags


def test_old_account_that_never_signed_in_is_flagged():
    user = evaluate(
        make_user(last_login_time=None, creation_time=NOW - timedelta(days=300)),
        inactive_days=90,
        now=NOW,
    )
    assert FLAG_NEVER_LOGGED_IN in user.flags


def test_admin_without_2sv_outranks_everything():
    user = evaluate(
        make_user(is_admin=True, two_step_enrolled=False), inactive_days=90, now=NOW
    )
    assert FLAG_ADMIN_NO_2SV in user.flags
    assert "2SV" in user.recommendation


def test_delegated_admin_counts_as_privileged():
    user = evaluate(
        make_user(is_delegated_admin=True, two_step_enrolled=False),
        inactive_days=90,
        now=NOW,
    )
    assert FLAG_ADMIN_NO_2SV in user.flags


def test_suspended_account_is_not_nagged_about_2sv():
    """A suspended user cannot enrol in 2SV -- flagging it is noise."""
    user = evaluate(
        make_user(suspended=True, two_step_enrolled=False), inactive_days=90, now=NOW
    )
    assert FLAG_NO_2SV not in user.flags


def test_suspended_but_not_archived_still_costs_money():
    user = evaluate(
        make_user(suspended=True, archived=False), inactive_days=90, now=NOW
    )
    assert FLAG_SUSPENDED_ACTIVE_LICENSE in user.flags


def test_archived_account_is_in_the_correct_state():
    user = evaluate(
        make_user(suspended=True, archived=True, last_login_time=NOW - timedelta(days=2)),
        inactive_days=90,
        now=NOW,
    )
    assert FLAG_SUSPENDED_ACTIVE_LICENSE not in user.flags


def test_epoch_timestamp_means_never_signed_in():
    """The Admin SDK returns 1970-01-01 instead of omitting lastLoginTime."""
    assert _parse_ts("1970-01-01T00:00:00.000Z") is None
    assert _parse_ts("2026-05-14T09:30:00.000Z") is not None


def test_summary_counts_and_ordering():
    users = [
        make_user(primary_email="clean@example.com"),
        make_user(
            primary_email="dormant@example.com",
            last_login_time=NOW - timedelta(days=200),
        ),
        make_user(
            primary_email="risky@example.com",
            is_admin=True,
            two_step_enrolled=False,
        ),
    ]
    evaluated, summary = analyze(users, inactive_days=90, now=NOW)

    assert summary.total == 3
    assert summary.inactive == 1
    assert summary.admins_without_2sv == 1
    # Worst finding must be first so the top of the CSV is actionable.
    assert evaluated[0].primary_email == "risky@example.com"
