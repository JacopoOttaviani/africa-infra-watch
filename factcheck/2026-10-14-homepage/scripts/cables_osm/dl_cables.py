import json, sys, time, urllib.request, os
allf, outdir = sys.argv[1], sys.argv[2]
ids = [c["id"] for c in json.load(open(allf)) if c.get("id")]
UA = {"User-Agent": "africa-project-atlas-factcheck/0.1"}
fail = []
for i, cid in enumerate(ids, 1):
    p = os.path.join(outdir, cid.replace("/", "_") + ".json")
    if os.path.exists(p) and os.path.getsize(p) > 0:
        continue
    for a in range(3):
        try:
            req = urllib.request.Request(f"https://www.submarinecablemap.com/api/v3/cable/{cid}.json", headers=UA)
            b = urllib.request.urlopen(req, timeout=60).read()
            open(p, "wb").write(b)
            break
        except Exception as e:
            if a == 2: fail.append((cid, str(e)))
            time.sleep(2 + 3*a)
    time.sleep(0.15)
    if i % 100 == 0: print(i, flush=True)
print("done", len(ids), "failed", fail)
