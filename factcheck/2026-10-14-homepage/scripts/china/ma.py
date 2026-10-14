import sys, json
D = json.load(open(sys.argv[1])); site = json.load(open(sys.argv[2]))
sid = set(f["properties"]["aiddata_id"] for f in site["features"])
for r in D["rows"]:
    if r["AidData Record ID"] in sid and (r["M&A"]=="Yes" or r["AidData Record ID"] in (89500,)):
        print(r["AidData Record ID"], r["Recipient"], r["Commitment Year"], round((r["Amount (Constant USD 2021)"] or 0)/1e6,1), r["Sector Name"], r["Level of Public Liability"], "|", r["Title"][:140])
r = {x["AidData Record ID"]: x for x in D["rows"]}[60932]
import re
d = str(r["Description"]); 
for kw in ("construction","no evidence","begun","stall"):
    for m in re.finditer(kw, d, re.I):
        print("60932 desc:", d[max(0,m.start()-200):m.end()+200].replace("\n"," ")); break
