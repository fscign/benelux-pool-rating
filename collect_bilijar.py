"""bilijar.club: Serbian pool tournaments (also some clubs in Croatia, Bosnia, Montenegro, North Macedonia). Added 13 Nov 2026.

Every tournament page (tournament.php?ID=n, ids from 1 upward, no robots.txt on the site) is plain HTML with all matches:
round, date, both player ids, score, handicap spot "(a-b)" and table. Everything is stored (gather first, decide later);
the site gives no discipline field, so the game is guessed from the title (mostly 9-ball) and the raw title is kept.
Handicap events are flagged, not dropped.

Output data/bilijar_raw.json.gz:
  tournaments: [id, title, date, scheme, category, players entered, 'Singl'/'Parovi', status, club, club id,
                description, handicap 1/0, game guess ('8-ball', '9-ball', '10-ball', 'straight', '')]
  matches:     [tournament id, match no, round, player A id, player B id, score A, score B, handicap spot, date, table]
  players:     {id: [name as shown ("Surname Firstname"), flag code]}
  done: finished tournaments older than 30 days (never read again); empty: ids with no tournament; max_id
First run reads every id (about 5,800 pages, saved every 100 pages, so a run cut off by the time limit continues).
Later runs read new ids and tournaments that are not finished or are less than 30 days old.
"""
import json, gzip, os, re, sys, time, datetime
import requests
from bs4 import BeautifulSoup

FILE = 'data/bilijar_raw.json.gz'
BASE = 'https://bilijar.club'
DELAY = 0.7
LOOKAHEAD = 80   # empty ids in a row after the last real one before the scan stops
TODAY = datetime.date.today()
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (pool rating collector; contact via github.com/fscign/pool-data)'})

D = json.load(gzip.open(FILE, 'rt', encoding='utf-8')) if os.path.exists(FILE) else \
    {'tournaments': [], 'matches': [], 'players': {}, 'done': [], 'empty': [], 'max_id': 0}
done, empty = set(D['done']), set(D['empty'])


def save():
    D['done'], D['empty'] = sorted(done), sorted(empty)
    with gzip.open(FILE + '.tmp', 'wt', encoding='utf-8') as f: json.dump(D, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(FILE + '.tmp', FILE)


def get(url):
    for i in range(4):
        try:
            r = S.get(url, timeout=60); r.raise_for_status(); r.encoding = 'utf-8'; return r.text
        except Exception:
            if i == 3: raise
            time.sleep(5 * (i + 1))


def txt(el): return re.sub(r'\s+', ' ', el.get_text(' ', strip=True)).strip() if el else ''


def game(title, desc):
    for s in (title, desc if not re.search(r'\d+\s*/\s*\d+', desc or '') else ''):
        s = (s or '').lower()
        if re.search(r'\b10[- ]?ball|desetk|\b10ka\b', s): return '10-ball'
        if re.search(r'\b8[- ]?ball|osmic|\b8ka\b', s): return '8-ball'
        if re.search(r'\b9[- ]?ball|devetk|\b9ka\b', s): return '9-ball'
        if re.search(r'14\.1|straight|stret|kontinu', s): return 'straight'
    return ''


def parse(tid, h):
    soup = BeautifulSoup(h, 'lxml')
    info = soup.find('table', id='turnir')
    row = info.find_all('tr')[1].find_all('td') if info and len(info.find_all('tr')) > 1 else []
    vals = [txt(c) for c in row] + [''] * 7
    m = re.match(r'(\d\d)\.(\d\d)\.(\d{4})', vals[0])
    if not m or m.group(3) == '1970': return None
    tdate = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    h3 = soup.find('h3')
    desc_el = h3.find('i') if h3 else None
    desc = txt(desc_el)
    first = h3.find(string=True) if h3 else None
    title = re.sub(r'\s+', ' ', str(first)).strip() if first else ''
    if not title and soup.title and soup.title.string: title = soup.title.string.strip()
    club_a = soup.select_one('a[href^="club.php?ID="] h4')
    club = txt(club_a)
    cid = re.search(r'club\.php\?ID=(\d+)', h)
    matches, hcp = [], 0
    for lab in soup.select('div.toggle > label'):
        rnd = re.sub(r'\s*-\s*završeni mečevi.*|\s*-\s*.*mečevi.*', '', txt(lab)).strip()
        tab = lab.find_next_sibling('div')
        if not tab: continue
        for tr in tab.select('table[id^=mec] tbody tr'):
            ins = tr.find_all('input', attrs={'name': re.compile(r'^ID[12]')})
            tds = tr.find_all('td', recursive=False)
            if len(ins) < 2 or len(tds) < 10: continue           # byes (">>") and hidden detail rows
            a, b = ins[0]['value'], ins[1]['value']
            if a in ('', '0') or b in ('', '0'): continue
            try: sa, sb = int(txt(tds[4])), int(txt(tds[5]))
            except ValueError: continue                          # not played yet
            spot = txt(tds[6])
            if spot and spot not in ('(0-0)',): hcp = 1
            dm = re.match(r'(\d\d)\.(\d\d)\.', txt(tds[1]))
            md = ''
            if dm:
                y = tdate.year + (1 if int(dm.group(2)) < tdate.month - 6 else 0)
                md = f'{y}-{dm.group(2)}-{dm.group(1)}'
            for side, pid in ((tds[3], a), (tds[7], b)):
                if pid not in D['players']:
                    fl = tr.find('a', href=f'players.php?ID={pid}')
                    img = fl.find('img') if fl else None
                    flag = re.search(r'flags/(\w+)\.', img['src']).group(1) if img and img.get('src') else ''
                    D['players'][pid] = [txt(side), flag]
            matches.append([tid, txt(tds[0]), rnd, int(a), int(b), sa, sb, spot, md, txt(tds[9]).replace('#', '').strip()])
    if vals[2].startswith('4') or re.search(r'hendi|handi|hcp', title + ' ' + desc, re.I): hcp = 1
    t = [tid, title, tdate.isoformat(), vals[1], vals[2], vals[3], vals[4], vals[5], club, int(cid.group(1)) if cid else 0,
         desc, hcp, game(title, desc)]
    return t, matches, tdate


def main():
    mins = float(sys.argv[sys.argv.index('--minutes') + 1]) if '--minutes' in sys.argv else 90
    stop_at = time.time() + mins * 60   # stop cleanly before the workflow's time limit
    have = {t[0]: i for i, t in enumerate(D['tournaments'])}
    tid, misses, n, new, upd = 0, 0, 0, 0, 0
    while misses < LOOKAHEAD:
        tid += 1
        if tid in done or (tid in empty and tid < D['max_id'] - LOOKAHEAD):
            continue
        if time.time() > stop_at:
            print('time budget used, continuing next run', flush=True); break
        h = get(f'{BASE}/tournament.php?ID={tid}'); time.sleep(DELAY); n += 1
        r = parse(tid, h)
        if r is None:
            empty.add(tid)
            if tid > D['max_id']: misses += 1
        else:
            misses = 0; empty.discard(tid)
            D['max_id'] = max(D['max_id'], tid)
            t, ms, tdate = r
            D['matches'] = [m for m in D['matches'] if m[0] != tid] + ms if tid in have else D['matches'] + ms
            if tid in have: D['tournaments'][have[tid]] = t; upd += 1
            else: have[tid] = len(D['tournaments']); D['tournaments'].append(t); new += 1
            if t[7].startswith('Završen') and (TODAY - tdate).days > 30: done.add(tid)
        if n % 100 == 0:
            save(); print(f'  id {tid}: {len(D["tournaments"])} tournaments, {len(D["matches"])} matches', flush=True)
    save()
    print(f'bilijar.club: {n} pages read, {new} new tournaments, {upd} re-read; total {len(D["tournaments"])} tournaments, '
          f'{len(D["matches"])} matches, {len(D["players"])} players, last id {D["max_id"]}', flush=True)


if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    main()
