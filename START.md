# START — Codex entrypoint

You are the lead orchestrating agent. Follow the current user request; do not start a new milestone automatically.

MVP-3 is implemented locally: 140 real articles, three published bilingual editions
(November 6, 9 and 13, 2026), and one archived November 13 revision.
Read `docs/MVP3_BACKFILL_REPORT.md` before resuming. Preserve existing PostgreSQL data.
MVP-4 automation code is implemented; paid unattended execution remains disabled.
Read `docs/MVP4_OPERATIONS.md` for scheduling, status, monthly budget and activation requirements.

1. Read `AGENTS.md`, `TASKS.md`, and `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DESIGN.md`, `docs/PIPELINE.md`.
2. Check repository state, tooling, dependencies, and available native Codex subagents.
3. If browser/web access is available, inspect https://ai-digest.liziran.com/en/ (home, digest, sources, archive, search, methodology, privacy, EN/ZH). Record verified facts versus assumptions. If unavailable, use supplied requirements and proceed.
4. Check the existing implementation and `TASKS.md`; M0-M5 and MVP-2/MVP-3 are complete locally.
5. Preserve shared contracts and existing functionality before delegating any authorized implementation.
6. **Explicitly spawn independent Codex subagents concurrently**, when supported, for frontend, collection, editorial and QA with exclusive file ownership (see `AGENTS.md`). Wait for their results, integrate and run checks. Do not invent agent execution.
7. Use offline fixtures and mocked providers for routine tests; use a disposable database for database-writing tests.
8. For each milestone report files changed, checks actually run, blockers and next action. Keep working after reporting.

## Success definition
Local developer can run the database, seed fixtures, start site, browse all routes in EN/ZH, run an offline digest pipeline, publish a validated edition, use archive/search/RSS, and rerun ingestion without duplicates.

## Immediate Codex user message
Follow the current user request. Do not rerun historical backfill, regenerate articles,
enable unattended paid jobs, push or deploy without the required authorization.
