import json, sys
A = json.load(open(sys.argv[1]))
ec = [a for a in A if a["pub"] != "EIB"]
parents = {p for a in ec if a["hier"] == "2" for p in a["parents"]}
kept = [a for a in A if a["pub"] == "EIB" or a["hier"] == "2" or a["id"] not in parents]
by = {a["id"]: a for a in A}
def sh(a): print(f"  {a['commit']/1e6:8.1f}M n2={a['ntx2']}/{a['ntx2_raw']} bud={a['budget_sum']/1e6:8.1f}M {a['pub']:5} h{a['hier']} st{a['status']} {a['id']:42} {a['iso']} {a['regions']} {a['instr']} | {(a['title'] or '')[:70]} | {'; '.join(a['impl'])[:50]} | par={a['parents']}")
mode = sys.argv[2]
if mode == "topec":
    for a in sorted([a for a in kept if a['pub']!='EIB'], key=lambda a:-a['commit'])[:25]: sh(a)
if mode == "eibimpl":
    for a in sorted([a for a in kept if a['pub']!='EIB' and any('Investment Bank' in i for i in a['impl'])], key=lambda a:-a['commit']): sh(a)
if mode == "eibgrant":
    for a in sorted([a for a in kept if a['pub']=='EIB' and a['instr']=='grant'], key=lambda a:-a['commit']): sh(a)
if mode == "topdec":
    for a in sorted([a for a in kept if a['pub']!='EIB' and a['hier']!='2'], key=lambda a:-a['commit'])[:15]: sh(a)
if mode == "ids":
    for i in sys.argv[3:]:
        sh(by[i]) if i in by else print("  missing", i)
if mode == "years":
    for a in kept:
        y = (a['dates'].get('2') or a['dates'].get('1') or '')[:4]
        if y and (y > '2026' or y < '2007'): print(y, a['dates']); sh(a)
