# Local human editorial review workbench

## Scope and operator trust
- `python -m services.review` works privately; it never publishes, calls AI, installs policy or writes PostgreSQL.
- Default state is ignored `artifacts/editorial-review`; repository-local state is restricted to ignored artifacts subdirectories.
- External state must be owner-private; served/public/shared directories and symlink paths are refused.
- Source import uses PostgreSQL read-only transactions. Stored editions, excerpts and revision history remain unchanged.
- No identities, passwords, reviews or genuine approvals are seeded. Agents use artificial temporary actors only in tests.
- An operator must verify actual people and authority outside this tool; a local password/attestation cannot prove legal identity.
- The first administrator requires explicit bootstrap and private identity evidence. Later enrollment requires an authenticated administrator.
- Users of the same OS account share its trust boundary; OS administrators can replace the journal or code.
- Hash chains and immutable triggers detect ordinary changes; they are not external signatures against a malicious OS owner.

## Identity setup (human action only; never executed by an agent)
- Put a nonempty identity attestation in a private file and create owner-only JSON with `reason: {en, zh}`,
  `files: [absolute private path]` and `references: [documented HTTPS URL]`; all three fields are mandatory.
- Example invocation structure (replace every uppercase identity placeholder with an actually verified person):
  `python -m services.review enroll --bootstrap --human-id HUMAN-ID --name "VERIFIED HUMAN" --role administrator --identity-evidence PRIVATE-JSON`
- Passwords require 15-1024 characters and are entered twice with interactive getpass, never flags, files, environment variables or command history.
- Use an authenticated administrator to enroll separate authors/reviewers; repeat `--role` for explicitly verified roles.
- Every later command needs `--actor HUMAN-ID` before its subcommand and a fresh password entry.
- PBKDF2-HMAC-SHA256 uses 600,000 iterations and independent 32-byte salts; sessions are opaque and expire after 120 seconds.
- Five failures within 15 minutes block further login during that window. Attempts and successful logins are journaled.
- Password reset, role changes and account retirement require separately designed recovery; none silently rewrites identity history.

## Read, draft and inspect
1. `--actor AUTHOR source-list` lists available real source IDs/dates through the protected DATABASE_URL setting.
2. `--actor AUTHOR import --issue-id STORED-ID --reason "Actual reason"` imports the source unchanged into a private candidate.
3. `--actor AUTHOR list` reports revision IDs, lineage, hashes, actors and change reasons.
4. `--actor AUTHOR show --revision REV --output draft.json` writes private `drafts/draft.json`, refusing overwrite.
5. Edit that private Issue JSON. Only issue title/introduction, story editorial fields/citations and candidate asset removal may change.
6. `--actor AUTHOR revise --revision REV --input PRIVATE-DRAFT --reason "Actual reason"` creates a new immutable snapshot.
7. `--actor REVIEWER report --revision REV --output report-name` writes escaped bilingual private analysis under `reports/`.
8. `--actor REVIEWER status --revision REV` displays findings, decisions, reasons, references, evidence hashes and approval state.
9. `--actor REVIEWER audit` displays the private event chain with password hashes/salts removed; `verify` checks journal integrity.

Every example above follows `python -m services.review`; use `--state-dir PRIVATE-DIRECTORY` before the subcommand if needed.
Imports can only come from read-only PostgreSQL through the CLI, never a replacement source file.
Revisions preserve publisher names, URLs, timestamps, excerpts, identities and historical source JSON exactly.
All authors anywhere in a candidate lineage are disqualified from reviewing that candidate.

## Evidence and decisions
- Review JSON always includes bilingual `reason`, actual private `files`, and documented HTTPS `references`.
- Files are bounded, hashed and retained privately by content address; approval/export rechecks their exact bytes.
- Credential paths/content, symlinks/reparse points, oversized input and missing evidence are refused; still inspect evidence for secrets manually.
- `decide --revision REV --scope story|link --target EXACT-ID --status pending|rejected|approved --review-file PRIVATE-JSON`.
- Story `checks` require booleans for originality_en, originality_zh, facts, citations and assets; all must be true for approval.
- Story `claims` maps each documented bilingual `claim` and `support` to exact cited `sourceIds`; approved stories need a nonempty map.
- Link reviews require exact `url`, `publisher`, `basis` (permission or legal-review), and `intendedUse: public-web`.
- Reviews may include `riskResolutions: [{findingId, reason: {en, zh}}]`; all current findings need documented resolution before final approval.
- Final review `checks`: title_introduction_en, title_introduction_zh, facts, citations and assets, all true.
- Findings/templates are heuristic prompts, not proof of originality, factual accuracy, authority or legal permission.
- Review both languages and every claim, title, introduction and source condition; no checkbox substitutes for that actual work.

## Final approval, previews, export and revocation
- `finalize --revision REV --review-file PRIVATE-JSON` requires complete current decisions and reviewer password confirmation again.
- A new revision invalidates prior decisions/approvals; stale revisions cannot export or become public previews.
- `preview --revision REV --output preview-name` writes private offline EN/ZH pages/RSS under `previews/`.
- Unapproved previews are withheld; approved previews receive only the exact existing shared PublicIssue gate projection.
- Full private evidence reports are separate from public projections; excerpts/assets/extra payloads never enter previews.
- `export --revision REV --output bundle.json` writes a NEW private `exports/bundle.json`; it does not install anything.
- The bundle contains private candidate JSON plus exact policy and audit metadata; never serve the bundle as a public file.
- `revoke --revision REV --review-file PRIVATE-JSON` appends revocation with documented evidence; later export is denied.
- Revocation cannot retract prior exported bundles or deployed static policies. Invalidate those artifacts and rebuild/release separately.
- Never install an older bundle without checking current journal approval/revocation; a release needs fresh human verification and authorization.
- Actual bilingual review, source-specific permission, real operator identity and independent legal judgment remain pending.
- Production launch, policy installation, source-data revision and paid automation require separate authorization.

## Verification
- `python -m unittest discover -s services/review -p 'test_*.py' -t . -v`
- Root `npm test` includes workbench tests. Shared bridge: `node packages/shared/public-display-cli.cjs` with bounded JSON stdin.
- Use only synthetic temporary actors/approvals in tests; protected source-table fingerprints and empty trusted policy must remain intact.
