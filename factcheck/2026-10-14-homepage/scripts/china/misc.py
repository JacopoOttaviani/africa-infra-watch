import sys, json, collections, re
D = json.load(open(sys.argv[1])); site = json.load(open(sys.argv[2]))
sid = set(f["properties"]["aiddata_id"] for f in site["features"])
C = collections.Counter
R = [r for r in D["rows"] if r["AidData Record ID"] in sid]
byid = {r["AidData Record ID"]: r for r in D["rows"]}
def a(r, f="Amount (Constant USD 2021)"):
    v = r[f]; return v if isinstance(v,(int,float)) else 0
bn = lambda x: round(x/1e9, 2)
print("site loans nominal", bn(sum(a(r,"Amount (Nominal USD)") for r in R if r["Flow Type Simplified"]=="Loan")))
print("site loans nominal RFA only", bn(sum(a(r,"Amount (Nominal USD)") for r in R if r["Flow Type Simplified"]=="Loan" and r["Recommended For Aggregates"]=="Yes")))
noamt = [r for r in R if not isinstance(r["Amount (Constant USD 2021)"],(int,float))]
print("no amount", len(noamt), C(r["Flow Type Simplified"] for r in noamt))
syn = [r for r in R if re.search(r"syndicat|contributes", r["Title"] or "", re.I)]
print("syndicate-titled records", len(syn))
# which site records share an umbrella parent record (umbrella=Yes) in same package
umb_by_parent = collections.defaultdict(list)
for r in D["rows"]:
    if r["Umbrella"]=="Yes":
        for p in str(r["AidData Parent ID"] or "").split("|"):
            if p: umb_by_parent[p].append(r["AidData Record ID"])
split = collections.defaultdict(list)
for r in syn:
    for p in str(r["AidData Parent ID"] or "").split("|"):
        if p: split[p].append(r["AidData Record ID"])
multi = {p: ids for p, ids in split.items() if len(ids) > 1}
print("parent packages with >1 syndicate-titled site record", len(multi))
for p, ids in list(multi.items())[:8]:
    print("  pkg", p, [(i, round(a(byid[i])/1e6), byid[i]["Title"][:60]) for i in ids], "umbrellas", umb_by_parent.get(p))
# Ethiopia-Djibouti gas pipeline 60932 details
r = byid[60932]
print("60932", r["Status"], r["Amount Estimated"], r["Funding Agencies"], r["Co-financing Agencies"])
print(" Staff:", str(r["Staff Comments"])[:900])
