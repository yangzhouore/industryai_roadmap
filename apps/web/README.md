# Industrial AI Digest web

From the repository root, with the existing PostgreSQL connection configured securely:

```sh
npm ci
npm run db:generate
npm run dev
npm run typecheck
npm run lint
npm run build
```

Open `http://127.0.0.1:3000/en` or `/zh`. The default reads PostgreSQL.
Next.js accepts exported `DATABASE_URL` or `apps/web/.env.local`; root `.env.local` is not loaded automatically.
An existing instance does not require migration, seed or historical backfill to resume.
Current MVP-3 data includes 140 real articles and bilingual editions for November 6, 9 and 13, 2026.
The old November 13 edition and review remain in database revision history.
Public readers require published state, validation, intact sources and no synthetic issue, story or source content.
Real editions also require trusted `config/public-display.json` human editorial and exact source-link clearances.
Clearances bind the full stored Issue hash; zero approvals are configured, so real editions remain private.
The public projection copies only known fields and never sends retained source excerpts, evidence or assets.
Changing any stored content invalidates its approval. No environment flag bypasses the review policy.
Empty databases show an honest no-published-news state. Drafts are never substituted with demo stories.
Viewing published pages does not call OpenAI; API credentials belong to the server-side editorial pipeline.

For offline UI development, explicitly set `DATA_MODE=fixture` in the process environment or `apps/web/.env.local`.
Fixture mode needs no credentials and labels every demonstration edition and reserved example URL.
Search supports keywords, actual topic filters and pagination. Locale switching preserves route and query.
RSS is at `/en/rss.xml` and `/zh/rss.xml`; sitemap and robots are at the root.
No third-party fonts, remote images, analytics, subscriptions or browser storage are required.

```sh
node --test apps/web/tests/data.test.mjs
node apps/web/tests/browser-smoke.mjs
```

Browser QA uses an installed Chromium executable with `WEB_URL` and optional `CHROME_PATH`.
Run its target server in explicit fixture mode; it asserts fixture-specific dates and content.
The generic `tests/smoke_web.py` also targets fixture dates and is not real-publication acceptance.
Browser artifacts are ignored under `artifacts/browser`.
See [MVP-3 report](../../docs/MVP3_BACKFILL_REPORT.md) and [acceptance](../../docs/ACCEPTANCE.md).
