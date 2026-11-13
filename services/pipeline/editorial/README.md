# Editorial worker

Install `python -m pip install -r services/pipeline/editorial/requirements.txt`.
Run `python -m unittest services.pipeline.editorial.test_editorial services.pipeline.editorial.test_live -v`.

- `prepare_issue(issue, provider=None)` copies input, validates provider output,
  ranks with an auditable score trace and returns an unvalidated draft.
- `validate_issue(issue, review=None)` returns errors; an empty list permits the publisher's
  separate atomic validation/publication transition.
- `score_story(story, weights=None)` exposes version, weights, dimensions and score.
- Missing authority/corroboration/attention evidence scores zero.
- `MockProvider` copies supplied bilingual content; no network or credentials.
- Production issue headings, introductions, story titles and summaries require
  cited excerpts or the defined neutral issue heading/introduction. Analysis and
  limitations must match cited text or standard conservative notes defined in
  `verification` unless a valid separate review artifact is supplied.
- Synthetic issues require every source and story to be synthetic. Synthetic
  URLs use reserved `example.org/fixtures/` and summaries remain grounded.
- Date, citation, numeric, acronym, Chinese text and diversity gates are enforced.

## Limits

Validation proves consistency with supplied evidence, not external truth.
Source approval and evidence authenticity remain collection/editorial duties.
Entity checks compare retained acronyms; translated names need human review.
The real Responses provider and three-pass pipeline are documented in
[LIVE.md](LIVE.md). Mocked transport tests make no paid API calls.
