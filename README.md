# workspace-audit

Finds dormant licences and 2-step verification gaps in a Google Workspace tenant, and writes the result as a CSV you can hand to a manager or a finance team.

**Runs with no credentials and no tenant.** A synthetic fixture ships with the repo, so you can clone it and see real output in two commands.

---

## The problem

In a tenant of a couple of hundred accounts, three things quietly go wrong:

- **People stop using accounts, but the licences keep billing.** Nobody notices, because nothing breaks.
- **Suspended accounts still hold a paid licence** until somebody archives or deletes them. Offboarding usually stops at "suspended".
- **Privileged accounts drift out of 2SV coverage** - a super admin without 2-step verification is the single worst finding in a Workspace tenant, and the admin console does not put it in front of you.

The Admin console can answer each of these one screen at a time. It cannot produce a single sorted list of what to act on this week, and it cannot be scheduled.

I was running this review by hand, roughly once a quarter, across a multi-domain tenant. It took an afternoon and the results were never comparable between runs. This tool does the same review in about a second and produces a stable, diffable artefact.

## What it produces

```
Workspace audit  (mock)
----------------------------------------------
Accounts total                            44
  active                                  41
  suspended                                3
  with admin privileges                    3
----------------------------------------------
Inactive (>= 90 days)                      8
Never signed in                            2
Without 2SV                                5
Admins without 2SV                         1
----------------------------------------------
!! 1 privileged account(s) have no 2SV - fix first
-> 10 licence(s) worth reviewing for reclaim

CSV written to reports/workspace-audit.csv
```

And a CSV, worst findings first:

| email | org_unit | status | admin | 2sv | last_login | days | flags | recommendation |
|---|---|---|---|---|---|---|---|---|
| oleksii.verkhovyna@... | /Employees/Engineering | active | yes | off | 2026-09-09 | 3 | `NO_2SV;ADMIN_WITHOUT_2SV` | Enforce 2SV before anything else |
| yaroslav.nedbailo@... | /Contractors | active | no | on | never | | `NEVER_LOGGED_IN` | Confirm the account is still needed |
| kateryna.zvilnena@... | /Employees/Support | suspended | no | on | 2025-08-06 | 402 | `INACTIVE;SUSPENDED_NOT_ARCHIVED` | Archive or delete - still holds a paid licence |

The ordering is the point. The first rows are what you do today; the rest is the backlog.

## Try it

```bash
git clone https://github.com/lRem1x/workspace-audit.git
cd workspace-audit
python -m workspace_audit --source mock
```

No Google project, no service account, no dependencies beyond the standard library.

```bash
# stricter threshold
python -m workspace_audit --source mock --days 60

# choose where the CSV lands
python -m workspace_audit --source mock --output reports/q3.csv
```

## Run it against a real tenant

Read-only, by design. The tool never writes to Workspace.

1. Create a GCP project and a service account.
2. Enable the **Admin SDK API**.
3. In `Admin console -> Security -> Access and data control -> API controls -> Domain-wide delegation`, authorise the service account's client ID for one scope:
   ```
   https://www.googleapis.com/auth/admin.directory.user.readonly
   ```
4. Download the service account key and point the tool at it:

```bash
export WORKSPACE_AUDIT_CREDENTIALS=/path/to/key.json
export WORKSPACE_AUDIT_ADMIN=admin@yourdomain.com

pip install -r requirements.txt
python -m workspace_audit --source api --days 90
```

> The service account key is a credential. Keep it outside the repository - `.gitignore` already excludes `*.json` at the root and the `credentials/` directory.

## Checks

| Flag | Meaning | Why it matters |
|---|---|---|
| `ADMIN_WITHOUT_2SV` | Privileged account, no 2-step verification | Highest-value target in the tenant |
| `NEVER_LOGGED_IN` | Account older than 14 days that has never signed in | Provisioned and forgotten; usually a full licence |
| `INACTIVE` | No sign-in for N days (default 90) | Licence reclaim candidate |
| `NO_2SV` | Active account without 2-step verification | Compliance gap |
| `SUSPENDED_NOT_ARCHIVED` | Suspended but still consuming a licence | Offboarding stopped halfway |

Two deliberate exceptions, both of which exist because the first version produced noise:

- **New accounts get a 14-day grace period.** Somebody who joined last week has not had a chance to sign in, and flagging them trains people to ignore the report.
- **Suspended accounts are not flagged for missing 2SV.** They cannot enrol. The finding would be unactionable.

## How it is put together

```
workspace_audit/
  models.py            WorkspaceUser + Admin SDK timestamp parsing
  sources/
    base.py            the interface every source implements
    google_api.py      live tenant, paginated, read-only scope
    mock.py            local JSON fixture
  analyze.py           all the rules live here
  report.py            CSV + console summary
  cli.py               argument parsing
```

Sources are swappable because analysis and reporting never see where the data came from. That is what makes the offline mode possible without a parallel code path, and it is what would make a second source - an exported CSV, a different provider - a single file rather than a rewrite.

## Notes from building it

- **`lastLoginTime` is never absent.** For an account that has never signed in, the Admin SDK returns the Unix epoch rather than omitting the field. Naive parsing produces "last login: 1970-01-01" and an inactivity figure around 20,000 days. `models._parse_ts` treats anything at or before 1970 as *never*.
- **Pagination is not optional.** `maxResults` caps at 500. Past that, a single `users().list()` call silently returns a partial tenant, and the audit under-reports. `list_next()` handles the token.
- **`projection=full` plus a narrow `fields` mask.** The fields the audit needs are not all in the basic projection, but requesting the full resource without a mask pulls a great deal of personal data the tool has no reason to touch.
- **`utf-8-sig` for the CSV.** Without the BOM, Excel on Windows mangles non-ASCII names, and the report goes to people who open it in Excel.

## Tests

```bash
pip install pytest
python -m pytest -q
```

12 tests covering the rules, the grace period, the epoch-timestamp case and the output ordering.

## Data

`data/mock_users.json` is entirely synthetic - invented names on `example.com`. Timestamps are stored as day offsets rather than fixed dates, so the fixture never goes stale: an account that is "120 days dormant" stays 120 days dormant whenever you run it.

## Licence

MIT
