"""Turkish Billiards Federation pool portal (portal.bilardo.gov.tr): merge results read in a browser. Added 13 Nov 2026.

The portal refuses GitHub's servers (403), so it is read once a month in the built-in browser on Aleksandrs's PC
(tbf_browser.js, scheduled task "TBF Turkey monthly"). This script decides which ids to read and merges the results
into data/tbf_raw.json.gz, which is committed to the repo; the TBF Turkey workflow then copies it to the release.

  python3 tbf_merge.py --todo          ids to read: every id not finished yet, up to 60 past the last real one
  python3 tbf_merge.py results.json    merge (a JSON array from tbfChunk, chunks joined in order)
  python3 tbf_merge.py --sum chunk.json length and checksum, must equal tbfSum(i, size) in the browser

Events: national stages, provincial championships, women, seniors, youth, school and university events, 2012 on.
The game is in the name (8 TOP, 9 TOP, 10 TOP, 14+1); snooker and carom are skipped (only 8/9/10-ball and straight
pool are gathered). School and university events often name no game: kept with ''. Youth events often play sets:
"(n)" is then probably the number of sets, not the race; kept raw.

data/tbf_raw.json.gz:
  tournaments: [id, name, first date, last date, category, venue, format, game guess, matches stored]
  matches:     [tournament id, match code, round, player A id, player B id, score A, score B, race, status]
  players:     {id: full name}
  done: finished tournaments older than 30 days; empty: ids with no tournament; skipped: not pool; max_id
"""
import json, gzip, os, re, sys, datetime

FILE = 'data/tbf_raw.json.gz'
LOOKAHEAD = 60
TODAY = datetime.date.today()
MON = {m: i for i, m in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}

D = json.load(gzip.open(FILE, 'rt', encoding='utf-8')) if os.path.exists(FILE) else \
    {'tournaments': [], 'matches': [], 'players': {}, 'done': [], 'empty': [], 'skipped': [], 'max_id': 0}
done, empty, skipped = set(D['done']), set(D['empty']), set(D['skipped'])


def day(s):
    m = re.match(r'(\d\d)\.(\w{3})\.(\d{4})', (s or '').strip())
    return f'{m.group(3)}-{MON[m.group(2)]:02d}-{m.group(1)}' if m and m.group(2) in MON else ''


def game(name):
    n = name.upper().replace('İ', 'I')
    if re.search(r'SNOOKER|BANT|KARAMBOL|CAROM|PIRAMIT', n): return 'skip'
    if re.search(r'14\s*\+\s*1|14\.1|STRAIGHT', n): return 'straight'
    if re.search(r'\b10\s*TOP|\b10\s*BALL', n): return '10-ball'
    if re.search(r'\b9\s*TOP|\b9\s*BALL', n): return '9-ball'
    if re.search(r'\b8\s*TOP|\b8\s*BALL', n): return '8-ball'
    return ''


def todo():
    top = D['max_id'] + LOOKAHEAD if D['max_id'] else 1300
    return [i for i in range(1, top + 1) if i not in done and i not in skipped and not (i in empty and i < D['max_id'])]


def merge(results):
    have = {t[0]: k for k, t in enumerate(D['tournaments'])}
    new = upd = 0
    for r in sorted(results, key=lambda x: x['id']):
        if r.get('error'): continue                     # page could not be read: tried again next run
        tid, p = r['id'], r['p']
        if not p:
            empty.add(tid); continue
        empty.discard(tid); D['max_id'] = max(D['max_id'], tid)
        g = game(p[0])
        if g == 'skip': skipped.add(tid); continue
        ms = []
        for k, v in (r.get('n') or {}).items(): D['players'].setdefault(str(k), v)
        for code, rnd, a, sa, race, sb, b, st in r['m']:
            ms.append([tid, code, rnd, a, b, sa, sb, int(race) if str(race).isdigit() else race, st])
        t = [tid, p[0], day(p[1]), day(p[2]), p[3], p[4], p[5], g, len(ms)]
        if tid in have:
            D['matches'] = [m for m in D['matches'] if m[0] != tid] + ms; D['tournaments'][have[tid]] = t; upd += 1
        else:
            D['matches'] += ms; have[tid] = len(D['tournaments']); D['tournaments'].append(t); new += 1
        last = t[3] or t[2]
        if last and (TODAY - datetime.date.fromisoformat(last)).days > 30: done.add(tid)
    D['done'], D['empty'], D['skipped'] = sorted(done), sorted(empty), sorted(skipped)
    D['updated'] = TODAY.isoformat()
    os.makedirs('data', exist_ok=True)
    with gzip.open(FILE, 'wt', encoding='utf-8') as f: json.dump(D, f, ensure_ascii=False, separators=(',', ':'))
    print(f'TBF portal: {len(results)} ids read, {new} new tournaments, {upd} re-read; total {len(D["tournaments"])} tournaments, '
          f'{len(D["matches"])} matches, {len(D["players"])} players, last id {D["max_id"]}')


if __name__ == '__main__':
    if '--todo' in sys.argv: print(json.dumps(todo()))
    elif '--sum' in sys.argv:   # same checksum as tbfSum in tbf_browser.js, to check a chunk copied out of the browser
        t = open(sys.argv[-1], encoding='utf-8').read().strip()
        print(len(t), sum(ord(c) if ord(c) < 0x10000 else 0 for c in t) % 1000000007)
    else: merge([r for f in sys.argv[1:] for r in json.load(open(f, encoding='utf-8'))])   # one or more chunk files, in order
