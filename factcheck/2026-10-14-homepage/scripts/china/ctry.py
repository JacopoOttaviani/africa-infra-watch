import sys, json, collections
D = json.load(open(sys.argv[1])); keep_ids = set(json.load(open(sys.argv[2])))
rows = [r for r in D["rows"] if r["AidData Record ID"] in keep_ids]
c = collections.Counter(r["Recipient ISO-3"] for r in rows)
print(len([k for k in c if k]), sorted(c.items(), key=lambda x: str(x[0])))
for iso in ("MUS","SYC","CPV","COM","STP"):
    print(iso, c[iso])
# which African ISO3 present in Africa rows but absent from keep
allaf = collections.Counter(r["Recipient ISO-3"] for r in D["rows"] if r["Recipient Region"]=="Africa")
print("Africa recipients total", len([k for k in allaf if k]), "not in keep:", [k for k in allaf if k not in c])
print([ (r["Recipient"]) for r in D["rows"] if r["Recipient Region"]=="Africa" and r["Recipient ISO-3"] in [k for k in allaf if k not in c]][:5])
