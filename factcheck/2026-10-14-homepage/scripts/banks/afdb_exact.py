"""AfDB rank-0 ('exact site') markers: location-class of the chosen point and whether it is a shared default point.
Usage: afdb_exact.py AFDB_PARSED.json"""
import sys, json
from collections import Counter
WIN = (-30.0, -40.0, 65.0, 40.0)
acts = [a for a in json.load(open(sys.argv[1])) if a["infra"] and a["pts"]]
allpts = Counter(); best = {}
def ok(p): return (p[0], p[1]) != (0.0, 0.0) and WIN[0] <= p[0] <= WIN[2] and WIN[1] <= p[1] <= WIN[3]
for a in acts:
    good = [p for p in a["pts"] if ok(p)]
    for p in {(round(p[0], 4), round(p[1], 4)) for p in good}: allpts[p] += 1
    if good:
        # build_map keeps the FIRST location at the best rank (strict '<')
        b = None; br = 9
        for p in good:
            r = 0 if p[2] == "1" else 1 if p[3] in ("2", "4") else 2
            if r < br: b, br = p, r
        best[a["id"]] = (br, b)
r0 = [b for r, b in best.values() if r == 0]
print("rank-0 markers:", len(r0), "location-class of chosen point:", Counter(b[3] for b in r0))
for th in (2, 5, 10):
    print(f"  on a point shared by >={th} activities:", sum(1 for b in r0 if allpts[(round(b[0], 4), round(b[1], 4))] >= th))
r0u = [b for b in r0 if allpts[(round(b[0], 4), round(b[1], 4))] == 1]
print("  rank-0 on a point unique to the activity:", len(r0u), "class:", Counter(b[3] for b in r0u))
print("top shared rank-0 points:", Counter((round(b[0], 3), round(b[1], 3)) for b in r0).most_common(6))
