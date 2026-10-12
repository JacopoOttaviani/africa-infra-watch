#!/usr/bin/env python3
"""
Build the strategic corridors page, docs/corridors/index.html, from a
hand-kept register of Africa's main transport and energy corridors,
data/corridors.json.

    python3 build_corridors.py

The page is not linked from the site yet: it is in no menu, not in the
sitemap or llms.txt, and its <meta robots> says noindex, nofollow. To
announce it, add it to DEEP_THEMES and write_site_index() in shared.py,
add this script to refresh.py's build list and drop the NOINDEX swap below.

The register is curated by hand, not fetched. A corridor is in it when a
published priority list names it (the EU's Global Gateway strategic
corridors for Africa, the African Union's PIDA PAP2, the G7's PGII
flagships) or when it is one of the continent's large cross-border projects
with a foreign state behind it (TAZARA's Chinese rebuild, EACOP, Simandou,
the Saharan and Atlantic gas pipelines). Each corridor is split into a few
pieces (a port, a railway, a road, a pipeline), each with its own stage and
the address it was read from, and a list of who pays for, owns and builds
it. It is a register of the set, not of every deal: the corridors with a
deep dive of their own (/lobito/) carry their full financing there.

Geometry: pipelines are drawn from Global Energy Monitor's tracker already
on the site (data/gem_oil_gas_pipelines.geojson), the Lobito Corridor's
railway from OpenStreetMap (data/lobito_rail.json, build_lobito.py --rail);
everything else is drawn through the towns it links, as published, not on a
surveyed alignment. The map is equirectangular, on the 1:10m Natural Earth
basemap, and drawn here; the page's own script adds the tooltips, the
highlight and the colour switch.

The page wears the lender profiles' frame (donor.template.html). It reuses
build_lobito.py's helpers, which that page keeps stable for this one.
"""

import json
import math
import pathlib
import re
import shutil
import sys

from build_donors import FRAME, table, td
from build_donors import NAMES
from build_lobito import (STAGES, STATUS, _mid, clip_ring, esc, host, simplify, src_link, st,
                          stage_strip)
from shared import (AUTHOR_NAME, AUTHOR_URL, DATA, DOCS, EUR_USD, SITE_NAME, SITE_URL, WEB_URL,
                    brand_assets, fmt_date, site_url, today, wrap_document)

ROOT = pathlib.Path(__file__).parent
SRC = DATA / "corridors.json"
GEM = DATA / "gem_oil_gas_pipelines.geojson"
LOBITO_RAIL = DATA / "lobito_rail.json"
FRAG = ROOT / "sections" / "corridors.html"
SLUG = "corridors"
TITLE = "Africa's strategic corridors"
DESCRIPTION = ("Africa's strategic corridors on one map, from LAPSSET and the Lobito Corridor to TAZARA, the "
               "standard gauge railways, EACOP and the Saharan gas pipelines: the railways, roads, ports and "
               "pipelines of each, where every piece stands and who pays for and builds it, China, the United "
               "States, Europe, the Gulf or the development banks.")

# the site's country names, plus the two territories the register needs
CC = dict(NAMES, EH="Western Sahara", SO="Somalia")


# ------------------------------------------------------------- projection

# An equirectangular window on the continent, Dakar to Cape Guardafui and
# Tunis to the Cape. The northern edge cuts Spain, where the Atlantic gas
# pipeline is meant to end.
LON0, LON1, LAT0, LAT1 = -18.5, 52.5, -35.4, 38.2
MAP_W = 980.0
SC = MAP_W / (LON1 - LON0)
MAP_H = (LAT1 - LAT0) * SC


def xy(lon, lat):
    return round((lon - LON0) * SC, 1), round((LAT1 - lat) * SC, 1)


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


def in_window(lon, lat, pad=0.5):
    return LON0 - pad <= lon <= LON1 + pad and LAT0 - pad <= lat <= LAT1 + pad


# -------------------------------------------------------------- basemap

SEAS = [("Atlantic Ocean", -12.5, -8.0), ("Indian Ocean", 46.0, -24.5), ("Mediterranean Sea", 19.0, 35.0),
        ("Gulf of Guinea", 2.5, 1.2), ("Red Sea", 37.6, 21.0)]


def basemap():
    bm = json.loads((DATA / "africa_basemap_10m.json").read_text())
    out = []
    for c in bm["countries"]:
        rings = [ring for poly in c["p"] for ring in poly]
        if not any(in_window(x, y) for ring in rings for x, y in ring):
            continue
        d = path_d(rings, closed=True, eps=0.7)
        if d:
            out.append(f'<path class="land{"" if c.get("af") else " ctx"}" d="{d}"><title>{esc(c["n"])}</title></path>')
    for lk in bm["lakes"]:
        xs = [x for ring in lk["r"] for x, _ in ring]
        ys = [y for ring in lk["r"] for _, y in ring]
        # the great lakes only: Victoria, Tanganyika, Malawi, Turkana, Chad, Volta, Kariba
        if in_window(sum(xs) / len(xs), sum(ys) / len(ys), 0) and max(max(xs) - min(xs), max(ys) - min(ys)) > 0.9:
            out.append(f'<path class="lake" d="{path_d(lk["r"], closed=True)}"><title>{esc(lk["n"])}</title></path>')
    for lb in bm["labels"]:
        if lb["z"] > 3.2 or not in_window(lb["x"], lb["y"], 0):
            continue
        x, y = xy(lb["x"], lb["y"])
        out.append(f'<text class="ctry" x="{x}" y="{y}" text-anchor="middle">{esc(lb["n"].upper())}</text>')
    for name, lon, lat in SEAS:
        x, y = xy(lon, lat)
        out.append(f'<text class="sea" x="{x}" y="{y}" text-anchor="middle">{esc(name)}</text>')
    return "\n".join(out)


# ------------------------------------------------------------- the register

MODES = [  # mode, legend name
    ("rail", "Railway"), ("road", "Road or bridge"), ("pipeline", "Pipeline"),
    ("port", "Port"), ("other", "Border post, power line or other")]
MODE_OF = {"rail": "rail", "road": "road", "bridge": "road", "pipeline": "pipeline", "port": "port"}

KINDS = {"rail": "Railway", "road": "Road", "pipeline": "Pipeline", "multimodal": "Multimodal"}

REGIONS = [("west", "North and West Africa"), ("east", "East Africa and the Horn"),
           ("south", "Central and Southern Africa")]

# Backer groups. The eight hues are the site's validated categorical palette
# (the debt page's --dg-* and the Lobito page's --lf-* slots, plus slots 7
# and 8), as --cf-* here; "unknown" is the neutral grey.
GROUPS = [("china", "China"), ("us", "United States"), ("europe", "Europe"), ("gulf", "Gulf states"),
          ("otherstate", "Other states"), ("multi", "Development banks"),
          ("gov", "African governments"), ("private", "Companies and commercial banks")]
G_NAME = dict(GROUPS)
EUROPE = {"EU", "FR", "DE", "IT", "PT", "ES", "NL", "BE", "UK", "GB", "SE", "DK", "FI", "NO", "AT", "HU",
          "IE", "LU", "CH", "PL", "CZ"}
GULF = {"AE", "SA", "QA", "KW", "OM", "BH"}
MULTI = {"AfDB", "WB", "IFC", "MIGA", "AFC", "IsDB", "OPEC Fund", "Afreximbank", "BOAD", "DBSA", "TDB",
         "BADEA", "AIIB", "EBID", "multilateral", "IDA", "EADB", "NDB", "Shelter Afrique"}
AFRICA = set(NAMES) | {"EH"}


def group_of(code):
    if code == "CN":
        return "china"
    if code == "US":
        return "us"
    if code in EUROPE:
        return "europe"
    if code in GULF:
        return "gulf"
    if code in MULTI:
        return "multi"
    if code in AFRICA:
        return "gov"
    if code == "private":
        return "private"
    return "otherstate" if code and re.fullmatch(r"[A-Z]{2}", code) else "private"


# the roles that put money or ownership in, against those that only build
PAYS = {"lender", "grant", "equity", "owner", "concessionaire", "guarantor", "sponsor"}
ROLE = {"lender": "lender", "grant": "grant", "equity": "equity", "owner": "owner",
        "concessionaire": "concession", "builder": "builder", "guarantor": "guarantor", "sponsor": "own budget"}


def load():
    if not SRC.exists():
        sys.exit("missing data/corridors.json — the register is kept by hand")
    reg = json.loads(SRC.read_text())
    gem = {f["properties"]["name"]: f for f in json.loads(GEM.read_text())["features"]} if GEM.exists() else {}
    rail = json.loads(LOBITO_RAIL.read_text()) if LOBITO_RAIL.exists() else None
    return reg, gem, rail


def seg_lines(s, gem, rail):
    """A segment's geometry as lon/lat polylines ([] for a point)."""
    g = s["geometry"]
    if g["type"] == "line":
        return [[(w[1], w[2]) for w in g["waypoints"]]]
    if g["type"] == "gem":
        f = gem.get(g["name"])
        if not f:
            sys.exit(f"corridors: no GEM pipeline named {g['name']!r}")
        geo = f["geometry"]
        lines = [[tuple(p) for p in ln] for ln in (geo["coordinates"] if geo["type"] == "MultiLineString"
                                                   else [geo["coordinates"]])]
        # a pipeline built section by section: "lat": [south, north] keeps
        # the part of GEM's line between two parallels
        return clip_lat(lines, *g["lat"]) if g.get("lat") else lines
    if g["type"] == "osm_lobito":
        if not rail:
            sys.exit("corridors: missing data/lobito_rail.json — run `python3 build_lobito.py --rail`")
        return [[tuple(p) for p in ln] for k in g["lines"] for ln in rail["lines"][k]]
    return []


def clip_lat(lines, south, north):
    """Polylines cut to the band between two latitudes, split where they
    leave it, with a point interpolated on each crossing."""
    out = []
    for ln in lines:
        cur = []
        for a, b in zip(ln, ln[1:] + [None]):
            if south <= a[1] <= north:
                cur.append(a)
            if b is None:
                break
            for edge in (south, north):
                if (a[1] - edge) * (b[1] - edge) < 0:
                    t = (edge - a[1]) / (b[1] - a[1])
                    cur.append((a[0] + (b[0] - a[0]) * t, edge))
                    if not south <= b[1] <= north:
                        if len(cur) > 1:
                            out.append(cur)
                        cur = []
        if len(cur) > 1:
            out.append(cur)
    return out


def seg_point(s):
    g = s["geometry"]
    return (g["lon"], g["lat"]) if g["type"] == "point" else None


def chain_mid(lines):
    """The point halfway along the longest of a segment's polylines."""
    best = max(lines, key=lambda ln: sum(math.dist(a, b) for a, b in zip(ln, ln[1:])))
    return _mid([("", a, b) for a, b in best])


def money_native(c):
    a = c.get("amount")
    if a is None:
        return None
    cur = c.get("currency") or "USD"
    return f"{cur} {a / 1e9:,.1f} bn".replace(".0 bn", " bn") if a >= 1e9 else f"{cur} {a / 1e6:,.0f} m"


def lead_group(cor, s):
    """The colour of a segment under "who pays": its first funder's group."""
    by = {b["name"]: b for b in cor.get("backers", [])}
    for name in s.get("funded_by", []):
        if name in by:
            return group_of(by[name].get("funder_country"))
    return "unknown"


# ------------------------------------------------------------- the map marks

# planned pieces are drawn first, so that where a planned railway follows a
# road already built (LAPSSET's), the road shows on top and answers the pointer
DRAW_RANK = {"announced": 0, "approved": 1, "stalled": 2, "under_construction": 3, "operating": 4}


def map_marks(P, num, gem, rail):
    """Static SVG for the corridors: a casing and a stroke per line segment,
    a dot per point segment, a wide transparent copy of each line to point
    at, and one numbered marker per corridor. Every mark carries the
    corridor's id (data-c) and a prebuilt tooltip (data-tip)."""
    cases, strokes, hits, dots, anchors = [], [], [], [], {}
    for cor in P:
        cid = cor["id"]
        longest, best = None, -1.0
        for s in cor["segments"]:
            mode = MODE_OF.get(s["mode"], "other")
            grp = lead_group(cor, s)
            tip = esc(seg_tip(cor, s, num))
            lines = seg_lines(s, gem, rail)
            if lines:
                d = path_d(lines, eps=0.8)
                if not d:
                    continue
                cls = f'{mode} {s["status"]} b-{grp}'
                cases.append(f'<path class="case {mode}" data-c="{cid}" d="{d}"></path>')
                strokes.append((DRAW_RANK[s["status"]], f'<path class="seg {cls}" data-c="{cid}" d="{d}"></path>'))
                hits.append((DRAW_RANK[s["status"]], f'<path class="hitl" data-c="{cid}" data-tip="{tip}" d="{d}"></path>'))
                ln = sum(math.dist(a, b) for line in lines for a, b in zip(line, line[1:]))
                if s.get("anchor"):
                    ln = 1e9
                if ln > best:
                    best, longest = ln, chain_mid(lines)
            elif seg_point(s):
                x, y = xy(*seg_point(s))
                dots.append(f'<circle class="pt {mode} {s["status"]} b-{grp}" data-c="{cid}" data-tip="{tip}" '
                            f'cx="{x}" cy="{y}" r="{5.2 if mode == "port" else 4.2}"></circle>')
                if longest is None and best < 0:
                    longest = seg_point(s)
        if cid in MARK_AT:
            px_lines = [[xy(*p) for p in ln] for s in cor["segments"] for ln in seg_lines(s, gem, rail)]
            px_pts = [xy(*seg_point(s)) for s in cor["segments"] if seg_point(s)]
            anchors[cid] = snap(xy(*MARK_AT[cid]), px_lines, px_pts)
        else:
            anchors[cid] = xy(*longest)
    # markers closer than 24 px are set out in a row above their places,
    # 24 px apart, each with a leader line down to its own
    placed, leads, done = dict(anchors), [], set()
    for cid, (x, y) in sorted(anchors.items(), key=lambda t: num[t[0]]):
        if cid in done:
            continue
        near = [q for q in anchors if q not in done and math.dist(anchors[q], (x, y)) < 24]
        done.update(near)
        if len(near) < 2:
            continue
        cx = sum(anchors[q][0] for q in near) / len(near)
        cy = sum(anchors[q][1] for q in near) / len(near)
        near.sort(key=lambda q: anchors[q][0])
        x0 = max(cx - 12 * (len(near) - 1), 12)
        for i, q in enumerate(near):
            mx, my = x0 + 24 * i, cy - 30
            placed[q] = (round(mx, 1), round(my, 1))
            leads.append(f'<path class="leader" data-c="{q}" d="M{mx:.1f} {my:.1f} L{anchors[q][0]:.1f} {anchors[q][1]:.1f}"></path>')
    marks = []
    for cor in P:
        cid = cor["id"]
        x, y = placed[cid]
        marks.append(f'<g class="mk" data-c="{cid}" data-tip="{esc(cor_tip(cor, num))}" tabindex="0" role="button" '
                     f'aria-label="{esc(cor["name"])}"><circle cx="{x}" cy="{y}" r="9.5"></circle>'
                     f'<text x="{x}" y="{y + 3.6}" text-anchor="middle">{num[cid]}</text></g>')
    return ("<g id=\"g-case\">" + "".join(cases) + "</g><g id=\"g-seg\">" + "".join(h for _, h in sorted(strokes, key=lambda r: r[0])) + "</g>"
            "<g id=\"g-hit\">" + "".join(h for _, h in sorted(hits, key=lambda r: r[0])) + "</g><g id=\"g-pt\">" + "".join(dots) + "</g>"
            "<g id=\"g-lead\">" + "".join(leads) + "</g><g id=\"g-mk\">" + "".join(marks) + "</g>")


# The towns named on the map: the corridors' ports, their ends and the
# capitals they run through, placed by hand so that no two labels collide.
# name, lon, lat, label offset dx, dy, anchor
TOWNS = [
    ("Algiers", 3.05, 36.77, 6, 3.5, "start"), ("Hassi R'Mel", 3.27, 32.93, -6, 3.5, "end"),
    ("Tamanrasset", 5.52, 22.79, 6, 3.5, "start"), ("Agadez", 7.98, 17.0, 6, 3.5, "start"),
    ("Kano", 8.52, 12.0, 6, 3.5, "start"), ("Niamey", 2.11, 13.51, -6, 3.5, "end"),
    ("Lagos", 3.39, 6.45, 4, 13, "start"), ("Abidjan", -4.03, 5.32, -4, 13, "end"),
    ("Dakhla", -15.93, 23.7, -6, 3.5, "end"), ("Nouakchott", -15.98, 18.09, -6, 3.5, "end"),
    ("Morebaya", -13.25, 9.25, -6, 3.5, "end"), ("Simandou", -8.85, 8.55, 6, 3.5, "start"),
    ("Douala", 9.7, 4.05, -6, 0, "end"), ("Kribi", 9.91, 2.94, -6, 5, "end"),
    ("Ngaoundéré", 13.58, 7.32, 6, 3.5, "start"), ("N'Djamena", 15.05, 12.11, 6, 3.5, "start"),
    ("Addis Ababa", 38.7, 9.03, -6, 3.5, "end"), ("Djibouti", 43.15, 11.59, 6, 0, "start"),
    ("Berbera", 45.02, 10.44, 6, 3.5, "start"), ("Lamu", 40.9, -2.27, 6, 3.5, "start"),
    ("Mombasa", 39.67, -4.04, 6, 3.5, "start"), ("Nairobi", 36.82, -1.28, 6, 3.5, "start"),
    ("Kampala", 32.58, 0.32, -6, 0, "end"), ("Kigali", 30.06, -1.95, -6, 3.5, "end"),
    ("Hoima", 31.35, 1.43, -6, 3.5, "end"), ("Tanga", 39.1, -5.07, 6, 3.5, "start"),
    ("Dar es Salaam", 39.27, -6.8, 6, 3.5, "start"), ("Mwanza", 32.9, -2.52, 6, -3, "start"),
    ("Kigoma", 29.63, -4.88, -6, 3.5, "end"), ("Moyale", 39.05, 3.52, 6, 3.5, "start"),
    ("Lokichar", 35.65, 2.38, -6, 3.5, "end"),
    ("Lobito", 13.55, -12.35, -6, 3.5, "end"), ("Kolwezi", 25.47, -10.72, 0, -7, "middle"),
    ("Kapiri Mposhi", 28.68, -13.97, -6, 3.5, "end"), ("Lusaka", 28.28, -15.42, -6, 3.5, "end"),
    ("Harare", 31.04, -17.82, 6, 3.5, "start"), ("Beitbridge", 30.0, -22.21, 6, 3.5, "start"),
    ("Pretoria", 28.23, -25.71, -6, 3.5, "end"), ("Maputo", 32.59, -25.97, 6, 3.5, "start"),
    ("Nacala", 40.68, -14.54, 6, 3.5, "start"), ("Moatize", 33.95, -16.1, -6, 3.5, "end"),
]


def node_svg():
    out = []
    for name, lon, lat, dx, dy, anchor in TOWNS:
        x, y = xy(lon, lat)
        out.append(f'<circle class="town" cx="{x}" cy="{y}" r="2.3"></circle>'
                   f'<text class="tlbl" x="{x + dx}" y="{y + dy}" text-anchor="{anchor}">{esc(name)}</text>')
    return "".join(out)


# Where each corridor's numbered marker goes: a spot chosen by hand so the
# markers keep apart, snapped onto the corridor's own nearest line.
MARK_AT = {
    "dakhla-atlantic-sahel": (-13.2, 27.15), "nigeria-morocco-gas": (-18.3, 14.0),
    "simandou-transguinean": (-11.0, 9.6), "abidjan-lagos": (-1.5, 5.0),
    "niger-benin-pipeline": (3.0, 10.5), "trans-saharan-highway": (3.6, 30.0),
    "trans-saharan-gas": (5.5, 25.5), "addis-djibouti-railway": (41.0, 9.5),
    "berbera-corridor": (44.5, 9.9), "lapsset": (38.4, 1.8), "northern-corridor-sgr": (38.4, -3.0),
    "central-corridor-sgr": (35.0, -6.0), "eacop": (32.9, -3.9), "douala-ndjamena": (14.6, 9.6),
    "lobito": (17.6, -12.25), "tazara": (31.6, -10.7), "north-south": (30.6, -20.0),
    "maputo": (30.5, -25.5), "nacala": (37.5, -14.9),
}


def snap(target, lines, points):
    """The point of a corridor's lines (or its point pieces) nearest to a
    target, all in map pixels."""
    best, at = float("inf"), target
    for ln in lines:
        for a, b in zip(ln, ln[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((target[0] - a[0]) * dx + (target[1] - a[1]) * dy) / L)) if L else 0.0
            p = (a[0] + dx * t, a[1] + dy * t)
            d = math.dist(p, target)
            if d < best:
                best, at = d, p
    for p in points:
        if math.dist(p, target) < best:
            best, at = math.dist(p, target), p
    return round(at[0], 1), round(at[1], 1)


# --------------------------------------------------------------- tooltips

def countries(cor):
    return ", ".join(CC.get(c, c) for c in cor["countries"])


def seg_tip(cor, s, num):
    by = {b["name"]: b for b in cor.get("backers", [])}
    funders = [n for n in s.get("funded_by", []) if n in by or n]
    builders = [b["name"] for b in cor.get("backers", []) if b.get("role") == "builder" and b.get("segment") == s["name"]]
    km = f' · {s["length_km"]:,.0f} km' if s.get("length_km") else ""
    lines = [f'{STATUS[s["status"]]}{km} · {s.get("status_note", "")}']
    if funders:
        lines.append("Paid by " + ", ".join(funders))
    if builders:
        lines.append("Built by " + ", ".join(builders))
    return f'<b>{num[cor["id"]]}. {cor["short"]}: {s["name"]}</b>' + "<br>".join(esc(t) for t in lines)


def cor_tip(cor, num):
    cost = money_native(cor["cost"]) if cor.get("cost") else None
    bits = [f'{KINDS.get(cor["kind"], cor["kind"])} · {countries(cor)}']
    if cor.get("length_km"):
        bits[0] += f' · {cor["length_km"]:,.0f} km'
    bits.append(f'{STATUS[cor["status"]]}: {cor.get("status_note", "")}')
    if cost:
        bits.append(f'Cost: {cost}')
    return f'<b>{num[cor["id"]]}. {cor["name"]}</b>' + "<br>".join(esc(t) for t in bits)


# ----------------------------------------------------------- the page parts

def gdot(g):
    return f'<i class="gk" style="background:var(--cf-{g})"></i>'


def side_list(P, num):
    """The numbered list beside the map: hovering an entry lights its
    corridor; clicking it goes to its row in the table."""
    out = []
    for key, rname in REGIONS:
        group = [c for c in P if c["region"] == key]
        if not group:
            continue
        out.append(f'<li class="rg">{esc(rname)}</li>')
        for c in group:
            out.append(f'<li><a href="#c-{c["id"]}" data-c="{c["id"]}"><span class="pn">{num[c["id"]]}</span>'
                       f'<span class="nm">{esc(c["short"])}</span>'
                       f'<span class="sd {c["status"]}" title="{esc(STATUS[c["status"]])}"></span></a></li>')
    return "".join(out)


def backer_cell(cor):
    pay = [b for b in cor.get("backers", []) if b.get("role") in PAYS]
    build = [b for b in cor.get("backers", []) if b.get("role") == "builder"]

    def line(b):
        amt = money_native(b)
        meta = ", ".join(x for x in (ROLE.get(b.get("role"), b.get("role", "")), amt, str(b["year"]) if b.get("year") else None) if x)
        return (f'<span class="fw">{gdot(group_of(b.get("funder_country")))}<span>{esc(b["name"])}'
                f'<span class="dim"> · {esc(meta)}</span> {src_link(b["source"], "↗")}</span></span>')
    out = "".join(line(b) for b in pay) or '<span class="dim">no financing found</span>'
    if build:
        out += '<span class="kl2">Built by</span>' + "".join(line(b) for b in build)
    return out


def pieces_cell(cor):
    out = []
    for s in cor["segments"]:
        km = f' · {s["length_km"]:,.0f} km' if s.get("length_km") else ""
        out.append(f'<li><span class="sd {s["status"]}"></span><span><b>{esc(s["name"])}</b>'
                   f'<span class="dim"> · {esc(STATUS[s["status"]].lower())}{km}</span> '
                   f'<span class="pnote">{esc(s.get("status_note", ""))} {src_link(s["source"], host(s["source"]))}</span></span></li>')
    return f'<ul class="pieces">{"".join(out)}</ul>'


def board(P, num):
    rows = []
    for key, rname in REGIONS:
        group = [c for c in P if c["region"] == key]
        if not group:
            continue
        rows.append([f'<td colspan="4" class="grp">{esc(rname)}</td>'])
        for c in group:
            tags = "".join(f'<a class="tag" href="{esc(n["source"])}" target="_blank" rel="noopener noreferrer">'
                           f'{esc(short_list(n["list"]))}</a>' for n in c.get("named_by", []))
            cost = c.get("cost")
            facts = [KINDS.get(c["kind"], c["kind"]), countries(c)]
            if c.get("length_km"):
                facts.append(f'{c["length_km"]:,.0f} km')
            cost_html = (f'<span class="cost">Cost: {esc(money_native(cost))}'
                         f'{(" · " + esc(cost["note"])) if cost.get("note") else ""} {src_link(cost["source"], "↗")}</span>'
                         if cost and cost.get("amount") else "")
            deep = (f'<a class="deep" href="{esc(c["deep_dive"])}">The full register: {esc(c["deep_dive_label"])} →</a>'
                    if c.get("deep_dive") else "")
            srcs = " · ".join(src_link(s["url"], s.get("publisher") or None) for s in c.get("sources", [])[:4])
            rows.append([
                td(f'<span class="pn">{num[c["id"]]}</span>', "nc"),
                td(f'<b id="c-{c["id"]}">{esc(c["name"])}</b><span class="dim pc">{esc(" · ".join(facts))}</span>'
                   f'<span class="sum">{esc(c.get("summary", ""))}</span>'
                   f'<span class="why"><b>Why it matters.</b> {esc(c.get("strategic", ""))}</span>'
                   f'{cost_html}<span class="tags">{tags}</span>{deep}<span class="srcs">{srcs}</span>', "pname"),
                td(f'{stage_strip(c["status"])}{st(c["status"])}<span class="dim m">{esc(c.get("status_date", ""))}</span>'
                   f'<span class="snote">{esc(c.get("status_note", ""))}</span>' + pieces_cell(c), "latest"),
                td(backer_cell(c), "who"),
            ])
    t = table(
        f"The {len(P)} corridors of the register, by region. The number is the marker's on the map. The bar "
        f"shows how far the corridor's main line has got: announced, approved, being built, in service; each "
        f"piece has its own stage beneath. Backers are coloured by kind; a link after each goes to its source.",
        ["No.", "Corridor", "Stage and pieces", "Who pays and who builds"], rows, cls="board")
    return t.replace("<tr><td colspan", '<tr class="grow"><td colspan')


def short_list(name):
    m = re.match(r"EU Global Gateway strategic corridor (\d+)", name)
    if m:
        return f"EU Global Gateway · corridor {m.group(1)}"
    for k, v in (("PIDA", "AU PIDA PAP2"), ("PGII", "G7 PGII"), ("Agenda 2063", "AU Agenda 2063"),
                 ("FOCAC", "China FOCAC"), ("Belt and Road", "China Belt and Road")):
        if k in name:
            return v
    return name if len(name) < 40 else name[:38] + "…"


def matrix(P, num):
    """Who is behind which corridor: one row per corridor, one column per
    kind of backer; a disc where it pays or owns, a ring where it only
    builds. Hover a cell for the names."""
    used = [g for g, _ in GROUPS if any(group_of(b.get("funder_country")) == g for c in P for b in c.get("backers", []))]
    head = "".join(f'<th class="mx-h"><span>{gdot(g)}{esc(G_NAME[g])}</span></th>' for g in used)
    rows = []
    for key, rname in REGIONS:
        group = [c for c in P if c["region"] == key]
        for c in group:
            tds = []
            for g in used:
                bs = [b for b in c.get("backers", []) if group_of(b.get("funder_country")) == g]
                if not bs:
                    tds.append('<td class="mx"></td>')
                    continue
                pays = any(b.get("role") in PAYS for b in bs)
                names = " · ".join(f'{b["name"]} ({ROLE.get(b.get("role"), b.get("role", ""))})' for b in bs)
                tds.append(f'<td class="mx" title="{esc(names)}"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
                           f'<circle cx="12" cy="12" r="7" class="{"sol" if pays else "hol"}" style="--c:var(--cf-{g})"></circle></svg>'
                           f'<span class="sr">{esc(names)}</span></td>')
            rows.append(f'<tr><td class="name"><span class="pn">{num[c["id"]]}</span>{esc(c["short"])}</td>{"".join(tds)}</tr>')
    return (f'<div class="tbl mxwrap"><table class="matrix"><caption>Who is behind which corridor. One row per '
            f'corridor, one column per kind of backer. A disc means it lends, gives, owns or holds the concession; '
            f'a ring means it only builds. Hover a cell for the names.</caption>'
            f'<thead><tr><th>Corridor</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


# -------------------------------------------------------------- the page

def build_page(reg, gem, rail):
    P = reg["corridors"]
    order = {k: i for i, (k, _) in enumerate(REGIONS)}
    for c in P:
        if c["status"] not in STATUS or any(s["status"] not in STATUS for s in c["segments"]):
            sys.exit(f"corridors: unknown status in {c['id']}")
        if c["region"] not in order:
            sys.exit(f"corridors: unknown region {c['region']!r} in {c['id']}")

    def west_to_east(c):
        pts = [p for s in c["segments"] for ln in seg_lines(s, gem, rail) for p in ln] or \
              [seg_point(s) for s in c["segments"] if seg_point(s)]
        return sum(p[0] for p in pts) / len(pts)
    P.sort(key=lambda c: (order[c["region"]], west_to_east(c)))
    num = {c["id"]: i + 1 for i, c in enumerate(P)}

    segs = [s for c in P for s in c["segments"]]
    by_status = {k: sum(1 for c in P if c["status"] == k) for k in STATUS}
    seg_status = {k: sum(1 for s in segs if s["status"] == k) for k in STATUS}
    backers = {b["name"] for c in P for b in c.get("backers", [])}
    nations = {cc for c in P for cc in c["countries"] if cc in NAMES}
    srcs = ({s["url"] for c in P for s in c.get("sources", [])} | {s["source"] for s in segs}
            | {b["source"] for c in P for b in c.get("backers", [])}
            | {c["cost"]["source"] for c in P if c.get("cost") and c["cost"].get("source")})
    china = [c for c in P if any(group_of(b.get("funder_country")) == "china" for b in c.get("backers", []))]
    west = [c for c in P if any(group_of(b.get("funder_country")) in ("us", "europe") and b.get("role") in PAYS
                                for b in c.get("backers", []))]
    eu_named = [c for c in P if any("EU Global Gateway" in n["list"] for n in c.get("named_by", []))]
    pays = lambda g: [c for c in P if any(group_of(b.get("funder_country")) == g and b.get("role") in PAYS
                                          for b in c.get("backers", []))]
    cn_lead = [s for c in P for s in c["segments"] if lead_group(c, s) == "china"]
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}

    tokens = {
        "__COMPILED__": fmt_date(reg["compiled"]), "__N_CORRIDORS__": str(len(P)),
        "__N_SEGMENTS__": str(len(segs)), "__N_COUNTRIES__": str(len(nations)),
        "__N_BACKERS__": str(len(backers)), "__N_SOURCES__": str(len(srcs)),
        "__N_CHINA__": str(len(china)), "__N_WEST__": str(len(west)), "__N_EU_NAMED__": str(len(eu_named)),
        "__N_US__": words.get(len(pays("us")), str(len(pays("us")))),
        "__N_EUROPE__": words.get(len(pays("europe")), str(len(pays("europe")))),
        "__CN_LEAD_PHRASE__": cn_phrase(cn_lead),
        **{f"__C_{k.upper()}__": str(v) for k, v in by_status.items()},
        **{f"__S_{k.upper()}__": str(v) for k, v in seg_status.items()},
        "__MAP_W__": f"{MAP_W:.0f}", "__MAP_H__": f"{MAP_H:.0f}",
        "__BASEMAP__": basemap(), "__MARKS__": map_marks(P, num, gem, rail), "__NODES__": node_svg(),
        "__SIDE_LIST__": side_list(P, num),
        "__MODE_KEY__": "".join(f'<span class="dk"><i class="mk-{k}"></i>{esc(n)}</span>' for k, n in MODES
                                if any(MODE_OF.get(s["mode"], "other") == k for s in segs)),
        "__STATUS_KEY__": "".join(f'<span class="dk"><i class="sk {k}"></i>{esc(n)}</span>' for k, n in STATUS.items()),
        "__GROUP_KEY__": "".join(f'<span class="dk"><i class="sk b-{g}"></i>{esc(n)}</span>' for g, n in GROUPS
                                 if any(lead_group(c, s) == g for c in P for s in c["segments"]))
                         + '<span class="dk"><i class="sk b-unknown"></i>Not known</span>',
        "__GROUP_LEGEND__": "".join(f'<span class="dk">{gdot(g)}{esc(n)}</span>' for g, n in GROUPS),
        "__STATUS_BOARD__": board(P, num), "__MATRIX__": matrix(P, num),
        "__OTHER_STATES__": esc(", ".join(sorted({CC.get(b["funder_country"], b["funder_country"]) for c in P
                                                  for b in c.get("backers", [])
                                                  if group_of(b.get("funder_country")) == "otherstate"},
                                                 key=str))) or "none",
    }
    for k, v in reg.get("prose", {}).items():     # figures the lede states, kept in the register
        tokens[f"__{k.upper()}__"] = esc(v)
    return tokens


def cn_phrase(cn_lead):
    """How many of the pieces with a Chinese lead funder are built: "all 13
    pieces it leads are", or "11 of the 13 pieces it leads are"."""
    built = sum(1 for s in cn_lead if s["status"] in ("operating", "under_construction"))
    if built == len(cn_lead):
        return f"all {len(cn_lead)} pieces it leads are"
    return f"{built} of the {len(cn_lead)} pieces it leads are"


OTHER_NAMES = {"TR": "Türkiye", "JP": "Japan", "KR": "South Korea", "IN": "India", "RU": "Russia",
               "SG": "Singapore", "CA": "Canada", "AU": "Australia", "BR": "Brazil", "MY": "Malaysia"}
CC.update(OTHER_NAMES)


def jsonld(path):
    page = {"@context": "https://schema.org", "@type": "WebPage", "@id": site_url(path), "url": site_url(path),
            "name": TITLE, "description": DESCRIPTION, "inLanguage": "en",
            "isPartOf": {"@type": "WebSite", "@id": site_url("#website"), "name": SITE_NAME, "url": SITE_URL},
            "author": {"@type": "Person", "name": AUTHOR_NAME, "url": WEB_URL, "sameAs": [AUTHOR_URL]},
            "about": {"@type": "Place", "name": "Africa"}}
    return ('<script type="application/ld+json">'
            + json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n")


NOINDEX = ('<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">',
           '<meta name="robots" content="noindex,nofollow">')


def build():
    reg, gem, rail = load()
    tokens = build_page(reg, gem, rail)
    tokens.update({"__TITLE__": esc(TITLE), "__DATA_URL__": site_url("data/corridors.json"),
                   "__DATA_FILE__": "corridors.json", "__BUILT__": fmt_date(today())})
    page = FRAME.read_text().replace("<!--__BODY__-->", FRAG.read_text(), 1)
    for k, v in tokens.items():
        page = page.replace(k, v)
    # the frame's own map script looks for #map; this page draws #cmap itself
    page = page.replace("/*__PAYLOAD__*/", json.dumps({"charts": {}}), 1)
    # "corridors" is in no menu, so the Deep dives menu marks nothing current
    page = brand_assets(page, donor=SLUG)
    left = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]*__", page)))
    if left:
        sys.exit(f"corridors: unfilled tokens {', '.join(left)}")
    path = f"{SLUG}/index.html"
    doc = wrap_document(page, title=TITLE, description=DESCRIPTION, path=path, kind="profile",
                        extra_head=jsonld(path))
    if NOINDEX[0] not in doc:
        sys.exit("corridors: the robots meta changed in shared.wrap_document; update NOINDEX")
    doc = doc.replace(*NOINDEX)
    (DOCS / SLUG).mkdir(parents=True, exist_ok=True)
    (DOCS / SLUG / "index.html").write_text(doc)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC, DOCS / "data" / SRC.name)
    print(f"→ docs/{path}  {len(doc.encode()) / 1024:.0f} KB  (+ docs/data/{SRC.name})")


if __name__ == "__main__":
    build()
