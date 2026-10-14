"""Money by the site's sector label (first matching DAC code), per lender, and the DAC codes behind industry/trade/environment.
Usage: sector_money.py RECORDS.json AFDB_PARSED.json WB_PARSED.json"""
import sys, json
from collections import Counter, defaultdict
F = json.load(open(sys.argv[1]))
acts = {("AfDB", a["id"]): a for a in json.load(open(sys.argv[2]))}
acts.update({("WB", a["id"]): a for a in json.load(open(sys.argv[3]))})
m = defaultdict(float); n = Counter(); codes = defaultdict(Counter); codemoney = defaultdict(float)
DAC = [("210", "transport"), ("220", "ict"), ("23", "energy"), ("140", "water"), ("321", "industry"), ("322", "industry"), ("323", "industry"), ("331", "trade"), ("410", "environment")]
for r in F:
    m[(r["ln"], r["sector"])] += r["com"]; n[(r["ln"], r["sector"])] += 1
    a = acts[(r["ln"], r["id"])]
    for c in a["sectors"]:
        hit = next((s for p, s in DAC if c.startswith(p)), None)
        if hit:
            if hit == r["sector"] and hit in ("industry", "trade", "environment"):
                codes[hit][c] += 1; codemoney[(hit, c)] += r["com"]
            break
for k in sorted(m, key=lambda k: -m[k]): print(f"  {k[0]:5s} {k[1]:12s} n={n[k]:4d} USD {m[k]/1e9:6.1f} bn")
for s in ("industry", "trade", "environment"):
    print(s, [(c, k, round(codemoney[(s, c)] / 1e9, 2)) for c, k in codes[s].most_common(8)])
