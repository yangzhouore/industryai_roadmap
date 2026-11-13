# Feed collection

`npm run pipeline:collect` reads the checked-in synthetic RSS fixture offline.
Replay inserts zero additional articles. Candidate clusters and run audits persist.
Collection never publishes editions; reviewed bilingual inputs go through the publication CLI.

Live collection requires an explicit registry:
`python -m services.pipeline.ingest --mode live --registry config/sources.yaml`.
The registry uses JSON-compatible YAML with a `sources` array; six reviewed feeds are enabled.
Each active source needs ID, name, homepage, feed_url, allowed_hosts, synthetic=false,
and explicit feed_permitted, excerpt_permitted and policy_reviewed=true declarations.
Real sources also require policy_evidence URLs and policy_checked_at.
Only set these after reviewing the actual feed policy. HTTPS/DNS/robots checks still apply.

Use `--database` for SQLite paths or PostgreSQL URLs. PostgreSQL requires migrations first.
Failed sources roll back individually; successful sources survive partial feed failures.
Inspect `pipeline_runs` for source counts, failures and request audits.

## MVP-2 ingestion baseline (historical)

| Publisher | Feed | Stored articles |
| --- | --- | ---: |
| Siemens Simcenter | https://blogs.sw.siemens.com/simcenter/feed/ | 10 |
| NVIDIA Robotics | https://nvidianews.nvidia.com/cats/robotics.xml | 20 |
| AWS Industries | https://aws.amazon.com/blogs/industries/feed/ | 10 |
| MIT Robotics | https://news.mit.edu/topic/mitrobotics-rss.xml | 50 |
| Schneider Electric | https://blog.se.com/feed/ | 12 |
| Microsoft Cloud | https://www.microsoft.com/en-us/microsoft-cloud/blog/feed/ | 10 |

MVP-3 added 28 records, bringing the current total to 140 real articles.
The table above records the earlier MVP-2 baseline, not current per-source totals.
See `docs/MVP3_BACKFILL_REPORT.md` for coverage, publication and revision evidence.
PostgreSQL run `b3e2f95bbf2e4f1a9b20602dec86ce7a` inserted 112 real articles.
Replay `7ae35a09862f4190a94d00a0983951e7` inserted zero; four feeds returned HTTP304.
All six robots checks succeeded. Both runs recorded success and no source failures.
That baseline check found 112 candidate clusters and 112 records with originalTitle,
fetchedAt and policyEvidence. Source publication dates and event dates stay separate.
Feed language, original date string, authors and source attribution are retained.

Use `--database postgresql://digest@127.0.0.1:55432/digest` for the isolated local DB.
On portable Windows, add `artifacts/postgres/package/native/bin` to PATH and set
`PSYCOPG_IMPL=python` before running the live command above.

## Policy scope and skipped candidates

Enabled feeds are limited to local non-commercial metadata research. Descriptions
are limited to 400 characters; article bodies, content:encoded and images are discarded.
Official endpoint availability is not an unrestricted republication license.
Registry records evidence URLs, review date and redistribution_permitted=false.
NVIDIA's official RSS terms restrict use to non-commercial informational purposes:
https://www.nvidia.com/en-us/about-nvidia/rss/.
MIT's RSS syndication and attribution policy: https://news.mit.edu/terms-of-use.

arXiv robots.txt returned404 and Rockwell robots.txt returned403; neither was bypassed.
Siemens root feed returned200 with zero entries; Simcenter provides actual articles.
The Robot Report returned15 items, but persistent reuse remains disabled pending review.
Old Microsoft manufacturing feed returned404 after redirect; Cloud feed works.
All disabled candidates retain dated failure/review reasons in the registry.

Verification: `python -m unittest discover -s tests -p 'test_ingest*.py' -v`
and `python -m unittest services.pipeline.collectors.test_collection -v`: 27 passed.

## Historical backfill

`python -m services.pipeline.ingest --mode backfill --registry config/sources.yaml --database postgresql://digest@127.0.0.1:55432/digest --start 2026-11-01 --end 2026-11-13 --timezone Europe/Berlin`

The date range is inclusive and follows the source publication timestamp converted
to the requested IANA timezone. Event dates remain separate; unknown events stay null.
`archive_feeds` lists verified publisher RSS endpoints on already approved hosts.
No date filter is claimed when a publisher ignores query parameters.
Each endpoint is audited in `pipeline_runs` at stage `collection_backfill`.
Raw articles are inserted by canonical URL without overwriting original evidence.

Verified November feeds include Schneider's `/2026/11/feed/`, NVIDIA's robotics
category/tag, Omniverse/Cosmos/Isaac tag feeds and its all-news RSS. Siemens page2
works but contains only October articles; AWS date queries return the same feed.
Schneider query-parameter archives are disallowed by robots; its permitted month
path returned RSS. Additional day/month page feeds returned404. arXiv's official
API host robots disallows collection, so that API was not queried.

First backfill `a86d65dc582e4a1cb817a184203a2d71` added27 articles: total112→139,
with the November1–13 Berlin publication-date set increasing27→54. A later feed
update added one new candidate; final totals are140 real raw candidates and55 in-window.
Stable replay `4eee6da680e64feea422c46ecc84593a` inserted0; duplicate canonical URLs0.
These counts include unranked candidates and do not imply industrial relevance.
November8 was recovered; November1 remains a coverage gap, not proof of no news.
See `historical_backfill_evidence.json` for verified endpoints, replay and daily counts.
`archive_discovery_evidence.json` records unavailable endpoints and policy limits.
Latest backfill checks:17 ingestion tests and14 collector tests passed (31 total).
