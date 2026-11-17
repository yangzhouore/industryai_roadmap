# MVP-4.1 CI and production preparation

## Commits and remote verification
- Started from d70a34f; immutable mvp-4 still targets e7524d058222fda369cd0ab4d2d4852d7ef67b38.
- Dedicated CI repair: 481951f; follow-up slow-Chrome startup/credential hardening: 0ec9e92.
- [Run 43900708777](https://github.com/yangzhouore/industryai_roadmap/actions/runs/43900708777) passed both offline and PostgreSQL jobs.
- Original sandbox/fixture-visibility failures were inspected in run 43854684646 and repaired without changing the public reader.
- Browser tests retain all 105 assertions; fixture HTTP checks and isolated real-data visibility checks are separate.
- CI receives no real OpenAI key and does not invoke the live editorial or historical backfill runner.
- Final infrastructure commit adds native Ubuntu/systemd/Caddy validation and encrypted PostgreSQL recovery to the same workflow.
- Production preparation 701009b passed both jobs in [run 44049852883](https://github.com/yangzhouore/industryai_roadmap/actions/runs/44049852883).

## Local verification completed
- Backend: 170 tests passed with isolated PostgreSQL integration enabled (102 repository tests +68 pipeline tests).
- Frontend: nine tests, lint, typecheck and production build passed.
- Fixture HTTP: 24 checks; browser: 105 checks with normal sandboxing; PostgreSQL HTTP projection: 54 checks.
- Production configuration: 10 guard tests and four shell syntax checks passed.
- Recovery: 15 tests passed, including actual pg_dump/age/pg_restore and protected temporary password files.
- Staged secret/path scan: 189 files, zero findings; every project Markdown file is below 100 lines.
- Native Ubuntu systemd/calendar/shell/Caddy parsers and actual encrypted PostgreSQL recovery passed remotely.

## Actual data preservation and recovery
- Captured fingerprints of all 19 current public database tables before this work; no source records were changed.
- A real read-only pg_dump 18.7 snapshot was streamed into age 1.3.2 encryption without a plaintext dump file.
- Restored into a new isolated industrial_ai_restore_* target, never an existing application database.
- All 19 table hashes, 140 real articles, November 6/9/13 bilingual editions and one immutable revision matched.
- Repeated the real-data roundtrip November 17 after hardening, including byte-identical budget state and UTC-normalized fingerprints.
- Recovery rejects nonempty targets, functions/types, same-source names, invalid identities and existing state files.
- Test ciphertext/identity/report remain ignored private artifacts under artifacts/mvp41.
- Transport custody was explicitly simulated locally; actual external-cloud transfer is not claimed.

## Prepared production configuration
- Ubuntu host-native services: Node SSR, Python worker, private PostgreSQL 18, Caddy TLS, persistent logs and health checks.
- Separate OS/database identities; protected environment files; no default production credentials; no public port 5432.
- Berlin 07:00/09:15 timer, dry-run worker by default; encrypted backup timer and off-host approval are also inactive.
- Explicit preparation helpers refuse existing clusters, identities, modified releases and unsafe secret/build inputs.
- Backup source is read-only; restore writes only an isolated empty target; off-host cloud backends fail closed.
- [Security review](SECURITY_REVIEW.md) records independent findings and remaining target-host validation gates.

## Remaining deployment gates
- Provision a separately approved host/domain/TLS and scoped secrets, then validate the actual host and alert delivery.
- Approve independent off-host storage/identity custody and verify a real remote upload/download/restore before activation.
- Resolve publisher-specific public reuse/translation rights; MIT's conditional story grant is not blanket clearance.
- Triage development-only dependency advisories; production-only audit currently reports zero findings.
- No paid API calls, unattended activation, public deployment, VPS purchase or MVP-5 work occurred.
