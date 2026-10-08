"""Shared translations, currency metadata and explicit monetary precision."""
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from .timezones import TIMEZONES

from babel import Locale
from babel.numbers import get_currency_name, get_currency_precision, get_territory_currencies
from flask import g, request

LANGUAGES = {'en': 'English', 'fr': 'Français', 'ja': '日本語'}
TRANSLATIONS = {code: json.loads((Path(__file__).parent / 'static' / 'locales' / f'{code}.json').read_text()) for code in LANGUAGES}
# CLDR tender currencies in use today, not obsolete currency codes.
CURRENCIES = sorted({code for territory in Locale('en').territories
                     for code in get_territory_currencies(territory)})


def language():
    if getattr(g, 'user', None) is not None:
        return g.user['language']
    return request.accept_languages.best_match(list(LANGUAGES), default='en')


def translate(key, *args):
    text = TRANSLATIONS[language()].get(key, TRANSLATIONS['en'].get(key, key))
    for index, value in enumerate(args):
        text = text.replace('{' + str(index) + '}', str(value))
    return text


@lru_cache(maxsize=3)
def currency_catalog(locale):
    return [dict(code=code, name=get_currency_name(code, locale=locale), digits=get_currency_precision(code)) for code in CURRENCIES]


def price_micros(value, currency):
    """Reject precision loss instead of silently rounding a user's pack price."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError()
    try:
        amount = Decimal(str(value))
        step = Decimal(1).scaleb(-get_currency_precision(currency))
        if not amount.is_finite() or not 0 <= amount <= 1_000_000 or amount != amount.quantize(step):
            raise ValueError()
        return int(amount * 1_000_000)
    except InvalidOperation as exc:
        raise ValueError() from exc


def money(micros, currency):
    return float((Decimal(micros) / 1_000_000).quantize(Decimal(1).scaleb(-get_currency_precision(currency)), rounding=ROUND_HALF_UP))


def price_string(micros, currency):
    amount = (Decimal(micros) / 1_000_000).quantize(Decimal(1).scaleb(-get_currency_precision(currency)), rounding=ROUND_HALF_UP)
    return f'{amount:.{get_currency_precision(currency)}f}'


def cost_summary(amounts, default_currency):
    """Never add unlike currencies. Legacy scalar is null for mixed totals."""
    costs = {code: money(amount, code) for code, amount in sorted(amounts.items())} or {default_currency: 0.0}
    sole = next(iter(costs)) if len(costs) == 1 else None
    return dict(costs=costs, currency=sole, cost=costs[sole] if sole else None)
