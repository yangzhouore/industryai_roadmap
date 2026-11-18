# Public launch operator checklist - MVP-4.2

## Current launch state
- No production deployment or paid automation is authorized. The trusted public policy has no approvals.
- All 140 articles, three bilingual editions and revision history remain private/preserved, not deleted.
- An empty public archive and 404 for uncleared editions are expected until the review below is complete.

Use the [local review CLI](EDITORIAL_REVIEW.md) for private candidates, authenticated decisions and exact export.
Exported bundles contain private evidence: never serve them or install policy automatically.

## Content review before approval
1. Work from a protected read-only snapshot; never edit stored source evidence to make a public test pass.
2. Review every EN/ZH issue title/introduction and story title/summary/why/limitation, including company/category/IDs.
3. Write independently phrased factual reporting and original Industrial AI analysis; retain uncertainty and attribution.
4. Remove copied paragraphs, faithful translated excerpts, unapproved quotations, publisher artwork/logos and hidden payloads.
   Evidence verification or an AI similarity check cannot establish originality or legal permission.
   If historical prose is unsuitable, keep it withheld; a future authorized revision must preserve prior content/history.
5. Review every exact publisher name and source URL for the intended public-web use/business model.
   Resolve Schneider link restrictions, Siemens applicability and other publisher-specific questions; record the legal basis.
6. Obtain required permission or qualified legal review; retain dated evidence and identify the human reviewer.
   A feed, short excerpt length, noncommercial label or model review is not public-display clearance.

## Trusted clearance configuration
- config/public-display.json is version 1, intendedUse=public-web; only reviewed deployments may change it.
- Every real edition needs its exact issueId and canonical full stored-JSON contentSha256 (SHA-256 UTF-8).
- Canonical JSON recursively sorts object keys, retains array order and uses compact JSON.stringify serialization.
- An editorial clearance records editorialApproved, reviewedBy, reviewedAt and a protected HTTPS reviewEvidence URL for BOTH languages/all fields.
- Every sourceLinks record must match exact sourceId/url/publisher and record approved, basis (permission or legal-review),
  evidenceUrl (HTTPS), reviewedBy and reviewedAt. No broad host/subdomain or source-wide approval substitutes for exact links.
- Do not mark any approval true until the corresponding human review and legal questions are resolved.
- Missing/duplicate/malformed reviews, changed content and incomplete links withhold the whole edition.
- The hash binds private evidence too: any stored-content change requires a new complete review, never automatic renewal.
- Public projections always omit excerpts and unknown evidence/assets, even for cleared editions; approval is no text license.
- No environment switch bypasses real-content clearance. Fixture mode is explicitly labeled and forbidden by production preflight.

## Verification and release gates
1. Run frontend projection tests and the complete backend/DB/browser/regression CI matrix with blank paid credentials.
2. Check EN/ZH home/digest/Sources, archive/search, RSS, sitemap, metadata and serialized RSC for withheld text/assets.
3. Include a cleared original positive test and unapproved/stale/unknown/malformed/withdrawn-policy negative tests.
4. Compare read-only fingerprints: all 19 tables, 140 articles, November 6/9/13 editions and immutable revision must match.
5. Purge any prior CDN/proxy caches before revocation or launch; RSS sends no-store and Next routes are dynamic.
   External caches/search engines may retain previously served material; code cannot retract third-party copies.
6. Resolve six moderate development dependency advisories and validate actual target TLS/firewall/secrets/alert delivery.
7. Provision approved independent backup storage, verify genuine upload/download/isolated restore and identity custody.
8. Obtain separate approval for deployment. Paid scheduling remains separately disabled; no activation is implied.

## Remaining blockers
- Human bilingual originality review and per-link/source legal decisions; all current source approvals remain false.
- Host/domain/secrets, real off-host backup custody and target-host operational validation remain unprovisioned.
- This checklist prepares review; it is not publisher consent, legal advice or evidence of a live launch.
