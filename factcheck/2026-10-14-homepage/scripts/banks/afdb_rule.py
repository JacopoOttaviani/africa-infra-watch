"""Re-derive AfDB commitment totals under the site's rule and under 'AfDB-provided only'.
Usage: afdb_rule.py PARSED.json [SDR_USD]"""
import sys, json
from collections import Counter, defaultdict
acts = [a for a in json.load(open(sys.argv[1])) if a["infra"] and a["locs"] > 0]
rate = float(sys.argv[2]) if len(sys.argv) > 2 else 1.35
print("activities", len(acts), "unique ids", len({a["id"] for a in acts}))
print("default-currency", Counter(a["dc"] for a in acts))
print("tx currency attrs", Counter(t["cur"] for a in acts for t in a["txs"]))
prov = Counter(); provsum = defaultdict(float)
for a in acts:
    for t in a["txs"]:
        if t["type"] == "2":
            k = (t["prov_ref"], (t["prov_name"] or "")[:50]); prov[k] += 1; provsum[k] += t["value"]
print("type-2 provider orgs (count, sum XDR m):")
for k, n in prov.most_common(40): print("  ", n, round(provsum[k] / 1e6, 1), k)
AFDB_REFS = {"XM-DAC-46002", "XM-DAC-46003", "XM-DAC-46004"}
site = afdb = other = 0.0; dis = 0.0
per = []
for a in acts:
    s = sum(t["value"] for t in a["txs"] if t["type"] == "2")
    b = sum(t["value"] for t in a["txs"] if t["type"] == "2" and (t["prov_ref"] in AFDB_REFS))
    d = sum(t["value"] for t in a["txs"] if t["type"] == "3")
    site += s; afdb += b; dis += d
    per.append((s - b, s, b, d, a["id"], a["title"]))
print(f"site rule: {site/1e9:.3f} bn XDR = USD {site*rate/1e9:.1f} bn")
print(f"AfDB-provided only: {afdb/1e9:.3f} bn XDR = USD {afdb*rate/1e9:.1f} bn")
print(f"inflation: {(site-afdb)/1e9:.3f} bn XDR = USD {(site-afdb)*rate/1e9:.1f} bn ({(site-afdb)/site:.1%})")
print(f"disbursed: {dis/1e9:.3f} bn XDR = USD {dis*rate/1e9:.1f} bn; share of site commit {dis/site:.1%}, of AfDB-only commit {dis/afdb:.1%}")
per.sort(reverse=True)
print("activities with non-AfDB commitments:", sum(1 for p in per if p[0] > 0))
for p in per[:25]: print(f"  extra {p[0]*rate/1e6:9.1f}  site {p[1]*rate/1e6:9.1f}  afdb {p[2]*rate/1e6:9.1f} USD m  {p[4]}  {(p[5] or '')[:60]}")
