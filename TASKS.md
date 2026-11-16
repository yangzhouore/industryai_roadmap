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
- M0-M5 local gates passed; historical 50 backend/seven frontend tests and 24 HTTP checks.
- MVP-2/MVP-3 supersede demo-only acceptance; see docs/ACCEPTANCE.md and MVP3_BACKFILL_REPORT.md.

## MVP-3 stabilization - 2026-11-13
- [x] Verified existing unborn Git repository and identity; prepared initial source checkpoint.
- [x] Expanded exclusions for environment variants, keys, database dumps, caches and runtime artifacts.
- [x] Restricted root .env.local to Windows owner, SYSTEM and Administrators; contents/readability preserved.
- [x] Precommit secret scan passed; no real credentials in eligible source files.
- [x] Updated stale MVP-2/demo documentation; all 22 project Markdown files remain under 100 lines.
- [x] Reran tests: 93 backend passed, 12 DB-writing tests skipped; 9 frontend passed; lint/typecheck passed.
- [x] All 15 PostgreSQL table fingerprints unchanged; 140 real articles, three bilingual editions, one revision retained.
- [x] Ten local real-publication route checks passed. No paid calls, backfill, push or deployment.
- Initial checkpoint fdcd708 retained; Git does not back up ignored database/runtime data.

## MVP-4 - Automated daily publishing (local implementation)
- [x] Berlin 07:00 slots/DST, overlap locks, missed-run status and manual/dry-run/resume CLI.
- [x] Disabled GitHub schedule plus Windows task export; no task registered or paid execution activated.
- [x] Incremental real-source collection, explicit source inventory and canonical/reviewed-event deduplication.
- [x] Read-only probe: all 14 permitted endpoints; same 55 historical candidates, November 1 still unresolved.
- [x] Daily Luna classification batches, Terra generation/review/translation, low reasoning and sealed temporal gates.
- [x] Concurrent USD 2 monthly ledger, pre-request reservations, retries, failed calls and legacy carryover.
- [x] Durable stage resume, atomic bilingual publication/event claims and append-only edition/review snapshots.
- [x] Additive local schema applied; existing 15-table fingerprints preserved with 140 articles/three editions/one revision.
- [x] Regression checks and secret scan recorded in docs/MVP4_ACCEPTANCE.md.
- [ ] Explicit authorization to activate unattended paid calls, register an enabled task or deploy.
- Next: review operational setup/activation separately. Existing coverage gaps remain honest omissions.

## MVP-4 release preparation - 2026-11-16
- [x] Pushed accepted e7524d0 and immutable mvp-4 tag; no history rewrite or activation.
- [x] Read-only status confirms disabled paid scheduler; deployment/cost audit in docs/DEPLOYMENT_PLAN.md.
- [ ] CI smoke failures and deployment blockers recorded in the plan; MVP-5 has not started.
