"""Year totals (WLD) over downloaded debtors, China share by year, and a few specific lookups.
    python3 -I years.py <by_debtor_dir>"""
import json, os, sys
D = sys.argv[1]
tot, china, bnd, by_iso_2024 = {}, {}, {}, {}
isr = {}
for f in sorted(os.listdir(D)):
    raw = open(os.path.join(D, f), encoding="utf-8").read()
    if not raw.lstrip().startswith("{"):
        continue
    for r in json.loads(raw)["source"]["data"]:
        if r["value"] is None:
            continue
        var = {x["concept"]: x for x in r["variable"]}
        y = int(var["Time"]["value"]); cp = var["Counterpart-Area"]["id"]; iso = var["Country"]["id"]
        if cp == "WLD":
            tot[y] = tot.get(y, 0) + r["value"]
            if y == 2024: by_iso_2024[iso] = r["value"]
        elif cp == "730":
            china[y] = china.get(y, 0) + r["value"]
        elif cp == "BND":
            bnd[y] = bnd.get(y, 0) + r["value"]
        elif cp == "546" and y == 2024:
            isr[iso] = r["value"]
for y in range(2000, 2025):
    print(y, f"{tot.get(y,0)/1e9:7.1f}", f"china {china.get(y,0)/1e9:6.1f} ({china.get(y,0)/tot[y]*100:4.1f}%)", f"bonds {bnd.get(y,0)/1e9:6.1f}")
print("peak year", max(tot, key=lambda y: tot[y] if y >= 2000 else 0))
print("DJI 2024", by_iso_2024.get("DJI", 0)/1e9)
print("Israel 2024 by debtor", {k: round(v/1e9, 3) for k, v in isr.items()})
