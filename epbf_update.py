"""Weekly EPBF data collection (Euro Tour, Euro Tour Women, European Championships, Youth Tour).

Only gathers data into data/epbf_data.json.gz; the rating does not use it (yet).
Adds events that are not in the file, and re-reads events that started in the last 60 days
(results can come in late). Format is described in the project doc epbf-data.md.
"""
import gzip, json, os, re, sys, time, datetime
import requests
from bs4 import BeautifulSoup

BASE = 'https://www.epbf.com'
SERIES = ['eurotour', 'eurotour-women', 'european-championships', 'youth-tour']
FILE = 'data/epbf_data.json.gz'
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (Latvian pool rating data collector)'})
log = []
def say(*a):
    m = ' '.join(str(x) for x in a); print(m, flush=True); log.append(m)

START = time.time()
BUDGET = 25 * 60          # stop reading after 25 minutes (normal run: about 2 minutes) and save what we have
FAILS = [0]               # consecutive failed requests; epbf.com down or very slow -> stop early
class OutOfTime(Exception): pass

def get(path):
    for i in range(3):
        if time.time() - START > BUDGET: raise OutOfTime('time budget used up')
        try:
            r = S.get(BASE + path, timeout=(10, 30))
            if 400 <= r.status_code < 500: r.raise_for_status()      # page does not exist: no retry
            r.raise_for_status(); FAILS[0] = 0; return r.text
        except requests.HTTPError as e:
            if e.response is not None and 400 <= e.response.status_code < 500: raise
            err = e
        except Exception as e:
            err = e
        FAILS[0] += 1
        if FAILS[0] >= 8: raise OutOfTime(f'epbf.com not responding ({err})')
        if i < 2: time.sleep(5 * (i + 1))
    raise err

def T(el):   # like textContent with collapsed whitespace
    return re.sub(r'\s+', ' ', el.get_text()).strip() if el else ''

def event_list(ser):
    soup = BeautifulSoup(get(f'/tournaments/{ser}/previous-events/'), 'lxml')
    out = {}
    for a in soup.find_all('a', href=True):
        m = re.search(r'/id/(\d+)/information', a['href'])
        if not m or m.group(1) in out: continue
        c = a
        for _ in range(6):
            if c.parent is None: break
            c = c.parent
            if len(T(c)) > 40: break
        out[m.group(1)] = re.sub(r' Open details$', '', T(c))
    return out

SERIES_HEAD = {'predator euro tour', 'predator euro tour women', 'predator european pool championships', 'predator youth tour',
               'epbf', 'tournaments', 'menu', 'our sponsors', 'our local event sponsors', 'previous event'}
def info(ser, eid):
    soup = BeautifulSoup(get(f'/tournaments/{ser}/id/{eid}/information/'), 'lxml')
    main = soup.select_one('.bg-white.box-shadow') or soup.body
    txt = T(main)
    g = lambda p: (re.search(p, txt) or [None, ''])[1]
    # the event's own name: page headings without the series heading and sponsor blocks
    heads = []
    for h in soup.find_all(['h1', 'h2', 'h3']):
        x = T(h)
        if x and x.lower() not in SERIES_HEAD and x not in heads: heads.append(x)
    h3 = soup.find_all('h3')
    return dict(group=T(soup.find('h1')), name=' · '.join(heads[:2]) or T(h3[1] if len(h3) > 1 else (h3[0] if h3 else None)),
                start=g(r'Start: ([A-Za-z]{3} \d+, \d{4})'), final=g(r'Final: ([A-Za-z]{3} \d+, \d{4})'),
                disc=g(r'Discipline: (.*?)(?: Entry| Format|$)'))

def name_id(td):
    if td is None: return ['', 0]
    s = td.find('span'); a = td.find('a', href=True)
    pid = int((re.search(r'show/(\d+)', a['href']) or [0, 0])[1]) if a else 0
    return [T(s) if s else T(td), pid]

def flag(td):
    im = td.find('img') if td is not None else None
    if not im: return ''
    f = (im.get('src') or '').split('/')[-1]
    return re.sub(r'\.(svg|png)$', '', f)

def draw(ser, eid):
    soup = BeautifulSoup(get(f'/tournaments/{ser}/id/{eid}/draw-results/'), 'lxml')
    out, rnd = [], ''
    for el in soup.find_all(['h3', 'tr']):
        if el.name == 'h3': rnd = T(el); continue
        if 'full_layout' not in (el.get('class') or []): continue
        c = el.find_all('td', recursive=False)
        if len(c) < 10: continue
        cell = lambda cls: el.find('td', class_=cls)
        na, ia = name_id(cell('name_a')); nb, ib = name_id(cell('name_b'))
        out.append([T(c[0]), rnd, T(c[1]), T(c[3]), na, ia, flag(c[5]), T(cell('score_a')), T(cell('score_b')), nb, ib, flag(c[9]), T(cell('status'))])
    return out

def ranking(ser, eid):
    soup = BeautifulSoup(get(f'/tournaments/{ser}/id/{eid}/ranking/'), 'lxml')
    rows = []
    for tr in soup.find_all('tr'):
        cells = []
        for td in tr.find_all(['td', 'th'], recursive=False):
            s = td.find('span', class_='d-md-inherit') or td.find('span', class_='d-none')
            a = td.find('a', href=True)
            v = T(s) if s and T(s) else T(td)
            if a: v += '#' + ((re.search(r'show/(\d+)', a['href']) or [0, ''])[1])
            cells.append(v)
        if len(cells) > 2 and re.match(r'\d', cells[0]): rows.append(cells)
    return rows

def started(ev):
    try: return datetime.datetime.strptime(ev.get('start', ''), '%b %d, %Y').date()
    except ValueError: return None

def guess_series(ev):
    t = (ev.get('name', '') + ' ' + ev.get('group', '') + ' ' + ev.get('disc', '')).lower()
    if 'youth tour' in t: return 'youth-tour'
    if 'european championship' in t or re.search(r'\bec\b', t) or 'heyball' in t or 'para' in t: return 'european-championships'
    return 'eurotour-women' if '(women)' in t else 'eurotour'

def read_event(ser, eid, text):
    ev = dict(ser=ser, id=int(eid)); ev.update(info(ser, eid)); time.sleep(0.5)
    ev['matches'] = draw(ser, eid); time.sleep(0.5)
    if not ev['matches']: ev['ranking'] = ranking(ser, eid); time.sleep(0.5)
    ev['list'] = text
    return ev

if __name__ == '__main__':
    data = json.load(gzip.open(FILE, 'rt', encoding='utf-8')) if os.path.exists(FILE) else {'events': []}
    have = {e['id']: i for i, e in enumerate(data['events'])}
    today = datetime.date.today(); recent = today - datetime.timedelta(days=60)
    new = upd = nm = 0
    def store(ev, label):
        global new, upd, nm
        if ev['id'] in have: data['events'][have[ev['id']]] = ev; upd += 1
        else: data['events'].append(ev); have[ev['id']] = len(data['events']) - 1; new += 1
        nm += len(ev['matches'])
        say(f'  {label}: {ev["ser"]} {ev["id"]} {(ev.get("list") or ev.get("name", ""))[:70]} ({len(ev["matches"])} matches)')
    listed = set()
    stopped = False
    for ser in SERIES:
        if stopped: break
        try: lst = event_list(ser)
        except OutOfTime as e: say(f'STOPPED: {e}'); stopped = True; break
        except Exception as e: say(f'{ser}: list failed: {e}'); continue
        for eid, text in lst.items():
            listed.add(int(eid))
            old = data['events'][have[int(eid)]] if int(eid) in have else None
            if old and old['ser'] == ser and old.get('list') and not old.get('not_listed_yet'):
                d0 = started(old)
                if not (d0 and d0 >= recent): continue
            try: ev = read_event(ser, eid, text)
            except OutOfTime as e: say(f'STOPPED: {e}'); stopped = True; break
            except Exception as e: say(f'  could not read {ser} {eid}: {e}'); continue
            store(ev, 'new' if not old else 're-read')
    # Finished events that are not in the lists yet (EPBF adds them there later): try the ids after the newest known one.
    top = max(have) if have else 0
    for eid in range(top - 30, top + 31):
        if stopped: break
        if eid in listed: continue
        old = data['events'][have[eid]] if eid in have else None
        if old:
            d0 = started(old)
            if not (d0 and d0 >= recent): continue
        try:
            ev = dict(ser='eurotour', id=eid); ev.update(info('eurotour', eid)); time.sleep(0.5)
        except OutOfTime as e: say(f'STOPPED: {e}'); stopped = True; break
        except Exception: continue          # no event with this id
        d0 = started(ev)
        if not d0 or d0 > today: continue    # not played yet
        ser = guess_series(ev)
        label = ev.get('name', '')
        try: ev = read_event(ser, eid, f'{ev.get("start", "")} {label}')
        except OutOfTime as e: say(f'STOPPED: {e}'); stopped = True; break
        except Exception as e: say(f'  could not read {ser} {eid}: {e}'); continue
        ev['not_listed_yet'] = True
        store(ev, 'found by id' if not old else 're-read (by id)')
    data['collected'] = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + 'Z'
    os.makedirs('data', exist_ok=True)
    with gzip.open(FILE, 'wt', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    total = sum(1 for e in data['events'] for m in e.get('matches') or [])
    if stopped: say('Run stopped early: the next run continues from here (nothing is lost).')
    say(f'EPBF: {new} new events, {upd} recent events re-read, {nm} match rows read; file now has {len(data["events"])} events and {total} match rows')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        open(os.environ['GITHUB_STEP_SUMMARY'], 'a').write('\n'.join(log) + '\n')
