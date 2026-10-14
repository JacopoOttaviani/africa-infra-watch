"""Kept records whose recipients include non-African countries/regions: whole commitment counted for Africa."""
import sys, os, json, collections
import xml.etree.ElementTree as ET
AF = set("DZ AO BJ BW BF BI CM CV CF TD KM CG CD DJ EG GQ ER SZ ET GA GM GH GN GW CI KE LS LR LY MG MW ML MR MU MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD TZ TG TN UG ZM ZW".split())
AFREG = {"189", "289", "298", "1027", "1028", "1029", "1030"}
kept = json.load(open(sys.argv[1]))
ec = [a for a in kept if a["pub"] != "EIB"]
parents = {p for a in ec if a["hier"] == "2" for p in a["parents"]}
keep = {a["id"]: a for a in kept if a["pub"] == "EIB" or a["hier"] == "2" or a["id"] not in parents}
files = sys.argv[2:]
rows = []
for fn in files:
    for act in ET.parse(fn).getroot().iter("iati-activity"):
        i = act.find("iati-identifier").text
        if i not in keep: continue
        rc = [(r.get("code"), r.get("percentage")) for r in act.iter("recipient-country")]
        rr = [(r.get("code"), r.get("percentage")) for r in act.iter("recipient-region")]
        non = [c for c, _ in rc if c not in AF] + [c for c, _ in rr if c not in AFREG]
        if non:
            afp = sum(float(p or 0) for c, p in rc if c in AF) + sum(float(p or 0) for c, p in rr if c in AFREG)
            rows.append((keep[i]["commit"], i, keep[i]["pub"], (act.find("title/narrative").text or "")[:50], rc[:5], rr, afp))
rows.sort(reverse=True)
for r in rows[:25]: print(f"{r[0]/1e6:7.1f}M {r[2]:5} {r[1]:42} {r[3]:50} rc={r[4]} rr={r[5]} african%={r[6]}")
print("records", len(rows), "EUR m", round(sum(r[0] for r in rows)/1e6, 1))
by = collections.defaultdict(lambda: [0, 0.0])
for r in rows: by[r[2]][0] += 1; by[r[2]][1] += r[0]
print({k: (v[0], round(v[1]/1e6, 1)) for k, v in by.items()})
afr = sum(r[0] * r[6] / 100 for r in rows)
print(f"African share by the publisher's own percentages: EUR {afr/1e6:.1f}M; counted in full: EUR {sum(r[0] for r in rows)/1e6:.1f}M; overstatement EUR {(sum(r[0] for r in rows)-afr)/1e6:.1f}M")
