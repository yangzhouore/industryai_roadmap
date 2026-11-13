# MVP-4 daily operations

## Schedule and publication day

The target is **07:00 Europe/Berlin**, with daylight saving handled by IANA timezone rules.
An edition dated D uses source publications from the complete Berlin day D-1.
Publication time, ingestion time and known event time remain distinct; unknown event dates stay unknown.
GitHub's workflow declares the Berlin timezone directly and retries the daily slot at 09:15.
Schedules can be delayed or dropped; a later tick reports missed dates rather than inventing editions.
[GitHub schedule semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Safe local inspection

```powershell
python -m services.pipeline.daily run --dry-run
python -m services.pipeline.daily tick --dry-run --resume
python -m services.pipeline.daily status
python -m services.pipeline.collectors.discovery
```

Dry-run reads stored evidence only: no collection, API requests, budget reservation or publication.
Status reports recent runs, missing scheduled dates, published IDs, source outcomes and monthly estimates.
First review/apply the additive automation migration in a controlled maintenance step; no reset or seed is needed.
The additive migration is applied to this local instance and verified in disposable schemas.
Fresh installations still need the reviewed migration; the scheduler never applies it automatically.
Initial configuration starts schedule auditing on November 14, 2026.

## Explicit activation remains pending

Unattended paid execution is disabled in `config/automation.json`.
A scheduled paid run requires both `unattendedPaidApproved=true` and process `UNATTENDED_PAID_APPROVED=true`.
GitHub additionally requires `LIVE_NEWS_ENABLED=true`; never set these without user authorization.
Manual paid execution requires an explicitly authorized `--allow-paid` run; `--resume` reuses durable stages.
The GitHub workflow's default manual dispatch is dry-run and receives no OpenAI key.
Do not dispatch paid runs, register/enable a task, push or deploy merely to inspect status.
Hosted GitHub runners need a reachable PostgreSQL service; a Windows loopback database is not reachable remotely.
November execution also requires the preserved local MVP-3 budget ledger for carryover reconciliation.

## Windows availability

`watch` runs only while its Python process and computer are running; sleep pauses it and shutdown stops it.
`services/pipeline/windows-task.ps1` exports a **disabled dry-run** Task Scheduler XML by default.
It polls every 15 minutes and at boot/logon; the CLI decides whether the Berlin slot is due.
The optional `-Register` creates a disabled task only; this milestone does not invoke it.
The template uses the current user's interactive token, stores no password and needs a logged-in session.
`WakeToRun` can request wake from sleep, subject to hardware and power policy; it cannot run while powered off.
`StartWhenAvailable` supports a delayed catch-up after availability returns; exact 07:00 is not guaranteed.
[Wake setting](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-waketorun-settingstype-element),
[missed-start behavior](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-startwhenavailable).
An authorized always-on hosted runner can run while Windows is asleep/off, once remote data access is configured.

## Budget, retries and preservation

The application ceiling is USD 2 per Berlin calendar month, not an account/provider billing limit.
Each attempt reserves estimated worst-case cost transactionally before network access.
Retries and failed/unknown responses remain counted; token usage settles estimates where available.
Interrupted requests retain reservations. Historical estimates are imported idempotently before new paid work.
Provider billing can differ; account-level settings are never changed.
[Luna rates](https://developers.openai.com/api/docs/models/gpt-6-luna) and
[Terra rates](https://developers.openai.com/api/docs/models/gpt-6.1-terra) underpin the Standard-rate estimates.
Resume uses PostgreSQL response/candidate caches and reconstructs a fresh process-verified review.
Publication and reviewed event claims commit atomically; incomplete bilingual or rejected output stays private.
Existing published editions are not replaced by daily drafts; prior versions/reviews remain append-only.
Each new daily edition also writes its exact content/review snapshot to immutable edition_revisions.
Inspect failed reasons and reservations before manually retrying; do not erase the ledger to regain budget.

## Discovery limits

The permitted archive probe still finds 55 unique candidates for November 1–13 and none for November 1.
This is bounded accessible-feed evidence, not proof that no industrial AI news existed.
Four unavailable/unapproved source candidates remain disabled; restrictions are not bypassed.
No historical re-ingestion or new article generation was performed during MVP-4 verification.
