#!/usr/bin/env python3
"""srcprobe.py — which data sources can the runner actually reach?

Round 3. Round 2's SBR probe answered HTTP 200 on both mlb-odds xlsx paths —
but the body was ~67KB of HTML, not a spreadsheet (a real xlsx starts with
PK zip magic). The site is WordPress now; the old /scoresoddsarchives/mlb/
file paths render a page instead of a file. Round 3 asks the pages
themselves where the files went: fetch the plausible archive pages and list
every xlsx/xls/csv href in the returned HTML. Either a real download URL
falls out (rung-x-posted-line calibration proceeds) or none exists on any
page (the item gets recorded measured-absent, honestly).
"""
import re, sys, urllib.request

BUA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
T = [
 ("xlsx path 2023",   "https://www.sportsbookreviewsonline.com/scoresoddsarchives/mlb/mlb%20odds%202023.xlsx"),
 ("old archive page", "https://www.sportsbookreviewsonline.com/scoresoddsarchives/mlb/mlbaoddsarchives.htm"),
 ("wp page 2023",     "https://www.sportsbookreviewsonline.com/scoresoddsarchives/mlb-odds-2023/"),
 ("wp page 2024",     "https://www.sportsbookreviewsonline.com/scoresoddsarchives/mlb-odds-2024/"),
 ("archives index",   "https://www.sportsbookreviewsonline.com/scoresoddsarchives/"),
]

for name, url in T:
    try:
        h = {"User-Agent": BUA}
        r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=25)
        b = r.read(400000)
        if b[:2] == b"PK":
            print(f"  {name:<18} HTTP {r.status}  {len(b)}B  REAL SPREADSHEET (PK magic)")
            continue
        html = b.decode("utf-8", "replace")
        links = re.findall(r'href="([^"]+\.(?:xlsx|xls|csv)[^"]*)"', html, re.I)
        seen = list(dict.fromkeys(links))
        print(f"  {name:<18} HTTP {r.status}  {len(b)}B html, {len(seen)} file link(s)")
        for l in seen[:8]:
            print(f"      {l}")
        if not seen:
            # no file links -- say what the page is instead of nothing
            t = re.search(r"<title>([^<]*)</title>", html, re.I)
            print(f"      (no xlsx/xls/csv hrefs; title: {t.group(1).strip() if t else '?'})")
    except Exception as e:
        print(f"  {name:<18} FAIL {type(e).__name__} {getattr(e, 'code', '')}")
