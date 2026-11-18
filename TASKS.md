# TASKS - milestone and acceptance board

Only the lead changes status; mark verified work honestly. Every Markdown file stays below 100 lines.
Earlier M0-M5, MVP-2/3/4 records are preserved in [milestone history](docs/MILESTONE_HISTORY.md).

## Preserved baseline
- [x] MVP-3 stable checkpoint fdcd708 and immutable mvp-3 tag preserved.
- [x] MVP-4 accepted e7524d0, immutable mvp-4 tag preserved; release plan d70a34f pushed.
- [x] Existing local data: 140 real articles, November 6/9/13 bilingual editions, immutable revision history.
- [x] Unattended paid execution remains disabled; no hosting deployment or VPS purchase.

## MVP-4.1 - CI repair and production preparation (verified)
- [x] Inspected failed run 43854684646 and both job logs; retained all browser assertions.
- [x] Dedicated CI repair 481951f pushed; isolated PostgreSQL job passed remotely.
- [x] Final remote offline browser job and complete CI matrix pass (701009b).
- [x] Local repair checks: 170 backend, nine frontend, 24 fixture HTTP +105 browser, 54 isolated PostgreSQL HTTP checks.
- [x] Local lint, typecheck, build and staged secret/path scan passed.
- [x] Reproducible Ubuntu services, private PostgreSQL, Caddy, timer, health and persistent logs accepted.
- [x] Real read-only 140-article encrypted backup restored into a new isolated target; 19 table hashes matched.
- [x] Recovery hardening/off-host transport configuration and isolated restore passed locally and in Ubuntu CI.
- [x] Evidence-based source/attribution audit recorded; no blanket public reuse clearance claimed.
- [x] Independent security audit, final data-preservation fingerprints, secret scan and Markdown checks pass.
- [x] Production-preparation 701009b pushed; both jobs passed in [run 44049852883](https://github.com/yangzhouore/industryai_roadmap/actions/runs/44049852883).

## Boundaries and remaining activation gates
- Never delete, reset, replace or overwrite the preserved application data.
- Database writes for verification are confined to explicitly isolated targets/schemas.
- No paid OpenAI calls, unattended activation, production deployment, VPS purchase or credential replacement.
- Public source/translation rights and actual production/off-host credentials require further approval/evidence.
- MVP-5 has not started. Public launch remains gated by evidence and separate authorization.

## MVP-4.2 - Public content safety and launch readiness
- [x] Audit all third-party fields, source-specific permissions and assets; retain outstanding questions.
- [x] Separate retained evidence from an allowlisted public projection; default-deny real editions without exact review.
- [x] Enforce bilingual editorial and exact source-link review across pages, feeds, search and SEO.
- [x] Independent content/security/QA reviews, negative exposure tests and positive fixture/cleared projection coverage.
- [x] Preserve all 19 source table hashes, 140 articles, three bilingual editions and immutable revisions.
- [x] Full regression/secret/Markdown checks; c2d96fb pushed and both jobs passed in [run 44053537080](https://github.com/yangzhouore/industryai_roadmap/actions/runs/44053537080).
- [x] Record launch blockers and concise operator checklist; no deployment or paid activation.

## MVP-4.3 - Local editorial review and release workflow
- [x] Read-only real-edition import/inspection; private bilingual citation and heuristic-risk reports.
- [x] Append-only candidate revisions/decision audit, protected local credentials and authenticated independent human approval.
- [x] Exact shared-gate hashes, documented story/link decisions, evidence binding, revocation and explicit clearance export.
- [x] Withheld/cleared local EN/ZH digest/Sources/RSS/archive previews; public app remains fail-closed.
- [x] Preserve all existing PostgreSQL table hashes and empty public policy; no actual users/approvals invented.
- [x] Independent security review and local regressions/browser/DB tests passed; both remote jobs passed in [push run 44277892858](https://github.com/yangzhouore/industryai_roadmap/actions/runs/44277892858) and [PR run 44277885943](https://github.com/yangzhouore/industryai_roadmap/actions/runs/44277885943).
- [x] Commit e25f745 pushed to [PR #2](https://github.com/yangzhouore/industryai_roadmap/pull/2); operator commands and human/legal/release gates documented.
