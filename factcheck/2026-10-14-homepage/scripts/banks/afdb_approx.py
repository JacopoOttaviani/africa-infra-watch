"""For AfDB activities whose best point is approximate (exactness 2) with location-class 2/4, test
whether that point is shared by many activities (a country default point) or distinct (a real place).
Usage: afdb_approx.py AFDB_PARSED.json"""
import sys, json
from collections import Counter
WIN = (-30.0, -40.0, 65.0, 40.0)
acts = [a for a in json.load(open(sys.argv[1])) if a["infra"] and a["pts"]]
best = {}
allpts = Counter()
for a in acts:
    good = [p for p in a["pts"] if (p[0], p[1]) != (0.0, 0.0) and WIN[0] <= p[0] <= WIN[2] and WIN[1] <= p[1] <= WIN[3]]
    for p in good: allpts[(round(p[0], 4), round(p[1], 4))] += 1
    if not good: continue
    rk = sorted(good, key=lambda p: 0 if p[2] == "1" else 1 if p[3] in ("2", "4") else 2)[0]
    best[a["id"]] = rk
r1 = {i: p for i, p in best.items() if p[2] != "1" and p[3] in ("2", "4")}
shared = sum(1 for p in r1.values() if allpts[(round(p[0], 4), round(p[1], 4))] >= 5)
print("rank-1 AfDB markers:", len(r1), "of which on a point used >=5 times across activities:", shared)
print("most-used points:", allpts.most_common(8))
