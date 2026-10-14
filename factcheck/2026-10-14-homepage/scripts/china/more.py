import sys, json, collections, re
D = json.load(open(sys.argv[1])); site = json.load(open(sys.argv[2]))
sp = {f["properties"]["aiddata_id"]: f["properties"] for f in site["features"]}
C = collections.Counter
R = [r for r in D["rows"] if r["AidData Record ID"] in sp]
def a(r, f="Amount (Constant USD 2021)"):
    v = r[f]; return v if isinstance(v,(int,float)) else 0
bn = lambda x: round(x/1e9, 2)
# cofinanced mismatch
up = set(r["AidData Record ID"] for r in R if r["Co-financed"]=="Yes")
st = set(i for i,p in sp.items() if p.get("cofinanced"))
print("upstream cofin", len(up), "site cofin flag", len(st), "up-not-site", sorted(up-st)[:20], "site-not-up", sorted(st-up)[:5])
for i in sorted(up-st)[:5]:
    r = [x for x in R if x["AidData Record ID"]==i][0]; print("   ", i, r["Co-financing Agencies"], "|", r["Title"][:80])
# implementers truncation check
for name in ("SinoHydro","Huawei Technologies Co., Ltd.","China Road & Bridge Corporation (CRBC)", "Industrial and Commercial Bank of China (ICBC)"):
    upn = [r["AidData Record ID"] for r in R if name in [x.strip() for x in str(r["Implementing Agencies"] or "").split("|")] + [x.strip() for x in str(r["Funding Agencies"] or "").split("|")]]
    sn = [i for i in upn if name not in (sp[i].get("implementers") or "") + (sp[i].get("funders") or "")]
    print(name, "upstream", len(upn), "missing on site", len(sn), [(i, len(str([x for x in R if x["AidData Record ID"]==i][0]["Implementing Agencies"]))) for i in sn][:8])
# stalled list
stl = sorted([r for r in R if r["Status"] in ("Suspended","Cancelled")], key=a, reverse=True)
for r in stl[:8]: print("stalled", r["AidData Record ID"], r["Status"], round(a(r)/1e6,1), r["Title"][:90])
# M&A, refinancing etc in kept set
for fl in ("M&A","Refinancing","Working Capital","PxF/Commodity Prepayment","Rescue","Investment Project Loan"):
    s = [r for r in R if r[fl]=="Yes"]; print(fl, len(s), bn(sum(a(r) for r in s)))
oil = [r for r in R if r["Collateralized"]=="Yes" and re.search(r"\boil\b|crude|petrol|commodit|copper|cobalt|mineral|iron ore|bauxite|cocoa|sesame|manganese|chrome", str(r["Collateral"] or ""), re.I)]
print("commodity-collateralized (strict)", len(oil), bn(sum(a(r) for r in oil)))
# Africa-wide totals
af = [r for r in D["rows"] if r["Recipient Region"]=="Africa"]
rfa = [r for r in af if r["Recommended For Aggregates"]=="Yes"]
print("Africa RFA=Yes n", len(rfa), "const21", bn(sum(a(r) for r in rfa)), "adj const21", bn(sum(a(r,"Adjusted Amount (Constant USD 2021)") for r in rfa)), "nominal", bn(sum(a(r,"Amount (Nominal USD)") for r in rfa)))
ln = [r for r in rfa if r["Flow Type Simplified"]=="Loan"]
print("Africa RFA loans n", len(ln), "const21", bn(sum(a(r) for r in ln)), "nominal", bn(sum(a(r,"Amount (Nominal USD)") for r in ln)))
inf = [r for r in rfa if r["Infrastructure"]=="Yes"]
print("Africa RFA infra n", len(inf), "const21", bn(sum(a(r) for r in inf)), "nominal", bn(sum(a(r,"Amount (Nominal USD)") for r in inf)))
infl = [r for r in inf if r["Flow Type Simplified"]=="Loan"]
print("Africa RFA infra loans", len(infl), "nominal", bn(sum(a(r,"Amount (Nominal USD)") for r in infl)))
# sovereign/public: Level of Public Liability
print("public liability in site loans", C(r["Level of Public Liability"] for r in R if r["Flow Type Simplified"]=="Loan").most_common())
ppg = [r for r in R if r["Flow Type Simplified"]=="Loan" and r["Level of Public Liability"] in ("Central government debt","Central government-guaranteed debt","Other public sector debt")]
print("site loans PPG nominal", bn(sum(a(r,"Amount (Nominal USD)") for r in ppg)), "const21", bn(sum(a(r) for r in ppg)))
allrows = D["rows"]; g = [r for r in allrows if r["Recommended For Aggregates"]=="Yes"]
print("GLOBAL RFA n", len(g), "adj const21", bn(sum(a(r,"Adjusted Amount (Constant USD 2021)") for r in g)), "const21", bn(sum(a(r) for r in g)))
print("geo feature avail in site", C(r["Geospatial Feature Available"] for r in R))
