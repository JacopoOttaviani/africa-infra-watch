import sys, json, collections
D = json.load(open(sys.argv[1]))
rows = D["rows"]
C = collections.Counter
af = [r for r in rows if r["Recipient Region"] == "Africa"]
print("all rows", len(rows), "Africa rows", len(af))
print("Recipient Region values", C(r["Recipient Region"] for r in rows))
# sequential filter as described
umb = [r for r in af if r["Umbrella"] == "Yes"]
rest = [r for r in af if r["Umbrella"] != "Yes"]
pl = [r for r in rest if r["Status"] == "Pipeline: Pledge"]
rest = [r for r in rest if r["Status"] != "Pipeline: Pledge"]
ni = [r for r in rest if r["Infrastructure"] != "Yes"]
keep = [r for r in rest if r["Infrastructure"] == "Yes"]
print("umbrella", len(umb), "pledge", len(pl), "not infra", len(ni), "keep", len(keep))
print("Umbrella values", C(r["Umbrella"] for r in af), "Infra values", C(r["Infrastructure"] for r in af))
print("Recipients in keep without ISO", C(r["Recipient"] for r in keep if not r["Recipient ISO-3"]))
print("Status", C(r["Status"] for r in keep))
print("countries", len(set(r["Recipient ISO-3"] for r in keep if r["Recipient ISO-3"])))
print("years", min(r["Commitment Year"] for r in keep), max(r["Commitment Year"] for r in keep))
def amt(r, f="Adjusted Amount (Constant USD 2021)"):
    v = r[f]
    return v if isinstance(v,(int,float)) else None
for f in ("Adjusted Amount (Constant USD 2021)", "Amount (Constant USD 2021)", "Amount (Nominal USD)", "Adjusted Amount (Nominal USD)"):
    s = sum(amt(r,f) or 0 for r in keep); n = sum(1 for r in keep if amt(r,f) is not None)
    print(f, round(s/1e9,2), "bn  n with amount", n)
print("Flow Type Simplified", C(r["Flow Type Simplified"] for r in keep))
print("Flow Type", C(r["Flow Type"] for r in keep))
for fs in ("Loan","Grant","Vague"):
    print(" sum", fs, round(sum(amt(r) or 0 for r in keep if r["Flow Type Simplified"]==fs)/1e9,2))
print("Financial Distress", C((r["Flow Type Simplified"], r["Financial Distress"]) for r in keep))
print("Co-financed", C(r["Co-financed"] for r in keep))
print("RFA in keep", C(r["Recommended For Aggregates"] for r in keep))
print("Geo precision", C(r["Geographic Level of Precision Available"] for r in keep))
print("Geo feature", C(r["Geospatial Feature Available"] for r in keep))
# funders
f = C(); im = C()
for r in keep:
    for p in dict.fromkeys(x.strip() for x in str(r["Funding Agencies"] or "").split("|") if x.strip()): f[p]+=1
    for p in dict.fromkeys(x.strip() for x in str(r["Implementing Agencies"] or "").split("|") if x.strip()): im[p]+=1
print("funders", f.most_common(8))
print("implementers", im.most_common(8))
SEC = {110: "education", 120: "health", 130: "health", 140: "water", 150: "government",
    160: "social", 210: "transport", 220: "ict", 230: "energy", 310: "agriculture",
    320: "industry", 330: "trade", 410: "environment"}
print("sector (site mapping)", C(SEC.get(int(r["Sector Code"] or 0), "other") for r in keep).most_common())
print("sector names", C(r["Sector Name"] for r in keep).most_common())
json.dump([r["AidData Record ID"] for r in keep], open(sys.argv[2],"w"))
