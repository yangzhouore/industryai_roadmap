# Private Tracker candidate extraction

The extraction CLI uses the canonical snapshot from [private evidence batches](TRACKER_EVIDENCE.md).
Its default predictions use an offline text baseline. It also prepares structured OpenAI
Responses request bodies and consumes saved Responses. All three operations run locally
without network access, API credentials, database writes, or publication.

## Offline extraction and evaluation

```powershell
python -m services.tracker.extract_candidates candidates --snapshot artifacts/tracker-private/snapshot.json --output artifacts/tracker-private/candidates.json
python -m services.tracker.extract_candidates evaluate --snapshot artifacts/tracker-private/snapshot.json --gold artifacts/tracker-private/curation.json --output artifacts/tracker-private/evaluation.json
python -m unittest discover -s tests -p 'test_tracker_extraction*.py' -v
```

Evaluation selects the reviewed article IDs and scores source-only predictions against
the reference curation. It reports exact stage and kind agreement, supported precision
and recall, unresolved recall, and canonical evidence and date preservation. A saved model
response can be evaluated with `--responses`. The offline metrics describe the heuristic;
model performance requires a separately authorized model run.

The local eight-case comparison matched 7 of 8 stages and 5 of 8 categories. It
identified 2 of 3 supported milestones and left all 5 unresolved cases unresolved,
with all 8 canonical references and dates intact. These figures describe this small
reviewed sample. The committed synthetic fixture keeps coverage reproducible in CI.

## OpenAI request preparation and replay

```powershell
python -m services.tracker.extract_candidates requests --snapshot artifacts/tracker-private/snapshot.json --model gpt-6.1-terra --output artifacts/tracker-private/requests.json
python -m services.tracker.extract_candidates candidates --snapshot artifacts/tracker-private/snapshot.json --responses artifacts/tracker-private/responses.json --output artifacts/tracker-private/model-candidates.json
```

Request and candidate commands accept repeated `--article-id` arguments to restrict scope.
Each request contains one article ID, its stored title and excerpt, and the entity catalog.
Schema-constrained outputs cite the same article and quote stored text verbatim. The request
uses `store: false` and omits canonical URLs and date fields. Request and response files still
contain private evidence. Sending a request requires separate paid-call and source-use authorization.

The input envelope is `{"version":1,"responses":[{"articleId":"…","response":{…}}]}`.
Save the completed Responses API object as `response`. The validator refuses incomplete
or refused responses and checks source scope, entity mentions, quoted text, lifecycle cues,
and duplicate evidence. Publication and event dates come only from the canonical snapshot.
Announcements, partnerships, marketing, and uncertain lifecycle cues cannot establish a
production stage.

The request file includes a Standard API cost estimate for the selected corpus. The Terra
defaults are USD 1 per million input tokens and USD 5 per million output tokens. The Luna
defaults are USD 0.10 and USD 0.50. For a different model, supply `--input-rate` and
`--output-rate` together. Calculations use serialized UTF-8 size as an input token proxy
and the full 1,200-token output allowance per request. The file includes a padded input
scenario. Neither scenario measures usage or guarantees the provider's final bill.
[OpenAI API pricing](https://developers.openai.com/api/docs/pricing)

## Human curation

All candidates carry pending review status. Reviewers inspect the original references,
company and technology roles, reported stage, and separate dates. Keep unsupported or
conflicting details unresolved. Drafts are private artifacts and the Tracker importer
rejects their schema. A human reviewer must separately prepare the existing curation JSON
and use the MVP-5.2 compiler and isolated import path. Public clearance remains separate.
