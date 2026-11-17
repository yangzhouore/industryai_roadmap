# MVP-4.2 public content safety and launch readiness

## Implementation and public behavior
- Started from cbcaaa50099355df7489358e190c4aaef6236224; no deployment or paid activation.
- Private stored Issue/Source evidence is unchanged; server-only PublicIssue/PublicSource is a fresh allowlisted projection.
- Retained excerpts, translations of source excerpts, raw evidence, model/review payloads and assets never enter that projection.
- Real editions require trusted public-web policy, exact full stored-content SHA-256, human bilingual editorial review,
  and complete approved exact source ID/URL/publisher link records with dated reviewer/basis/HTTPS evidence.
- Duplicate/malformed policy, stale content hashes and absent reviews withhold the whole edition on every surface.
- config/public-display.json contains no approvals. All three historical real editions are withheld publicly, not deleted.
- Positive original-editorial projections use artificial in-memory unit records; no genuine source/content approval was created.
- Sources pages use labeled editorial context, factual citation metadata and reviewed links instead of publisher excerpts.
- RSS is no-store; policy is bundled at build time and changes/revocations require rebuild plus external cache handling.

## Verification executed locally
- 170 backend tests (102 repository +68 pipeline), 16 frontend reader/projection tests.
- Three reviewed migrations/replay and database seed/idempotency checks in an isolated test database.
- 10 production safety tests; 15 recovery tests including actual encrypted PostgreSQL dump/restore into isolated targets.
- Lint, typecheck and production build passed; fixture pipeline replay publishes three, then leaves all three unchanged.
- 24 fixture HTTP checks and all 105 browser checks retained/passed with normal local sandboxing.
- 124 database HTML/RSC checks cover both locales, Sources/digest 404s, home/archive/search, RSS, sitemap and metadata.
- Valid-but-uncleared test records carry copied-prose/private-evidence/response/review/asset sentinels; none were exposed.
- Tests include a cleared artificial positive projection, exact-link denial, stale hashes, malformed reviews and nested-copy isolation.
- Bilingual smoke caught new Chinese label corruption; corrected before final checks, with the assertion retained.
- RSS checks assert no-store. Denial tests require empty feeds/results/categories and absent withheld links, not merely HTTP success.
- Final staged secret scan/Markdown checks and actual remote CI are recorded after commit verification.

## Preservation and independent reviews
- Read-only baseline and final comparison matched all 19 public-table hashes, 140 real articles,
  November 6/9/13 bilingual editions and one immutable revision; no historical record is rewritten.
- [Content audit](PUBLIC_CONTENT_AUDIT.md), [independent security review](PUBLIC_CONTENT_SECURITY.md),
  [source reuse evidence](SOURCE_REUSE_AUDIT.md) and [operator checklist](PUBLIC_LAUNCH_CHECKLIST.md) document scope and limits.
- Independent content, frontend, security and QA work completed using bounded file ownership.

## Remaining launch blockers
- Human bilingual originality review and publisher-specific source/link legal decisions; all source approvals remain false.
- MIT adaptation/translation conditions; NVIDIA noncommercial scope; AWS/Microsoft blog use; Schneider links; Siemens terms applicability.
- Approved host/domain/secrets, actual TLS/firewall/alerts and genuine off-host backup transfer/restore custody are unprovisioned.
- Six moderate development dependency advisories remain separate maintenance; no production dependency findings at MVP-4.1 audit.
- Structured clearance validates records, not reviewer authority or legal sufficiency; it cannot prove wording independence.
- No new paid API use, scheduled paid job, publisher outreach, infrastructure purchase, production deployment or MVP-5 work.
