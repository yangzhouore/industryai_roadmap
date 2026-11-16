# CI matrix and browser isolation

## Jobs
- Offline: backend mocked-provider tests, frontend reader tests, fixture replay,
  typecheck, lint, build, all 24 fixture HTTP checks and the existing browser assertions.
- PostgreSQL: all migrations and isolated write integration, replay/constraints,
  then separate database-mode HTTP acceptance on a uniquely owned temporary schema.
- Database smoke setup accepts only explicitly isolated TEST_DATABASE_URL targets.
  It never uses the production DATABASE_URL as a source of writable test data.
- The temporary projection includes a source-grounded NIST research snapshot,
  with the original 2024 source date and mocked editorial review. It is QA data,
  not a new publisher announcement, and is removed with its owned test schema.
- Checks require the public validated bilingual projection to appear in routes,
  archive, search, RSS and sitemap, while synthetic, draft, validated-only and
  malformed rows remain hidden. A 404 for a synthetic date is required, not ignored.
- The normal public reader is unchanged. Fixture and database assertions are separate.

## Chromium on hosted Ubuntu
- Stable Chrome and its installed setuid sandbox helper are selected explicitly.
- Browser launch first attempts normal sandboxing. No global AppArmor or kernel
  security setting is changed.
- If Ubuntu returns the known `No usable sandbox!` launch error, an explicit
  CI_CHROMIUM_NO_SANDBOX=1 permits a retry with `--no-sandbox` only when Linux,
  CI=true and GITHUB_ACTIONS=true all match. Local invocation fails closed.
- This opt-out removes Chromium's renderer isolation and would be unsafe for
  arbitrary web content. It is limited to a disposable hosted runner with no
  OpenAI/production secrets and a loopback fixture server; never use it in production.
- The harness refuses remote browser targets and retains all accessibility,
  desktop/mobile, contrast, keyboard and locale assertions. Browser checks stay enabled.
- Browser screenshots/report are uploaded even after failures for diagnosis.
- Chrome has a bounded 90-second startup window on busy runners, accepts its
  documented stderr debugging endpoint as well as DevToolsActivePort, and reports
  launch errors/signals explicitly. Readiness never skips browser assertions.
- Checkout does not persist the GitHub read token into the working tree.
- Chromium's supported helper/fallback options are documented in its
  [Ubuntu sandbox guide](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md).

## Paid-call prevention
- CI never receives OPENAI_API_KEY or production secrets; the key is explicitly blank.
- Tests inject mocked HTTP; no workflow invokes the live/backfill editor.
- UNATTENDED_PAID_APPROVED is false. No scheduler activation or release-tag changes.
- A tracked-blob secret/path scan rejects realistic credentials, private keys and
  sensitive runtime/environment files without echoing matching values.
