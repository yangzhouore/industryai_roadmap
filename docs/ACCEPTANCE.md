# Local acceptance - MVP-3

## Current verified data

- PostgreSQL: 140 real raw articles, seven retained issue rows and one archived revision.
- Three real validated bilingual editions are public locally: 2026-11-06, 2026-11-09 and 2026-11-13.
- The prior November 13 edition and matching review remain in append-only history.
- Synthetic editions remain available only through explicit fixture mode.
- Six reviewed publisher feeds support opt-in local collection; permitted evidence coverage is bounded.
- Classification uses `gpt-6-luna`; generation and independent review use `gpt-6.1-terra`.

## Recorded verification

- MVP-3 execution: 105 backend tests and nine frontend tests passed; build, typecheck and lint passed.
- MVP-3 execution: 43 read-only route/data checks passed, including publisher links.
- Recovery audit: 93 backend tests passed; 12 PostgreSQL-writing tests were intentionally skipped.
- Recovery audit: all nine frontend tests, typecheck and lint passed.
- Recovery audit: 57 read-only database/localhost checks passed without paid calls or publisher requests.
- Recovery verified article uniqueness, bilingual routes, sources, search, archive, RSS and revision review hashes.
- These are separate historical runs; stabilization results are recorded in TASKS.md.
- Earlier foundation counts of 50 backend/seven frontend tests describe an older suite.
- Fixture browser screenshots and accessibility/keyboard/locale evidence remain in ignored artifacts/browser.
- Remote GitHub Actions execution and public deployment have not been performed.

## Review and operating limits

Open http://127.0.0.1:3000/en or http://127.0.0.1:3000/zh while the local server is running.
Normal database mode serves validated real publications and excludes synthetic issues and drafts.
Viewing existing content requires no OpenAI API calls.
Public hosting, email and unattended paid publication remain inactive.
See [MVP-3 coverage report](MVP3_BACKFILL_REPORT.md), [operations](DEPLOYMENT.md)
and [database setup](../packages/db/README.md).
