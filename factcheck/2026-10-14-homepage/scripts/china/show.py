import sys, json, textwrap
D = json.load(open(sys.argv[1]))
rows = {r["AidData Record ID"]: r for r in D["rows"]}
for i in sys.argv[2:]:
    r = rows[int(i)]
    print("="*100)
    for k in ("AidData Record ID","Recommended For Aggregates","AidData Parent ID","Umbrella","Recipient","Commitment Year","Title","Status","Flow Type","Sector Name","Infrastructure","Funding Agencies","Amount (Original Currency)","Original Currency","Amount (Nominal USD)","Amount (Constant USD 2021)","Amount Estimated","Collateralized","Collateral","Direct Receiving Agencies","Implementing Agencies","Co-financed","Co-financing Agencies","Financial Distress"):
        print(f"{k}: {r[k]}")
    print("Description:", textwrap.shorten(str(r["Description"]), int(sys.argv[0+0] and 4000) if False else 4000))
    print("Staff Comments:", textwrap.shorten(str(r["Staff Comments"]), 2500))
