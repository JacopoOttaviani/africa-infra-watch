#!/usr/bin/env python3
"""
Render the link-preview image (Open Graph / Twitter card) for the site.

Reads   data/africa_basemap_10m.json  (coastlines; falls back to the 1:110m file)
        data/*.geojson via build_map   (the same three layers the map draws)
        brand/mark.svg                 (the compass-rose mark)
Writes  docs/social.png                1200 x 630, what Slack, WhatsApp, LinkedIn,
                                       iMessage and X show next to a shared link
        docs/icon-192.png, docs/apple-touch-icon.png
                                       the favicon as PNG, for Google's result
                                       favicon and home-screen icons

The picture is the map itself: every power unit, AfDB and World Bank project,
Chinese- and EU-financed project, Piano Mattei project and construction way over the region, in the status
palette, with the title on the left. It
is drawn as SVG and rasterised by a headless Chrome, which every Mac with Chrome
has and which renders the web fonts the pages use. Pass AIW_CHROME to point at
another Chromium binary; without any, the script warns and keeps the PNG that
is already committed.

WhatsApp only fetches preview images under about 300 KB, so the PNG is
palette-quantised (256 colours) when it comes out larger.
"""

import json
import math
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

from build_map import build_assets, build_finance, build_ground  # noqa: E402
from build_dashboard import build_china, build_eu, build_lookup, build_mattei  # noqa: E402
from region import REGION  # noqa: E402
from shared import (BANK, BRAND, DATA, DOCS, MAP_LAYERS, NUM_WORD, SITE_NAME, SITE_URL, SOCIAL_H, SOCIAL_IMAGE,  # noqa: E402
                    SOCIAL_W, china_span)

# one public dataset per source card, and the EU card is two (Commission and EIB)
N_DATASETS = NUM_WORD.get(len(MAP_LAYERS) + 1, str(len(MAP_LAYERS) + 1))

W, H = SOCIAL_W, SOCIAL_H
OUT = DOCS / SOCIAL_IMAGE

# Dark theme of the pages (map.template.html), so the card reads on the white
# and the dark chat backgrounds alike and the coloured records glow.
C = {
    "paper": "#0F1512", "land": "#1B231E", "ctx": "#141B17", "border": "#3D4A43",
    "ink": "#E6EBE6", "ink2": "#A8B4AC", "ink3": "#7E8C84", "accent": "#5FB495",
    "announced": "#B7810F", "approved": "#92A4FC", "under_construction": "#D44A98",
    "operating": "#67C98B", "stalled": "#6E7A75",
}
STATUS_LABEL = [("announced", "Announced"), ("approved", "Approved"),
                ("under_construction", "Under construction"), ("operating", "Operating"),
                ("stalled", "Stalled")]

# Map window (region.py): for Africa the continent, Madagascar and the Gulf of
# Aden coast, the far islands (Cabo Verde, Mauritius, Seychelles) outside, as
# on a postcard; for Southeast Asia the Andaman Sea to western New Guinea.
LON0, LON1, LAT0, LAT1 = REGION.social_win
MAP_X0, MAP_X1, MAP_Y0, MAP_Y1 = 590, 1185, 14, 616

CHROME_CANDIDATES = [
    os.environ.get("AIW_CHROME", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    shutil.which("google-chrome") or "", shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
]


def find_chrome():
    for c in CHROME_CANDIDATES:
        if c and pathlib.Path(c).exists():
            return c
    return None


# ------------------------------------------------------------ projection

def make_proj():
    """Plain equirectangular, as the dashboard uses: one scale for both axes,
    fitted to the window (its height for a tall region, its width for a wide
    one), the map centred in the other direction."""
    s = min((MAP_Y1 - MAP_Y0) / (LAT1 - LAT0), (MAP_X1 - MAP_X0) / (LON1 - LON0))
    w, h = (LON1 - LON0) * s, (LAT1 - LAT0) * s
    x0 = MAP_X0 + ((MAP_X1 - MAP_X0) - w) / 2
    y0 = MAP_Y0 + ((MAP_Y1 - MAP_Y0) - h) / 2
    return lambda lon, lat: (x0 + (lon - LON0) * s, y0 + (LAT1 - lat) * s), s


def ring_path(ring, proj):
    pts = []
    for lon, lat in ring:
        x, y = proj(lon, lat)
        pts.append(f"{x:.1f},{y:.1f}")
    return "M" + "L".join(pts) + "Z"


def poly_paths(p, proj):
    """A basemap country's `p` is a list of polygons, each a list of rings."""
    return " ".join(ring_path(ring, proj) for poly in p for ring in poly)


# ------------------------------------------------------------------ svg

def load_basemap():
    p10 = DATA / REGION.basemap_10m
    if p10.exists():
        return json.loads(p10.read_text())["countries"], True
    return json.loads((DATA / REGION.basemap_110).read_text())["countries"], False


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def star_path(x, y, d):
    """A five-pointed star of outer radius d, one point up, as an SVG path."""
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = d if i % 2 == 0 else d * 0.42
        pts.append(f"{x + rr * math.cos(a):.1f} {y + rr * math.sin(a):.1f}")
    return "M" + "L".join(pts) + "Z"


def hex_path(x, y, d):
    """A flat-topped hexagon of circumradius d, as an SVG path."""
    pts = [f"{x + d * math.cos(i * math.pi / 3):.1f} {y + d * math.sin(i * math.pi / 3):.1f}" for i in range(6)]
    return "M" + "L".join(pts) + "Z"


def draw(assets, finance, ground, china, eu, mattei, countries, is10m):
    proj, s = make_proj()
    out = []

    # -- land
    africa, ctx = [], []
    # the 10m basemap holds the whole world; only land that reaches the
    # card's window (with a margin) is worth a path
    lo0, lo1, la0, la1 = LON0 - 12, LON1 + 12, LAT0 - 8, LAT1 + 8
    near = lambda ring: any(lo0 <= x <= lo1 and la0 <= y <= la1 for x, y in ring)
    for c in countries:
        af = str(c.get("af", "1")) == "1" if is10m else True
        polys = c["p"] if af else [poly for poly in c["p"] if near(poly[0])]
        if polys:
            (africa if af else ctx).append(poly_paths(polys, proj))
    out.append(f'<clipPath id="win"><rect x="{MAP_X0}" y="{MAP_Y0}" width="{MAP_X1 - MAP_X0}" height="{MAP_Y1 - MAP_Y0}" rx="10"/></clipPath>')
    out.append('<g clip-path="url(#win)">')
    out.append(f'<g fill="{C["ctx"]}" stroke="{C["border"]}" stroke-width=".5" stroke-opacity=".5">'
               + "".join(f'<path d="{d}"/>' for d in ctx) + "</g>")
    out.append(f'<g fill="{C["land"]}" stroke="{C["border"]}" stroke-width=".6" stroke-linejoin="round">'
               + "".join(f'<path d="{d}"/>' for d in africa) + "</g>")

    # -- ground truth: the traced ways, drawn first so the points sit on top
    gi = {k: i for i, k in enumerate(ground["cols"])}
    lines = []
    for r in ground["rows"]:
        col = C.get(r[gi["status"]], C["stalled"])
        for g in r[gi["g"]]:
            pts = [proj(lon, lat) for lon, lat in g]
            d = "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            lines.append(f'<path d="{d}" stroke="{col}"/>')
    out.append('<g fill="none" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" opacity=".9">'
               + "".join(lines) + "</g>")

    # -- Chinese finance: triangles, by sqrt(commitment), biggest first
    ni = {k: i for i, k in enumerate(china["cols"])}
    tri = []
    for r in sorted(china["rows"], key=lambda r: -(r[ni["usd_m"]] or 0)):
        x, y = proj(r[ni["lon"]], r[ni["lat"]])
        d = min(7.5, 2.2 + math.sqrt(max(0, r[ni["usd_m"]] or 1)) * 0.2)
        col = C.get(r[ni["status"]], C["stalled"])
        tri.append(f'<path d="M{x:.1f} {y - d * 1.05:.1f}L{x + d * 1.08:.1f} {y + d * 0.75:.1f}'
                   f'L{x - d * 1.08:.1f} {y + d * 0.75:.1f}Z" fill="{col}"/>')
    out.append(f'<g opacity=".82" stroke="{C["paper"]}" stroke-width=".6">' + "".join(tri) + "</g>")

    # -- EU finance: five-pointed stars, by sqrt(commitment), biggest first
    ei = {k: i for i, k in enumerate(eu["cols"])}
    stars = []
    for r in sorted(eu["rows"], key=lambda r: -(r[ei["usd_m"]] or 0)):
        x, y = proj(r[ei["lon"]], r[ei["lat"]])
        d = min(8, 2.6 + math.sqrt(max(0, r[ei["usd_m"]] or 1)) * 0.2)
        col = C.get(r[ei["status"]], C["stalled"])
        stars.append(f'<path d="{star_path(x, y, d)}" fill="{col}"/>')
    out.append(f'<g opacity=".82" stroke="{C["paper"]}" stroke-width=".6" stroke-linejoin="round">' + "".join(stars) + "</g>")

    # -- Piano Mattei: hexagons, by sqrt(stated amount), biggest first
    mi = {k: i for i, k in enumerate(mattei["cols"])}
    hexes = []
    for r in sorted(mattei["rows"], key=lambda r: -(r[mi["usd_m"]] or 0)):
        x, y = proj(r[mi["lon"]], r[mi["lat"]])
        d = min(7.5, 2.4 + math.sqrt(max(0, r[mi["usd_m"]] or 1)) * 0.2)
        col = C.get(r[mi["status"]], C["stalled"])
        hexes.append(f'<path d="{hex_path(x, y, d)}" fill="{col}"/>')
    out.append(f'<g opacity=".82" stroke="{C["paper"]}" stroke-width=".6" stroke-linejoin="round">' + "".join(hexes) + "</g>")

    # -- finance: squares, side by sqrt(commitment), biggest first
    fi = {k: i for i, k in enumerate(finance["cols"])}
    sq = []
    for r in sorted(finance["rows"], key=lambda r: -(r[fi["usd_m"]] or 0)):
        x, y = proj(r[fi["lon"]], r[fi["lat"]])
        # a net commitment can be negative after cancellations (two World Bank
        # activities are): size those as the smallest square
        side = min(10, 3 + math.sqrt(max(0, r[fi["usd_m"]] or 1)) * 0.28)
        col = C.get(r[fi["status"]], C["stalled"])
        sq.append(f'<rect x="{x - side / 2:.1f}" y="{y - side / 2:.1f}" width="{side:.1f}" height="{side:.1f}" fill="{col}"/>')
    out.append(f'<g opacity=".82" stroke="{C["paper"]}" stroke-width=".6">' + "".join(sq) + "</g>")

    # -- assets: circles, radius by sqrt(MW), biggest first
    ai = {k: i for i, k in enumerate(assets["cols"])}
    ci = []
    for r in sorted(assets["rows"], key=lambda r: -(r[ai["mw"]] or 0)):
        x, y = proj(r[ai["lon"]], r[ai["lat"]])
        rad = min(9, 1.6 + math.sqrt(r[ai["mw"]] or 1) * 0.11)
        col = C.get(r[ai["status"]], C["stalled"])
        ci.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.1f}" fill="{col}"/>')
    out.append(f'<g opacity=".8" stroke="{C["paper"]}" stroke-width=".5">' + "".join(ci) + "</g>")
    out.append("</g>")   # clip

    # -- text column
    mark = (BRAND / "mark.svg").read_text().strip()
    mark = mark.replace('width="1em" height="1em"', 'width="46" height="46" x="64" y="52"', 1)
    mark = mark.replace('id="aiw-cut"', 'id="soc-cut"').replace('url(#aiw-cut)', 'url(#soc-cut)')
    out.append(f'<g color="{C["accent"]}">{mark}</g>')
    out.append(f'<text x="124" y="83" class="kicker">{esc(REGION.kicker)}</text>')

    # the two-colour wordmark (SITE_WORDMARK in shared.py), one word on one line:
    # "Africa" in the accent and "Watch" in the ink; other editions "Infra" in the ink
    # and "Radar" in the accent
    if REGION.key == "africa":
        # a tspan, since the .title rule's fill would beat a fill attribute on the text itself
        out.append(f'<text x="62" y="262" class="title"><tspan fill="{C["accent"]}">Africa</tspan>Watch</text>')
    else:
        out.append(f'<text x="62" y="262" class="title">Infra<tspan fill="{C["accent"]}">Radar</tspan></text>')
    out.append('<text x="64" y="400" class="sub">Announced, approved and ongoing projects across</text>')
    out.append(f'<text x="64" y="430" class="sub">{esc(REGION.land)}, from {N_DATASETS} public datasets.</text>')

    n_a, n_f, n_g, n_c, n_e = (len(assets["rows"]), len(finance["rows"]), len(ground["rows"]),
                               len(china["rows"]), len(eu["rows"]))
    y = 466
    for glyph, num, src in (
        ("circle", f"{n_a:,} power units", "Global Energy Monitor"),
        # two layers, two counts: the bank projects and the EU's own records are never added
        ("rect", f"{n_f:,} {BANK}, World Bank and AFD projects · {n_e:,} EU records"
         if any(r[finance["cols"].index("ln")] == "AFD" for r in finance["rows"])
         else f"{n_f:,} {BANK} and World Bank projects · {n_e:,} EU records", "via IATI"),
        ("tri", f"{n_c:,} Chinese-financed projects", f"AidData, {china_span()[0]}–{china_span()[1]}"),
        ("line", f"{n_g:,} construction works", "OpenStreetMap"),
    ):
        if glyph == "circle":
            out.append(f'<circle cx="72" cy="{y - 5}" r="6" fill="{C["operating"]}"/>')
        elif glyph == "rect":
            out.append(f'<rect x="66" y="{y - 11}" width="12" height="12" fill="{C["approved"]}"/>')
        elif glyph == "tri":
            out.append(f'<path d="M72 {y - 12}L79 {y + 1}H65Z" fill="{C["operating"]}"/>')
        else:
            out.append(f'<path d="M64 {y - 5}h16" stroke="{C["under_construction"]}" stroke-width="3.5" stroke-linecap="round"/>')
        out.append(f'<text x="92" y="{y}" class="num">{num}</text>'
                   f'<text x="92" y="{y + 18}" class="src">{esc(src)}</text>')
        y += 38

    # -- status legend under the map, and the address
    lx = MAP_X0 + 6
    out.append(f'<rect x="{MAP_X0}" y="{MAP_Y1 - 30}" width="{MAP_X1 - MAP_X0}" height="30" rx="8" fill="{C["paper"]}" opacity=".78"/>')
    for k, label in STATUS_LABEL:
        out.append(f'<circle cx="{lx + 10}" cy="{MAP_Y1 - 15}" r="4.5" fill="{C[k]}"/>')
        out.append(f'<text x="{lx + 20}" y="{MAP_Y1 - 11}" class="leg">{label}</text>')
        lx += 22 + len(label) * 7.1 + 18
    host = SITE_URL.replace("https://", "").replace("http://", "").rstrip("/")
    out.append(f'<text x="64" y="{H - 18}" class="url">{esc(host)}</text>')
    return "\n".join(out)


def page(svg_body):
    css = f"""
    @import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;800&family=Source+Serif+4:opsz,wght@8..60,400&family=IBM+Plex+Mono:wght@500;600&display=block');
    html,body{{margin:0;background:{C["paper"]};width:{W}px;height:{H}px;overflow:hidden}}
    svg{{display:block}}
    text{{fill:{C["ink"]}}}
    .kicker{{font:600 15px/1 "IBM Plex Mono",ui-monospace,Menlo,monospace;letter-spacing:.14em;text-transform:uppercase;fill:{C["accent"]}}}
    .title{{font:800 74px/1 "Archivo","Helvetica Neue",Arial,sans-serif;letter-spacing:-.025em;fill:{C["ink"]}}}
    .sub{{font:400 21px/1 "Source Serif 4",Georgia,serif;fill:{C["ink2"]}}}
    .num{{font:600 17px/1 "IBM Plex Mono",ui-monospace,Menlo,monospace;fill:{C["ink"]}}}
    .src{{font:500 12px/1 "Archivo","Helvetica Neue",Arial,sans-serif;fill:{C["ink3"]}}}
    .leg{{font:500 12px/1 "IBM Plex Mono",ui-monospace,Menlo,monospace;fill:{C["ink2"]}}}
    .url{{font:500 14px/1 "IBM Plex Mono",ui-monospace,Menlo,monospace;fill:{C["ink3"]}}}
    """
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<rect width="{W}" height="{H}" fill="{C["paper"]}"/>{svg_body}</svg></body></html>')


# ---------------------------------------------------------------- render

def rasterise(html, out, w=W, h=H, post=None):
    chrome = find_chrome()
    if not chrome:
        print("!! no Chrome/Chromium found (set AIW_CHROME); keeping the existing", out.name)
        return False
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "page.html"
        png = pathlib.Path(td) / "shot.png"
        src.write_text(html)
        cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--default-background-color=00000000",   # transparent corners on the icons
               f"--window-size={w},{h}", "--virtual-time-budget=8000",
               f"--screenshot={png}", src.as_uri()]
        # No --user-data-dir: a fresh profile makes Chrome hang on first run.
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            sys.exit("Chrome did not finish within 90 s")
        if not png.exists():
            print(res.stderr[-800:])
            sys.exit("Chrome produced no screenshot")
        (post or shrink)(png, out)
    return True


def icon_page(size):
    svg = (BRAND / "favicon.svg").read_text()
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;background:transparent}}'
            f'svg{{display:block;width:{size}px;height:{size}px}}</style></head><body>{svg}</body></html>')


def icons():
    """The favicon tile at 192 (Google, Android) and 180 (iOS home screen)."""
    for name, size in (("icon-192.png", 192), ("apple-touch-icon.png", 180)):
        out = DOCS / name
        if rasterise(icon_page(size), out, size, size, post=shutil.copy):
            print(f"→ {out.relative_to(ROOT)}  {size}x{size}, {out.stat().st_size / 1024:.0f} KB")


def shrink(png, out):
    """Keep the file under WhatsApp's ~300 KB preview ceiling: quantise to a
    256-colour palette when the truecolour PNG is bigger than that."""
    try:
        from PIL import Image
    except ImportError:
        shutil.copy(png, out)
        return
    im = Image.open(png).convert("RGB")
    if im.size != (W, H):
        im = im.crop((0, 0, W, H))
    im.save(out, optimize=True)
    if out.stat().st_size > 290_000:
        im.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG) \
          .save(out, optimize=True)


def main():
    print("layers  …")
    base110 = json.loads((DATA / REGION.basemap_110).read_text())
    idx = build_lookup(base110["countries"])
    assets, finance, ground = build_assets(), build_finance(), build_ground(idx)
    china = build_china(idx, simp=lambda part: [])     # markers only, no footprints
    eu = build_eu(idx)
    # the Piano Mattei layer is Africa's; an edition without it draws no hexagons
    mattei = build_mattei(idx) if "mattei" in REGION.layers else {"cols": [], "rows": []}
    countries, is10m = load_basemap()
    print("drawing …")
    html = page(draw(assets, finance, ground, china, eu, mattei, countries, is10m))
    DOCS.mkdir(exist_ok=True)
    if rasterise(html, OUT):
        print(f"→ {OUT.relative_to(ROOT)}  {W}x{H}, {OUT.stat().st_size / 1024:.0f} KB")
    icons()


if __name__ == "__main__":
    main()
