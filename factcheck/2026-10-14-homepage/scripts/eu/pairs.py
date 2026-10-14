"""Pair each Commission-funded EIB record (funder MS-EC) with Commission records for the same project: same country, shared title word, amount within 30%."""
import sys, json, re
import xml.etree.ElementTree as ET
A = json.load(open(sys.argv[2]))
ec = [a for a in A if a["pub"] != "EIB"]
parents = {p for a in ec if a["hier"] == "2" for p in a["parents"]}
kept = {a["id"]: a for a in A if a["pub"] == "EIB" or a["hier"] == "2" or a["id"] not in parents}
eck = [a for a in kept.values() if a["pub"] != "EIB" and a["commit"]]
STOP = set("rehabilitation project projet programme program support upgrade water energy road network transport modernisation sustainable development investment grant phase contribution renewable expansion facility africa".split())
def words(t): return {w for w in re.findall(r"[a-z]{4,}", (t or "").lower().replace("é", "e")) if w not in STOP}
msec = []
for act in ET.parse(sys.argv[1]).getroot().iter("iati-activity"):
    i = act.find("iati-identifier").text
    if i in kept and any(p.get("role") == "1" and (p.find("narrative").text or "") == "MS-EC" for p in act.iter("participating-org")):
        msec.append(kept[i])
tot_eib = tot_pair = 0.0; used = set()
for e in sorted(msec, key=lambda a: -a["commit"]):
    cands = [c for c in eck if c["iso"] == e["iso"] and c["id"] not in used and (words(c["title"]) & words(e["title"]) or any("Investment Bank" in x for x in c["impl"]))]
    best = [c for c in cands if 0.7 <= c["commit"] / e["commit"] <= 1.3] if e["commit"] else []
    if best:
        b = min(best, key=lambda c: abs(c["commit"] - e["commit"]))
        used.add(b["id"]); tot_eib += e["commit"]; tot_pair += b["commit"]
        print(f"EIB {e['commit']/1e6:6.1f}M {e['id'][13:]} {e['title'][:42]:42} <-> EC {b['commit']/1e6:6.1f}M {b['id'][8:]} {b['title'][:50]} [{'; '.join(b['impl'])[:30]}]")
print(f"paired: EIB EUR {tot_eib/1e6:.1f}M with EC EUR {tot_pair/1e6:.1f}M; double count = min sum approx EUR {min(tot_eib, tot_pair)/1e6:.1f}M")
