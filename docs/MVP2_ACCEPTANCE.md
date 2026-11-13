# MVP-2 execution - historical record (2026-11-13)

This records the initial authorized MVP-2 test, not the current database/model state.
MVP-3 superseded it: 140 real articles, three bilingual publications (November 6, 9 and 13),
and append-only preservation of the previous November 13 edition and review.
Current routing: `gpt-6-luna` classification; `gpt-6.1-terra` generation/independent review.
See [MVP-3 report](MVP3_BACKFILL_REPORT.md). Unattended paid publication remains disabled.

## Actual live collection
At MVP-2 acceptance, PostgreSQL contained 112 real feed articles from six distinct publishers.
The stored counts below describe that historical collection snapshot.
Metadata includes canonical URL, original title, publisher, publication time, fetch time,
bounded feed evidence, policy evidence, content hash and request audit.

| Publisher | Stored | Working feed |
| --- | ---: | --- |
| Siemens Simcenter | 10 | https://blogs.sw.siemens.com/simcenter/feed/ |
| NVIDIA Robotics Newsroom | 20 | https://nvidianews.nvidia.com/cats/robotics.xml |
| AWS for Industries | 10 | https://aws.amazon.com/blogs/industries/feed/ |
| MIT News Robotics | 50 | https://news.mit.edu/topic/mitrobotics-rss.xml |
| Schneider Electric Blog | 12 | https://blog.se.com/feed/ |
| Microsoft Cloud Blog | 10 | https://www.microsoft.com/en-us/microsoft-cloud/blog/feed/ |

Replay: six successful sources, zero inserted duplicates; four HTTP304 responses.
Collection is local noncommercial metadata research; no unrestricted republication license asserted.
Raw candidates are not all classified industrial-AI news; editorial selection is a separate stage.
Unavailable/restricted sources and reasons are recorded in config/sources.yaml.

## Initial live publication (now archived)
- Authorized manual test completed: one real bilingual November 13 digest was published locally.
- MVP-3 replaced the public edition; the original content and review are preserved in revision history.
- One NVIDIA source article dated 2026-10-21T10:20:00Z; edition date is 2026-11-13.
- Model: gpt-4.1-mini-2025-04-14. Four requests total, including a rejected initial draft.
- Total measured input6099/output2864 tokens; estimated USD0.007022 at published standard rates.
- Classification reused after rejection; exact quote indexing computed deterministically before independent review.
- English/Chinese pages, source notebook, archive, search and original publisher HTTP200 verified.
- Full response/usage/review reports remain in ignored artifacts/initial-live.
- Credential retained in ignored .env.local, never printed or committed.
- Daily workflow prepared; unattended paid runs require separate UNATTENDED_PAID_APPROVED approval.

## MVP-2 verification (historical)
- Normal EN/ZH homepage, archive, search and RSS return200 with no synthetic sources.
- Old synthetic digest routes return404 in normal database mode.
- Frontend build, typecheck, lint and nine reader regressions passed.
- 72 Python regressions passed with PostgreSQL enabled, including 15 live-provider adapter tests.
- Classification/generation/independent fact-check uses three bounded API requests and at most30 candidates.
- Failed-review drafts remain private; public validation requires a matching process-verified review receipt.
- Explicit demo-mode browser regression:105 checks passed (not real-content acceptance).
- Live collection and replay executed against PostgreSQL, not mocked HTTP.
- Live editorial, independent review, translation and real-content route acceptance passed.

## Daily operation (superseded by MVP-4)
The old MVP-2 live dry-run collected and could incur editorial costs; that behavior has been replaced.
`python -m services.pipeline.live --dry-run` now delegates to MVP-4 read-only planning with no network or paid calls.
See [MVP-4 operations](MVP4_OPERATIONS.md) for daily scheduling, authorization, budget and resume.
`.github/workflows/live.yml` is opt-in via LIVE_NEWS_ENABLED and uses secret environment values.
No public deployment or scheduled paid service has been activated.
