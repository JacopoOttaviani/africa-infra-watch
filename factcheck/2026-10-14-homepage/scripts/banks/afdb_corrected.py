"""AfDB totals: site rule (all type-2) vs MapAfrica's 'African Development Bank Group' grouping
(all type-2 except government counterpart funds, provider ref *-COA-GOV) vs strict own resources.
Usage: afdb_corrected.py PARSED.json"""
import sys, json
from collections import Counter
R = 1.35
acts = [a for a in json.load(open(sys.argv[1])) if a["infra"] and a["locs"] > 0]
def is_gov(t): return (t["prov_ref"] or "").endswith("-COA-GOV")
OWN = {"XM-DAC-46002", "XM-DAC-46003", "XM-DAC-NTF", "XM-DAC-TSF"}
site = grp = own = gov = dis = 0.0
rows = []
for a in acts:
    c2 = [t for t in a["txs"] if t["type"] == "2"]
    s = sum(t["value"] for t in c2); g = sum(t["value"] for t in c2 if not is_gov(t))
    o = sum(t["value"] for t in c2 if t["prov_ref"] in OWN)
    d = sum(t["value"] for t in a["txs"] if t["type"] == "3")
    site += s; grp += g; own += o; dis += d
    rows.append((s, g, a["id"], a["title"], a["status"], d))
print("None-provider type-2:", [(a["id"], t["value"], t["prov_name"], t["ref"]) for a in acts for t in a["txs"] if t["type"] == "2" and not t["prov_ref"]])
print(f"site rule (all type-2):        {site/1e9:7.3f} bn XDR = USD {site*R/1e9:6.1f} bn")
print(f"excl. government counterpart:  {grp/1e9:7.3f} bn XDR = USD {grp*R/1e9:6.1f} bn  (government share {(site-grp)/1e9:.3f} bn XDR = USD {(site-grp)*R/1e9:.1f} bn = {(site-grp)/site:.1%})")
print(f"AfDB+ADF+NTF+TSF only:         {own/1e9:7.3f} bn XDR = USD {own*R/1e9:6.1f} bn")
print(f"disbursed (type 3, all):       {dis/1e9:7.3f} bn XDR = USD {dis*R/1e9:6.1f} bn; {dis/site:.1%} of site, {dis/grp:.1%} of excl-gov")
print("activities carrying a government counterpart commitment:", sum(1 for r in rows if r[0] > r[1]))
print("TOP 12 by site rule -> corrected (USD m):")
for s, g, i, t, st, d in sorted(rows, reverse=True)[:12]: print(f"  {s*R/1e6:9.1f} -> {g*R/1e6:9.1f}  {i}  {t[:60]}")
print("TOP 12 by corrected rule (USD m):")
for s, g, i, t, st, d in sorted(rows, key=lambda r: -r[1])[:12]: print(f"  {g*R/1e6:9.1f} (site {s*R/1e6:9.1f})  st={st}  {i}  {t[:60]}")
