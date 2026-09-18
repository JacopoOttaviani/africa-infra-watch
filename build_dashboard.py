#!/usr/bin/env python3
"""
Compile the three ingested layers into a single self-contained dashboard.

Reads   data/*.geojson  +  data/africa_basemap.json
Writes  dashboard.html   (payload injected inline)

The dashboard has to be self-contained: the publishing sandbox blocks runtime
requests to any external host, so there is no tile server and no fetch() —
the basemap and every project record ship inside the page. That is also why
the payload is stored column-wise rather than as an array of objects.
"""

import json
import pathlib
import re
import sys

from shared import (  # noqa: F401  (SDR_* re-exported for build_map.py)
    DOCS, SDR_NOTE, SDR_USD, brand_assets, load_meta, payload_meta, site_facts, wrap_document,
)

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "data"
TEMPLATE = ROOT / "dashboard.template.html"
OUT = ROOT / "dashboard.html"

# GEM uses country names; IATI uses ISO-3166-1 alpha-2. Bridge them.
NAME_TO_ISO = {
    "Algeria": "DZ", "Angola": "AO", "Benin": "BJ", "Botswana": "BW",
    "Burkina Faso": "BF", "Burundi": "BI", "Cameroon": "CM",
    "Cape Verde": "CV", "Cabo Verde": "CV", "Central African Republic": "CF",
    "Chad": "TD", "Comoros": "KM", "Congo": "CG",
    "Republic of the Congo": "CG", "Democratic Republic of Congo": "CD",
    "DR Congo": "CD", "Djibouti": "DJ", "Egypt": "EG",
    "Equatorial Guinea": "GQ", "Eritrea": "ER", "Eswatini": "SZ",
    "Ethiopia": "ET", "Gabon": "GA", "Gambia": "GM", "Ghana": "GH",
    "Guinea": "GN", "Guinea-Bissau": "GW", "Ivory Coast": "CI",
    "Cote d'Ivoire": "CI", "Côte d'Ivoire": "CI", "Kenya": "KE",
    "Lesotho": "LS", "Liberia": "LR", "Libya": "LY", "Madagascar": "MG",
    "Malawi": "MW", "Mali": "ML", "Mauritania": "MR", "Mauritius": "MU",
    "Morocco": "MA", "Mozambique": "MZ", "Namibia": "NA", "Niger": "NE",
    "Nigeria": "NG", "Rwanda": "RW", "Sao Tome and Principe": "ST",
    "Senegal": "SN", "Seychelles": "SC", "Sierra Leone": "SL",
    "Somalia": "SO", "South Africa": "ZA", "South Sudan": "SS",
    "Sudan": "SD", "Tanzania": "TZ", "Togo": "TG", "Tunisia": "TN",
    "Uganda": "UG", "Zambia": "ZM", "Zimbabwe": "ZW",
    "Western Sahara": "EH",
}
ISO_TO_NAME = {}
for _n, _i in NAME_TO_ISO.items():
    ISO_TO_NAME.setdefault(_i, _n)

# Islands too small to appear in Natural Earth 110m — drawn as markers so
# their projects don't float in blank ocean.
ISLANDS = [
    {"n": "Cabo Verde", "iso": "CV", "lon": -23.6, "lat": 15.1},
    {"n": "São Tomé and Príncipe", "iso": "ST", "lon": 6.6, "lat": 0.25},
    {"n": "Comoros", "iso": "KM", "lon": 43.3, "lat": -11.6},
    {"n": "Mauritius", "iso": "MU", "lon": 57.55, "lat": -20.3},
    {"n": "Seychelles", "iso": "SC", "lon": 55.5, "lat": -4.6},
]

# DAC 5-digit purpose codes → the dashboard's sector vocabulary.
DAC_SECTOR = [
    ("210", "transport"), ("220", "ict"), ("230", "energy"),
    ("140", "water"), ("321", "industry"), ("322", "industry"),
    ("323", "industry"), ("331", "trade"), ("410", "environment"),
]


def load(name):
    p = DATA / name
    if not p.exists():
        sys.exit(f"missing {p} — run fetch_sources.py first")
    return json.loads(p.read_text())["features"]


def r(v, dp=3):
    return round(v, dp)


# ---------------------------------------------------------- point in polygon

def build_lookup(countries):
    """Bounding box + ray-cast test per country, for assigning OSM lines."""
    idx = []
    for c in countries:
        xs, ys = [], []
        for poly in c["p"]:
            for x, y in poly[0]:
                xs.append(x)
                ys.append(y)
        idx.append((c["iso"], c["n"], min(xs), min(ys), max(xs), max(ys), c["p"]))
    return idx


def in_ring(x, y, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xint:
                inside = not inside
        j = i
    return inside


def locate(x, y, idx):
    for iso, name, x0, y0, x1, y1, polys in idx:
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        for poly in polys:
            if in_ring(x, y, poly[0]):
                if not any(in_ring(x, y, h) for h in poly[1:]):
                    return iso, name
    return None, None


# --------------------------------------------------------------- geometry

def simplify(coords, tol=0.02, cap=14):
    """Decimate a way to at most `cap` vertices, keeping ends.

    A continental view cannot resolve more than this, and it keeps the
    embedded payload small enough to ship inside the page.
    """
    pts = [[r(x), r(y)] for x, y in coords]
    out = [pts[0]]
    for p in pts[1:-1]:
        lx, ly = out[-1]
        if abs(p[0] - lx) + abs(p[1] - ly) >= tol:
            out.append(p)
    out.append(pts[-1])
    if len(out) > cap:
        step = len(out) / (cap - 1)
        keep = [out[int(i * step)] for i in range(cap - 1)] + [out[-1]]
        out = keep
    return out


# ------------------------------------------------------------------ layers

def build_assets():
    """GEM power units. One row per unit; project_id lets you dedupe."""
    rows = []
    for f in load("gem_power_assets.geojson"):
        p = f["properties"]
        iso = NAME_TO_ISO.get((p.get("country") or "").strip())
        if not iso:
            continue
        lon, lat = f["geometry"]["coordinates"]
        try:
            cap = round(float(p["capacity_mw"]), 1) if p.get("capacity_mw") else None
        except (TypeError, ValueError):
            cap = None
        yr = None
        if p.get("start_year"):
            m = re.match(r"(\d{4})", str(p["start_year"]))
            yr = int(m.group(1)) if m else None
        rows.append([
            (p.get("name") or "").strip()[:78], iso, r(lon), r(lat),
            p.get("dash_status"), (p.get("tech") or "").strip()[:26] or None,
            cap, yr, p.get("project_id") or None, p.get("url") or None,
        ])
    return {
        "cols": ["name", "iso", "lon", "lat", "status", "tech", "mw", "yr",
                 "pid", "url"],
        "rows": rows,
    }


def build_finance():
    """AfDB activities, deduped to one point per project.

    Prefers an exactness=1 location so the marker sits on the works rather
    than at a country centroid.
    """
    best = {}
    for f in load("iati_afdb_finance.geojson"):
        p = f["properties"]
        pid = p.get("iati_id")
        if not pid:
            continue
        prec = p.get("geo_precision")
        rank = 0 if prec == "1" else 1
        if pid in best and best[pid][0] <= rank:
            continue
        lon, lat = f["geometry"]["coordinates"]
        sector = None
        for code in (p.get("dac_sectors") or []):
            for pre, s in DAC_SECTOR:
                if code.startswith(pre):
                    sector = s
                    break
            if sector:
                break
        com = p.get("commitment")
        best[pid] = (rank, [
            (p.get("name") or "").strip()[:88],
            p.get("country") or "", r(lon), r(lat), p.get("dash_status"),
            sector, round(com * SDR_USD / 1e6, 2) if com else None,
            prec, p.get("location_name") or None, pid,
        ])
    return {
        "cols": ["name", "iso", "lon", "lat", "status", "sector",
                 "usd_m", "prec", "place", "iid"],
        "rows": [v[1] for v in best.values()],
    }


def build_ground(idx):
    """OSM ways, dissolved by name where a name exists."""
    feats = load("osm_construction.geojson")
    groups, loose = {}, []
    for f in feats:
        p = f["properties"]
        g = f["geometry"]["coordinates"]
        if len(g) < 2:
            continue
        key = (p.get("name"), p.get("sector")) if p.get("name") else None
        if key:
            groups.setdefault(key, {"p": p, "parts": []})["parts"].append(g)
        else:
            loose.append((p, [g]))

    out = []
    for (name, sector), v in groups.items():
        out.append((v["p"], v["parts"]))
    out.extend(loose)

    rows = []
    skipped = 0
    for p, parts in out:
        # A handful of level-crossing stubs come through with no status
        # resolved. They are unnamed service track, not projects — drop them
        # rather than let them vanish silently from every status filter.
        if not p.get("dash_status"):
            skipped += 1
            continue
        parts = sorted(parts, key=len, reverse=True)[:6]
        mid = parts[0][len(parts[0]) // 2]
        iso, _ = locate(mid[0], mid[1], idx)
        rows.append({
            "n": (p.get("name") or "").strip()[:78] or None,
            "iso": iso,
            "sec": p.get("sector"),
            "st": p.get("dash_status"),
            "cls": p.get("eventual_class"),
            "wd": p.get("wikidata"),
            "oid": (p.get("osm_id") or "").replace("way/", "") or None,
            "g": [simplify(part) for part in parts],
        })
    if skipped:
        print(f"   dropped {skipped} unnamed stub(s) with no resolved status")
    return rows


# ------------------------------------------------------------------- build

def main():
    base = json.loads((DATA / "africa_basemap.json").read_text())
    countries = base["countries"]
    idx = build_lookup(countries)

    print("assets  …")
    assets = build_assets()
    print(f"   {len(assets['rows']):,} power units")

    print("finance …")
    finance = build_finance()
    print(f"   {len(finance['rows']):,} projects")

    print("ground  …")
    ground = build_ground(idx)
    located = sum(1 for g in ground if g["iso"])
    print(f"   {len(ground):,} works ({located:,} located to a country)")

    # Natural Earth's NAME field carries map abbreviations ("Dem. Rep. Congo",
    # "Eq. Guinea"). Those are right for a cramped label on a map and wrong for
    # a filter dropdown, so NE fills gaps and the full names win.
    names = {}
    for c in countries:
        if c["iso"]:
            names[c["iso"]] = c["n"]
    names.update(ISO_TO_NAME)
    # ISO_TO_NAME is built by first-wins from the GEM alias table, which
    # yields some exonyms. Prefer the official forms for display.
    names.update({"CI": "Côte d'Ivoire", "CV": "Cabo Verde",
                  "CG": "Republic of the Congo", "-99": "Somaliland",
                  "EH": "Western Sahara"})
    # Natural Earth draws Somaliland (no ISO code, hence "-99") and Western
    # Sahara as polygons separate from Somalia and Morocco. That is the
    # boundary source's cartographic choice; label them plainly rather than
    # leaving records attributed to an unnamed code.
    names["-99"] = "Somaliland"
    names["EH"] = "Western Sahara"
    for i in ISLANDS:
        names[i["iso"]] = i["n"]

    payload = {
        "meta": payload_meta(load_meta()),
        "names": names,
        "basemap": {"countries": countries, "islands": ISLANDS},
        "assets": assets,
        "finance": finance,
        "ground": ground,
    }

    blob = json.dumps(payload, separators=(",", ":"))
    html = brand_assets(TEMPLATE.read_text())
    if "/*__PAYLOAD__*/" not in html:
        sys.exit("template missing /*__PAYLOAD__*/ marker")
    page = html.replace("/*__PAYLOAD__*/", blob)
    OUT.write_text(page)
    kb = OUT.stat().st_size / 1024
    print(f"\npayload {len(blob) / 1024:.0f} KB → {OUT.name} {kb:.0f} KB")
    if kb > 15000:
        print("  ! approaching the 16 MB artifact ceiling")

    # GitHub Pages copy: a complete document rather than an artifact fragment.
    DOCS.mkdir(exist_ok=True)
    (DOCS / "dashboard.html").write_text(wrap_document(
        page, title="Africa Infrastructure Monitor", path="dashboard.html", kind="dashboard",
        facts=site_facts(assets, finance, ground),
        description="Dashboard of announced, approved and ongoing infrastructure in Africa: "
                    "power plants, African Development Bank finance and construction works from "
                    "OpenStreetMap, with charts by country and sector and a sortable project table."))
    print(f"→ docs/dashboard.html")


if __name__ == "__main__":
    main()
