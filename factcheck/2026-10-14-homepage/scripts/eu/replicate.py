"""Independent re-parse of upstream EC + EIB IATI files with the site's stated filters.
usage: replicate.py <ec_dir> <eib_xml> <out_json>"""
import sys, os, json, re, collections
import xml.etree.ElementTree as ET
AF = set("DZ AO BJ BW BF BI CM CV CF TD KM CG CD DJ EG GQ ER SZ ET GA GM GH GN GW CI KE LS LR LY MG MW ML MR MU MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD TZ TG TN UG ZM ZW".split())
INFRA = ("210", "23", "140", "321", "322", "323", "331", "410", "220")
EU_REG = {"189", "289", "298"}
EIB_SECTOR = [((5, 9), "industry"), ((10, 33), "industry"), ((35, 35), "energy"), ((36, 38), "water"),
              ((39, 39), "environment"), ((41, 43), "industry"), ((49, 52), "transport"), ((60, 63), "ict")]
FIN = {"110": "grant", "111": "grant", "210": "grant", "411": "loan", "412": "loan", "421": "loan",
       "510": "equity", "511": "equity", "512": "equity", "520": "equity"}
EUR_USD = 1.1206
def eib_bucket(c):
    try: n = int((c or "")[:2])
    except ValueError: return None
    for (lo, hi), b in EIB_SECTOR:
        if lo <= n <= hi: return b
def narr(e, p):
    x = e.find(p); return (x.text or "").strip() if x is not None and x.text else None
def parse(act, pub, fname):
    if pub == "EIB":
        codes = [(s.get("code") or "", narr(s, "narrative")) for s in act.iter("sector") if s.get("vocabulary") == "99"]
        bs = [b for b in (eib_bucket(c) for c, _ in codes) if b]
        if not bs: return None
        sector = bs[0]; slabel = next((n for c, n in codes if eib_bucket(c)), None)
    else:
        sc = [s.get("code") for s in act.iter("sector") if s.get("code") and s.get("vocabulary") in (None, "1")]
        if not any(c.startswith(INFRA) for c in sc): return None
        sector = None; slabel = sc
    countries = []
    for rc in act.iter("recipient-country"):
        try: pct = float(rc.get("percentage") or 100)
        except ValueError: pct = 100.0
        countries.append((rc.get("code"), pct))
    regions = [rr.get("code") for rr in act.iter("recipient-region")]
    afr = [c for c in countries if c[0] in AF]
    if not afr and not (set(regions) & EU_REG): return None
    iso = max(afr, key=lambda c: c[1])[0] if afr else None
    st = act.find("activity-status"); code = st.get("code") if st is not None else None
    if code not in ("1","2","3","4","5","6"): return None
    cur0 = act.get("default-currency") or "EUR"
    seen = set(); com = dis = 0.0; ntx2 = 0; ntx2_raw = 0; txs = []
    for tx in act.iter("transaction"):
        tt, v = tx.find("transaction-type"), tx.find("value")
        if tt is None or v is None or not v.text: continue
        try: amt = float(v.text)
        except ValueError: continue
        cur = v.get("currency") or cur0
        if cur == "USD": amt = amt / EUR_USD
        elif cur != "EUR": continue
        td = tx.find("transaction-date")
        key = (tt.get("code"), td.get("iso-date") if td is not None else None, v.text, cur)
        if tt.get("code") == "2": ntx2_raw += 1
        if pub == "EIB" and key in seen: continue
        seen.add(key)
        if tt.get("code") == "2": com += amt; ntx2 += 1; txs.append((key[1], amt))
        elif tt.get("code") == "3": dis += amt
    locs = []
    for loc in act.iter("location"):
        pos = narr(loc, "point/pos")
        if pos: locs.append((pos, narr(loc, "name/narrative")))
    dates = {d.get("type"): (d.get("iso-date") or "")[:10] for d in act.iter("activity-date") if d.get("iso-date")}
    impl = []
    for po in act.iter("participating-org"):
        if po.get("role") == "4":
            n = (narr(po, "narrative") or "").strip(" *")
            if n and n.title() not in impl: impl.append(n.title() if n.isupper() else n)
    fin = next((d.get("code") for d in act.iter("default-finance-type")), None)
    aid = next((d.get("code") for d in act.iter("default-aid-type")), None)
    budgets = []
    for b in act.iter("budget"):
        v = b.find("value")
        if v is not None and v.text: budgets.append(float(v.text))
    return {"pub": pub, "file": fname, "id": narr(act, "iati-identifier"), "hier": act.get("hierarchy") or "1",
            "parents": [ra.get("ref") for ra in act.iter("related-activity") if ra.get("type") == "1" and ra.get("ref")],
            "children": [ra.get("ref") for ra in act.iter("related-activity") if ra.get("type") == "2" and ra.get("ref")],
            "title": narr(act, "title/narrative"), "iso": iso, "regions": regions, "status": code,
            "commit": round(com, 2), "disb": round(dis, 2), "ntx2": ntx2, "ntx2_raw": ntx2_raw, "tx2": txs,
            "budget_sum": sum(budgets), "sector": sector, "slabel": slabel, "fin": fin, "instr": FIN.get(fin or "", "budget support" if (aid or "").startswith("A") else None),
            "aid": aid, "nlocs": len(locs), "locs": locs[:3], "dates": dates, "impl": impl}
out = []
ec_dir, eib, dst = sys.argv[1], sys.argv[2], sys.argv[3]
for fn in sorted(os.listdir(ec_dir)):
    pub = "NEAR" if "NEAR" in fn else "INTPA"
    root = ET.parse(os.path.join(ec_dir, fn)).getroot()
    for act in root.iter("iati-activity"):
        a = parse(act, pub, fn)
        if a: out.append(a)
root = ET.parse(eib).getroot()
for act in root.iter("iati-activity"):
    a = parse(act, "EIB", "eib")
    if a: out.append(a)
json.dump(out, open(dst, "w"))
print(len(out))
