"""CueScore regions: several countries collected into one file by one workflow (added 13 Nov 2026).

CS_REGION (env) picks a region below; without it the collectors use the single country in CS_COUNTRY, as before.
'rest' = every CueScore country that is not in Europe (CueScore's own country list minus every European name here).
CS_DISCIPLINES (env, regex) limits which events are read; without it the old pool filter of each collector is used.
Aleksandrs 13 Nov 2026: new regions gather only 8-ball, 9-ball, 10-ball and straight pool (handicap events included, flagged).
"""
import os, re, time

# Collected elsewhere: one workflow per country / CueScore Nordic in this repo; Latvia, Lithuania, Estonia in the Latvian repo.
COLLECTED = ['Germany', 'Poland', 'Czech Republic', 'Netherlands', 'Belgium', 'Luxembourg', 'Austria', 'Switzerland',
             'Italy', 'France', 'Finland', 'Sweden', 'Denmark', 'Norway', 'Latvia', 'Lithuania', 'Estonia']
REGIONS = {
    'uk': ['United Kingdom', 'England', 'Scotland', 'Wales', 'Northern Ireland', 'Isle of Man', 'Jersey', 'Guernsey', 'Ireland'],
    'south': ['Spain', 'Catalonia', 'Portugal', 'Greece', 'Malta', 'Cyprus', 'Turkish North Cyprus', 'Gibraltar', 'Andorra',
              'San Marino', 'Monaco', 'Vatican'],
    'east': ['Bosnia and Herzegovina', 'Croatia', 'Slovenia', 'Montenegro', 'Serbia', 'North Macedonia', 'Albania', 'Kosovo',
             'Bulgaria', 'Romania', 'Moldova', 'Hungary', 'Slovakia', 'Ukraine', 'Belarus', 'Russia',
             # other European countries that fit no other group
             'Iceland', 'Faroe Islands', 'Liechtenstein', 'Aland Islands', 'Svalbard and Jan Mayen'],
}
API = 'https://api.cuescore.com'
REGION = os.environ.get('CS_REGION') or ''
DISC = re.compile(os.environ['CS_DISCIPLINES'], re.I) if os.environ.get('CS_DISCIPLINES') else None


def countries(get, default):
    if not REGION: return [os.environ.get('CS_COUNTRY') or default]
    if REGION == 'rest':
        europe = set(COLLECTED) | {c for v in REGIONS.values() for c in v}
        return sorted(i['name'] for i in get(f'{API}/countries/').json()['items'] if i['name'] not in europe)
    return REGIONS[REGION]


def label(default):
    """Lower-case name written into each tournament row when the event itself has no country."""
    return REGION or (os.environ.get('CS_COUNTRY') or default).lower()


def list_events(get, country, a, b):
    """Every event of one country between a and b (YYYY-MM-DD). One list query stops at about 9,900 results,
    so a range that comes close is split into months."""
    items, off = [], 0
    while True:
        j = get(f'{API}/tournaments/?country={country}&from={a}&to={b}&offset={off}').json()
        items += j['items']
        if not j.get('hasMore'): break
        off = j['nextOffset']; time.sleep(0.2)
    if len(items) < 9000 or a[:7] == b[:7] or a[:4] != b[:4]: return items
    import calendar
    y = int(a[:4]); out = []
    for m in range(int(a[5:7]), int(b[5:7]) + 1):
        out += list_events(get, country, f'{y}-{m:02d}-01', f'{y}-{m:02d}-{calendar.monthrange(y, m)[1]}')
    return out


def event_country(j, default):
    c = j.get('country')
    return ((c.get('name') if isinstance(c, dict) else c) or default).lower()
