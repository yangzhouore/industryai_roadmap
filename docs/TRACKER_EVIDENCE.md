# Private Tracker evidence batches

See [private extraction](TRACKER_EXTRACTION.md) for offline candidate suggestions and model response replay.

This workflow uses existing PostgreSQL records and performs no collection or provider
calls. The inventory matches exact company names and known aliases in Siemens, NVIDIA,
ABB, Schneider Electric, Microsoft, and AWS coverage. An occurrence in a title, excerpt,
or publisher field establishes an inventory match. Project roles and milestone maturity
require review of the stored evidence.

## Snapshot and compile

Use the configured PostgreSQL reader for the following export. The exporter verifies
a read-only repeatable-read transaction and captures canonical articles, current
published editions, and exact normalized citations into a protected, ignored directory.

```powershell
python -m services.tracker.evidence_snapshot --output artifacts/tracker-private/snapshot.json
python -m services.tracker.evidence_batch --snapshot artifacts/tracker-private/snapshot.json --curation artifacts/tracker-private/curation.json --output-dir artifacts/tracker-private/batch
```

The compiler reads a private JSON object with `version: 1` and a `candidates` array.
Each candidate uses these fields:

| Fields | Meaning |
|---|---|
| `projectKey`, `milestoneKey` | Stable lowercase keys. Reuse them for the same event. |
| `name`, `claim`, `reason` | Private reviewed wording and supporting evidence limits. |
| `companies`, `technologies` | Company `{id, role}` entries and registered technology IDs. |
| `evidence` | Entries with `articleId`, `kind` (`vendor` or `other`), and an exact stored `quote`. |
| `classification`, `stage`, `status` | Supported lifecycle or unresolved evidence. Unresolved entries use a null stage. |
| `binding` | Optional exact `{issueId, storyId}` for an existing published story. |
| `expectedRevision` | Optional current milestone revision for a correction. Defaults to zero for the first import. |

Lifecycle classifications are `research`, `prototype`, `pilot`, `deployment`, `scaling`,
and `commercial`. Deployment maps to the `deployed` stage. Announcements,
partnerships, and marketing stay unresolved. A conflicting edition binding keeps the
proposed stage for private review and excludes the milestone from the manifest.

The output includes `inventory.json`, `dataset.json`, and `coverage.json`.
`tracker-import.json` is produced when at least one candidate matches the exact
published story, lifecycle stage, and complete set of canonical citations and dates.
The private dataset retains original evidence references and null event dates.

## Isolated validation

Point `DATABASE_URL` at a verified disposable clone that contains the exact original
article and edition records, with the Tracker schema applied. Run the existing importer
twice and compare the original-table fingerprints and Tracker revision counts.

```powershell
python -m services.tracker --input artifacts/tracker-private/batch/tracker-import.json
python -m services.tracker --milestone-history '<milestone ID from isolated import>'
```

The importer retains prior revisions when correcting or withdrawing a milestone.
Use its existing withdrawal manifest format. Private curation artifacts stay outside
Git and web routes. Public display still requires the existing exact edition and
source-use clearance, and this workflow does not change review approvals.
