# Database

`prisma/schema.prisma` models the public edition projection and normalized evidence,
clustering, scoring, translation and run audit tables. SQL migrations also maintain
PostgreSQL checks and expression GIN indexes that Prisma cannot fully represent.

For a new disposable database only:

```powershell
$env:DATABASE_URL='postgresql://digest:digest@localhost:5432/digest'
npm run db:generate
npm run db:migrate
npm run db:seed
npm run db:seed
node --test packages/db/test-idempotency.cjs
```

The fixture seed uses stable IDs and upserts; repeated execution preserves edition
count. All seed content is labeled synthetic and uses reserved example.org URLs.
Production publication belongs to the Python pipeline, which validates both locales
and persists evidence atomically before exposing a published edition.

`prisma validate` and client generation do not prove database connectivity or apply
migrations. PostgreSQL execution was verified locally; a disposable CI service job is configured.

## Existing MVP-3 instance

The local instance holds 140 real raw articles, three published bilingual editions
(2026-11-06, 2026-11-09 and 2026-11-13), seven retained issue rows and one archived revision.
Do not rerun migrations, seed or backfill as a recovery step for this existing instance.
The setup and test commands here are for explicitly prepared disposable environments.
Database files and runtime evidence remain ignored; a Git checkpoint is not a data backup.

## Portable Windows test instance

Supply trusted portable PostgreSQL binaries (including `pg_trgm`) without installing a service:

```powershell
./packages/db/local-postgres.ps1 -BinDirectory ./artifacts/postgres/bin
$env:DATABASE_URL='postgresql://digest@127.0.0.1:55432/digest'
$env:TEST_DATABASE_URL='postgresql://digest@127.0.0.1:55432/digest_pipeline_test'
npm run db:migrate
node --test packages/db/test-idempotency.cjs
python -m unittest discover -s tests -p 'test_postgres*.py' -v
./packages/db/local-postgres.ps1 -Action stop -BinDirectory ./artifacts/postgres/bin
```

Windows fallback used for local verification: npm-distributed PostgreSQL 18.6
from `@embedded-postgres/windows-x64@18.6.0-beta.19` (upstream
`github.com/leinelissen/embedded-postgres`). Keep it outside workspace dependencies:

```powershell
New-Item -ItemType Directory artifacts/postgres -Force
npm pack @embedded-postgres/windows-x64@18.6.0-beta.19 --pack-destination artifacts/postgres --ignore-scripts --loglevel error
tar -xzf artifacts/postgres/embedded-postgres-windows-x64-18.6.0-beta.19.tgz -C artifacts/postgres
./packages/db/local-postgres.ps1 -BinDirectory ./artifacts/postgres/package/native/bin
```

The npm archive includes `initdb`, `postgres` and `pg_ctl`, but omits `psql`;
the startup script uses the declared Python psycopg dependency to create databases.

The script confines its data/logs to ignored `artifacts/local-postgres`, listens only
on loopback, and uses trust authentication for this disposable test instance.
The Python tests apply migrations in unique schemas and drop those schemas afterward.
Leave `TEST_DATABASE_URL` unset for verification that must not write to PostgreSQL.

## Correcting historical editions

`edition_revisions` preserves exact previous edition JSON and its matching historical
review receipt. SQL rejects updates/deletions of archived revisions. No foreign key
ties history to the mutable current edition row.
Inside the lead Store's replacement transaction, call
`archive_current_issue(db, issue_id, expected_content=old_issue)` from `revisions.py`
after validating replacement content. The helper locks the current published row,
archives it and leaves the current edition untouched. A failed replacement rolls
back the archive too. The replacement review belongs to the new publication;
never supply it as the previous version's review.

Read-only coverage audit: `python packages/db/audit_backfill.py --start 2026-11-01 --end 2026-11-13`.
It uses exact Europe/Berlin calendar days; it does not assume that an older source
is eligible merely because it was collected or published in an edition later.
