import json, sys, os, collections
tg = sys.argv[1]; inc = json.load(open(sys.argv[2]))
lpgeo = json.load(open(os.path.join(tg, "landing-point_landing-point-geo.json")))
ctry = collections.Counter(x[1] for c in inc for x in c["af"])
print("included landing countries:", len(ctry)); print(sorted(ctry.items()))
# landing points geographically in/near Africa but in a non-African country
for f in lpgeo["features"]:
    p = f["properties"]; lon, lat = f["geometry"]["coordinates"][:2]
    nm = p.get("name", "")
    if (-19 <= lon <= -13 and 27 <= lat <= 30) or any(k in nm for k in ("Ceuta", "Melilla", "Socotra", "Madeira", "Funchal", "Canar", "Palmas", "Tenerife", "Lampedusa", "Pantelleria", "Hadibu")):
        print("  edge LP:", p.get("id"), "|", nm, lon, lat)
# which cables land at those edge LPs, and do they have any other African landing?
edge_ids = set()
for f in lpgeo["features"]:
    p = f["properties"]; lon, lat = f["geometry"]["coordinates"][:2]
    if (-19 <= lon <= -13 and 27 <= lat <= 30) or any(k in p.get("name","") for k in ("Ceuta", "Melilla", "Socotra", "Hadibu")):
        edge_ids.add(p["id"])
incids = {c["id"] for c in inc}
for fn in os.listdir(os.path.join(tg, "cable")):
    d = json.load(open(os.path.join(tg, "cable", fn)))
    hits = [lp["id"] for lp in d.get("landing_points", []) if lp.get("id") in edge_ids]
    if hits: print("  cable", d["id"], "lands at", hits, "| included on site:", d["id"] in incids)
