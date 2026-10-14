import json, sys, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip
qa, qb, bm = sys.argv[1:4]
clip.load(bm)
A = [e for e in json.load(open(qa))["elements"] if e["type"] != "count"]
B = [e for e in json.load(open(qb))["elements"] if e["type"] != "count" and e["tags"].get("set") == "code"]
SIG = set("motorway trunk primary secondary motorway_link trunk_link primary_link".split())
def rows(els):
    out = []
    for e in els:
        lon, lat = e["geometry"]["coordinates"]; iso = clip.country(lon, lat)
        if iso: out.append((iso, e["tags"], e["id"], lon, lat))
    return out
ra, rb = rows(A), rows(B)
def cls(t): return t["c"] if t["hw"] == "construction" else t["p"]
sig = [r for r in ra if cls(r[1]) in SIG]
def works(road_rows, other_rows):
    g = set(); loose = 0
    for r in road_rows:
        if r[1]["name"]: g.add((r[1]["name"], "road"))
        else: loose += 1
    for r in other_rows:
        s = "rail" if r[1]["rw"] else "air"
        if r[1]["name"]: g.add((r[1]["name"], s))
        else: loose += 1
    return len(g) + loose
fs, us = len(sig) + len(rb), len(ra) + len(rb)
fw, uw = works(sig, rb), works(ra, rb)
print(f"segments: filtered {fs:,}  unfiltered {us:,}  ratio {us/fs:.1f}x")
print(f"works:    filtered {fw:,}  unfiltered {uw:,}  ratio {uw/fw:.1f}x")
km_f = sum(float(r[1]["len"]) for r in sig + rb)/1000; km_u = sum(float(r[1]["len"]) for r in ra + rb)/1000
print(f"km:       filtered {km_f:,.0f}  unfiltered {km_u:,.0f}  ratio {km_u/km_f:.1f}x")
exc = [r for r in ra if cls(r[1]) not in SIG]
c = collections.Counter(cls(r[1]) or "(no class tag)" for r in exc)
print("excluded segments:", len(exc), " residential+service share:", f"{(c['residential']+c['service'])/len(exc):.0%}")
# residential by country
rc = collections.Counter(r[0] for r in exc if cls(r[1]) == "residential")
print("residential by country top 8:", rc.most_common(8))
# only residential+service excluded (literal reading of 'small residential and service streets are excluded')
lit = len(ra) - sum(1 for r in ra if cls(r[1]) in ("residential", "service")) + len(rb)
print(f"if only residential+service were dropped: {lit:,} segments ({lit/fs:.1f}x the filtered count)")
# way-id age proxy for residential
ids = sorted(r[2] for r in exc if cls(r[1]) == "residential")
print("residential way id quartiles:", ids[len(ids)//4], ids[len(ids)//2], ids[3*len(ids)//4], " max id overall:", max(r[2] for r in ra))
# islands within bbox but outside basemap
allA = [(e["geometry"]["coordinates"], e["tags"]) for e in A]
boxes = {"Comoros": (43.1, -12.5, 44.6, -11.3), "Mayotte": (44.9, -13.1, 45.4, -12.6), "Sao Tome & Principe": (6.4, -0.1, 7.5, 1.8), "Bioko(GQ)": (8.3, 3.1, 9.0, 3.9)}
for k, (x0, y0, x1, y1) in boxes.items():
    inb = [(xy, t) for xy, t in allA if x0 <= xy[0] <= x1 and y0 <= xy[1] <= y1]
    s = [t for xy, t in inb if cls(t) in SIG]
    kept = sum(1 for xy, t in inb if cls(t) in SIG and clip.country(*xy))
    print(f"  {k}: {len(inb)} road ways, {len(s)} significant, {kept} kept by the clip")
