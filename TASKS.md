# TASKS - milestone and acceptance board

Only the lead changes status; mark verified work honestly. Every Markdown file stays below 100 lines.
Earlier M0-M5, MVP-2/3/4 records are preserved in [milestone history](docs/MILESTONE_HISTORY.md).

## Preserved baseline
- [x] MVP-3 stable checkpoint fdcd708 and immutable mvp-3 tag preserved.
- [x] MVP-4 accepted e7524d0, immutable mvp-4 tag preserved; release plan d70a34f pushed.
- [x] Existing local data: 140 real articles, November 6/9/13 bilingual editions, immutable revision history.
- [x] Unattended paid execution remains disabled; no hosting deployment or VPS purchase.

## MVP-4.1 - CI repair and production preparation (in progress)
- [x] Inspected failed run 43854684646 and both job logs; retained all browser assertions.
- [x] Dedicated CI repair 481951f pushed; isolated PostgreSQL job passed remotely.
- [ ] Final remote offline browser job and complete CI matrix pass.
- [x] Local repair checks: 170 backend, nine frontend, 24 fixture HTTP +105 browser, 54 isolated PostgreSQL HTTP checks.
- [x] Local lint, typecheck, build and staged secret/path scan passed.
- [x] Reproducible Ubuntu services, private PostgreSQL, Caddy, timer, health and persistent logs accepted.
- [x] Real read-only 140-article encrypted backup restored into a new isolated target; 19 table hashes matched.
- [x] Recovery hardening/off-host transport configuration tested locally; isolated restore CI awaits remote run.
- [x] Evidence-based source/attribution audit recorded; no blanket public reuse clearance claimed.
- [x] Independent security audit, final data-preservation fingerprints, secret scan and Markdown checks pass.
- [ ] Final verified production-preparation commit pushed and actual GitHub jobs pass.

## Boundaries and remaining activation gates
- Never delete, reset, replace or overwrite the preserved application data.
- Database writes for verification are confined to explicitly isolated targets/schemas.
- No paid OpenAI calls, unattended activation, production deployment, VPS purchase or credential replacement.
- Public source/translation rights and actual production/off-host credentials require further approval/evidence.
- MVP-5 has not started. Continue MVP-4.1 verification until complete or a real blocker is reported.
