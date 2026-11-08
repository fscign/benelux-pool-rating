"""Matchroom / World Nineball Tour data collection (wntlivescores.com).

Only gathers data into data/wnt_data.json.gz; the rating does not use it.
Adds new events and re-reads events that ended in the last REREAD_DAYS days.
Needs a WNT account: GitHub secrets WNT_EMAIL and WNT_PASSWORD.
Same JSON format as the first browser collection (2 Nov 2026), see claude/wnt-data.md.
"""
import datetime as dt
import gzip
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.wntlivescores.com"
FILE = "data/wnt_data.json.gz"
REREAD_DAYS = 60
PAUSE = 0.4  # seconds between requests
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
FORMAT = {
    "match": ["stage", "match no", "round", "date time", "table", "name A", "flag A",
              "score A", "score B", "name B", "flag B", "status"],
    "ranking": ["place", "name", "player slug", "flag", "prize"],
}

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (latvian-pool-rating data collection)"


def summary(text):
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def tc(el):
    """Like the browser's textContent (all text, no separators added)."""
    return el.get_text() if el is not None else ""


def get(path):
    time.sleep(PAUSE)
    r = S.get(BASE + path, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {path}")
    if r.url.rstrip("/").endswith("/login"):
        raise RuntimeError(f"redirected to login: {path}")
    return BeautifulSoup(r.text, "html.parser")


def login():
    email, pw = os.environ.get("WNT_EMAIL"), os.environ.get("WNT_PASSWORD")
    if not email or not pw:
        sys.exit("WNT_EMAIL / WNT_PASSWORD secrets are missing")
    S.get(BASE + "/login", timeout=60)
    S.post(BASE + "/login", data={"username": email, "password": pw}, timeout=60)
    try:
        doc = get("/events")
    except RuntimeError as e:
        sys.exit(f"Login failed ({e}). Check the WNT_EMAIL / WNT_PASSWORD secrets.")
    return doc


# ---------- parsers (mirror the browser collection) ----------

def event_list(doc):
    slugs, cards = [], {}
    for a in doc.find_all("a", href=True):
        m = re.match(r"^/events/([^/]+)/ranking", a["href"])
        if not m:
            continue
        slug = m.group(1)
        if slug in cards:
            continue
        c = a
        for _ in range(6):
            if c.parent is None:
                break
            c = c.parent
            if len(ws(tc(c))) > 60:
                break
        slugs.append(slug)
        cards[slug] = ws(tc(c))
    return slugs, cards


def flag_of(p):
    img = p.select_one(".flag img") if p is not None else None
    return (img.get("src") or "").split("/")[-1].replace(".svg", "") if img else ""


def sel_text(el, css):
    x = el.select_one(css)
    return tc(x).strip() if x is not None else ""


def parse_list(doc):
    out, rnd = [], ""
    for e in doc.select(".round-name, .match"):
        cls = e.get("class") or []
        if "round-name" in cls:
            rnd = ws(tc(e))
            continue
        p1, p2 = e.select_one(".player1"), e.select_one(".player2")
        cstr = " ".join(cls)
        m = re.search(r"\b(finished|live|scheduled|pending|walkover|bye)\b", cstr)
        status = m.group(1) if m else ""
        if p1 is not None and "winner" in (p1.get("class") or []):
            status += " w1"
        elif p2 is not None and "winner" in (p2.get("class") or []):
            status += " w2"
        out.append([
            sel_text(e, ".match-id strong"), rnd,
            sel_text(e, ".match-date") + " " + sel_text(e, ".match-time .value"),
            sel_text(e, ".playing-table"),
            sel_text(e, ".player1_name"), flag_of(p1),
            sel_text(e, ".player1_score"), sel_text(e, ".player2_score"),
            sel_text(e, ".player2_name"), flag_of(p2), status,
        ])
    return out


def parse_ranking(doc):
    rows = []
    for i, p in enumerate(doc.select(".col.player")):
        a = p.find("a")
        pos = p.select_one(".position")
        names = [tc(s).strip() for s in p.select(".player-name span")]
        fl = p.select_one(".country-flag img")
        place = re.sub(r"[\s#]", "", tc(pos)) if pos is not None else ""
        if i == 0 and not place:
            place = "1"
        rows.append([
            place, " ".join(names),
            (a.get("href") or "").replace("/players/", "") if a is not None else "",
            (fl.get("src") or "").split("/")[-1].replace(".svg", "") if fl is not None else "",
            sel_text(p, ".points"),
        ])
    return rows


def collect(slug, card):
    e = {"slug": slug, "name": "", "type": "", "date": "", "venue": "", "location": "",
         "prize": "", "stages": [], "matches": [], "ranking": []}
    it = ws(tc(get("/events/" + slug).body))
    rx = lambda p: (re.search(p, it) or [None, ""])[1]
    e["name"] = rx(r"Event info (.*?) Date")
    e["date"] = rx(r"Date (.*?) Venue")
    e["venue"] = rx(r"Venue (.*?) Location")
    e["location"] = rx(r"Location (.*?) (?:Prize fund|Live action|Player List)")
    e["prize"] = rx(r"Prize fund (\S+)")
    for n in range(1, 6):
        try:
            d = get(f"/events/{slug}/matches-list/{n}")
            ms = parse_list(d)
        except RuntimeError:
            if n > 1:
                break
            continue
        if not ms:
            if n > 1:
                break
            continue
        nm = next((a for a in d.find_all("a", href=True)
                   if a["href"].endswith(f"/matches-list/{n}")
                   and re.search(r"Stage|Group|Main|Qual|Final", tc(a), re.I)), None)
        e["stages"].append({"n": n, "name": tc(nm).strip() if nm is not None else "", "count": len(ms)})
        e["matches"] += [[n] + m for m in ms]
    e["ranking"] = parse_ranking(get(f"/events/{slug}/ranking"))
    e["type"] = (re.search(r"(Major Event|Ranking Event|Invitational|Blue Ribbon|Qualifier)", card) or [None, ""])[1]
    if not e["name"]:
        e["name"] = (re.match(r"^(.*?)\.\s", card) or [None, ""])[1]
    return e


def end_date(date):
    """'Aug 27 - 30, 2026', 'Jul 29 - Aug 1, 2026', 'May 30 - Jun 4, 2023' -> date of the last day."""
    m = re.match(r"(\w{3}) (\d+)(?: - (?:(\w{3}) )?(\d+))?, (\d{4})", date or "")
    if not m:
        return None
    mon = MONTHS.get(m.group(3) or m.group(1))
    day = int(m.group(4) or m.group(2))
    try:
        return dt.date(int(m.group(5)), mon, day)
    except (TypeError, ValueError):
        return None


def played(e):
    return sum(1 for m in e["matches"] if m[7].isdigit() and m[8].isdigit())


def main():
    old = {"events": []}
    if os.path.exists(FILE):
        with gzip.open(FILE, "rt", encoding="utf-8") as f:
            old = json.load(f)
    stored = {e["slug"]: e for e in old["events"]}

    slugs, cards = event_list(login())
    if len(slugs) < max(10, len(stored) // 2):
        sys.exit(f"Only {len(slugs)} events on the list (stored {len(stored)}); stopping without changes.")

    today = dt.date.today()
    new_events, lines, added, reread, changed = [], [], 0, 0, 0
    for slug in slugs:
        st = stored.get(slug)
        end = end_date(st["date"]) if st else None
        if st and end and (today - end).days > REREAD_DAYS:
            new_events.append(st)
            continue
        try:
            e = collect(slug, cards.get(slug, ""))
        except Exception as ex:  # keep the stored copy if a page fails
            lines.append(f"- {slug}: ERROR {ex}")
            if st:
                new_events.append(st)
            continue
        if st is None:
            added += 1
            lines.append(f"- NEW {e['name']} ({e['date']}): {played(e)} played matches, {len(e['ranking'])} placings")
        else:
            reread += 1
            if json.dumps(e, sort_keys=True) != json.dumps(st, sort_keys=True):
                changed += 1
                lines.append(f"- updated {e['name']}: played {played(st)} -> {played(e)}, placings {len(st['ranking'])} -> {len(e['ranking'])}")
        new_events.append(e)
    # never drop stored events that disappeared from the list
    gone = [e for s, e in stored.items() if s not in set(slugs)]
    new_events += gone

    tot = sum(played(e) for e in new_events)
    summary("## WNT data collection")
    summary(f"Events on the list: {len(slugs)}; new: {added}; re-read (last {REREAD_DAYS} days or no date): {reread}; changed: {changed}; kept but no longer listed: {len(gone)}")
    summary(f"Total events {len(new_events)}, played matches {tot}, placing rows {sum(len(e['ranking']) for e in new_events)}")
    for l in lines:
        summary(l)

    if added == 0 and changed == 0 and len(new_events) == len(old["events"]):
        summary("No changes, file not rewritten.")
        return
    out = {"collected": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": BASE + "/events", "format": FORMAT, "events": new_events}
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    summary(f"Saved {FILE}.")


if __name__ == "__main__":
    main()
