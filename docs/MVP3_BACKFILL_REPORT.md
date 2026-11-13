# MVP-3 historical backfill — 2026-11-01 through 2026-11-13

## Result and scope
- Executed all 13 Berlin calendar dates against real PostgreSQL. No recurring paid calls enabled.
- Recovered 28 new real raw candidates: 112 previously stored → 140 total; 55 fall within this window (27 old + 28 new).
- Reviewed 14 working feed/archive endpoints across Siemens, NVIDIA, AWS, MIT, Schneider Electric and Microsoft.
- Source archive/policy audit: `services/pipeline/collectors/historical_backfill_evidence.json` and `archive_discovery_evidence.json`.
- This is accessible-feed coverage, not a claim of exhaustive worldwide news or complete publisher archives.
- 55 candidates classified; six initially included, two rejected by deterministic source checks.
- Four unique stories selected for writing; three passed independent review and published; one failed maturity/scoring review.
- 52 candidates were not published. No synthetic items or fabricated no-update articles were added.

## Berlin daily coverage
| Date | Raw candidates | Outcome |
| --- | ---: | --- |
| 2026-11-01 | 0 | Unpublished: no accessible evidence |
| 2026-11-02 | 1 | Unpublished: no eligible industrial AI evidence |
| 2026-11-03 | 4 | Unpublished: no eligible industrial AI evidence |
| 2026-11-04 | 4 | Unpublished: no eligible industrial AI evidence |
| 2026-11-05 | 10 | Unpublished: independent maturity/scoring review failed |
| 2026-11-06 | 2 | Published: one story |
| 2026-11-07 | 1 | Unpublished: no eligible industrial AI evidence |
| 2026-11-08 | 2 | Unpublished: no eligible industrial AI evidence |
| 2026-11-09 | 10 | Published: one story |
| 2026-11-10 | 7 | Unpublished: no eligible industrial AI evidence |
| 2026-11-11 | 4 | Unpublished: no eligible industrial AI evidence |
| 2026-11-12 | 7 | Unpublished: no eligible industrial AI evidence |
| 2026-11-13 | 3 | Published: one story; previous edition archived |

## Models and measured usage
Authenticated model metadata returned200 for both requested models; actual Responses structured-output requests succeeded.
| Model | Input tokens | Output tokens | Reasoning subset | Requests | Estimated USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| gpt-6-luna | 23,356 | 13,702 | 4,560 | 14 | 0.00970110 |
| gpt-6.1-terra | 25,295 | 12,228 | 3,078 | 12 | 0.09274975 |
Total estimated spend: **USD0.10245085**, including failed pilots and retries; authorized ceiling USD2.00.
Reasoning tokens are already included in output tokens and were not charged twice.
Rates include actual cache-read/write usage; this is an application estimate, not an account invoice.
Pricing: https://developers.openai.com/api/docs/models/gpt-6-luna and https://developers.openai.com/api/docs/models/gpt-6.1-terra.
The persistent ledger reserves worst-case request cost before every attempt; interrupted/unknown-usage requests retain reservations.
No fallback models, account billing changes or unattended paid jobs were used.
Verification establishes grounding in publisher evidence; vendor-reported results are not independently certified.

## Pilot, quality and preservation
- November9 pilot passed claim/quote/date/translation validation and independent Terra review.
- Unlike the old GPT-4.1 mini edition's October21 source under November13, new sources must match the Berlin issue day exactly.
- This is not a same-article A/B benchmark; no unsupported model-quality superiority is claimed.
- Pilot failures exposed unknown maturity/identity schema handling and research deployment-score inconsistency; corrected without bypassing review.
- Unsupported entity/company/quote candidates are excluded individually. Uncertain evidence is not replaced by invented facts.
- November5 remains unpublished because review did not support prototype maturity or its score.
- One append-only revision preserves the previous November13 edition and matching review; no existing verified content was deleted.
- PostgreSQL: 140 raw articles, seven retained issue rows, three real public editions, one archived revision.
- New issue sources retain publication timestamps; event/update/ingestion fields remain distinct and event dates are not inferred.

## Verification and commands
- 105 backend tests and nine frontend tests passed; Prisma generation, production build, typecheck and lint passed.
- 43 read-only acceptance checks passed: all13 EN/ZH date routes, published sources/original HTTP200 links, archive ordering/search, translation parity, score consistency and no duplicate issue events.
- Raw URL replay inserted0; duplicate canonical URLs0. Actual resume reused cached stages without increasing spend or creating editions.
- `python -m services.pipeline.backfill --start 2026-11-01 --end 2026-11-13 --resume --max-cost-usd 2`
- Supports `--dry-run`, `--date` and `--resume`; dry-run writes a separate plan and performs no paid calls/publication.
- Data/audits: ignored `artifacts/mvp3/progress.json`, `budget.json`, response/review files and PostgreSQL pipeline_runs.
- Review: http://127.0.0.1:3000/en/archive and http://127.0.0.1:3000/zh/archive.

## Remaining coverage limitations
November1 could not be recovered. Robots restrictions, empty feeds, unchanged pagination and unavailable archives are recorded in the collector audit.
The other unpublished dates do not establish that no news existed: bounded permitted feed evidence was insufficient or out of scope.
Broader article-body retrieval/republication and restricted arXiv/other endpoints were not bypassed.
