"""Offline review prompts. Heuristics never certify originality, facts or reuse rights."""
from difflib import SequenceMatcher
from hashlib import sha256
import json
import re
import unicodedata

MAX_INPUT_BYTES = 2 * 1024 * 1024
FIELDS = ('title', 'summary', 'why', 'limitation')


def _bounded(issue):
    if not isinstance(issue, dict):
        raise ValueError('An issue object is required')
    try:
        encoded = json.dumps(issue, ensure_ascii=True, sort_keys=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, RecursionError):
        raise ValueError('Bounded JSON content is required') from None
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError('Review input exceeds its private analysis bound')
    if not isinstance(issue.get('sources'), list) or not isinstance(issue.get('stories'), list):
        raise ValueError('Issue source/story arrays are required')
    if len(issue['sources']) > 200 or len(issue['stories']) > 200:
        raise ValueError('Review record count exceeds its bound')
    return encoded


def _normalize(value):
    return re.sub(r'[^\w]', '', unicodedata.normalize('NFKC', str(value)).casefold())


def _pair(value, locale):
    return value.get(locale, '') if isinstance(value, dict) and isinstance(value.get(locale), str) else ''


def _numbers(text):
    # Numeric/unit mentions only: scores and metadata are not prose claims.
    return set(re.findall(r'(?<!\w)\d+(?:[.,]\d+)*(?:\s?[%\uFF05])?|\d+(?:\.\d+)?|[\u96F6\u3007\u4E00\u4E8C\u4E09\u56DB\u4E94\u516D\u4E03\u516B\u4E5D\u5341\u767E\u5343\u4E07\u4EBF]+(?=[\u5BB6\u53F0\u4E2A\u9879\u5E74\u6708\u5929\u500D])', unicodedata.normalize('NFKC', text)))


def analyze(issue):
    """Return stable, revision-bound prompts; callers require independent human review."""
    full_hash = sha256(_bounded(issue)).hexdigest()
    findings = []
    comparison_budget = 128
    budget_reported = False
    sources = {s['id']: s for s in issue.get('sources', []) if isinstance(s, dict) and isinstance(s.get('id'), str)}

    def add(scope, severity, kind, reason, ids=()):
        item = {'storyId': scope, 'severity': severity, 'kind': kind, 'reason': reason,
                'sourceIds': sorted(set(ids))}
        encoded = json.dumps(item, sort_keys=True, ensure_ascii=True).encode('ascii')
        item['id'] = 'risk-' + sha256(full_hash.encode('ascii') + b'\n' + encoded).hexdigest()[:24]
        findings.append(item)

    def assets(value, path='issue'):
        if isinstance(value, dict):
            for key, child in value.items():
                location = path + '.' + key
                if re.search(r'(?:asset|image|logo|video|thumbnail|embed|html|media|photo|artwork|graphic|svg|icon|attachment|enclosure|poster|audio|script|iframe)', key, re.I) and child:
                    add(location, 'high', 'asset_review',
                        'Unknown or retained asset/HTML field requires private rights and safety review; do not embed it.')
                assets(child, location)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                assets(child, f'{path}[{index}]')
    assets(issue)
    scopes = [(issue, ('title', 'introduction'), list(sources), 'issue:' + str(issue.get('id', 'unknown')))]
    scopes.extend((story, FIELDS, story.get('sourceIds', []) if isinstance(story, dict) else [], None) for story in issue.get('stories', []))
    for story, fields, requested, issue_scope in scopes:
        if not isinstance(story, dict):
            add('issue', 'high', 'malformed_story', 'A malformed story needs correction before review.')
            continue
        sid = issue_scope or str(story.get('id', 'missing-story-id'))
        ids = [i for i in requested if isinstance(i, str)] if isinstance(requested, list) else []
        cited = [sources[i] for i in ids if i in sources]
        if not ids or len(cited) != len(ids):
            add(sid, 'high', 'missing_citation', 'Missing/unresolved citation IDs leave factual claims unsupported.', ids)
        # Every fact still needs human judgment even when a lexical check finds no risk.
        add(sid, 'review', 'human_fact_review',
            'Review every factual clause, qualifier, entity, date and both languages against the exact cited records; lexical matching is not verification.', ids)
        matched_locales = set()
        for locale in ('en', 'zh'):
            evidence = '\n'.join(_pair(s.get('excerpt'), locale) for s in cited)
            available_numbers = _numbers(evidence)
            for field in fields:
                text = _pair(story.get(field), locale)
                if not text:
                    add(sid, 'high', 'missing_bilingual_field', f'{field}.{locale} is absent; bilingual human review cannot be completed.', ids)
                    continue
                normalized = _normalize(text)
                for source in cited:
                    excerpt = _normalize(_pair(source.get('excerpt'), locale))
                    if len(normalized) < (12 if locale == 'zh' else 28) or not excerpt:
                        continue
                    if comparison_budget <= 0:
                        if not budget_reported:
                            add('issue', 'high', 'analysis_bound', 'Lexical comparison budget exhausted; the remaining text requires full human comparison.')
                            budget_reported = True
                        break
                    comparison_budget -= 1
                    sample, evidence_sample = normalized[:1024], excerpt[:1024]
                    if len(normalized)>1024 or len(excerpt)>1024:
                        add(sid, 'review', 'analysis_bound', f'{field}.{locale} near-match checking uses a bounded leading sample; inspect the remaining text manually.', [source['id']])
                    matcher = SequenceMatcher(None, sample, evidence_sample, autojunk=True)
                    longest = matcher.find_longest_match(0, len(sample), 0, len(evidence_sample)).size
                    copied = normalized in excerpt or longest >= (18 if locale == 'zh' else 48)
                    near = matcher.ratio() >= 0.65 or longest / len(sample) >= 0.65
                    if copied or near:
                        matched_locales.add(locale)
                        add(sid, 'high', 'copied_passage' if copied else 'near_copied_passage',
                            f'{field}.{locale} overlaps retained source text; inspect wording and permissions rather than treating paraphrase as clearance.', [source['id']])
                unsupported = sorted(_numbers(text) - available_numbers)
                if unsupported:
                    add(sid, 'high', 'unsupported_number',
                        f'{field}.{locale} contains numeric/unit mentions absent from the same-language cited evidence: ' + ', '.join(unsupported) + '. Translation or formatting differences require human reconciliation.', ids)
                if evidence and len(normalized) >= 30:
                    a = set(re.findall(r'[a-z]{4,}', text.casefold())) if locale == 'en' else set(re.findall(r'[\u3400-\u9fff]{2}', text))
                    b = set(re.findall(r'[a-z]{4,}', evidence.casefold())) if locale == 'en' else set(re.findall(r'[\u3400-\u9fff]{2}', evidence))
                    if a and len(a & b) / len(a) < 0.08:
                        add(sid, 'review', 'unsupported_claim_scope',
                            f'{field}.{locale} has little lexical overlap with cited evidence. It may be independent analysis, translation variation or an unsupported claim; review clause by clause.', ids)
        if matched_locales:
            add(sid, 'high', 'translated_dependence',
                'One or both language versions closely track retained evidence. Translation can preserve source expression; separately review English and Chinese originality and rights.', ids)
    return findings


def suggest(issue):
    """Editable prompts only; no factual draft, copied source passage or API generation."""
    _bounded(issue)
    available = {s.get('id'):s for s in issue.get('sources', []) if isinstance(s, dict)}
    result = {}
    for story in issue.get('stories', []):
        if not isinstance(story, dict) or not isinstance(story.get('id'), str):
            continue
        ids = [i for i in story.get('sourceIds', []) if isinstance(i, str) and i in available]
        refs = ', '.join(ids) or '[NO RESOLVED CITATION]'
        anchors = '\n'.join(' | '.join(str(available[i].get(key,'[NOT PROVIDED]')) for key in ('id','name','publishedAt','eventAt','url')) for i in ids) or '[NO CITED SOURCE METADATA]'
        lead_ref = str(available[ids[0]].get('name','[PUBLISHER]')) if ids else '[PUBLISHER]'
        lead_date = str(available[ids[0]].get('publishedAt','[PUBLICATION DATE]')) if ids else '[PUBLICATION DATE]'
        result[story['id']] = {
            'en': ('MACHINE-ASSISTED EDITABLE SUGGESTION - UNREVIEWED, NOT A FACTUAL ARTICLE OR APPROVAL\n'
                   'Cited source metadata (ID | publisher | publication | event | URL):\n' + anchors + '\n'
                   'Lede template: In its source record dated ' + lead_date + ', ' + lead_ref + ' describes [INSERT ONLY THE EVIDENCE-CHECKED INDUSTRIAL WORKFLOW, ORGANIZATION AND MATURITY]. [ADD A PRECISE CITATION; LEAVE UNRESOLVED FACTS BLANK].\n'
                   'Title: [Write a fresh headline after checking the cited records.]\n'
                   'Summary: [Describe only the evidenced industrial workflow, attributed organization and actual maturity; leave unsupported details blank.]\n'
                   'Analysis template: The operational question is [YOUR ORIGINAL, EXPLICITLY LABELED ANALYSIS ABOUT THE VERIFIED WORKFLOW]; the cited record supports [CHECKED FACTUAL BASIS], while [UNRESOLVED CONTEXT] remains unverified.\n'
                   'Limitation template: The record establishes [CHECKED SCOPE] but does not establish [IDENTIFIED EVIDENCE GAP]; [HUMAN CHECK REQUIRED] before any claim about deployment, results or metrics.\n'
                   'Citations to inspect: ' + refs + '\n'
                   'Retain factual names/numbers only after checking evidence; do not translate or lightly rewrite source prose. Resolve every placeholder manually.'),
            'zh': ('\u673a\u5668\u8f85\u52a9\u7f16\u8f91\u5efa\u8bae\uff1a\u672a\u7ecf\u4eba\u5de5\u5ba1\u6838\uff0c\u4e0d\u662f\u4e8b\u5b9e\u6587\u7ae0\u6216\u6279\u51c6\u3002\n'
                   '\u5f15\u7528\u5143\u6570\u636e (ID | publisher | publication | event | URL):\n' + anchors + '\n'
                   '\u5bfc\u8bed\u6a21\u677f\uff1a' + lead_ref + '\u5728 ' + lead_date + '\u7684\u6765\u6e90\u8bb0\u5f55\u4e2d\u63cf\u8ff0\u4e86[\u4ec5\u586b\u5199\u5df2\u6838\u5bf9\u7684\u5de5\u4e1a\u6d41\u7a0b\u3001\u673a\u6784\u548c\u6210\u719f\u5ea6]\uff0c[\u6dfb\u52a0\u51c6\u786e\u5f15\u7528\uff0c\u4e0d\u660e\u4e8b\u5b9e\u7559\u7a7a]\u3002\n'
                   '\u6807\u9898\uff1a[\u6838\u5bf9\u5f15\u7528\u540e\u72ec\u7acb\u64b0\u5199\u6807\u9898\u3002]\n'
                   '\u6458\u8981\uff1a[\u4ec5\u63cf\u8ff0\u8bc1\u636e\u652f\u6301\u7684\u5de5\u4e1a\u6d41\u7a0b\u3001\u673a\u6784\u548c\u6210\u719f\u5ea6\uff1b\u4e0d\u660e\u7ec6\u8282\u7559\u7a7a\u3002]\n'
                   '\u5206\u6790\u6a21\u677f\uff1a[\u5df2\u6838\u5bf9\u7684\u5de5\u4e1a\u6d41\u7a0b]\u63d0\u51fa\u7684\u64cd\u4f5c\u95ee\u9898\u662f[\u72ec\u7acb\u5206\u6790]\uff0c\u4f46[\u672a\u6838\u5b9e\u7684\u4e0a\u4e0b\u6587]\u4ecd\u5f85\u9a8c\u8bc1\u3002\n'
                   '\u5c40\u9650\u6a21\u677f\uff1a\u5f53\u524d\u8bb0\u5f55\u4ec5\u80fd\u652f\u6301[\u8bc1\u636e\u8303\u56f4]\uff0c\u5c1a\u4e0d\u80fd\u652f\u6301[\u8bc1\u636e\u7f3a\u53e3]\uff1b\u4efb\u4f55\u90e8\u7f72\u6216\u6307\u6807\u65ad\u8a00\u5747\u9700[\u4eba\u5de5\u6838\u67e5]\u3002\n'
                   '\u9700\u6838\u5bf9\u7684\u5f15\u7528\uff1a' + refs + '\n'
                   '\u540d\u79f0\u548c\u6570\u5b57\u987b\u6838\u5bf9\u8bc1\u636e\uff1b\u4e0d\u76f4\u63a5\u7ffb\u8bd1\u6216\u8f7b\u5fae\u6539\u5199\u6765\u6e90\u6587\u5b57\uff0c\u6240\u6709\u5360\u4f4d\u7b26\u7531\u4eba\u5de5\u89e3\u51b3\u3002')}
    return result
