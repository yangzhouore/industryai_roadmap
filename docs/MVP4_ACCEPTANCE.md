# MVP-4 local acceptance

## Scope
- Built on stabilized MVP-3 fdcd708, retaining the later GitHub initialization/license merge.
- Website layout and public content were preserved; no new production articles were generated.
- Target: 07:00 Europe/Berlin, previous complete Berlin source-publication day, DST-aware.
- Configured unattended paid approval remains false; no task registration, push or deployment.

## Data and schema
- Applied only the additive 20261114000000_daily_automation migration locally.
- Four new tables hold run state, monthly requests, reviewed event identities and resume caches.
- All existing domain/audit data fingerprints match the baseline; prior migration rows are unchanged.
- Existing 140 real articles, November 6/9/13 bilingual publications and one archived revision remain intact.
- Prior estimated spend carried forward: USD 0.10245085 MVP-3 + USD 0.007022 MVP-2 = USD 0.10947285.
- This is application accounting, not a provider invoice or account-level billing setting.

## Safety and operating limits
- Dry-run is read-only stored-evidence planning, including the legacy live entrypoint.
- Every paid attempt first reserves cost under a transactional monthly lock; unknown attempts retain reservations.
- Resume caches successful stages; failed outputs are re-reviewed, never silently accepted.
- Publication, normalized evidence, reviewed event claims and immutable content/review snapshots commit atomically.
- Production schema has zero new live automation runs or generated editions from verification.
- Real API/editorial tests use mock transport; PostgreSQL tests use isolated schemas in digest_pipeline_test.
- A local sleeping/shut-down Windows computer cannot guarantee execution; see operations for wake/catch-up limits.
- Hosted execution needs a reachable PostgreSQL service and explicit activation; local loopback is insufficient.

## Evidence
- The 14-endpoint permitted archive probe recovered the same 55 November 1-13 candidates; November 1 remains unknown.
- Runtime fingerprints, test logs, status and probe reports are ignored under artifacts/mvp4.
- Backend: 163 tests passed with PostgreSQL enabled, zero skipped; includes real concurrent budget reservations.
- Frontend: nine reader tests passed; typecheck, lint, Prisma generation/validation and production build passed.
- Website: 30 database-backed bilingual HTTP/RSS checks passed; published content and missing-date behavior preserved.
- Windows task export: six XML safety assertions passed; workflow YAML validation passed, no registration performed.
- Secret scan: 141 eligible source files, zero real credential/token/private-key findings; credential ACL preserved.
- All 24 project Markdown files remain below 100 lines; PostgreSQL CI now includes daily automation integration.
- No paid API requests, unattended activation, historical re-ingestion, push or deployment occurred.
