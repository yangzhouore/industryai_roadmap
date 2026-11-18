# MVP-4.3 frozen local editorial review contract

## Boundaries
- Existing PostgreSQL is READ ONLY. No migrations or source edition/revision writes in this milestone.
- CLI: python -m services.review; local state default artifacts/editorial-review, never web/public.
- Private SQLite journal stores append-only candidate revisions, authenticated decisions and hash-chained events.
- Source imports retain full Issue; revisions create snapshots with parent/hash/author/reason, never UPDATE history.
- No public HTTP endpoints, runtime policy overrides, API calls or automatic policy installation.
- Fixed shared packages/shared/public-display.ts defines canonicalIssueHash/validIssue/projectPublicIssue as MVP-4.2.
- packages/shared/public-display-cli.cjs accepts bounded JSON stdin: {action:hash|validate|project, issue, policy?}.
- JSON response: {hash} / {valid:boolean} / {issue:PublicIssue|null}; never creates or changes approvals.

## Core CLI responsibilities (services/review except analysis.py/render.py)
- Explicit enrollment with actual human ID/name/roles/identity-attestation and interactive password; no seeded identities.
- Per-command getpass authentication; author/reviewer roles, salted slow hashes, bounded failures; no password flags/env/logs.
- Different authenticated author/reviewer required; enrollment authority/manual identity verification remains explicit.
- Read-only list/import existing real editions; snapshot lineage, hash, actor and reason recorded append-only.
- Per-story review covers EN/ZH original wording/facts/citation mapping/assets; per-link exact ID/publisher/URL legal basis.
- Pending/rejected/approved decisions require reasons, actual local evidence file hashes and documented HTTPS references.
- Final approval requires every story/link reviewed against exact revision hash, resolved risks, separate reviewer and reauthentication.
- No self-approval or invented identity/evidence; absent credentials, evidence or review fail closed.
- Export new bundle {issue, policy, revision/audit metadata} only from actual complete approval; refuse overwrite.
- Export never edits issues table or config/public-display.json; future release needs separate authorization.
- Changed revisions invalidate prior decisions by revision/hash; revocation is an append-only event.
- Integrity/auth/access/symlink/size guards required; errors never echo private content or credentials.

## Analysis/render interfaces (services/review/analysis.py and render.py)
- analyze(issue:dict)->list[dict]: id, storyId (or issue/source scope), severity, kind, reason, sourceIds.
- Flag exact/near copied EN/ZH passages, translated dependence, unsupported numbers/claims, missing citations and assets.
- Findings are heuristic prompts, not factual/legal verification; every story still needs documented human judgment.
- suggest(issue:dict)->dict keyed story ID with en/zh original editable templates/guidance using only cited records.
- No invented facts or automatic application; unresolved factual slots remain explicit placeholders.
- render_review(issue, findings, suggestions, output_dir): private bilingual report with citations/metadata and risk reasons.
- render_preview(public_issue_or_none, output_dir): separate EN/ZH digest/Sources/archive/home and RSS, no raw evidence.
- Unapproved preview receives None and renders withheld/no items; approved preview receives only shared gate PublicIssue.
- Artifacts private, escaped, offline/no embeds/scripts; never overwrite existing outputs.

## Verification
- Synthetic temporary actors/approvals only in tests; no actual enrollment/approval by agents.
- Nineteen source table hashes before/after match; public policy remains empty.
- Test auth/roles/self-approval/tamper/concurrency/revisions/evidence/exports and preview in browser.
- Run complete existing regression and remote CI; every Markdown file below 100 lines.
