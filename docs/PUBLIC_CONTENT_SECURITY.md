# Public content security review - MVP-4.2

## Independent scope
Reviewed the public reader, projection, static policy, shared contracts, routes, feeds and client boundaries.
Reviewed code independently of its implementation author; no application files changed by this reviewer.
The separate [content audit](PUBLIC_CONTENT_AUDIT.md) records publisher evidence and legal questions.
This is an engineering review, not rights clearance, a penetration test or a deployment authorization.

## Boundary verified in code
- `apps/web/src/lib/data.ts` is server-only and is the common public reader for every content surface.
- Database reads still require published/validated/nonsynthetic records; factual checks remain in place.
- `config/public-display.json` is trusted release configuration with no approved editions.
- Real issues require valid human-review metadata, exact full-content SHA256 and editorialApproved=true.
- Every source requires its exact id, URL and publisher plus explicit approval, basis and review evidence.
- Duplicate/malformed policy records, missing review fields and mismatched content withhold the whole issue.
- Unknown runtime environment flags cannot bypass the trusted policy; fixture mode uses bundled demo records.
- The hash covers retained excerpts and unknown private fields too; changed evidence invalidates stale review.
- Projection explicitly rebuilds each issue/source/story and bilingual text object; no object spreading is used.
- Excerpts, quote pointers, assets, raw metadata, model responses and unknown keys do not cross the projection.
- Arrays/text objects are copied; mutating a projection cannot rewrite the stored object or private evidence.

## Output paths reviewed
Home, archive, search, digest, source notebook and edition navigation consume projected issues only.
The source notebook now displays labeled editorial context instead of retained publisher text.
Metadata resolution and the parent route guard use the same reader; withheld edition routes return 404.
Sitemap and RSS use the same gate; denied edition slugs and prose do not have a separate publication path.
RSS XML escapes content and sends Cache-Control: no-store; content pages/sitemap are force-dynamic.
React escapes text; no raw HTML injection, JSON-LD serialization or public evidence download route was found.
Client Navigation receives locale/static translations, not raw issues; error output is generic.
No publisher image/logo rendering or remote asset configuration was found; the illustration is local CSS/HTML.

## Findings and corrections
No gate bypass was identified in the reviewed implementation.
Review caught question-mark Chinese source labels and a stale Chinese methodology statement.
The frontend author corrected those strings and aligned the bilingual clearance explanation.
The earlier RSS public cache was replaced with no-store to avoid retaining newly served cleared content.
Prior CDN/browser/search-engine copies need a separate purge/revocation plan; response headers cannot retract copies.

## Executed verification
`npm run test:web`: 16 tests passed independently during this review.
Coverage includes approved projection, denied default/flags, unknown-field canaries and nested alias isolation.
It also checks stale full-content hashes, exact source permissions, malformed/duplicate policy and non-JSON input.
QA reported 124 isolated database HTTP/RSC deny checks, backend 170, infrastructure 10 and recovery 15 passed.
Independent post-matrix read-only comparison matched all 19 source-table hashes, 140 real articles and three bilingual editions.
The one immutable revision also matches; evidence is ignored artifacts/mvp42/content-audit-preservation.json.
No real approval was created to exercise the positive path; approvals in unit tests describe artificial records.
The unit harness stubs Prisma/module loading; it is not a live approved-content browser test or legal approval.

## Operational limits
Human review remains responsible for independent wording, factual attribution and both language versions.
The software validates approval structure and matching content, not the authority or legal sufficiency of a reviewer.
The policy is bundled at build time: review changes/revocations require a rebuilt, reviewed release and cache handling.
Keep raw database access, evidence artifacts, backups and logs private; do not add a preview bypass to public services.
Production secrets, actual host validation, publisher questions and off-host custody remain deployment blockers.
No API call, scheduler activation, publisher message, deployment or source-record mutation occurred in this review.
