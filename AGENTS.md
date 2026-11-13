# Industrial AI Digest — Repository Agent Instructions

## Mission
Build an original bilingual industrial-AI intelligence website inspired by https://ai-digest.liziran.com/en/. Match the editorial information architecture and reading quality, not its trademarks, copyrighted articles, or source code.

## Startup protocol
1. Read `START.md`, `TASKS.md`, and all relevant `docs/*.md` before implementation.
2. Inspect existing code and preserve working functionality. Do not overwrite user changes.
3. You are explicitly authorized and requested to delegate independent work to Codex subagents in parallel where tools support it.
4. Main agent owns orchestration, shared contracts, integration, tests, and milestone acceptance.
5. Start implementing immediately. Do not stop after a plan; proceed until blocked by real permissions or credentials.

## Architecture constraints
- Monorepo: `apps/web` (Next.js, TS, Tailwind, next-intl), `services/pipeline` (Python), `packages/db` (Postgres/Prisma), `packages/shared`.
- Database is the source of truth. Public pages serve only published, validated editions.
- Fixture/mock mode works without external API keys or network access.
- News records need auditable source attribution, separate published/event dates, and idempotent ingestion.
- Do not generate false facts, sources, citations, industrial project claims, or metrics.
- Avoid unjustified dependencies, scraping restrictions, and embedding copyrighted articles.

## Delegation and ownership
- `frontend`: owns `apps/web/**` except cross-team shared contract files.
- `pipeline`: owns `services/pipeline/collectors/**`, `extraction/**`, `dedup/**`.
- `editorial`: owns `services/pipeline/scoring/**`, `editorial/**`, `verification/**`, `translation/**`.
- `database`: owns `packages/db/**` only after lead approves schema contract.
- `qa`: owns relevant testing configuration/tests under `tests/**` and CI checks; coordinate tests under another agent's owned directory.
- `publishing`: owns RSS, deployment and scheduling after frontend and pipeline contracts stabilize.
- Lead exclusively owns `AGENTS.md`, `TASKS.md`, root package configuration, shared contracts, and integration merges.
- Assign bounded tasks with expected deliverables, write boundaries, verification commands and acceptance criteria.
- Spawn independent agents simultaneously only after contracts are frozen. Agents must not edit each other's areas or shared files.
- If native delegation is unavailable, use the same task allocation sequentially without fabricating agents.

## Quality gates
- Each milestone: functional code, tests, lint/format/typechecks where applicable, error handling, README commands.
- Report actual command results; never claim execution without running it.
- Keep every `.md` file under 100 lines. Keep directions concise and maintainable.
- Preserve progress in `TASKS.md` only from the main agent. Mark incomplete work honestly.
- Do not auto-deploy publicly, send emails, purchase services, or expose credentials without explicit authorization.
