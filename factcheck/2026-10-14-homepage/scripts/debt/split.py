"""Sum PPG series by creditor type per counterpart over the 50 debtors.
    python3 -I split.py <split_2024.json>"""
import json, sys
d = json.load(open(sys.argv[1]))
agg, names = {}, {}
for r in d["source"]["data"]:
    var = {x["concept"]: x for x in r["variable"]}
    if r["value"] is None:
        continue
    k = (var["Counterpart-Area"]["id"], var["Series"]["id"])
    agg[k] = agg.get(k, 0) + r["value"]
    names[var["Series"]["id"]] = var["Series"]["value"]
for s, n in sorted(names.items()):
    print(s, "=", n)
S = ["DT.DOD.DPPG.CD", "DT.DOD.BLAT.CD", "DT.DOD.MLAT.CD", "DT.DOD.PCBK.CD", "DT.DOD.PBND.CD", "DT.DOD.PROP.CD", "DT.DOD.OFFT.CD", "DT.DOD.PRVT.CD"]
print("cp   " + " ".join(f"{s.split('.')[2]:>8}" for s in S))
for cp in ["WLD", "730", "012", "004", "302", "994", "BND"]:
    print(f"{cp:<4} " + " ".join(f"{agg.get((cp, s), 0)/1e9:8.2f}" for s in S))
