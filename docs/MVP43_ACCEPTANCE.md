# MVP-4.3 local editorial review and release preparation

## Implementation
- Baseline: 8db12b55046d8c051e4fdae5bbf1cc3881df32d3; dedicated mvp-4.3-editorial-review branch.
- Local CLI: python -m services.review (or npm run review -- --help); no public review route or background service.
- Explicit human enrollment requires actual identity attestation, administrator authority and private interactive passwords.
- No real account, identity, password, permission, review or public approval is seeded or created by agents.
- Private append-only SQLite events preserve candidate parents, content hashes, authors, decisions and revocations.
- Source PostgreSQL uses verified read-only transactions; immutable historical editions and source evidence remain untouched.
- Rewrites may change candidate editorial fields only; source identity/metadata/excerpts and historical snapshots are preserved.
- Bilingual reports place original story fields beside factual citations, retained source excerpts, dates and metadata.
- Heuristics flag copied/near-copied wording, translated dependence, unsupported numbers/claim scope and assets.
- Suggestions are metadata-anchored original editable sentence templates with explicit factual slots, not verified generated stories.
- No AI/provider calls occur; suggestions never change a candidate or historical edition automatically.

## Human review and export boundaries
- Story/link statuses have reasons, HTTPS references and private evidence file hashes tied to the exact revision.
- Approval requires every story/link, both language checks, claim mappings, risk resolutions and fresh reviewer authentication.
- All contributing authors in the entire candidate lineage are disqualified from reviewing that candidate.
- Changed revisions, changed decisions, missing/changed evidence and revocation prevent clearance export.
- Shared packages/shared/public-display.ts provides the existing exact hash and public gate for both web and local CLI.
- A bounded data-only Node bridge reuses that gate; the public app still reads only its unchanged trusted policy.
- Export creates a new PRIVATE candidate/policy/audit bundle; it never installs policy, writes editions or deploys.
- Local preview shows only the approved shared PublicIssue projection; unapproved previews are withheld with empty feeds/archive.
- Separate EN/ZH home/digest/Sources/archive and RSS files are offline, escaped, script-free and contain no source excerpts/assets.
- Authenticated status/audit views retain reasons/references; credential hashes/salts are omitted from audit output.

## Independent verification and preservation
- Separate implementation, analysis/rendering, QA/security and lead integration used bounded file ownership.
- Machine-only private inspection reports were generated for November 6/9/13, without journal enrollment/import/approval.
- All real public previews remained withheld; source fingerprints matched after machine-only inspection.
- Final local matrix passed: npm test, pipeline (68), review (22), deployment (10), recovery (15), idempotency (1).
- Frontend test:web (16), lint, typecheck and build passed; fixture/database HTTP smoke passed (24/124 assertions).
- Chromium smoke passed 17 cases with three screenshots; Windows skips one optional symlink-only test.
- Fresh read-only source comparison matches all 19 table hashes, 140 articles, three bilingual issues and one revision.
- Isolated recovery roundtrip and database migrations passed; secret scan passed and all 41 Markdown files are below 100 lines.
- Both GitHub Actions jobs passed for e25f745 in [push run 44277892858](https://github.com/yangzhouore/industryai_roadmap/actions/runs/44277892858)
  and [PR run 44277885943](https://github.com/yangzhouore/industryai_roadmap/actions/runs/44277885943).
- Existing public-display policy remains empty; all source-reuse approvals remain false.

## Operator guidance and limits
- [Review commands](EDITORIAL_REVIEW.md), [analysis limits](EDITORIAL_REVIEW_ANALYSIS.md),
  [independent security findings](MVP43_SECURITY.md), [contract](EDITORIAL_REVIEW_CONTRACT.md),
  and [launch checklist](PUBLIC_LAUNCH_CHECKLIST.md) describe setup and remaining gates.
- Actual verified people must enroll and independently review both languages/claims/permissions; none of that human work is claimed.
- The journal protects ordinary mutations with triggers/hash chains, not a malicious OS owner who can replace code/state.
- Password/account recovery and external identity verification remain explicit operator/security work, not automatic identity rewriting.
- Revocation blocks future exports but cannot retract old bundles or deployed policy; fresh authorized release/cache handling is required.
- Moving an approved candidate into a public database/policy is a separate authorized publishing step; this workflow does not do it.
- Publisher questions, genuine human review/permissions, infrastructure/secrets/TLS/alerts, off-host custody and dependency triage remain launch gates.
- No PostgreSQL reset, historical overwrite, public deployment, infrastructure purchase, paid automation or MVP-5 work occurred.
