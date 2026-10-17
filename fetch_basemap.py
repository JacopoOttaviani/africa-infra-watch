#!/usr/bin/env python3
"""
Build the vector basemap for the interactive map from Natural Earth 1:10m.

Downloads (once, into a cache dir) the Natural Earth GeoJSON mirrors kept in
the nvkelso/natural-earth-vector repository and writes a single compact file:

    data/africa_basemap_10m.json          (AIW_REGION=sea: data/sea/sea_basemap_10m.json)

and, for an edition that has none yet, the coarse country file the dashboard
draws and the fetchers clip with (data/sea/sea_basemap.json): the region's
countries cut from the same 1:10m shapes and simplified hard, so that an
island state too small for Natural Earth 1:110m (Singapore) keeps a polygon.
Africa's data/africa_basemap.json predates this script and is kept as it is.

Layers kept, and why:
  countries   the whole world. The region in full detail; every other country as
              grey context, simplified harder, so wherever the map is panned
              there is land under it and a cable to India or a pipeline into
              Spain ends on a coast, not in open sea
  admin1      first-level subdivisions, the region only, for orientation when zoomed in
  lakes       the Rift lakes, Chad, Volta, Nasser, Kariba … in full; the large
              lakes of the rest of the world coarsely
  rivers      Nile, Congo, Niger, Zambezi, Orange … by Natural Earth scalerank;
              the rest of the world's major rivers coarsely
  places      capitals and cities with Natural Earth's own min_zoom threshold
  labels      one label anchor per country (Natural Earth LABEL_X/Y, MIN_LABEL)

Coordinates are rounded and Douglas-Peucker simplified; the page decimates
further per frame, so the file only needs to hold what a zoomed-in view can
resolve. Everything ships inline in the page: the publishing sandbox blocks
runtime requests, so there is no tile server to fall back on.
"""

import json
import math
import pathlib
import sys
import urllib.request

from region import REGION, ROOT_DATA  # noqa: E402

ROOT = pathlib.Path(__file__).parent
DATA = REGION.data_dir
# the Natural Earth download cache is shared by every edition
CACHE = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT_DATA / ".ne_cache"
OUT = DATA / REGION.basemap_10m
OUT_COARSE = DATA / REGION.basemap_110

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
FILES = {
    "countries": "ne_10m_admin_0_countries.geojson",
    "admin1": "ne_10m_admin_1_states_provinces.geojson",
    "lakes": "ne_10m_lakes.geojson",
    "rivers": "ne_10m_rivers_lake_centerlines.geojson",
    "places": "ne_10m_populated_places_simple.geojson",
}

# Detail window: the region plus enough margin that its neighbours (for
# Africa the Mediterranean, the Arabian peninsula and the Mascarene islands)
# are drawn with the same care. Water inside it is kept at full detail;
# outside, only the large features, coarsely. Land is kept everywhere.
WIN = REGION.win  # lon0, lat0, lon1, lat1

# The whole world in Web Mercator. Antarctica runs to the pole, which the
# projection cannot place, so land is clipped at the usual 85° parallels.
WORLD = (-180.0, -85.0, 180.0, 85.0)

# Natural Earth codes Somaliland "-99" and Western Sahara "EH". Keep both as
# drawn; the page labels them plainly rather than hiding the boundary source's
# choice.


def fetch(name):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / FILES[name]
    if not p.exists():
        print(f"   downloading {FILES[name]} …")
        urllib.request.urlretrieve(BASE + FILES[name], p)
    return json.loads(p.read_text())["features"]


# ------------------------------------------------------------ geometry utils

def dp(pts, tol):
    """Douglas-Peucker, iterative, in degrees."""
    n = len(pts)
    if n < 3:
        return list(pts)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        md, mi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if L == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / L
                t = 0.0 if t < 0 else 1.0 if t > 1 else t
                d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if d > md:
                md, mi = d, i
        if md > tol:
            keep[mi] = True
            stack.append((a, mi))
            stack.append((mi, b))
    return [p for p, k in zip(pts, keep) if k]


def rnd(pts, dp_=4):
    out = []
    for x, y in pts:
        q = [round(x, dp_), round(y, dp_)]
        if not out or out[-1] != q:
            out.append(q)
    return out


def clip_ring(ring, win):
    """Sutherland-Hodgman against an axis-aligned window (convex, so exact)."""
    x0, y0, x1, y1 = win

    def clip(pts, inside, intersect):
        out = []
        if not pts:
            return out
        prev = pts[-1]
        for cur in pts:
            if inside(cur):
                if not inside(prev):
                    out.append(intersect(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(intersect(prev, cur))
            prev = cur
        return out

    def ix(p, q, x):
        t = (x - p[0]) / (q[0] - p[0])
        return (x, p[1] + t * (q[1] - p[1]))

    def iy(p, q, y):
        t = (y - p[1]) / (q[1] - p[1])
        return (p[0] + t * (q[0] - p[0]), y)

    pts = [tuple(p) for p in ring]
    pts = clip(pts, lambda p: p[0] >= x0, lambda p, q: ix(p, q, x0))
    pts = clip(pts, lambda p: p[0] <= x1, lambda p, q: ix(p, q, x1))
    pts = clip(pts, lambda p: p[1] >= y0, lambda p, q: iy(p, q, y0))
    pts = clip(pts, lambda p: p[1] <= y1, lambda p, q: iy(p, q, y1))
    return pts


def touches(ring, win):
    x0, y0, x1, y1 = win
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in ring)


def polys(g):
    if g["type"] == "Polygon":
        return [g["coordinates"]]
    if g["type"] == "MultiPolygon":
        return g["coordinates"]
    return []


polys_of = polys


def lines(g):
    if g["type"] == "LineString":
        return [g["coordinates"]]
    if g["type"] == "MultiLineString":
        return g["coordinates"]
    return []


def ring_area(r):
    a = 0.0
    for i in range(len(r)):
        x0, y0 = r[i]
        x1, y1 = r[(i + 1) % len(r)]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


# ------------------------------------------------------------------ layers

def build_countries(feats):
    out, labels = [], []
    africa = set()
    for f in feats:
        p = f["properties"]
        # the region's own countries (for Africa, Natural Earth files Mauritius
        # and Seychelles under "Seven seas"; region.py knows)
        is_af = REGION.ne_member(p)
        iso = p["ISO_A2_EH"]
        # Bir Tawil is unclaimed land between Egypt and Sudan; keep the
        # polygon so there is no hole, but it is not a country to filter by.
        if p["NAME"] == "Bir Tawil":
            iso = ""
        rings_out = []
        for poly in polys(f["geometry"]):
            outer = poly[0]
            # near = context land inside the detail window (Europe, the
            # Middle East), drawn a little finer than the far side of the world
            near = is_af or touches(outer, WIN)
            new_poly = []
            for j, ring in enumerate(poly):
                r = ring if is_af else clip_ring(ring, WORLD)
                if len(r) < 4:
                    continue
                # tolerance and decimals go together: 0.03° needs no more
                # than two decimals (about 1 km) to hold what is left
                r = (rnd(dp(r, 0.0025)) if is_af else
                     rnd(dp(r, 0.01), 3) if near else rnd(dp(r, 0.03), 2))
                if len(r) >= 4 and (j == 0 or ring_area(r) > (0.0005 if near else 0.02)):
                    new_poly.append(r)
            if new_poly and (is_af or ring_area(new_poly[0]) > (0.02 if near else 0.1)):
                rings_out.append(new_poly)
        if not rings_out:
            continue
        if is_af:
            africa.add(p["ADM0_A3"])
        out.append({
            "iso": iso, "a3": p["ADM0_A3"], "n": p["NAME_EN"] or p["NAME"],
            "af": 1 if is_af else 0, "p": rings_out,
        })
        if is_af and iso and p.get("LABEL_X") is not None:
            labels.append({
                "iso": iso, "n": p["NAME"], "x": round(p["LABEL_X"], 2),
                "y": round(p["LABEL_Y"], 2), "z": p.get("MIN_LABEL", 3),
            })
    return out, labels, africa


def build_admin1(feats, africa):
    out = []
    for f in feats:
        p = f["properties"]
        if p["adm0_a3"] not in africa:
            continue
        rings = []
        for poly in polys(f["geometry"]):
            for ring in poly:
                r = rnd(dp(ring, 0.012), 3)
                if len(r) >= 4:
                    rings.append(r)
        if rings:
            out.append({"a3": p["adm0_a3"], "n": p["name_en"] or p["name"],
                        "x": round(p["longitude"], 2), "y": round(p["latitude"], 2),
                        "r": rings})
    return out


def build_lakes(feats):
    out = []
    for f in feats:
        p = f["properties"]
        for poly in polys(f["geometry"]):
            near = touches(poly[0], WIN)
            if not near and (ring_area(poly[0]) < 0.3 or p.get("scalerank", 9) > 3):
                continue   # far away: only the big ones (Baikal, the Great Lakes …)
            rings = [rnd(dp(r, 0.003)) if near else rnd(dp(r, 0.03), 2) for r in poly]
            rings = [r for r in rings if len(r) >= 4]
            if rings:
                out.append({"n": p.get("name_en") or p.get("name"),
                            "z": p.get("min_zoom", 5), "r": rings})
    return out


def build_rivers(feats):
    out = []
    for f in feats:
        p = f["properties"]
        for ln in lines(f["geometry"]):
            near = touches(ln, WIN)
            if not near and p.get("scalerank", 9) > 4:
                continue   # far away: only the great rivers
            pts = rnd(dp(ln, 0.004)) if near else rnd(dp(ln, 0.04), 2)
            if len(pts) >= 2:
                out.append({"n": p.get("name_en") or p.get("name"),
                            "s": p.get("scalerank", 9), "z": p.get("min_zoom", 6),
                            "c": pts})
    return out


def build_places(feats, africa):
    out = []
    for f in feats:
        p = f["properties"]
        if p["adm0_a3"] not in africa:
            continue
        cap = 1 if p["featurecla"].startswith("Admin-0 capital") else 0
        out.append({
            "n": p["name"], "iso": p["iso_a2"], "x": round(p["longitude"], 3),
            "y": round(p["latitude"], 3), "z": p.get("min_zoom", 7),
            "pop": p.get("pop_max") or 0, "cap": cap,
        })
    return out


def build_coarse(feats):
    """The region's countries for the dashboard and the fetchers' clipping,
    in the shape of data/africa_basemap.json ({"countries": [{"n", "iso",
    "p"}]}, polygons of rings of [lon, lat]): the 1:10m shapes simplified to
    about a kilometre and rounded to three decimals, keeping every polygon
    larger than about 50 km² and each country's largest whatever its size."""
    out = []
    for f in feats:
        p = f["properties"]
        if not REGION.ne_member(p) or not p["ISO_A2_EH"] or p["ISO_A2_EH"] == "-99":
            continue
        polys = []
        for poly in polys_of(f["geometry"]):
            rings = []
            for j, ring in enumerate(poly):
                r = rnd(dp(ring, 0.01), 3)
                if len(r) >= 4 and (j == 0 or ring_area(r) > 0.004):
                    rings.append(r)
            if rings:
                polys.append((ring_area(rings[0]), rings))
        if not polys:
            continue
        polys.sort(key=lambda x: -x[0])
        kept = [rings for a, rings in polys if a > 0.004] or [polys[0][1]]
        iso = p["ISO_A2_EH"]
        out.append({"n": REGION.display.get(iso, p["NAME_EN"] or p["NAME"]), "iso": iso, "p": kept})
    return out


def main():
    print("countries …")
    feats = fetch("countries")
    countries, labels, africa = build_countries(feats)
    print(f"   {len(countries)} countries, {sum(c['af'] for c in countries)} {REGION.adj}")
    if not OUT_COARSE.exists():
        coarse = build_coarse(feats)
        DATA.mkdir(parents=True, exist_ok=True)
        OUT_COARSE.write_text(json.dumps({"countries": coarse}, separators=(",", ":"), ensure_ascii=False))
        print(f"   → {OUT_COARSE.relative_to(ROOT)}: {len(coarse)} countries, "
              f"{sum(len(poly) for c in coarse for poly in c['p'])} rings, for the dashboard and the clipping")
    print("admin1 …")
    admin1 = build_admin1(fetch("admin1"), africa)
    print(f"   {len(admin1)} units")
    print("lakes …")
    lakes = build_lakes(fetch("lakes"))
    print(f"   {len(lakes)}")
    print("rivers …")
    rivers = build_rivers(fetch("rivers"))
    print(f"   {len(rivers)} segments")
    print("places …")
    places = build_places(fetch("places"), africa)
    print(f"   {len(places)} ({sum(p['cap'] for p in places)} capitals)")

    payload = {
        "src": "Natural Earth 1:10m, public domain",
        "win": WIN, "world": WORLD,
        "countries": countries, "labels": labels, "admin1": admin1,
        "lakes": lakes, "rivers": rivers, "places": places,
    }
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.write_text(blob)
    print(f"\n→ {OUT.relative_to(ROOT)}  {len(blob) / 1024:.0f} KB")
    for k in ("countries", "admin1", "lakes", "rivers", "places", "labels"):
        print(f"   {k:10s} {len(json.dumps(payload[k], separators=(',', ':'))) / 1024:6.0f} KB")


if __name__ == "__main__":
    main()
