# Testing and acceptance

## Foundation
Install/start from clean checkout, .env.example, Docker DB, migrations and fixture seed; verify no private credentials required.

## Frontend
Route tests for every EN/ZH page; locale switching; keyboard navigation, basic accessibility, responsive layouts, empty/error states, metadata and search behavior.

## Pipeline
RSS/XML parsers, canonicalization, publish vs event date, URL security, duplicate and syndicated reports, independent source counts, score versioning, retries, timeouts and partial failure.

## Editorial
Mock provider outputs; Pydantic rejection of malformed text; fabricated URLs; ungrounded metrics; EN/ZH figure mismatches; refusal to publish incomplete issues; fewer than 3 stories handled.

## Integration
Run fixture import twice -> unchanged counts; draft -> validated -> published; browse same issue EN/ZH; issue appears in archive, search and RSS. Run lint, TS typecheck, unit and integration tests, Python formatting/lint/pytest where installed.

## Reporting
Only report actually run commands and results. Note untested external providers and deployment work separately.
