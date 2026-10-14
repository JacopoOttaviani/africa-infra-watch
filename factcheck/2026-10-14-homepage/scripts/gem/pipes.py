"""Recompute the site's GEM pipeline figures from GEM's raw route GeoJSONs.
Usage: python3 -I pipes.py <ggit.geojson> <goit.geojson>
Filters copied from fetch_sources.fetch_pipelines + build_dashboard.build_pipelines."""
import json, math, sys, collections, re

AFRICA_NAMES = {
    "Algeria", "Angola", "Benin", "Botswana", "Burkina Faso", "Burundi",
    "Cameroon", "Cape Verde", "Cabo Verde", "Central African Republic", "Chad",
    "Comoros", "Congo", "Democratic Republic of Congo", "DR Congo", "Djibouti",
    "Egypt", "Equatorial Guinea", "Eritrea", "Eswatini", "Ethiopia", "Gabon",
    "Gambia", "Ghana", "Guinea", "Guinea-Bissau", "Ivory Coast", "Cote d'Ivoire",
    "Côte d'Ivoire", "Kenya", "Lesotho", "Liberia", "Libya", "Madagascar",
    "Malawi", "Mali", "Mauritania", "Mauritius", "Morocco", "Mozambique",
    "Namibia", "Niger", "Nigeria", "Rwanda", "Sao Tome and Principe", "Senegal",
    "Seychelles", "Sierra Leone", "Somalia", "South Africa", "South Sudan",
    "Sudan", "Tanzania", "Togo", "Tunisia", "Uganda", "Zambia", "Zimbabwe",
    "Western Sahara", "Republic of the Congo",
}
NAME_TO_ISO_KEYS = AFRICA_NAMES | {"The Gambia", "Democratic Republic of the Congo"}
ISO = {"Cape Verde": "CV", "Cabo Verde": "CV", "Congo": "CG", "Republic of the Congo": "CG",
       "Democratic Republic of Congo": "CD", "DR Congo": "CD", "Democratic Republic of the Congo": "CD",
       "Gambia": "GM", "The Gambia": "GM", "Ivory Coast": "CI", "Cote d'Ivoire": "CI", "Côte d'Ivoire": "CI"}
STATUS = {
    "announced": "announced", "pre-construction": "approved", "permitted": "approved",
    "construction": "under_construction", "operating": "operating",
    "cancelled": "stalled", "shelved": "stalled", "mothballed": "stalled",
    "retired": "operating", "proposed": "announced", "idle": "stalled",
}


def num(s):
    try:
        return float(str(s).replace(",", "")) if s not in (None, "") else None
    except ValueError:
        return None


def parts(geom):
    if not geom:
        return []
    t = geom.get("type")
    if t == "LineString":
        return [geom["coordinates"]] if len(geom.get("coordinates") or []) >= 2 else []
    if t == "MultiLineString":
        return [c for c in geom.get("coordinates") or [] if len(c) >= 2]
    if t == "GeometryCollection":
        return [p for g in geom.get("geometries") or [] for p in parts(g)]
    return []


def hav(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def geolen(ps):
    return sum(hav(a, b) for p in ps for a, b in zip(p, p[1:]))


segs, unrouted, n_af = [], [], collections.Counter()
weird = []
for path, trk in zip(sys.argv[1:3], ("GGIT", "GOIT")):
    for f in json.load(open(path))["features"]:
        p = f.get("properties") or {}
        cs = [c.strip() for c in (p.get("CountriesOrAreas") or "").split(",") if c.strip()]
        if not any(c in AFRICA_NAMES or c == "The Gambia" for c in cs):
            continue
        n_af[trk] += 1
        for k in ("LengthMergedKm", "LengthKnownKm", "LengthEstimateKm"):
            v = p.get(k)
            if v not in (None, "", "--") and num(v) is None:
                weird.append((trk, p.get("PipelineName"), k, v))
        ps = parts(f.get("geometry"))
        if not ps:
            unrouted.append((trk, p.get("PipelineName"), p.get("SegmentName"), p.get("Status"), p.get("RouteType")))
            continue
        st = (p.get("Status") or "").strip().lower()
        L = num(p.get("LengthMergedKm")) or num(p.get("LengthKnownKm")) or num(p.get("LengthEstimateKm"))
        segs.append(dict(trk=trk, name=(p.get("PipelineName") or "").strip(), seg=(p.get("SegmentName") or "").strip(),
                         raw=st, dash=STATUS.get(st), fuel=(p.get("Fuel") or "").strip(), cs=cs, L=L,
                         merged=p.get("LengthMergedKm"), known=p.get("LengthKnownKm"), est=p.get("LengthEstimateKm"),
                         geo=geolen(ps), ps=ps, pid=p.get("ProjectID"), wiki=p.get("Wiki"),
                         route=p.get("RouteType"), acc=p.get("RouteAccuracy"),
                         known_units=p.get("LengthKnownUnits"), lknown=p.get("LengthKnown")))

print("African segments:", dict(n_af), "total", sum(n_af.values()))
print("unrouted:", len(unrouted), collections.Counter(u[0] for u in unrouted))
print("routed:", len(segs))
print("non-numeric length strings:", collections.Counter((w[2], w[3]) for w in weird))
nostat = [s for s in segs if not s["dash"]]
print("routed but unmapped status (dropped by build):", len(nostat), collections.Counter(s["raw"] for s in nostat))
kept = [s for s in segs if s["dash"]]
print("KEPT (site records):", len(kept))
print("raw status:", collections.Counter(s["raw"] for s in kept))
print("dash status:", collections.Counter(s["dash"] for s in kept))
print("fuel:", collections.Counter(s["fuel"] for s in kept))
systems = {(s["name"] or None) for s in kept}
print("systems (distinct PipelineName):", len(systems))
isos = {ISO.get(c, c) for s in kept for c in s["cs"] if c in NAME_TO_ISO_KEYS}
print("African countries on routes:", len(isos))
allc = {c for s in kept for c in s["cs"]}
print("all countries on routes (incl. non-African):", len(allc))
nolen = [s for s in kept if not s["L"]]
print("segments without a GEM length (site falls back to drawn route):", len(nolen))
tot = sum(s["L"] or s["geo"] for s in kept)
print(f"total km (GEM length, else raw-geometry): {tot:,.1f}")
for st in ("under_construction", "announced", "operating", "stalled"):
    ss = [s for s in kept if s["dash"] == st]
    print(f"  {st}: {len(ss)} segments, {sum(s['L'] or s['geo'] for s in ss):,.1f} km")

print("\nLength vs raw route geometry (ratio = GEM length / drawn route length), flagged if >2.5 or <0.4 with drawn >20 km:")
fl = []
for s in kept:
    if s["L"] and s["geo"] > 0:
        r = s["L"] / s["geo"]
        if r > 2.5 or (r < 0.4 and s["geo"] > 20):
            fl.append((r, s))
for r, s in sorted(fl, key=lambda x: -abs(math.log(x[0]))):
    print(f"  ratio {r:6.2f} | GEM {s['L']:>9,.1f} km | drawn {s['geo']:>8,.1f} km | merged={s['merged']} known={s['known']} ({s['lknown']} {s['known_units']}) est={s['est']} | {s['trk']} {s['raw']:<12} | {s['name'][:45]} · {s['seg'][:25]} | {s['acc']} | {s['pid']}")

print("\nKnown vs estimate disagreement (known/estimate > 3 or < 1/3):")
for s in kept:
    k, e = num(s["known"]), num(s["est"])
    if k and e and (k / e > 3 or k / e < 1 / 3):
        print(f"  known {k:>9,.1f} est {e:>9,.1f} | merged {s['merged']} | drawn {s['geo']:,.1f} | {s['trk']} {s['raw']} | {s['name'][:50]} · {s['seg'][:25]} | {s['pid']}")

print("\nTop 25 by site length:")
for s in sorted(kept, key=lambda s: -(s["L"] or s["geo"]))[:25]:
    lon = [c[0] for p in s["ps"] for c in p]; lat = [c[1] for p in s["ps"] for c in p]
    print(f"  {s['L'] or s['geo']:>9,.1f} | drawn {s['geo']:>8,.1f} | {s['raw']:<12} | {s['name'][:45]} · {s['seg'][:30]} | {','.join(s['cs'])[:70]} | bbox lon {min(lon):.1f}..{max(lon):.1f} lat {min(lat):.1f}..{max(lat):.1f} | {s['wiki']}")

print("\nNamed checks:")
for key in ("Medgaz", "Transmed", "Trans-Mediterranean", "Greenstream", "Nigeria-Morocco", "Nigeria–Morocco", "Trans-Sahara",
            "Nigeria–Libya", "Nigeria-Libya", "GasNosu", "Tazama", "Niger–Benin", "Niger-Benin", "Greater Nile", "Maghreb", "Enrico Mattei", "Pedro Duran", "Galsi", "Arab Gas", "EACOP", "East African Crude"):
    for s in kept:
        if key.lower() in (s["name"] + " " + s["seg"]).lower():
            lon = [c[0] for p in s["ps"] for c in p]; lat = [c[1] for p in s["ps"] for c in p]
            print(f"  [{key}] {s['name']} · {s['seg']} | {s['raw']} | L={s['L']} (merged {s['merged']}, known {s['known']}, est {s['est']}) | drawn {s['geo']:,.1f} | {','.join(s['cs'])} | lon {min(lon):.2f}..{max(lon):.2f} lat {min(lat):.2f}..{max(lat):.2f} | parts {len(s['ps'])}")
    for u in unrouted:
        if key.lower() in ((u[1] or "") + " " + (u[2] or "")).lower():
            print(f"  [{key}] UNROUTED {u}")
