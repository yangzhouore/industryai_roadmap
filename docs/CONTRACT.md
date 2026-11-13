# Frozen implementation contract

- Shared public JSON types: `packages/shared/index.ts`; fixture: `packages/shared/fixtures/issues.json` (array of Issue).
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
