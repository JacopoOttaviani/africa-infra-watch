import sys, os, collections
import xml.etree.ElementTree as ET
INFRA = ("210", "23", "140", "321", "322", "323", "331", "410", "220")
for fn in sys.argv[1:]:
    root = ET.parse(fn).getroot()
    n = ninfra = 0; tot = 0.0; regs = collections.Counter(); hier = collections.Counter(); st = collections.Counter(); top=[]
    for act in root.iter("iati-activity"):
        n += 1
        sc = [s.get("code") for s in act.iter("sector") if s.get("code") and s.get("vocabulary") in (None, "1")]
        if not any(c.startswith(INFRA) for c in sc): continue
        s = act.find("activity-status"); code = s.get("code") if s is not None else None
        if code not in "123456": continue
        ninfra += 1
        for rr in act.iter("recipient-region"): regs[rr.get("code")] += 1
        for rc in act.iter("recipient-country"): regs["c:"+rc.get("code")] += 1
        hier[act.get("hierarchy")] += 1
        c = sum(float(t.find("value").text) for t in act.iter("transaction") if t.find("transaction-type").get("code") == "2")
        tot += c; st[code]+=1
        top.append((c, act.find("iati-identifier").text, (act.find("title/narrative").text or "")[:60], act.get("hierarchy")))
    top.sort(reverse=True)
    print(os.path.basename(fn), "acts", n, "infra+status", ninfra, "commit EURm", round(tot/1e6,1), dict(hier), dict(st), regs.most_common(6))
    for t in top[:3]: print("    ", round(t[0]/1e6,1), t[1], t[3], t[2])
