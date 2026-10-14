import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip
qa, bm, thr = sys.argv[1], sys.argv[2], int(sys.argv[3])
clip.load(bm)
A = [e for e in json.load(open(qa))["elements"] if e["type"] != "count"]
n = tot = 0
for e in A:
    if clip.country(*e["geometry"]["coordinates"]):
        tot += 1
        if e["id"] > thr: n += 1
print(f"clipped road ways today {tot:,}; created after way id {thr} (~18 Sep 2026 fetch): {n:,}")
