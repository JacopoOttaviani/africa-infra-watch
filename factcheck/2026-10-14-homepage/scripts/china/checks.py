import sys, json, collections
D = json.load(open(sys.argv[1])); site = json.load(open(sys.argv[2]))
sid = set(f["properties"]["aiddata_id"] for f in site["features"])
by = {r["AidData Record ID"]: r for r in D["rows"]}
subs = [65749, 65750, 65758, 73515, 73516, 73517, 73548, 73549, 73553, 73557, 73558]
s = sum(by[i]["Amount (Nominal USD)"] or 0 for i in subs)
print("65748 subsidiaries with amounts, nominal sum $m:", round(s/1e6,1), " 2174 - sum =", round(2174 - s/1e6,1), " recorded:", by[65748]["Amount (Nominal USD)"]/1e6)
ratios = collections.defaultdict(set)
for r in D["rows"]:
    if r["AidData Record ID"] in sid and r["Original Currency"]=="USD" and isinstance(r["Amount (Nominal USD)"],(int,float)) and r["Amount (Nominal USD)"]>0 and isinstance(r["Amount (Constant USD 2021)"],(int,float)):
        ratios[r["Commitment Year"]].add(round(r["Amount (Constant USD 2021)"]/r["Amount (Nominal USD)"], 4))
for y in sorted(ratios): print(y, sorted(ratios[y]))
