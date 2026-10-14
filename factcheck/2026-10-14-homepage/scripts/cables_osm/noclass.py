import json, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip
qa, bm = sys.argv[1], sys.argv[2]; clip.load(bm)
A = [e for e in json.load(open(qa))["elements"] if e["type"] != "count"]
nc = []
for e in A:
    t = e["tags"]; cls = t["c"] if t["hw"] == "construction" else t["p"]
    if cls in ("", "yes", "construction", "proposed", "highway", "road"):
        iso = clip.country(*e["geometry"]["coordinates"])
        if iso: nc.append((float(t["len"] or 0)/1000, iso, t["name"], t["hw"], e["id"]))
print("no/vague class ways in Africa:", len(nc), " km:", round(sum(x[0] for x in nc)), " >=5km:", sum(1 for x in nc if x[0] >= 5), " km of those:", round(sum(x[0] for x in nc if x[0] >= 5)))
for x in sorted(nc, reverse=True)[:12]: print("   ", round(x[0],1), x[1], x[2][:60], x[3], "way/%d" % x[4])
