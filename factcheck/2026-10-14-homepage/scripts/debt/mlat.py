"""Which counterparts IDS itself classes multilateral vs bilateral vs private (2024, 50 debtors).
    python3 -I mlat.py <counterpart_list.json> <page files...>"""
import json, sys
names = {v["id"]: " ".join(v["value"].split()) for v in json.load(open(sys.argv[1]))["source"][0]["concept"][0]["variable"]}
agg = {}
for p in sys.argv[2:]:
    for r in json.load(open(p))["source"]["data"]:
        if not r["value"]:
            continue
        var = {x["concept"]: x for x in r["variable"]}
        k = (var["Counterpart-Area"]["id"], var["Series"]["id"].split(".")[2])
        agg[k] = agg.get(k, 0) + r["value"]
INST = {"019", "237", "877", "878", "887", "888", "890", "892", "893", "895", "896", "897", "898", "899"} | {f"{n:03d}" for n in range(802, 820)}
site_multi = lambda c: c in INST or (c.isdigit() and int(c) >= 901 and c != "994")
cps = sorted({c for c, _ in agg})
tot = {s: sum(v for (c, ss), v in agg.items() if ss == s and c != "WLD") for s in ("MLAT", "BLAT", "PRVT")}
print("WLD rows:", {s: round(agg.get(("WLD", s), 0) / 1e9, 2) for s in ("MLAT", "BLAT", "PRVT")})
print("sum over counterparts:", {s: round(v / 1e9, 2) for s, v in tot.items()})
print("\nSite-multilateral codes with non-MLAT money (bn):")
for c in cps:
    if c == "WLD" or not site_multi(c):
        continue
    b, pr = agg.get((c, "BLAT"), 0), agg.get((c, "PRVT"), 0)
    if b + pr > 1e6:
        print(f"  {c} {names.get(c)}: MLAT {agg.get((c,'MLAT'),0)/1e9:.3f} BLAT {b/1e9:.3f} PRVT {pr/1e9:.3f}")
print("\nNon-site-multilateral codes with MLAT money (bn):")
for c in cps:
    if c != "WLD" and not site_multi(c) and agg.get((c, "MLAT"), 0) > 1e6:
        print(f"  {c} {names.get(c)}: MLAT {agg[(c,'MLAT')]/1e9:.3f}")
