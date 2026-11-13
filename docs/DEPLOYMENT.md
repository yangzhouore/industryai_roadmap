# Deployment and operations

## Current local deployment

The local PostgreSQL instance holds 140 real articles, three bilingual publications
(November 6, 9 and 13, 2026), and the previous November 13 edition/review in append-only history.
Six reviewed publisher feeds are enabled for opt-in local metadata research.
Classification uses `gpt-6-luna`; generation and independent review use `gpt-6.1-terra`.
Public hosting, email and unattended paid publication remain inactive.

## Resume the website

- Use the existing database; recovery does not require migrations, seed or backfill.
- Install dependencies with `npm ci` if needed; generate the client with `npm run db:generate`.
- Export the existing `DATABASE_URL` securely and set `DATA_MODE=database`.
- Next.js loads `apps/web/.env.local`; it does not load root `.env.local` automatically.
- Run `npm run dev`, or `npm run build` followed by `npm run start --workspace apps/web`.
- Check EN/ZH homepage, dated digests, source notebooks, archive, search, RSS, sitemap and robots.
- The Python live commands load supported settings from ignored root `.env.local`.
- Reading published content needs database access but no OpenAI API calls.

## Workflows and publication

- `.github/workflows/check.yml` verifies offline code and a disposable PostgreSQL service.
- `.github/workflows/dry-run.yml` schedules offline fixture validation; it never publishes news.
- Offline scheduled runs write `artifacts/pipeline-status.json`, retained by Actions even after failures.
- Paid `.github/workflows/live.yml` runs require `LIVE_NEWS_ENABLED=true`; scheduled runs also require `UNATTENDED_PAID_APPROVED=true`.
- Live workflow secrets/variables need explicit review before remote activation; local settings do not configure GitHub.
- MVP-4 `pipeline:daily -- run --dry-run` and compatibility `pipeline:live -- --dry-run` perform read-only stored-evidence planning.
- These dry-runs never collect, reserve budget, call the API or publish. See [daily operations](MVP4_OPERATIONS.md).
- Publication validates both locales and a matching review receipt, and stores evidence transactionally.
- Failed-review drafts stay private. Historical replacement archives the exact prior edition and matching review.
- Completed historical backfill is not a routine startup or health-check command.
- The daily target is 07:00 Europe/Berlin with DST, durable resume and a USD 2 monthly application ceiling.
- Paid scheduled execution requires both local configuration approval and the process approval flag; defaults remain disabled.

## Security and release authority

Keep API/database credentials server-side in ignored environment files or a secrets manager.
Restrict local credential files to the account running the application, SYSTEM and necessary administrators.
Git checkpoints exclude credentials, database storage, runtime responses, caches and build output.
Keep database backups separate from source control; a Git commit is not a database backup.
Before production release, review source reuse permissions, backups, migrations, rate/cost limits,
error monitoring, metadata, bilingual parity and a safe publication rollback procedure.
The reviewed feed scope is local noncommercial metadata research, not blanket republication permission.
Never push, publicly deploy, enable paid jobs or send email without explicit user authorization.
