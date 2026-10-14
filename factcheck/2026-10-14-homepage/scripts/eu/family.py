import json, sys
A = json.load(open(sys.argv[1]))
ec = [a for a in A if a["pub"] != "EIB"]
parents = {p for a in ec if a["hier"] == "2" for p in a["parents"]}
keptids = {a["id"] for a in A if a["pub"] == "EIB" or a["hier"] == "2" or a["id"] not in parents}
for pat in sys.argv[2:]:
    print("==", pat)
    for a in sorted([a for a in A if pat in a["id"] or any(pat in p for p in a["parents"])], key=lambda a: a["id"]):
        print(f"  {'KEPT' if a['id'] in keptids else 'fold'} {a['commit']/1e6:8.2f}M h{a['hier']} st{a['status']} {a['id']:40} {a['file'][14:]:12} {a['iso']} {a['regions']} tx={a['tx2']} | {(a['title'] or '')[:60]} | par={[p[-14:] for p in a['parents']]}")
