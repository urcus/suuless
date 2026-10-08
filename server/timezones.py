"""Geographical picker from IANA data; legacy identifiers remain readable.

Use the same bundled tzdata for the catalog, aliases and conversions so host
OS updates cannot make these three disagree. Never deduplicate by UTC offset.
"""
from datetime import datetime, timezone
from functools import lru_cache
from importlib.resources import files
import unicodedata
from zoneinfo import ZoneInfo

from babel import Locale
from babel.dates import get_timezone_location
import tzdata

DATA = files('tzdata.zoneinfo')
VALID_TIMEZONES = frozenset(files('tzdata').joinpath('zones').read_text().splitlines()) - {'localtime'}
REGIONS = {}
for line in DATA.joinpath('zone1970.tab').read_text().splitlines():
    if line and not line.startswith('#'):
        countries, _, identifier, *_ = line.split('\t')
        REGIONS[identifier] = countries.split(',')
REGIONS['UTC'] = []
TIMEZONES = sorted(REGIONS)

LINKS = {}
for line in DATA.joinpath('tzdata.zi').read_text().splitlines():
    fields = line.split()
    if fields and fields[0] == 'L':
        LINKS[fields[2]] = fields[1]


def canonical_timezone(identifier):
    """Return a picker representative if possible, without changing stored IDs."""
    current = identifier
    seen = set()
    while current in LINKS and current not in seen:
        seen.add(current)
        current = LINKS[current]
    if current in ('Etc/UTC', 'Etc/GMT'):
        return 'UTC'
    return current if current in REGIONS else None


ALIASES = {key: canonical_timezone(key) for key in sorted(VALID_TIMEZONES)
           if canonical_timezone(key) is not None and canonical_timezone(key) != key}


@lru_cache(maxsize=1024)
def get_zone(identifier):
    if identifier not in VALID_TIMEZONES:
        raise ValueError('Unknown IANA time zone')
    with DATA.joinpath(*identifier.split('/')).open('rb') as source:
        return ZoneInfo.from_file(source, key=identifier)


def search_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value).lower() if not unicodedata.combining(c))


@lru_cache(maxsize=2048)
def location(identifier, locale):
    if identifier == 'UTC':
        return 'UTC'
    return get_timezone_location(get_zone(identifier), locale=locale, return_city=True)


@lru_cache(maxsize=2048)
def metadata(identifier, locale):
    representative = canonical_timezone(identifier)
    countries = REGIONS.get(representative, [])
    names = [str(Locale.parse(locale).territories.get(code, code)) for code in countries]
    city = location(identifier, locale)
    aliases = [key for key, target in ALIASES.items() if target == identifier]
    terms = [identifier, city, *countries, *names, *aliases]
    for language in ('en', 'fr', 'ja'):
        terms.extend(str(Locale.parse(language).territories.get(code, code)) for code in countries)
        terms.append(location(identifier, language))
        terms.extend(location(alias, language) for alias in aliases if '/' in alias)
    return dict(id=identifier, city=city, countries=names, country_codes=countries,
                search=search_key(' '.join(terms)), legacy=identifier not in REGIONS)


def timezone_info(identifier, locale, instant=None):
    instant = instant or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError('An absolute instant is required')
    info = metadata(identifier, locale)
    seconds = int(instant.astimezone(get_zone(identifier)).utcoffset().total_seconds())
    hours, minutes = divmod(abs(seconds) // 60, 60)
    offset = f"UTC{'+' if seconds >= 0 else '-'}{hours:02d}:{minutes:02d}"
    place = info['city']
    if info['countries']:
        place += ' — ' + info['countries'][0]
    return dict(info, offset_seconds=seconds, utc_offset=offset,
                label=f"{place} ({offset}) · {identifier}")


def timezone_catalog(locale, instant):
    return [timezone_info(key, locale, instant) for key in TIMEZONES]


TZDATA_VERSION = tzdata.IANA_VERSION
