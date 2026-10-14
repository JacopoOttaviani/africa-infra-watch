import sys, json, re
D = json.load(open(sys.argv[1]))
rows = {r["AidData Record ID"]: r for r in D["rows"]}
ids = [int(x) for x in sys.argv[3:]]
pat = re.compile(sys.argv[2])
for i in ids:
    r = rows[i]
    for k in ("Description","Staff Comments"):
        t = str(r[k] or "")
        for m in pat.finditer(t):
            s = max(0, m.start()-500); e = min(len(t), m.end()+400)
            print(f"[{i} {k}] ...{t[s:e]}...\n")
