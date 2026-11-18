# Frozen implementation contract

- Stored editorial JSON types: `packages/shared/index.ts`; fixture: `packages/shared/fixtures/issues.json` (array of Issue).
- Issue has id, slug, date (YYYY-MM-DD), state, validated, synthetic, title/intro text, sources and stories.
- Text fields are `{en: string, zh: string}`. Introduction key is `introduction`.
- Source: id, name, url, publishedAt (ISO UTC), eventAt (nullable ISO), timezone, synthetic, excerpt (Text).
- Story: id, category, maturity, company, kind (feature/quick_bite), title/summary/why/limitation (Text), sourceIds, evidenceStatus, score (0–100).
- Synthetic sources use reserved `https://example.org/fixtures/...` and must display a fixture label. Never present as news.
- All public readers filter `state === published && validated === true` and validate references.
- Production PostgreSQL stores Issue JSON in DigestIssue.content alongside normalized audit tables.
- Python fixture adapter: SQLite `data/digest.sqlite`, issues table `(id, slug UNIQUE, issue_date UNIQUE, state, validated, content)`; atomic publication.
- Python live PostgreSQL adapter uses psycopg and same columns via mapped Prisma names.
- Collection API: `collect_fixture(issues: list[dict]) -> list[dict]` yields normalized sources with source IDs intact; `canonicalize_url(url)` and `validate_url(url, allowed_hosts)`.
- Editorial API: `validate_issue(issue: dict) -> list[str]`, `score_story(story: dict) -> dict`, `prepare_issue(issue: dict) -> dict`.
- Pipeline CLI owns persistence/state changes; web reads fixture when DATA_MODE=fixture, Prisma otherwise.
- Ownership: frontend apps/web; collection collectors/extraction/dedup; editorial scoring/editorial/verification/translation. Lead handles integration, database and tests.

## MVP-4.2 public display boundary
- Stored Issue/Source retain evidence unchanged; PublicIssue/PublicSource omit source excerpts.
- All page/feed/search/SEO readers use only the explicit server public projection.
- Real editions require trusted config/public-display.json clearance matching the canonical SHA-256 of the full stored Issue.
- Policy version 1 / public-web: edition editorialApproved, reviewer/date/HTTPS evidence; every source link needs exact ID/URL/publisher,
  approved, basis (permission or legal-review), HTTPS evidence URL, reviewer and review date.
- Missing/malformed policy, duplicate reviews, stale hashes or incomplete source clearances withhold the whole edition.
- Both language prose and titles/introduction/analysis must be independently written and reviewed; model verification is insufficient.
- Public projections allowlist known fields, never spread stored objects, and always omit excerpts, evidence payloads and assets.
- Explicit fixture mode remains labeled; it also uses sanitized projections. No runtime preview bypass for uncleared real editions.
- Default policy has zero approvals; changing approvals requires documented human review, never ingestion or paid automation.

## MVP-4.3 local review boundary
- Pure shared public-display.ts is reused by the web reader and a bounded local data-only Node bridge.
- Local candidate journal, authentication, append-only decisions/revisions and exact clearance export are defined in
  [review contract](EDITORIAL_REVIEW_CONTRACT.md); the PostgreSQL source and existing history remain read-only.
- Review reports contain private evidence; previews receive only shared-gate public projections or withheld/empty output.
- No public web review routes, preview override, automatic public policy installation, paid call or deployment is introduced.
