#!/usr/bin/env python3
"""
Compile the six ingested layers into a single self-contained dashboard.

Reads   data/*.geojson  +  data/africa_basemap.json  +  data/africa_basemap_10m.json
        (the latter for the rest of the world, drawn as grey context, and
        for the country label anchors)
Writes  dashboard.html   (payload injected inline)

The dashboard has to be self-contained: the publishing sandbox blocks runtime
requests to any external host, so there is no tile server and no fetch() —
the basemap and every project record ship inside the page. That is also why
the payload is stored column-wise rather than as an array of objects.
"""

import json
import math
import pathlib
import re
import sys

from fetch_basemap import WIN, dp, ring_area, rnd, touches
from shared import (  # noqa: F401  (SDR_* re-exported for build_map.py)
    DASHBOARD_LAYERS, DOCS, SDR_NOTE, SDR_USD, brand_assets, inline_vendor, load_meta,
    payload_meta, site_facts, wrap_document,
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
    "Western Sahara": "EH", "The Gambia": "GM", "Democratic Republic of the Congo": "CD",
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

def load_10m():
    p = DATA / "africa_basemap_10m.json"
    if not p.exists():
        sys.exit("missing data/africa_basemap_10m.json — run fetch_basemap.py first")
    return json.loads(p.read_text())


def build_labels():
    """One label anchor per African country, as the map page draws them:
    Natural Earth's LABEL_X/Y and MIN_LABEL, with NE's short map name
    ("Dem. Rep. Congo"), which is the right form for a label even though
    the dropdowns use the full one."""
    return load_10m()["labels"]


def build_context():
    """The rest of the world as grey context land, so the dashboard's basemap
    is the whole world like the map page's and a cable heading for India or a
    pipeline into Spain ends on a coast rather than in open sea. Taken from
    the 1:10m file the map page ships and simplified much harder: this page
    zooms to a country at most, and the land is context, never selectable.
    Countries inside the detail window (Europe, the Middle East) keep a
    little more shape than the far side of the world. Small islands go."""
    out = []
    for c in load_10m()["countries"]:
        if c["af"]:
            continue   # Africa comes from the 110m file, with its own styling and hit-testing
        polys = []
        for poly in c["p"]:
            near = touches(poly[0], WIN)
            rings = []
            for j, ring in enumerate(poly):
                r = rnd(dp(ring, 0.04), 2) if near else rnd(dp(ring, 0.15), 1)
                if len(r) >= 4 and (j == 0 or ring_area(r) > (0.05 if near else 0.2)):
                    rings.append(r)
            if rings and ring_area(rings[0]) > (0.1 if near else 0.4):
                polys.append(rings)
        if polys:
            out.append(polys)
    return out


# The finance layer's two lenders: file, short lender code as the payload
# carries it, and how their amounts reach US dollars. AfDB reports in XDR
# (IMF SDR); the World Bank in USD. Kept in step with build_map.py.
FINANCE_FILES = [("iati_afdb_finance.geojson", "AfDB"), ("iati_worldbank_finance.geojson", "WB")]
TO_USD = {"XDR": SDR_USD, "USD": 1.0}

# DAC 5-digit purpose codes → the dashboard's sector vocabulary.
DAC_SECTOR = [
    ("210", "transport"), ("220", "ict"), ("23", "energy"),
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

# The dashboard frame (the template's BOUNDS) plus a margin, in degrees. A
# pipeline or cable route is clipped to this window at build time: a cable
# from Europe to India is drawn only where it runs around the continent, so
# the frame stays readable and the payload small. The margin lets a route run
# off the canvas rather than stop at its edge.
LINE_WINDOW = (-32.0, -48.0, 66.0, 50.0)


def simplify_line(coords, tol=0.012):
    """Dashboard simplification for a pipeline or cable route: Douglas-Peucker
    at about a kilometre, three-decimal rounding, clipped to LINE_WINDOW.
    Returns a list of parts, because a route that leaves the window and comes
    back becomes several. The map uses a finer tolerance and no clipping."""
    pts = dp([tuple(c[:2]) for c in coords], tol)
    x0, y0, x1, y1 = LINE_WINDOW
    inside = lambda q: x0 <= q[0] <= x1 and y0 <= q[1] <= y1  # noqa: E731
    parts, cur = [], []
    for i, q in enumerate(pts):
        if inside(q):
            if not cur and i:
                cur.append(pts[i - 1])   # the vertex before entering, so the line comes in from off-frame
            cur.append(q)
        elif cur:
            cur.append(q)                # the vertex after leaving
            parts.append(cur)
            cur = []
    if cur:
        parts.append(cur)
    out = []
    for part in parts:
        q = []
        for x, y in part:
            v = [r(x), r(y)]
            if not q or q[-1] != v:
                q.append(v)
        if len(q) >= 2:
            out.append(q)
    return out


def _length_km(geoms):
    """Sum of segment lengths of already-simplified [lon, lat] parts."""
    total = 0.0
    for g in geoms:
        for a, b in zip(g, g[1:]):
            dx = (b[0] - a[0]) * 111.32 * abs(math.cos(math.radians(a[1])))
            dy = (b[1] - a[1]) * 110.57
            total += (dx * dx + dy * dy) ** 0.5
    return total


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
    """AfDB and World Bank activities, one record per activity per lender.

    The map carries the same two lenders (build_map.build_finance); this keeps
    the leaner column set the dashboard actually reads. Precision rank per
    location: 0 = exact site (IATI exactness 1, AfDB), 1 = a named place or
    site (World Bank location-class 2 or 4, which the Bank still marks
    exactness 2), 2 = a country or region centroid. The best location a lender
    publishes becomes the marker.
    """
    best = {}
    for fname, ln in FINANCE_FILES:
        if not (DATA / fname).exists():
            print(f"   ! {fname} missing, lender {ln} skipped")
            continue
        for f in load(fname):
            p = f["properties"]
            pid = p.get("iati_id")
            if not pid:
                continue
            if p.get("geo_precision") == "1":
                rank = 0
            elif p.get("location_class") in ("2", "4"):
                rank = 1
            else:
                rank = 2
            key = (ln, pid)
            if key in best and best[key][0] <= rank:
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
            rate = TO_USD.get(p.get("currency") or ("XDR" if ln == "AfDB" else "USD"))
            best[key] = (rank, [
                (p.get("name") or "").strip()[:88],
                p.get("country") or "", r(lon), r(lat), p.get("dash_status"),
                sector, round(com * rate / 1e6, 2) if com and rate else None,
                rank, (p.get("location_name") or "")[:40] or None, pid, ln,
                p.get("project_url") or None,
            ])
    return {
        "cols": ["name", "iso", "lon", "lat", "status", "sector",
                 "usd_m", "prec", "place", "iid", "ln", "purl"],
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


# The two line layers. Shared with build_map.py, which passes its own, finer
# simplifier; the dashboard clips and thins the routes for a continental frame.

def _isos(names):
    out = []
    for n in names or []:
        iso = NAME_TO_ISO.get(n)
        if iso and iso not in out:
            out.append(iso)
    return out


def _route_parts(f, simp):
    parts = sorted(f["geometry"]["coordinates"], key=len, reverse=True)
    return [g for part in parts for g in simp(part) if len(g) >= 2]


def build_pipelines(idx, simp=simplify_line):
    """One record per GEM pipeline segment that has a route. `simp` maps one
    raw part to a list of simplified parts."""
    rows = []
    for f in load("gem_oil_gas_pipelines.geojson"):
        p = f["properties"]
        if not p.get("dash_status"):
            continue
        geoms = _route_parts(f, simp)
        if not geoms:
            continue
        mid = geoms[0][len(geoms[0]) // 2]
        isos = _isos(p.get("countries"))
        iso = isos[0] if isos else locate(mid[0], mid[1], idx)[0]
        cap = None
        if p.get("capacity") is not None and p.get("capacity_units"):
            cap = f"{p['capacity']:,.0f} {p['capacity_units']}".replace(".0 ", " ")
        rows.append([
            (p.get("name") or "").strip()[:110] or None, iso, mid[0], mid[1],
            p["dash_status"], (p.get("fuel") or "").strip()[:12] or None,
            round(p["length_km"], 1) if p.get("length_km") else round(_length_km(geoms), 1),
            cap, p.get("capacity_bcm_y"), p.get("capacity_boed"),
            (p.get("start_year") or "")[:4] or None,
            (p.get("owner") or "").strip()[:120] or None,
            (p.get("start_location") or "").strip()[:50] or None,
            (p.get("end_location") or "").strip()[:50] or None,
            p.get("diameter") or None,
            p.get("project_id") or None, p.get("url") or None, p.get("tracker"),
            isos or None, (p.get("pipeline") or "").strip()[:90] or None, geoms,
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "fuel", "km", "cap", "bcm", "boed",
                     "yr", "owner", "from", "to", "dia", "pid", "url", "trk", "isos", "pipe", "g"],
            "rows": rows}


def build_cables(idx, simp=simplify_line, rnd=r):
    """One record per submarine cable landing in Africa. The marker sits at
    the centre of its African landing points, so a cable that also reaches
    India or Europe is filed where it touches the continent. `rnd` rounds
    coordinates, so each page keeps its own precision."""
    rows = []
    for f in load("telegeography_cables.geojson"):
        p = f["properties"]
        if not p.get("dash_status"):
            continue
        geoms = _route_parts(f, simp)
        if not geoms:
            continue
        lps = [[rnd(lp["lon"]), rnd(lp["lat"]), (lp.get("name") or "").split(",")[0][:40], lp.get("iso")]
               for lp in p.get("landing_points") or []]
        if lps:
            lon = sum(x[0] for x in lps) / len(lps)
            lat = sum(x[1] for x in lps) / len(lps)
        else:
            lon, lat = geoms[0][len(geoms[0]) // 2]
        isos = []
        for lp in lps:
            if lp[3] and lp[3] not in isos:
                isos.append(lp[3])
        rows.append([
            (p.get("name") or "").strip()[:100] or None, isos[0] if isos else None,
            rnd(lon), rnd(lat), p["dash_status"], p.get("rfs_year"),
            1 if p.get("is_planned") else 0,
            # TeleGeography leaves length blank for a few planned systems
            # (Umoja, MRSC); fall back to the drawn route so they still rank
            round(p["length_km"]) if p.get("length_km") else round(_length_km(geoms)),
            (p.get("owners") or "").strip()[:200] or None,
            (p.get("suppliers") or "").strip()[:80] or None,
            p.get("url") or None, p.get("cable_id"),
            p.get("landing_total") or len(lps), len(p.get("countries") or []),
            (p.get("notes") or "").strip()[:200] or None,
            lps or None, isos or None, geoms,
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "rfs", "planned", "km", "owners",
                     "suppliers", "url", "cid", "lp_total", "n_cts", "notes", "lps", "isos", "g"],
            "rows": rows}


# AidData's Chinese official finance. Shared with build_map.py like the line
# layers: a point per project, plus the OpenStreetMap footprint (closed rings
# of a buffered, dissolved feature) where AidData geocoded the project
# precisely. `min_extent` drops rings too small to read at the page's scale
# (a building on the dashboard's continental frame); `cap` bounds the vertices
# a single footprint may carry (the whole TAZARA railway comes with several
# records).
CHINA_PREC = {"precise": 0, "within_5km": 1, "admin": 2, "country": 3}


def _decimate(geoms, cap):
    total = sum(len(g) for g in geoms)
    if total <= cap:
        return geoms
    out = []
    for g in geoms:
        n = max(3, int(len(g) * cap / total))
        if len(g) <= n:
            out.append(g)
            continue
        step = (len(g) - 1) / (n - 1)
        q = [g[round(i * step)] for i in range(n - 1)] + [g[-1]]
        out.append(q)
    return out


def _china_title(t, n=130):
    """AidData's titles are sentences, sometimes suffixed "(Linked to Project
    ID#12345)"; drop the suffix and cut long ones at a word boundary."""
    t = re.sub(r"\s*\(Linked to Project ID#?[^)]*\)", "", (t or "").strip())
    if len(t) <= n:
        return t or None
    cut = t[:n].rsplit(" ", 1)[0]
    return (cut if len(cut) > n * 0.6 else t[:n - 1]).rstrip(",;:·-— ") + "…"


def build_china(idx, simp=simplify_line, rnd=r, cap=60, min_extent=0.02):
    rows = []
    for f in load("aiddata_china_finance.geojson"):
        p = f["properties"]
        if not p.get("dash_status"):
            continue
        geoms = None
        if f["geometry"]["type"] == "MultiLineString":
            geoms = [g for g in _route_parts(f, simp)
                     if max(max(q[0] for q in g) - min(q[0] for q in g),
                            max(q[1] for q in g) - min(q[1] for q in g)) >= min_extent]
            geoms = _decimate(geoms, cap) if geoms else None
        lon, lat = p["lon"], p["lat"]
        iso = p.get("country") or locate(lon, lat, idx)[0]
        amt = p.get("amount_usd_2021")
        # the OSM link without its host and map fragment: "way/1164438280"
        osm = re.sub(r"^https?://www\.openstreetmap\.org/|#.*$", "", (p.get("osm_links") or [""])[0]) or None
        rows.append([
            _china_title(p.get("name")), iso, rnd(lon), rnd(lat),
            p["dash_status"], p.get("sector") or "other",
            round(amt / 1e6, 2) if amt else None,
            CHINA_PREC.get(p.get("geo_precision"), 3), (p.get("place") or "")[:50] or None,
            p.get("aiddata_id"), p.get("sector_code"),
            p.get("flow_simple"), p.get("flow_class"),
            (p.get("funders") or "")[:110] or None, (p.get("implementers") or "")[:110] or None,
            p.get("commitment_year"), p.get("start_year"), p.get("completion_year"),
            p.get("interest_rate"), p.get("maturity_years"),
            1 if p.get("financial_distress") else 0,
            (p.get("cofinanciers") or "")[:100] if p.get("cofinanced") else None,
            # AidData's own word only where the shared status does not imply it
            p.get("raw_status") if p["dash_status"] == "stalled" else None,
            1 if p.get("amount_estimated") else 0, osm, geoms,
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "sector", "usd_m", "prec", "place", "aid",
                     "sc", "flow", "cls", "funders", "impl", "cyr", "syr", "eyr", "rate", "mat",
                     "distress", "cofin", "raw", "est", "osm", "g"],
            "rows": rows}


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
    fc = finance["cols"]
    by_ln = {ln: sum(1 for x in finance["rows"] if x[fc.index("ln")] == ln) for ln in ("AfDB", "WB")}
    print(f"   {len(finance['rows']):,} projects ({by_ln['AfDB']:,} AfDB, {by_ln['WB']:,} World Bank)")

    print("ground  …")
    ground = build_ground(idx)
    located = sum(1 for g in ground if g["iso"])
    print(f"   {len(ground):,} works ({located:,} located to a country)")

    print("pipes   …")
    pipelines = build_pipelines(idx)
    pkm = sum(x[pipelines["cols"].index("km")] or 0 for x in pipelines["rows"])
    print(f"   {len(pipelines['rows']):,} pipeline segments, {pkm:,.0f} km")

    print("cables  …")
    cables = build_cables(idx)
    nlp = sum(len(x[cables["cols"].index("lps")] or []) for x in cables["rows"])
    print(f"   {len(cables['rows']):,} submarine cables, {nlp:,} African landing points")

    print("china   …")
    china = build_china(idx)
    cc = china["cols"]
    cusd = sum(x[cc.index("usd_m")] or 0 for x in china["rows"]) / 1000
    cfp = sum(1 for x in china["rows"] if x[cc.index("g")])
    print(f"   {len(china['rows']):,} Chinese-financed projects, ${cusd:,.1f}bn (2021 USD), {cfp:,} footprints kept")

    labels = build_labels()
    print(f"   {len(labels):,} country labels")

    print("context …")
    context = build_context()
    print(f"   {len(context):,} countries beyond Africa, {sum(len(r) for c in context for p in c for r in p):,} vertices")

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
    # islands that only submarine cables reach
    names.update({"YT": "Mayotte", "RE": "Réunion", "SH": "Saint Helena"})

    payload = {
        "meta": payload_meta(load_meta(), DASHBOARD_LAYERS),
        "names": names,
        "basemap": {"countries": countries, "islands": ISLANDS, "context": context, "labels": labels},
        "assets": assets,
        "finance": finance,
        "ground": ground,
        "pipelines": pipelines,
        "cables": cables,
        "china": china,
    }

    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    html = inline_vendor(brand_assets(TEMPLATE.read_text()))
    if "/*__PAYLOAD__*/" not in html:
        sys.exit("template missing /*__PAYLOAD__*/ marker")
    page = html.replace("/*__PAYLOAD__*/", blob)
    OUT.write_text(page)
    kb = OUT.stat().st_size / 1024
    print(f"\npayload {len(blob.encode()) / 1024:.0f} KB → {OUT.name} {kb:.0f} KB")
    for k in ("basemap", "assets", "finance", "ground", "pipelines", "cables", "china"):
        print(f"   {k:9s} {len(json.dumps(payload[k], separators=(',', ':'), ensure_ascii=False).encode()) / 1024:6.0f} KB")
    if kb > 15000:
        print("  ! approaching the 16 MB artifact ceiling")

    # GitHub Pages copy: a complete document rather than an artifact fragment.
    DOCS.mkdir(exist_ok=True)
    (DOCS / "dashboard.html").write_text(wrap_document(
        page, title="Africa Infrastructure Map", path="dashboard.html", kind="dashboard",
        facts=site_facts(assets, finance, ground, pipelines, cables, china),
        description="Dashboard of announced, approved and ongoing infrastructure in Africa: "
                    "power plants and oil and gas pipelines (Global Energy Monitor), African "
                    "Development Bank and World Bank finance, Chinese-financed projects "
                    "2000–2021 (AidData), "
                    "construction works from OpenStreetMap and submarine cables (TeleGeography), "
                    "with charts by country and sector and a sortable project table."))
    print(f"→ docs/dashboard.html")


if __name__ == "__main__":
    main()
