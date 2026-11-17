# Public content audit - MVP-4.2, 2026-11-17

## Scope and decision
Read-only review of current source configuration, application routes and preserved PostgreSQL records.
This is evidence and engineering review, not legal clearance or a determination of statutory exceptions.
No publisher is approved for public display by this audit; source review flags remain false.
Existing originals, translations, citations, reviews and revisions must remain intact in private storage.

## Exposure traced before the MVP-4.2 repair
All publication routes consume `getIssues()` from `apps/web/src/lib/data.ts`.
That reader validates stored Issue JSON but previously returned the original object with no rights projection.

| Surface | Data exposed from an issue |
| --- | --- |
| Home, EN/ZH | Issue title/introduction/date; story titles/category/maturity; source count; earlier edition titles |
| Digest, EN/ZH | Issue title/introduction; story title/summary/why/limitation, kind, category, maturity and evidence status; publisher citation names |
| Source notebook, EN/ZH | Source excerpt in selected language, publisher name/link, publication/event timestamps/timezone and story score/title |
| Search | Story title/summary/category/maturity and issue date; title/summary/category/issue title used for matching |
| Archive/navigation | Issue titles/dates and story titles; links reveal edition slugs and source counts |
| RSS | Issue title/introduction, issue date, canonical edition URL and GUID; 300-second public cache |
| HTML/OG metadata | Edition title, site description, canonical/locale alternates and URL; inherited title template |
| Sitemap | All edition and source-notebook paths from the same issue list, with locale alternates |
| Framework responses | Rendered HTML and React server payloads need the same projected inputs; no private Issue objects should reach client props |

Robots advertises the sitemap. Robots/noindex instructions are not access controls.
Generic methodology/privacy/changelog and application error/loading pages contain static project prose.
Only Navigation and error handling are client components; no direct public database/evidence API was found.

## Evidence versus editorial expression
`services/pipeline/extraction` retains bounded RSS/Atom descriptions and metadata, not fetched article bodies.
The live generator requires original title plus newline plus source excerpt in its source evidence field,
and faithfully translates that evidence into the other locale. Those bilingual fields are publisher prose.
The three real published issues each have one source; English evidence lengths are 468, 465 and 385 characters.
The 400-character feed bound does not bound the combined headline/evidence field or create reuse permission.
Story/issue titles, introductions, summaries, analysis and limitations are generated editorial fields;
AI generation and factual verification alone do not establish independent wording or reuse rights.
A reviewer must inspect both languages and every visible field, including short metadata/RSS text.
Company/publisher names, dates, scores and links still require accurate attribution and source-specific review.
No publisher image/logo fields, image elements, remote image configuration or public asset directory were found.
The visible machine illustration is project CSS/HTML (`Blueprint`); no publisher artwork is needed.

## Private retention boundary
`raw_articles` retains title, body_excerpt, raw_metadata (including originalTitle/authors) and timestamps.
`story_citations.excerpt_or_pointer`, issue JSON and source translations retain evidence and quote associations.
Reviews/claim offsets, automation caches, historical artifacts and append-only edition revisions remain private.
The public reader queries published issue JSON only; it must not serialize unknown nested keys or raw metadata.
Keep backups, dumps, keys, pipeline logs and artifact directories outside web roots and public build output.
Private retention policy, provider processing rights and publication rights are separate unresolved questions.

## Primary publisher evidence rechecked
- [MIT News policy](https://news.mit.edu/terms-of-use): conditional story republication requires headline/subheadline/byline, linked citation and bottom notice; image permissions are separate. Adaptation/translation scope remains unresolved.
- [NVIDIA RSS](https://www.nvidia.com/en-us/about-nvidia/rss/): noncommercial information use only; cessation rights reserved. Proposed public summaries/translations need scoped review.
- [AWS terms](https://aws.amazon.com/terms/): content rights reserved; Site Access limits copying/derivative/commercial uses. No Industries-blog-specific grant verified.
- [Microsoft terms](https://www.microsoft.com/en-us/legal/terms-of-use): personal/noncommercial restrictions and limited unmodified-document permission; no general blog display/translation clearance established.
- [Schneider terms](https://www.se.com/ww/en/about-us/legal/terms-of-use/): written reuse permission and a hyperlink restriction; blog applicability and intended links need clarification.
- [Siemens terms](https://www.siemens.com/global/en/general/terms-of-use.html): fetch timed out again. Applicable Simcenter/blog terms remain unresolved; do not infer a grant.
Original summaries and outbound links reduce reproduced expression; they do not automatically resolve terms or rights.
Review must identify jurisdiction, business model, systematic feed-use rights and the basis for each language/use.

## Required public boundary
Reconstruct an explicit PublicIssue/PublicSource allowlist; exclude excerpts, quotes, pointers and unknown keys.
Use a separate fail-closed public policy, rather than treating factual validation as rights clearance.
Require reviewed source-link scope and exact-content-hash editorial clearance covering both locales and all surfaces.
Any edited title/introduction/story/source field or stale/missing review must remove the edition everywhere.
Do not create an environment bypass that makes stored local evidence publicly visible.
Keep source evidence unchanged privately; fixture content remains visibly synthetic and independent of real clearance.
Verify denial in HTML, source pages, RSC, search, archive, RSS, metadata and sitemap, plus unknown-key canaries.
Test any approved-path behavior with isolated synthetic test records only; no genuine approval is granted here.

## Preservation evidence
Baseline: ignored `artifacts/mvp42/content-audit-before.json`, captured using a read-only repeatable snapshot.
It covers all 19 public-table hashes, 140 real articles, November 6/9/13 bilingual editions and one revision.
After the complete local matrix, all 19 table hashes matched this baseline exactly.
All 140 real records, three bilingual editions and the revision remain unchanged; test writes stayed isolated.
No collection, paid API request, source edit, publisher outreach or public deployment occurred during this audit.
