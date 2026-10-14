import sys, collections
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
want = set(sys.argv[2:])
for act in root.iter("iati-activity"):
    i = act.find("iati-identifier").text
    if i not in want: continue
    t = act.find("title/narrative").text
    tx = collections.Counter()
    for x in act.iter("transaction"):
        tt = x.find("transaction-type").get("code"); v = x.find("value")
        tx[(tt, x.find("transaction-date").get("iso-date"), v.text, v.get("currency") or act.get("default-currency"))] += 1
    fin = [d.get("code") for d in act.iter("default-finance-type")]
    st = act.find("activity-status").get("code")
    rc = [r.get("code") for r in act.iter("recipient-country")]
    rr = [r.get("code") for r in act.iter("recipient-region")]
    sec = [(s.get("vocabulary"), s.get("code"), (s.find("narrative").text if s.find("narrative") is not None else "")) for s in act.iter("sector")]
    nloc = len(list(act.iter("location")))
    print(i, t, "status", st, "fin", fin, "countries", rc, rr, "locations", nloc)
    print("   sectors", sec[:4])
    for k, n in sorted(tx.items()):
        print("   tx", k, "x", n)
    po = [(p.get("role"), (p.find("narrative").text if p.find("narrative") is not None else "")) for p in act.iter("participating-org")]
    print("   orgs", po[:6])
    print("   dates", [(d.get("type"), d.get("iso-date")) for d in act.iter("activity-date")])
