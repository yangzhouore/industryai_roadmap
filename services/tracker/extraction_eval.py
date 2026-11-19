"""Offline extraction baseline and aggregate metrics against reviewed cases."""

import re
from collections import defaultdict

from .evidence_batch import STAGE_FOR
from .extraction_validation import lifecycle_evidence
from .inventory import inventory, mention_pattern, normalized_text
from .manifest import Catalog, TrackerError


_LIFECYCLE_ORDER = ('scaling', 'deployment', 'pilot', 'prototype', 'research', 'commercial')
_NON_OPERATING = {
    'partnership': re.compile(r'\b(?:partners?(?:hip|ing)?|collaborat(?:e|es|ion|ing)|memorandum of understanding)\b', re.I),
    'announcement': re.compile(r'\b(?:announc(?:e|ed|ement|es|ing)|plans? to|will deploy|scheduled to)\b', re.I),
    'marketing': re.compile(r'\b(?:webinar|learn how|accelerate your|help(?:s|ing)? organizations|showcas(?:e|es|ed|ing))\b', re.I),
}
_PROJECT_NAME = re.compile(
    r'(?i)\b(?:project|initiative|program(?:me)?|system|agent|platform)\s+(?:named|called)\s+["“]([^"”\r\n]{2,120})["”]'
)


def _spans(article):
    for field in ('title', 'excerpt'):
        for sentence in re.split(r'(?<=[.!?。！？])\s+|[\r\n]+', article[field]):
            sentence = sentence.strip()
            if sentence:
                yield sentence[:500]


def _classify(spans):
    for kind in _LIFECYCLE_ORDER:
        for span in spans:
            if lifecycle_evidence(kind, span):
                return kind, span
    for kind, pattern in _NON_OPERATING.items():
        for span in spans:
            if pattern.search(span):
                return kind, span
    return 'unresolved', spans[0]


def offline_predictions(snapshot, article_ids=None):
    """Predict with fixed text rules and exact entity aliases, without reference labels."""
    articles = {article['id']: article for article in snapshot['articles']}
    if len(articles) != len(snapshot['articles']):
        raise TrackerError('Offline extraction requires unique canonical article IDs.')
    selected = set(articles if article_ids is None else article_ids)
    if not selected <= articles.keys():
        raise TrackerError('Offline extraction refers to an unknown article.')

    index = inventory(snapshot['articles'], snapshot['editions'])
    companies = defaultdict(list)
    for company_id, group in index['companies'].items():
        for article in group['articles']:
            if article['matches']['title'] or article['matches']['excerpt']:
                companies[article['id']].append(company_id)
    technologies = {
        entry.id: tuple(mention_pattern(alias) for alias in entry.aliases)
        for entry in Catalog.load().technologies
    }

    candidates = []
    for article_id in sorted(selected):
        article = articles[article_id]
        spans = list(_spans(article))
        if not spans:
            continue
        kind, quote = _classify(spans)
        project = _PROJECT_NAME.search(quote)
        normalized = [normalized_text(article[field]) for field in ('title', 'excerpt')]
        candidates.append({
            'projectName': project.group(1) if project else None,
            'companyIds': sorted(companies[article_id]),
            'technologyIds': sorted(technology for technology, aliases in technologies.items()
                                    if any(alias.search(part) for alias in aliases for part in normalized)),
            'kind': kind,
            'stage': STAGE_FOR.get(kind),
            'evidence': [{'articleId': article_id, 'quote': quote}],
        })
    return {'candidates': candidates}


def _ratio(numerator, denominator):
    return round(numerator / denominator, 6) if denominator else None


def _evidence_checks(row, articles):
    dates = canonical = True
    for evidence in row['evidence']:
        article = articles[evidence['articleId']]
        quote = evidence.get('quote')
        canonical = canonical and isinstance(quote, str) and bool(quote) and (
            quote in article['title'] or quote in article['excerpt']
        ) and all(evidence.get(key) == article[key] for key in ('url', 'publisher', 'sourceId', 'contentHash'))
        dates = dates and all(key in evidence and evidence[key] == article[key]
                             for key in ('publishedAt', 'eventAt', 'sourceTimezone'))
    return canonical, dates


def evaluate(snapshot, gold_curation, validated):
    """Score exact article-set matches and publish aggregate counts only."""
    articles = {article['id']: article for article in snapshot['articles']}
    predictions = defaultdict(list)
    for row in validated['candidates']:
        predictions[frozenset(item['articleId'] for item in row['evidence'])].append(row)
    cases = {}
    for case in gold_curation['candidates']:
        article_ids = frozenset(item['articleId'] for item in case['evidence'])
        if not article_ids or not article_ids <= articles.keys() or article_ids in cases:
            raise TrackerError('Evaluation cases require unique, known canonical article sets.')
        cases[article_ids] = case

    expected_supported = sum(case['status'] == 'supported' for case in cases.values())
    expected_unresolved = len(cases) - expected_supported
    matched = ambiguous = stage_correct = kind_correct = evidence_correct = dates_correct = 0
    supported_correct = supported_predictions = unresolved_correct = 0
    for article_ids, case in cases.items():
        rows = predictions.get(article_ids, [])
        supported_predictions += sum(row['stage'] is not None for row in rows)
        if len(rows) != 1:
            ambiguous += len(rows) > 1
            continue
        matched += 1
        row = rows[0]
        expected_stage = case['stage'] if case['status'] == 'supported' else None
        same_stage = row['stage'] == expected_stage
        stage_correct += same_stage
        kind_correct += row['kind'] == case['classification']
        supported_correct += same_stage and expected_stage is not None
        unresolved_correct += same_stage and expected_stage is None
        canonical, dates = _evidence_checks(row, articles)
        evidence_correct += canonical
        dates_correct += dates

    return {
        'cases': len(cases),
        'predictedCases': matched,
        'ambiguousCases': ambiguous,
        'expectedSupported': expected_supported,
        'expectedUnresolved': expected_unresolved,
        'stageMatches': stage_correct,
        'kindMatches': kind_correct,
        'stageAccuracy': _ratio(stage_correct, len(cases)),
        'kindAccuracy': _ratio(kind_correct, len(cases)),
        'supportedPrecision': _ratio(supported_correct, supported_predictions),
        'supportedRecall': _ratio(supported_correct, expected_supported),
        'unresolvedRecall': _ratio(unresolved_correct, expected_unresolved),
        'canonicalEvidenceCases': evidence_correct,
        'canonicalDateCases': dates_correct,
        'unmatchedPredictionRows': sum(len(rows) for key, rows in predictions.items() if key not in cases),
    }
