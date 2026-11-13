"""bill4you.ru (pool section): Russian federation and club pool tournaments, also Belarus and nearby. Added 13 Nov 2026.

Manual workflow only (Aleksandrs 13 Nov 2026: gather and keep available, no nightly run).
robots.txt: Crawl-delay 1 for normal agents; only login, signup and grid downloads are disallowed (not used here).
  /bff/pool/tournaments?...&status=finished&page=N&per_page=50   list (JSON): id, title, date, country, city, format
  /pool/tournament/<id>/view-grid                                 bracket (HTML): every match with both player ids
                                                                  (data-id), flag, name, score, table, time, round, race (BO n)
The game is taken from the title (пул 9 / 8 / 10, 14+1); "Дуплеты" and pyramid variants are skipped (only 8/9/10-ball and
straight pool are gathered). "С форой" (handicap) events are kept and flagged. Group stages are not read yet.

Output data/bill4you_raw.json.gz:
  tournaments: [id, title, date, country, city, format, game guess, handicap 1/0, matches stored]
  matches:     [tournament id, match id, number, round, best of, player A id, player B id, score A, score B, table, time]
  players:     {id: [name "Surname Firstname", flag]}
  done: tournaments read; skipped: other games, teams or doubles
"""
import json, gzip, os, re, sys, time, html
import requests

FILE = 'data/bill4you_raw.json.gz'
BASE = 'https://bill4you.ru'
DELAY = 1.5
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (pool rating collector; github.com/fscign/pool-data)', 'Accept-Language': 'ru'})
D = json.load(gzip.open(FILE, 'rt', encoding='utf-8')) if os.path.exists(FILE) else \
    {'tournaments': [], 'matches': [], 'players': {}, 'done': [], 'skipped': []}
done, skipped = set(D['done']), set(D['skipped'])


def get(path, as_json=False):
    for i in range(4):
        try:
            time.sleep(DELAY)
            r = S.get(BASE + path, timeout=60); r.raise_for_status(); r.encoding = 'utf-8'
            return r.json() if as_json else r.text
        except Exception:
            if i == 3: raise
            time.sleep(5 * (i + 1))


def plain(s): return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def game(title):
    t = title.lower().replace('«', '"').replace('»', '"')
    if re.search(r'дуплет|пирамид|снукер|комбинир|ротаци|one\s*pocket|ван.?покет|банк|блэкбол|blackball', t): return 'skip'
    if re.search(r'14\s*\+\s*1|14\.1|стрейт|straight', t): return 'straight'
    if re.search(r'10\b|"10"|десят', t): return '10-ball'
    if re.search(r'\b9\b|"9"|девят', t): return '9-ball'
    if re.search(r'\b8\b|"8"|восьм', t): return '8-ball'
    return ''


def listing(max_pages):
    out, page, last = [], 1, 1
    while page <= min(last, max_pages):
        j = get(f'/bff/pool/tournaments?title&countryId&cityId&organizerId&status=finished&dateFrom&dateTo&rating=false&page={page}&per_page=50', True)
        out += [x for x in j.get('items', []) if x.get('tournamentId')]
        last = (j.get('_meta') or {}).get('pageCount') or 1
        page += 1
    return out


def grid(tid):
    h = get(f'/pool/tournament/{tid}/view-grid')
    out, prev = [], 0
    rnd, bo = '', 0
    for m in re.finditer(r'<div class="match-item__wrapper" id="tournament-match-(\d+)">(.*?)<div class="match-item__info-footer">(.*?)</div>', h, re.S):
        head = plain(h[prev:m.start()]); prev = m.end()
        hm = list(re.finditer(r'(ТУР\s*\d+|ФИНАЛ\w*|ПОЛУФИНАЛ\w*|ЧЕТВЕРТЬФИНАЛ\w*)?\s*BO\s*(\d+)\s*([А-ЯЁ ]*СЕТКА)?', head))
        if hm: rnd = ' '.join(x for x in (hm[-1].group(1), hm[-1].group(3)) if x).strip(); bo = int(hm[-1].group(2))
        body = m.group(2)
        parts = re.findall(r'data-id="(\d+)">(.*?)</a>\s*<div class="participant__score[^"]*">\s*([^<]*?)\s*</div>', body, re.S)
        if len(parts) != 2: continue
        sc = [p[2] for p in parts]
        if not all(s.isdigit() for s in sc): continue
        num = re.search(r'match-item__number">\s*#?(\d+)', body); tab = re.search(r'table-name">\s*([^<]*?)\s*<', body)
        tm = re.search(r'info-header__date">\s*([^<]*?)\s*<', body)
        for pid, inner, _ in parts:
            if pid not in D['players']:
                fl = re.search(r'flags/flat/ico/(\w+)\.ico', inner)
                D['players'][pid] = [plain(re.sub(r'<img[^>]*>', '', inner)), fl.group(1) if fl else '']
        out.append([tid, int(m.group(1)), int(num.group(1)) if num else 0, rnd, bo, int(parts[0][0]), int(parts[1][0]),
                    int(sc[0]), int(sc[1]), tab.group(1) if tab else '', tm.group(1) if tm else ''])
    return out


def main():
    full = '--all' in sys.argv or not D['tournaments']
    stop_at = time.time() + (float(sys.argv[sys.argv.index('--minutes') + 1]) if '--minutes' in sys.argv else 90) * 60
    items = listing(999 if full else 3)
    todo = [x for x in items if x['tournamentId'] not in done and x['tournamentId'] not in skipped]
    print(f'bill4you: {len(items)} finished tournaments listed, {len(todo)} to read', flush=True)
    new = 0
    for x in todo:
        if time.time() > stop_at: print('time budget used, continuing next run', flush=True); break
        tid = x['tournamentId']; title = x.get('title') or ''
        g = game(title)
        if g == 'skip' or x.get('tournamentType') not in ('players', None) or (x.get('formatText') or '1 x 1') != '1 x 1':
            skipped.add(tid); continue
        try: ms = grid(tid)
        except Exception as e: print('  could not read', tid, e, flush=True); continue
        hcp = 1 if re.search(r'фор[аоуы]|гандикап|handicap', title, re.I) else 0
        D['tournaments'].append([tid, title, (x.get('date') or '')[:10], x.get('region') or '', x.get('city') or '',
                                 x.get('formatText') or '', g, hcp, len(ms)])
        D['matches'] += ms; done.add(tid); new += 1
        if new % 50 == 0: save(); print(f'  {new} read', flush=True)
    save()
    print(f'bill4you: {new} new tournaments; total {len(D["tournaments"])} tournaments, {len(D["matches"])} matches, '
          f'{len(D["players"])} players, {len(skipped)} skipped', flush=True)


def save():
    D['done'], D['skipped'] = sorted(done), sorted(skipped)
    os.makedirs('data', exist_ok=True)
    with gzip.open(FILE + '.tmp', 'wt', encoding='utf-8') as f: json.dump(D, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(FILE + '.tmp', FILE)


if __name__ == '__main__':
    main()
