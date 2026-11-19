"""Prepare or validate private extraction candidates without making API calls."""

import argparse
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import json
from pathlib import Path
import sys

from services.review.security import ReviewError, load_private_json
from .evidence_snapshot import private_output, write_json
from .extraction_eval import evaluate, offline_predictions
from .extraction_request import MAX_ARTICLES, request_bundle, response_json
from .extraction_validation import validate_candidates
from .manifest import TrackerError


DEFAULT_MODEL = 'gpt-6.1-terra'
STANDARD_RATES = {DEFAULT_MODEL: ('1.00', '5.00'), 'gpt-6-luna': ('0.10', '0.50')}
PRICING_URL = 'https://developers.openai.com/api/docs/pricing'


def estimate_cost(bundle, input_rate=None, output_rate=None):
    model = bundle['model']
    if (input_rate is None) != (output_rate is None):
        raise TrackerError('Provide both token rates or use a model with listed rates.')
    if input_rate is None:
        if model not in STANDARD_RATES:
            raise TrackerError('Custom models require explicit input and output rates.')
        input_rate, output_rate = STANDARD_RATES[model]
    try:
        rates = Decimal(input_rate), Decimal(output_rate)
        if any(not rate.is_finite() or not 0 <= rate <= 1000 or rate.as_tuple().exponent < -8 for rate in rates):
            raise ValueError
    except (InvalidOperation, TypeError, ValueError) as error:
        raise TrackerError('Token rates must be finite nonnegative prices per million tokens.') from error

    sizes = [len(json.dumps(request['body'], ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
             for request in bundle['requests']]
    input_tokens = sum((size + 3) // 4 for size in sizes)
    padded_input_tokens = sum(size + 256 for size in sizes)
    output_tokens = sum(request['body']['max_output_tokens'] for request in bundle['requests'])

    def usd(tokens):
        amount = (tokens * rates[0] + output_tokens * rates[1]) / Decimal(1_000_000)
        return str(amount.quantize(Decimal('0.000001'), rounding=ROUND_CEILING))

    return {
        'model': model, 'requests': len(sizes), 'inputUsdPerMillion': str(rates[0]),
        'outputUsdPerMillion': str(rates[1]), 'estimatedInputTokens': input_tokens,
        'paddedInputTokenProxy': padded_input_tokens, 'maximumRequestedOutputTokens': output_tokens,
        'estimatedUsdAtFullOutput': usd(input_tokens), 'paddedUsdAtFullOutput': usd(padded_input_tokens),
        'pricingReference': PRICING_URL,
    }


def selected_articles(snapshot, requested):
    if (not isinstance(snapshot, dict) or type(snapshot.get('version')) is not int
            or snapshot['version'] != 1 or not isinstance(snapshot.get('articles'), list)
            or not isinstance(snapshot.get('editions'), list)):
        raise TrackerError('The extraction snapshot format is invalid.')
    known = [article['id'] for article in snapshot['articles']]
    if len(known) != len(set(known)):
        raise TrackerError('The extraction snapshot contains duplicate article identities.')
    if requested is None:
        return set(known)
    selected = set(requested)
    if not selected <= set(known) or len(selected) != len(requested):
        raise TrackerError('Select unique articles from the canonical snapshot.')
    return selected


def validate_saved(snapshot, saved, allowed):
    if (not isinstance(saved, dict) or saved.keys() != {'version', 'responses'}
            or type(saved['version']) is not int or saved['version'] != 1
            or not isinstance(saved['responses'], list) or len(saved['responses']) > MAX_ARTICLES):
        raise TrackerError('The saved Responses bundle format is invalid.')
    results = {'version': 1, 'candidates': [], 'rejected': 0, 'duplicates': 0}
    seen = set()
    for record in saved['responses']:
        if not isinstance(record, dict) or record.keys() != {'articleId', 'response'}:
            raise TrackerError('Every saved response must name its canonical article.')
        article_id = record['articleId']
        if not isinstance(article_id, str) or article_id not in allowed or article_id in seen:
            raise TrackerError('A saved response repeated or exceeded its canonical article scope.')
        seen.add(article_id)
        validated = validate_candidates(snapshot, response_json(record['response']), {article_id})
        results['candidates'].extend(validated['candidates'])
        results['rejected'] += validated['rejected']
        results['duplicates'] += validated['duplicates']
    results['candidates'].sort(key=lambda candidate: candidate['candidateId'])
    return results


def evaluated_articles(gold):
    if (not isinstance(gold, dict) or type(gold.get('version')) is not int or gold['version'] != 1
            or not isinstance(gold.get('candidates'), list) or not gold['candidates']):
        raise TrackerError('Evaluation requires a protected, nonempty reference curation.')
    return sorted({item['articleId'] for row in gold['candidates'] for item in row['evidence']})


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_subparsers(dest='mode', required=True)
    for name in ('requests', 'candidates', 'evaluate'):
        mode = modes.add_parser(name)
        mode.add_argument('--snapshot', type=Path, required=True)
        mode.add_argument('--output', type=Path, required=True)
        if name != 'evaluate':
            mode.add_argument('--article-id', action='append')
        if name == 'requests':
            mode.add_argument('--model', default=DEFAULT_MODEL)
            mode.add_argument('--input-rate')
            mode.add_argument('--output-rate')
        else:
            mode.add_argument('--responses', type=Path)
        if name == 'evaluate':
            mode.add_argument('--gold', type=Path, required=True)
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        output = private_output(args.output)
        snapshot = load_private_json(args.snapshot)
        gold = load_private_json(args.gold) if args.mode == 'evaluate' else None
        selected = selected_articles(snapshot, evaluated_articles(gold) if gold is not None else args.article_id)
        if args.mode == 'requests':
            result = request_bundle(snapshot, args.model, sorted(selected))
            result['costEstimate'] = estimate_cost(result, args.input_rate, args.output_rate)
        else:
            if args.responses:
                result = validate_saved(snapshot, load_private_json(args.responses), selected)
                mode = 'saved-responses'
            else:
                result = validate_candidates(snapshot, offline_predictions(snapshot, selected), selected)
                mode = 'offline-heuristic'
            if gold is not None:
                result = {'version': 1, 'mode': mode, 'metrics': evaluate(snapshot, gold, result)}
            else:
                result['mode'] = mode
        write_json(output, result)
        print('Wrote a protected local extraction artifact.')
        return 0
    except (TrackerError, ReviewError) as error:
        print(str(error), file=sys.stderr)
    except (KeyError, TypeError, ValueError, OSError):
        print('Private extraction failed. Input details were withheld.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
