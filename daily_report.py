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
    return lines


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


if __name__ == "__main__":
    main()
