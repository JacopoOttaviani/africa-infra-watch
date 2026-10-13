#!/usr/bin/env python3
"""
The map beside the opening text of every deep dive.

The pages on donor.template.html lay their head out as a grid: the kicker,
title and lede on the left, a small map on the right with one key figure
under it (the .headgrid / .locator styles live in the frame). Two kinds:

  lender_shape()  the outline of the lending country, or the members of a
                  bloc, from the committed Natural Earth 1:10m basemap
                  (data/africa_basemap_10m.json, which keeps every country of
                  the world). Orthographic, centred on the country, so Russia
                  and the United States keep their shape; the neighbours are
                  drawn faintly and fade out towards the edges.
  africa_map()    the continent from the 1:110m basemap, each country filled
                  with a CSS colour the caller picks (debt and comparison pages).

head_wrap() puts the figure into a page: it wraps the fragment's first
<div class="head"> and closes the grid before the first <dl class="kpis">, so
the prose files stay as they are. Corridors, Lobito and LAPSSET write their
own grid by hand and do not call it.
"""

import html
import json
import math
import re

from shared import DATA

W = 400                      # the lender map's width in SVG units; height follows the shape
PAD = 0.12                   # margin around the lender, as a share of its larger side
ASPECT = (0.6, 1.15)         # height / width, clamped so Russia is not a ribbon nor Norway a needle

# Overseas pieces left out of an outline, kept by the centroid of each polygon:
# lon0, lat0, lon1, lat1. France without Guiana, Réunion and Mayotte; Spain
# without the Canaries; Portugal without the Azores and Madeira; the United
# States as the contiguous 48; Norway without Svalbard.
KEEP = {"FRA": (-6, 41, 10, 52), "ESP": (-10, 35, 5, 45), "PRT": (-10, 36, -6, 43),
        "USA": (-126, 24, -66, 50), "NOR": (-180, -90, 180, 72)}

EU27 = ("AUT BEL BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN IRL ITA LVA LTU LUX MLT NLD POL PRT ROU "
        "SVK SVN ESP SWE").split()

# Each profile's countries, by ISO 3166 alpha-3 (the basemap's "a3").
PROFILE_SHAPES = {
    "russia": ["RUS"], "turkey": ["TUR"], "italy": ["ITA"], "china": ["CHN"], "usa": ["USA"],
    "germany": ["DEU"], "france": ["FRA"], "spain": ["ESP"], "japan": ["JPN"],
    "eu": EU27, "nordics": ["DNK", "FIN", "ISL", "NOR", "SWE"], "gulf": ["ARE", "KWT", "QAT", "SAU"],
}

_BM = {}


def _basemap(name):
    if name not in _BM:
        _BM[name] = json.loads((DATA / name).read_text())
    return _BM[name]


def esc(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------- geometry

def _centroid(ring):
    return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)


def _kept(country):
    """The polygons of a country that belong in its outline."""
    box = KEEP.get(country["a3"])
    if not box:
        return country["p"]
    out = []
    for poly in country["p"]:
        lon, lat = _centroid(poly[0])
        if box[0] <= lon <= box[2] and box[1] <= lat <= box[3]:
            out.append(poly)
    return out


def _ortho(lon0, lat0):
    """Orthographic projection on the unit sphere, y pointing down. Points on
    the far side are pushed onto the horizon, where the window clips them."""
    l0, p0 = math.radians(lon0), math.radians(lat0)
    sp0, cp0 = math.sin(p0), math.cos(p0)

    def f(lon, lat):
        lam, phi = math.radians(lon) - l0, math.radians(lat)
        cp = math.cos(phi)
        x = cp * math.sin(lam)
        y = cp0 * math.sin(phi) - sp0 * cp * math.cos(lam)
        if sp0 * math.sin(phi) + cp0 * cp * math.cos(lam) < 0:
            n = math.hypot(x, y) or 1.0
            x, y = x / n, y / n
        return x, -y
    return f


def _clip(ring, x0, y0, x1, y1):
    """Sutherland–Hodgman: a closed ring cut to the rectangle."""
    def cut(pts, inside, cross):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
        return out

    def at_x(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def at_y(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)
    pts = ring
    for inside, cross in ((lambda p: p[0] >= x0, at_x(x0)), (lambda p: p[0] <= x1, at_x(x1)),
                          (lambda p: p[1] >= y0, at_y(y0)), (lambda p: p[1] <= y1, at_y(y1))):
        if not pts:
            break
        pts = cut(pts, inside, cross)
    return pts


def _simplify(pts, eps):
    """Douglas–Peucker on a list of (x, y), iterative."""
    if len(pts) < 4:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        best, bi = 0.0, None
        for i in range(a + 1, b):
            px, py = pts[i]
            d = (abs(dy * px - dx * py + bx * ay - by * ax) / norm) if norm else math.hypot(px - ax, py - ay)
            if d > best:
                best, bi = d, i
        if bi is not None and best > eps:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def _d(rings):
    out = []
    for r in rings:
        out.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in r) + " Z")
    return " ".join(out)


# ------------------------------------------------------------ the lender map

def lender_shape(a3s, label):
    """An SVG of the countries in a3s filled, their neighbours faint behind."""
    bm = _basemap("africa_basemap_10m.json")
    mine = [c for c in bm["countries"] if c["a3"] in a3s]
    missing = set(a3s) - {c["a3"] for c in mine}
    assert not missing, f"not in the basemap: {sorted(missing)}"
    polys = [poly for c in mine for poly in _kept(c)]
    lons = [p[0] for poly in polys for p in poly[0]]
    lats = [p[1] for poly in polys for p in poly[0]]
    if max(lons) - min(lons) > 180:          # across the antimeridian (Russia's Chukotka)
        lons = [lo + 360 if lo < 0 else lo for lo in lons]
    proj = _ortho((min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2)

    xy = [proj(lo, la) for poly in polys for lo, la in poly[0]]
    x0, x1 = min(p[0] for p in xy), max(p[0] for p in xy)
    y0, y1 = min(p[1] for p in xy), max(p[1] for p in xy)
    pad = PAD * max(x1 - x0, y1 - y0)
    x0, x1, y0, y1 = x0 - pad, x1 + pad, y0 - pad, y1 + pad
    w, h = x1 - x0, y1 - y0
    if h / w < ASPECT[0]:
        grow = (ASPECT[0] * w - h) / 2
        y0, y1 = y0 - grow, y1 + grow
    elif h / w > ASPECT[1]:
        grow = (h / ASPECT[1] - w) / 2
        x0, x1 = x0 - grow, x1 + grow
    sc = W / (x1 - x0)
    H = round((y1 - y0) * sc)

    def rings_of(c, polys_, eps, clip):
        out = []
        for poly in polys_:
            for ring in poly:
                pts = [proj(lo, la) for lo, la in ring]
                bx0, bx1 = min(p[0] for p in pts), max(p[0] for p in pts)
                by0, by1 = min(p[1] for p in pts), max(p[1] for p in pts)
                if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
                    continue
                if clip:
                    pts = _clip(pts, x0, y0, x1, y1)
                pts = _simplify([((x - x0) * sc, (y - y0) * sc) for x, y in pts], eps)
                # islets under a pixel and a half add bytes, not shape
                if len(pts) >= 3 and (max(p[0] for p in pts) - min(p[0] for p in pts) > 1.5
                                      or max(p[1] for p in pts) - min(p[1] for p in pts) > 1.5):
                    out.append(pts)
        return out

    ctx, on = [], []
    for c in bm["countries"]:
        if c["a3"] in a3s:
            r = rings_of(c, _kept(c), 0.45, clip=False)
            if r:
                on.append(f'<path class="lc on" d="{_d(r)}"><title>{esc(c["n"])}</title></path>')
        else:
            r = rings_of(c, c["p"], 0.9, clip=True)
            if r:
                ctx.append(f'<path class="lc" d="{_d(r)}"><title>{esc(c["n"])}</title></path>')
    # the neighbours fade out towards the frame, so the cut at the edge does not show
    return (f'<svg class="loc shape" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">'
            f'<defs><radialGradient id="hm-fade" cx=".5" cy=".5" r=".62">'
            f'<stop offset=".55" stop-color="#fff"/><stop offset="1" stop-color="#000"/></radialGradient>'
            f'<mask id="hm-mask" maskContentUnits="userSpaceOnUse"><rect width="{W}" height="{H}" fill="url(#hm-fade)"/></mask></defs>'
            f'<g mask="url(#hm-mask)">{"".join(ctx)}</g>{"".join(on)}</svg>')


# ------------------------------------------------------------ the continent

AF_LON0, AF_LON1, AF_LAT0, AF_LAT1 = -18.5, 52.5, -35.5, 38.0
AF_SC = 5.0


def africa_map(fill, titles, label):
    """The continent with each country filled by fill[iso2] (a CSS colour,
    usually a var(--token)); the others plain land. titles[iso2] is the hover text."""
    bm = _basemap("africa_basemap.json")

    def xy(lon, lat):
        return (lon - AF_LON0) * AF_SC, (AF_LAT1 - lat) * AF_SC
    out = []
    for c in sorted(bm["countries"], key=lambda c: c["iso"] in fill):
        rings = []
        for poly in c["p"]:
            for ring in poly:
                pts = _simplify([xy(lo, la) for lo, la in ring], 0.35)
                if len(pts) >= 3:
                    rings.append(pts)
        style = f' style="fill:{fill[c["iso"]]}"' if c["iso"] in fill else ""
        cls = "lc on" if c["iso"] in fill else "lc"
        out.append(f'<path class="{cls}"{style} d="{_d(rings)}"><title>{esc(titles.get(c["iso"], c["n"]))}</title></path>')
    w, h = (AF_LON1 - AF_LON0) * AF_SC, (AF_LAT1 - AF_LAT0) * AF_SC
    return f'<svg class="loc afr" viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="{esc(label)}">{"".join(out)}</svg>'


# ------------------------------------------------------------ the figure

def figure(svg, big, text, keys=""):
    """The map and its key figure: one large number, a sentence under it, and
    optionally a row of colour keys."""
    return (f'<figure class="locator">{svg}<figcaption class="insight"><b class="ins-n m">{big}</b>'
            f'<span class="ins-t">{text}</span>{keys}</figcaption></figure>')


def head_wrap(frag, fig):
    """Put fig beside the fragment's head: the head and the figure share a grid
    that closes before the KPI row."""
    assert frag.count('<div class="head">') == 1, "expected one head"
    assert len(re.findall(r'<dl class="kpis">', frag)) >= 1, "expected a KPI row after the head"
    frag = frag.replace('<div class="head">', '<div class="headgrid">\n<div class="head">', 1)
    return frag.replace('<dl class="kpis">', f'{fig}\n</div>\n\n<dl class="kpis">', 1)


# ------------------------------------------------------------ the minerals figure

def minerals_figure(L, cname, floor=0.10):
    """The continent with every country that mines at least a tenth of the
    world's output of one of the page's minerals; L is build_minerals.latest()."""
    lead = {}
    for r in L.values():
        for iso, _, s in r["af"]:
            if s >= floor:
                lead.setdefault(iso, []).append((s, r["name"]))
    best = max(((s, iso, name) for iso, rows in lead.items() for s, name in rows), default=None)
    titles = {iso: f"{cname(iso)}: " + ", ".join(f"{n.lower()} {100 * s:.0f}%" for s, n in sorted(rows, reverse=True))
              for iso, rows in lead.items()}
    svg = africa_map({iso: "var(--copper)" for iso in lead}, titles,
                     f"Map of Africa with the {len(lead)} countries that mine a tenth or more of the world's output "
                     f"of at least one mineral shaded")
    text = (f"mine a tenth or more of the world's output of at least one of the {len(L)} minerals on this page. "
            "Hover a country for its shares.")
    if best:
        s, iso, name = best
        text += f" The largest: {esc(cname(iso))}, {100 * s:.0f}% of the world's {esc(name.lower())}."
    return figure(svg, f"{len(lead)} countries", text)


# ------------------------------------------------------------ the lender figure

# How each profile names the creditors its IDS series counts.
OWED_TO = {"russia": "Russian creditors", "turkey": "Turkish creditors", "italy": "Italian creditors",
           "china": "Chinese creditors", "usa": "American creditors", "germany": "German creditors",
           "france": "French creditors", "spain": "Spanish creditors", "japan": "Japanese creditors",
           "eu": "the European Investment Bank", "nordics": "Nordic creditors",
           "gulf": "creditors in the four Gulf states"}


def usd(v):
    return f"USD {v / 1e9:,.2f} bn" if v >= 1e9 else f"USD {v / 1e6:,.0f} m"   # as __IDS_STOCK_BN__ prints it


def lender_figure(slug, name, ids):
    """The outline of the lender and its headline debt figure, the same series
    (World Bank IDS, by counterpart) as the debt and comparison pages."""
    y = ids["data_to"]
    now = ids["continent"].get(str(y), 0)
    then_y = y - 10
    then = ids["continent"].get(str(then_y), 0)
    cs = [c for c in ids["countries"] if c["latest_year"] == y and c["latest_stock"] > 0]
    top = max(cs, key=lambda c: c["latest_stock"]) if cs else None
    bits = [f"owed to {OWED_TO[slug]} by {len(cs)} African government{'s' if len(cs) != 1 else ''} "
            f"at the end of {y}"]
    if then:
        word = "up" if now > then else "down"
        bits[0] += f", {word} from {usd(then)} in {then_y}."
    else:
        bits[0] += "."
    if top and now:
        bits.append(f"{esc(top['name'])} owes the most, {100 * top['latest_stock'] / now:.0f}% of it.")
    a3s = PROFILE_SHAPES[slug]
    what = {"eu": "the 27 member states of the European Union", "nordics": "the five Nordic countries",
            "gulf": "Saudi Arabia, the United Arab Emirates, Qatar and Kuwait",
            "usa": "the contiguous United States"}.get(slug, name)
    svg = lender_shape(a3s, f"Outline of {what}")
    return figure(svg, usd(now), " ".join(bits))
