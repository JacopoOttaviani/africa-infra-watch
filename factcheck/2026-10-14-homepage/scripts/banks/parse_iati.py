"""Parse IATI activity XML files with the site's infra filter; write a JSON summary per activity.
Usage: parse_iati.py OUT.json FILE [FILE...]
Per activity: id, file, default-currency, status, sectors, n locations with a point, and every
type-2/type-3 transaction (value, currency attr, value-date, provider ref/name, receiver, ref, finance-type)."""
import sys, json, xml.etree.ElementTree as ET
INFRA = ("210", "23", "140", "321", "322", "323", "331", "410", "220")
out = []
for fn in sys.argv[2:]:
    try:
        it = ET.iterparse(fn)
        for ev, act in it:
            if act.tag != "iati-activity":
                continue
            sectors = [s.get("code") for s in act.iter("sector") if s.get("code") and s.get("vocabulary") in (None, "1", "2")]
            infra = any(c.startswith(INFRA) for c in sectors)
            st = act.find("activity-status")
            locs = 0; pts = []
            for loc in act.iter("location"):
                pos = loc.find("point/pos")
                if pos is not None and (pos.text or "").strip():
                    try:
                        lat, lon = (float(x) for x in pos.text.split()[:2])
                    except ValueError:
                        continue
                    locs += 1
                    ex = loc.find("exactness"); lc = loc.find("location-class")
                    pts.append([lon, lat, ex.get("code") if ex is not None else None, lc.get("code") if lc is not None else None])
            txs = []
            for t in act.iter("transaction"):
                tt = t.find("transaction-type"); v = t.find("value")
                if tt is None or v is None or not v.text: continue
                code = tt.get("code")
                if code not in ("1", "2", "3", "4", "11"): continue
                prov = t.find("provider-org"); rec = t.find("receiver-org"); td = t.find("transaction-date"); ft = t.find("finance-type")
                try: amt = float(v.text)
                except ValueError: continue
                txs.append({"type": code, "value": amt, "cur": v.get("currency"), "vdate": v.get("value-date"),
                            "date": td.get("iso-date") if td is not None else None, "ref": t.get("ref"),
                            "prov_ref": prov.get("ref") if prov is not None else None,
                            "prov_name": (prov.findtext("narrative") if prov is not None else None),
                            "rec_name": (rec.findtext("narrative") if rec is not None else None),
                            "ft": ft.get("code") if ft is not None else None,
                            "desc": (t.findtext("description/narrative") or "")[:80]})
            rc = act.find("recipient-country")
            out.append({"id": (act.findtext("iati-identifier") or "").strip(), "file": fn.rsplit("/", 1)[-1],
                        "dc": act.get("default-currency"), "status": st.get("code") if st is not None else None,
                        "sectors": sectors, "infra": infra, "locs": locs,
                        "country": rc.get("code") if rc is not None else None,
                        "title": act.findtext("title/narrative"), "txs": txs, "pts": pts,
                        "aid": [[d.get("vocabulary"), d.get("code")] for d in act.iter("default-aid-type")] + [[d.get("vocabulary"), d.get("code")] for t in act.iter("transaction") for d in t.iter("aid-type")][:3],
                        "dft": (act.find("default-finance-type").get("code") if act.find("default-finance-type") is not None else None),
                        "sectp": [[s.get("vocabulary"), s.get("code"), s.get("percentage")] for s in act.iter("sector")],
                        "region": (act.find("recipient-region").get("code") if act.find("recipient-region") is not None else None),
                        "dates": {d.get("type"): d.get("iso-date") for d in act.iter("activity-date")}})
            act.clear()
    except ET.ParseError as e:
        print("PARSE ERROR", fn, e, file=sys.stderr)
json.dump(out, open(sys.argv[1], "w"))
print(len(out), "activities;", sum(a["infra"] for a in out), "infra;", sum(a["infra"] and a["locs"] > 0 for a in out), "infra with a point")
