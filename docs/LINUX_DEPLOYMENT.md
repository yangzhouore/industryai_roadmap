# Ubuntu production configuration - prepared, not deployed

No VPS has been purchased or configured. All units remain uninstalled/inactive here.
The default pipeline service runs **dry-run only**, with no paid API permission.
Public deployment still requires the source reuse approval in `SOURCE_REUSE_AUDIT.md`.

## Layout and prerequisites
- Ubuntu 24 LTS; Node 22+, Python 3.12/venv, PostgreSQL 18 with pg_trgm, Caddy, age, rclone and POSIX ACL tools.
- Install packages from their official signed repositories after provisioning approval:
  [PostgreSQL Ubuntu](https://www.postgresql.org/download/linux/ubuntu/), [Caddy](https://caddyserver.com/docs/install).
- Release code: `/srv/industrial-ai/releases/<approved-commit>`; `current` points to the approved release.
- Python environment: `/srv/industrial-ai/venv`; persistent data: `/var/lib/industrial-ai`.
- Secrets: `/etc/industrial-ai/*.env`, root-owned 0600; templates contain no credentials.
- PostgreSQL's dedicated `18/industrial_ai` cluster listens on 127.0.0.1:5432 only.
- Web/worker/backup OS accounts are separate; PostgreSQL owner/web/worker/backup roles are separate.

## Future provisioning procedure (not executed)
1. Check prerequisites with `bash deploy/linux/bootstrap.sh --check`; this never mutates services.
2. After explicit target approval, `sudo bash deploy/linux/bootstrap.sh --provision` prepares directories/units.
3. No existing secret file or differing service file is overwritten; no services/timers are enabled or started.
4. `sudo bash deploy/linux/provision-postgres.sh --provision` creates a NEW stopped dedicated cluster only.
5. Existing cluster paths or a listener on 5432 cause refusal; other clusters/data are never modified.
6. Review the private cluster config, firewall 80/443 and restricted SSH; PostgreSQL must never be internet-facing.
7. Only then start the NEW private cluster under separate deployment approval.
8. Supply four strong unique passwords in protected environment variables named by `environment/database.env.example`.
9. `provision_database.py --provision` creates NEW scoped roles/database via local postgres peer authentication.
10. Any existing role/database causes refusal. No development passwords, URI passwords in arguments or password logs.
    Both provisioning/grant sessions verify the exact dedicated cluster config/data paths before any mutation.
11. Configure migration.env with the owner connection and apply reviewed migrations as that role, never seed/reset.
12. Run `grant_database.py --apply` locally as admin after migrations to grant bounded worker and read-only reader/backup access.

## Build and release preparation
- Check out the approved full commit into a NEW `/srv/industrial-ai/releases/<40-character-commit>` directory.
- Run `sudo bash deploy/linux/prepare-release.sh --prepare <new-release-path>` only after target preparation approval.
- The helper builds with the dedicated unprivileged industrial-build account; only SITE_URL reaches build processes.
- Use DATA_MODE=database; SITE_URL must be the real HTTPS origin at build and runtime.
- The helper creates a per-release Python venv, records resolved packages and seals runtime code root:industrial-ai.
- Post-build Git checks compare tracked code to the original approved commit; root checks disable hooks/fsmonitor/external diff.
- It creates `.next/cache` with industrial-web ownership; no missing writable path can block the web unit.
- A failed/previous preparation is refused; the helper never overwrites an existing venv, state tree or current release.
- Under separate deployment approval, link `current` to the prepared release and `/srv/industrial-ai/venv` to `current/.venv`.
- The helper links only that new release's artifacts to persistent state; it never selects current or starts any unit.
- Make `apps/web/.next/cache` writable only by industrial-web; worker reports remain industrial-worker-owned 0700.
- Copy the private legacy November budget file securely to persistent `artifacts/mvp3/budget.json` before paid execution.
- Web DATABASE_URL must use industrial_web, worker uses industrial_worker, backup uses industrial_backup.
- Production database URLs reject query parameters/fragments so libpq cannot override the checked loopback host or role.
- Health uses industrial_web's read-only connection, but runs as industrial-worker so it can inspect private report freshness.
- Web and health must receive no OpenAI key. Worker key is server-side only; examples reject missing/default credentials.
- Fill proxy.env with approved SITE_HOST/ACME_EMAIL; placeholders fail preflight before any app proxy is started.
- Caddy serves TLS to 127.0.0.1:3000; its admin API remains loopback and access logs rotate under `/var/log/industrial-ai`.

## Scheduling, monitoring and activation boundaries
- The timer targets 07:00 and 09:15 Europe/Berlin with Persistent=true, AccuracySec=1s and current IANA timezone data.
- PostgreSQL session locks prevent overlap; the worker has a 30-minute timeout and uses the existing durable resume ledger.
- Units use private temp directories, protected filesystems and journald; persistent journal retention is bounded to 30 days.
- The health timer runs every five minutes; private health checks HTTP, read-only database access and active-run freshness.
- Alert routing from failed systemd units/journal is operator-provided and must be tested before paid activation.
- Default units contain no `--allow-paid`; bootstrap never enables any web/worker/health/backup timer or Caddy service.
- The paid drop-in is an uninstalled `.example` and additionally requires an explicit approval marker.
- Paid activation needs separate user approval, config.unattendedPaidApproved=true and process UNATTENDED_PAID_APPROVED=true.
- A sleeping/shut-down Windows laptop is irrelevant to the VPS; an unavailable VPS can only catch up after it restarts.

## Backup, recovery and verification
- Backup credentials are separate, read-only and private; age recipient encryption needs no private key on the VPS.
- Recovery identity and isolated restore target credentials stay off the live worker; see database recovery documentation.
- Backups must include database evidence/reviews/automation tables and the separately preserved legacy state file.
- Daily off-host encrypted backup service/timer are supplied with the recovery tooling; they also remain disabled.
- `BACKUP_OFFHOST_APPROVED=false` prevents upload until an independent off-host destination is approved.
- Rclone's owner-only configuration belongs under the industrial-backup state directory, outside inaccessible root secret dirs.
- After explicitly installing the legacy ledger, `prepare-legacy-state.sh --allow-backup-read` grants targeted read/traverse ACLs.
- No API key is made readable; November backups fail closed if that required ledger is missing or unreadable.
- `--state-file` places exact ledger bytes/hash inside the encrypted manifest, without an extra plaintext copy.
- Restore supplemental state only via recovery `--state-output` in the new isolated target directory; verify its hash first.
- Restore only into an explicitly isolated empty target; assert article counts, all bilingual dates and revision hashes.
- Offline guard tests: `python -m unittest discover -s deploy/linux -p 'test_*.py' -v`.
- Ubuntu parser checks: `python deploy/linux/validate_linux.py`; no units are installed or started by validation.
- Validate backups/restores in isolation, then public HTTP/metadata/TLS/source attribution and secret separation before release.
- No service activation, PostgreSQL modification, public deployment or paid API request was performed by this preparation.
