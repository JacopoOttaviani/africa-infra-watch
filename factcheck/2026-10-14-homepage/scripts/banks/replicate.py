"""Rebuild the site's finance-layer statistics straight from the upstream IATI XML (parsed).
Usage: replicate.py AFDB_PARSED.json WB_PARSED.json
Mirrors fetch_iati + place_iati + build_map.build_finance (infra DAC filter, window, best-precision marker)."""
import sys, json
from collections import Counter
SDR = 1.35
WIN = (-30.0, -40.0, 65.0, 40.0)
STATUS = {"1": "announced", "2": "building", "3": "operating", "4": "operating", "5": "stalled", "6": "stalled"}
DAC = [("210", "transport"), ("220", "ict"), ("23", "energy"), ("140", "water"), ("321", "industry"),
       ("322", "industry"), ("323", "industry"), ("331", "trade"), ("410", "environment")]
def recs(fn, ln):
    out = []
    for a in json.load(open(fn)):
        if not a["infra"] or not a["pts"]:
            continue
        good = [p for p in a["pts"] if (p[0], p[1]) != (0.0, 0.0) and WIN[0] <= p[0] <= WIN[2] and WIN[1] <= p[1] <= WIN[3]]
        if good:
            ranks = [0 if p[2] == "1" else 1 if p[3] in ("2", "4") else 2 for p in good]
            rank = min(ranks)
        elif a["country"]:
            rank = 2
        else:
            continue
        sector = None
        for c in a["sectors"]:
            for pre, s in DAC:
                if c.startswith(pre): sector = s; break
            if sector: break
        rate = SDR if ln == "AfDB" else 1.0
        com = sum(t["value"] for t in a["txs"] if t["type"] == "2") * rate
        com_ng = sum(t["value"] for t in a["txs"] if t["type"] == "2" and not (t["prov_ref"] or "").endswith("-COA-GOV")) * rate
        dis = sum(t["value"] for t in a["txs"] if t["type"] == "3") * rate
        out.append(dict(id=a["id"], ln=ln, iso=a["country"], rank=rank, sector=sector or "other", status=STATUS.get(a["status"]),
                        com=com, com_ng=com_ng, dis=dis, title=a["title"], raw=a["status"], dates=a.get("dates", {})))
    return out
A = recs(sys.argv[1], "AfDB"); W = recs(sys.argv[2], "WB"); F = A + W
print("activities: AfDB", len(A), "WB", len(W), "total", len(F))
print("countries:", len({r["iso"] for r in F if r["iso"]}))
for lab, S in (("AfDB", A), ("WB", W)):
    c = sum(r["com"] for r in S); d = sum(r["dis"] for r in S); cng = sum(r["com_ng"] for r in S)
    print(f"{lab}: committed USD {c/1e9:.1f} bn (excl. gov counterpart {cng/1e9:.1f} bn), disbursed {d/1e9:.1f} bn = {d/c:.0%} (of excl-gov {d/cng:.0%})")
c = sum(r["com"] for r in F); d = sum(r["dis"] for r in F)
print(f"total committed {c/1e9:.1f} bn, disbursed {d/1e9:.1f} bn")
print("AfDB exact share", f"{sum(r['rank']==0 for r in A)/len(A):.1%}", " WB named place share", f"{sum(r['rank']<=1 for r in W)/len(W):.1%}",
      " all site-or-place", f"{sum(r['rank']<=1 for r in F)/len(F):.1%}")
print("multinational (no recipient-country): AfDB", sum(1 for r in A if not r["iso"]), "WB", sum(1 for r in W if not r["iso"]))
print("status all", Counter(r["status"] for r in F)); print("status AfDB", Counter(r["status"] for r in A)); print("status WB", Counter(r["status"] for r in W))
print("sector", Counter(r["sector"] for r in F).most_common())
json.dump(F, open(sys.argv[3], "w")) if len(sys.argv) > 3 else None
