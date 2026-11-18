# Industrial AI Intelligence Tracker

The Tracker adds Company, Technology, and Deployment directories at `/en/tracker`
and `/zh/tracker`. Search both languages by title, topic, organization, stage, or publisher.
The timeline uses reported event dates first and falls back to the earliest publication date
when event dates are missing or conflict. Each original citation keeps its own dates.

## Local fixture walkthrough

```powershell
npm.cmd ci
$env:DATA_MODE = 'fixture'
npm.cmd run dev
```

Open `http://127.0.0.1:3000/en/tracker` or switch to Chinese. The demo projects
reuse the labeled synthetic digest evidence. Company coverage includes Siemens, NVIDIA,
ABB and Schneider Electric. Demo project activity is attached only to demo companies.

## Private PostgreSQL workflow

Use a disposable database or a reviewed copy of the existing news database for evaluation.
Set `DATABASE_URL` in the private process environment. The migration only creates tracker
tables, indexes, and triggers. The web reader requires SELECT on issues, tracker milestones,
revisions, evidence, and the two revision association tables.

```powershell
npm.cmd run db:generate
npm.cmd run db:migrate
python -m services.tracker --list-editions
python -m services.tracker --list-stories '<published edition ID>'
```

Prepare a private version 1 JSON manifest using exact IDs and the canonical hash from the
list command. This example is a template. Replace the angle-bracketed values with reviewed input.

```json
{
  "version": 1,
  "changes": [{
    "projectKey": "project-curation-key",
    "milestoneKey": "pilot-curation-key",
    "expectedRevision": 0,
    "issueId": "<published edition ID>",
    "issueHash": "<canonical SHA-256>",
    "storyId": "<story ID>",
    "companies": ["Siemens"],
    "technologies": ["Digital Twins"],
    "sourceRoles": {"<story source ID>": "vendor"}
  }]
}
```

```powershell
python -m services.tracker --input '<private manifest path>'
python -m services.tracker --milestone-history '<milestone ID from import>'
```

- Reuse stable project and milestone keys for updates. Set `expectedRevision` to the
  last revision and provide the full replacement mapping. Exact replays make no new revision.
- To withdraw, submit the same keys and current `expectedRevision` with `"withdraw": true`.
  A withdrawal retains history. The CLI checks exact canonical source URL, publisher,
  publication and event dates, and source timezone against normalized citations.
- Resolve company and technology aliases with the checked-in bilingual catalog. Keep unknown
  or ambiguous aliases out of imports. Use a new milestone key only for a distinct event.
- Assign `vendor`, `independent`, or `other` based on evidence review. Omitted roles
  default to `other`. Only explicitly classified corroboration from at least two distinct
  publishers and hosts earns the independently verified label.

## Publication boundary

Real project text is derived from the current published, validated, cleared digest story.
The tracker requires the exact edition hash and all matching source clearances under the
existing gate. Stale or withdrawn heads remain private. Original links and attribution
come from the approved projection. Raw excerpts, manifests, private review records,
and unsupported company and technology associations stay out of public responses.

The checked-in policy has zero real approvals. The tracker shows the company and technology
directories and an honest empty state until eligible real milestones have clearance.
Tracker imports affect tracker tables only. They do not start background jobs or change approvals.
