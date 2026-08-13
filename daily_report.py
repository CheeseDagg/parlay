#!/usr/bin/env python3
"""daily_report.py — write BOARD.md: today's heaviest legs + candidate tickets.

Runs after pull_feeds.py in the Action. Everything in BOARD.md is derived from
the feed files in this repo, so the report and the board cannot disagree.

Two standing facts are printed at the top of every report, on purpose:
  * F5 totals ride under the market key alternate_totals_1st_5_innings —
    the 2026-08-03 claim that FanDuel had none came from probing the wrong
    (totals_h1) key and is retracted;
  * every ticket is a candidate, not an instruction: check each leg against
    the FanDuel app before placing. Prices move; this file has a timestamp.
"""
import math, os, subprocess, sys, datetime as dt
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board
from board import build
from times import ct


def _today_et():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return dt.datetime.now(dt.timezone.utc).date()


def next_sunday_et():
    today = _today_et()
    return (today + dt.timedelta(days=(6 - today.weekday()) % 7)).isoformat()


def heaviest_table(horizon, n=25):
    markets = build('FanDuel', no_plus=True, min_price=350,
                    cutoff=board._utcnow(), horizon=horizon)
    legs = sorted((o for v in markets.values() for o in v),
                  key=lambda o: -o['p'])[:n]
    if not legs:
        return "_(no legs at -350 or heavier inside the horizon)_\n"
    out = ["| # | start (CT) | leg | price | p(hit) | fam |",
           "|---|---|---|---|---|---|"]
    for i, o in enumerate(legs, 1):
        out.append(f"| {i} | {ct(o['t'])} | {o['lab']} | {o['price']:+d} "
                   f"| {o['p']*100:.1f}% | {o['fam']} |")
    return "\n".join(out) + "\n"


def try_ticket(title, target, flags, legs_sweep):
    """Run solve2 over a descending legs sweep; keep the first ticket found."""
    for legs in legs_sweep:
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "solve2.py"), "FanDuel",
             str(target), f"--legs={legs}"] + flags,
            capture_output=True, text=True)
        if r.returncode == 0 and "joint hit probability" in r.stdout:
            body = r.stdout.split("=" * 20, 1)[-1]
            return (f"### {title}\n\n```\n"
                    + ("=" * 20) + body.strip() + "\n```\n")
    return f"### {title}\n\n_No ticket meets these constraints today._\n"


def hot_section():
    """RULES.md #25 rendered into the artifact the morning build actually
    reads. On the Actions runner the slate is absent and only the market arm
    fires; locally, a fresh MLBTool pull lights up the model arms too. Either
    way, absence of hot games writes nothing rather than an empty header."""
    try:
        import board
        hot = board.hot_games("FanDuel")
    except Exception as e:          # a broken flag must not kill the report
        return [f"_hot-game check unavailable: {e}_", ""]
    if not hot:
        return []
    lines = ["## HOT GAMES — F5 top rung only (rule 25)", ""]
    lines += [f"- **{g}** — {why}" for g, why in sorted(hot.items())]
    lines.append("")
    return lines


def flags_section():
    """The measured red flags, in the artifact the morning pass reads first.
    Hot games already print; these are the three instruments added 8/13 --
    gopher starters, COLD soccer teams, blowup parks -- each fail-soft,
    because a missing form file must dim the report, not kill it."""
    import json
    lines = []
    try:
        with open(os.path.join(HERE, 'mlbform.json')) as fh:
            mf = json.load(fh)
        gop = []
        for g, v in (mf.get('games') or {}).items():
            for side in ('away_sp', 'home_sp'):
                sp = v.get(side) or {}
                if sp.get('hr9_5') and sp['hr9_5'] >= mf.get('hr9_warn', 1.8):
                    gop.append(f"- **{g}** {sp['name']} HR/9 **{sp['hr9_5']:.2f}** last 5")
        if gop:
            lines += [f"## GOPHER starters (mlbform, {mf.get('date','?')})", ''] + gop + ['']
    except Exception:
        lines += ['_mlbform.json unreadable -- starter form unknown_', '']
    try:
        with open(os.path.join(HERE, 'socform.json')) as fh:
            sf = json.load(fh)
        cold = [f"- **{t}** {v['form']} ({v['ppg']} ppg, last {v['newest']})"
                for t, v in (sf.get('teams') or {}).items() if v.get('ppg', 9) <= 0.6]
        if cold:
            lines += [f"## COLD soccer teams on the board (socform, {sf.get('built','?')})", ''] + cold + ['']
    except Exception:
        lines += ['_socform.json unreadable -- team form unknown_', '']
    try:
        with open(os.path.join(HERE, 'f5hist.json')) as fh:
            f5 = json.load(fh)
        rows = f5.get('venue') or []
        base = f5.get('blowup_base', 0.062)
        hotp = {r['k']: r for r in rows if r.get('blow', 0) >= 0.10}
        if hotp:
            lines += ['## Blowup parks (F5 >= 11 runs, 3 seasons)', '']
            lines += [f"- **{k}** {v['blow']*100:.1f}% vs {base*100:.1f}% league"
                      for k, v in sorted(hotp.items(), key=lambda x: -x[1]['blow'])] + ['']
    except Exception:
        pass
    try:
        with open(os.path.join(HERE, 'cflhist.json')) as fh:
            ch = json.load(fh)
        import board
        legs = [l for v in board.build('FanDuel', min_price=0).values() for l in v]
        lines += cfl_flags(legs, ch)
    except Exception:
        pass                       # no CFL on the board most days -- silence
    return lines


def cfl_flags(legs, ch):
    """CFL total legs beside the measured base (cflhist: 321 games 2022-25).
    CFL was the one carried sport priced on nothing; now a Thursday-board
    total says how often its line ACTUALLY held, and shouts when the market
    and four seasons of results disagree by 8+ points."""
    import re as _re
    st = (ch or {}).get('stats') or {}
    rungs = st.get('rungs') or {}
    out = []
    for l in legs:
        if l.get('fam') != 'CFL':
            continue
        m = _re.search(r'\b(Over|Under)\s+(\d+\.5)\b', l.get('lab', ''))
        if not m or m.group(2) not in rungs:
            continue
        r = rungs[m.group(2)]
        base = r['p_under'] if m.group(1) == 'Under' else 1 - r['p_under']
        gap = (l.get('p', 0) - base) * 100
        tag = '  **market >> base**' if gap >= 8 else ''
        out.append(f"- {l['lab']} {l.get('price','?')}: market {l.get('p',0)*100:.0f}% "
                   f"vs base {base*100:.0f}% (n={r['n']}){tag}")
    if out:
        out = [f"## CFL legs vs measured base (cflhist n={st.get('n','?')}, "
               f"home {st.get('home_pct',0)*100:.1f}%, mean total "
               f"{st.get('mean_total','?')})", ''] + out + ['']
    return out


def main():
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sunday = next_sunday_et()
    md = [f"# Board report — {ts}",
          "",
          "Auto-generated by the daily refresh. **Check every leg against the "
          "FanDuel app before placing anything** — prices move, and this file "
          "has a timestamp.",
          "",
          *hot_section(),
          *flags_section(),
          f"## Heaviest favorites through Sunday {sunday} (-350 or better, de-vigged)",
          "",
          heaviest_table(sunday),
          "",
          "## Candidate tickets",
          "",
          try_ticket(f"~21x through Sunday {sunday} (max hit probability)",
                     21, [f"--by={sunday}", "--minprice=350", "--nofam=ML"],
                     range(22, 13, -1)),
          "",
          try_ticket(f"~12x through Sunday {sunday}, baseball capped at 4 legs",
                     12, [f"--by={sunday}", "--minprice=350", "--nofam=ML",
                          "--maxmlb=4"],
                     range(20, 11, -1)),
          "",
          try_ticket("~10x tonight only (everything settles today, ET)",
                     10, [f"--by={_today_et().isoformat()}", "--minprice=300",
                          "--nofam=ML"],
                     range(16, 7, -1)),
          ""]
    with open(os.path.join(HERE, "BOARD.md"), "w") as fh:
        fh.write("\n".join(md))
    print("wrote BOARD.md")


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    ch = {'stats': {'n': 321, 'home_pct': 0.533, 'mean_total': 51.48,
                    'rungs': {'49.5': {'p_under': 0.467, 'n': 321}}}}
    legs = [
        {'fam': 'CFL', 'lab': 'WPG@SSK Under 49.5', 'price': -180, 'p': 0.70},
        {'fam': 'CFL', 'lab': 'WPG@SSK Over 49.5', 'price': -105, 'p': 0.51},
        {'fam': 'CFL', 'lab': 'WPG@SSK Under 40.5', 'price': -300, 'p': 0.75},
        {'fam': 'FG', 'lab': 'CIN@CWS Under 9.5', 'price': -300, 'p': 0.90},
    ]
    out = cfl_flags(legs, ch)
    chk(any('Under 49.5' in l and 'market 70% vs base 47%' in l
            and 'market >> base' in l for l in out),
        "a market 23 points over four seasons of results is SHOUTED")
    chk(any('Over 49.5' in l and 'base 53%' in l
            and 'market >> base' not in l for l in out),
        "the over side prices against 1-p_under and a 2-point gap stays quiet")
    chk(not any('40.5' in l for l in out) and not any('CIN@CWS' in l for l in out),
        "an unmeasured rung and a non-CFL leg say nothing")
    chk(out[0].startswith('## CFL legs vs measured base (cflhist n=321'),
        "the header carries n, home edge and mean total")
    chk(cfl_flags([{'fam': 'FG', 'lab': 'x Under 9.5', 'p': .9}], ch) == [],
        "no CFL legs -> no section, not an empty header")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest() if '--selftest' in sys.argv else main())
