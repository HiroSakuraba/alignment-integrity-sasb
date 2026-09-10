"""Serial request ledger. Reserve before HTTP; uncertain calls retain reservation."""
from decimal import Decimal, ROUND_CEILING
from .adapters import AdapterError

# USD per million tokens; input includes a conservative 25% cache-write margin.
# Verified against provider documentation on 2026-09-10. Recheck before reuse.
RATES = {'openai': (Decimal('0.25'), Decimal('1.20')),
         'anthropic': (Decimal('1.25'), Decimal('5'))}
MAX_OUTPUT = 256
MAX_INPUT_BYTES = 12000


class BudgetExceeded(AdapterError):
    pass


class Budget:
    def __init__(self, dollars='0.50', max_requests=34, checkpoint=None):
        value = Decimal(str(dollars))
        if not value.is_finite() or not Decimal('0.000001') <= value <= Decimal('1'):
            raise ValueError('budget must be positive and at most $1')
        if type(max_requests) is not int or not 1 <= max_requests <= 34:
            raise ValueError('request limit must be 1..34')
        self.limit = int(value * 1000000)
        self.max_requests = max_requests
        self.entries = []
        self.blocked = None
        self.checkpoint = checkpoint or (lambda: None)

    @property
    def charged(self):
        return sum(e['accounted_microdollars'] for e in self.entries)

    def stop(self, reason):
        self.blocked = reason
        self.checkpoint()
        raise BudgetExceeded(reason)

    def reserve(self, provider, model, system, user):
        if self.blocked:
            raise BudgetExceeded(self.blocked)
        if any(e['status'] in {'pending', 'unknown', 'failed'} for e in self.entries):
            self.stop('unresolved request; stop and reconcile provider usage')
        size = len(system.encode('utf-8')) + len(user.encode('utf-8'))
        if size > MAX_INPUT_BYTES:
            self.stop('input exceeds pilot byte limit')
        # At most one text token per UTF-8 byte, plus ample protocol allowance.
        bound = size + 4096
        cost = self.cost(provider, bound, MAX_OUTPUT)
        if len(self.entries) >= self.max_requests or self.charged + cost > self.limit:
            self.stop('pilot request or estimated cost limit reached')
        row = {'provider': provider, 'model': model, 'status': 'pending',
               'input_token_bound': bound, 'reserved_microdollars': cost,
               'accounted_microdollars': cost, 'usage': None}
        self.entries.append(row)
        self.checkpoint()
        return row

    @staticmethod
    def cost(provider, inputs, outputs):
        inp, out = RATES[provider]
        return int((inp * inputs + out * outputs).to_integral_value(rounding=ROUND_CEILING))

    def settle(self, row, inputs, outputs):
        if any(type(v) is not int or v < 0 for v in (inputs, outputs)):
            raise AdapterError('missing or invalid provider token usage')
        row['usage'] = {'input_tokens': inputs, 'output_tokens': outputs}
        if inputs > row['input_token_bound'] or outputs > MAX_OUTPUT:
            row['accounted_microdollars'] = max(row['reserved_microdollars'], self.cost(row['provider'], inputs, outputs))
            raise AdapterError('provider usage exceeded reservation; stop pilot')
        row['accounted_microdollars'] = self.cost(row['provider'], inputs, outputs)
        row['status'] = 'received'
        self.checkpoint()

    def snapshot(self):
        return {'limit_microdollars': self.limit, 'accounted_microdollars': self.charged,
                'max_requests': self.max_requests, 'requests': self.entries, 'blocked': self.blocked,
                'rates_usd_per_million': {p: list(map(str, r)) for p, r in RATES.items()},
                'note': 'Conservative local estimate, not provider billing enforcement. Pending/unknown calls retain reservations.'}
