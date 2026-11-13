# TASKS — Milestones and delegation board

## MVP-3 - Historical backfill complete (2026-11-01 through 13 Berlin)
- [x] Verified Luna/Terra API access and structured-output compatibility; configured two-model routing.
- [x] Recovered 28 additional candidates; classified all 55 in-period records across 13 dates.
- [x] Pilot passed; full run stayed below USD 2 (estimated USD 0.10245085 including failures).
- [x] Published November 6, 9, 13; other dates remain unpublished with explicit evidence/review reasons.
- [x] Preserved previous November 13 content/review in append-only history; no verified data deleted.
- [x] Resume/dry-run/budget flags, 105 backend + 9 reader tests and 43 route/data acceptance checks verified.
- Report: docs/MVP3_BACKFILL_REPORT.md. Unattended paid calls remain disabled.

## MVP-2 — Real news activation (complete; historical baseline)
- [x] Initial audit found an empty real-source registry and mock-only editorial; subsequently resolved.
- [x] Discover and execute six legitimate working real-source feeds (collection agent).
- [x] Persist 112 real articles, attribution, timestamps and evidence; replay inserts zero.
- [x] Implement live editorial/classification/translation and fact-check provider; 15 mocked API tests pass.
- [x] Exclude synthetic content from default public queries; explicit demo mode only (frontend agent).
- [x] Run real-source dry-run and persist credential-blocked status; opt-in daily workflow supplied.
- [x] Published one real bilingual digest (2026-11-13); verified EN/ZH digest, sources, archive and search.
- [x] Recorded 112 articles, six sources, one real digest; 72 Python and nine reader tests pass.
- Credential saved in ignored .env.local; initial paid test authorized and completed. Unattended paid calls disabled.
- Historical MVP-2 counts are superseded by MVP-3: 140 articles and three real editions.

Only the lead agent changes status. `[ ]` pending; `[x]` verified. Never mark done without checking.

## M0 — Foundation (lead + database, sequential contract first)
- [x] Inspect repo and reference, document evidence/assumptions.
- [x] Create monorepo, environment examples, commands and Docker/Postgres configuration.
- [x] Define shared schema and owned directory boundaries; database agent implements migrations.
- [x] Add reproducible fixture/seed and baseline CI/test scripts.
- **Gate:** clean setup and local fixture boot work.

## M1 — Website (frontend; parallel with M2 after M0)
- [x] Bilingual responsive homepage, magazine editorial visual system.
- [x] Digest page, per-issue source list, archive, search (EN/ZH HTTP tests).
- [x] Methodology, changelog, privacy, navigation, metadata (HTTP/source review).
- [x] Screenshots/accessibility and mobile checks where available.
- **Gate:** all routes work against fixtures and match the design spec.

## M2 — Collection (pipeline; parallel with M1/M3 after M0)
- [x] Source registry, allowed feed collection, normalize and persist.
- [x] Extraction, retries, rate limits, SSRF protections, URL/title dedup (14 offline tests).
- [x] Event clustering and audit/run logs.
- **Gate:** repeated fixture collection is idempotent, failures handled.

## M3 — Editorial (editorial; parallel with M1/M2 after M0)
- [x] Industrial taxonomy, maturity stages and scored ranking.
- [x] Up to 3 lead stories plus quick bites, with diversity rules.
- [x] Pluggable provider plus deterministic mock; real three-pass provider added in MVP-2/MVP-3.
- [x] Citation-grounded claim checks and EN/ZH numeric/entity consistency.
- **Gate:** invalid or unsupported facts cannot be published.

## M4 — Integration (lead + QA; after M1–M3)
- [x] Connect website to published database editions, search and archives.
- [x] Atomic draft/validated/published transitions (SQLite failure/rollback tests).
- [x] Integration, failure, locale and accessibility tests.
- **Gate:** end-to-end publish and replay verified.

## M5 — Publishing (publishing + QA; after M4)
- [x] RSS, sitemap, robots, canonical, hreflang, OG metadata (build and HTTP checks).
- [x] Scheduled workflows with dry-run and monitoring; optional email disabled by default.
- [x] Production deployment documentation and production dependency security checks.
- **Gate:** local and CI reproducibility proven; no unauthorized deployment.

## Parallel execution rule
After M0 shared contracts freeze, spawn frontend, pipeline and editorial simultaneously. QA may begin fixture and contract tests in parallel. Lead integrates only after agents report completion and touched files.

## Foundation acceptance (historical, before MVP-2/MVP-3)
- All local M0-M5 implementation and verification tasks completed.
- 50 Python tests passed with PostgreSQL enabled; 7 frontend reader tests passed.
- Real PostgreSQL migration, seed replay, constraints, evidence writes and rollback passed.
- Database-backed web: 24 HTTP checks passed; browser report and screenshots under artifacts/browser.
- Browser checks cover desktop/mobile, contrast, accessibility tree, keyboard and locale navigation.
- Build, typecheck and lint passed; scheduled success/failure monitoring verified.
- Feed fixture replay inserts zero duplicates; candidates and audit records persisted.
- Portable PostgreSQL and local preview supplied; only explicit fixture mode now serves synthetic content.
- GitHub Actions workflows are ready but remote execution has not been triggered.
- MVP-2 supersedes demo-only operation: real feeds and manual AI publication now verified; email/public hosting inactive.

## MVP-3 stabilization - 2026-11-13
- [x] Verified existing unborn Git repository and identity; prepared initial source checkpoint.
- [x] Expanded exclusions for environment variants, keys, database dumps, caches and runtime artifacts.
- [x] Restricted root .env.local to Windows owner, SYSTEM and Administrators; contents/readability preserved.
- [x] Precommit secret scan passed; no real credentials in eligible source files.
- [x] Updated stale MVP-2/demo documentation; all 22 project Markdown files remain under 100 lines.
- [x] Reran tests: 93 backend passed, 12 DB-writing tests skipped; 9 frontend passed; lint/typecheck passed.
- [x] All 15 PostgreSQL table fingerprints unchanged; 140 real articles, three bilingual editions, one revision retained.
- [x] Ten local real-publication route checks passed. No paid calls, backfill, push or deployment.
- Stop after the initial checkpoint. MVP-4 has not started; Git does not back up ignored database/runtime data.
