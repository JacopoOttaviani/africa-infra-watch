import json, sys, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip
qb, bm, sigf = sys.argv[1], sys.argv[2], sys.argv[3]
clip.load(bm)
d = json.load(open(qb))
els = [e for e in d["elements"] if e["type"] != "count"]
by = collections.defaultdict(list)
for e in els: by[e["tags"]["set"]].append(e)
# code set: rail + aeroway=construction
code = []
for e in by["code"]:
    lon, lat = e["geometry"]["coordinates"]; iso = clip.country(lon, lat)
    t = e["tags"]
    if not iso: continue
    kind = ""
    for k in ("rw", "ae", "hw"):
        if t[k] in ("construction", "proposed"): kind = t[k]; break
    sector = "rail" if t["rw"] else "air" if t["ae"] else "road"
    code.append((iso, sector, kind, t["name"], float(t["len"] or 0), e["id"], t))
print("code set (rail+aeroway) raw:", len(by["code"]), "clipped:", len(code))
print(" by sector/kind:", collections.Counter((r[1], r[2]) for r in code))
air = [r for r in code if r[1] == "air"]
for r in air: print("   AIR way", r[5], r[0], r[3], r[6])
rail = [r for r in code if r[1] == "rail"]
print(" rail km:", round(sum(r[4] for r in rail)/1000), " rail classes:", collections.Counter((r[6]["c"] or r[6]["p"] or "-") for r in rail).most_common(12))
sig = json.load(open(sigf))
allseg = len(sig) + len(code)
print("TOTAL segments (sig roads + rail + air):", allseg)
print(" status: construction", sum(1 for r in sig if r[1]=="construction") + sum(1 for r in code if r[2]=="construction"),
      " proposed", sum(1 for r in sig if r[1]=="proposed") + sum(1 for r in code if r[2]=="proposed"))
print(" km total:", round((sum(r[4] for r in sig) + sum(r[4] for r in code))/1000))
countries = {r[0] for r in sig} | {r[0] for r in code}
print(" countries:", len(countries))
# works
groups = set(); loose = collections.Counter(); gstat = {}
for r in sig:
    if r[3]: groups.add((r[3], "road")); gstat.setdefault((r[3],"road"), r[1])
    else: loose[("road", r[1])] += 1
for r in code:
    if r[3]: groups.add((r[3], r[1])); gstat.setdefault((r[3], r[1]), r[2])
    else: loose[(r[1], r[2])] += 1
nworks = len(groups) + sum(loose.values())
print(" works:", nworks, " named:", len(groups), f"({len(groups)/nworks:.1%})")
sec = collections.Counter(s for _, s in groups)
for (s, k), v in loose.items(): sec[s] += v
print(" works by sector:", sec)
ws = collections.Counter(gstat.values())
for (s, k), v in loose.items(): ws[k] += v
print(" works by status (first segment's status for named groups):", ws)
# airport alternatives
print("\nAIRPORT alternatives (nwr):", len(by["air"]))
aa = []
for e in by["air"]:
    lon, lat = e["geometry"]["coordinates"]; iso = clip.country(lon, lat)
    if iso: aa.append((iso, e["tags"]))
print(" clipped to Africa:", len(aa))
cc = collections.Counter((t["otype"], t["ae"] or "-", (t["c"] or "-")[:20], t["cae"] or "-", t["pae"] or "-", t["lu"] or "-") for _, t in aa)
for k, v in cc.most_common(40): print("  ", v, k)
print(" named airport-related features:")
for iso, t in aa:
    if t["name"] and (t["ae"] in ("aerodrome","construction","proposed","terminal","runway") or t["cae"] or t["pae"] or t["lu"]):
        print("   ", iso, t["otype"], t["ae"], t["c"], t["cae"], t["pae"], t["lu"], "|", t["name"][:60])
# islands
print("\nISLANDS (outside bbox or basemap):", len(by["island"]))
SIG = set("motorway trunk primary secondary motorway_link trunk_link primary_link".split())
isl = []
for e in by["island"]:
    t = e["tags"]; lon, lat = e["geometry"]["coordinates"]
    cls = t["c"] if t["hw"] == "construction" else t["p"] if t["hw"] == "proposed" else None
    keep = bool(t["rw"]) or bool(t["ae"]) or cls in SIG
    isl.append((round(lon,2), round(lat,2), t["hw"], t["rw"], t["ae"], cls, t["name"], keep, float(t["len"] or 0)))
print(" would pass the code's class filter:", sum(1 for r in isl if r[7]), " km:", round(sum(r[8] for r in isl if r[7])/1000,1))
for r in isl:
    if r[7]: print("   ", r)
