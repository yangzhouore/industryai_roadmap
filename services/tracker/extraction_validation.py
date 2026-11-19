"""Validate untrusted extraction proposals against the canonical evidence snapshot."""

from collections import defaultdict
from functools import lru_cache
import json
import re
from urllib.parse import urlsplit

from .evidence_batch import CLASSIFICATIONS, STAGE_FOR, text
from .inventory import REFERENCE_FIELDS, inventory, mention_pattern, normalized_text
from .manifest import Catalog, STAGES, TrackerError, alias_key, identifier, opaque_id
from .store import timestamp


PROPOSAL_FIELDS = {'projectName', 'companyIds', 'technologyIds', 'kind', 'stage', 'evidence'}
MAX_PROPOSALS = 1000
MAX_QUOTES = 8
MIN_QUOTE = 8
EXTENT = 500

# Lifecycle cues describe supported assertions. Ordinary mentions of the word
# deployment, or a project that merely aims to deploy, do not clear this check.
CUES = {
    'research': (
        r'\b(?:researchers?\b.{0,95}\b(?:trained|built|used|tested|testing|studied|evaluated|developed|simulation)|'
        r'research (?:study|studies|on|into)|(?:conducted|presented)\b.{0,55}\bresearch|'
        r'experiments? (?:showed|demonstrated|found)|trained?\b.{0,50}\bsimulation)\b'
    ),
    'prototype': (r'\b(?:prototyped|(?:built|created|developed|tested|demonstrated|completed)\b.{0,60}'
                  r'\b(?:prototype|proof[- ]of[- ]concept)|prototype (?:is operating|was tested|worked))\b'),
    'pilot': (r'\b(?:piloted|triall?ed|(?:began|started|ran|running|conducted|completed)\b.{0,60}'
              r'\b(?:pilot|trial)|(?:pilot|trial) (?:is underway|began|started|concluded))\b'),
    'deployment': (
        r'\b(?:rolled out|went live|in (?:active |commercial )?production|'
        r'in (?:daily |routine )operation|operational since|installed and (?:operating|running)|'
        r'gave.{1,150}(?:staff|teams|engineers|geoscientists|operators).{1,170}(?:agent|software|system))\b'
    ),
    'scaling': (r'\b(?:scaled (?:up|out|[^,;.!?]{0,85}\b(?:to|across))|'
                r'expanded (?:to|across)|extended (?:the rollout|deployment))\b'),
    'commercial': r'\b(?:commercially available|commerciali[sz]ed|began selling|shipping to paying customers)\b',
    'announcement': r'\b(?:announc(?:e[ds]?|ing|ement[s]?)|unveil(?:s|ed|ing)?|introduc(?:e[ds]?|ing))\b',
    'partnership': r'\b(?:partnerships?|partnered|collaboration|joint initiative)\b',
    'marketing': r'\b(?:showcas(?:e[sd]?|ing)|promot(?:e[sd]?|ing|ional)|help(?:s|ing)?|can help|designed to|describes?)\b',
}
CUES = {kind: re.compile(pattern, re.IGNORECASE) for kind, pattern in CUES.items()}
NEGATION = re.compile(r"\b(?:no|not|never|without|neither|cannot|hasn['’]t|haven['’]t|"
                      r"didn['’]t|isn['’]t|wasn['’]t|weren['’]t|won['’]t)\b", re.IGNORECASE)
FUTURE = re.compile(r'\b(?:plan(?:s|ned|ning)?|aim(?:s|ed)?|propos(?:e[sd]?|al)|expects?|'
                    r'expected|intends?|intended|scheduled|will|would|could|might|may|can|pending|future|'
                    r'(?:is|remains) (?:the|a) (?:goal|target|objective))\b', re.IGNORECASE)
NONPRODUCTION = re.compile(r'\b(?:pilots?|prototype[s]?|simulat(?:ion|ed)|laboratory|labs?|'
                           r'test[ -]environment|proof[ -]of[ -]concept|(?:pre|non)[ -]?production|'
                           r'demos?|demonstrations?|staging)\b', re.IGNORECASE)
SENTENCE_END = re.compile(r'[.!?。！？](?=\s|$)|[。！？]')
CLAUSE_END = re.compile(r'[,;:.!?，；：。！？]|\b(?:while|whereas|but|however|and|or)\b', re.IGNORECASE)
METRIC_OR_DATE = re.compile(r'\d\s*(?:%|percent\b)|\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b', re.IGNORECASE)


def lifecycle_blocked(kind, quote):
    if kind not in STAGE_FOR:
        return False
    if NEGATION.search(quote) or FUTURE.search(quote):
        return True
    return kind in {'deployment', 'scaling', 'commercial'} and bool(NONPRODUCTION.search(quote))


def lifecycle_evidence(kind, quote):
    """Recognize explicit lexical cues for a proposed lifecycle interpretation."""
    if kind == 'unresolved':
        return True
    return isinstance(kind, str) and kind in CUES and bool(CUES[kind].search(quote)) and not lifecycle_blocked(kind, quote)


def cited_passages(article, quote):
    """Recover complete surrounding sentences, including omitted qualifiers."""
    for container in (article['title'], article['excerpt']):
        ends = [0, *(mark.end() for mark in SENTENCE_END.finditer(container)), len(container)]
        for occurrence in re.finditer(re.escape(quote), container):
            start, end = occurrence.span()
            left = max(boundary for boundary in ends if boundary <= start)
            right = min(boundary for boundary in ends if boundary >= end)
            yield container[left:right]


def evidence_classification(kind, stage, quotes, passages, name):
    if stage != STAGE_FOR.get(kind):
        return 'unresolved', None
    if kind in STAGE_FOR and (
        not any(lifecycle_evidence(kind, clause) for quote in quotes
                for clause in split_for_project(quote, name) if name is None or name.search(clause))
        or any(lifecycle_blocked(kind, passage) for passage in passages)
    ):
        return 'unresolved', None
    if kind in CUES and kind not in STAGE_FOR and not any(lifecycle_evidence(kind, quote) for quote in quotes):
        return 'unresolved', None
    return kind, stage


def intact_snapshot(snapshot):
    if (not isinstance(snapshot, dict) or type(snapshot.get('version')) is not int or snapshot['version'] != 1
            or not isinstance(snapshot.get('articles'), list) or not isinstance(snapshot.get('editions'), list)):
        raise TrackerError('Extraction validation requires a version 1 canonical snapshot.')
    articles, urls = {}, set()
    try:
        for article in snapshot['articles']:
            if not isinstance(article, dict):
                raise ValueError
            url = urlsplit(article['url'])
            if (not identifier(article['id']) or article['id'] in articles or article['url'] in urls
                    or url.scheme != 'https' or not url.hostname or url.username or url.password
                    or not all(isinstance(article[key], str) for key in (*REFERENCE_FIELDS, 'title', 'excerpt')
                               if key != 'eventAt')
                    or timestamp(article['publishedAt']) is None):
                raise ValueError
            timestamp(article['eventAt'])
            articles[article['id']] = article
            urls.add(article['url'])
        company_index = inventory(snapshot['articles'], snapshot['editions'])['companies']
    except (TypeError, KeyError, ValueError, AttributeError):
        raise TrackerError('Canonical snapshot references are invalid or duplicated.') from None
    companies = {
        company: {row['id'] for row in entry['articles'] if row['matches']['title'] or row['matches']['excerpt']}
        for company, entry in company_index.items()
    }
    return articles, companies


@lru_cache(maxsize=1)
def entity_catalog():
    catalog = Catalog.load()
    patterns = {entry.id: [mention_pattern(alias) for alias in entry.aliases] for entry in catalog.technologies}
    return catalog, patterns


def entity_ids(values, aliases):
    if not isinstance(values, list) or len(values) > 20 or not all(text(value, 120) for value in values):
        raise ValueError
    entities = {aliases.get(alias_key(value)) for value in values}
    if None in entities:
        raise ValueError
    return sorted(entities)


def split_for_project(quote, name):
    if name is None:
        return [quote]
    spans = [match.span() for match in name.finditer(quote)]
    points = [mark for mark in CLAUSE_END.finditer(quote)
              if not any(left <= mark.start() < right for left, right in spans)]
    return [quote[left:right] for left, right in zip(
        [0, *(mark.end() for mark in points)], [*(mark.start() for mark in points), len(quote)],
    )]


def exact_name(name, quotes, catalog):
    if (not text(name, 160) or name != name.strip() or METRIC_OR_DATE.search(name)
            or alias_key(name) in catalog.company_aliases or alias_key(name) in catalog.technology_aliases):
        raise ValueError
    literal = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(name) + r'(?![A-Za-z0-9_])')
    if not any(literal.search(quote) for quote in quotes):
        raise ValueError
    return literal


def validate_one(proposal, articles, company_index, scope, catalog, tech_patterns):
    if not isinstance(proposal, dict) or proposal.keys() != PROPOSAL_FIELDS:
        raise ValueError
    name, kind, stage, evidence = (proposal[key] for key in ('projectName', 'kind', 'stage', 'evidence'))
    if (not isinstance(kind, str) or kind not in CLASSIFICATIONS
            or (stage is not None and (not isinstance(stage, str) or stage not in STAGES))
            or not isinstance(evidence, list) or not 1 <= len(evidence) <= MAX_QUOTES):
        raise ValueError
    references, passages, seen = [], [], set()
    for item in evidence:
        if not isinstance(item, dict) or item.keys() != {'articleId', 'quote'}:
            raise ValueError
        article_id, quote = item['articleId'], item['quote']
        if (not identifier(article_id) or article_id not in scope or article_id in seen
                or not text(quote, EXTENT) or len(quote.strip()) < MIN_QUOTE or quote != quote.strip()):
            raise ValueError
        source = articles[article_id]
        context = list(cited_passages(source, quote))
        if not context:
            raise ValueError
        passages.extend(context)
        seen.add(article_id)
        references.append({'articleId': article_id, 'quote': quote,
                           **{key: source[key] for key in REFERENCE_FIELDS if key != 'id'}})

    cited = [articles[key] for key in sorted(seen)]
    companies = entity_ids(proposal['companyIds'], catalog.company_aliases)
    technologies = entity_ids(proposal['technologyIds'], catalog.technology_aliases)
    material = [normalized_text(article[key]) for article in cited for key in ('title', 'excerpt')]
    if (any(not (company_index.get(company, set()) & seen) for company in companies)
            or any(not any(pattern.search(part) for pattern in tech_patterns[technology] for part in material)
                   for technology in technologies)):
        raise ValueError
    quotes = [entry['quote'] for entry in references]
    name_match = exact_name(name, quotes, catalog) if name is not None else None
    kind, stage = evidence_classification(kind, stage, quotes, passages, name_match)
    return {
        'candidateId': opaque_id('candidate', *sorted(seen)), 'projectName': name,
        'companyIds': companies, 'technologyIds': technologies, 'kind': kind, 'stage': stage,
        'reviewStatus': 'pending', 'evidence': sorted(references, key=lambda item: item['articleId']),
    }


def coalesce(rows):
    result = min(rows, key=lambda row: json.dumps(row, ensure_ascii=True, sort_keys=True))
    result = dict(result)
    if len({(row['kind'], row['stage']) for row in rows}) > 1:
        result.update(kind='unresolved', stage=None)
    if len({row['projectName'] for row in rows}) > 1:
        result['projectName'] = None
    for name in ('companyIds', 'technologyIds'):
        result[name] = sorted(set.intersection(*(set(row[name]) for row in rows)))
    return result


def validate_candidates(snapshot, prediction, article_ids=None):
    """Produce pending private candidates; proposals never enter the importer."""
    if (not isinstance(prediction, dict) or prediction.keys() != {'candidates'}
            or not isinstance(prediction['candidates'], list) or len(prediction['candidates']) > MAX_PROPOSALS):
        raise TrackerError('Invalid extraction response envelope.')
    articles, companies = intact_snapshot(snapshot)
    if article_ids is not None and (
        not isinstance(article_ids, (list, tuple, set, frozenset))
        or not all(identifier(value) and value in articles for value in article_ids)
    ):
        raise TrackerError('Extraction response scope contains unknown article references.')
    scope = set(articles if article_ids is None else article_ids)
    catalog, technologies = entity_catalog()
    by_id, rejected = defaultdict(list), 0
    for proposal in prediction['candidates']:
        try:
            candidate = validate_one(proposal, articles, companies, scope, catalog, technologies)
        except ValueError:
            rejected += 1
        else:
            by_id[candidate['candidateId']].append(candidate)
    return {'version': 1, 'candidates': [coalesce(by_id[key]) for key in sorted(by_id)],
            'rejected': rejected, 'duplicates': sum(len(rows) - 1 for rows in by_id.values())}
