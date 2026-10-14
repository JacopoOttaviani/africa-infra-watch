import sys, os, re, collections
import xml.etree.ElementTree as ET
INFRA = ("210", "23", "140", "321", "322", "323", "331", "410", "220")
n = 0; ft = collections.Counter(); rows = []
for fn in sys.argv[1:]:
    for act in ET.parse(fn).getroot().iter("iati-activity"):
        t = " ".join((x.text or "") for x in act.iter("narrative") if x is not None)[:2000]
        title = (act.find("title/narrative").text if act.find("title/narrative") is not None else "") or ""
        fin = [d.get("code") for d in act.iter("default-finance-type")] + [x.get("code") for x in act.iter("finance-type")]
        is_g = any(f in ("1100", "1110", "1120") for f in fin) or re.search(r"guarantee", title, re.I)
        if not is_g: continue
        n += 1
        tx2 = sum(float(x.find("value").text) for x in act.iter("transaction") if x.find("transaction-type").get("code") == "2")
        sc = [s.get("code") for s in act.iter("sector") if s.get("vocabulary") in (None, "1")]
        rows.append((tx2, os.path.basename(fn)[14:], act.find("iati-identifier").text, title[:80], fin, any(c and c.startswith(INFRA) for c in sc), act.find("activity-status").get("code") if act.find("activity-status") is not None else None))
rows.sort(reverse=True)
for r in rows[:25]: print(f"{r[0]/1e6:8.1f}M {r[1]:10} {r[2]:42} st{r[6]} fin={r[4]} infra={r[5]} | {r[3]}")
print("guarantee-like activities:", n, "with type-2 commitment >0:", sum(1 for r in rows if r[0] > 0))
