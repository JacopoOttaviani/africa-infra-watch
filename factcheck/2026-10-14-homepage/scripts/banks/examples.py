"""For each type-2 provider ref, show an example infra activity whose type-2 providers include it. Usage: examples.py PARSED.json"""
import sys, json
from collections import defaultdict, Counter
acts = [a for a in json.load(open(sys.argv[1])) if a["infra"] and a["locs"] > 0]
ex = {}; allprov = Counter(); sums = defaultdict(float)
for a in acts:
    provs = {t["prov_ref"] for t in a["txs"] if t["type"] == "2"}
    for t in a["txs"]:
        if t["type"] == "2":
            allprov[t["prov_ref"]] += 1; sums[t["prov_ref"]] += t["value"]
    for p in provs:
        if p not in ex or len(provs) < len(ex[p][1]):
            ex[p] = (a["id"], provs)
for p, n in allprov.most_common():
    print(f"{n:5d} {sums[p]/1e6:10.1f}  {p!s:28s} e.g. {ex[p][0]} {sorted(map(str, ex[p][1]))}")
# type 3 providers
c3 = Counter(); s3 = defaultdict(float)
for a in acts:
    for t in a["txs"]:
        if t["type"] == "3": c3[t["prov_ref"]] += 1; s3[t["prov_ref"]] += t["value"]
print("type-3 providers:")
for p, n in c3.most_common(15): print(f"  {n:5d} {s3[p]/1e6:10.1f} {p}")
