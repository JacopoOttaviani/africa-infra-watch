#!/usr/bin/env python3
"""
Build the Lobito Corridor page, docs/lobito/index.html, from a hand-kept
register of the corridor's projects, data/lobito.json, and the corridor's
railways from OpenStreetMap, data/lobito_rail.json.

    python3 build_lobito.py          build the page
    python3 build_lobito.py --rail   refetch the railways from Overpass first

The page is not linked from the site yet: it is in no menu, not in the
sitemap or llms.txt, and its <meta robots> says noindex, nofollow. To
announce it, add it to DEEP_THEMES and write_site_index() in shared.py,
add this script to refresh.py's build list and drop the NOINDEX swap below.

The register is curated by hand, not fetched: every project, status and
financing line in it carries the URL it was read from. A project belongs to
the corridor when its funder or developer names the Lobito Corridor, or when
it sits on the corridor's rail and road spine (Lobito to the Copperbelt).
Each financing line has a firmness, kept apart from the project's status:
pledged (an announced intention or an MoU), approved (a board decision),
signed (an agreement or concession signed) and disbursing (money flowing).
The umbrella pledges (the United States' "over USD 4 bn mobilised", Team
Europe's "over EUR 2 bn") are listed apart and never added to the project
lines, which they overlap.

build_corridors.py (the /corridors/ page) imports simplify, clip_ring, _mid,
stage_strip, st, fdot, STATUS, STAGES, status_name, src_link, host, esc,
native, money and usd from here, and reads data/lobito.json and
data/lobito_rail.json: keep those names and signatures stable.

The page wears the lender profiles' frame (donor.template.html); the map is
an equirectangular window on the corridor, drawn here from the 1:10m
Natural Earth basemap, and the frame's script draws its marks and tooltips.
"""

import html
import json
import math
import pathlib
import re
import shutil
import sys
import urllib.parse
import urllib.request

from build_donors import FRAME, table, td
from shared import (AUTHOR_NAME, AUTHOR_URL, DATA, DOCS, EUR_NOTE, EUR_USD, SITE_NAME, SITE_URL, WEB_URL,
                    brand_assets, fmt_date, site_url, today, wrap_document)

ROOT = pathlib.Path(__file__).parent
SRC = DATA / "lobito.json"
RAIL = DATA / "lobito_rail.json"
FRAG = ROOT / "sections" / "lobito.html"
SLUG = "lobito"
TITLE = "The Lobito Corridor"
DESCRIPTION = ("The Lobito Corridor, from Angola's Atlantic port through DR Congo to Zambia's Copperbelt: "
               "every railway, road, border post, port and energy project financed under its name, where "
               "each one stands and who is paying for it, from development banks to the United States, "
               "the European Union, Italy and the companies building it.")


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


# ------------------------------------------------------------- projection

# An equirectangular window on the corridor, the Atlantic off Lobito to the
# Copperbelt. At 12°S a
# degree of longitude is 0.98 of a degree of latitude, so no correction.
LON0, LON1, LAT0, LAT1 = 12.2, 29.3, -14.0, -9.6
MAP_W = 1120.0
SC = MAP_W / (LON1 - LON0)
MAP_H = (LAT1 - LAT0) * SC


def xy(lon, lat):
    return round((lon - LON0) * SC, 1), round((LAT1 - lat) * SC, 1)


def simplify(pts, eps):
    """Douglas-Peucker on a list of (x, y)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy)
        best, idx = 0.0, None
        for i in range(a + 1, b):
            px_, py_ = pts[i]
            d = abs(dy * (px_ - ax) - dx * (py_ - ay)) / ln if ln else math.hypot(px_ - ax, py_ - ay)
            if d > best:
                best, idx = d, i
        if idx is not None and best > eps:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def clip_ring(pts, x0, y0, x1, y1):
    """Sutherland-Hodgman: a polygon ring clipped to a rectangle."""
    def clip(pts, inside, cut):
        out = []
        if not pts:
            return out
        prev = pts[-1]
        for cur in pts:
            if inside(cur):
                if not inside(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur))
            prev = cur
        return out
    at_x = lambda x: lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))
    at_y = lambda y: lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)
    pts = clip(pts, lambda p: p[0] >= x0, at_x(x0))
    pts = clip(pts, lambda p: p[0] <= x1, at_x(x1))
    pts = clip(pts, lambda p: p[1] >= y0, at_y(y0))
    pts = clip(pts, lambda p: p[1] <= y1, at_y(y1))
    return pts


def path_d(lines, closed=False, eps=0.6):
    """lon/lat polylines (or rings) as one SVG path in map pixels."""
    out = []
    for ln in lines:
        pts = [xy(a, b) for a, b in ln]
        if closed:
            pts = clip_ring(pts, -8, -8, MAP_W + 8, MAP_H + 8)
        pts = simplify(pts, eps)
        if len(pts) < (3 if closed else 2):
            continue
        out.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + (" Z" if closed else ""))
    return " ".join(out)


def in_window(lon, lat, pad=0.6):
    return LON0 - pad <= lon <= LON1 + pad and LAT0 - pad <= lat <= LAT1 + pad


# -------------------------------------------------------------- basemap

FOCUS = {"AO", "CD", "ZM"}
TOWNS = [  # name, dx, dy, anchor: the label's offset from the dot
    ("Lobito", -6, -6, "end"), ("Benguela", -6, 12, "end"), ("Huambo", 0, 15, "middle"),
    ("Kuito", 0, 15, "middle"), ("Luena", 0, 15, "middle"), ("Luau", 4, 15, "end"),
    ("Dilolo", 6, -6, "start"), ("Kolwezi", 0, -9, "middle"), ("Likasi", 7, -5, "start"),
    ("Lubumbashi", 7, 4, "start"), ("Solwezi", 0, 15, "middle"), ("Chingola", -7, 4, "end"),
    ("Kitwe", -7, 10, "end"), ("Ndola", 7, 10, "start"), ("Mwinilunga", 0, 15, "middle"),
]
EXTRA_TOWNS = {"Jimbe": (24.021, -11.109), "Luacano": (21.65, -11.217)}   # not in Natural Earth's places
TOWNS += [("Jimbe", 0, -8, "middle"), ("Luacano", 0, 15, "middle")]
COUNTRY_LABELS = [("ANGOLA", 17.3, -13.6), ("DR CONGO", 24.0, -9.85), ("ZAMBIA", 25.4, -13.55)]


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
    adm = [ring for a in bm["admin1"] if a["a3"] in ("AGO", "COD", "ZMB")
           for poly in a["r"] for ring in ([poly] if isinstance(poly[0][0], (int, float)) else poly)]
    out.append(f'<path class="adm" d="{path_d(adm, eps=0.8)}"></path>')
    for lk in bm["lakes"]:
        if any(in_window(x, y) for ring in lk["r"] for x, y in ring):
            out.append(f'<path class="lake" d="{path_d(lk["r"], closed=True)}"><title>{esc(lk["n"])}</title></path>')
    # the larger rivers only, and the Luapula, which is the DR Congo-Zambia border
    rivers = [r["c"] for r in bm["rivers"] if r.get("n") and (r["s"] <= 7 or r["n"] == "Luapula")
              and any(in_window(x, y, 0) for x, y in r["c"])]
    out.append(f'<path class="river" d="{path_d(rivers, eps=0.8)}"></path>')
    for name, lon, lat in COUNTRY_LABELS:
        x, y = xy(lon, lat)
        out.append(f'<text class="ctry" x="{x}" y="{y}" text-anchor="middle">{name}</text>')
    places = {p["n"]: p for p in bm["places"] if p["iso"] in FOCUS}
    places.update({n: {"x": x, "y": y} for n, (x, y) in EXTRA_TOWNS.items()})
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
# corridor countries shaded, the railway drawn, the detail map's window boxed.
LOC_LON0, LOC_LON1, LOC_LAT0, LOC_LAT1 = -18.5, 52.5, -35.5, 38.0
LOC_SC = 5.0
LOC_W, LOC_H = (LOC_LON1 - LOC_LON0) * LOC_SC, (LOC_LAT1 - LOC_LAT0) * LOC_SC


def lxy(lon, lat):
    return round((lon - LOC_LON0) * LOC_SC, 1), round((LOC_LAT1 - lat) * LOC_SC, 1)


def locator(reg, rail):
    bm = json.loads((DATA / "africa_basemap.json").read_text())

    def d_of(lines, closed=False, eps=0.4):
        out = []
        for ln in lines:
            pts = simplify([lxy(a, b) for a, b in ln], eps)
            if len(pts) >= (3 if closed else 2):
                out.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + (" Z" if closed else ""))
        return " ".join(out)
    out = [f'<svg class="loc" viewBox="0 0 {LOC_W:.0f} {LOC_H:.0f}" role="img" aria-label="Map of Africa with '
           f'Angola, DR Congo and Zambia shaded and the Lobito Corridor\'s railway drawn from Lobito, on Angola\'s '
           f'Atlantic coast, to the mines of DR Congo and Zambia">']
    # the focus countries last, so their outline sits on top of their neighbours'
    for c in sorted(bm["countries"], key=lambda c: c["iso"] in FOCUS):
        d = d_of([ring for poly in c["p"] for ring in poly], closed=True)
        out.append(f'<path class="lc{" on" if c["iso"] in FOCUS else ""}" d="{d}"><title>{esc(c["n"])}</title></path>')
    x0, y0 = lxy(LON0, LAT1)
    x1, y1 = lxy(LON1, LAT0)
    out.append(f'<rect class="lwin" x="{x0}" y="{y0}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}"></rect>')
    L = rail["lines"]
    out.append(f'<path class="lrail" d="{d_of(L["cfb"] + L["drc"], eps=0.3)}"></path>')
    for p in reg["projects"]:
        if p["segment"] == "rail" and p["geometry"]["type"] == "line":
            out.append(f'<path class="lplan" d="{d_of([[(w[1], w[2]) for w in p["geometry"]["waypoints"]]], eps=0.2)}"></path>')
    for name, lon, lat, dx, dy, anchor in (("Lobito", 13.55, -12.35, -6, 4, "end"),
                                           ("Kolwezi", 25.47, -10.72, 2, -7, "middle")):
        x, y = lxy(lon, lat)
        out.append(f'<circle class="ldot" cx="{x}" cy="{y}" r="2.6"></circle>'
                   f'<text class="llbl" x="{x + dx}" y="{y + dy}" text-anchor="{anchor}">{name}</text>')
    for name, lon, lat in (("DR CONGO", 23.4, -3.0), ("ANGOLA", 17.4, -16.4), ("ZAMBIA", 27.0, -16.0)):
        x, y = lxy(lon, lat)
        out.append(f'<text class="lctry" x="{x}" y="{y}" text-anchor="middle">{name}</text>')
    x, y = lxy(-8.0, -18.0)
    out.append(f'<text class="lsea" x="{x}" y="{y}" text-anchor="middle">Atlantic</text>')
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------- railways (OSM)

OVERPASS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter",
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
RAIL_QUERY = ('[out:json][timeout:180];way["railway"="rail"]'
              f'({LAT0 - 1.0},{LON0 - 1.4},{LAT1 + 0.2},{LON1 + 0.2});out tags geom;')


def _inside(lon, lat, rings):
    """Even-odd point in polygon over a list of rings."""
    hit = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
    return hit


def rail_class(tags, lon, lat, drc_rings):
    """Which line a railway way belongs to: the Benguela Railway (Lobito to
    Luau), the DR Congo line from Dilolo by Kolwezi and Lubumbashi to
    Sakania (the Mota-Engil concession of 2026), the rest of the DR Congo
    and Zambian network, or another Angolan line (Luanda, Moçâmedes)."""
    op = (tags.get("operator", "") + " " + tags.get("name", "")).lower()
    if "cfb" in op or "benguela" in op:
        return "cfb"
    if any(k in op for k in ("luanda", "moçâmedes", "cfm", "jamba")):
        return "ctx"
    if lon < 22.0:
        return "cfb" if -13.4 < lat < -10.5 else "ctx"
    if _inside(lon, lat, drc_rings) and not (lon > 25.8 and lat > -10.45):   # not the Tenke-Kamina branch
        return "drc"
    return "net"


def fetch_rail():
    body = urllib.parse.urlencode({"data": RAIL_QUERY}).encode()
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
    bm = json.loads((DATA / "africa_basemap_10m.json").read_text())
    drc = [ring for c in bm["countries"] if c["iso"] == "CD" for poly in c["p"] for ring in poly]
    lines = {"cfb": [], "drc": [], "net": [], "ctx": []}
    for e in elements:
        t = e.get("tags", {})
        if t.get("service") or not e.get("geometry"):
            continue
        g = [(p["lon"], p["lat"]) for p in e["geometry"]]
        lon, lat = sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g)
        g = simplify(g, 0.004)
        lines[rail_class(t, lon, lat, drc)].append([[round(a, 3), round(b, 3)] for a, b in g])
    pack = {"source": "OpenStreetMap contributors, ODbL 1.0", "url": "https://www.openstreetmap.org/copyright",
            "fetched": today(), "query": RAIL_QUERY, "lines": lines}
    RAIL.write_text(json.dumps(pack, separators=(",", ":")))
    print(f"→ {RAIL.relative_to(ROOT)}  " + ", ".join(f"{k} {len(v)} ways" for k, v in lines.items()))


# -------------------------------------------------------------- the register

SEGMENTS = [  # map group, legend name, marker kind
    ("rail", "Railways", "square"), ("road", "Roads and bridges", "diamond"),
    ("border", "Border posts, trade and logistics", "triangle"), ("port", "Port", "star"),
    ("energy", "Energy", "hex"), ("other", "Farming, digital, industry, studies", "circle")]
SEG_NAME = {k: n for k, n, _ in SEGMENTS}
SEG_OF = {"rail": "rail", "road": "road", "bridge": "road", "border": "border", "logistics": "border",
          "trade facilitation": "border", "port": "port", "energy": "energy"}

STATUS = {"announced": "Announced", "approved": "Approved", "under_construction": "Under construction",
          "operating": "Operating", "stalled": "Stalled"}
# programmes, studies and plans ("soft": true in the register) are not built:
# the same stages read differently for them
SOFT = {"under_construction": "Under way", "operating": "Running"}


def status_name(p):
    return (SOFT if p.get("soft") else {}).get(p["status"], STATUS[p["status"]])
STAGES = ["announced", "approved", "under_construction", "operating"]

FIRM = [("signed", "Signed or disbursing"), ("approved", "Approved, not yet signed"),
        ("pledged", "Pledged or announced")]
FIRM_OF = {"disbursing": "signed", "signed": "signed", "approved": "approved", "pledged": "pledged"}

# Funder groups wear the debt page's creditor colours (the --dg-* slots,
# validated for colour-blind separation in both themes), as --lf-* here.
FGROUPS = [("multi", "Development banks"), ("us", "United States"), ("europe", "Europe"),
           ("china", "China"), ("private", "Companies and commercial lenders"),
           ("gov", "Corridor governments"), ("other", "Others")]
FG_NAME = dict(FGROUPS)
FG_OF = {"US": "us", "CN": "china", "AO": "gov", "ZM": "gov", "CD": "gov", "private": "private",
         "AfDB": "multi", "AFC": "multi", "WB": "multi", "Afreximbank": "multi", "multilateral": "multi",
         "DBSA": "multi", "MIGA": "multi", "IFC": "multi",
         "EU": "europe", "IT": "europe", "BE": "europe", "DE": "europe", "FR": "europe", "PT": "europe",
         "NL": "europe", "ES": "europe", "HU": "europe", "UK": "europe", "SE": "europe"}

CC = {"AO": "Angola", "CD": "DR Congo", "ZM": "Zambia"}


def load():
    if not SRC.exists():
        sys.exit("missing data/lobito.json — the register is kept by hand")
    if not RAIL.exists():
        sys.exit("missing data/lobito_rail.json — run `python3 build_lobito.py --rail`")
    return json.loads(SRC.read_text()), json.loads(RAIL.read_text())


def usd(f):
    """A financing line's amount in USD (euros at the shared reference rate);
    None for no amount or another currency (kwanza is left as stated)."""
    a = f.get("amount")
    if a is None or f.get("currency", "USD") not in ("USD", "EUR"):
        return None
    return a * EUR_USD if f.get("currency") == "EUR" else a


def counted(f):
    """What a line adds to the sums: a guarantee lends nothing, and a line
    marked "in_total": false is part of another one (its note says which)."""
    if f.get("instrument") == "guarantee" or f.get("in_total") is False:
        return None
    return usd(f)


def money(v, short=False):
    if v is None:
        return "–"
    if v >= 1e9:
        return f"USD {v / 1e9:,.2f} bn".replace(".00 bn", " bn") if not short else f"{v / 1e9:,.1f} bn"
    return f"USD {v / 1e6:,.0f} m" if not short else f"{v / 1e6:,.0f} m"


def native(f):
    """The amount as the source states it."""
    a = f.get("amount")
    if a is None:
        return "not disclosed"
    cur = f.get("currency") or "USD"
    return f"{cur} {a / 1e9:,.2f} bn".replace(".00 bn", " bn") if a >= 1e9 else f"{cur} {a / 1e6:,.1f} m".replace(".0 m", " m")


def fgroup(f):
    return FG_OF.get(f.get("funder_country"), "other")


def seg(p):
    return SEG_OF.get(p["segment"], "other")


def host(url):
    h = urllib.parse.urlparse(url).netloc
    return h[4:] if h.startswith("www.") else h


def src_link(url, label=None):
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label or host(url))}</a>'


def stage_strip(status):
    """Four cells, announced to operating, filled to the project's stage. A
    stalled project shows its cells hollow."""
    if status == "stalled":
        cells = "".join("<i></i>" for _ in STAGES)
        return f'<span class="stage stalled" aria-hidden="true">{cells}</span>'
    k = STAGES.index(status) if status in STAGES else 0
    cells = "".join(f'<i class="on"></i>' if i <= k else "<i></i>" for i in range(len(STAGES)))
    return f'<span class="stage {esc(status)}" aria-hidden="true">{cells}</span>'


def st(status, name=None):
    return f'<span class="st {esc(status)}"><i></i>{esc(name or STATUS.get(status, status))}</span>'


def fdot(g):
    return f'<i class="fk" style="background:var(--lf-{g})"></i>'


# ------------------------------------------------------------ the map marks

def map_payload(reg, rail, num):
    def tip(p):
        fin = p.get("finance", [])
        funders = sorted({f["funder"] for f in fin})
        lines = [f'{esc(status_name(p))} · {esc(p.get("status_note", ""))}']
        if funders:
            lines.append("Funded by " + esc(", ".join(funders)))
        return (f'<b>{num[p["id"]]}. {esc(p["name"])}</b>{esc(SEG_NAME[seg(p)])} · '
                f'{esc(", ".join(CC.get(c, c) for c in p["countries"]))}<br>' + "<br>".join(lines))

    L = rail["lines"]
    rail_tips = {
        "ctx": "<b>Other Angolan railways</b>The Luanda and Moçâmedes lines, not part of the corridor",
        "net": "<b>Rest of the rail network</b>Zambia's Copperbelt lines and the DR Congo's line north from "
               "Tenke. The planned Zambia–Lobito railway would join Zambia Railways at Chingola",
        "drc": "<b>DR Congo railway, Dilolo to Kolwezi, Lubumbashi and Sakania</b>SNCC's line, about 1,000 km, "
               "under a 30-year concession to Mota-Engil Africa since August 2026. The Lobito Atlantic Railway "
               "runs trains from Dilolo to Kolwezi under a track-access deal",
        "cfb": "<b>Benguela Railway, Lobito to Luau</b>1,289 km, rebuilt with a China Eximbank loan (its AidData "
               "record is under Already on the map); run since January 2024 by the Lobito Atlantic Railway "
               "concession",
    }
    # the two corridor lines wear the status of the register's project that
    # names them (its "rail_line": cfb or drc), or the line's own where the
    # project is a concession over a line already running ("line_status")
    line_status = {p["rail_line"]: p.get("line_status", p["status"]) for p in reg["projects"] if p.get("rail_line")}
    groups = [{"id": f"g-rail-{k}", "kind": "line", "cls": f"rail {k} {line_status.get(k, '')}".strip(),
               "items": [{"d": path_d(L[k], eps=0.5), "tip": rail_tips[k]}]} for k in ("ctx", "net", "drc", "cfb")]
    # line projects (planned railways, roads), then a wide transparent copy
    # of each on top so the thin line is easy to point at
    lines, hits = [], []
    for p in reg["projects"]:
        g = p["geometry"]
        if g["type"] != "line":
            continue
        d = path_d([[(w[1], w[2]) for w in g["waypoints"]]], eps=0.3)
        lines.append({"d": d, "cls": f'{seg(p)} {p["status"]}', "tip": tip(p)})
        hits.append({"d": d, "tip": tip(p)})
    groups.append({"id": "g-lines", "kind": "line", "cls": "proj", "items": lines})
    groups.append({"id": "g-hits", "kind": "line", "cls": "hitline", "items": hits})
    # one marker per mapped project: at its point, or halfway along its line;
    # an "area" project (a programme over several provinces) has none
    at = {}
    for p in reg["projects"]:
        g = p["geometry"]
        if g["type"] == "point":
            at[p["id"]] = xy(g["lon"], g["lat"])
        elif g["type"] == "line":
            at[p["id"]] = xy(*_mid(g["waypoints"]))
    # markers closer than 22 px (several projects at Lobito, at Luau, around
    # Huambo) are set out in a row above the place, 30 px apart, each with a
    # leader line down to it, so every number can be read
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
        x0 = max(cx - 15 * (len(near) - 1), 10)
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


def _mid(wps):
    """The point halfway along a waypoint line, for its numbered marker."""
    pts = [(w[1], w[2]) for w in wps]
    seglen = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    half, run = sum(seglen) / 2, 0.0
    for (a, b), s in zip(zip(pts, pts[1:]), seglen):
        if run + s >= half and s:
            t = (half - run) / s
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        run += s
    return pts[0]


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


def nice_step(v):
    p = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v / p <= m:
            return m * p
    return 10 * p


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
           f'funder has put into Lobito Corridor projects, split into signed, approved and pledged">']
    v = 0
    while v <= top + 1e-6:
        out.append(f'<line class="gl" x1="{xv(v):.1f}" x2="{xv(v):.1f}" y1="{T - 6}" y2="{H - 6}"></line>'
                   f'<text class="ax" x="{xv(v):.1f}" y="{T - 10}" text-anchor="middle">'
                   f'{v / 1e9:,.1f}{" bn" if v == top else ""}</text>'.replace(">0.0<", ">0<"))
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


def _bar(x, y, w, h, r):
    """A horizontal bar, square at the baseline, rounded r at its data end."""
    r = min(r, w / 2, h / 2)
    return (f"M{x:.1f} {y:.1f} H{x + w - r:.1f} Q{x + w:.1f} {y:.1f} {x + w:.1f} {y + r:.1f} "
            f"V{y + h - r:.1f} Q{x + w:.1f} {y + h:.1f} {x + w - r:.1f} {y + h:.1f} H{x:.1f} Z")


# the funder chart's row labels; tooltips and tables keep the full names
FUNDER_SHORT = {
    "US International Development Finance Corporation (DFC)": "US DFC",
    "Millennium Challenge Corporation (MCC)": "US Millennium Challenge Corp.",
    "US Trade and Development Agency (USTDA)": "US Trade and Development Agency",
    "Cassa Depositi e Prestiti (CDP), guaranteed by SACE": "Italy's CDP, SACE guarantee",
    "Rome Process / Mattei Plan Financing Facility (Italy, at the AfDB)": "Mattei Plan facility (Italy)",
    "Italian Agency for Development Cooperation (AICS)": "Italy's AICS",
    "Development Bank of Southern Africa (DBSA)": "Development Bank of Southern Africa",
    "Lobito Atlantic Railway (Trafigura, Mota-Engil, Vecturis)": "Lobito Atlantic Railway",
    "Germany and the European Investment Bank": "Germany and the EIB",
    "International Finance Corporation (IFC)": "IFC (World Bank Group)",
    "World Bank (Diversifica Mais project)": "World Bank",
    "ARCCLA (Government of Angola)": "ARCCLA (Angola)",
    "Africa Finance Corporation (AFC)": "Africa Finance Corp. (AFC)",
    "African Development Bank Group": "African Development Bank",
    "Multilateral Investment Guarantee Agency (MIGA)": "MIGA (World Bank Group)",
    "Fonds National d'Entretien Routier (FONER)": "FONER (DR Congo road fund)",
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
            why = ("guarantee" if f.get("instrument") == "guarantee" else "inside another line"
                   if f.get("in_total") is False else "in kwanza" if usd(f) is None and f.get("amount") else
                   "not disclosed")
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


def donut(order, total):
    """A 72 px donut of the funders' shares, from twelve o'clock clockwise in
    the list's order, with the total in the hole. Each slice carries its
    tooltip; a 1.5 px surface stroke is the gap between slices."""
    R, r, c = 33.0, 21.0, 36.0
    out, a0 = [], -math.pi / 2
    for sl in order:
        a1 = a0 + 2 * math.pi * sl["v"] / total
        big = 1 if a1 - a0 > math.pi else 0
        pt = lambda rad, a: f"{c + rad * math.cos(a):.2f} {c + rad * math.sin(a):.2f}"
        d = (f"M{pt(R, a0)} A{R} {R} 0 {big} 1 {pt(R, a1)} L{pt(r, a1)} A{r} {r} 0 {big} 0 {pt(r, a0)} Z")
        share = sl["v"] / total * 100
        tip = (f'{sl["name"]}: {money(sl["v"])}, {"<1" if share < 1 else f"{share:.0f}"}%'
               f'{", pledged" if sl["pledged"] else ""}')
        out.append(f'<path class="ds{" pl" if sl["pledged"] else ""}" d="{d}" style="fill:var(--lf-{sl["g"]})">'
                   f'<title>{esc(tip)}</title></path>')
        a0 = a1
    tot = money(total, short=True)
    return (f'<svg class="donut" viewBox="0 0 72 72" width="72" height="72" role="img" '
            f'aria-label="Shares of {esc(money(total))} by funder">{"".join(out)}'
            f'<text x="36" y="33" text-anchor="middle" class="dt1">USD</text>'
            f'<text x="36" y="44" text-anchor="middle" class="dt2">{esc(tot)}</text></svg>')


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

def build_page(reg, rail):
    P = reg["projects"]
    order = {k: i for i, (k, _, _) in enumerate(SEGMENTS)}

    def west_to_east(p):
        g = p["geometry"]       # an area carries a lon too, for this order only
        return _mid(g["waypoints"])[0] if g["type"] == "line" else g["lon"]
    P.sort(key=lambda p: (order[seg(p)], west_to_east(p)))
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
        f"The {len(P)} projects of the register, by kind and from the Atlantic eastwards. The number is the "
        f"marker's on the map. The bar shows how far each has got: announced, approved, being built, in "
        f"service. Funders are coloured by kind.",
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
            td((money(usd(f)) if f.get("currency") == "EUR" and f.get("amount") else "")
               + ('<span class="nis">not in the sums</span>' if usd(f) and counted(f) is None else ""), "num dim"),
            td(f'<span class="firm f-{FIRM_OF.get(f["firmness"], "pledged")}"><i></i>{esc(f["firmness"])}</span>'),
            td(esc(str(f["year"])) if f.get("year") else '<span class="dim">–</span>'),
            td(f'{esc(f.get("note", ""))} {src_link(f["source"])}', "dnote"),
        ])
    t_deals = table(
        f"Every financing line in the register, {len(deals)} of them. Amounts as the source states them, with "
        f"euros converted at {esc(EUR_NOTE)}. Firmness: pledged (an announcement or memorandum), approved (a "
        f"board decision), signed (an agreement), disbursing (money flowing). Guarantees, and lines that are "
        f"part of another, are listed but left out of the sums.",
        ["Project", "Funder", "Instrument", "#Amount", "#In USD", "Firmness", "Year", "Note and source"],
        drows, cls="deals")

    # ---- the umbrella pledges
    prow = []
    for pl in sorted(reg.get("pledges", []), key=lambda x: x.get("date", "")):
        prow.append([td(f'{fdot(FG_OF.get(pl.get("funder_country"), "other"))}<b>{esc(pl["funder"])}</b>', "name"),
                     td(esc(pl["what"]) + (f'<span class="dim pc">{esc(pl["note"])}</span>' if pl.get("note") else "")),
                     td(esc(native(pl)), "num"), td(esc(pl.get("firmness", ""))),
                     td(f'{esc(fmt_date(pl.get("date", "")))} {src_link(pl["source"])}', "dnote")])
    t_pledges = table(
        "The headline commitments, as their makers announced them. They overlap one another and the project "
        "lines above, include private money they hope to attract, and are not added up anywhere on this page.",
        ["Who", "What was promised", "#Amount", "Kind", "When and source"], prow, cls="pledges")

    # ---- money counted under the corridor's name that is not on it
    ew = reg.get("elsewhere", [])
    erow = [[td(f'{fdot(FG_OF.get(e.get("funder_country"), "other"))}{esc(e["funder"])}', "name"),
             td(esc(e["what"]) + (f'<span class="dim pc">{esc(e["where"])}</span>' if e.get("where") else "")),
             td(esc(native(e)), "num"), td(esc(e.get("firmness", ""))),
             td(f'{esc(e.get("note", ""))} {src_link(e["source"])}', "dnote")] for e in ew]
    ew_total = sum(usd(e) or 0 for e in ew if e.get("instrument") != "insurance")
    t_elsewhere = table(
        "Financing that its funder, or the White House, has counted under the Lobito Corridor, but that is "
        "not on it or names no place on it. It is not in the register's projects, the map or the sums above; "
        "the insurance is listed but not added to the total.",
        ["Funder", "What", "#Amount", "Firmness", "Note and source"], erow, cls="pledges")

    # ---- timeline and governance
    tl = "".join(f'<li><span class="m">{esc(fmt_date(e["date"]))}</span><span>{esc(e["event"])} '
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
        "__RAIL_FETCHED__": fmt_date(rail["fetched"]), "__EUR_NOTE__": esc(EUR_NOTE),
        "__MAP_W__": f"{MAP_W:.0f}", "__MAP_H__": f"{MAP_H:.0f}", "__BASEMAP__": basemap(),
        "__LOCATOR__": locator(reg, rail),
        "__SEG_LEGEND__": "".join(
            f'<label><input type="checkbox" checked data-g="g-{k}"><span class="sw seg-{k}"></span>{esc(n)}</label>'
            for k, n, _ in SEGMENTS if any(seg(p) == k and p["geometry"]["type"] != "area" for p in P)),
        "__STATUS_KEY__": "".join(f'<span class="dk"><i class="sk {k}"></i>{esc(n)}</span>' for k, n in STATUS.items()),
        "__FUNDER_KEY__": "".join(f'<span class="dk">{fdot(g)}{esc(n)}</span>' for g, n in FGROUPS
                                  if any(a["g"] == g for _, a in frows)),
        "__FIRM_KEY__": "".join(f'<span class="dk"><i class="fz f-{k}"></i>{esc(n)}</span>' for k, n in FIRM),
        "__STATUS_BOARD__": board, "__TABLE_ELSEWHERE__": t_elsewhere, "__ELSEWHERE__": money(ew_total),
        "__ELSEWHERE_CMP__": "more than" if ew_total > firm_tot["signed"] else "against",
        "__N_ELSEWHERE__": str(len(ew)), "__CHART_FUNDERS__": funders_svg(frows), "__MATRIX__": matrix_html(reg, num),
        "__TABLE_DEALS__": t_deals, "__TABLE_PLEDGES__": t_pledges, "__TIMELINE__": tl, "__GOVERNANCE__": gov,
        "__SITE_RECORDS__": site_records(reg),
    }
    for k, v in reg.get("prose", {}).items():     # figures the lede states, kept in the register
        tokens[f"__{k.upper()}__"] = esc(v)
    payload = {"map": map_payload(reg, rail, num), "charts": {}}
    return tokens, payload


# ----------------------------------------------- what the site already holds

SITE_LAYERS = [  # file, layer name, id field, link field
    ("iati_afdb_finance.geojson", "AfDB", "iati_id", "project_url"),
    ("iati_worldbank_finance.geojson", "World Bank", "iati_id", "project_url"),
    ("iati_eu_finance.geojson", "EU finance", "iati_id", "project_url"),
    ("piano_mattei.geojson", "Piano Mattei", "id", "url"),
    ("aiddata_china_finance.geojson", "China (AidData)", "aiddata_id", "url"),
    ("osm_construction.geojson", "OpenStreetMap", "osm_id", None),
    ("gem_power_assets.geojson", "Power plants (GEM)", "project_id", "url"),
]
# "Lobito" alone is a town (its sanitation and its refinery are not the
# corridor's); the corridor, its railway and its port are. Kasomeno-Mwenda is
# left out: no funder calls it the corridor's, and it runs east, to Tanzania
CORRIDOR_WORDS = re.compile(r"lobito\W+(?:\w+\W+){0,2}corridor|corredor do lobito|lobito port|port of lobito|"
                            r"benguela rail|caminho de ferro de benguela|dilolo", re.I)


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
            rows.append((layer, [td(esc(layer)), td(src_link(link, label) if link else name, "name"),
                                 td(esc(q.get("country") or "")), td(st(q.get("dash_status", ""))),
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
            "about": {"@type": "Place", "name": "Lobito Corridor"}}
    return ('<script type="application/ld+json">'
            + json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n")


NOINDEX = ('<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">',
           '<meta name="robots" content="noindex,nofollow">')


def build():
    reg, rail = load()
    tokens, payload = build_page(reg, rail)
    tokens.update({"__TITLE__": esc(TITLE), "__DATA_URL__": site_url("data/lobito.json"),
                   "__DATA_FILE__": "lobito.json", "__BUILT__": fmt_date(today())})
    page = FRAME.read_text().replace("<!--__BODY__-->", FRAG.read_text(), 1)
    for k, v in tokens.items():
        page = page.replace(k, v)
    page = page.replace("/*__PAYLOAD__*/", json.dumps(payload, ensure_ascii=False, separators=(",", ":")), 1)
    # "lobito" is in no menu, so the Deep dives menu marks nothing current and
    # opens its entries in this tab, as on the other deep dives
    page = brand_assets(page, donor=SLUG)
    left = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]*__", page)))
    if left:
        sys.exit(f"lobito: unfilled tokens {', '.join(left)}")
    path = f"{SLUG}/index.html"
    doc = wrap_document(page, title=TITLE, description=DESCRIPTION, path=path, kind="profile",
                        extra_head=jsonld(path))
    if NOINDEX[0] not in doc:
        sys.exit("lobito: the robots meta changed in shared.wrap_document; update NOINDEX")
    doc = doc.replace(*NOINDEX)
    (DOCS / SLUG).mkdir(parents=True, exist_ok=True)
    (DOCS / SLUG / "index.html").write_text(doc)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC, DOCS / "data" / SRC.name)
    print(f"→ docs/{path}  {len(doc.encode()) / 1024:.0f} KB  (+ docs/data/{SRC.name})")


if __name__ == "__main__":
    if "--rail" in sys.argv[1:] or not RAIL.exists():
        fetch_rail()
    build()
