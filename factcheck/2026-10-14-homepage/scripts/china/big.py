import sys, json, collections
D = json.load(open(sys.argv[1])); keep_ids = set(json.load(open(sys.argv[2])))
site = json.load(open(sys.argv[3]))
site_ids = set(f["properties"]["aiddata_id"] for f in site["features"])
rows = [r for r in D["rows"] if r["AidData Record ID"] in site_ids]
def a(r): v=r["Amount (Constant USD 2021)"]; return v if isinstance(v,(int,float)) else 0
rows.sort(key=a, reverse=True)
for r in rows[:30]:
    print(r["AidData Record ID"], "|", round(a(r)/1e6,1), "| nomUSD", round((r["Amount (Nominal USD)"] or 0)/1e6,1), "| orig", r["Amount (Original Currency)"], r["Original Currency"], "| yr", r["Commitment Year"], "| RFA", r["Recommended For Aggregates"], "| umb", r["Umbrella"], "| parent", r["AidData Parent ID"], "| status", r["Status"], "| sector", r["Sector Name"], "| est", r["Amount Estimated"], "|", (r["Title"] or "")[:110])
