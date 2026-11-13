"""ÖPBV (Austrian pool federation, oepbv.at): every tournament result since 2019. Added 13 Nov 2026.

The ÖPBV site runs TournamentApp (same maker as tournamentapp.de) but in another layout:
  ergebnisse.php?art=&typ=&bla=&mnt1=&mnt2=<year>&seite_nr=<n>   list: date, id, name, place, discipline icon
  ergebnisse.php?...&id=<id>                                       the tournament's parts (tabID): startliste / spielfeld
  turnier/php_public/startliste.php?tID=&tabID=                    start list: licence number, "Surname Firstname", flag, club
  turnier/php_public/spielfeld_iframe.php?tID=&tabID=&rub=list     every match: code, time, both names, score, status
Match rows give names only ("Firstname Surname"); they are tied to licence numbers through the start list of the same
event. Doubles (names with "/") are stored with id 0 and flagged, not used. Everything else is stored; the build decides.

Output data/oepbv_raw.json.gz:
  tournaments: [id, name, date dd.mm.yyyy, place, discipline ('8', '9', '10', '8910' multiball, '14' straight, ...), parts]
  matches:     [tournament id, tab id, part name, match code, match id, licence A, licence B, name A, name B,
                score A, score B, time 'dd.mm. hh:mm', finished 1/0, doubles 1/0]
  players:     {licence: [name "Surname Firstname", flag, club]}
First run reads every year since 2019; later runs re-read the current and previous year's list and read tournaments
that are new, less than 60 days old, or still have unfinished matches.
"""
import json, gzip, os, re, sys, time, datetime, html
import requests

FILE = 'data/oepbv_raw.json.gz'
BASE = 'https://www.oepbv.at/'
FIRST_YEAR = 2019
DAYS = 60
DELAY = 0.5
TODAY = datetime.date.today()
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (pool rating collector; github.com/fscign/pool-data)', 'Accept-Language': 'de-AT,de;q=0.9'})

D = json.load(gzip.open(FILE, 'rt', encoding='utf-8')) if os.path.exists(FILE) else {'tournaments': [], 'matches': [], 'players': {}}
VERSION = 2   # raise when reading changes: everything is read again (v1 of 13 Nov 2026 opened tournaments without year/page: no parts)
if D.get('version') != VERSION: D = {'tournaments': [], 'matches': [], 'players': D.get('players', {}), 'version': VERSION}


def get(path):
    for i in range(4):
        try:
            r = S.get(BASE + path, timeout=60); r.raise_for_status(); r.encoding = 'utf-8'
            time.sleep(DELAY); return r.text
        except Exception:
            if i == 3: raise
            time.sleep(5 * (i + 1))


def plain(s): return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()
def key(name): return ' '.join(sorted(plain(name).lower().replace('-', ' ').split()))


def year_list(y):
    out, n = [], 1
    while True:
        h = get(f'ergebnisse.php?art=&typ=&bla=&mnt1=&mnt2={y}&seite_nr={n}')
        rows = re.findall(r"<tr id=.kal_\d+.><td[^>]*>([^<]*)</td>(.*?)</tr>", h, re.S)
        got = 0
        for date, rest in rows:
            m = re.search(r"iframe_kalender_info\.php\?id=(\d+)['\"][^>]*>([^<]*)<", rest)
            if not m: continue
            place = re.search(r"iframe_spielort_kalender[^>]*>([^<]*)<", rest)
            disc = re.search(r"kugeln/(\w+)\.png", rest)
            out.append(dict(id=int(m.group(1)), name=plain(m.group(2)), date=plain(date),
                            place=plain(place.group(1)) if place else '', disc=disc.group(1) if disc else '',
                            done='fa-check-circle' in rest, y=y, n=n)); got += 1
        if not got or f'seite_nr={n + 1}' not in h: break
        n += 1
    return out


def startlist(tid, tab):
    h = get(f'turnier/php_public/startliste.php?tID={tid}&tabID={tab}')
    out = {}
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', h, re.S):
        c = [plain(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
        fl = re.search(r'flaggen/(\w+)\.jpg', row)
        if len(c) >= 4 and c[1].isdigit() and c[2]:
            out[c[1]] = [c[2], fl.group(1) if fl else '', c[4] if len(c) > 4 else '']
    return out


def results(tid, tab):
    h = get(f'turnier/php_public/spielfeld_iframe.php?tID={tid}&tabID={tab}&rub=list&scroll=&akt=aus')
    heads = [(m.start(), plain(m.group(1))) for m in re.finditer(r'<td[^>]*colspan[^>]*>(.*?)</td>', h, re.S) if plain(m.group(1)) and plain(m.group(1)) != 'ALLE PARTIEN']
    out = []
    for m in re.finditer(r'<tr class="f-w-700">(.*?)</tr>', h, re.S):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', m.group(1), re.S)
        if len(cells) < 9: continue
        mid = re.search(r'[?&]id=(\d+)', cells[0])
        sc = re.match(r'(\d+)\s*-\s*(\d+)', plain(cells[6]))
        if not sc: continue
        na = plain(re.sub(r'<span.*', '', cells[4], flags=re.S)); nb = plain(re.sub(r'<span.*', '', cells[8], flags=re.S))
        part = ''
        for pos, name in heads:
            if pos < m.start(): part = name
            else: break
        out.append(dict(code=plain(cells[0]), mid=int(mid.group(1)) if mid else 0, time=plain(cells[3]), a=na, b=nb,
                        sa=int(sc.group(1)), sb=int(sc.group(2)), fin=1 if 'fa-check-circle' in cells[1] else 0,
                        dbl=1 if '/' in na or '/' in nb else 0, part=part))
    return out


def read(t):
    h = get(f"ergebnisse.php?art=&typ=&bla=&mnt1=&mnt2={t['y']}&seite_nr={t['n']}&id={t['id']}")   # opens only with its list year and page
    tabs = list(dict.fromkeys(re.findall(r'spielfeld\.php\?tID=\d+&(?:amp;)?tabID=(\d+)', h)))
    ms, players = [], {}
    for tab in tabs:
        sl = startlist(t['id'], tab)
        players.update(sl)
        by = {key(v[0]): k for k, v in sl.items()}
        for r in results(t['id'], tab):
            la = 0 if r['dbl'] else int(by.get(key(r['a']), 0)); lb = 0 if r['dbl'] else int(by.get(key(r['b']), 0))
            ms.append([t['id'], int(tab), r['part'], r['code'], r['mid'], la, lb, r['a'], r['b'], r['sa'], r['sb'], r['time'], r['fin'], r['dbl']])
    return tabs, ms, players


def main():
    have = {x[0]: i for i, x in enumerate(D['tournaments'])}
    years = range(FIRST_YEAR, TODAY.year + 1) if not have else range(TODAY.year - 1, TODAY.year + 1)
    listed = []
    for y in years: listed += year_list(y)
    open_t = {m[0] for m in D['matches'] if not m[12]}
    cut = TODAY - datetime.timedelta(days=DAYS)
    todo = []
    for t in listed:
        dm = re.search(r'(\d\d)\.(\d\d)\.(\d{4})\s*$', t['date'])
        d = datetime.date(int(dm.group(3)), int(dm.group(2)), int(dm.group(1))) if dm else TODAY
        if d > TODAY: continue
        if t['id'] not in have or d >= cut or (t['id'] in open_t and d >= TODAY - datetime.timedelta(days=180)): todo.append(t)
    print(f'ÖPBV: {len(listed)} tournaments listed, {len(todo)} to read', flush=True)
    new = upd = 0
    for k, t in enumerate(todo):
        try: tabs, ms, pl = read(t)
        except Exception as e: print('  could not read', t['id'], e, flush=True); continue
        row = [t['id'], t['name'], t['date'], t['place'], t['disc'], len(tabs)]
        D['matches'] = [m for m in D['matches'] if m[0] != t['id']] + ms
        if t['id'] in have: D['tournaments'][have[t['id']]] = row; upd += 1
        else: have[t['id']] = len(D['tournaments']); D['tournaments'].append(row); new += 1
        for lic, v in pl.items(): D['players'][lic] = v
        if (k + 1) % 50 == 0:
            save(); print(f'  {k + 1}/{len(todo)}', flush=True)
    save()
    print(f'ÖPBV: {new} new tournaments, {upd} re-read; total {len(D["tournaments"])} tournaments, {len(D["matches"])} matches, '
          f'{sum(1 for m in D["matches"] if not m[13] and m[5] and m[6])} singles with both licences, {len(D["players"])} players', flush=True)


def save():
    os.makedirs('data', exist_ok=True)
    with gzip.open(FILE + '.tmp', 'wt', encoding='utf-8') as f: json.dump(D, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(FILE + '.tmp', FILE)


if __name__ == '__main__':
    main()
