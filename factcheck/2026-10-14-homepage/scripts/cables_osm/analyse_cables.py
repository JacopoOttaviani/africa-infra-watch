import json, sys, os, collections, re
tg = sys.argv[1]
TG_ISO_NAMES = ["Algeria","Angola","Benin","Cameroon","Cape Verde","Comoros","Congo, Dem. Rep.","Congo, Rep.",
 "Côte d'Ivoire","Djibouti","Egypt","Equatorial Guinea","Eritrea","Gabon","Gambia","Ghana","Guinea","Guinea-Bissau",
 "Kenya","Liberia","Libya","Madagascar","Mauritania","Mauritius","Mayotte","Morocco","Mozambique","Namibia","Nigeria",
 "Réunion","Saint Helena, Ascension and Tristan da Cunha","Sao Tome and Principe","Senegal","Seychelles","Sierra Leone",
 "Somalia","South Africa","Sudan","Tanzania","Togo","Tunisia","Uganda","Western Sahara"]
TG = set(TG_ISO_NAMES)
def tgc(name):
    for c in sorted(TG, key=len, reverse=True):
        if name.endswith(", " + c): return c
lpgeo = json.load(open(os.path.join(tg, "landing-point_landing-point-geo.json")))
lp_xy = {f["properties"]["id"]: f["geometry"]["coordinates"][:2] for f in lpgeo["features"] if f.get("properties", {}).get("id") and f.get("geometry")}
geo = json.load(open(os.path.join(tg, "cable_cable-geo.json")))
routes = {f["properties"]["id"] for f in geo["features"] if (f.get("properties") or {}).get("id")}
ids = [c["id"] for c in json.load(open(os.path.join(tg, "cable_all.json")))]
YEAR = 2026
allcountries = collections.Counter()
out = []
for cid in ids:
    d = json.load(open(os.path.join(tg, "cable", cid + ".json")))
    lps = [lp for lp in d.get("landing_points", []) if lp.get("id")]
    for lp in lps: allcountries[lp.get("country")] += 1
    af = []
    for lp in lps:
        c = lp.get("country") or tgc(lp.get("name") or "")
        if c in TG and lp["id"] in lp_xy:
            af.append((lp["id"], c, bool(lp.get("is_tbd"))))
    af_nogeo = [lp for lp in lps if (lp.get("country") or tgc(lp.get("name") or "")) in TG and lp["id"] not in lp_xy]
    if not af and not af_nogeo: continue
    planned = bool(d.get("is_planned")); rfs = d.get("rfs_year")
    st = "Operating" if not planned else ("Under construction" if isinstance(rfs, int) and rfs <= YEAR + 1 else "Announced")
    km = d.get("length") or ""
    kmv = float(re.sub(r"[^0-9.]", "", km.replace(",", ""))) if re.search(r"\d", km) else None
    out.append(dict(id=cid, name=d.get("name"), planned=planned, rfs=d.get("rfs"), rfs_year=rfs, status=st, km=kmv,
                    owners=d.get("owners"), af=af, af_nogeo=[x["id"] for x in af_nogeo], route=cid in routes,
                    countries=sorted({lp.get("country") for lp in lps if lp.get("country")}), notes=d.get("notes")))
inc = [c for c in out if c["af"] and c["route"]]
print("cables with an African landing (any):", len(out), " kept (landing with coords + route):", len(inc))
for c in out:
    if c not in inc: print("   not kept:", c["id"], "af:", c["af"], "nogeo:", c["af_nogeo"], "route:", c["route"])
print("countries/territories with landings:", len({x[1] for c in inc for x in c["af"]}))
print("African landing points (sum over cables):", sum(len(c["af"]) for c in inc), " distinct:", len({x[0] for c in inc for x in c["af"]}))
print("planned:", sum(c["planned"] for c in inc))
print("status:", collections.Counter(c["status"] for c in inc))
print("km total:", sum(c["km"] or 0 for c in inc), " missing km:", [c["id"] for c in inc if not c["km"]])
own = collections.Counter()
for c in inc:
    for o in re.split(r",\s*", c["owners"] or ""):
        if o: own[o.strip()] += 1
print("owners top:", own.most_common(10))
print("\nAfrican-looking countries NOT in TG_ISO (all TG landings):")
AFR_HINT = ["Africa","Egypt","Sudan","Somali","Eritrea","Ethiopia","Libya","Tunisia","Morocco","Alger","Canary","Ceuta","Melilla","Madeira","Ascension","Tristan","Helena","Cabo","Verde","Guinea","Gambia","Congo","Ivoire","Cote","Sao","São","Principe","Réunion","Reunion","Mayotte","Comoros","Seychelles","Mauritius","Madagascar","Mozambique","Tanzania","Kenya","Djibouti","Somaliland","Sahara","Namibia","Angola","Gabon","Cameroon","Nigeria","Benin","Togo","Ghana","Liberia","Sierra","Senegal","Mauritania","Zanzibar","Socotra","Yemen","Rodrigues"]
for k, v in sorted(allcountries.items(), key=lambda x: str(x[0])):
    if k not in TG and any(h.lower() in str(k).lower() for h in AFR_HINT): print("   ", k, v)
json.dump(inc, open(os.path.join(os.path.dirname(tg.rstrip("/")), "cables_upstream_inc.json"), "w"), ensure_ascii=False, indent=0)
