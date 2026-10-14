"""Print an IATI activity's header, sectors and every transaction. Usage: dump_activity.py FILE IATI_ID"""
import sys, xml.etree.ElementTree as ET
fn, iid = sys.argv[1], sys.argv[2]
for ev, act in ET.iterparse(fn):
    if act.tag != "iati-activity":
        continue
    i = act.findtext("iati-identifier", "").strip()
    if i != iid:
        act.clear(); continue
    print("default-currency:", act.get("default-currency"), "last-updated:", act.get("last-updated-datetime"))
    print("title:", act.findtext("title/narrative"))
    st = act.find("activity-status"); print("status:", st.get("code") if st is not None else None)
    for d in act.iter("activity-date"): print("date", d.get("type"), d.get("iso-date"))
    for s in act.iter("sector"): print("sector", s.get("vocabulary"), s.get("code"), s.get("percentage"))
    for o in act.iter("participating-org"): print("org", o.get("role"), o.get("ref"), (o.findtext("narrative") or "")[:60])
    for b in act.iter("budget"):
        v = b.find("value"); print("budget", b.findtext("period-start") , b.find("period-start").get("iso-date"), b.find("period-end").get("iso-date"), v.text, v.get("currency"), v.get("value-date"))
    for t in act.iter("transaction"):
        tt = t.find("transaction-type"); v = t.find("value"); td = t.find("transaction-date")
        desc = t.findtext("description/narrative") or ""
        prov = t.find("provider-org"); rec = t.find("receiver-org")
        print("tx type", tt.get("code"), "date", td.get("iso-date") if td is not None else None, "value", v.text, "cur", v.get("currency"), "vdate", v.get("value-date"), "ref", t.get("ref"), "|", desc[:80], "| prov", (prov.get("ref") if prov is not None else None), (prov.findtext("narrative") if prov is not None else None), "| finance", (t.find("finance-type").get("code") if t.find("finance-type") is not None else None))
    for d in act.iter("document-link"): print("doc", d.get("url"))
    for c in act.iter("contact-info"): pass
    loc = list(act.iter("location")); print("n locations", len(loc))
    other = act.findall("other-identifier"); [print("otherid", o.get("ref"), o.get("type")) for o in other]
    act.clear()
