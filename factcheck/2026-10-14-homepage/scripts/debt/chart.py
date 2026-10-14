"""Pull DATA.debt.africa from docs/dashboard.html line 914 and print per-year totals.
    python3 -I chart.py <dashboard.html>"""
import json, sys
for line in open(sys.argv[1], encoding="utf-8"):
    if line.startswith("const DATA = "):
        d = json.loads(line[len("const DATA = "):].rstrip().rstrip(";"))
        break
db = d["debt"]
a = db["africa"]
print("from", db["from"], "to", db["to"], "updated", db["updated"], "n", a["n"], "imf", a["imf"])
print("groups", db["groups"])
print("g", a["g"], "sum", sum(a["g"]))
print("top", a["top"])
for i, row in enumerate(a["s"]):
    print(db["from"] + i, round(sum(row) / 1000, 1))
