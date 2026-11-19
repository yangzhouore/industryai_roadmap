"""Compile a reviewed private evidence batch into an exact Tracker manifest."""

import argparse
import json
from pathlib import Path
import sys

from services.review.security import ReviewError, load_private_json
from .evidence_snapshot import private_output, write_json
from .inventory import COMPANIES, REFERENCE_FIELDS, inventory
from .manifest import Catalog, KEY, TrackerError, parse_change
from .store import issue_bridge, timestamp


STAGE_FOR = {'research': 'research', 'prototype': 'prototype', 'pilot': 'pilot',
             'deployment': 'deployed', 'scaling': 'scaling', 'commercial': 'commercial'}
CLASSIFICATIONS = set(STAGE_FOR) | {'announcement', 'partnership', 'marketing', 'unresolved'}
FIELDS = {'projectKey', 'milestoneKey', 'name', 'claim', 'classification', 'stage',
          'companies', 'technologies', 'evidence', 'status', 'reason'}


def require(condition, reason):
    if not condition:
        raise TrackerError(reason)


def text(value, limit=500):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def validate_candidate(candidate, articles, company_articles, technology_ids):
    require(isinstance(candidate, dict) and FIELDS <= candidate.keys() <= FIELDS | {'binding', 'expectedRevision'},
            'Curation candidate fields are invalid.')
    require(all(isinstance(candidate[key], str) and KEY.fullmatch(candidate[key])
                for key in ('projectKey', 'milestoneKey')), 'Curation keys must be stable ASCII slugs.')
    require(all(text(candidate[key]) for key in ('name', 'claim', 'reason')), 'Curation requires a name, claim and reason.')
    classification, stage, status = candidate['classification'], candidate['stage'], candidate['status']
    require(isinstance(classification, str) and classification in CLASSIFICATIONS,
            'Curation classification is invalid.')
    require((status == 'supported' and classification in STAGE_FOR and STAGE_FOR[classification] == stage)
            or (status == 'unresolved' and stage is None),
            'Maturity requires an explicitly supported lifecycle classification.')
    revision = candidate.get('expectedRevision', 0)
    require(type(revision) is int and 0 <= revision < 2147483647, 'Curation revision must be a nonnegative integer.')

    companies = candidate['companies']
    require(isinstance(companies, list) and companies and all(
        isinstance(entry, dict) and entry.keys() == {'id', 'role'}
        and isinstance(entry['id'], str) and entry['id'] in COMPANIES and text(entry['role'], 160)
        for entry in companies), 'Curation company roles must use an inventory company.')
    require(len({entry['id'] for entry in companies}) == len(companies), 'Curation company roles are duplicated.')
    technologies = candidate['technologies']
    require(isinstance(technologies, list) and all(isinstance(value, str) and value in technology_ids
            for value in technologies) and len(set(technologies)) == len(technologies),
            'Curation technology IDs must be unique and registered.')

    evidence = candidate['evidence']
    require(isinstance(evidence, list) and evidence and all(
        isinstance(entry, dict) and entry.keys() == {'articleId', 'kind', 'quote'}
        and isinstance(entry['articleId'], str) and entry['articleId'] in articles
        and entry['kind'] in ('vendor', 'other') and text(entry['quote'])
        for entry in evidence), 'Curation requires original canonical articles and explicit source roles.')
    cited = {entry['articleId'] for entry in evidence}
    require(len(cited) == len(evidence), 'Curation article references are duplicated.')
    require(all(cited & company_articles[company['id']] for company in companies),
            'Each curated company must appear in its canonical evidence.')
    for entry in evidence:
        record = articles[entry['articleId']]
        require(any(entry['quote'] in record[field] for field in ('title', 'excerpt')),
                'Curation quote is absent from its exact stored article.')
    if 'binding' in candidate:
        binding = candidate['binding']
        require(isinstance(binding, dict) and binding.keys() == {'issueId', 'storyId'}
                and all(text(value, 240) for value in binding.values()), 'Curation edition binding is invalid.')


def exact_roles(edition, story, evidence, articles):
    sources = {source['id']: source for source in edition['content']['sources']}
    citations = {(link['rawArticleId'], link['sourceUrl']) for link in edition['bindings']
                 if link['storyId'] == story['id']}
    roles = {}
    for item in evidence:
        article = articles[item['articleId']]
        exact = [source_id for source_id in story['sourceIds'] if (
            (article['id'], article['url']) in citations
            and sources[source_id]['url'] == article['url']
            and sources[source_id]['name'] == article['publisher']
            and sources[source_id]['timezone'] == article['sourceTimezone']
            and timestamp(sources[source_id]['publishedAt']) == timestamp(article['publishedAt'])
            and timestamp(sources[source_id]['eventAt']) == timestamp(article['eventAt'])
        )]
        if len(exact) != 1 or exact[0] in roles:
            return None
        roles[exact[0]] = item['kind']
    return roles if roles.keys() == set(story['sourceIds']) else None


def compile_binding(row, editions, articles, hashes, catalog):
    if row['status'] == 'unresolved':
        return 'unresolved', None
    if 'binding' not in row:
        return 'raw-only', None
    key = row['binding']
    edition = editions.get(key['issueId'])
    if not edition:
        return 'missing-edition', None
    if edition['id'] not in hashes:
        content = edition['content']
        valid = (content.get('id') == edition['id'] and content.get('slug') == edition['slug']
                 and content.get('synthetic') is False and issue_bridge('validate', content).get('valid'))
        hashes[edition['id']] = issue_bridge('hash', content).get('hash') if valid else None
    digest = hashes[edition['id']]
    if not digest:
        return 'invalid-edition', None
    story = next((story for story in edition['content']['stories'] if story['id'] == key['storyId']), None)
    if not story:
        return 'missing-story', None
    if story['maturity'] != row['stage']:
        return 'stage-conflict', None
    roles = exact_roles(edition, story, row['evidence'], articles)
    if roles is None:
        return 'citation-conflict', None
    if not row['technologies']:
        return 'missing-technology', None
    change = {'projectKey': row['projectKey'], 'milestoneKey': row['milestoneKey'],
              'expectedRevision': row.get('expectedRevision', 0),
              'issueId': edition['id'], 'issueHash': digest, 'storyId': story['id'],
              'companies': sorted(company['id'] for company in row['companies']),
              'technologies': sorted(row['technologies']), 'sourceRoles': roles}
    parse_change(change, catalog)
    return 'eligible', change


def coverage_for(index, records):
    eligible = [row for row in records if row['bindingStatus'] == 'eligible']

    def counts(rows):
        supported = [row for row in rows if row['status'] == 'supported']
        return {'reviewedCandidates': len(rows), 'supportedProjects': len({row['projectKey'] for row in supported}),
                'supportedMilestones': len(supported), 'unresolved': len(rows) - len(supported),
                'vendorReportedDeployments': sum(row['classification'] == 'deployment'
                    and all(item['kind'] == 'vendor' for item in row['evidence']) for row in supported),
                'importEligibleMilestones': sum(row['bindingStatus'] == 'eligible' for row in rows)}

    return {'canonicalArticles': index['articleCount'], 'publishedEditions': index['editionCount'],
            **counts(records), 'importEligibleProjects': len({row['projectKey'] for row in eligible}),
            'independentlyVerifiedMilestones': 0,
            'byCompany': {company: {**data['counts'], **counts([
                row for row in records if any(item['id'] == company for item in row['companies'])
            ])} for company, data in index['companies'].items()}}


def prepare(data, curation):
    require(isinstance(data, dict) and type(data.get('version')) is int and data['version'] == 1
            and isinstance(data.get('articles'), list) and isinstance(data.get('editions'), list), 'Invalid evidence snapshot.')
    require(isinstance(curation, dict) and curation.keys() == {'version', 'candidates'}
            and type(curation['version']) is int and curation['version'] == 1 and isinstance(curation['candidates'], list),
            'Invalid private curation batch.')
    articles = {article['id']: article for article in data['articles']}
    editions = {edition['id']: edition for edition in data['editions']}
    require(len(articles) == len(data['articles']) == len({article['url'] for article in articles.values()})
            and len(editions) == len(data['editions']), 'Canonical evidence identifiers must be unique.')
    index = inventory(data['articles'], data['editions'])
    catalog = Catalog.load()
    company_articles = {company: {article['id'] for article in entry['articles']}
                        for company, entry in index['companies'].items()}
    technology_ids = {entry.id for entry in catalog.technologies}
    seen_keys, seen_evidence = set(), set()
    hashes, records, changes = {}, [], []
    for row in curation['candidates']:
        validate_candidate(row, articles, company_articles, technology_ids)
        key = (row['projectKey'], row['milestoneKey'])
        require(key not in seen_keys, 'Duplicate curation project and milestone key.')
        seen_keys.add(key)
        fact = (row['projectKey'], row['stage'], frozenset(e['articleId'] for e in row['evidence']))
        if row['status'] == 'supported':
            require(fact not in seen_evidence, 'Duplicate canonical evidence for a project stage.')
            seen_evidence.add(fact)
        binding_status, change = compile_binding(row, editions, articles, hashes, catalog)
        if change:
            changes.append(change)
        record = {**row, 'bindingStatus': binding_status, 'references': [
            {key: articles[item['articleId']][key] for key in REFERENCE_FIELDS} for item in row['evidence']
        ]}
        if row['status'] == 'supported' and binding_status not in ('eligible', 'raw-only'):
            record.update(status='unresolved', proposedStage=row['stage'], stage=None)
        records.append(record)
    records.sort(key=lambda row: (row['projectKey'], row['milestoneKey']))
    changes.sort(key=lambda row: (row['projectKey'], row['milestoneKey']))
    require(len(changes) <= 100, 'A Tracker import batch may contain at most 100 changes.')
    return {'inventory': index, 'dataset': {'version': 1, 'candidates': records},
            'manifest': {'version': 1, 'changes': changes}, 'coverage': coverage_for(index, records)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--curation', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(load_private_json(args.snapshot), load_private_json(args.curation))
        private = {'inventory.json': result['inventory'], 'dataset.json': result['dataset'],
                   'coverage.json': result['coverage']}
        if result['manifest']['changes']:
            private['tracker-import.json'] = result['manifest']
        paths = {name: private_output(args.output_dir / name) for name in private}
        for name, value in private.items():
            write_json(paths[name], value)
        coverage = result['coverage']
        print(f"Compiled {coverage['supportedMilestones']} supported, {coverage['unresolved']} unresolved, "
              f"and {coverage['importEligibleMilestones']} import-eligible private milestones.")
        return 0
    except (TrackerError, ReviewError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (KeyError, TypeError, ValueError, OSError):
        print('Private evidence batch failed. Source details were withheld.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
