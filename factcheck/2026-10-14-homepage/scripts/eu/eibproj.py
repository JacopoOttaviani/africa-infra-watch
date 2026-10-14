"""Per EIB project number: every IATI activity in the raw file, its deduped and raw type-2 sums, and whether the site's filter keeps it."""
import sys, json, re, collections
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
parsed = {a["id"]: a for a in json.load(open(sys.argv[2])) if a["pub"] == "EIB"}
want = set(sys.argv[3:])
for act in root.iter("iati-activity"):
    i = act.find("iati-identifier").text
    m = re.match(r"XM-DAC-918-3-(\d{8})", i)
    if not m or m.group(1) not in want: continue
    cur0 = act.get("default-currency")
    raw = 0.0; seen = set(); dd = 0.0; n = 0
    for x in act.iter("transaction"):
        if x.find("transaction-type").get("code") != "2": continue
        v = x.find("value"); k = (x.find("transaction-date").get("iso-date"), v.text, v.get("currency") or cur0)
        raw += float(v.text); n += 1
        if k not in seen: seen.add(k); dd += float(v.text)
    sec = [s.get("code") for s in act.iter("sector") if s.get("vocabulary") == "99"]
    rc = [r.get("code") for r in act.iter("recipient-country")] + [r.get("code") for r in act.iter("recipient-region")]
    print(f"{m.group(1)} {i:30} {act.find('title/narrative').text[:45]:45} st{act.find('activity-status').get('code')} cur={cur0} raw={raw/1e6:8.2f}M ({n} tx) dedup={dd/1e6:8.2f}M site={'KEPT %.2fM' % (parsed[i]['commit']/1e6) if i in parsed else 'not kept'} sec={sec[:3]} rc={rc}")
