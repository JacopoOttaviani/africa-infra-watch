"""EIB records funded by the Commission (participating-org role 1) vs Commission contracts implemented by the EIB."""
import sys, json, collections
import xml.etree.ElementTree as ET
A = json.load(open(sys.argv[2]))
ec = [a for a in A if a["pub"] != "EIB"]
parents = {p for a in ec if a["hier"] == "2" for p in a["parents"]}
kept = {a["id"]: a for a in A if a["pub"] == "EIB" or a["hier"] == "2" or a["id"] not in parents}
fund = collections.defaultdict(lambda: [0, 0.0]); rows = []
for act in ET.parse(sys.argv[1]).getroot().iter("iati-activity"):
    i = act.find("iati-identifier").text
    if i not in kept: continue
    f = tuple(sorted({(p.find("narrative").text or "") for p in act.iter("participating-org") if p.get("role") == "1"}))
    a = kept[i]
    fund[(f, a["instr"])][0] += 1; fund[(f, a["instr"])][1] += a["commit"]
    if "MS-EC" in f: rows.append(a)
for k, v in sorted(fund.items(), key=lambda kv: -kv[1][1]): print(k, v[0], round(v[1]/1e6, 1), "M")
print("EIB records funded by MS-EC:", len(rows), round(sum(a['commit'] for a in rows)/1e6, 1), "M EUR")
eibimpl = [a for a in kept.values() if a["pub"] != "EIB" and any("Investment Bank" in x for x in a["impl"])]
print("EC kept records implemented by EIB:", len(eibimpl), round(sum(a['commit'] for a in eibimpl)/1e6, 1), "M EUR")
for a in sorted(eibimpl, key=lambda a: -a["commit"]): print(f"   EC {a['commit']/1e6:7.1f}M {a['iso']} {a['id']} {a['title'][:70]}")
for a in sorted(rows, key=lambda a: -a["commit"])[:12]: print(f"   EIB {a['commit']/1e6:7.1f}M {a['iso']} {a['id']} {a['title'][:60]}")
