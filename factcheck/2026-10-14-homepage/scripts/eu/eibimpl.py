"""Kept Commission records whose implementer (role 4) is the EIB, by ref XM-DAC-42004 or by name."""
import sys, json
import xml.etree.ElementTree as ET
A = json.load(open(sys.argv[1]))
ec = [a for a in A if a["pub"] != "EIB"]
parents = {p for a in ec if a["hier"] == "2" for p in a["parents"]}
kept = {a["id"]: a for a in ec if a["hier"] == "2" or a["id"] not in parents}
byref = byname = both = 0; tot = 0.0; ids = set()
for fn in sys.argv[2:]:
    for act in ET.parse(fn).getroot().iter("iati-activity"):
        i = act.find("iati-identifier").text
        if i not in kept: continue
        r = n = False
        for p in act.iter("participating-org"):
            if p.get("role") != "4": continue
            nm = p.find("narrative"); nm = (nm.text or "") if nm is not None else ""
            if p.get("ref") == "XM-DAC-42004": r = True
            if "EUROPEAN INVESTMENT BANK" in nm.upper(): n = True
        if r or n:
            ids.add(i); tot += kept[i]["commit"]; byref += r; byname += n; both += (r and n)
print("EIB-implemented Commission records:", len(ids), "by ref", byref, "by name", byname, "both", both, "EUR m", round(tot/1e6, 1))
