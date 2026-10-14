"""Aid-type (budget support) tallies, AfDB status-1 records, type-3 government providers, and one-activity dump.
Usage: aidtype_status.py AFDB_PARSED.json WB_PARSED.json RECORDS.json [ACTIVITY_ID]"""
import sys, json
from collections import Counter, defaultdict
A = {a["id"]: a for a in json.load(open(sys.argv[1]))}; W = {a["id"]: a for a in json.load(open(sys.argv[2]))}
recs = json.load(open(sys.argv[3]))
for ln, acts in (("AfDB", A), ("WB", W)):
    n = Counter(); s = defaultdict(float)
    for r in recs:
        if r["ln"] != ln: continue
        k = tuple(sorted({x[1] for x in acts[r["id"]]["aid"] if x[0] in (None, "1")})) or ("none",)
        n[k] += 1; s[k] += r["com"]
    bs = [k for k in n if {"A01", "A02"} & set(k)]
    print(ln, "aid types:", {k: (n[k], round(s[k] / 1e9, 1)) for k in n}, "| budget support A01/A02:", sum(n[k] for k in bs), "activities, USD", round(sum(s[k] for k in bs) / 1e9, 1), "bn")
ann = [r for r in recs if r["ln"] == "AfDB" and r["raw"] == "1"]
print("AfDB status-1 records:", len(ann), "with type-2:", sum(1 for r in ann if any(t["type"] == "2" for t in A[r["id"]]["txs"])),
      "UA", round(sum(t["value"] for r in ann for t in A[r["id"]]["txs"] if t["type"] == "2") / 1e9, 2), "bn; with actual start date:", sum(1 for r in ann if "2" in A[r["id"]]["dates"]))
g3 = [(r["id"], t["value"]) for r in recs if r["ln"] == "AfDB" for t in A[r["id"]]["txs"] if t["type"] == "3" and (t["prov_ref"] or "").endswith("-COA-GOV")]
print("AfDB type-3 transactions from a -COA-GOV provider:", len(g3), round(sum(v for _, v in g3) / 1e6, 1), "UA m")
print("WB type-2 provider refs:", Counter(t["prov_ref"] for r in recs if r["ln"] == "WB" for t in W[r["id"]]["txs"] if t["type"] == "2"))
if len(sys.argv) > 4:
    a = A.get(sys.argv[4]) or W.get(sys.argv[4])
    print(a["id"], a["title"], a["dates"], "status", a["status"], a["aid"])
    for t in a["txs"]:
        if t["type"] == "2": print("  type 2", t["value"], t["date"], t["prov_ref"], t["prov_name"], "|", t["desc"])
