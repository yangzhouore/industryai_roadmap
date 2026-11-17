# MVP-4.1 security review - conditional deployment readiness

## Scope and independence
- Cross-author source reviews covered Linux provisioning, PostgreSQL, recovery and
  the secret scanner; the infrastructure reviewer independently reviewed recovery.
  This is not a penetration test or a live-host security certification.
- Review used source inspection, local guard tests, actual GitHub job logs and
  read-only Windows ACL checks. No production service or paid job was activated.
- CI repair commit 0ec9e92 passed both jobs in
  [run 43900708777](https://github.com/yangzhouore/industryai_roadmap/actions/runs/43900708777).
- That run retained all 105 browser assertions and 24 fixture HTTP assertions;
  the browser log had no sandbox-fallback warning. Separate PostgreSQL visibility checks passed.

## Secrets, privilege and network boundaries
- Root .env.local still has inheritance disabled and exactly three explicit allowed
  principals: the Windows owner, SYSTEM and Administrators. No credential values were printed.
- Environment files and runtime artifacts remain ignored. The tracked-file scanner
  detects configured OpenAI keys when available, realistic tokens, private keys and age identities.
- Review closed force-add path gaps for .pgpass, .pg_service.conf and cloud credential JSON files;
  path tests pass. Pattern scanning cannot establish that arbitrary prose contains no secret.
- Production templates contain blank secrets; preflight rejects example hosts,
  weak database credentials, incorrect roles and an OpenAI key on the web reader.
- Production URI checks now reject query parameters/fragments: libpq host/user overrides
  cannot bypass the checked loopback destination and role; behavioral regression tests pass.
- Web, worker, build and backup OS identities are separate; migration privileges
  are distinct from runtime database privileges. PostgreSQL is bound to loopback only.
- Package lifecycle/build commands run as industrial-build with public SITE_URL,
  without runtime database/API credentials; prepared runtime code is sealed root-owned.
- Caddy is the public TLS entrypoint. PostgreSQL 5432 and the Caddy admin API must
  remain private; target firewall/DNS/TLS verification is still required before release.
- Bootstrap/provision/build helpers default to checks and do not start or enable services.
- Paid execution remains dry-run by default and needs separate explicit approval,
  config/process gates and the uninstalled paid-worker drop-in/approval marker.

## Backup and recovery findings
- Source capture is a read-only exported PostgreSQL snapshot. pg_dump streams
  into age encryption; clear database dumps are not staged on disk or printed.
- Database passwords use protected transient libpq files rather than command arguments.
- Archive and manifest are encrypted; the manifest binds ciphertext and complete
  table/content/review fingerprints. UTC normalization avoids timezone-only hash failures.
- age provides ciphertext integrity, not sender identity. Trusted off-host write custody or
  separately verified backup provenance is required before privileged restoration; no signature is claimed.
- Restore requires a separately named isolated target and rejects existing relations,
  functions, types, extensions and other user objects; source data is never overwritten.
- Off-host production destinations need approval, supported cloud backends and
  verified HTTPS endpoints; local aliases, private endpoints and insecure overrides fail closed.
- Review found rclone SFTP defaults do not verify server host keys, risking backup
  credentials. The implementation now rejects SFTP instead of claiming it is secured.
  [rclone host-key documentation](https://rclone.org/sftp/#host-key-validation).
- Runtime rclone/cloud endpoint overrides are rejected so validation matches transfers.
- Encrypted local transport exercises recovery mechanics; it does not prove independent
  off-host custody. Actual cloud credentials, retention permissions and alert routing remain untested.
- Windows recovery state/identity checks restrict access; private recovery identities
  must stay off the live worker and outside Git. No existing identity was changed.

## CI-only sandbox exception and remaining release gates
- Chromium tries normal sandboxing first. Only its explicit sandbox-launch failure
  permits the opt-in fallback on GitHub Linux CI, using a loopback fixture target.
- That exception removes renderer isolation; it is not suitable for arbitrary websites
  or production. Checkout no longer persists its read token, and CI receives no paid API secret.
- [Chromium guidance](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md).
- Conditional sign-off covers prepared code/configuration, not a live host or legal clearance.
- Before deployment: approve target/domain/secrets, attest independent backup storage,
  test restoration/alerts/TLS on the target, triage build advisories and review source-reuse evidence.
- Cloud account policies, operator access and publisher permission still need explicit decisions.
- Dependency audit rerun November 17: `npm audit --omit=dev` exited 0 (zero advisories);
  full `npm audit` exited 1 with six moderate findings, zero high/critical, tracing to minimatch
  [glob amplification](https://github.com/advisories/GHSA-g3hv-75wg-m249) through TypeScript ESLint. Builds run without runtime secrets;
  CI has 20-minute timeouts. A tested dependency refresh remains separate maintenance; no runtime exposure is claimed.
- No blanket public-republication approval, service activation or MVP-5 work is implied.
