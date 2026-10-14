import sys, json, re
D = json.load(open(sys.argv[1])); site = json.load(open(sys.argv[2]))
site_ids = set(f["properties"]["aiddata_id"] for f in site["features"])
pats = sys.argv[3:]
tot = 0; tot_site = 0
for r in D["rows"]:
    txt = " ".join(str(r[k] or "") for k in ("Title","Description","Staff Comments"))
    hit = [p for p in pats if re.search(r"#\s*"+p+r"\b", txt)]
    parent = str(r["AidData Parent ID"] or "")
    if hit or any(p in parent.split("|") for p in pats):
        a = r["Amount (Nominal USD)"]
        insite = r["AidData Record ID"] in site_ids
        if isinstance(a,(int,float)) and r["Recommended For Aggregates"]=="Yes": tot += a
        if isinstance(a,(int,float)) and insite: tot_site += a
        print(r["AidData Record ID"], "site" if insite else "    ", "RFA", r["Recommended For Aggregates"], "umb", r["Umbrella"], "inf", r["Infrastructure"], "parent", parent, "yr", r["Commitment Year"], "nomUSD", round(a/1e6,1) if isinstance(a,(int,float)) else None, r["Status"], "|", (r["Funding Agencies"] or "")[:30], "|", (r["Title"] or "")[:100], "| hit", hit)
print("sum nominal RFA=Yes", tot/1e6, " sum nominal in site", tot_site/1e6)
