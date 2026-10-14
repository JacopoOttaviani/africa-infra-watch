"""Implementers of kept Commission records counted by organisation ref (role 4), not by name string."""
import sys, json, os, collections
import xml.etree.ElementTree as ET
A = json.load(open(sys.argv[1]))
ec = [a for a in A if a["pub"] != "EIB"]
parents = {p for a in ec if a["hier"] == "2" for p in a["parents"]}
kept = {a["id"] for a in ec if a["hier"] == "2" or a["id"] not in parents}
byref = collections.Counter(); names = collections.defaultdict(collections.Counter)
for fn in sys.argv[2:]:
    for act in ET.parse(fn).getroot().iter("iati-activity"):
        i = act.find("iati-identifier").text
        if i not in kept: continue
        refs = set()
        for p in act.iter("participating-org"):
            if p.get("role") == "4" and p.get("ref"):
                refs.add(p.get("ref")); n = p.find("narrative"); names[p.get("ref")][(n.text if n is not None else None)] += 1
        for r in refs: byref[r] += 1
for r, n in [(r, byref[r]) for r in ("XM-DAC-42004", "FR-3", "XM-DAC-5-52", "DE-1", "XM-DAC-41301")] + byref.most_common(0): print(n, r, names[r].most_common(3))
