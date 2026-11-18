# MVP-4.3 independent security review

## Scope and trust boundary
- QA reviewed separately authored journal/authentication, analysis/rendering and shared gate code.
- Tests use artificial temporary actors, files and approvals; agents enrolled no real identity.
- This is a local CLI with interactive passwords, no public review endpoint or paid API call.
- Actual identity verification and enrollment authority remain operator responsibilities.
- Unique local IDs and separate passwords cannot prove that two accounts are different humans.

## Authentication and evidence
- PBKDF2-HMAC-SHA256 uses 600,000 iterations, random 32-byte salts and constant-time comparison.
- Fixed stored parameters reject overrides; passwords are bounded to 15–1024 characters at enrollment.
- The 15-character minimum follows current [NIST single-factor guidance](https://pages.nist.gov/800-63-4/sp800-63b.html).
- This meets the [OWASP PBKDF2 baseline](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#pbkdf2).
  OWASP prefers memory-hard algorithms where available; this implementation chooses the standard library for portability.
- [Python guidance](https://docs.python.org/3/library/hashlib.html#key-derivation) supports slow salted derivation,
  adequate random salts and bounded password input. No FIPS certification is claimed.
- CLI passwords require a TTY/getpass; flags, stdin and environment cannot supply authentication.
- Opaque sessions stay in memory for 120 seconds; five failures lock the account for 15 minutes.
- Evidence is copied into private content-addressed storage and hashed against actual bytes.
- HTTPS references document human review; software does not authenticate a publisher's permission grant.

## Findings addressed during cross-review
- Credential evidence filters originally missed worker.env, PostgreSQL service and credential JSON files.
  Backend now rejects those paths; independent tests submit artificial credential-named files and require refusal.
- State/report paths could previously enter tracked repository directories such as docs.
  Backend/render guards now allow repository artifacts only; renderer tests require rejection before creation.
- Full candidate lineage contributes to author disqualification, including an author of an earlier revision.
- Final approval requires fresh password confirmation, all story/link decisions, evidence and risk resolutions.
- Exports use the exact shared TypeScript web gate; no environment or preview bypass installs approvals.

## Journal and output limits
- SQL triggers prevent UPDATE/DELETE; transaction locks serialize append operations; the event chain detects edits.
- The journal is not tamper-proof against its OS owner/administrator, who can replace files and recompute hashes.
  Independent external custody/anchoring would be needed for that stronger guarantee.
- Private directories, bounded files, symlink/reparse checks and exclusive output creation reduce accidental exposure.
- Reports escape retained evidence, use restrictive CSP, load no remote assets and never overwrite outputs.
- Public previews contain only shared-gate projections or a withheld state, without source excerpts.
- Local revocation blocks future bundles; it cannot retract an already copied bundle or change deployed policy.
- PostgreSQL source reads set and verify read-only transactions; no source migration/write is part of this workflow.

## Verification evidence
- Independent shared bridge: five tests passed; exact approvals, stale hashes, bounded transport and redaction.
- Independent source/CLI: three tests passed; read-only SQL, parameterization and password-input refusal.
- Real Chromium: 17 artificial report/preview cases passed; three screenshots visually checked.
- Full local runs passed: review 22 tests; backend 119; pipeline 68; targeted final race/tamper checks passed.
- Frontend 16 tests, lint, typecheck, build, 17 Chromium checks and database denial smoke passed.
- Isolated encrypted backup/restore and deployment suites passed; live source fingerprint is unchanged.
- Current public policy remains empty; no real edition receives approval from these tests or this report.
