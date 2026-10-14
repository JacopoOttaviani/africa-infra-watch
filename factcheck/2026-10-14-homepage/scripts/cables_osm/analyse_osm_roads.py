import json, sys, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip
qa, bm = sys.argv[1], sys.argv[2]
clip.load(bm)
d = json.load(open(qa))
els = [e for e in d["elements"] if e["type"] != "count"]
cnt = [e for e in d["elements"] if e["type"] == "count"]
print("raw count statement:", cnt[0]["tags"] if cnt else None, "elements:", len(els))
SIG = set("motorway trunk primary secondary motorway_link trunk_link primary_link".split())
rows = []
for e in els:
    lon, lat = e["geometry"]["coordinates"]
    iso = clip.country(lon, lat)
    t = e["tags"]
    cls = t["c"] if t["hw"] == "construction" else t["p"]
    rows.append((iso, t["hw"], cls, t["name"], float(t["len"] or 0), t["rw"], t["ae"], e["id"]))
af = [r for r in rows if r[0]]
print("in Africa (basemap clip on bbox centre):", len(af), "dropped:", len(rows) - len(af))
sig = [r for r in af if r[2] in SIG]
print("SIGNIFICANT road segments:", len(sig), " construction:", sum(r[1]=="construction" for r in sig), " proposed:", sum(r[1]=="proposed" for r in sig))
print("SIGNIFICANT road km (server length):", round(sum(r[4] for r in sig)/1000))
print("SIG with railway tag:", sum(1 for r in sig if r[5]), "with aeroway tag:", sum(1 for r in sig if r[6]))
print("SIG countries:", len({r[0] for r in sig}))
c = collections.Counter(r[2] or "(none)" for r in af)
print("all classes (clipped), top 25:")
for k, v in c.most_common(25): print(f"   {k:20s} {v:7d} {v/len(af):6.1%}")
print("total clipped all road classes:", len(af), " ratio to SIG:", round(len(af)/len(sig), 2))
st = collections.Counter(r[1] for r in af); print("all classes by highway=", st)
small = {"residential","service","unclassified","tertiary","living_street","track","footway","path","pedestrian","cycleway","steps","tertiary_link","secondary_link","road","yes","bridleway","busway","raceway","construction","proposed",""}
print("named share SIG segments:", round(sum(1 for r in sig if r[3])/len(sig)*100,1), "%")
# works grouping like build_map: (name, sector) groups + loose unnamed
g = set(); loose = 0
for r in sig:
    if r[3]: g.add((r[3], "road"))
    else: loose += 1
print("road works (name groups + unnamed):", len(g) + loose, " named groups:", len(g))
json.dump([list(r) for r in sig], open(os.path.join(os.path.dirname(qa), "sig_roads_clipped.json"), "w"))
json.dump(dict(c), open(os.path.join(os.path.dirname(qa), "all_road_classes_clipped.json"), "w"))
