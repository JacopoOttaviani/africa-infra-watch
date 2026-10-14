import sys, json, collections, re
D = json.load(open(sys.argv[1])); keep_ids = set(json.load(open(sys.argv[2])))
site = json.load(open(sys.argv[3]))
site_ids = set(f["properties"]["aiddata_id"] for f in site["features"])
C = collections.Counter
R = [r for r in D["rows"] if r["AidData Record ID"] in site_ids]
def a(r, f="Amount (Constant USD 2021)"):
    v = r[f]; return v if isinstance(v,(int,float)) else 0
bn = lambda x: round(x/1e9, 2)
print("N", len(R), "total const21", bn(sum(a(r) for r in R)), "nominal", bn(sum(a(r,"Amount (Nominal USD)") for r in R)))
print("loans", sum(r["Flow Type Simplified"]=="Loan" for r in R), bn(sum(a(r) for r in R if r["Flow Type Simplified"]=="Loan")),
      "grants", sum(r["Flow Type Simplified"]=="Grant" for r in R), bn(sum(a(r) for r in R if r["Flow Type Simplified"]=="Grant")),
      "vague", sum(r["Flow Type Simplified"]=="Vague" for r in R), bn(sum(a(r) for r in R if r["Flow Type Simplified"]=="Vague")))
print("distress loans", sum(r["Financial Distress"]=="Yes" for r in R))
st = C(r["Status"] for r in R); print("status", st)
stalled = [r for r in R if r["Status"] in ("Suspended","Cancelled")]
print("stalled n", len(stalled), "const21", bn(sum(a(r) for r in stalled)))
rfa = [r for r in R if r["Recommended For Aggregates"]=="Yes"]
print("RFA=Yes n", len(rfa), "const21", bn(sum(a(r) for r in rfa)), "loans", bn(sum(a(r) for r in rfa if r["Flow Type Simplified"]=="Loan")))
print("with amount", sum(1 for r in R if isinstance(r["Amount (Constant USD 2021)"],(int,float))))
print("cofinanced Yes", sum(r["Co-financed"]=="Yes" for r in R), C(r["Co-financed"] for r in R))
print("cofin agencies nonempty", sum(1 for r in R if r["Co-financing Agencies"]))
gp = C(r["Geographic Level of Precision Available"] for r in R); print("geo precision upstream", gp, {k: round(100*v/len(R),1) for k,v in gp.items()})
f = C(); im = C()
for r in R:
    for p in dict.fromkeys(x.strip() for x in str(r["Funding Agencies"] or "").split("|") if x.strip()): f[p]+=1
    for p in dict.fromkeys(x.strip() for x in str(r["Implementing Agencies"] or "").split("|") if x.strip()): im[p]+=1
print("funders", f.most_common(6)); print("implementers", im.most_common(6))
SEC = {110: "education", 120: "health", 130: "health", 140: "water", 150: "government", 160: "social", 210: "transport", 220: "ict", 230: "energy", 310: "agriculture", 320: "industry", 330: "trade", 410: "environment"}
sc = C(SEC.get(int(r["Sector Code"] or 0), "other") for r in R); print("sectors", sc.most_common())
ind = [r for r in R if int(r["Sector Code"] or 0)==320]
print("industry n", len(ind), "const21", bn(sum(a(r) for r in ind)))
for r in sorted(ind, key=a, reverse=True)[:12]: print("   ", r["AidData Record ID"], round(a(r)/1e6,1), r["Title"][:100])
oil = [r for r in R if r["Collateralized"]=="Yes" and re.search(r"oil|crude|petrol|commodit|copper|cobalt|mineral|iron ore|bauxite|receivable", str(r["Collateral"] or ""), re.I)]
print("commodity-collateralized n", len(oil), "const21", bn(sum(a(r) for r in oil)))
coll = [r for r in R if r["Collateralized"]=="Yes"]; print("all collateralized n", len(coll), bn(sum(a(r) for r in coll)))
pxf = [r for r in R if r["PxF/Commodity Prepayment"]=="Yes"]; print("PxF flag n", len(pxf), bn(sum(a(r) for r in pxf)))
oiltitle = [r for r in R if re.search(r"oil-backed|oil prepayment|oil-for|commodity", r["Title"] or "", re.I)]
print("titles oil-backed", len(oiltitle), bn(sum(a(r) for r in oiltitle)), [ (r["AidData Record ID"], round(a(r)/1e6)) for r in oiltitle])
mfa = [r for r in R if re.search(r"master (loan )?facility|credit line|line of credit|loan facility|framework", r["Title"] or "", re.I)]
print("facility-type titles", len(mfa), bn(sum(a(r) for r in mfa)))
for r in sorted(mfa, key=a, reverse=True)[:15]: print("   ", r["AidData Record ID"], round(a(r)/1e6,1), r["Sector Name"], "|", r["Title"][:110])
