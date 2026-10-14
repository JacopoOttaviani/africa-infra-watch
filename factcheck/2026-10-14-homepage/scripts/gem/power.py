"""Recompute the site's GEM power figures from GEM's raw release CSV.
Usage: python3 -I power.py <integrated_map.csv>
Filters copied from fetch_sources.fetch_gem + build_map.build_assets."""
import csv, sys, collections

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
GEM_STATUS = {
    "announced": "announced", "pre-construction": "approved", "permitted": "approved",
    "construction": "under_construction", "operating": "operating",
    "cancelled": "stalled", "shelved": "stalled", "mothballed": "stalled",
    "retired": "operating",
}
SUSPECT = ["Gambia", "Réunion", "Reunion", "Mayotte", "Saint Helena", "São Tomé",
           "Sao Tome", "Somaliland", "Ivoire", "Congo", "Cabo", "Cape Verde", "Eswatini",
           "Swaziland", "Western Sahara", "Sudan", "Canary", "Ceuta", "Melilla"]

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8", errors="replace")))
print("total rows in release:", len(rows))
countries = collections.Counter(r["country-area1"].strip() for r in rows)
print("\nCountry names that look African but are NOT in AFRICA_NAMES:")
for c, n in sorted(countries.items()):
    if c not in AFRICA_NAMES and any(s.lower() in c.lower() for s in SUSPECT):
        print("  ", repr(c), n)
print("AFRICA_NAMES not present in GEM:", sorted(n for n in AFRICA_NAMES if n not in countries))

af_all = [r for r in rows if r["country-area1"].strip() in AFRICA_NAMES]
af = []
nocoord = 0
for r in af_all:
    try:
        float(r["Longitude"]); float(r["Latitude"])
    except (TypeError, ValueError, KeyError):
        nocoord += 1
        continue
    af.append(r)
print(f"\nAfrican rows {len(af_all)}, dropped for no coords {nocoord}, kept {len(af)}")
print("countries:", len({r['country-area1'].strip() for r in af}))
print("projects (distinct project-id):", len({r['project-id'] for r in af if r['project-id']}))
print("distinct unit-id:", len({r['unit-id'] for r in af if r['unit-id']}), "blank unit-id:", sum(1 for r in af if not r['unit-id']))

def mw(r):
    try:
        return round(float(r["capacity"]), 1) if r["capacity"] else 0.0
    except ValueError:
        return 0.0

raw_status = collections.Counter(r["status"].strip().lower() for r in af)
print("\nraw status:", dict(raw_status))
dash = collections.Counter(GEM_STATUS.get(r["status"].strip().lower()) for r in af)
print("dash status:", dict(dash))
tot = sum(mw(r) for r in af)
pipe = [r for r in af if GEM_STATUS.get(r["status"].strip().lower()) in ("announced", "approved", "under_construction")]
print(f"total GW {tot/1000:.1f}; pipeline GW {sum(mw(r) for r in pipe)/1000:.1f} in {len(pipe)} units")
exact = sum(1 for r in af if r["location-accuracy"] == "exact")
print("location-accuracy:", dict(collections.Counter(r["location-accuracy"] for r in af)),
      f"exact share {exact/len(af):.1%}")
tech = collections.Counter(((r.get("tech-type") or r.get("fuel") or "").strip()[:26] or "unknown") for r in af)
print("top tech:", tech.most_common(8))
print("asset types:", dict(collections.Counter(r["asset-type"] for r in af)))
# GW by raw status
gws = collections.defaultdict(float)
for r in af:
    gws[r["status"].strip().lower()] += mw(r)
print("GW by raw status:", {k: round(v/1000, 1) for k, v in gws.items()})

print("\nTop 70 African units by capacity:")
for r in sorted(af, key=mw, reverse=True)[:70]:
    print(f"  {mw(r):>9,.1f} | {r['status']:<15} | {r['country-area1']:<14} | {r['name'][:48]:<48} | unit={r['unit-name'][:28]!r} | {r['unit-id']} | {r['project-id']} | {r['tech-type']} | {r['location-accuracy']}")

# exact (name, capacity) duplicates
print("\nSame name + same capacity pairs among units >= 1000 MW:")
grp = collections.defaultdict(list)
for r in af:
    if mw(r) >= 1000:
        grp[(r["name"], mw(r))].append(r)
for k, v in grp.items():
    if len(v) > 1:
        print(" ", k, [(x["unit-name"], x["unit-id"], x["status"], x["start-year"], x["Latitude"], x["Longitude"]) for x in v])

# full-row duplicates (all fields but unit-id)
print("\nRows identical in every field except unit-id:")
seen = collections.defaultdict(list)
for r in af:
    key = tuple((k, v) for k, v in r.items() if k not in ("unit-id",))
    seen[key].append(r["unit-id"])
dups = {k: v for k, v in seen.items() if len(v) > 1}
print("  groups:", len(dups), "extra rows:", sum(len(v) - 1 for v in dups.values()),
      "extra MW:", sum((len(v) - 1) * mw(dict(k)) for k, v in dups.items()))
for k, v in list(dups.items())[:40]:
    d = dict(k)
    print("   ", d["name"][:50], d["unit-name"][:20], mw(d), d["status"], v)
print("duplicate unit-ids:", [u for u, n in collections.Counter(r['unit-id'] for r in af).items() if n > 1][:20])
