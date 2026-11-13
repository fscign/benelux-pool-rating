"""Turkish Billiards Federation pool portal (portal.bilardo.gov.tr, BilliardPort software). Added 13 Nov 2026.

National stages (T.B.F. etap), provincial championships (il birinciliği / il şampiyonası), youth, women, seniors,
school and university events, 2012 to now. Tournament ids run from 1 to about 1,200 (sparse below about 480).
robots.txt only blocks three SEO crawlers. Pages are plain server HTML:
  page_tour_profile?tour=n   name, dates, category, venue, format
  page_tour_matches?tour=n   every match: round, match code, both player ids (fncViewMatchesClick), score, race "(n)"
The game is in the name (8 TOP, 9 TOP, 10 TOP, 14+1); events named snooker are skipped (Aleksandrs 13 Nov 2026:
gather only 8-ball, 9-ball, 10-ball and straight pool). School and university events often name no game: kept with ''.
Youth events often play sets: the "(n)" then is probably the number of sets, not the race; kept raw.

Output data/tbf_raw.json.gz:
  tournaments: [id, name, first date, last date, category, venue, format, game guess, matches stored]
  matches:     [tournament id, match code, round, player A id, player B id, score A, score B, race, status]
  players:     {id: name}
  done: finished tournaments older than 30 days; empty: ids with no tournament; skipped: not pool; max_id
"""
import json, gzip, os, re, sys, time, datetime, html
import requests

FILE = 'data/tbf_raw.json.gz'
BASE = 'https://portal.bilardo.gov.tr'
DELAY = 1.0
LOOKAHEAD = 60
TODAY = datetime.date.today()
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (pool rating collector; github.com/fscign/pool-data)'})
MON = {m: i for i, m in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}

D = json.load(gzip.open(FILE, 'rt', encoding='utf-8')) if os.path.exists(FILE) else \
    {'tournaments': [], 'matches': [], 'players': {}, 'done': [], 'empty': [], 'skipped': [], 'max_id': 0}
VERSION = 1   # raise when the parser changes: every stored tournament is then read again
if D.get('version') != VERSION: D['done'] = []; D['version'] = VERSION
done, empty, skipped = set(D['done']), set(D['empty']), set(D['skipped'])


def save():
    D['done'], D['empty'], D['skipped'] = sorted(done), sorted(empty), sorted(skipped)
    with gzip.open(FILE + '.tmp', 'wt', encoding='utf-8') as f: json.dump(D, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(FILE + '.tmp', FILE)


def get(path):
    for i in range(4):
        try:
            r = S.get(f'{BASE}/{path}', timeout=60); r.raise_for_status(); r.encoding = 'utf-8'
            time.sleep(DELAY); return r.text
        except Exception:
            if i == 3: raise
            time.sleep(5 * (i + 1))


def plain(s): return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def day(s):
    m = re.match(r'(\d\d)\.(\w{3})\.(\d{4})', s.strip())
    return f'{m.group(3)}-{MON.get(m.group(2), 1):02d}-{m.group(1)}' if m and m.group(2) in MON else ''


def game(name):
    n = name.upper().replace('İ', 'I')
    if re.search(r'SNOOKER|BANT|KARAMBOL|CAROM|PIRAMIT', n): return 'skip'
    if re.search(r'14\s*\+\s*1|14\.1|STRAIGHT', n): return 'straight'
    if re.search(r'\b10\s*TOP|\b10\s*BALL', n): return '10-ball'
    if re.search(r'\b9\s*TOP|\b9\s*BALL', n): return '9-ball'
    if re.search(r'\b8\s*TOP|\b8\s*BALL', n): return '8-ball'
    return ''


def profile(tid):
    s = plain(re.sub(r'<script[\s\S]*?</script>', ' ', get(f'page_tour_profile?tour={tid}')))
    m = re.search(r'Name: (.*?) Dates: (.*?) - (.*?) Category: (.*?) Location: (.*?) Format: (\S*)', s)
    if not m or not m.group(1).strip(): return None
    return [tid, m.group(1).strip(), day(m.group(2)), day(m.group(3)), m.group(4).strip(), m.group(5).strip(' ,'), m.group(6)]


def matches(tid):
    h = get(f'page_tour_matches?tour={tid}')
    heads = [(mm.start(), plain(mm.group(1))) for mm in re.finditer(r'<th[^>]*class="groupHeader"[^>]*>(.*?)</th>', h, re.S)]
    out = []
    for mm in re.finditer(r'<tr[^>]*>((?:(?!</tr>).)*?date-box.*?)</tr>', h, re.S):
        row = mm.group(1)
        cells = re.split(r'<td\b', row)[1:]
        ids = re.findall(r'fncViewMatchesClick\((\d+)\)', row)
        if len(cells) < 7 or len(ids) < 2 or '0' in ids[:2]: continue      # byes
        ct = [plain('<td' + c) for c in cells]
        try: sa, sb = int(ct[3]), int(ct[5])
        except ValueError: continue
        if sa == 0 and sb == 0: continue                                  # not played
        code = re.match(r'\s*([A-Z]?\d+)', re.sub(r'<span.*', '', cells[0].split('>', 1)[1], flags=re.S))
        rnd = ''
        for pos, name in heads:
            if pos < mm.start(): rnd = name
            else: break
        a, b = ids[0], ids[1]
        D['players'].setdefault(a, ct[2]); D['players'].setdefault(b, ct[6])
        race = re.sub(r'[()]', '', ct[4])
        out.append([tid, code.group(1) if code else '', rnd, int(a), int(b), sa, sb, int(race) if race.isdigit() else race,
                    ct[8] if len(ct) > 8 else ''])
    return out


def main():
    stop_at = time.time() + (float(sys.argv[sys.argv.index('--minutes') + 1]) if '--minutes' in sys.argv else 90) * 60
    have = {t[0]: i for i, t in enumerate(D['tournaments'])}
    tid, misses, n, new, upd = 0, 0, 0, 0, 0
    while misses < LOOKAHEAD:
        tid += 1
        if tid in done or tid in skipped or (tid in empty and tid < D['max_id'] - LOOKAHEAD): continue
        if time.time() > stop_at: print('time budget used, continuing next run', flush=True); break
        p = profile(tid); n += 1
        if p is None:
            empty.add(tid)
            if tid > D['max_id']: misses += 1
            continue
        misses = 0; empty.discard(tid); D['max_id'] = max(D['max_id'], tid)
        g = game(p[1])
        if g == 'skip': skipped.add(tid); continue
        ms = matches(tid)
        t = p + [g, len(ms)]
        if tid in have:
            D['matches'] = [m for m in D['matches'] if m[0] != tid] + ms; D['tournaments'][have[tid]] = t; upd += 1
        else:
            D['matches'] += ms; have[tid] = len(D['tournaments']); D['tournaments'].append(t); new += 1
        last = p[3] or p[2]
        if last and (TODAY - datetime.date.fromisoformat(last)).days > 30: done.add(tid)
        if n % 50 == 0:
            save(); print(f'  id {tid}: {len(D["tournaments"])} tournaments, {len(D["matches"])} matches', flush=True)
    save()
    print(f'TBF portal: {n} ids read, {new} new tournaments, {upd} re-read; total {len(D["tournaments"])} tournaments, '
          f'{len(D["matches"])} matches, {len(D["players"])} players, last id {D["max_id"]}', flush=True)


if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    main()
