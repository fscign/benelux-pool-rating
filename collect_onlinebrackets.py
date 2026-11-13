"""online-brackets.com: pool tournaments (mostly Polish clubs and tours). Added 13 Nov 2026.

robots.txt allows everything for normal agents (Content-Signal: search=yes, ai-train=no, use=reference; this collector
only stores results for the rating database). The site's own public read API, no login:
  https://online-brackets.com/en/tournaments?discipline=12&page=N   list of pool tournaments (HTML, ids in /en/view/<id>)
  https://api.online-brackets.com/view/api/<id>                     tournament + players + matches (knock-out formats)
  https://api.online-brackets.com/view/api/<id>/group/<n>           round robin groups (format RR), rounds with matches
  https://api.online-brackets.com/view/api/<id>/details             description (only used for a handicap hint)
A round robin event may continue in a separate knock-out tournament (rrKnockoutId), which is read too.
PRIVACY: the player objects carry email and phone fields (seen empty). They are never stored: only id, name, surname,
country and the site user id are kept.
Only 8-ball, 9-ball, 10-ball and straight pool are gathered (category); doubles events are skipped.

Output data/onlinebrackets_raw.json.gz:
  tournaments: [id, name, category, format, state, start, end, organizer user id, handicap hint 1/0, parent id, matches stored]
  matches:     [tournament id, match id, player A id, player B id, score A, score B, race to, datetime, state,
                where (group n / side), forfeit A 1/0, forfeit B 1/0]
  players:     {id: [name, surname, country, site user id]}
  done: finished tournaments older than 30 days; skipped: other games or doubles
"""
import json, gzip, os, re, sys, time, datetime
import requests

FILE = 'data/onlinebrackets_raw.json.gz'
WEB = 'https://online-brackets.com'
API = 'https://api.online-brackets.com/view/api'
DELAY = 1.0
TODAY = datetime.date.today()
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (pool rating collector; github.com/fscign/pool-data)'})
WANTED = re.compile(r'^\s*(8|9|10)\s*-?\s*ball|straight|14\s*[.+]\s*1|^\s*1[04]-?1\b', re.I)
NOT_WANTED = re.compile(r'black\s*ball|snooker|heyball|chinese|carom|pyramid|one\s*pocket|bank|7\s*-?\s*ball|darts', re.I)

D = json.load(gzip.open(FILE, 'rt', encoding='utf-8')) if os.path.exists(FILE) else \
    {'tournaments': [], 'matches': [], 'players': {}, 'done': [], 'skipped': []}
done, skipped = set(D['done']), set(D['skipped'])


def get(url, as_json=True):
    for i in range(4):
        try:
            time.sleep(DELAY)
            r = S.get(url, timeout=60); r.raise_for_status()
            return r.json() if as_json else r.text
        except Exception:
            if i == 3: raise
            time.sleep(5 * (i + 1))


def list_ids():
    ids, n, last = [], 1, 1
    while n <= last:
        h = get(f'{WEB}/en/tournaments?discipline=12&page={n}', as_json=False)
        ids += [int(x) for x in re.findall(r'/en/view/(\d+)', h)]
        last = max([last] + [int(x) for x in re.findall(r'[?&]page=(\d+)', h)])
        n += 1
    return list(dict.fromkeys(ids))


def ddate(s):
    m = re.match(r'(\d\d)/(\d\d)/(\d{4})', s or '')
    return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def keep_player(p):
    if p and p.get('id') is not None:   # never email / phone
        D['players'][str(p['id'])] = [(p.get('name') or '').strip(), (p.get('surname') or '').strip(),
                                       (p.get('countryCode') or '').upper(), p.get('assignedUserId')]


def mrow(tid, m, where):
    if not m.get('p1Id') or not m.get('p2Id') or m.get('p1Score') is None: return None
    if m.get('state') not in ('COMPLETE', 'FINISHED', 'IN_PROGRESS', 'LIVE'): return None
    if m.get('p1Score', 0) == 0 and m.get('p2Score', 0) == 0 and not (m.get('p1Ff') or m.get('p2Ff')): return None
    return [tid, m.get('id'), m['p1Id'], m['p2Id'], m.get('p1Score'), m.get('p2Score'), m.get('raceTo'), m.get('datetime') or '',
            m.get('state'), where, 1 if m.get('p1Ff') else 0, 1 if m.get('p2Ff') else 0]


def read(tid, parent=0):
    d = get(f'{API}/{tid}')['data']
    t = d.get('tournament') or d
    cat = t.get('category') or ''
    if t.get('discipline') not in (None, 'POOL') or t.get('matchDoubles') or NOT_WANTED.search(cat) or (cat and not WANTED.search(cat)):
        return None, []
    for p in t.get('players') or []: keep_player(p)
    ms = []
    if t.get('format') == 'RR':
        for g in range(1, (t.get('rrGroupCount') or 0) + 1):
            gd = get(f'{API}/{tid}/group/{g}').get('data') or {}
            for rnd in gd.get('rounds') or []:
                for m in rnd.get('matches') or []:
                    r = mrow(tid, m, f'group {g}')
                    if r: ms.append(r)
    for m in d.get('matches') or []:
        r = mrow(tid, m, m.get('side') or '')
        if r: ms.append(r)
    try: desc = get(f'{API}/{tid}/details').get('description') or ''
    except Exception: desc = ''
    hcp = 1 if re.search(r'handicap|hendikep|\bfor(y|ami|ów)\b', desc, re.I) and not re.search(r'bez\s+(handicap|for)', desc, re.I) else 0
    row = [tid, t.get('name') or '', cat, t.get('format') or '', t.get('state') or '', t.get('startDate') or '', t.get('endDate') or '',
           t.get('userId'), hcp, parent, len(ms)]
    return row, ms, t.get('rrKnockoutId')


def main():
    have = {x[0]: i for i, x in enumerate(D['tournaments'])}
    ids = list_ids()
    todo = [i for i in ids if i not in done and i not in skipped]
    print(f'online-brackets: {len(ids)} pool tournaments listed, {len(todo)} to read', flush=True)
    new = upd = 0
    queue = [(i, 0) for i in todo]
    while queue:
        tid, parent = queue.pop(0)
        try: res = read(tid, parent)
        except Exception as e: print('  could not read', tid, e, flush=True); continue
        if res[0] is None: skipped.add(tid); continue
        row, ms, ko = res
        if ko and ko not in done and ko not in [q[0] for q in queue]: queue.append((ko, tid))
        D['matches'] = [m for m in D['matches'] if m[0] != tid] + ms
        if tid in have: D['tournaments'][have[tid]] = row; upd += 1
        else: have[tid] = len(D['tournaments']); D['tournaments'].append(row); new += 1
        end = ddate(row[6]) or ddate(row[5])
        if row[4] in ('COMPLETE', 'FINISHED', 'CLOSED') and end and (TODAY - end).days > 30: done.add(tid)
        if (new + upd) % 50 == 0: save()
    save()
    print(f'online-brackets: {new} new tournaments, {upd} re-read; total {len(D["tournaments"])} tournaments, '
          f'{len(D["matches"])} matches, {len(D["players"])} players, {len(skipped)} skipped (other games or doubles)', flush=True)


def save():
    D['done'], D['skipped'] = sorted(done), sorted(skipped)
    os.makedirs('data', exist_ok=True)
    with gzip.open(FILE + '.tmp', 'wt', encoding='utf-8') as f: json.dump(D, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(FILE + '.tmp', FILE)


if __name__ == '__main__':
    main()
