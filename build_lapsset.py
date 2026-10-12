#!/usr/bin/env python3
"""
Build the LAPSSET Corridor page, docs/lapsset/index.html, from a hand-kept
register of the corridor's projects, data/lapsset.json, and the corridor's
roads and railways from OpenStreetMap, data/lapsset_osm.json.

    python3 build_lapsset.py         build the page
    python3 build_lapsset.py --osm   refetch the roads and railways from Overpass first

The page is not linked from the site yet: it is in no menu, not in the
sitemap or llms.txt, and its <meta robots> says noindex, nofollow. To
announce it, add it to DEEP_THEMES and write_site_index() in shared.py,
add this script to refresh.py's build list and drop the NOINDEX swap below.

LAPSSET (Lamu Port–South Sudan–Ethiopia Transport) is Kenya's plan, launched
in 2012 with Ethiopia and South Sudan, for a port at Lamu and roads, a
railway, oil pipelines, airports and resort cities running north-west to
Juba and north to Addis Ababa. The register is curated by hand, not
fetched: every project, status and financing line in it carries the URL it
was read from. A project belongs to the corridor when the LAPSSET Corridor
Development Authority lists it as a component, when its funder or developer
names LAPSSET, or when it is a section of one of the corridor's roads,
pipelines or railway. Each financing line has a firmness, kept apart from
the project's status: pledged (an announced intention or an MoU), approved
(a board decision), signed (an agreement or concession signed) and
disbursing (money flowing). The corridor-wide figures (its cost, investment
conference pledges) are listed apart and never added to the project lines.

The page reuses the Lobito page's frame and its pure helpers, imported from
build_lobito.py; the functions that read a corridor's own constants (the
map window, the funder groups, the countries) are copied here with
LAPSSET's.
"""

import json
import math
import pathlib
import re
import shutil
import sys
import urllib.parse
import urllib.request

from build_donors import FRAME, table, td
from build_lobito import (FIRM, FIRM_OF, STAGES, STATUS, _bar, _mid, clip_ring, donut, esc, fdot,
                          host, money, native, nice_step, simplify, src_link, st, stage_strip, status_name)
from shared import (AUTHOR_NAME, AUTHOR_URL, DATA, DOCS, EUR_NOTE, EUR_USD, SITE_NAME, SITE_URL, WEB_URL,
                    brand_assets, fmt_date, site_url, today, wrap_document)

ROOT = pathlib.Path(__file__).parent
SRC = DATA / "lapsset.json"
OSM = DATA / "lapsset_osm.json"
FRAG = ROOT / "sections" / "lapsset.html"
SLUG = "lapsset"
TITLE = "The LAPSSET Corridor"
DESCRIPTION = ("The LAPSSET Corridor, Kenya's plan for a port at Lamu with roads, a railway and oil pipelines "
               "to South Sudan and Ethiopia: every part of it, where each one stands and who is paying for it, "
               "from Kenya's own budget to the development banks, China and the oil companies.")


# ------------------------------------------------------------- projection

# An equirectangular window from Juba to the Lamu archipelago, Lamu's coast
# to the Ethiopian border at Moyale. Near the equator a degree of longitude
# is a degree of latitude, so no correction. The road to Addis Ababa leaves
# the top of the map; the locator beside the lede shows all of it.
LON0, LON1, LAT0, LAT1 = 31.1, 41.95, -2.75, 5.55
MAP_W = 1120.0
SC = MAP_W / (LON1 - LON0)
MAP_H = (LAT1 - LAT0) * SC


def xy(lon, lat):
    return round((lon - LON0) * SC, 1), round((LAT1 - lat) * SC, 1)


def offset_line(pts, d):
    """A polyline moved d pixels to its left (negative: right), each vertex
    along the mean of its two segments' normals, so schematic lines drawn
    through the same towns (the railway, the products pipeline) run side by
    side instead of on top of one another."""
    if not d or len(pts) < 2:
        return pts
    norms = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        ln = math.hypot(bx - ax, by - ay) or 1.0
        norms.append(((ay - by) / ln, (bx - ax) / ln))
    out = []
    for i, (x, y) in enumerate(pts):
        n1 = norms[max(i - 1, 0)]
        n2 = norms[min(i, len(norms) - 1)]
        nx, ny = n1[0] + n2[0], n1[1] + n2[1]
        ln = math.hypot(nx, ny) or 1.0
        nx, ny = nx / ln, ny / ln
        k = d / max(nx * n2[0] + ny * n2[1], 0.5)
        out.append((round(x + nx * k, 1), round(y + ny * k, 1)))
    return out


def path_d(lines, closed=False, eps=0.6, off=0.0):
    """lon/lat polylines (or rings) as one SVG path in map pixels."""
    out = []
    for ln in lines:
        pts = [xy(a, b) for a, b in ln]
        if closed:
            pts = clip_ring(pts, -8, -8, MAP_W + 8, MAP_H + 8)
        pts = offset_line(pts, off)
        pts = simplify(pts, eps)
        if len(pts) < (3 if closed else 2):
            continue
        out.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + (" Z" if closed else ""))
    return " ".join(out)


def in_window(lon, lat, pad=0.6):
    return LON0 - pad <= lon <= LON1 + pad and LAT0 - pad <= lat <= LAT1 + pad


# -------------------------------------------------------------- basemap

FOCUS = {"KE", "ET", "SS"}
TOWNS = [  # name, dx, dy, anchor: the label's offset from the dot
    ("Lamu", 7, 4, "start"), ("Witu", -6, -6, "end"), ("Garissa", 7, 14, "start"), ("Isiolo", -7, 4, "end"),
    ("Nairobi", -7, 4, "end"), ("Meru", 7, 4, "start"), ("Marsabit", -7, 4, "end"), ("Moyale", 0, -10, "middle"),
    ("Wajir", 7, 4, "start"), ("Mandera", -7, -4, "end"), ("Lodwar", 7, 4, "start"), ("Lokichar", -7, 4, "end"),
    ("Lokichoggio", -7, 12, "end"), ("Kapoeta", 0, -9, "middle"), ("Torit", 0, -9, "middle"),
    ("Juba", 7, -5, "start"), ("Kampala", 0, 15, "middle"), ("Malindi", -7, 4, "end"),
]
EXTRA_TOWNS = {"Isiolo": (37.58, 0.35), "Lokichar": (35.65, 2.38), "Lokichoggio": (34.35, 4.20),
               "Kapoeta": (33.59, 4.77), "Torit": (32.57, 4.41), "Juba": (31.58, 4.85)}   # not in Natural Earth's places
COUNTRY_LABELS = [("KENYA", 38.3, -1.75), ("ETHIOPIA", 38.4, 5.15), ("SOUTH SUDAN", 32.5, 5.25),
                  ("UGANDA", 33.0, 1.9), ("SOMALIA", 41.55, 2.2)]


def basemap():
    bm = json.loads((DATA / "africa_basemap_10m.json").read_text())
    out = []
    for c in bm["countries"]:
        rings = [ring for poly in c["p"] for ring in poly]
        if not any(in_window(x, y) for ring in rings for x, y in ring):
            continue
        d = path_d(rings, closed=True)
        if d:
            out.append(f'<path class="land{"" if c["iso"] in FOCUS else " ctx"}" d="{d}"><title>{esc(c["n"])}</title></path>')
    adm = [ring for a in bm["admin1"] if a["a3"] in ("KEN", "ETH", "SSD")
           for poly in a["r"] for ring in ([poly] if isinstance(poly[0][0], (int, float)) else poly)]
    out.append(f'<path class="adm" d="{path_d(adm, eps=0.8)}"></path>')
    for lk in bm["lakes"]:
        if any(in_window(x, y) for ring in lk["r"] for x, y in ring):
            out.append(f'<path class="lake" d="{path_d(lk["r"], closed=True)}"><title>{esc(lk["n"])}</title></path>')
    # the larger rivers only, and the Tana, on whose lower course the High Grand Falls dam is planned
    rivers = [r["c"] for r in bm["rivers"] if r.get("n") and (r["s"] <= 6 or r["n"] == "Tana")
              and any(in_window(x, y, 0) for x, y in r["c"])]
    out.append(f'<path class="river" d="{path_d(rivers, eps=0.8)}"></path>')
    for name, lon, lat in COUNTRY_LABELS:
        x, y = xy(lon, lat)
        out.append(f'<text class="ctry" x="{x}" y="{y}" text-anchor="middle">{name}</text>')
    x, y = xy(41.35, -2.55)
    out.append(f'<text class="sea" x="{x}" y="{y}" text-anchor="middle">Indian Ocean</text>')
    places = {p["n"]: p for p in bm["places"] if p["iso"] in FOCUS | {"UG"}}
    places.update({n: {"x": x, "y": y} for n, (x, y) in EXTRA_TOWNS.items()})
    places["Mandera"] = {"x": 41.86, "y": 3.94}     # Natural Earth files it under Somalia
    for name, dx, dy, anchor in TOWNS:
        p = places.get(name)
        if not p:
            continue
        x, y = xy(p["x"], p["y"])
        out.append(f'<circle class="town" cx="{x}" cy="{y}" r="2.6"></circle>'
                   f'<text class="tlbl" x="{x + dx}" y="{y + dy}" text-anchor="{anchor}">{esc(name)}</text>')
    return "\n".join(out)


# ---------------------------------------------------------- the locator

# A small map of the whole continent beside the lede, to say where the
# corridor is before the detail map does: the 1:110m basemap, the three
# corridor countries shaded, the corridor's roads drawn, the detail map's
# window boxed.
LOC_LON0, LOC_LON1, LOC_LAT0, LOC_LAT1 = -18.5, 52.5, -35.5, 38.0
LOC_SC = 5.0
LOC_W, LOC_H = (LOC_LON1 - LOC_LON0) * LOC_SC, (LOC_LAT1 - LOC_LAT0) * LOC_SC


def lxy(lon, lat):
    return round((lon - LOC_LON0) * LOC_SC, 1), round((LOC_LAT1 - lat) * LOC_SC, 1)


def locator(reg, osm):
    bm = json.loads((DATA / "africa_basemap.json").read_text())

    def d_of(lines, closed=False, eps=0.4):
        out = []
        for ln in lines:
            pts = simplify([lxy(a, b) for a, b in ln], eps)
            if len(pts) >= (3 if closed else 2):
                out.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + (" Z" if closed else ""))
        return " ".join(out)
    out = [f'<svg class="loc" viewBox="0 0 {LOC_W:.0f} {LOC_H:.0f}" role="img" aria-label="Map of Africa with '
           f'Kenya, Ethiopia and South Sudan shaded and the LAPSSET Corridor drawn from Lamu, on Kenya\'s Indian '
           f'Ocean coast, to Juba and to Addis Ababa">']
    # the focus countries last, so their outline sits on top of their neighbours'
    for c in sorted(bm["countries"], key=lambda c: c["iso"] in FOCUS):
        d = d_of([ring for poly in c["p"] for ring in poly], closed=True)
        out.append(f'<path class="lc{" on" if c["iso"] in FOCUS else ""}" d="{d}"><title>{esc(c["n"])}</title></path>')
    x0, y0 = lxy(LON0, LAT1)
    x1, y1 = lxy(LON1, LAT0)
    out.append(f'<rect class="lwin" x="{x0}" y="{y0}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}"></rect>')
    # the corridor as a schematic: the register's road lines that are built
    # or being built in solid green, the rest dashed
    built, planned = [], []
    for p in reg["projects"]:
        g = p["geometry"]
        if g["type"] == "line" and seg(p) in ("road", "rail", "pipeline"):
            line = [(w[1], w[2]) for w in g["waypoints"]]
            (built if p["status"] in ("operating", "under_construction") and seg(p) == "road" else planned).append(line)
    out.append(f'<path class="lplan" d="{d_of(planned, eps=0.2)}"></path>')
    out.append(f'<path class="lrail" d="{d_of(built, eps=0.2)}"></path>')
    for name, lon, lat, dx, dy, anchor in (("Lamu", 40.92, -2.26, 6, 4, "start"),
                                           ("Juba", 31.58, 4.85, -6, 4, "end"),
                                           ("Addis Ababa", 38.75, 9.02, 6, -3, "start")):
        x, y = lxy(lon, lat)
        out.append(f'<circle class="ldot" cx="{x}" cy="{y}" r="2.6"></circle>'
                   f'<text class="llbl" x="{x + dx}" y="{y + dy}" text-anchor="{anchor}">{name}</text>')
    for name, lon, lat in (("KENYA", 37.6, -4.3), ("ETHIOPIA", 41.0, 11.6), ("SOUTH SUDAN", 29.0, 8.4)):
        x, y = lxy(lon, lat)
        out.append(f'<text class="lctry" x="{x}" y="{y}" text-anchor="middle">{name}</text>')
    x, y = lxy(46.5, -8.0)
    out.append(f'<text class="lsea" x="{x}" y="{y}" text-anchor="middle">Indian Ocean</text>')
    out.append("</svg>")
    return "".join(out)


# -------------------------------------------------- roads and railways (OSM)

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
BBOX = f"({LAT0 - 0.4},{LON0 - 0.4},{LAT1 + 0.6},{LON1 + 0.4})"
OSM_QUERY = ('[out:json][timeout:180];('
             f'way["highway"~"^(trunk|construction)$"]{BBOX};'
             f'way["railway"="rail"]{BBOX};'
             ');out tags geom;')

# The corridor's roads in OpenStreetMap: the Lamu–Garissa–Isiolo highway is
# A10 (and some ways under construction carry ref or name "LAPSSET"), the
# Isiolo–Moyale highway is the A2 north of Isiolo, the road to South Sudan is
# the A1 north of Lokichar, and the coast road from Garsen to Lamu is the A7.
OSM_CLASSES = ["ctx", "rail", "a7", "a10", "a2", "a1", "et"]


def osm_class(tags, lon, lat):
    if tags.get("railway"):
        return None if tags.get("service") else "rail"
    ref = (tags.get("ref") or "").replace(" ", "").upper()
    nm = (tags.get("name") or "") + " " + ref
    if re.search(r"lap+s+et", nm, re.I) or ref == "A10":
        return "a10"
    if ref == "A2" and lat > 0.36 and lon > 37.5:
        return "a2"
    if ref == "A1" and lat > 2.3:
        return "a1"
    if ref == "A7" and lon > 39.95 and lat > -2.6:
        return "a7"
    if lon > 37.5 and lat > 3.45 and re.search(r"addis ababa to nairobi", nm, re.I):
        return "et"
    return "ctx" if tags.get("highway") == "trunk" else None


def fetch_osm():
    body = urllib.parse.urlencode({"data": OSM_QUERY}).encode()
    last = None
    for ep in OVERPASS:
        try:
            req = urllib.request.Request(ep, data=body, headers={"User-Agent": "africa-project-atlas/0.1 (dataset build)"})
            with urllib.request.urlopen(req, timeout=240) as r:
                elements = json.loads(r.read())["elements"]
            break
        except Exception as e:     # try the next mirror
            last = e
            print(f"  {ep}: {e}", flush=True)
    else:
        sys.exit(f"Overpass failed on every mirror: {last}")
    lines = {k: [] for k in OSM_CLASSES}
    for e in elements:
        if not e.get("geometry"):
            continue
        g = [(p["lon"], p["lat"]) for p in e["geometry"]]
        lon, lat = sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g)
        k = osm_class(e.get("tags", {}), lon, lat)
        if k is None:
            continue
        # context roads only matter at map scale; the corridor's own keep more detail
        g = simplify(g, 0.01 if k in ("ctx", "rail") else 0.003)
        lines[k].append([[round(a, 3), round(b, 3)] for a, b in g])
    pack = {"source": "OpenStreetMap contributors, ODbL 1.0", "url": "https://www.openstreetmap.org/copyright",
            "fetched": today(), "query": OSM_QUERY, "lines": lines}
    OSM.write_text(json.dumps(pack, separators=(",", ":")))
    print(f"→ {OSM.relative_to(ROOT)}  " + ", ".join(f"{k} {len(v)} ways" for k, v in lines.items()))


# GEM's two LAPSSET pipeline segments. Their published routes are swapped
# between the records in GEM's own file (the Lokichar–Lamu record carries the
# line from Lokichar to Juba), so each is picked by where it starts, not by name.
def gem_pipelines():
    path = DATA / "gem_oil_gas_pipelines.geojson"
    out = {}
    if not path.exists():
        return out
    for ft in json.loads(path.read_text())["features"]:
        q = ft["properties"]
        if "LAPSSET" not in (q.get("pipeline") or ""):
            continue
        for part in ft["geometry"]["coordinates"]:
            ends = (part[0], part[-1])
            key = "lamu" if any(x > 40.5 for x, _ in ends) else "juba" if any(x < 32.5 for x, _ in ends) else None
            if key:
                out.setdefault(key, []).append(part)
    return out


# -------------------------------------------------------------- the register

SEGMENTS = [  # map group, legend name, marker kind
    ("port", "Port and free zone", "star"), ("road", "Roads", "diamond"), ("rail", "Railway", "square"),
    ("pipeline", "Oil pipelines and energy", "hex"), ("border", "Border posts and airports", "triangle"),
    ("other", "Dam, resort cities, studies", "circle")]
SEG_NAME = {k: n for k, n, _ in SEGMENTS}
SEG_OF = {"port": "port", "sez": "port", "road": "road", "bridge": "road", "rail": "rail", "pipeline": "pipeline",
          "energy": "pipeline", "border": "border", "airport": "border", "logistics": "border"}
# planned lines without a published route are drawn through the same towns:
# the railway a few pixels to one side, the products pipeline to the other
LINE_OFFSET = {"rail": 4.5, "pipeline": -4.5, "energy": 6.0}

# Funder groups wear the debt page's creditor colours (the --dg-* slots,
# validated for colour-blind separation in both themes), as --lf-* here.
FGROUPS = [("gov", "Corridor governments"), ("multi", "Development banks"), ("china", "China"),
           ("europe", "Europe"), ("us", "United States"), ("private", "Companies and commercial lenders"),
           ("other", "Others")]
FG_NAME = dict(FGROUPS)
FG_OF = {"KE": "gov", "ET": "gov", "SS": "gov", "US": "us", "CN": "china", "private": "private",
         "AfDB": "multi", "WB": "multi", "IFC": "multi", "multilateral": "multi", "Afreximbank": "multi",
         "AFC": "multi", "TDB": "multi", "MIGA": "multi", "BADEA": "multi", "OPEC Fund": "multi",
         "EU": "europe", "EIB": "europe", "UK": "europe", "GB": "europe", "DE": "europe", "FR": "europe",
         "IT": "europe", "NL": "europe", "SE": "europe", "DK": "europe", "NO": "europe", "FI": "europe"}

CC = {"KE": "Kenya", "ET": "Ethiopia", "SS": "South Sudan"}


def load():
    if not SRC.exists():
        sys.exit("missing data/lapsset.json — the register is kept by hand")
    if not OSM.exists():
        sys.exit("missing data/lapsset_osm.json — run `python3 build_lapsset.py --osm`")
    reg = json.loads(SRC.read_text())
    FX.update({cur: t for cur, t in reg.get("fx", {}).get("rates", {}).items()})
    return reg, json.loads(OSM.read_text())


# Kenya pays for much of the corridor in shillings, so unlike the Lobito page
# (which leaves kwanza as stated) shillings and birr are converted, at the
# World Bank's annual average official rate for the line's year (the
# register's "fx" block, with its source); a year past the table takes its
# last rate.
FX = {}


def fx_rate(cur, year):
    table_ = FX.get(cur)
    if not table_:
        return None
    years = sorted(int(y) for y in table_)
    y = min(max(int(year or years[-1]), years[0]), years[-1])
    return table_[str(y)]


def usd(f):
    """A financing line's amount in USD: euros at the shared reference rate,
    shillings and birr at their year's average; None for no amount or a
    currency without a rate."""
    a, cur = f.get("amount"), f.get("currency") or "USD"
    if a is None:
        return None
    if cur == "USD":
        return a
    if f.get("usd_per_unit"):        # the AfDB's unit of account, at the bank's own stated rate
        return a * f["usd_per_unit"]
    if cur == "EUR":
        return a * EUR_USD
    r = fx_rate(cur, f.get("year"))
    return a / r if r else None


def counted(f):
    """What a line adds to the sums: a guarantee lends nothing, a line marked
    "in_total": false is part of another one (its note says which), and a
    loan "cancelled" before it paid out is listed but not counted."""
    if f.get("instrument") == "guarantee" or f.get("in_total") is False or f.get("cancelled"):
        return None
    return usd(f)


def fgroup(f):
    return FG_OF.get(f.get("funder_country"), "other")

def fmt_when(d):
    """A register date as the page shows it: the research gives some only to
    the month or the year (2016-07, 1972), which fmt_date would pass through
    raw."""
    d = str(d or "")
    if re.fullmatch(r"\d{4}", d):
        return d
    m = re.fullmatch(r"(\d{4})-(\d{2})", d)
    if m:
        return f'{["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m[2]) - 1]} {m[1]}'
    return fmt_date(d)


def seg(p):
    return SEG_OF.get(p["segment"], "other")


# ------------------------------------------------------------ the map marks

def _bbox(wps, pad):
    xs, ys = [w[1] for w in wps], [w[2] for w in wps]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _centre(line):
    return sum(p[0] for p in line) / len(line), sum(p[1] for p in line) / len(line)


def marker_at(wps):
    """A line project's marker: halfway along it, or, for a line that leaves
    the map (the railway and road towards Addis Ababa), the point inside the
    map nearest to halfway, set 14 px in from the edge."""
    x, y = xy(*_mid(wps))
    if 14 <= x <= MAP_W - 14 and 14 <= y <= MAP_H - 14:
        return x, y
    pts = [(w[1], w[2]) for w in wps]
    samples = []
    for a, b in zip(pts, pts[1:]):
        for k in range(40):
            t = k / 40
            samples.append(xy(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    inside = [(sx, sy) for sx, sy in samples if 14 <= sx <= MAP_W - 14 and 14 <= sy <= MAP_H - 14]
    if not inside:
        return x, y
    return min(inside, key=lambda s: math.dist(s, (x, y)))


def map_payload(reg, osm, num):
    def tip(p):
        fin = p.get("finance", [])
        funders = sorted({f["funder"] for f in fin})
        lines = [f'{esc(status_name(p))} · {esc(p.get("status_note", ""))}']
        if funders:
            lines.append("Funded by " + esc(", ".join(funders)))
        return (f'<b>{num[p["id"]]}. {esc(p["name"])}</b>{esc(SEG_NAME[seg(p)])} · '
                f'{esc(", ".join(CC.get(c, c) for c in p["countries"]))}<br>' + "<br>".join(lines))

    L = osm["lines"]
    class_tips = {
        "ctx": "<b>Other trunk roads</b>Not part of LAPSSET",
        "rail": "<b>Railways in service</b>Kenya's standard-gauge line from Mombasa to Nairobi and Naivasha, the "
                "metre-gauge network and Uganda's lines. LAPSSET's own railway is not built",
        "a10": "<b>Lamu–Garissa–Isiolo highway (A10)</b>LAPSSET's road from the port inland; the stretches the "
               "register covers are coloured by their status",
        "a2": "<b>Isiolo–Moyale highway (A2)</b>The road to the Ethiopian border",
        "a1": "<b>Lokichar–Lodwar–Lokichoggio road (A1)</b>The road to the South Sudan border at Nadapal",
        "a7": "<b>Garsen–Witu–Lamu road (A7)</b>The coast road into Lamu",
        "et": "<b>Moyale–Hawassa road, Ethiopia</b>Ethiopia's leg towards Addis Ababa",
    }
    groups = [{"id": "g-osm-ctx", "kind": "line", "cls": "road ctx", "items": [{"d": path_d(L["ctx"], eps=1.5),
                                                                              "tip": class_tips["ctx"]}]},
              {"id": "g-osm-rail", "kind": "line", "cls": "rail ctx", "items": [{"d": path_d(L["rail"], eps=1.2),
                                                                               "tip": class_tips["rail"]}]}]
    # a register project with "osm": <class> is drawn on that class's real
    # ways inside the box of its waypoints, in its status's colour; the ways
    # no project claims are drawn plain, with the class's tooltip
    claimed, spine = set(), []
    for p in reg["projects"]:
        k, g = p.get("osm"), p["geometry"]
        if not k or g["type"] != "line":
            continue
        x0, y0, x1, y1 = _bbox(g["waypoints"], p.get("osm_pad", 0.15))
        ways = [i for i, ln in enumerate(L.get(k, [])) if (k, i) not in claimed
                and x0 <= _centre(ln)[0] <= x1 and y0 <= _centre(ln)[1] <= y1]
        claimed.update((k, i) for i in ways)
        if ways:
            spine.append({"d": path_d([L[k][i] for i in ways], eps=0.5), "cls": p["status"], "tip": tip(p)})
    for k in ("a7", "a10", "a2", "a1", "et"):
        rest = [ln for i, ln in enumerate(L.get(k, [])) if (k, i) not in claimed]
        if rest:
            groups.append({"id": f"g-osm-{k}", "kind": "line", "cls": "road spine",
                           "items": [{"d": path_d(rest, eps=0.5), "tip": class_tips[k]}]})
    groups.append({"id": "g-spine", "kind": "line", "cls": "road built", "items": spine})
    # line projects without an OSM road (planned roads, the railway, the
    # pipelines), then a wide transparent copy of each on top so the thin
    # line is easy to point at
    gem = gem_pipelines()
    lines, hits = [], []
    for p in reg["projects"]:
        g = p["geometry"]
        if g["type"] != "line" or p.get("osm"):
            continue
        if p.get("gem") and gem.get(p["gem"]):
            d = path_d(gem[p["gem"]], eps=0.4)
        else:
            d = path_d([[(w[1], w[2]) for w in g["waypoints"]]], eps=0.3, off=LINE_OFFSET.get(p["segment"], 0))
        # the raw segment too, so a power line (grouped with the pipelines) can be styled apart
        lines.append({"d": d, "cls": f'{seg(p)} {p["segment"]} {p["status"]}', "tip": tip(p)})
        hits.append({"d": d, "tip": tip(p)})
    for p in reg["projects"]:
        if p.get("osm") and p["geometry"]["type"] == "line":
            hits.append({"d": path_d([[(w[1], w[2]) for w in p["geometry"]["waypoints"]]], eps=0.3), "tip": tip(p)})
    groups.append({"id": "g-lines", "kind": "line", "cls": "proj", "items": lines})
    groups.append({"id": "g-hits", "kind": "line", "cls": "hitline", "items": hits})
    # one marker per mapped project: at its point, or halfway along its line;
    # an "area" project (a programme over several counties) has none
    at = {}
    for p in reg["projects"]:
        g = p["geometry"]
        if g["type"] == "point":
            at[p["id"]] = xy(g["lon"], g["lat"])
        elif g["type"] == "line":
            at[p["id"]] = marker_at(g["waypoints"])
    # markers closer than 22 px (several projects at Lamu, at Isiolo) are set
    # out in a row above the place, 30 px apart, each with a leader line down
    # to it, so every number can be read
    placed, leads, done = dict(at), [], set()
    for pid, (x, y) in sorted(at.items(), key=lambda t: num[t[0]]):
        if pid in done:
            continue
        near = [q for q in at if q not in done and math.dist(at[q], (x, y)) < 22]
        done.update(near)
        if len(near) < 2:
            continue
        cx = sum(at[q][0] for q in near) / len(near)
        cy = sum(at[q][1] for q in near) / len(near)
        near.sort(key=lambda q: num[q])
        x0 = min(max(cx - 15 * (len(near) - 1), 10), MAP_W - 10 - 30 * (len(near) - 1))
        for i, q in enumerate(near):
            mx, my = x0 + 30 * i, cy - 26
            placed[q] = (round(mx, 1), round(my, 1))
            leads.append(f"M{mx:.1f} {my + 5:.1f} L{cx:.1f} {cy:.1f}")
    if leads:
        groups.append({"id": "g-leads", "kind": "line", "cls": "leader",
                       "items": [{"d": " ".join(leads), "tip": "Several projects at one place: each marker is "
                                  "drawn above it, with a line to where it is"}]})
    kinds = {k: kind for k, _, kind in SEGMENTS}
    for k, _, _ in SEGMENTS:
        items = []
        for p in reg["projects"]:
            if seg(p) != k or p["id"] not in placed:
                continue
            x, y = placed[p["id"]]
            items.append({"x": x, "y": y, "cls": p["status"], "tip": tip(p), "label": str(num[p["id"]])})
        # "square" is the frame's fallback kind, a 10 px rect
        groups.append({"id": f"g-{k}", "kind": kinds[k], "cls": "asset", "items": items})
    return {"groups": groups}


# ------------------------------------------------------------- the charts

def funder_rows(reg):
    """Every financing line of every project, summed by funder and firmness."""
    agg = {}
    for p in reg["projects"]:
        for f in p.get("finance", []):
            v = counted(f)
            if v is None:
                continue
            a = agg.setdefault(f["funder"], {"g": fgroup(f), "by": {k: 0.0 for k, _ in FIRM}, "deals": []})
            a["by"][FIRM_OF.get(f["firmness"], "pledged")] += v
            a["deals"].append((p, f, v))
    return sorted(agg.items(), key=lambda t: -sum(t[1]["by"].values()))


def funders_svg(rows):
    """One bar per funder, its segments by firmness (dark = signed, light =
    pledged), drawn at build time; each segment carries its tooltip."""
    W, L, R, T, rowh, bh = 1060, 250, 92, 22, 30, 16
    H = T + rowh * len(rows) + 8
    top_v = max(sum(a["by"].values()) for _, a in rows)
    step = nice_step(top_v / 4)
    top = step * math.ceil(top_v / step)
    xv = lambda v: L + v / top * (W - L - R)
    out = [f'<svg id="c-funders" viewBox="0 0 {W} {H}" role="img" aria-label="Bar chart of the money each '
           f'funder has put into LAPSSET Corridor projects, split into signed, approved and pledged">']
    v = 0
    while v <= top + 1e-6:
        lab = f"{v / 1e9:,.1f}{' bn' if v == top else ''}" if top >= 1e9 else f"{v / 1e6:,.0f}{' m' if v == top else ''}"
        out.append(f'<line class="gl" x1="{xv(v):.1f}" x2="{xv(v):.1f}" y1="{T - 6}" y2="{H - 6}"></line>'
                   f'<text class="ax" x="{xv(v):.1f}" y="{T - 10}" text-anchor="middle">'
                   f'{lab}</text>'.replace(">0.0<", ">0<"))
        v += step
    for i, (name, a) in enumerate(rows):
        y = T + rowh * i + (rowh - bh) / 2
        total = sum(a["by"].values())
        out.append(f'<rect x="{L - 228}" y="{y + bh / 2 - 4.5:.1f}" width="9" height="9" rx="2" '
                   f'style="fill:var(--lf-{a["g"]})"></rect>'
                   f'<text class="blab" x="{L - 214}" y="{y + bh / 2 + 4:.1f}">{esc(_short(name))}</text>')
        x = L
        segs = [(k, a["by"][k]) for k, _ in FIRM if a["by"][k] > 0]
        for j, (k, val) in enumerate(segs):
            w = max(xv(val) - L - (2 if j < len(segs) - 1 else 0), 1.5)
            deals = [d for d in a["deals"] if FIRM_OF.get(d[1]["firmness"]) == k]
            tip = (f"<b>{esc(name)}</b>{esc(dict(FIRM)[k])}: {money(val)}<br>" + "<br>".join(
                f'{esc(d[0]["short"])}: {esc(native(d[1]))}' for d in sorted(deals, key=lambda d: -d[2])))
            last = j == len(segs) - 1
            r = 4 if last else 0
            out.append(f'<path class="fseg f-{k}" data-tip="{esc(tip)}" d="{_bar(x, y, w, bh, r)}"></path>')
            x += w + 2
        out.append(f'<text class="bval" x="{x + 4:.1f}" y="{y + bh / 2 + 4:.1f}">{money(total, short=True)}</text>')
    out.append("</svg>")
    return "".join(out)


# the funder chart's row labels; tooltips and tables keep the full names
FUNDER_SHORT = {
    "African Development Bank Group": "African Development Bank",
    "Export-Import Bank of China (China Eximbank)": "China Eximbank",
    "Industrial and Commercial Bank of China (ICBC)": "ICBC",
    "International Development Association (World Bank)": "World Bank (IDA)",
    "Japan International Cooperation Agency (JICA)": "JICA",
    "Kenya Ports Authority (KPA)": "Kenya Ports Authority",
    "Kenya Airports Authority (Government of Kenya)": "Kenya Airports Authority",
    "Government of the United Kingdom (via TradeMark East Africa)": "United Kingdom (TradeMark East Africa)",
    "Kenya National Highways Authority (KeNHA)": "KeNHA (Kenya)",
    "LAPSSET Corridor Development Authority (LCDA)": "LCDA (Kenya)",
}


def _short(name, n=34):
    name = FUNDER_SHORT.get(name, name)
    return name if len(name) <= n else name[:n - 1].rstrip() + "…"


def funding_cell(fin):
    """The status board's "Funded by" cell: one row per funder with its money
    and share, and, where two or more funders have put in an amount, a donut
    of those shares. Slices wear the funder group's colour; a pledge is pale.
    Lines without an amount, guarantees and lines inside another one are
    listed but not drawn, so the donut adds up only what the sums add up."""
    if not fin:
        return '<span class="dim">no financing found</span>'
    slices, rest = {}, []
    for f in fin:
        v = counted(f)
        firm = FIRM_OF.get(f["firmness"], "pledged")
        if v:
            k = (f["funder"], firm == "pledged")
            sl = slices.setdefault(k, {"name": f["funder"], "g": fgroup(f), "pledged": firm == "pledged", "v": 0.0})
            sl["v"] += v
        else:
            why = ("guarantee" if f.get("instrument") == "guarantee" else "cancelled" if f.get("cancelled")
                   else "inside another line" if f.get("in_total") is False
                   else f"in {f.get('currency')}" if usd(f) is None and f.get("amount") else "not disclosed")
            rest.append((f["funder"], fgroup(f), why))
    order = sorted(slices.values(), key=lambda sl: -sl["v"])
    total = sum(sl["v"] for sl in order)
    rows = []
    for sl in order:
        share = sl["v"] / total * 100 if total else 0
        rows.append(f'<span class="fr{" pl" if sl["pledged"] else ""}">{fdot(sl["g"])}'
                    f'<span class="fn">{esc(FUNDER_SHORT.get(sl["name"], sl["name"]))}{"<em> pledged</em>" if sl["pledged"] else ""}</span>'
                    f'<span class="fv">{money(sl["v"], short=True)}</span>'
                    f'<span class="fp">{"" if len(order) < 2 else ("<1" if share < 1 else f"{share:.0f}") + "%"}</span></span>')
    seen = set()
    for name, g, why in rest:
        if (name, why) in seen or any(sl["name"] == name for sl in order) and why == "not disclosed":
            continue
        seen.add((name, why))
        rows.append(f'<span class="fr nd">{fdot(g)}<span class="fn">{esc(FUNDER_SHORT.get(name, name))}</span>'
                    f'<span class="fv">{esc(why)}</span><span class="fp"></span></span>')
    chart = donut(order, total) if len(order) >= 2 else ""
    return f'<div class="fund">{chart}<div class="flist">{"".join(rows)}</div></div>'


def matrix_html(reg, num):
    """Who funds what: one row per financed project, one column per funder
    group, a disc in each cell sized by the money (area ∝ USD, one scale)."""
    fin = [p for p in reg["projects"] if p.get("finance")]
    cell = {}
    for p in fin:
        for f in p["finance"]:
            c = cell.setdefault((p["id"], fgroup(f)), {"v": 0.0, "firm": set(), "firm_any": set(), "lines": []})
            v = counted(f)
            c["v"] += v or 0
            # how firm the cell's money is: judged on the lines that carry an amount
            (c["firm"] if v else c["firm_any"]).add(FIRM_OF.get(f["firmness"], "pledged"))
            c["lines"].append(f'{f["funder"]}: {native(f)} ({f["firmness"]})')
    used = [g for g, _ in FGROUPS if any(k[1] == g for k in cell)]
    vmax = max(c["v"] for c in cell.values()) or 1
    head = "".join(f'<th class="mx-h"><span>{fdot(g)}{esc(FG_NAME[g])}</span></th>' for g in used)
    rows = []
    for p in sorted(fin, key=lambda p: num[p["id"]]):
        tds = []
        for g in used:
            c = cell.get((p["id"], g))
            if not c:
                tds.append('<td class="mx"></td>')
                continue
            r = 4 + 13 * math.sqrt(c["v"] / vmax) if c["v"] else 4
            hollow = (c["firm"] or c["firm_any"]) == {"pledged"}
            t = esc(" · ".join(c["lines"]))
            tds.append(f'<td class="mx" title="{t}"><svg viewBox="0 0 36 36" width="36" height="36" aria-hidden="true">'
                       f'<circle cx="18" cy="18" r="{r:.1f}" class="{"hol" if hollow else "sol"}" '
                       f'style="--c:var(--lf-{g})"></circle></svg>'
                       f'<span class="mxv">{"–" if not c["v"] else money(c["v"], short=True)}</span></td>')
        rows.append(f'<tr><td class="name"><span class="pn">{num[p["id"]]}</span>{esc(p["short"])}</td>{"".join(tds)}</tr>')
    return (f'<div class="tbl mxwrap"><table class="matrix"><caption>Who funds what. One row per project with '
            f'money attached, one column per kind of funder. A disc\'s area is the money, in US dollars, on one '
            f'scale; an open ring means only pledges. Hover a cell for the deals.</caption>'
            f'<thead><tr><th>Project</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


# -------------------------------------------------------------- the page

def build_page(reg, osm):
    P = reg["projects"]
    order = {k: i for i, (k, _, _) in enumerate(SEGMENTS)}

    def coast_inland(p):
        """From Lamu inland: by distance from the port, so the board reads
        along the corridor rather than west to east."""
        g = p["geometry"]       # an area carries a lon/lat too, for this order only
        lon, lat = _mid(g["waypoints"]) if g["type"] == "line" else (g["lon"], g["lat"])
        return math.dist((lon, lat), (40.86, -2.19))   # the port
    P.sort(key=lambda p: (order[seg(p)], coast_inland(p)))
    num = {p["id"]: i + 1 for i, p in enumerate(P)}

    # ---- the status board
    rows = []
    for k, name, _ in SEGMENTS:
        group = [p for p in P if seg(p) == k]
        if not group:
            continue
        rows.append([f'<td colspan="5" class="grp">{esc(name)}</td>'])
        for p in group:
            fin = p.get("finance", [])
            who = funding_cell(fin)
            srcs = " · ".join(src_link(s["url"], s.get("publisher") or None) for s in p.get("sources", [])[:3])
            rows.append([
                td(f'<span class="pn">{num[p["id"]]}</span>', "nc"),
                td(f'<b>{esc(p["name"])}</b><span class="dim pc">{esc(" · ".join(CC.get(c, c) for c in p["countries"]))}'
                   f'{(" · " + esc(p["developer"])) if p.get("developer") else ""}</span>'
                   f'<span class="sum">{esc(p.get("summary", ""))}</span>'
                   + (f'<span class="area">Not on the map: {esc(p["geometry"].get("place", ""))}</span>'
                      if p["geometry"]["type"] == "area" else ""), "pname"),
                td(f'{stage_strip(p["status"])}{st(p["status"], status_name(p))}'),
                td(f'{esc(p.get("status_note", ""))} <span class="dim m">{esc(p.get("status_date", ""))}</span>'
                   f'<span class="srcs">{srcs}</span>', "latest"),
                td(who, "who"),
            ])
    board = table(
        f"The {len(P)} projects of the register, by kind and from Lamu inland. The number is the marker's on "
        f"the map. The bar shows how far each has got: announced, approved, being built, in service. Funders "
        f"are coloured by kind.",
        ["No.", "Project", "Stage", "Latest", "Funded by"], rows, cls="board")
    board = board.replace("<tr><td colspan", '<tr class="grow"><td colspan')

    # ---- money
    frows = funder_rows(reg)
    firm_tot = {k: sum(a["by"][k] for _, a in frows) for k, _ in FIRM}
    deals = [(p, f) for p in P for f in p.get("finance", [])]
    undisclosed = [(p, f) for p, f in deals if f.get("amount") is None]
    drows = []
    for p, f in sorted(deals, key=lambda t: (num[t[0]["id"]], -(usd(t[1]) or 0))):
        drows.append([
            td(f'<span class="pn">{num[p["id"]]}</span>{esc(p["short"])}', "name"),
            td(f'{fdot(fgroup(f))}{esc(f["funder"])}'),
            td(esc(f.get("instrument", ""))),
            td(esc(native(f)), "num"),
            td((money(usd(f)) if f.get("currency", "USD") != "USD" and usd(f) else "")
               + (f'<span class="nis">at UA 1 = USD {f["usd_per_unit"]:.4g}, the AfDB\'s rate</span>'
                  if f.get("usd_per_unit") and f.get("amount") else
                  f'<span class="nis">at {esc(f["currency"])} {fx_rate(f["currency"], f.get("year")):,.0f} = USD 1</span>'
                  if f.get("currency") not in ("USD", "EUR", None) and usd(f) else "")
               + (f'<span class="nis">{"cancelled, " if f.get("cancelled") else ""}not in the sums</span>'
                  if (usd(f) or f.get("amount")) and counted(f) is None else ""), "num dim"),
            td(f'<span class="firm f-{FIRM_OF.get(f["firmness"], "pledged")}"><i></i>{esc(f["firmness"])}</span>'),
            td(esc(str(f["year"])) if f.get("year") else '<span class="dim">–</span>'),
            td(f'{esc(f.get("note", ""))} {src_link(f["source"])}', "dnote"),
        ])
    t_deals = table(
        f"Every financing line in the register, {len(deals)} of them. Amounts as the source states them, with "
        f"euros converted at {esc(EUR_NOTE)} and Kenyan shillings at the World Bank's average rate for the "
        f"line's year. Firmness: pledged (an announcement or memorandum), approved (a board decision), signed "
        f"(an agreement or a budget allocation), disbursing (money flowing). Guarantees, and lines that are "
        f"part of another, are listed but left out of the sums.",
        ["Project", "Funder", "Instrument", "#Amount", "#In USD", "Firmness", "Year", "Note and source"],
        drows, cls="deals")

    # ---- the corridor-wide figures
    prow = []
    for pl in sorted(reg.get("pledges", []), key=lambda x: x.get("date", "")):
        prow.append([td(f'{fdot(FG_OF.get(pl.get("funder_country"), "other"))}<b>{esc(pl["funder"])}</b>', "name"),
                     td(esc(pl["what"]) + (f'<span class="dim pc">{esc(pl["note"])}</span>' if pl.get("note") else "")),
                     td(esc(native(pl)), "num"), td(esc(pl.get("firmness", ""))),
                     td(f'{esc(fmt_when(pl.get("date", "")))} {src_link(pl["source"])}', "dnote")])
    t_pledges = table(
        "The corridor-wide figures, as their makers stated them: cost estimates, investment pledges and "
        "memoranda. They overlap one another and the project lines above, and are not added up anywhere on "
        "this page.",
        ["Who", "What was stated", "#Amount", "Kind", "When and source"], prow, cls="pledges")

    # ---- what was looked at and left out
    ex = reg.get("excluded", [])
    erow = [[td(esc(e["name"]), "name"), td(esc(e["why"])), td(src_link(e["source"]), "dnote")] for e in ex]
    t_excluded = table(
        "Projects near the corridor, or often mentioned with it, that the register leaves out, and why.",
        ["Project", "Why it is not in the register", "Source"], erow, cls="pledges")

    # ---- timeline and governance
    tl = "".join(f'<li><span class="m">{esc(fmt_when(e["date"]))}</span><span>{esc(e["event"])} '
                 f'{src_link(e["source"])}</span></li>' for e in sorted(reg.get("timeline", []), key=lambda e: e["date"]))
    gov = "".join(f'<dt>{esc(g["name"])}</dt><dd>{esc(g["what"])} <span class="dim">Since {esc(g.get("since", ""))}.</span> '
                  f'{src_link(g["source"])}</dd>' for g in reg.get("governance", []))

    # ---- the figures the prose quotes
    by_status = {k: sum(1 for p in P if p["status"] == k) for k in STATUS}
    n_src = len({s["url"] for p in P for s in p.get("sources", [])} | {f["source"] for _, f in deals}
                | {pl["source"] for pl in reg.get("pledges", [])} | {e["source"] for e in reg.get("timeline", [])})
    funders = {f["funder"] for _, f in deals}
    tokens = {
        "__COMPILED__": fmt_date(reg["compiled"]), "__N_PROJECTS__": str(len(P)),
        "__N_BUILDING__": str(by_status["under_construction"]), "__N_OPERATING__": str(by_status["operating"]),
        "__N_APPROVED__": str(by_status["approved"]), "__N_ANNOUNCED__": str(by_status["announced"]),
        "__N_STALLED__": str(by_status["stalled"]),
        "__N_DEALS__": str(len(deals)), "__N_UNDISCLOSED__": str(len(undisclosed)), "__N_FUNDERS__": str(len(funders)),
        "__N_SOURCES__": str(n_src),
        "__SIGNED__": money(firm_tot["signed"]), "__APPROVED__": money(firm_tot["approved"]),
        "__PLEDGED__": money(firm_tot["pledged"]),
        "__OSM_FETCHED__": fmt_date(osm["fetched"]), "__EUR_NOTE__": esc(EUR_NOTE),
        "__FX_URL__": esc(reg["fx"]["url"]), "__FX_NOTE__": esc(reg["fx"]["note"]),
        "__MAP_W__": f"{MAP_W:.0f}", "__MAP_H__": f"{MAP_H:.0f}", "__BASEMAP__": basemap(),
        "__LOCATOR__": locator(reg, osm),
        "__SEG_LEGEND__": "".join(
            f'<label><input type="checkbox" checked data-g="g-{k}"><span class="sw seg-{k}"></span>{esc(n)}</label>'
            for k, n, _ in SEGMENTS if any(seg(p) == k and p["geometry"]["type"] != "area" for p in P)),
        "__STATUS_KEY__": "".join(f'<span class="dk"><i class="sk {k}"></i>{esc(n)}</span>' for k, n in STATUS.items()),
        "__FUNDER_KEY__": "".join(f'<span class="dk">{fdot(g)}{esc(n)}</span>' for g, n in FGROUPS
                                  if any(a["g"] == g for _, a in frows)),
        "__FIRM_KEY__": "".join(f'<span class="dk"><i class="fz f-{k}"></i>{esc(n)}</span>' for k, n in FIRM),
        "__STATUS_BOARD__": board, "__TABLE_EXCLUDED__": t_excluded, "__N_EXCLUDED__": str(len(ex)),
        "__CHART_FUNDERS__": funders_svg(frows) if frows else "", "__MATRIX__": matrix_html(reg, num),
        "__TABLE_DEALS__": t_deals, "__TABLE_PLEDGES__": t_pledges, "__TIMELINE__": tl, "__GOVERNANCE__": gov,
        "__SITE_RECORDS__": site_records(reg),
    }
    for k, v in reg.get("prose", {}).items():     # figures the lede states, kept in the register
        tokens[f"__{k.upper()}__"] = esc(v)
    payload = {"map": map_payload(reg, osm, num), "charts": {}}
    return tokens, payload


# ----------------------------------------------- what the site already holds

SITE_LAYERS = [  # file, layer name, id field, link field
    ("iati_afdb_finance.geojson", "AfDB", "iati_id", "project_url"),
    ("iati_worldbank_finance.geojson", "World Bank", "iati_id", "project_url"),
    ("iati_eu_finance.geojson", "EU finance", "iati_id", "project_url"),
    ("aiddata_china_finance.geojson", "China (AidData)", "aiddata_id", "url"),
    ("osm_construction.geojson", "OpenStreetMap", "osm_id", None),
    ("gem_power_assets.geojson", "Power plants (GEM)", "project_id", "url"),
    ("gem_oil_gas_pipelines.geojson", "Pipelines (GEM)", "project_id", "url"),
]
# "Lamu" alone is a county and a town (its water, schools and courts are not
# the corridor's); LAPSSET, the port and the corridor's named works are
CORRIDOR_WORDS = re.compile(r"lap+s+et|lamu port|port of lamu|lamu[- ]garissa|lokichar[–-]lamu|isiolo[–-]moyale|"
                            r"merille[–-]marsabit|marsabit[–-]turbi|turbi[–-]moyale|isiolo international airport", re.I)


def site_records(reg):
    """The records of the site's own layers that name the corridor, or that a
    project of the register points at (its site_refs), as a table."""
    refs = {(r["layer"], str(r["id"])) for p in reg["projects"] for r in p.get("site_refs", [])}
    rows, seen = [], set()
    for fname, layer, idf, linkf in SITE_LAYERS:
        path = DATA / fname
        if not path.exists():
            continue
        for ft in json.loads(path.read_text())["features"]:
            q = ft["properties"]
            rid = str(q.get(idf, ""))
            text = " ".join(str(q.get(k) or "") for k in ("name", "description", "parent_name"))
            if not ((layer, rid) in refs or CORRIDOR_WORDS.search(text)):
                continue
            key = (layer, q.get("name"))
            if key in seen:
                continue
            seen.add(key)
            amt = q.get("commitment") or q.get("amount_usd_2021") or (q.get("amount_eur") and q["amount_eur"] * EUR_USD)
            link = q.get(linkf) if linkf else (f"https://www.openstreetmap.org/{rid}" if rid else None)
            # the EU's IATI export carries a few mis-encoded dashes and apostrophes
            label = re.sub(r"\s¿\s", " – ", re.sub(r"¿s\b", "’s", q.get("name") or ""))
            name = esc(label)
            ctry = q.get("country") or ", ".join(q.get("countries") or [])
            rows.append((layer, [td(esc(layer)), td(src_link(link, label) if link else name, "name"),
                                 td(esc(ctry)), td(st(q.get("dash_status", ""))),
                                 td(money(amt) if amt else "–", "num")]))
    rows.sort(key=lambda r: r[0])
    return table(
        f"{len(rows)} records in the site's own datasets that name the corridor or one of its works. They are "
        f"on the main map too, with each source's own status.",
        ["Dataset", "Record", "Country", "Status in the dataset", "#Amount"], [r for _, r in rows], cls="site")


def jsonld(path):
    page = {"@context": "https://schema.org", "@type": "WebPage", "@id": site_url(path), "url": site_url(path),
            "name": TITLE, "description": DESCRIPTION, "inLanguage": "en",
            "isPartOf": {"@type": "WebSite", "@id": site_url("#website"), "name": SITE_NAME, "url": SITE_URL},
            "author": {"@type": "Person", "name": AUTHOR_NAME, "url": WEB_URL, "sameAs": [AUTHOR_URL]},
            "about": {"@type": "Place", "name": "LAPSSET Corridor"}}
    return ('<script type="application/ld+json">'
            + json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n")


NOINDEX = ('<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">',
           '<meta name="robots" content="noindex,nofollow">')


def build():
    reg, osm = load()
    tokens, payload = build_page(reg, osm)
    tokens.update({"__TITLE__": esc(TITLE), "__DATA_URL__": site_url("data/lapsset.json"),
                   "__DATA_FILE__": "lapsset.json", "__BUILT__": fmt_date(today())})
    page = FRAME.read_text().replace("<!--__BODY__-->", FRAG.read_text(), 1)
    for k, v in tokens.items():
        page = page.replace(k, v)
    page = page.replace("/*__PAYLOAD__*/", json.dumps(payload, ensure_ascii=False, separators=(",", ":")), 1)
    # "lapsset" is in no menu, so the Deep dives menu marks nothing current and
    # opens its entries in this tab, as on the other deep dives
    page = brand_assets(page, donor=SLUG)
    left = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]*__", page)))
    if left:
        sys.exit(f"lapsset: unfilled tokens {', '.join(left)}")
    path = f"{SLUG}/index.html"
    doc = wrap_document(page, title=TITLE, description=DESCRIPTION, path=path, kind="profile",
                        extra_head=jsonld(path))
    if NOINDEX[0] not in doc:
        sys.exit("lapsset: the robots meta changed in shared.wrap_document; update NOINDEX")
    doc = doc.replace(*NOINDEX)
    (DOCS / SLUG).mkdir(parents=True, exist_ok=True)
    (DOCS / SLUG / "index.html").write_text(doc)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC, DOCS / "data" / SRC.name)
    print(f"→ docs/{path}  {len(doc.encode()) / 1024:.0f} KB  (+ docs/data/{SRC.name})")


if __name__ == "__main__":
    if "--osm" in sys.argv[1:] or not OSM.exists():
        fetch_osm()
    build()
