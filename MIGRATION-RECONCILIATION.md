# Migration reconciliation for fresh databases

> Historical migration checkpoint: application failures recorded below have since been reconciled. See BETA-CONTRACT.md for the current application contract and validation.

Source: main at `fb0fcf9862d86d91bef88ea025a74413fc1c6e26`.
Git merged sibling commits `ee92d38` (beta/account administration) and
`67e18d6` (company/call intelligence and account lifecycle). Both introduced
`q735136fac16` after `p624025efb15`. Call attributes on this main already
has the distinct ID `r846247adb17`; account administration is `r846247abd17`.

The reconciled graph retains every migration:

```text
existing base through p624025efb15
  |-- q735136fac16 beta --> r846247abd17 account administration ---------|
  |-- 9c2a7e6b410f company --> r846247adb17 attributes                    |
          --> s957358bec18 exclusions --> t068469cfd19 pilot audit -----|
                                      6d8f2a91c043 merge
                                               |
                                      u179570dfe20 lifecycle (head)
```

Company context receives revision `9c2a7e6b410f`; its parent stays
`p624025efb15`. Call attributes now points to that unique company revision.
The explicit merge has parents `r846247abd17` and `t068469cfd19`.
Lifecycle now follows the merge, so its shared schema dependencies are
guaranteed regardless of which parallel branch runs first.

Beta owns `organizations.suspended` and `platform_administrators`;
account administration owns `users.created_at`. Lifecycle retains
`last_login_at`, `account_events` and removal of the suspension default,
and reuses those three ancestor-owned objects instead of recreating them.
Lifecycle downgrade retains shared objects and restores the suspension default.
Existing guards against discarding account/audit history remain.
All beta grants, platform invitation metadata/events, company annotations,
call attributes/correction events, exclusions and pilot audits remain present.

The source merge also omitted `BetaAccess`, `PlatformEvent` and the
`Organization.beta_access` relationship from ORM metadata while retaining their
migrations, imports and tests. These exact schema mappings are restored from
`ee92d38`. Otherwise Alembic's drift check proposes removing the preserved beta
tables and the application fails to import. No route or access-policy change
is included.

This repair targets fresh databases. An installation that has already applied
one of the ambiguous old revisions requires a separate schema/history audit;
revision strings alone cannot identify which old branch actually ran.
Do not stamp or delete history to bypass that audit.

From `backend`, with an explicitly selected disposable PostgreSQL database:

```powershell
python -m alembic heads
python -m alembic branches
python -m alembic history --verbose
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -m pytest -q --tb=short
python -m ruff check app tests migrations
```

`DATABASE_URL` selects the Alembic target. `SIGNAL_TEST_POSTGRES_URL` enables
PostgreSQL regression tests, which create and remove random isolated schemas
inside the selected disposable database. Do not point test variables at production.
Expected single head: `u179570dfe20`.

The graph regression parses every migration file before loading Alembic, checks
unique IDs and complete base/head reachability. Database regression tests
exercise both branch orders, compare all model tables and columns, run Alembic
schema drift detection, repeat upgrade, verify shared account/beta data survives
lifecycle, and check lifecycle rollback preserves ancestor-owned objects.

Local PostgreSQL 16.6 validation passed: a fresh `alembic upgrade head`, repeated
upgrade, current/head agreement, and `alembic check`. All 37 application tables
and 301 columns match model names and nullability. The database regression file
passed all 25 tests with PostgreSQL integration enabled (no skipped integration
cases), including SQLite/PostgreSQL branch-order and legacy-data checks.

The full backend suite is not green. The normal run stops collecting
`test_beta_foundation.py` because the existing entitlement service has no
`INACTIVE_ACCESS_MESSAGE`. A diagnostic full run with
`--continue-on-collection-errors` finished with **411 passed, 21 failed,
9 errors**. Other causes are the platform provisioning signature mismatch and
unregistered/missing platform endpoints. Full backend Ruff reports six existing
errors in account routes, team routes and the browser-test bootstrap. Ruff passes
for all changed Python files. These application policy/routing issues are outside
this migration repair and remain unchanged; passing migrations do not establish
application release readiness.
