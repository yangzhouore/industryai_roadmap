# Real editorial adapter

`from services.pipeline.editorial.live import generate_real_issue`

`draft, review = generate_real_issue(articles, issue_date, provider=None, draft_sink=None, *, strict_day=False, daily_window=False, excluded_event_keys=())`

## Input and credentials

- Input is 1–30 real collected article dictionaries; daily mode permits up to 300 in classification batches of 30.
- Required fields: sourceId, name, url, title, excerpt (string), publishedAt,
  timezone, synthetic=false. Optional: eventAt, language (`en` default or `zh`).
- URLs must be canonical public HTTPS destinations; excerpts max 3400 characters.
- Collection must already have approved source policies and fetched the evidence.
- Provider requires `OPENAI_API_KEY`. `OPENAI_CLASSIFY_MODEL` defaults to
  `gpt-6-luna`; `OPENAI_MODEL` and `OPENAI_VERIFY_MODEL` default to `gpt-6.1-terra`.
- `OPENAI_REASONING_EFFORT` defaults to `low`; `none` is supported, `minimal` is
  rejected for these models. There is no model substitution after API failure.
- Missing credentials/configuration fail closed. No mock or manual prose fallback.

## Three passes

1. Luna extracts entities, assigns event clusters and classifies category/maturity,
   company and evidence-backed score dimensions. Trace weights are explicit.
2. Generate bilingual source translations, titles, summaries, analysis and limits.
   Every complete field maps to original Unicode quote start/end offsets.
3. Independently check every claim, classification and source translation for
   entailment, bilingual meaning, entities, uncertainty, quantities and units.

Unverifiable source authority/corroboration/attention score zero. At most three
company/category-distinct leads are selected; remaining selected stories are bites.
No issue is generated if classification yields no supported industrial candidates.
Duplicate event keys, known syndication groups and highly similar original titles
are reduced to one story. An organization alone never establishes an event group.
Outputs use the existing public Issue schema, state=draft and validated=false.
`draft_sink(deepcopy(draft))` runs after public schema validation and before fact
review, allowing failed/unverified editions to remain private drafts.
With `strict_day=True`, all sources must fall on the exact Europe/Berlin calendar
day (including DST); issue ID is `issue-<date>-historical`. Review binds this policy.

With `daily_window=True`, issue date is the publication date and source evidence
must be from the previous complete Berlin day, including 23/25-hour DST days.
Known event times outside that window are excluded; missing event time stays unknown.
The source window is bound to review. These policies cannot be combined.
Daily classification covers every candidate in batches, globally selects stories,
then generates/reviews once; batch response IDs and membership are sealed in review.
`excluded_event_keys` prevents previously published normalized event identities.
Trace includes selected candidates and classifier, event, story-limit or budget rejections.

## Review and publication

- Call `validate_issue(issue, review)` or `validate_review(issue, review)`.
- The review binds exact issue content (excluding state/validated) and immutable
  original evidence hashes. Claim/translation/classification coverage is complete.
- Exact pointers, numeric and acronym parity are checked locally, even when the
  model says a claim is supported. Mere evidenceStatus=verified is insufficient.
- A process-local HMAC seal rejects modified or fabricated review JSON. Its random
  key exists only in memory and is never returned, persisted or logged.
- Publish with `Store.publish(draft, review=review)` in that same process. Persist
  review JSON as audit evidence; a later process must run verification again.
- No secret files or keys are created. Receipt JSON contains provider response IDs,
  model names, scoring traces, claims, evidence, hashes and check results only.

## HTTP adapter and limits

`OpenAIProvider(api_key=None, model=None, verification_model=None, ...)` uses only
`https://api.openai.com/v1/responses`; redirects and inherited proxies are disabled.
Requests use strict `text.format` JSON Schema, `store=false`, bounded input/output,
timeouts and at most two retries. Refusals, incomplete responses, errors, malformed
JSON/schema, missing coverage and failed review all prevent publication. API error
bodies and secrets are never included in exceptions.

Inject `before_request(context)` to reserve cost before every HTTP attempt,
including retries. Context has stage/model/maxOutputTokens/attempt/request without
credentials. `after_response(record)` receives model/responseId/status/raw usage
and reasoningTokens even for incomplete responses. Unknown usage is None: keep
the worst-case reservation. Callbacks may raise to stop further paid requests.

Contract checked against official documentation:
- [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Responses creation](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [GPT-6.1 Terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra)

## Verification status and limits

Run `python -m unittest services.pipeline.editorial.test_live services.pipeline.editorial.test_mvp3 -v` for mocked HTTP,
source-backed draft, review, rollback/publication, credential and tamper tests.
These tests do not publish news and do not contact the OpenAI API. They exercise a
short NIST source snapshot, not fabricated external project claims.

This module's tests use mocked HTTP; the lead records actual pilot access, output
quality, cost and multilingual semantic checks separately. Fact-checking establishes
evidence consistency rather than
independent external truth. Reviewers can still make semantic mistakes; attribution
and limitations must remain visible, and uncertain claims must be rejected.
