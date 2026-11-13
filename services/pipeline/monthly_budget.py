"""Concurrent, fail-closed application estimates; never provider billing limits.

Rates retain the MVP-3 audited USD-per-million-token estimates: normal input,
cache read, cache write, output. Reserved request cost is a conservative UTF-8
byte input bound plus overhead and the configured maximum output tokens.
Unknown responses remain reserved. Actual provider billing can differ.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

from .budget import BudgetExceeded


RATES = {
    'gpt-6-luna': tuple(map(Decimal, ('.10', '.01', '.125', '.50'))),
    'gpt-6.1-terra': tuple(map(Decimal, ('1', '.05', '1.25', '5'))),
}
MILLION = Decimal(1000000)
BERLIN = ZoneInfo('Europe/Berlin')


def as_amount(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise BudgetExceeded('Malformed application cost') from None
    if not number.is_finite() or number < 0:
        raise BudgetExceeded('Malformed application cost')
    return number


def tokens(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BudgetExceeded('Malformed token usage; reservation retained')
    return value


def stored_money(value):
    """Match PostgreSQL NUMERIC(24,12), including legacy JSON float noise."""
    try:
        return as_amount(value).quantize(Decimal('.000000000001'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise BudgetExceeded('Application cost exceeds ledger precision') from None


def sanitized_usage(usage):
    """Retain known numeric counters only, never arbitrary provider fields."""
    if usage is None:
        return None
    if not isinstance(usage, dict):
        raise BudgetExceeded('Malformed legacy token usage')
    incoming, outgoing = tokens(usage.get('input_tokens')), tokens(usage.get('output_tokens'))
    input_details = usage.get('input_tokens_details')
    output_details = usage.get('output_tokens_details')
    input_details = {} if input_details is None else input_details
    output_details = {} if output_details is None else output_details
    if not isinstance(input_details, dict) or not isinstance(output_details, dict):
        raise BudgetExceeded('Malformed legacy token details')
    cached = tokens(input_details.get('cached_tokens', 0))
    written = tokens(input_details.get('cache_write_tokens', 0))
    reasoning = tokens(output_details.get('reasoning_tokens', 0))
    if cached + written > incoming or reasoning > outgoing:
        raise BudgetExceeded('Inconsistent legacy token usage')
    return {'input_tokens': incoming, 'output_tokens': outgoing,
            'input_tokens_details': {'cached_tokens': cached, 'cache_write_tokens': written},
            'output_tokens_details': {'reasoning_tokens': reasoning}}


class MonthlyBudget:
    def __init__(self, store, run_id=None, now=None, limit=2):
        self.store, self.run_id = store, run_id
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.limit = as_amount(limit)
        if not 0 < self.limit <= 2:
            raise ValueError('Monthly application ceiling is USD 2.00')
        self.pending = None

    def _time(self):
        current = self.now() if callable(self.now) else self.now
        if not isinstance(current, datetime) or current.tzinfo is None:
            raise ValueError('Budget time must be timezone-aware')
        return current

    def _month(self):
        return self._time().astimezone(BERLIN).strftime('%Y-%m')

    def _lock(self, month):
        if self.store.postgres:
            self.store.execute('SELECT pg_advisory_xact_lock(hashtext(?))',
                               ('industrial-ai-monthly-budget:' + month,))

    def _total(self, month):
        rows = self.store.execute('SELECT estimated_usd FROM api_requests WHERE month=?', (month,)).fetchall()
        return sum((as_amount(row[0]) for row in rows), Decimal(0))

    def before(self, context):
        model = context.get('model')
        if model not in RATES:
            raise BudgetExceeded('Unapproved model; no fallback')
        payload = context.get('request')
        if not isinstance(payload, dict):
            raise BudgetExceeded('Missing request budget envelope')
        output_bound = tokens(payload.get('max_output_tokens'))
        if not 1 <= output_bound <= 16000:
            raise BudgetExceeded('Request output exceeds approved envelope')
        try:
            input_bound = len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()) + 4096
        except (TypeError, ValueError):
            raise BudgetExceeded('Malformed request budget envelope') from None
        rates = RATES[model]
        reserve = (input_bound * max(rates[:3]) + output_bound * rates[3]) / MILLION
        month, identifier = self._month(), uuid4().hex
        attempt = tokens(context.get('attempt', 0))
        stage = context.get('stage')
        if not isinstance(stage, str) or not stage:
            raise BudgetExceeded('Missing request stage')
        with self.store.transaction():
            self._lock(month)
            if self._total(month) + reserve > self.limit:
                raise BudgetExceeded('Insufficient monthly application budget; no request sent')
            self.store.execute('''INSERT INTO api_requests
                (id,month,run_id,stage,model,attempt,status,reserved_usd,estimated_usd,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (identifier, month, self.run_id, stage, model, attempt, 'reserved',
                 str(reserve), str(reserve), self._time().isoformat()))
        # An earlier failed attempt stays reserved when a retry receives a new ID.
        self.pending = {'id': identifier, 'month': month, 'model': model,
                        'stage': stage,
                        'reserved': reserve, 'input_bound': input_bound, 'output_bound': output_bound}
        return identifier

    def after(self, record):
        pending, self.pending = self.pending, None
        if pending is None:
            raise BudgetExceeded('Response without a persisted request reservation')
        usage = record.get('usage')
        if usage is None:
            return
        if not isinstance(usage, dict):
            raise BudgetExceeded('Malformed usage; reservation retained')
        requested = record.get('requestedModel', pending['model'])
        if requested != pending['model']:
            raise BudgetExceeded('Response model does not match reservation')
        returned_model = record.get('model', pending['model'])
        if not isinstance(returned_model, str) or not (returned_model == pending['model']
                or returned_model.startswith(pending['model'] + '-')):
            raise BudgetExceeded('Response model does not match reservation')
        if record.get('stage', pending['stage']) != pending['stage']:
            raise BudgetExceeded('Response stage does not match reservation')
        input_count, output_count = tokens(usage.get('input_tokens')), tokens(usage.get('output_tokens'))
        details = usage.get('input_tokens_details', {})
        output_details = usage.get('output_tokens_details', {})
        details = {} if details is None else details
        output_details = {} if output_details is None else output_details
        if not isinstance(details, dict) or not isinstance(output_details, dict):
            raise BudgetExceeded('Malformed token details; reservation retained')
        cached, written = tokens(details.get('cached_tokens', 0)), tokens(details.get('cache_write_tokens', 0))
        reasoning = tokens(output_details.get('reasoning_tokens', 0))
        if cached + written > input_count or reasoning > output_count:
            raise BudgetExceeded('Inconsistent token usage; reservation retained')
        rates = RATES[pending['model']]
        estimated = ((input_count - cached - written) * rates[0] + cached * rates[1]
                     + written * rates[2] + output_count * rates[3]) / MILLION
        safe_usage = {'input_tokens': input_count, 'output_tokens': output_count,
                      'input_tokens_details': {'cached_tokens': cached, 'cache_write_tokens': written},
                      'output_tokens_details': {'reasoning_tokens': reasoning}}
        exceeded = input_count > pending['input_bound'] or output_count > pending['output_bound']
        if exceeded:
            estimated = max(estimated, pending['reserved'])
        response_id = record.get('responseId')
        if response_id is not None and (not isinstance(response_id, str)
                or re.fullmatch(r'resp_[A-Za-z0-9_-]{1,200}', response_id) is None):
            raise BudgetExceeded('Malformed response ID; reservation retained')
        with self.store.transaction():
            self._lock(pending['month'])
            self.store.execute('''UPDATE api_requests SET status=?,estimated_usd=?,usage=?,response_id=?
                WHERE id=? AND status='reserved' ''',
                ('measured', str(estimated), self.store.json_value(safe_usage), response_id, pending['id']))
        if exceeded:
            raise BudgetExceeded('Provider usage exceeded reserved envelope; further calls blocked')

    def summary(self, month=None):
        month = month or self._month()
        if not isinstance(month, str) or re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month) is None:
            raise ValueError('Budget month must be YYYY-MM')
        rows = self.store.execute('''SELECT model,status,reserved_usd,estimated_usd,usage,attempt
            FROM api_requests WHERE month=? ORDER BY created_at,id''', (month,)).fetchall()
        total = sum((as_amount(row[3]) for row in rows), Decimal(0))
        reserved = sum((as_amount(row[3]) for row in rows if row[1] == 'reserved'), Decimal(0))
        usage = {'inputTokens': 0, 'outputTokens': 0, 'reasoningTokens': 0}
        usage_unknown = 0
        for row in rows:
            data = json.loads(row[4]) if isinstance(row[4], str) else row[4]
            if data:
                usage['inputTokens'] += data.get('input_tokens', 0)
                usage['outputTokens'] += data.get('output_tokens', 0)
                usage['reasoningTokens'] += data.get('output_tokens_details', {}).get('reasoning_tokens', 0)
            else:
                usage_unknown += 1
        return {'month': month, 'limitUSD': float(self.limit), 'estimatedUSD': float(total),
                'remainingUSD': float(max(Decimal(0), self.limit - total)), 'reservedUSD': float(reserved),
                'requests': len(rows), 'reservedRequests': sum(row[1] == 'reserved' for row in rows),
                'retryRequests': sum(row[5] > 0 for row in rows), 'models': sorted({row[0] for row in rows}),
                'usageUnknownRequests': usage_unknown,
                **usage, 'basis': 'application estimate, including unresolved reservations; not provider billing'}

    def import_legacy(self, path, month='2026-11'):
        """Idempotently retain already incurred MVP-3 estimates before new paid work."""
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        records = data.get('requests')
        if not isinstance(records, list):
            raise BudgetExceeded('Legacy ledger is malformed')
        if not isinstance(month, str) or re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month) is None:
            raise ValueError('Budget month must be YYYY-MM')
        prepared = []
        for index, record in enumerate(records):
            if not isinstance(record, dict) or record.get('model') not in RATES:
                raise BudgetExceeded('Legacy ledger has an unknown model')
            charge = stored_money(record.get('charge'))
            reserve = stored_money(record.get('reserved', charge))
            usage = sanitized_usage(record.get('usage'))
            attempt = tokens(record.get('attempt', 0))
            response_id = record.get('responseId')
            if not isinstance(response_id, str) or re.fullmatch(r'resp_[A-Za-z0-9_-]{1,200}', response_id) is None:
                response_id = None
            identifier = 'legacy-mvp3-' + sha256(f'{month}:{index}'.encode()).hexdigest()
            prepared.append((identifier, record, charge, reserve, usage, attempt, response_id))
        with self.store.transaction():
            self._lock(month)
            for identifier, record, charge, reserve, usage, attempt, response_id in prepared:
                old = self.store.execute('SELECT estimated_usd,reserved_usd,model FROM api_requests WHERE id=?', (identifier,)).fetchone()
                if old and (stored_money(old[0]) != charge or stored_money(old[1]) != reserve or old[2] != record['model']):
                    raise BudgetExceeded('Previously imported legacy estimate changed; manual reconciliation required')
                stage = record.get('stage') if record.get('stage') in {'classify', 'generate', 'verify'} else 'unknown'
                self.store.execute('''INSERT INTO api_requests
                    (id,month,run_id,stage,model,attempt,status,reserved_usd,estimated_usd,usage,response_id,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING''',
                    (identifier, month, None, 'legacy:' + stage,
                     record['model'], attempt, 'measured' if record.get('status') == 'measured' else 'reserved',
                     str(reserve), str(charge), self.store.json_value(usage) if usage is not None else None,
                     response_id, self._time().isoformat()))
                # Metadata-only reconciliation of an earlier import; money/status
                # remain untouched and existing known usage is never overwritten.
                self.store.execute('''UPDATE api_requests SET usage=coalesce(usage,?),
                    response_id=coalesce(response_id,?),attempt=CASE WHEN attempt=0 THEN ? ELSE attempt END
                    WHERE id=?''', (self.store.json_value(usage) if usage is not None else None,
                                    response_id, attempt, identifier))
        return len(prepared)

    def import_charge(self, identifier, month, amount, model='historical'):
        """Preserve a documented pre-ledger estimate without recording credential data."""
        charge = stored_money(amount)
        if (not isinstance(identifier, str) or not identifier or not isinstance(month, str)
                or re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month) is None):
            raise ValueError('Historical charge needs a stable ID and month')
        with self.store.transaction():
            self._lock(month)
            old = self.store.execute('SELECT month,estimated_usd FROM api_requests WHERE id=?', (identifier,)).fetchone()
            if old:
                if old[0] != month or stored_money(old[1]) != charge:
                    raise BudgetExceeded('Historical estimate changed; manual reconciliation required')
                return False
            self.store.execute('''INSERT INTO api_requests
                (id,month,run_id,stage,model,attempt,status,reserved_usd,estimated_usd,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (identifier, month, None, 'legacy', model, 0, 'measured',
                 str(charge), str(charge), self._time().isoformat()))
        return True
