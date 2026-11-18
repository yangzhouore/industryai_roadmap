# Local editorial analysis and offline reports

## Scope
`services/review/analysis.py` and `render.py` perform no network requests, API calls or source-database writes.
They do not enroll users, authenticate decisions, grant rights or install public policy.
The authenticated review journal/CLI owns those workflow requirements under the frozen review contract.
A private standalone analysis/report is a machine prompt, not a journal import, decision or approval.

## Analysis
`analyze(issue)` returns deterministic finding IDs bound to the complete stored revision and finding details.
Each finding has storyId (or issue/source path scope), severity, kind, reason and sourceIds.
Checks cover issue title/introduction and story title/summary/analysis/limitation in both languages.
Exact/long common passages and near-match ratios flag possible copied wording.
Fuzzy matching samples at most 1,024 normalized characters per comparison and 128 pairs per issue; bounds raise prompts.
Close source-expression matches raise a separate translated-dependence prompt.
Numeric/unit mentions absent from same-language cited evidence raise unsupported-number prompts.
Missing citation IDs, low lexical claim overlap and retained asset/HTML keys also require review.
Every story receives a human fact-review prompt even when lexical checks identify no copying.
These are heuristics: they do not establish truth, independent wording, translation entailment or legal permission.
Translation, formatting, terminology and standard phrases can produce false positives or false negatives.

## Editable suggestions
`suggest(issue)` returns en/zh strings keyed by story ID; it never changes the issue.
Suggestions anchor the cited source ID, publisher, publication/event timestamp and original URL.
Original lede, analysis and limitation sentence templates contain explicit unresolved factual slots.
Names, deployment claims, metrics and outcomes must be filled only after checking actual cited evidence.
Source excerpts are not translated or lightly paraphrased into a proposed article.
Every suggestion is labeled machine-assisted, unreviewed and not a factual article or human approval.
No model/API provider is used; the authenticated author must create a new reasoned revision to apply changes.

## Private report
`render_review(issue, findings, suggestions, output_dir)` creates a new private `index.html` only.
The report includes full private evidence, bilingual fields side by side, citation IDs, source metadata,
risk reasons, editable suggestions and the complete stored snapshot for inspection.
Evidence and arbitrary metadata are escaped text; source URLs become links only when HTTPS without credentials.
No script, image, iframe, remote font or background resource is embedded.
A restrictive CSP disables scripts/resources/forms; no-referrer avoids sending a report URL on a clicked link.
The reader may deliberately open an outbound source link; it is not fetched automatically.

## Public projection preview
`render_preview(public_issue_or_none, output_dir)` consumes only the actual shared-gate result supplied by core.
The renderer adds strict field/type checks; it cannot independently authenticate the provenance of a Python dict.
Raw Issue objects with source excerpts or unknown nested fields are rejected before output creation.
None produces withheld home/digest/Sources/archive pages in EN/ZH, plus empty RSS feeds.
A PublicIssue produces only its projected editorial fields, metadata and links, with synthetic demo labels where applicable.
Files: index.html and en/zh index.html, digest.html, sources.html, archive.html, rss.xml (11 files).
All links between preview pages are local; no production domain or deployment is implied.
Preview never reads retained evidence, creates approvals or changes config/public-display.json.

## File safety and limits
Both renderers return outputDir plus generated relative files, and refuse an existing output directory.
Output paths reject traversal, symlink/reparse parents, web/public/build roots and repository metadata directories.
Within this repository, only ignored artifacts subdirectories are allowed; private external test/state paths are supported.
New directories/files use 0700/0600 on Unix and protected owner/SYSTEM/Administrators ACLs on Windows.
Inputs and reports are size-bounded; private strings are escaped and invalid public XML/control text is rejected.
Keep outputs under ignored private artifacts outside replaceable/public releases; do not commit evidence reports.
Concurrent hostile processes running as the same OS user are outside the local file-permission trust boundary.

## Focused verification
`python -m unittest services.review.test_analysis services.review.test_render -v`
Thirteen tests cover copied EN/ZH and issue prose, revision binding, metrics/citations/assets, placeholders,
HTML escaping, withheld previews, unknown-field leaks, nested aliases, no-overwrite and private path checks.
Local Windows result: 12 passed; one Unix symlink test skipped because Windows link privilege varies.
The symlink test remains enabled for Ubuntu CI; no genuine reviewer identity or approval is created in these tests.
Read-only baseline: ignored artifacts/mvp43/analysis-source-before.json, 19 tables/140 articles/three editions/one revision.
Compare all source-table hashes after integration; synthetic journal/approval fixtures belong only in isolated tests.

## Machine-only inspection of preserved editions
Read the November 6/9/13 editions through a read-only snapshot and rendered one private report per date.
Each also received the actual shared gate's None result and 11 withheld preview files; all public approvals remain empty.
November 13 raised copied/near-copied and translated-dependence prompts; the other dates still require human review.
No finding establishes infringement or factual error, and no machine suggestion was applied.
No Workbench identity, enrollment, journal import, decision, resolution or approval was created for these real records.
Evidence: ignored artifacts/mvp43/machine-analysis-report.json; all 19 source-table hashes matched before/after.
