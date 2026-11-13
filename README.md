# Industrial AI Digest

Original bilingual industrial intelligence site. Normal pages show only real validated publications.

## Current MVP-4 state

- PostgreSQL holds 140 real source articles and three published bilingual digests: November 6, 9 and 13, 2026.
- The previous November 13 edition and its review are preserved in append-only revision history.
- Six reviewed publisher feeds are enabled for opt-in local metadata collection.
- Classification uses `gpt-6-luna`; generation and independent review use `gpt-6.1-terra`.
- Public hosting, email delivery and unattended paid publication remain inactive.
- See [MVP-3 report](docs/MVP3_BACKFILL_REPORT.md) for coverage limits and historical execution evidence.
- MVP-4 adds Berlin scheduling, transactional monthly budgets, resumable editorial stages and operational status.
- Automated paid execution remains disabled. See [daily operations](docs/MVP4_OPERATIONS.md).

## Local website

Requires Node 22+, Python 3.11+ and PostgreSQL for real publications.
From a prepared checkout with dependencies and the Prisma client installed:

```powershell
npm ci
npm run db:generate
# Export the existing DATABASE_URL securely; do not print credentials.
$env:DATA_MODE='database'
npm run dev
```

Open http://127.0.0.1:3000/en or http://127.0.0.1:3000/zh.
Next.js loads `apps/web/.env.local`, not the root `.env.local`; an exported `DATABASE_URL` works for both.
The Python live commands load supported settings from ignored root `.env.local`.
Viewing existing publications requires no OpenAI API calls.

For a new disposable database, see [database setup](packages/db/README.md).
Do not seed, reset or rerun backfill merely to resume an existing working instance; apply only reviewed upgrade migrations.

## Offline development and checks

```powershell
python -m pip install -r services/pipeline/requirements.txt
npm test
npm run test:web
npm run typecheck
npm run lint
npm run build
```

Backend PostgreSQL integration tests require `TEST_DATABASE_URL` and create/drop isolated test schemas.
Leave it unset when preserving all existing database state.
For offline UI development, set `DATA_MODE=fixture` explicitly; synthetic editions are labeled.
The fixture pipeline (`npm run pipeline`) uses ignored `data/digest.sqlite` and makes no paid calls.
`python tests/run_web_smoke.py` targets fixture routes by default; it is not real-content acceptance.

## Live operation and safety

Real collection and editorial execution are opt-in; credentials remain server-side and Git-ignored.
MVP-4 `npm run pipeline:daily -- run --dry-run` reads stored evidence without collection, API calls or publication.
The compatibility `pipeline:live` entrypoint now uses the same guarded runner and safe dry-run semantics.
`npm run pipeline:status` reports runs, missing schedule slots, source outcomes and estimated monthly usage.
Historical backfill has already completed; do not rerun it as a startup step.
The offline scheduled workflow uses the fixture CLI dry-run. The live workflow has separate opt-in guards.
No public deployment, push, email or paid run is authorized by these setup instructions.

See [operations](docs/DEPLOYMENT.md), [acceptance](docs/ACCEPTANCE.md),
[contracts](docs/CONTRACT.md) and [task board](TASKS.md).
