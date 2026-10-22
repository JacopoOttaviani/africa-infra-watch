#!/usr/bin/env python3
"""
Compile the eight ingested layers into a single self-contained dashboard.

Reads   data/*.geojson  +  data/africa_basemap.json  +  data/africa_basemap_10m.json
        (the latter for the rest of the world, drawn as grey context, and
        for the country label anchors)
Writes  dashboard.html   (payload injected inline)

With AIW_REGION=sea the same script reads data/sea/ and writes the Southeast
Asia edition under docs/se-asia/ (see region.py).

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
from region import REGION
from shared import (  # noqa: F401  (SDR_* re-exported for build_map.py)
    BANK, DASHBOARD_LAYERS, DATA, DOCS, EUR_USD, LOCAL_NOTE, LOCAL_USD, SDR_NOTE, SDR_USD, brand_assets, inline_vendor, load_meta,
    SITE_NAME, china_span, payload_meta, site_facts, wrap_document,
)

ROOT = pathlib.Path(__file__).parent

from build_debt import dashboard_payload as debt_payload  # noqa: E402
TEMPLATE = ROOT / "dashboard.template.html"
# the artifact build (payload inlined); another edition's carries its key: dashboard.sea.html
OUT = ROOT / ("dashboard.html" if REGION.key == "africa" else f"dashboard.{REGION.key}.html")

# GEM uses country names; IATI uses ISO-3166-1 alpha-2. Bridge them (the
# region's table, region.py; first name wins for ISO -> name).
NAME_TO_ISO = dict(REGION.names)
ISO_TO_NAME = {}
for _n, _i in NAME_TO_ISO.items():
    ISO_TO_NAME.setdefault(_i, _n)

# Islands too small to appear in Natural Earth 110m — drawn as markers so
# their projects don't float in blank ocean.
ISLANDS = REGION.islands

def load_10m():
    p = DATA / REGION.basemap_10m
    if not p.exists():
        sys.exit(f"missing {p} — run fetch_basemap.py first")
    return json.loads(p.read_text())


def build_labels():
    """One label anchor per country of the region, as the map page draws them:
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
            continue   # the region comes from the coarse file, with its own styling and hit-testing
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


# The finance layer's lenders: file, short lender code as the payload
# carries it, and how their amounts reach US dollars. AfDB reports in XDR
# (IMF SDR); ADB and the World Bank in USD; AFD (Africa only) in EUR. Kept in
# step with build_map.py.
FINANCE_FILES = [(f"iati_{REGION.bank['publisher']}_finance.geojson", BANK), ("iati_worldbank_finance.geojson", "WB")]
if getattr(REGION, "afd_files", None):
    FINANCE_FILES.append(("iati_afd_finance.geojson", "AFD"))
TO_USD = {"XDR": SDR_USD, "USD": 1.0, "EUR": EUR_USD, **LOCAL_USD}

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
LINE_WINDOW = REGION.line_window


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
            # exact site or not, as on the map: the record card's
            # "possibly the same project" lookup trusts only exact units by distance
            1 if p.get("geo_precision") == "exact" else 0,
        ])
    return {
        "cols": ["name", "iso", "lon", "lat", "status", "tech", "mw", "yr",
                 "pid", "url", "exact"],
        "rows": rows,
    }


def build_finance():
    """AfDB, World Bank and AFD activities, one record per activity per lender.

    The map carries the same lenders (build_map.build_finance); this keeps
    the leaner column set the dashboard actually reads. Precision rank per
    location: 0 = exact site (IATI exactness 1, AfDB), 1 = a named place or
    site (World Bank location-class 2 or 4, which the Bank still marks
    exactness 2; an AFD point that is not its office), 2 = a country or
    region centroid. The best location a lender publishes becomes the marker.
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
            elif p.get("location_class") in ("2", "4") or p.get("place_given"):
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
            com, pub = p.get("commitment"), p.get("commitment_published")
            cur = p.get("currency") or (REGION.bank["currency"] if ln == BANK else "USD")
            rate = TO_USD.get(cur)
            cnote = p.get("counted_note")
            if cur in LOCAL_USD:      # a loan published in the borrower's currency
                cnote = "; ".join(x for x in (cnote, f"published in {cur}, converted at 1 {cur} = {LOCAL_USD[cur]:g} USD ({LOCAL_NOTE})") if x)
            best[key] = (rank, [
                (p.get("name") or "").strip()[:88],
                p.get("country") or "", r(lon), r(lat), p.get("dash_status"),
                sector, round(com * rate / 1e6, 2) if com and rate else None,
                rank, (p.get("location_name") or "")[:40] or None, pid, ln,
                p.get("project_url") or None,
                # the lender's own figure where the counted one differs, and why
                round(pub * rate / 1e6, 2) if pub and rate else None, p.get("counted_note"),
            ])
    return {
        "cols": ["name", "iso", "lon", "lat", "status", "sector",
                 "usd_m", "prec", "place", "iid", "ln", "purl", "pub_m", "cnote"],
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
        # the middle vertex of the longest raw part, as build_map takes it,
        # so a coastal or border work lands in the same country on both pages
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
            p.get("length_note") or None,
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "fuel", "km", "cap", "bcm", "boed",
                     "yr", "owner", "from", "to", "dia", "pid", "url", "trk", "isos", "pipe", "g", "lnote"],
            "rows": rows}


def build_cables(idx, simp=simplify_line, rnd=r):
    """One record per submarine cable landing in the region. The marker sits at
    the centre of its landing points there, so a cable that also reaches
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
            # TeleGeography leaves length blank for a few systems (Umoja,
            # FEA, ReuNION); the fetcher's estimate from the whole drawn route
            # stands in, flagged, so both pages show the same figure
            round(p["length_km"]) if p.get("length_km") else (p.get("length_km_est") or None),
            # owner and supplier lists whole: the Methodology tallies them,
            # and a consortium cable lists a dozen or more
            (p.get("owners") or "").strip() or None,
            (p.get("suppliers") or "").strip() or None,
            p.get("url") or None, p.get("cable_id"),
            p.get("landing_total") or len(lps), len(p.get("countries") or []),
            (p.get("notes") or "").strip()[:400] or None,
            lps or None, isos or None, geoms,
            0 if p.get("length_km") else 1,
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "rfs", "planned", "km", "owners",
                     "suppliers", "url", "cid", "lp_total", "n_cts", "notes", "lps", "isos", "g", "km_est"],
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
    t = re.sub(r"\s*\(Linked to (?:Project|Record) ID#?[^)]*\)", "", (t or "").strip())
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
        amt, pub = p.get("amount_usd_const"), p.get("amount_usd_const_published")
        # the OSM link without its host and map fragment: "way/1164438280"
        osm = re.sub(r"^https?://www\.openstreetmap\.org/|#.*$", "", (p.get("osm_links") or [""])[0]) or None
        rows.append([
            _china_title(p.get("name")), iso, rnd(lon), rnd(lat),
            p["dash_status"], p.get("sector") or "other",
            round(amt / 1e6, 2) if amt else None,
            CHINA_PREC.get(p.get("geo_precision"), 3), (p.get("place") or "")[:50] or None,
            p.get("aiddata_id"), p.get("sector_code"),
            p.get("flow_simple"), p.get("flow_class"),
            # whole lists: the Methodology tallies funders and implementers
            p.get("funders") or None, p.get("implementers") or None,
            p.get("commitment_year"), p.get("start_year"), p.get("completion_year"),
            p.get("interest_rate"), p.get("maturity_years"),
            1 if p.get("financial_distress") else 0,
            # co-financed by AidData's flag; some flagged records name no co-financier
            ((p.get("cofinanciers") or "")[:100] or "unnamed") if p.get("cofinanced") else None,
            # AidData's own word only where the shared status does not imply it
            p.get("raw_status") if p["dash_status"] == "stalled" else None,
            1 if p.get("amount_estimated") else 0, osm, geoms,
            round(pub / 1e6, 2) if pub else None, p.get("counted_note"),
            # new in AidData's CLG 1.0: no location published yet, so at the country's centre
            1 if p.get("new_in_clg") else 0,
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "sector", "usd_m", "prec", "place", "aid",
                     "sc", "flow", "cls", "funders", "impl", "cyr", "syr", "eyr", "rate", "mat",
                     "distress", "cofin", "raw", "est", "osm", "g", "pub_m", "cnote", "new"],
            "rows": rows}


# The EU institutions' finance, shared with build_map.py like the Chinese
# layer: one point per record (a Commission contract or uncontracted decision,
# an EIB operation), its commitment in euros converted at the stated rate,
# and the other named places a contract lists, for the detail view.
def build_eu(idx, rnd=r):
    rows = []
    for f in load("iati_eu_finance.geojson"):
        p = f["properties"]
        if not p.get("dash_status"):
            continue
        lon, lat = f["geometry"]["coordinates"]
        sector = p.get("sector")
        codes = p.get("sector_codes") or []
        if not sector:
            for code in codes:
                for pre, s in DAC_SECTOR:
                    if code.startswith(pre):
                        sector = s
                        break
                if sector:
                    break
        com, dis, pub = p.get("commitment"), p.get("disbursed"), p.get("commitment_published")
        locs = p.get("locations") or None
        if locs:
            locs = [[rnd(x), rnd(y), (n or "")[:40]] for x, y, n in locs[:16]]
        cts = p.get("countries") or []
        rows.append([
            (p.get("name") or "").strip()[:110] or None, p.get("country") or "",
            rnd(lon), rnd(lat), p["dash_status"], sector or "other",
            round(com * EUR_USD / 1e6, 2) if com else None,
            round(com / 1e6, 2) if com else None,
            round(dis * EUR_USD / 1e6, 2) if dis else None,
            p.get("geo_precision"), (p.get("location_name") or "")[:40] or None,
            p.get("iati_id"), codes[0] if codes else None, (p.get("sector_label") or "")[:60] or None,
            p.get("publisher"), p.get("kind"), (p.get("parent_name") or "")[:110] or None,
            (p.get("implementers") or "")[:400] or None, p.get("instrument"), p.get("aid_type_name"),
            p.get("start_year"), p.get("end_year"), p.get("project_url"), locs,
            1 if p.get("mixed_currency") else 0, cts if len(cts) > 1 else None, p.get("region"),
            round(pub / 1e6, 2) if pub else None, p.get("counted_note"),
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "sector", "usd_m", "eur_m", "dis_m", "prec",
                     "place", "iid", "dac", "slabel", "pub", "kind", "parent", "impl", "instr", "aid",
                     "syr", "eyr", "purl", "locs", "mixed", "isos", "region", "pub_eur", "cnote"],
            "rows": rows}


def eu_summary(eu):
    """One line for the build log: records, dollars, and the split by publisher."""
    ec = eu["cols"]
    usd = sum(x[ec.index("usd_m")] or 0 for x in eu["rows"]) / 1000
    by = {k: sum(1 for x in eu["rows"] if x[ec.index("pub")] == k) for k in ("INTPA", "NEAR", "EIB")}
    return (f"{len(eu['rows']):,} EU-financed records, ${usd:,.1f}bn at {EUR_USD} USD/EUR "
            f"({by['INTPA']:,} INTPA, {by['NEAR']:,} NEAR, {by['EIB']:,} EIB)")


# Italy's Piano Mattei, shared with build_map.py like the EU layer: one
# point per project as the Government's portal lists it, the amount the portal
# states (euros, converted at the stated rate), the portal's stage and
# directives, and the other named places for the detail view.
def build_mattei(idx, rnd=r):
    rows = []
    for f in load("piano_mattei.geojson"):
        p = f["properties"]
        if not p.get("dash_status"):
            continue
        lon, lat = f["geometry"]["coordinates"]
        eur = p.get("amount_eur")
        locs = p.get("locations") or None
        if locs:
            locs = [[rnd(x), rnd(y), (n or "")[:40]] for x, y, n in locs[:16]]
        cts = p.get("countries") or []
        rows.append([
            (p.get("name") or "").strip()[:120] or None, p.get("country") or "",
            rnd(lon), rnd(lat), p["dash_status"], p.get("sector") or "other",
            round(eur * EUR_USD / 1e6, 2) if eur else None,
            round(eur / 1e6, 2) if eur else None,
            p.get("geo_precision"), (p.get("location_name") or "")[:48] or None,
            p.get("id"), " · ".join(p.get("directives") or []) or None,
            (p.get("objective") or "")[:140] or None, p.get("stage"),
            # implementer and resources whole: the Methodology tallies them
            (p.get("implementer") or "") or None, (p.get("partnerships") or "")[:160] or None,
            (p.get("international_partners") or "")[:120] or None, (p.get("resources") or "") or None,
            (p.get("amount_text") or "")[:120] or None, 1 if p.get("amount_shared") else 0,
            locs, cts if len(cts) > 1 else None, p.get("url_en") or p.get("url"), p.get("url"),
            (p.get("description") or "")[:360] or None, (p.get("name_it") or "").strip()[:120] or None,
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "sector", "usd_m", "eur_m", "prec", "place",
                     "id", "dirs", "obj", "stage", "impl", "partners", "intl", "funds", "amt", "shared",
                     "locs", "isos", "url", "url_it", "desc", "name_it"],
            "rows": rows}


def mattei_summary(m):
    """One line for the build log: projects, stated euros, and the split by stage."""
    c = m["cols"]
    eur = sum(x[c.index("eur_m")] or 0 for x in m["rows"]) / 1000
    by = {}
    for x in m["rows"]:
        by[x[c.index("stage")]] = by.get(x[c.index("stage")], 0) + 1
    return (f"{len(m['rows']):,} Piano Mattei projects, €{eur:,.2f}bn stated by the portal "
            f"({', '.join(f'{v} {k.lower()}' for k, v in sorted(by.items(), key=lambda kv: -kv[1]))})")


# ------------------------------------------------------------------- build

def main():
    base = json.loads((DATA / REGION.basemap_110).read_text())
    countries = base["countries"]
    idx = build_lookup(countries)

    print("assets  …")
    assets = build_assets()
    print(f"   {len(assets['rows']):,} power units")

    print("finance …")
    finance = build_finance()
    fc = finance["cols"]
    by_ln = {ln: sum(1 for x in finance["rows"] if x[fc.index("ln")] == ln) for ln in (BANK, "WB", "AFD")}
    print(f"   {len(finance['rows']):,} projects ({by_ln[BANK]:,} {BANK}, {by_ln['WB']:,} World Bank"
          + (f", {by_ln['AFD']:,} AFD" if by_ln["AFD"] else "") + ")")

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
    print(f"   {len(cables['rows']):,} submarine cables, {nlp:,} {REGION.adj} landing points")

    print("china   …")
    china = build_china(idx)
    cc = china["cols"]
    cusd = sum(x[cc.index("usd_m")] or 0 for x in china["rows"]) / 1000
    cfp = sum(1 for x in china["rows"] if x[cc.index("g")])
    print(f"   {len(china['rows']):,} Chinese-financed projects, ${cusd:,.1f}bn ({china_span()[2]} USD), {cfp:,} footprints kept")

    print("eu      …")
    eu = build_eu(idx)
    print(f"   {eu_summary(eu)}")

    mattei = None
    if "mattei" in REGION.layers:
        print("mattei  …")
        mattei = build_mattei(idx)
        print(f"   {mattei_summary(mattei)}")

    labels = build_labels()
    print(f"   {len(labels):,} country labels")

    print("context …")
    context = build_context()
    print(f"   {len(context):,} countries beyond {REGION.name}, {sum(len(r) for c in context for p in c for r in p):,} vertices")

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
    # the same display names as the map's (build_map.py), so the two rails
    # read alike: the region's table (for Africa, Natural Earth's Somaliland,
    # "-99", and Western Sahara labelled plainly, and the islands only cables reach)
    names.update(REGION.display)
    for i in ISLANDS:
        names[i["iso"]] = i["n"]

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
        "eu": eu,
        "mattei": mattei,
        # country-year debt by creditor for the "Who it owes" box; None until
        # fetch_debt.py has run, and for an edition without a debt section
        # (the box then hides itself)
        "debt": debt_payload() if REGION.debt else None,
    }

    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    html = inline_vendor(brand_assets(TEMPLATE.read_text(), here="dashboard"))
    if "/*__PAYLOAD__*/" not in html:
        sys.exit("template missing /*__PAYLOAD__*/ marker")
    page = html.replace("/*__PAYLOAD__*/", blob)
    OUT.write_text(page)
    kb = OUT.stat().st_size / 1024
    print(f"\npayload {len(blob.encode()) / 1024:.0f} KB → {OUT.name} {kb:.0f} KB")
    for k in ("basemap", "assets", "finance", "ground", "pipelines", "cables", "china", "eu", "mattei"):
        if payload.get(k) is not None:
            print(f"   {k:9s} {len(json.dumps(payload[k], separators=(',', ':'), ensure_ascii=False).encode()) / 1024:6.0f} KB")
    if kb > 15000:
        print("  ! approaching the 16 MB artifact ceiling")

    # GitHub Pages copy: a complete document rather than an artifact fragment.
    DOCS.mkdir(exist_ok=True)
    (DOCS / "dashboard.html").write_text(wrap_document(
        page, title=SITE_NAME, path="dashboard.html", kind="dashboard",
        facts=site_facts(assets, finance, ground, pipelines, cables, china, eu, mattei),
        description=f"Dashboard of announced, approved and ongoing infrastructure in {REGION.name}: "
                    f"power plants and oil and gas pipelines (Global Energy Monitor), {REGION.bank['name']}, "
                    + ("World Bank and French development agency (AFD) finance, "
                       if any(ln == "AFD" for _, ln in FINANCE_FILES) else "and World Bank finance, ") +
                    "Chinese-financed projects "
                    f"{china_span()[0]}–{china_span()[1]} (AidData), European Union finance (European Commission and EIB), "
                    + ("Italy's Piano Mattei projects, " if mattei is not None else "") +
                    "construction works from OpenStreetMap and submarine cables (TeleGeography), "
                    "with charts by country and sector and a sortable project table."))
    print(f"→ {(DOCS / 'dashboard.html').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
