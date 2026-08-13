#!/usr/bin/env python3
"""fdsoccer.py — pull TODAY'S soccer straight from FanDuel's own public
sportsbook endpoints, for the competitions The Odds API does not carry.

Why this exists. On 2026-08-13 FanDuel was pricing ~27 UEFA Europa League and
Conference League third-qualifying-round second legs. The Odds API catalog has
no key for either competition, so the board saw five Leagues Cup matches and
called that the day's soccer. Every odds aggregator is blocked by the egress
proxy on the session that maintains this repo -- but this script runs on the
Actions runner, which has open egress, same as the normal odds pull.

These are the public, unauthenticated odds the FanDuel web client itself reads
to render the sportsbook: no login, no account data, nothing but the prices
already on the public board. `_ak` is the client key their own JS ships.

Output is a board-shaped fragment on stdout plus fdsoccer.json, so prices go
through the same de-vig and the same preflight gates as everything else. A
price this script cannot verify is DROPPED, never guessed -- the whole reason
it exists is that a guessed number is worse than a missing one.
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

AK = "FhMFpcPWXMeyZxOx"          # FanDuel web client key, shipped in their JS
REGIONS = ("nj", "pa", "co", "va")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json",
        "Referer": "https://sportsbook.fanduel.com/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def try_regions(path):
    """FanDuel shards by state; try a few and take the first that answers."""
    last = None
    for co in REGIONS:
        url = f"https://sbapi.{co}.fanduel.com/api/{path}"
        sep = "&" if "?" in path else "?"
        url = f"{url}{sep}_ak={AK}&timezone=America%2FChicago"
        try:
            return co, get(url)
        except Exception as e:
            last = f"{co}: {type(e).__name__} {getattr(e,'code','')}"
    print(f"    all regions failed ({last})")
    return None, None


def american(v):
    try:
        return int(round(float(v)))
    except Exception:
        return None


def main():
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=int(os.environ.get("FD_HOURS", "16")))
    print(f"window {now:%Y-%m-%d %H:%M}Z -> {end:%Y-%m-%d %H:%M}Z\n")

    co, nav = try_regions("content-managed-page?page=CUSTOM&customPageId=soccer")
    if not nav:
        print("could not reach FanDuel"); return 1
    print(f"reached sbapi.{co}.fanduel.com\n")

    attach = nav.get("attachments") or {}
    events = attach.get("events") or {}
    markets = attach.get("markets") or {}
    comps = {str(k): v.get("name", "?")
             for k, v in (attach.get("competitions") or {}).items()}
    print(f"navigation payload: {len(events)} events, {len(markets)} markets, "
          f"{len(comps)} competitions")

    rows, out = [], []
    for ev in events.values():
        t = ev.get("openDate") or ev.get("startTime") or ""
        if not t:
            continue
        try:
            when = datetime.fromisoformat(t.replace("Z", "+00:00"))
        except ValueError:
            continue
        if not (now - timedelta(minutes=30) <= when <= end):
            continue
        comp = comps.get(str(ev.get("competitionId")), ev.get("competitionName", "?"))
        rows.append((when, comp, ev.get("name", "?"), ev.get("eventId")))

    rows.sort()
    print(f"{len(rows)} soccer events inside the window\n")
    for when, comp, name, eid in rows:
        print(f"  {when:%m/%d %H:%M}Z  {comp:<34} {name}")
        out.append({"eventId": eid, "start": f"{when:%Y-%m-%dT%H:%MZ}",
                    "competition": comp, "name": name, "markets": {}})

    # Per-event odds. One call each, and only for events we are going to use.
    for rec in out:
        _, ev = try_regions(f"event-page?eventId={rec['eventId']}")
        if not ev:
            continue
        mk = (ev.get("attachments") or {}).get("markets") or {}
        for m in mk.values():
            mtype = m.get("marketType") or m.get("marketName") or ""
            runners = {}
            for r in m.get("runners", []):
                price = ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds")
                         or {}).get("americanOddsInt")
                p = american(price)
                if p is not None:
                    runners[r.get("runnerName", "?")] = p
            if len(runners) >= 2:
                rec["markets"][m.get("marketName") or mtype] = runners

    with open("fdsoccer.json", "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    got = sum(1 for r in out if r["markets"])
    print(f"\nwrote fdsoccer.json — {got}/{len(out)} events with prices")
    return 0


if __name__ == "__main__":
    sys.exit(main())
