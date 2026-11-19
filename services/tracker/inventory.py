"""Find exact company names in stored material without inferring project roles."""

from collections import defaultdict
import re
import unicodedata

from .manifest import alias_key


# Short Latin acronyms require uppercase and token boundaries. Product names
# such as Azure and broad parent references such as Amazon are excluded.
COMPANIES = {
    'siemens': ('Siemens', '西门子', 'Siemens AG'),
    'nvidia': ('NVIDIA', '英伟达', 'Nvidia Corporation'),
    'abb': ('ABB', 'ABB Ltd', 'ABB Group'),
    'schneider-electric': ('Schneider Electric', '施耐德电气', 'Schneider Electric SE'),
    'microsoft': ('Microsoft', '微软', 'Microsoft Corporation'),
    'aws': ('Amazon Web Services', '亚马逊云科技', 'AWS'),
}
ACRONYMS = {'ABB', 'AWS'}
FIELDS = ('title', 'excerpt', 'publisher')
REFERENCE_FIELDS = ('id', 'sourceId', 'publisher', 'url', 'publishedAt', 'eventAt', 'sourceTimezone', 'contentHash')


def normalized_text(value):
    return ' '.join(unicodedata.normalize('NFKC', value or '').split())


def mention_pattern(alias):
    pattern = re.escape(alias)
    if alias.isascii():
        pattern = rf'(?<![A-Za-z0-9_]){pattern}(?![A-Za-z0-9_])'
    return re.compile(pattern, 0 if alias in ACRONYMS else re.IGNORECASE)


PATTERNS = {company: [(alias, mention_pattern(alias)) for alias in aliases]
            for company, aliases in COMPANIES.items()}


def edition_references(editions):
    links = defaultdict(list)
    classifications = defaultdict(list)
    names = {alias_key(alias): company for company, aliases in COMPANIES.items() for alias in aliases}
    for edition in sorted(editions, key=lambda row: row['id']):
        base = {'issueId': edition['id'], 'slug': edition['slug']}
        stories = {story['id']: story for story in edition['content']['stories']}
        for story_id, story in sorted(stories.items()):
            company = names.get(alias_key(story.get('company') or ''))
            if company:
                classifications[company].append({
                    **base, 'storyId': story_id, 'company': story['company'], 'stage': story.get('maturity'),
                })
        ordered = sorted(edition['bindings'], key=lambda binding: (
            binding['storyId'], binding['rawArticleId'], binding['claimKey'], binding['sourceUrl'],
        ))
        for binding in ordered:
            if binding['storyId'] in stories:
                links[(binding['rawArticleId'], binding['sourceUrl'])].append({
                    **base, 'storyId': binding['storyId'],
                    'claimKey': binding['claimKey'], 'sourceUrl': binding['sourceUrl'],
                })
    return links, classifications


def inventory(articles, editions):
    """Index candidate mentions, source provenance, and exact edition links.

    A publisher match describes where an article came from. An edition match
    records a citation or stored classification. None of these matches by
    themselves verify an operational deployment or a subject's role.
    """
    links, classifications = edition_references(editions)
    references = defaultdict(list)
    for article in sorted(articles, key=lambda row: row['id']):
        fields = {field: normalized_text(article.get(field)) for field in FIELDS}
        for company, aliases in PATTERNS.items():
            matches = {field: [alias for alias, pattern in aliases if pattern.search(value)]
                       for field, value in fields.items()}
            if any(matches.values()):
                reference = {key: article[key] for key in REFERENCE_FIELDS}
                references[company].append({
                    **reference, 'matches': matches, 'editionLinks': links[(article['id'], article['url'])],
                })

    companies = {}
    for company, aliases in COMPANIES.items():
        rows = references[company]
        stories = classifications[company]
        companies[company] = {
            'id': company, 'name': aliases[0], 'aliases': list(aliases),
            'counts': {
                'articles': len(rows),
                **{field: sum(bool(row['matches'][field]) for row in rows) for field in FIELDS},
                'editionBoundArticles': sum(bool(row['editionLinks']) for row in rows),
                'classifiedStories': len(stories),
            },
            'articles': rows, 'editionClassifications': stories,
        }
    return {'version': 1, 'articleCount': len(articles), 'editionCount': len(editions), 'companies': companies}
