# Architecture and interfaces

## Services
- `apps/web`: Next.js server-rendered public site; published data only.
- `services/pipeline`: Python scheduled ingestion + editorial pipeline.
- `packages/db`: PostgreSQL schema, migrations, seed.
- `packages/shared`: type/schema contracts consumed by web and pipeline as appropriate.

## Data flow
feed/API -> raw_articles -> clusters -> scores -> selected draft -> verified bilingual publication -> published views -> web/RSS.

## Invariants
- Store event_time and published_at separately, including source timezone.
- All items and claims reference actual sources.
- Publication uses transaction: no half-published bilingual issue.
- Pipeline is replayable/idempotent; no duplicate daily issue or raw URL records.
- Source handling follows legal/robots constraints. URLs validated to prevent SSRF.
- Only trusted rendered components; never inject raw untrusted HTML.

## API/data contract
Agree on issue, story, source, citation, score and language fields before agents independently code. Use schema validation and fixtures. Website must gracefully handle no issues, missing images, failed search and partial source metadata.

## Environment
Use `.env.example` placeholders; no credentials in repo. Docker Compose for PostgreSQL, fixture mode for pipeline, npm/pnpm frontend tasks and Python environment for pipeline.
