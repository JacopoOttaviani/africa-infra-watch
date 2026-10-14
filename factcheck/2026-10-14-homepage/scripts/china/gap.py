import sys, json, collections
D = json.load(open(sys.argv[1])); keep_ids = set(json.load(open(sys.argv[2])))
site = json.load(open(sys.argv[3]))
site_ids = set(f["properties"]["aiddata_id"] for f in site["features"])
rows = {r["AidData Record ID"]: r for r in D["rows"]}
print("site", len(site_ids), "mine", len(keep_ids), "site-not-mine", len(site_ids-keep_ids))
miss = sorted(keep_ids - site_ids)
print("missing", len(miss))
amt = 0
for i in miss:
    r = rows[i]
    a = r["Amount (Constant USD 2021)"]
    amt += a if isinstance(a,(int,float)) else 0
    print(i, r["Recipient ISO-3"], r["Recipient"], r["Status"], r["Flow Type Simplified"], r["Financial Distress"], r["Co-financed"], r["Geographic Level of Precision Available"], r["Geospatial Feature Available"], a, (r["Title"] or "")[:90])
print("missing amount bn", amt/1e9)
