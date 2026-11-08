"""Predator Pro Billiard Series (PBS) data collection.

Reads the CueScore tournaments listed in pbs_ids.json (PBS events are CueScore
tournaments of the hidden organizer "probilliardseries") from the public
CueScore API and saves data/pbs_data.json.gz. Only gathers data; the rating
does not use it.

Set-format matches (race to 4 per set) are split: EVERY SET IS ONE ROW (one
"match" for the rating).
  - A set tied 3-3 is decided by a shootout. The shootout (logged as an extra
    "set" with its own numbers) is ignored; the set is kept as 3-3 racks.
  - A set logged one rack short (e.g. 3-1 for a set that was won) gets the
    missing rack added to its winner, but only when the set winners of the
    whole match then add up to the official set score.
  - Anything else that does not add up is kept with flag "bad" (not to be used).
Plain races (e.g. 8-ball race to 8) are one row as usual.

Run: python pbs_update.py            (adds new IDs, re-reads events ended in the last 60 days)
     python pbs_update.py --all      (re-reads everything)
"""
import gzip
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.cuescore.com/tournament/?id={}"
IDS_FILE = "pbs_ids.json"
FIXES_FILE = "pbs_fixes.json"   # manual corrections: {matchId: {setNo: [a, b] | "drop"}}
OUT = os.path.join("data", "pbs_data.json.gz")
DELAY = float(os.environ.get("PBS_DELAY", 8))  # seconds between requests (CueScore robots.txt crawl-delay)
RECENT_DAYS = 60
GAMES = {"8-Ball", "9-Ball", "10-Ball"}
NOT_SINGLES = ("double", "mixed", "team", "pocket", "bank", "straight", "14.1", "scotch")

FORMAT = ("match row: [matchId, setNo (0 = plain race), round, time UTC, raceTo, "
          "playerIdA, nameA, countryA (alpha3), racksA, racksB, nameB, playerIdB, countryB, "
          "flag, winner (A/B)]. flag: race = plain race; set = complete set; "
          "set_3_3 = set tied 3-3, decided by shootout (shootout ignored; winner empty if the shootout was not logged); "
          "set_fixed = missing last rack added to set winner; "
          "shootout = deciding shootout logged as a set (racks null, never use; winner kept for reference); "
          "extra = set logged after a player had already won the match (scoring mistake, racks null, never use); "
          "corrected = set score fixed by hand from pbs_fixes.json (use); dropped = set removed by hand (never use); "
          "no_racks = set format but no rack data (racks null); bad = does not add up, do not use. "
          "Walkovers and unplayed matches are left out.")


def fetch(tid):
    req = urllib.request.Request(API.format(tid), headers={"User-Agent": "pool-rating-collector/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def player(p):
    c = p.get("country") or {}
    return p.get("playerId"), (p.get("name") or "").strip(), (c.get("alpha3") or "") if isinstance(c, dict) else ""


def is_walkover(m):
    names = (m["playerA"].get("name") or "") + "|" + (m["playerB"].get("name") or "")
    return "walk over" in names.lower() or not m["playerA"].get("playerId") or not m["playerB"].get("playerId")


def raw_sets(m):
    """Per-set rack scores [a, b] in playing order, shootouts included."""
    if m.get("sets"):
        s = [[x.get("scoreA") or 0, x.get("scoreB") or 0] for x in m["sets"]]
        return [x for x in s if x != [0, 0]]
    sets, a, b = [], 0, 0
    for n in m.get("notes") or []:
        t = n.get("note", "")
        if t == "set start":
            if a or b:
                sets.append([a, b])
            a = b = 0
        elif t.startswith("A frame win"):   # also "A frame win runout"
            a += 1
        elif t.startswith("B frame win"):
            b += 1
        elif t == "set end":
            sets.append([a, b])
            a = b = 0
    if a or b:
        sets.append([a, b])
    return [x for x in sets if x != [0, 0]]


def split_sets(m, target=None):
    """Return list of (setNo, racksA, racksB, flag, winner, loggedA, loggedB, shootout).

    target = sets needed to win the match in this round (from the other matches
    of the same round). Sets played after a player already had `target` sets are
    scoring mistakes: flag "extra", never used.
    """
    race = m.get("raceTo") or 4
    s = raw_sets(m)
    if not s:
        return None
    sets, i = [], 0          # each: [a, b, kind, winner, shootout score]
    while i < len(s):
        a, b = s[i]
        if a == b == race - 1:
            w, so = "", None
            if i + 1 < len(s):
                so = s[i + 1]
                w = "A" if so[0] > so[1] else "B" if so[1] > so[0] else ""
                i += 2
            else:
                i += 1
            sets.append([a, b, "set_3_3", w, so])
            continue
        w = "A" if a > b else "B" if b > a else ""
        complete = max(a, b) == race and min(a, b) < race
        level = sum(x[3] == "A" for x in sets) == sum(x[3] == "B" for x in sets) and sets
        if i == len(s) - 1 and level and not complete:
            # deciding "set" with sets level that is not a real race: a shootout
            sets.append([a, b, "shootout", w, None])
        else:
            sets.append([a, b, "raw", w, None])
        i += 1
    if target:
        wa = wb = 0
        for x in sets:
            if max(wa, wb) >= target:
                x[2] = "extra"
                continue
            # only clearly decided sets count toward the match win
            a, b, kind, w = x[0], x[1], x[2], x[3]
            decided = (kind == "raw" and max(a, b) == race and min(a, b) < race) or (kind in ("set_3_3", "shootout") and w)
            if decided:
                wa += w == "A"
                wb += w == "B"
    real = [x for x in sets if x[2] != "extra"]
    wa, wb = sum(x[3] == "A" for x in real), sum(x[3] == "B" for x in real)
    sa, sb = m.get("scoreA") or 0, m.get("scoreB") or 0
    consistent = (wa, wb) == (sa, sb) or bool(
        target and max(wa, wb) == target and min(wa, wb) < target and (wa > wb) == (sa > sb))
    out = []
    for n, (a, b, kind, w, so) in enumerate(sets, 1):
        if kind == "set_3_3":
            out.append((n, a, b, "set_3_3", w, a, b, so))  # racks are real even if the shootout was not logged
        elif kind == "shootout":
            out.append((n, None, None, "shootout", w, a, b, None))
        elif kind == "extra":
            out.append((n, None, None, "extra", w, a, b, None))
        elif max(a, b) == race and min(a, b) < race:
            out.append((n, a, b, "set", w, a, b, None))
        elif consistent and max(a, b) == race - 1 and min(a, b) < race - 1:
            ua, ub = (a + 1, b) if w == "A" else (a, b + 1)
            out.append((n, ua, ub, "set_fixed", w, a, b, None))
        else:
            out.append((n, a, b, "bad", w, a, b, None))
    return out


def round_targets(d):
    """Sets needed to win, per round: most common winner set count among the round's matches."""
    from collections import Counter
    c = {}
    for m in d.get("matches") or []:
        if m.get("matchstatus") != "finished" or is_walkover(m):
            continue
        if not ((m.get("bestOfSets") or 0) > 0 or m.get("sets")):
            continue
        hi = max(m.get("scoreA") or 0, m.get("scoreB") or 0)
        if hi > 0:
            c.setdefault(m.get("roundName"), Counter())[hi] += 1
    return {r: cnt.most_common(1)[0][0] for r, cnt in c.items()}


def build_event(entry, d):
    ev = {
        "id": d.get("tournamentId"), "path": entry.get("path", ""), "name": d.get("name"),
        "discipline": d.get("discipline"), "start": d.get("starttime"), "stop": d.get("stoptime"),
        "timezone": d.get("timezone"), "status": d.get("status"), "url": d.get("url"),
        "venue": "", "country": "", "matches": [],
    }
    v = (d.get("venues") or [{}])[0] if isinstance(d.get("venues"), list) and d.get("venues") else {}
    if isinstance(v, dict):
        ev["venue"] = v.get("name", "")
        c = v.get("country") or {}
        ev["country"] = c.get("alpha3", "") if isinstance(c, dict) else ""
    name = (d.get("name") or "").lower()
    if d.get("discipline") not in GAMES or any(k in name for k in NOT_SINGLES):
        ev["skipped"] = "not 8/9/10-ball singles"
        return ev
    targets = round_targets(d)
    for m in d.get("matches") or []:
        if m.get("matchstatus") != "finished" or is_walkover(m):
            continue
        ida, na, ca = player(m["playerA"])
        idb, nb, cb = player(m["playerB"])
        base = [m.get("matchId"), m.get("roundName"), m.get("starttime") or d.get("starttime")]
        set_format = (m.get("bestOfSets") or 0) > 0 or bool(m.get("sets"))
        if not set_format:
            a, b = m.get("scoreA") or 0, m.get("scoreB") or 0
            if a == b == 0:
                continue
            w = "A" if a > b else "B" if b > a else ""
            ev["matches"].append([base[0], 0, base[1], base[2], m.get("raceTo"), ida, na, ca, a, b, nb, idb, cb, "race", w])
            continue
        parts = split_sets(m, targets.get(m.get("roundName")))
        if not parts:
            if (m.get("scoreA") or 0) + (m.get("scoreB") or 0) == 0:
                continue
            w = "A" if m["scoreA"] > m["scoreB"] else "B"
            ev["matches"].append([base[0], 0, base[1], base[2], m.get("raceTo"), ida, na, ca, None, None, nb, idb, cb, "no_racks", w])
            continue
        fix = FIXES.get(str(m.get("matchId")), {})
        for n, a, b, flag, w, *_ in parts:
            f = fix.get(str(n))
            if f == "drop":
                a = b = None
                flag = "dropped"
            elif isinstance(f, list):
                a, b = f
                flag = "corrected"
                w = "A" if a > b else "B" if b > a else ""
            ev["matches"].append([base[0], n, base[1], base[2], m.get("raceTo"), ida, na, ca, a, b, nb, idb, cb, flag, w])
    return ev


FIXES = {}


def main():
    global FIXES
    full = "--all" in sys.argv
    if os.path.exists(FIXES_FILE):
        FIXES = json.load(open(FIXES_FILE, encoding="utf-8")).get("fixes", {})
    ids = json.load(open(IDS_FILE, encoding="utf-8"))["events"]
    old = {}
    if os.path.exists(OUT) and not full:
        with gzip.open(OUT, "rt", encoding="utf-8") as f:
            old = {e["id"]: e for e in json.load(f).get("events", [])}
    now = datetime.now(timezone.utc)
    events, new, reread, failed = [], [], [], []
    first = True
    for entry in ids:
        tid = entry["id"]
        if entry.get("skip"):
            continue
        prev = old.get(tid)
        need = prev is None or prev.get("status") != "Finished"
        if prev and not need and prev.get("stop"):
            try:
                need = datetime.fromisoformat(prev["stop"].replace("Z", "+00:00")) > now - timedelta(days=RECENT_DAYS)
            except ValueError:
                need = True
        if not need:
            events.append(prev)
            continue
        if not first:
            time.sleep(DELAY)
        first = False
        try:
            ev = build_event(entry, fetch(tid))
        except Exception as e:  # keep old copy on failure
            failed.append(f"{tid} ({e})")
            if prev:
                events.append(prev)
            continue
        (new if prev is None else reread).append(f"{tid} {ev['name']}")
        events.append(ev)
    data = {"collected": now.isoformat(timespec="seconds"), "source": "CueScore API, PBS tournaments from pbs_ids.json",
            "format": FORMAT, "events": events}
    os.makedirs("data", exist_ok=True)
    before = None
    if os.path.exists(OUT):
        with gzip.open(OUT, "rt", encoding="utf-8") as f:
            before = json.dumps(json.load(f).get("events"), sort_keys=True)
    changed = before != json.dumps(events, sort_keys=True)
    if changed:
        with gzip.open(OUT, "wt", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    flags = {}
    for e in events:
        for r in e.get("matches", []):
            flags[r[13]] = flags.get(r[13], 0) + 1
    lines = [f"PBS collection {now:%Y-%m-%d %H:%M} UTC", f"Events: {len(events)} (new {len(new)}, re-read {len(reread)}, failed {len(failed)})",
             "Rows by flag: " + ", ".join(f"{k} {v}" for k, v in sorted(flags.items())),
             "File " + ("updated" if changed else "unchanged")]
    lines += ["New: " + x for x in new] + ["Failed: " + x for x in failed]
    print("\n".join(lines))
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write("\n\n".join(lines) + "\n")
    if failed and not events:
        sys.exit(1)


if __name__ == "__main__":
    main()
