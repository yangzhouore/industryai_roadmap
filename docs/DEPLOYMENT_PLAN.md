# MVP-4 release and deployment plan - 2026-11-16

## Release state
- Verified a clean checkout at e7524d058222fda369cd0ab4d2d4852d7ef67b38 before release.
- Pushed main fast-forward and annotated mvp-4; the tag targets that exact accepted commit.
- No history rewritten, deployment performed, credential changed or paid scheduler activated.
- Initial [branch/tag CI runs](https://github.com/yangzhouore/industryai_roadmap/actions?query=workflow%3AVerify) failed smoke checks; MVP-4.1 repair is recorded below.
- [Run 43852949645](https://github.com/yangzhouore/industryai_roadmap/actions/runs/43852949645) and
  [run 43852949664](https://github.com/yangzhouore/industryai_roadmap/actions/runs/43852949664) passed tests, migrations, lint/typecheck and builds.
- Offline failure: Chromium cannot start its sandbox on the Ubuntu runner; HTTP route checks passed first.
- PostgreSQL failure: smoke expects synthetic November 12 content; normal database mode correctly returns 404.
- Remedy: sandbox-compatible browser setup; separate fixture-route tests from real-only database visibility tests.
- Keep mvp-4 immutable; any CI repair needs a new follow-up commit and verified checks before deployment.
- CI installation reported six moderate advisories in the full dependency tree; production-only npm audit reports zero.
- Triage the build/development advisories before rollout; no package versions were changed in this audit.
- MVP-4.1 repair 0ec9e92 passed both jobs in [run 43900708777](https://github.com/yangzhouore/industryai_roadmap/actions/runs/43900708777).
- Prepared Ubuntu code is under deploy/linux; native parser/recovery checks are now part of the CI matrix.
- See [MVP-4.1 verification](MVP41_ACCEPTANCE.md), [Linux setup](LINUX_DEPLOYMENT.md) and [source rights audit](SOURCE_REUSE_AUDIT.md).

## Recommended low-cost architecture
- One always-on EU/UK Linux VPS, initially 4 vCPU/8 GB RAM/75 GB disk, using OVHcloud VPS-2 as a cost reference.
- TLS reverse proxy (Caddy/nginx) -> Next.js Node SSR on loopback; PostgreSQL and Python worker on the same host.
- Private DB socket/loopback removes internet DB reachability and pooling problems; never expose port 5432 publicly.
- Use direct/session PostgreSQL connections: transaction pooling breaks session-level advisory run locks.
- One host is economical, not highly available; operator owns patching, monitoring, restore and capacity management.
- Prefer PostgreSQL 18 for the existing portable 18.x dataset; pg_trgm and all three reviewed migrations are required.
- Restore a verified logical backup into a NEW target only after authorization; do not downgrade or overwrite the local DB.
- Restore acceptance must match 140 real articles, the exact three bilingual dates and archived content/review hashes.

## Runtime and storage requirements
- Node 22+, npm ci, npm run db:generate, npm run build; retain workspace packages and generated Prisma client.
- Serve apps/web with next start behind TLS; current start binds 127.0.0.1, suitable for the same-host proxy.
- A PaaS/container instead needs 0.0.0.0 and its PORT; static-only hosting cannot serve database-backed routes.
- Python 3.11+ venv, requirements.txt, timezone data and tested psycopg/libpq; lock/test exact versions before rollout.
- Host-native systemd services/timers, Caddy, private PostgreSQL, health and backup configuration are implemented in deploy/linux.
- Existing compose.yaml is development-only: demo password and published DB port must not be used in production.
- Persist PostgreSQL data including api_requests, automation_cache/runs/events, evidence and immutable edition_revisions.
- Persist private artifacts/reports outside replaceable code releases; securely carry artifacts/mvp3/budget.json for November.
- That November file remains required by the runner even after carryover charges were imported into PostgreSQL.
- Daily encrypted logical backups to a separate provider/location; retain seven daily/four weekly copies and test restore.
- Provider VM snapshots supplement backups; they do not establish database restore correctness or off-site protection.

## Scheduling and availability
- Proposed timer: OnCalendar=*-*-* 07:00:00 Europe/Berlin, Persistent=true, AccuracySec=1s; retry at 09:15.
- Installed IANA timezone data handles CET/CEST automatically; sync the server clock with NTP.
- [Calendar syntax](https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html),
  [timer catch-up/accuracy](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html).
- Run daily tick --resume from the repository root; add --allow-paid only after separate explicit approval.
- Give the oneshot worker an explicit long timeout (for example 30 minutes); systemd's short default can kill valid runs.
- PostgreSQL locks prevent overlap; resume is durable; missed historical days remain visible rather than fabricated.
- Alert on missed/failed runs and exhausted budget; target 07:00 execution does not guarantee zero infrastructure delay.
- VPS execution is independent of Windows sleep/shutdown; an offline VPS catches up after restart, not while powered off.
- Keep the GitHub paid workflow disabled as a second scheduler; hosted Actions would need a securely reachable DB.

## Environment and credential separation
- Web: DATA_MODE=database, private read-only DATABASE_URL, SITE_URL at both build and runtime; no OpenAI key.
- Worker: write-capable DATABASE_URL, OPENAI_API_KEY, Luna classification, Terra generation/review and low reasoning.
- Migration role is separate; use restricted secret files/service credentials, never Git or NEXT_PUBLIC_* for secrets.
- Runtime model routing is fixed by daily.py; configuration cannot silently switch to a fallback model.
- Both config.unattendedPaidApproved and process UNATTENDED_PAID_APPROVED remain false; no credentials provisioned here.
- New hosted secrets/roles, domain/TLS and source reuse approvals require explicit provisioning/deployment authorization.

## Monthly costs: hosting and API are separate
| Item | Planning estimate | Basis |
| --- | --- | --- |
| VPS-2 | From GBP 6.29 ex VAT | [OVHcloud UK](https://www.ovhcloud.com/en-gb/vps/), advertised 4 vCPU/8 GB/75 GB; confirm term/renewal/region/stock |
| Independent encrypted backup storage | GBP 2-4 allowance | Estimate for this small dataset; provider/retention quote pending |
| Domain | GBP 1-2 equivalent | Optional planning allowance, usually billed annually; not a registrar quote |
| Hosting total | Budget GBP 10-15 ex VAT | Includes margin, excludes operator labor and unusual traffic/storage growth |
| OpenAI | Illustrative USD 1.13/30 days; USD 2 app ceiling | Token scenario below; this is not a provider/account billing cap |

Rates per million input/output tokens: [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) USD 0.10/0.50;
[Terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra) USD 1/5; cache rates differ.
Example daily totals: Luna 8k input/2k output + Terra 16k input/4k output = USD 0.0378; times 30 = USD 1.134.
Volumes/retries vary; reservations and failed calls count, and the pipeline stops when the next call cannot fit.
Actual provider billing/taxes/other API use may differ; no account spending settings are changed.
November app estimates already include USD 0.10947285; remaining estimated budget is USD 1.89052715.
Managed alternative: [Railway](https://docs.railway.com/pricing), USD 5 minimum credited toward usage;
budget roughly USD 15-25 for web, private PostgreSQL and worker/storage, subject to measured usage and backup costs.

## Current local status and deployment blockers
- Read-only status succeeded with the documented portable libpq fallback; unattendedPaidApproved=false.
- November 14/15/16 are reported as missed slots while activation remains disabled; no catch-up/paid run was executed.
- Existing 140 articles, three bilingual digests and revision history must remain intact through any future migration.
- Blockers: target-host validation, approved off-host credentials/custody, secret provisioning and publisher reuse clearance.
- All enabled feeds specify local_noncommercial and redistribution_permitted=false: public source/attribution review is pending.
- No live paid end-to-end hosted verification, public deployment or unattended activation is authorized by this plan.
- MVP-5 has not started. Release is recorded; public deployment readiness remains blocked by the items above.
