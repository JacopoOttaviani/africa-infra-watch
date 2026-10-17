#!/usr/bin/env python3
"""
Build the minerals deep dive, docs/minerals/index.html: what Africa mines,
how much of the world's supply that is, where the deposits are, what is
left in the ground, where it is shipped, and the rare earths.

    python3 fetch_minerals.py        # data/minerals.json, data/minerals_sites.geojson
    python3 build_minerals.py        # the page

A DRAFT FOR REVIEW, NOT PUBLISHED. The page is in no menu, not in the
sitemap or llms.txt, refresh.py does not build it, and its <meta robots>
says noindex, nofollow. To publish it: add ("minerals", "Africa's
minerals", "...", "minerals.json") to DEEP_THEMES and the page to
write_site_index() in shared.py, add fetch_minerals.py and this script to
refresh.py, and drop the NOINDEX swap in build().

Sources (all official): the British Geological Survey's World Mineral
Statistics for production by country, 2000-2024 (full country coverage,
so Africa's share is a whole share; BGS asks for an acknowledgement and
allows non-commercial use); the USGS Mineral Commodity Summaries 2026 for
2025 production and reserves, and for lithium, tantalum and rare earths,
whose BGS tables mix ore and contained metal; two USGS deposit datasets for
the map; UN Comtrade for where the ores go; and a hand-kept register of the
continent's rare-earth projects, data/minerals_ree.json, every line with
the address it was read from.

Mines and plants: the USGS compilation of Africa's mineral industry (2021,
2018 reference year), read by `fetch_minerals.py facilities` from the
zip downloaded by hand into data/ (ScienceBase's bot check stops scripts):
data/minerals_facilities.geojson and data/minerals_exploration.geojson.
Their owners' home countries are this page's classification, kept by hand
in data/minerals_owners.json (one entry per owner name as the USGS spells
it; edit it there, and the chart and tooltips follow).

The page wears the lender profiles' frame (donor.template.html) and draws
its own SVG (#mmap, not #map, so the frame's map script leaves it alone).
It imports only pure helpers from build_lobito.py.
"""

import json
import math
import pathlib
import re
import shutil
import sys

from build_donors import FRAME, NAMES
from headmap import head_wrap, minerals_figure   # the map beside the head
from build_lobito import NOINDEX, clip_ring, esc, host, simplify, src_link
from shared import (AUTHOR_NAME, AUTHOR_URL, DATA, DOCS, SITE_NAME, SITE_URL, WEB_URL, brand_assets, fmt_date,
                    site_url, today, wrap_document)

ROOT = pathlib.Path(__file__).parent
SRC = DATA / "minerals.json"
SITES = DATA / "minerals_sites.geojson"
REE = DATA / "minerals_ree.json"
FACS = DATA / "minerals_facilities.geojson"         # fetch_minerals.py facilities (USGS 2021, by hand)
EXPS = DATA / "minerals_exploration.geojson"
OWNERS = DATA / "minerals_owners.json"              # owners' home countries, classified for this page
FRAG = ROOT / "sections" / "minerals.html"
SLUG = "minerals"
TITLE = "Africa's minerals"
DESCRIPTION = ("What Africa mines and how much of the world's supply it is, from cobalt, platinum and "
               "manganese to gold, diamonds and rare earths: production by country since 2000, a map of "
               "the deposits, what is left in the ground and where the ores are shipped, from official "
               "statistics (BGS, USGS, UN Comtrade).")

CC = dict(NAMES, EH="Western Sahara")
WORLD_NAMES = {"CN": "China", "RU": "Russia", "AU": "Australia", "CA": "Canada", "US": "United States",
               "ID": "Indonesia", "CL": "Chile", "PE": "Peru", "BR": "Brazil", "IN": "India", "KZ": "Kazakhstan",
               "TR": "Türkiye", "PH": "Philippines", "CU": "Cuba", "UZ": "Uzbekistan", "JO": "Jordan",
               "FI": "Finland", "MM": "Myanmar", "MX": "Mexico", "AR": "Argentina", "NC": "New Caledonia",
               "SE": "Sweden", "UA": "Ukraine", "NO": "Norway", "VN": "Vietnam", "MY": "Malaysia",
               "PG": "Papua New Guinea", "KP": "North Korea", "PT": "Portugal", "BO": "Bolivia",
               "LA": "Laos", "TH": "Thailand", "IR": "Iran", "SA": "Saudi Arabia", "GL": "Greenland",
               "JM": "Jamaica", "FR": "France", "GG": "Guernsey", "LU": "Luxembourg", "KR": "South Korea",
               "JP": "Japan", "GB": "United Kingdom", "AE": "United Arab Emirates", "IE": "Ireland",
               "SG": "Singapore", "QA": "Qatar", "DE": "Germany", "BE": "Belgium", "CH": "Switzerland",
               "IL": "Israel", "HK": "Hong Kong", "NL": "Netherlands", "PK": "Pakistan", "IT": "Italy",
               "ES": "Spain", "PL": "Poland", "TW": "Taiwan", "EU": "European Union", "AT": "Austria"}


def cname(iso):
    return CC.get(iso) or WORLD_NAMES.get(iso) or iso


# ------------------------------------------------------------- formatting

def pct(x, dp=None):
    """A share as the page writes it: 77%, 4.5%, 0.4%, under 0.1%."""
    if x is None:
        return "n/a"
    v = x * 100
    if v == 0:
        return "0%"
    if v < 0.1:
        return "under 0.1%"
    if dp is not None:
        return f"{v:.{dp}f}%"
    return f"{v:.0f}%" if v >= 9.5 else f"{v:.1f}%"


def qty(v, unit):
    """A quantity with its unit, kept readable: 268,547 t, 4.1 Mt, 179,984 kg."""
    if v is None:
        return "n/a"
    if unit.startswith("t") and v >= 1e6:
        return f"{v / 1e6:,.1f} million {unit}"
    if unit == "carats" and v >= 1e6:
        return f"{v / 1e6:,.1f} million carats"
    if unit == "kg" and v >= 1000:
        return f"{v / 1000:,.1f} t"
    return f"{v:,.0f} {unit}"


def usd(v):
    if v >= 1e9:
        return f"USD {v / 1e9:,.1f} bn"
    if v >= 1e6:
        return f"USD {v / 1e6:,.0f} m"
    return f"USD {v / 1e3:,.0f} k"


WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
         11: "eleven", 12: "twelve"}


# ------------------------------------------------------------- the numbers

def load_layer(path):
    return json.loads(path.read_text())["features"] if path.exists() else []


def load():
    pack = json.loads(SRC.read_text())
    sites = json.loads(SITES.read_text())["features"]
    ree = json.loads(REE.read_text()) if REE.exists() else None
    return pack, sites, ree, load_layer(FACS), load_layer(EXPS), \
        (json.loads(OWNERS.read_text()) if OWNERS.exists() else None)


def latest(pack):
    """Each mineral's latest year, the world's output and every named
    producer's share of it: BGS where it is whole, USGS 2025 otherwise."""
    out = {}
    for m in pack["minerals"]:
        k = m["key"]
        if m["src"] == "usgs":
            u = pack["mcs"]["minerals"][k]
            world = u["world_prod"]
            vals = dict(u["prod"])
            year, src = u["year"], "USGS"
            note = ("USGS names only the larger producers; "
                    f"{pct(u['other_prod'] / world)} of world output is under \"other countries\"."
                    if u.get("other_prod") else "")
        else:
            b = pack["bgs"]["minerals"][k]
            world = b["world"][-1]
            vals = {iso: s[-1] for iso, s in b["countries"].items() if s[-1]}
            year, src, note = b["years"][-1], "BGS", ""
        share = {iso: v / world for iso, v in vals.items()}
        af = sorted(((iso, vals[iso], share[iso]) for iso in vals if iso in CC), key=lambda t: -t[1])
        top = sorted(share.items(), key=lambda kv: -kv[1])[:5]
        out[k] = dict(m, year=year, src=src, world=world, af=af, africa=sum(s for _, _, s in af),
                      top=top, note=note)
    return out


def trends(pack, L):
    """Africa's share of world output, year by year, for the BGS minerals."""
    out = {}
    for m in pack["minerals"]:
        if m["src"] != "bgs":
            continue
        b = pack["bgs"]["minerals"][m["key"]]
        ys = b["years"]
        sh = [round(a / w, 4) if w else None for a, w in zip(b["africa"], b["world"])]
        lead = []
        for i in range(len(ys)):
            best = max(((s[i], iso) for iso, s in b["countries"].items() if iso in CC), default=(0, None))
            lead.append([best[1], round(best[0] / b["world"][i], 4) if b["world"][i] else 0])
        out[m["key"]] = {"years": ys, "share": sh, "lead": lead}
    return out


# ------------------------------------------------------------- projection

# The continent, Dakar to Cape Guardafui and Tunis to the Cape: the same
# window as the corridors page.
LON0, LON1, LAT0, LAT1 = -18.5, 52.5, -35.4, 38.2
MAP_W = 980.0
SC = MAP_W / (LON1 - LON0)
MAP_H = (LAT1 - LAT0) * SC


def xy(lon, lat):
    return round((lon - LON0) * SC, 1), round((LAT1 - lat) * SC, 1)


def path_d(lines, closed=False, eps=0.6):
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
        if not d:
            continue
        if c["iso"] in CC:
            out.append(f'<path class="land c" data-iso="{c["iso"]}" d="{d}"></path>')
        else:
            out.append(f'<path class="land ctx" d="{d}"><title>{esc(c["n"])}</title></path>')
    for lk in bm["lakes"]:
        xs = [x for ring in lk["r"] for x, _ in ring]
        ys = [y for ring in lk["r"] for _, y in ring]
        if in_window(sum(xs) / len(xs), sum(ys) / len(ys), 0) and max(max(xs) - min(xs), max(ys) - min(ys)) > 0.9:
            out.append(f'<path class="lake" d="{path_d(lk["r"], closed=True)}"></path>')
    for name, lon, lat in SEAS:
        x, y = xy(lon, lat)
        out.append(f'<text class="sea" x="{x}" y="{y}" text-anchor="middle">{esc(name)}</text>')
    return "\n".join(out)


# ------------------------------------------------------------------ the map

# The map's minerals: the chip, the mineral whose output shades the
# countries, and the deposit key its points carry.
MAP_CHIPS = [
    ("cobalt", "Cobalt", "cobalt"), ("copper", "Copper", "copper"), ("pgm", "Platinum group", "platinum"),
    ("manganese", "Manganese", "manganese"), ("chromium", "Chromium", "chromium"), ("gold", "Gold", "gold"),
    ("diamond", "Diamonds", "diamond"), ("bauxite", "Bauxite", "bauxite"), ("iron", "Iron ore", "iron"),
    ("phosphate", "Phosphate", "phosphate"), ("titanium", "Titanium", "titanium"), ("zircon", "Zircon", "zircon"),
    ("lithium", "Lithium", "lithium"), ("graphite", "Graphite", "graphite"), ("tantalum", "Tantalum", "tantalum"),
    ("tin", "Tin", "tin"), ("ree", "Rare earths", "ree"), ("uranium", "Uranium", "uranium"),
    ("vanadium", "Vanadium", "vanadium"), ("nickel", "Nickel", "nickel"),
]
STEPS = [0.01, 0.05, 0.15, 0.40]            # share of world output: under 1%, 1-5, 5-15, 15-40, 40+
ALL_STEPS = [2, 4, 6, 9]                    # minerals with 1% or more: 1, 2-3, 4-5, 6-8, 9+


def number(feats):
    """Number a layer's points in drawing order (north to south), dropping
    those outside the map; the payload's lists follow the same numbers."""
    out = []
    for f in sorted(feats, key=lambda f: -f["geometry"]["coordinates"][1]):
        f["properties"].pop("_i", None)
        if in_window(*f["geometry"]["coordinates"], 0):
            f["properties"]["_i"] = len(out)
            out.append(f)
    return out


def map_marks(sites, facs, exps):
    """Three layers, one shown at a time: mines and plants (USGS 2021, the
    default when the file is there), deposits, exploration projects. The
    groups are empty here: the page's script draws the marks from
    map_points(), which keeps the page a quarter of a megabyte lighter."""
    out = []
    if facs:
        out.append('<g id="g-fac" data-layer="fac"></g>')
    out.append(f'<g id="g-dep" data-layer="dep"{" hidden" if facs else ""}></g>')
    if exps:
        out.append('<g id="g-exp" data-layer="exp" hidden></g>')
    return "\n".join(out)


def map_points(sites, facs, exps):
    """[x, y, minerals, kind] per site, in each layer's numbering."""
    pts = {}
    for lay, feats in (("fac", facs), ("dep", sites), ("exp", exps)):
        rows = []
        for f in feats:
            x, y = xy(*f["geometry"]["coordinates"])
            p = f["properties"]
            rows.append([x, y, " ".join(p["minerals"]), "p" if p.get("kind") == "plant" else "m"])
        if rows:
            pts[lay] = rows
    return pts


def fac_tip(p, owners_home):
    items = []
    for it in p["items"]:
        cap = ""
        if it["capacity"]:
            cap = f'{it["capacity"]:,.0f} {it["unit"].lower()}'.strip() + (" (shared)" if it["shared"] else "")
        items.append([it["commodity"] + (f' ({it["product"].lower()})' if it["product"] and it["product"] != "Mine" else ""), cap])
    own = [[o["name"], o["stake"], owners_home.get(o["name"])] for o in p["owners"][:5]]
    return [p["name"], p["iso"], p["kind"], p["status"], p["year"], p["operator"], own, items,
            1 if p.get("approx") else 0]


def map_payload(L, sites, facs, exps, owners_home):
    val = {}
    for chip, _, key in MAP_CHIPS:
        val[chip] = {iso: round(s, 5) for iso, _, s in L[key]["af"]}
    allc = {}
    for k, r in L.items():
        if k in COUNT_ONCE:
            continue
        for iso, _, s in r["af"]:
            if s >= 0.01:
                allc.setdefault(iso, []).append([r["name"], round(s, 4)])
    for v in allc.values():
        v.sort(key=lambda t: -t[1])
    deps = []
    for f in sites:
        p = f["properties"]
        also = p.get("also")
        # an OFR record's address is its number; PP 1802 has one address for all
        url = p["url"]
        rec = url.split("rec_id=")[1] if "rec_id=" in url else ""
        deps.append([p["name"], p["commodity"], p.get("type") or "", p["src"], rec, p["iso"],
                     also["name"] if also and also["name"] != p["name"] else ""])
    count = {lay: {chip: sum(1 for f in feats if chip in f["properties"]["minerals"]) for chip, _, _ in MAP_CHIPS}
             for lay, feats in (("dep", sites), ("fac", facs), ("exp", exps))}
    for lay, feats in (("dep", sites), ("fac", facs), ("exp", exps)):
        count[lay]["all"] = len(feats)
    return {"chips": [[c, n, k] for c, n, k in MAP_CHIPS], "val": val, "all": allc, "deps": deps,
            "pts": map_points(sites, facs, exps),
            "facs": [fac_tip(f["properties"], owners_home) for f in facs],
            "exps": [[f["properties"][k] for k in ("name", "iso", "stage", "commodity", "owner", "share", "verified")]
                     for f in exps],
            "count": count, "steps": STEPS, "allSteps": ALL_STEPS}


def chip_html():
    out = ['<button type="button" class="mchip" data-c="all" aria-pressed="true">All minerals</button>']
    out += [f'<button type="button" class="mchip" data-c="{c}" aria-pressed="false">{esc(n)}</button>'
            for c, n, _ in MAP_CHIPS]
    return "".join(out)


# ------------------------------------------------------- the share chart

FAM_NAME = {"battery": "Batteries, grids", "pgm": "Platinum group", "steel": "Steel, alloys",
            "tech": "Electronics, magnets", "sands": "Mineral sands", "ores": "Bulk ores",
            "precious": "Precious", "energy": "Nuclear fuel"}
# palladium and rhodium come with platinum: counted once, as platinum, when
# the page counts a country's minerals
COUNT_ONCE = ("palladium", "rhodium")


def share_countries(L, n=7):
    """The countries the share chart colours: Africa's largest producer of at
    least one mineral, the n with the largest summed share. Every other
    African producer is one grey; the colour follows the country in every
    row, and the bars stack them in this order."""
    total, leads = {}, set()
    for r in L.values():
        for i, (iso, _, s) in enumerate(r["af"]):
            total[iso] = total.get(iso, 0) + s
            if i == 0:
                leads.add(iso)
    return sorted(leads, key=lambda iso: -total[iso])[:n]


def share_key(L):
    named = share_countries(L)
    return ("".join(f'<span class="dk"><i class="gk" style="background:var(--sc-{i + 1})"></i>{esc(cname(iso))}</span>'
                    for i, iso in enumerate(named))
            + '<span class="dk"><i class="gk" style="background:var(--sc-other)"></i>Other African countries</span>'
            + '<span class="dk"><i class="gk" style="background:var(--surface-2);box-shadow:inset 0 0 0 1px var(--rule)">'
              '</i>Rest of the world</span>')


def share_chart(L):
    rows = sorted(L.values(), key=lambda r: -r["africa"])
    named = share_countries(L)
    slot = {iso: i + 1 for i, iso in enumerate(named)}
    W, LAB, BAR, RH = 980, 186, 556, 34
    H = RH * len(rows) + 30
    x0 = LAB
    out = [f'<svg id="sharechart" viewBox="0 0 {W} {H}" role="img" aria-label="Africa\'s share of world mine '
           f'production for {len(rows)} minerals, by producing country">']
    for g in (0, 0.25, 0.5, 0.75, 1):
        gx = x0 + BAR * g
        out.append(f'<line class="sgrid" x1="{gx:.1f}" x2="{gx:.1f}" y1="18" y2="{H - 6}"></line>'
                   f'<text class="ax" x="{gx:.1f}" y="11" text-anchor="middle">{int(g * 100)}%</text>')
    for i, r in enumerate(rows):
        y = 22 + i * RH
        out.append(f'<g class="srow" data-k="{r["key"]}" tabindex="0">')
        out.append(f'<rect class="shit" x="0" y="{y - 4}" width="{W}" height="{RH}"></rect>')
        out.append(f'<text class="sname" x="0" y="{y + 11}">{esc(r["name"])}</text>'
                   f'<text class="sfam" x="0" y="{y + 23}">{esc(FAM_NAME[r["fam"]])} · {r["src"]} {r["year"]}</text>')
        out.append(f'<rect class="strack" x="{x0}" y="{y + 3}" width="{BAR}" height="16" rx="2"></rect>')
        x = x0
        # the coloured countries first, always in the same order, then the rest by size
        segs = sorted(r["af"], key=lambda t: (slot.get(t[0], 99), -t[2]))
        for iso, _, s in segs:
            w = BAR * s
            if w < 0.6:
                continue
            gap = 2 if w > 3 else 0
            fill = f"var(--sc-{slot[iso]})" if iso in slot else "var(--sc-other)"
            out.append(f'<rect class="sseg" x="{x:.1f}" y="{y + 3}" width="{max(w - gap, 0.6):.1f}" height="16" '
                       f'rx="1.5" style="fill:{fill}"></rect>')
            lab = cname(iso) if w > 8 * len(cname(iso)) + 8 else (iso if w > 22 else "")
            if lab:
                out.append(f'<text class="slab" x="{x + 5:.1f}" y="{y + 15}">{esc(lab)}</text>')
            x += w
        lead = r["af"][0] if r["af"] else None
        tail = f'{esc(cname(lead[0]))} {pct(lead[2])}' if lead else ""
        out.append(f'<text class="sval" x="{x0 + BAR + 14}" y="{y + 15}"><tspan class="sbig">{pct(r["africa"])}</tspan>'
                   f'<tspan dx="8">{tail}</tspan></text>')
        out.append("</g>")
    out.append("</svg>")
    return "".join(out), [r["key"] for r in rows]


def share_payload(L):
    return {k: {"name": r["name"], "unit": r["unit"], "year": r["year"], "src": r["src"], "world": r["world"],
                "africa": round(r["africa"], 4), "note": r["note"],
                "af": [[iso, v, round(s, 5)] for iso, v, s in r["af"]],
                "top": [[iso, round(s, 4)] for iso, s in r["top"]]} for k, r in L.items()}


def share_table(L):
    rows = sorted(L.values(), key=lambda r: -r["africa"])
    body = []
    for r in rows:
        prods = ", ".join(f"{cname(iso)} {pct(s)}" for iso, _, s in r["af"][:6])
        more = len(r["af"]) - 6
        if more > 0:
            prods += f" and {more} more"
        body.append(f'<tr><td class="name">{esc(r["name"])}</td><td class="num">{pct(r["africa"])}</td>'
                    f'<td>{esc(prods) or "–"}</td><td class="num">{esc(qty(r["world"], r["unit"]))}</td>'
                    f'<td>{r["src"]} {r["year"]}</td></tr>')
    return ('<div class="tbl"><table><caption>Africa\'s share of world mine production, by mineral and '
            'producing country</caption><thead><tr><th>Mineral</th><th class="num">Africa</th>'
            '<th>African producers (share of world)</th><th class="num">World output</th><th>Source</th></tr>'
            f'</thead><tbody>{"".join(body)}</tbody></table></div>')


# ----------------------------------------------------- the trend panels

TREND_KEYS = ["cobalt", "platinum", "manganese", "chromium", "bauxite", "titanium", "gold", "diamond",
              "copper", "graphite", "uranium", "phosphate"]


def trend_panels(L, T):
    W, H, PL, PR, PT, PB = 300, 150, 30, 40, 12, 22
    out = []
    for k in TREND_KEYS:
        t = T[k]
        ys, sh = t["years"], t["share"]
        y0, y1 = ys[0], ys[-1]
        X = lambda y: PL + (y - y0) / (y1 - y0) * (W - PL - PR)
        Y = lambda s: PT + (1 - s) * (H - PT - PB)
        pts = [(X(y), Y(s)) for y, s in zip(ys, sh) if s is not None]
        line = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        area = line + f" L{pts[-1][0]:.1f} {Y(0):.1f} L{pts[0][0]:.1f} {Y(0):.1f} Z"
        grid = "".join(f'<line x1="{PL}" x2="{W - PR}" y1="{Y(g):.1f}" y2="{Y(g):.1f}"></line>' for g in (0, .5, 1))
        axy = "".join(f'<text class="ax" x="{PL - 5}" y="{Y(g) + 3.5:.1f}" text-anchor="end">{int(g * 100)}%</text>'
                      for g in (0, .5, 1))
        axx = (f'<text class="ax" x="{X(y0):.1f}" y="{H - 6}" text-anchor="start">{y0}</text>'
               f'<text class="ax" x="{X(y1):.1f}" y="{H - 6}" text-anchor="end">{y1}</text>')
        lx, ly = pts[-1]
        r = L[k]
        lead = t["lead"][-1]
        sub = (f'{pct(sh[0])} in {y0}, {pct(sh[-1])} in {y1}. Largest African producer: '
               f'{cname(lead[0])}, {pct(lead[1])} of world output.')
        out.append(
            f'<figure class="chart tp" data-k="{k}"><h3>{esc(r["name"])}</h3><p class="sub">{esc(sub)}</p>'
            f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Africa\'s share of world {esc(r["name"].lower())} '
            f'output, {y0} to {y1}: {esc(sub)}"><g class="grid">{grid}</g>{axy}{axx}'
            f'<path class="area" d="{area}"></path><path class="series" d="{line}"></path>'
            f'<circle class="tend" cx="{lx:.1f}" cy="{ly:.1f}" r="3.5"></circle>'
            f'<text class="tval" x="{lx + 6:.1f}" y="{ly + 4:.1f}">{pct(sh[-1])}</text>'
            f'<line class="xh" x1="0" x2="0" y1="{PT}" y2="{Y(0):.1f}"></line>'
            f'<circle class="xd" r="4" cx="-10" cy="-10"></circle>'
            f'<rect class="thit" x="{PL}" y="{PT}" width="{W - PL - PR}" height="{H - PT - PB}" '
            f'data-x0="{PL}" data-x1="{W - PR}" data-pt="{PT}" data-h="{H - PT - PB}"></rect></svg>'
            f'<div class="tip ttip"></div></figure>')
    return "".join(out)


# ----------------------------------------------------- reserves vs output

RES_KEYS = ["platinum", "phosphate", "cobalt", "manganese", "chromium", "diamond", "bauxite", "graphite",
            "titanium", "zircon", "copper", "tin", "gold", "iron", "lithium", "vanadium", "ree"]
RES_NAME = {"platinum": "Platinum-group metals", "diamond": "Industrial diamonds", "titanium": "Titanium (ilmenite)",
            "zircon": "Zircon"}


def reserves_rows(pack, L):
    mcs = pack["mcs"]["minerals"]
    rows = []
    for k in RES_KEYS:
        u = mcs[k]
        if not u.get("world_res") or u.get("africa_res") is None:
            continue
        rows.append({"key": k, "name": RES_NAME.get(k, L[k]["name"]),
                     "prod": u["africa_prod"] / u["world_prod"], "res": u["africa_res"] / u["world_res"],
                     "res_af": {iso: v for iso, v in u["res"].items() if iso in CC},
                     "world_res": u["world_res"], "res_unit": u["res_unit"], "prod_unit": u["prod_unit"],
                     "other_res": u.get("other_res")})
    rows.sort(key=lambda r: -r["res"])
    return rows


def reserves_chart(rows):
    W, LAB, BAR, RH = 980, 190, 600, 30
    H = RH * len(rows) + 34
    x0 = LAB
    out = [f'<svg id="reschart" viewBox="0 0 {W} {H}" role="img" aria-label="Africa\'s share of world reserves '
           f'and of world mine production in 2025, for {len(rows)} minerals">']
    for g in (0, 0.25, 0.5, 0.75, 1):
        gx = x0 + BAR * g
        out.append(f'<line class="sgrid" x1="{gx:.1f}" x2="{gx:.1f}" y1="18" y2="{H - 6}"></line>'
                   f'<text class="ax" x="{gx:.1f}" y="11" text-anchor="middle">{int(g * 100)}%</text>')
    for i, r in enumerate(rows):
        y = 30 + i * RH
        xp, xr = x0 + BAR * r["prod"], x0 + BAR * r["res"]
        a, b = sorted((xp, xr))
        out.append(f'<g class="rrow" data-k="{r["key"]}" tabindex="0">'
                   f'<rect class="shit" x="0" y="{y - 13}" width="{W}" height="{RH}"></rect>'
                   f'<text class="sname" x="0" y="{y + 4}">{esc(r["name"])}</text>'
                   f'<line class="rlink" x1="{a:.1f}" x2="{b:.1f}" y1="{y}" y2="{y}"></line>'
                   f'<circle class="rp" cx="{xp:.1f}" cy="{y}" r="5"></circle>'
                   f'<circle class="rr" cx="{xr:.1f}" cy="{y}" r="5"></circle>'
                   f'<text class="sval" x="{x0 + BAR + 14}" y="{y + 4}">{pct(r["res"])} of reserves'
                   f'<tspan class="dim" dx="8">{pct(r["prod"])} of output</tspan></text></g>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------- where it goes

def trade_chart(pack):
    tr = pack["trade"]
    groups = [g["id"] for g in tr["groups"]]
    rows = sorted(tr["minerals"].items(), key=lambda kv: -sum(kv[1]["total"].values()))
    W, LAB, BAR, RH = 980, 178, 600, 34
    H = RH * len(rows) + 30
    x0 = LAB
    out = [f'<svg id="tradechart" viewBox="0 0 {W} {H}" role="img" aria-label="Where Africa\'s mineral exports '
           f'went in {tr["year"]}, by destination, for {len(rows)} minerals">']
    for g in (0, 0.25, 0.5, 0.75, 1):
        gx = x0 + BAR * g
        out.append(f'<line class="sgrid" x1="{gx:.1f}" x2="{gx:.1f}" y1="18" y2="{H - 6}"></line>'
                   f'<text class="ax" x="{gx:.1f}" y="11" text-anchor="middle">{int(g * 100)}%</text>')
    for i, (k, m) in enumerate(rows):
        y = 22 + i * RH
        tot = sum(m["total"].values())
        out.append(f'<g class="trow" data-k="{k}" tabindex="0">'
                   f'<rect class="shit" x="0" y="{y - 4}" width="{W}" height="{RH}"></rect>'
                   f'<text class="sname" x="0" y="{y + 11}">{esc(m["label"])}</text>'
                   f'<text class="sfam" x="0" y="{y + 23}">{esc(usd(tot))}</text>')
        x = x0
        for g in groups:
            v = m["total"].get(g, 0)
            if not v or not tot:
                continue
            w = BAR * v / tot
            gap = 2 if w > 3 else 0
            out.append(f'<rect class="tseg" x="{x:.1f}" y="{y + 3}" width="{max(w - gap, 0.6):.1f}" height="16" '
                       f'rx="1.5" style="fill:var(--td-{g})"></rect>')
            if w > 44:
                out.append(f'<text class="tlab" x="{x + 5:.1f}" y="{y + 15}">{v / tot * 100:.0f}%</text>')
            x += w
        lead = max(groups, key=lambda g: m["total"].get(g, 0))
        out.append(f'<text class="sval" x="{x0 + BAR + 14}" y="{y + 15}">'
                   f'{esc(next(gg["label"] for gg in tr["groups"] if gg["id"] == lead))} '
                   f'{m["total"][lead] / tot * 100:.0f}%</text></g>')
    out.append("</svg>")
    return "".join(out)


def trade_key(pack):
    return "".join(f'<span class="dk"><i class="gk" style="background:var(--td-{g["id"]})"></i>{esc(g["label"])}</span>'
                   for g in pack["trade"]["groups"])


def trade_table(pack):
    tr = pack["trade"]
    groups = tr["groups"]
    head = "".join(f'<th class="num">{esc(g["label"])}</th>' for g in groups)
    body = []
    for k, m in sorted(tr["minerals"].items(), key=lambda kv: -sum(kv[1]["total"].values())):
        tot = sum(m["total"].values())
        cells = "".join(f'<td class="num">{m["total"].get(g["id"], 0) / tot * 100:.0f}%</td>' for g in groups)
        ex = sorted(m["by_exporter"].items(), key=lambda kv: -sum(kv[1].values()))[:3]
        exs = ", ".join(cname(e) for e, _ in ex)
        body.append(f'<tr><td class="name">{esc(m["label"])}<span class="dim m"> HS {esc(", ".join(m["hs"]))}</span></td>'
                    f'<td class="num">{tot / 1e6:,.0f}</td>{cells}<td>{esc(exs)}</td></tr>')
    return (f'<div class="tbl"><table><caption>Imports from African countries reported by the rest of the world, '
            f'{tr["year"]}, share by destination</caption><thead><tr><th>Mineral</th><th class="num">USD m</th>{head}'
            f'<th>Largest African exporters</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def trade_lede(pack):
    """The lede's paragraph on where the minerals go, from the trade data."""
    tr = pack.get("trade")
    if not tr:
        return ""
    M = tr["minerals"]
    share = lambda k, g: M[k]["total"].get(g, 0) / sum(M[k]["total"].values())
    allv = {g["id"]: sum(m["total"].get(g["id"], 0) for m in M.values()) for g in tr["groups"]}
    tot = sum(allv.values())
    # the ores whose heading holds nothing else (lithium's 2530.90 does)
    china = sorted(("bauxite", "cobalt", "chromium", "copper", "manganese", "iron"), key=lambda k: -share(k, "china"))[:3]
    named = ", ".join(f"{pct(share(k, 'china'))} of the {M[k]['label'].lower()}" for k in china[:2]) + \
        f" and {pct(share(china[2], 'china'))} of the {M[china[2]]['label'].lower()}"
    gold = sum(M["gold"]["total"].values())
    uae = tr.get("uae_missing")
    blind = ""
    if uae:
        blind = (f' Gold is the blind spot. The United Arab Emirates, which reported buying {usd(uae["gold"]["total"])} '
                 f'of African gold in {uae["year"]}, had not reported {tr["year"]} to UN Comtrade, so the {usd(gold)} '
                 f'of gold counted here is a floor.')
    return (f'<p class="lede"><strong>Where it goes is another map.</strong> Of the {usd(tot)} of ores, concentrates '
            f'and first metals that the rest of the world reported buying from African countries in {tr["year"]}, '
            f'China took {pct(allv["china"] / tot)} and Europe {pct(allv["europe"] / tot)}. China bought {named}.'
            f'{blind}</p>')


def refined_note(pack):
    """Gold refined in a country counts as that country's: South Africa's
    refinery takes in gold from its neighbours."""
    tr = pack.get("trade") or {}
    kg = tr.get("minerals", {}).get("gold", {}).get("kg", {}).get("ZA")
    mined = pack["bgs"]["minerals"]["gold"]["countries"].get("ZA", [0])[-1]
    if not kg or not mined or kg < 1.5 * mined:
        return ""
    return (f' Importers reported {kg / 1000:,.0f} tonnes of gold from South Africa in {tr["year"]}, '
            f'{kg / mined:.0f} times the {mined / 1000:,.0f} tonnes mined there (BGS): the rest is gold refined in or '
            f'traded through South Africa, which customs records count as South African.')


def uae_note(pack):
    tr = pack.get("trade") or {}
    uae = tr.get("uae_missing")
    if not uae:
        return ""
    top = sorted(uae["gold"]["by"].items(), key=lambda kv: -kv[1])[:3]
    names = ", ".join(cname(i) for i, _ in top[:2]) + f" and {cname(top[2][0])}"
    return (f' <b>The United Arab Emirates is missing:</b> it had not reported its {tr["year"]} imports when this was '
            f'fetched. In {uae["year"]} it reported buying {usd(uae["gold"]["total"])} of gold from African countries, '
            f'most from {names}, and {usd(uae["diamond"]["total"])} of diamonds; the bars leave that year out, so the '
            f'gold and diamond rows understate the Gulf.')


# --------------------------------------------------------- country table

def country_table(pack, L, sites, facs):
    deps, mines = {}, {}
    for f in sites:
        deps[f["properties"]["iso"]] = deps.get(f["properties"]["iso"], 0) + 1
    for f in facs:
        if f["properties"]["kind"] == "mine" and f["properties"]["minerals"] != ["other"]:
            mines[f["properties"]["iso"]] = mines.get(f["properties"]["iso"], 0) + 1
    tr = pack.get("trade", {}).get("minerals", {})
    exp, china, buyer = {}, {}, {}
    for k, m in tr.items():
        for e, by in m["by_exporter"].items():
            exp[e] = exp.get(e, 0) + sum(by.values())
            china[e] = china.get(e, 0) + by.get("china", 0)
    prod = {}
    for k, r in L.items():
        if k in COUNT_ONCE:
            continue
        for iso, _, s in r["af"]:
            if s >= 0.01:
                prod.setdefault(iso, []).append((s, r["name"]))
    isos = sorted(set(prod) | {i for i, n in deps.items() if n >= 3} | {e for e, v in exp.items() if v >= 5e7},
                  key=lambda i: (-len(prod.get(i, [])), -exp.get(i, 0)))
    body = []
    for iso in isos:
        if iso not in CC:
            continue
        ps = sorted(prod.get(iso, []), reverse=True)
        pl = ", ".join(f"{n} {pct(s)}" for s, n in ps[:5]) + (f" and {len(ps) - 5} more" if len(ps) > 5 else "")
        e = exp.get(iso, 0)
        body.append(f'<tr><td class="name">{esc(cname(iso))}</td><td class="num">{len(ps)}</td><td>{esc(pl) or "–"}</td>'
                    f'<td class="num">{mines.get(iso, 0) if facs else "–"}</td>'
                    f'<td class="num">{deps.get(iso, 0)}</td><td class="num">{f"{e / 1e6:,.0f}" if e else "–"}</td>'
                    f'<td class="num">{pct(china[iso] / e) if e else "–"}</td></tr>')
    return ('<div class="tbl"><table><caption>African countries by the minerals they mine (1% or more of world '
            'output), their mines of these minerals and deposits on the map (USGS), and their mineral exports</caption><thead><tr><th>Country</th>'
            '<th class="num">Minerals</th><th>Share of world output</th><th class="num">Mines (2018)</th>'
            '<th class="num">Deposits</th>'
            f'<th class="num">Mineral exports, USD m</th><th class="num">To China</th></tr></thead><tbody>{"".join(body)}'
            '</tbody></table></div>')


# ----------------------------------------------------------- rare earths

STAGE = {  # the register's stages -> the site's status colours and words
    "producing": ("operating", "Producing"), "construction": ("under_construction", "Being built"),
    "feasibility": ("approved", "Feasibility"), "exploration": ("announced", "Exploration"),
    "stalled": ("stalled", "Stalled"),
}


# where each project's name sits beside its dot on the rare-earth map, for
# the pairs that would otherwise collide: (dx, dy, anchor)
LABEL_AT = {"zandkopsdrift": (-9, 4, "end"), "steenkampskraal": (9, 10, "start"), "ngualla": (-9, 4, "end"),
            "wigu-hill": (9, 4, "start"), "kangankunde": (-9, -3, "end"), "songwe-hill": (9, 10, "start"),
            "phalaborwa-rainbow": (9, 4, "start"), "mrima-hill": (9, 6, "start"), "ampasindava": (-9, -7, "end"),
            "qmm-mandena": (-9, 4, "end"), "gakara": (-9, 4, "end"), "lofdal": (-9, 4, "end"),
            "longonjo": (-9, 4, "end"), "mabounie": (-9, 4, "end")}


def stake(o):
    s = o.get("stake")
    if s in (None, ""):
        return ""
    s = str(s)
    return " " + (s if "%" in s else s + "%")


def short_name(n, k=48):
    n = re.sub(r"\s*\((?:LSE|ASX|TSX|NYSE|JSE|AIM|TSX-V|TSXV)[^)]*\)", "", n or "")
    return n if len(n) <= k else n[:k - 1].rstrip() + "…"


def first_clause(s, k=90):
    s = (s or "").split(". ")[0].strip()
    return s if len(s) <= k else s[:k - 1].rstrip() + "…"


def ree_parts(ree, sites):
    if not ree:
        return "", "<p class=\"note\">The rare-earth register is being compiled.</p>", {}
    projects = ree["projects"]
    placed = [p for p in projects if p.get("lat") is not None and p.get("lon") is not None]
    # an inset map of Africa south of 15°N, where the projects are
    lo0, lo1, la0, la1 = -18.5, 52.5, -35.4, 15.0
    W = 520.0
    sc = W / (lo1 - lo0)
    H = (la1 - la0) * sc
    P = lambda lon, lat: (round((lon - lo0) * sc, 1), round((la1 - lat) * sc, 1))
    bm = json.loads((DATA / "africa_basemap.json").read_text())
    out = [f'<svg id="reemap" viewBox="0 0 {W:.0f} {H:.0f}" role="img" aria-label="Map of Africa\'s rare-earth '
           f'projects by stage, with the other USGS rare-earth deposits">']
    for c in bm["countries"]:
        ds = []
        for poly in c["p"]:
            for ring in poly:
                pts = clip_ring([P(a, b) for a, b in ring], -4, -4, W + 4, H + 4)
                pts = simplify(pts, 0.4)
                if len(pts) >= 3:
                    ds.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z")
        if ds:
            out.append(f'<path class="rl{"" if c.get("af") else " ctx"}" d="{" ".join(ds)}"></path>')
    for f in sites:
        if "ree" in f["properties"]["minerals"]:
            lon, lat = f["geometry"]["coordinates"]
            if lo0 <= lon <= lo1 and la0 <= lat <= la1:
                x, y = P(lon, lat)
                out.append(f'<circle class="rdep" cx="{x}" cy="{y}" r="2.2"><title>{esc(f["properties"]["name"])} '
                           f'(USGS rare-earth deposit)</title></circle>')
    order = list(STAGE)
    for p in sorted(placed, key=lambda p: order.index(p["stage"]) if p["stage"] in order else 9, reverse=True):
        x, y = P(p["lon"], p["lat"])
        s = STAGE.get(p["stage"], ("announced", p["stage"]))[0]
        dx, dy, anchor = LABEL_AT.get(p["id"], (9, 4, "start"))
        label = re.split(r" \(| Rare| Heavy| Monazite| mineral| Ionic", p["name"])[0]
        out.append(f'<g class="rpj" data-id="{esc(p["id"])}" tabindex="0"><circle class="rp {s}" cx="{x}" cy="{y}" r="6">'
                   f'</circle><text class="rn" x="{x + dx}" y="{y + dy}" text-anchor="{anchor}">{esc(label)}</text></g>')
    out.append("</svg>")
    # the register table
    rows = []
    for p in sorted(projects, key=lambda p: (order.index(p["stage"]) if p["stage"] in order else 9, p["country"])):
        s, sname = STAGE.get(p["stage"], ("announced", p["stage"]))
        owners = "; ".join(f'{short_name(o["name"])}{stake(o)}{" (" + cname(o["home"]) + ")" if o.get("home") else ""}'
                           for o in p.get("owners", []))
        deals = []
        offs = p.get("offtake") or []
        for o in offs[:3]:
            deals.append(f'<b>Buyer</b> {esc(short_name(o.get("buyer")))}'
                         f'{" (" + esc(cname(o["home"])) + ")" if o.get("home") else ""}'
                         f'{" " + src_link(o["source"], "↗") if o.get("source") else ""}')
        if len(offs) > 3:
            deals.append(f'<span class="dim">and {len(offs) - 3} more buyers</span>')
        fins = p.get("finance") or []
        for fi in fins[:4]:
            amt = f' {usd(fi["amount_usd"])}' if fi.get("amount_usd") else ""
            deals.append(f'<b>Money</b> {esc(short_name(fi.get("lender"), 56))}'
                         f'{" (" + esc(cname(fi["home"])) + ")" if fi.get("home") else ""}{esc(amt)}'
                         f'<span class="dim"> {esc(first_clause(fi.get("instrument"), 60))}</span>'
                         f'{" " + src_link(fi["source"], "↗") if fi.get("source") else ""}')
        if len(fins) > 4:
            deals.append(f'<span class="dim">and {len(fins) - 4} more financing lines</span>')
        res = p.get("resource") or {}
        srcs = {u for u in [p.get("stage_source"), p.get("note_source"), res.get("source"),
                            (p.get("licence") or {}).get("source")] if u}
        where = "" if p.get("lat") is not None else ' <span class="dim">(not on the map: no published location)</span>'
        rows.append(
            f'<tr id="ree-{esc(p["id"])}"><td class="name">{esc(p["name"])}<span class="pc dim">{esc(cname(p["country"]))}'
            f'{" · " + esc(p["deposit_type"]) if p.get("deposit_type") else ""}</span>{where}</td>'
            f'<td><span class="st {s}"><i></i>{esc(sname)}</span>'
            f'<span class="pc dim">as of {esc(p.get("stage_date") or "")}</span></td>'
            f'<td>{esc(owners) or "–"}{"<span class=pc>State: " + esc(first_clause(p["state_partner"], 120)) + "</span>" if p.get("state_partner") else ""}</td>'
            f'<td>{esc(first_clause(res.get("text"), 70)) or "–"}</td>'
            f'<td class="deals">{"<br>".join(deals) or "–"}</td>'
            f'<td class="latest">{esc(p.get("note") or "")}<span class="srcs">{" · ".join(src_link(u) for u in sorted(srcs))}</span></td></tr>')
    early = sum(1 for p in projects if p["stage"] in ("exploration", "stalled"))
    table = ('<div class="tbl"><table class="reetab"><caption>Africa\'s rare-earth projects at feasibility stage or '
             f'beyond, and {WORDS.get(early, early)} earlier or stalled ones the register follows, by stage. A mineral-sands '
             'mine counts only where its operator reports recovering or selling monazite</caption>'
             '<thead><tr><th>Project</th><th>Stage</th><th>Owners</th><th>Resource</th><th>Buyers and money</th>'
             f'<th>Latest</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    rules = "".join(f'<li><b>{esc(cname(r["country"]))}, {esc(r["date"])}.</b> {esc(r["text"])} '
                    f'{src_link(r["source"], "Source")}</li>' for r in ree.get("export_rules", []))
    left = "".join(f'<li><b>{esc(x.get("name"))}.</b> {esc(x.get("why"))}</li>' for x in ree.get("left_out", []))
    qs = "".join(f'<li>{esc(q if isinstance(q, str) else json.dumps(q, ensure_ascii=False))}</li>'
                 for q in ree.get("open_questions", []))
    extra = (f'<details class="tblbox"><summary>Export rules that touch rare earths ({len(ree.get("export_rules", []))})'
             f'</summary><ul class="facts">{rules}</ul></details>'
             f'<details class="tblbox"><summary>Looked at and left out ({len(ree.get("left_out", []))})</summary>'
             f'<ul class="facts">{left}</ul></details>'
             f'<details class="tblbox review"><summary>Open questions for review ({len(ree.get("open_questions", []))})'
             f'</summary><ul class="facts">{qs}</ul></details>')
    tips = {p["id"]: {"name": p["name"], "country": cname(p["country"]),
                      "stage": STAGE.get(p["stage"], ("", p["stage"]))[1], "type": p.get("deposit_type") or "",
                      "owners": "; ".join(f'{short_name(o["name"])}{stake(o)}' + (f' ({cname(o["home"])})' if o.get("home") else "")
                                          for o in p.get("owners", [])),
                      "res": (p.get("resource") or {}).get("text") or "", "note": p.get("note") or "",
                      "loc": "USGS deposit point" if p.get("loc_precision") == "usgs" else
                             ("approximate" if p.get("loc_precision") == "approx" else "")}
            for p in placed}
    stage_n = {k: sum(1 for p in projects if p["stage"] == k) for k in STAGE}
    return "".join(out), table + extra, {"tips": tips, "stage_n": stage_n}


def ree_facts(ree):
    if not ree or not ree.get("facts"):
        return ""
    return "<ul class=\"facts\">" + "".join(
        f'<li>{esc(f["text"])} {src_link(f["source"], "Source")}'
        f'{" · " + src_link(f["source_2"], "Also") if f.get("source_2") else ""}</li>'
        for f in ree["facts"] if f.get("source")) + "</ul>"


# ------------------------------------------------------ who owns the mines

# Owner groups, relative to the mine's country; the order is the stacking
# order. The hues are the site's validated categorical slots (China aqua,
# Europe yellow, North America green as the United States elsewhere).
OWN_GROUPS = [["state", "Host government"], ["local", "Host-country companies and miners"],
              ["africa", "Other African companies"], ["china", "China"], ["europe", "Europe"],
              ["namerica", "North America"], ["australia", "Australia"], ["other", "Other countries"]]
EUROPE_ISO = set("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE GB CH NO "
                 "JE GG IM LI".split())
GENERIC_STATE = re.compile(r"^(Government|State|Republic)\b", re.I)
GENERIC_LOCAL = re.compile(r"artisanal|small[- ]scale|cooperative|^private|^others?\b|common shares|employee|"
                           r"community|^public\b|local investors|^various", re.I)
OWN_MIN_MINES = 8                    # minerals with fewer mines than this get no row
# the mines that count: working or being built in 2018, not those on care and
# maintenance, suspended or closed
OWN_STATUS = {"Assumed Active", "Active", "Construction", "Development"}


def owner_index(owners):
    return {o["name"]: o for o in (owners or [])}


def own_group(name, cls, site_iso):
    if GENERIC_STATE.match(name or ""):
        return "state"
    c = cls.get(name)
    home = c.get("home") if c else None
    if not home:
        return "local" if GENERIC_LOCAL.search(name or "") else None
    if home == site_iso:
        return "state" if c.get("state") else "local"
    if home in CC:
        return "africa"
    if home in ("CN", "HK", "MO"):
        return "china"
    if home in EUROPE_ISO:
        return "europe"
    if home in ("US", "CA"):
        return "namerica"
    if home == "AU":
        return "australia"
    return "other"


def equity(p):
    """A mine's owners and their share of it: stated stakes (scaled down if
    they add up past 100%), the rest split among owners with no stake given,
    and anything left unattributed."""
    known = [o for o in p["owners"] if o["stake"] is not None]
    unknown = [o for o in p["owners"] if o["stake"] is None]
    tot = sum(o["stake"] for o in known)
    scale = 100 / tot if tot > 100.5 else 1
    out = [(o["name"], o["stake"] * scale / 100) for o in known]
    rest = max(0.0, 1 - sum(s for _, s in out))
    if unknown and rest > 0.001:
        out += [(o["name"], rest / len(unknown)) for o in unknown]
        rest = 0
    if rest > 0.001:
        out.append((None, rest))
    return out


def ownership(facs, cls):
    """Per mineral: its mines (2018), the equity-weighted share of them held
    by each owner group, and the owners holding the most."""
    if not facs or not cls:
        return [], {}
    mines = [f["properties"] for f in facs if f["properties"]["kind"] == "mine"
             and f["properties"]["minerals"] != ["other"] and f["properties"]["status"] in OWN_STATUS]
    keys = ["all"] + [c for c, _, _ in MAP_CHIPS]
    rows = []
    for k in keys:
        ms = [p for p in mines if k == "all" or k in p["minerals"]]
        if len(ms) < OWN_MIN_MINES:
            continue
        g, who = {}, {}
        for p in ms:
            for name, s in equity(p):
                grp = own_group(name, cls, p["iso"]) if name else None
                g[grp or "none"] = g.get(grp or "none", 0) + s
                if name:
                    who[name] = who.get(name, 0) + s
        n = len(ms)
        rows.append({"key": k, "name": "All these minerals" if k == "all" else dict((c, l) for c, l, _ in MAP_CHIPS)[k],
                     "n": n, "g": {x: round(v / n, 4) for x, v in g.items()},
                     "classified": round(1 - g.get("none", 0) / n, 4),
                     "top": [[nm, round(v, 2), (cls.get(nm) or {}).get("home")] for nm, v in
                             sorted(who.items(), key=lambda kv: -kv[1])[:8]]})
    rows = rows[:1] + sorted(rows[1:], key=lambda r: -r["n"])
    return rows, {}


def own_chart(rows):
    if not rows:
        return '<p class="note">The ownership chart needs data/minerals_owners.json.</p>'
    W, LAB, BAR, RH = 980, 186, 556, 34
    H = RH * len(rows) + 30
    x0 = LAB
    out = [f'<svg id="ownchart" viewBox="0 0 {W} {H}" role="img" aria-label="Who owned Africa\'s mines in 2018, '
           f'by the home country of their owners, mineral by mineral">']
    for gx in (0, 0.25, 0.5, 0.75, 1):
        x = x0 + BAR * gx
        out.append(f'<line class="sgrid" x1="{x:.1f}" x2="{x:.1f}" y1="18" y2="{H - 6}"></line>'
                   f'<text class="ax" x="{x:.1f}" y="11" text-anchor="middle">{int(gx * 100)}%</text>')
    for i, r in enumerate(rows):
        y = 22 + i * RH
        out.append(f'<g class="orow{" oall" if r["key"] == "all" else ""}" data-k="{r["key"]}" tabindex="0">'
                   f'<rect class="shit" x="0" y="{y - 4}" width="{W}" height="{RH}"></rect>'
                   f'<text class="sname" x="0" y="{y + 11}">{esc(r["name"])}</text>'
                   f'<text class="sfam" x="0" y="{y + 23}">{r["n"]} mines{", each counted once" if r["key"] == "all" else ""}</text>'
                   f'<rect class="strack" x="{x0}" y="{y + 3}" width="{BAR}" height="16" rx="2"></rect>')
        x = x0
        for gid, _ in OWN_GROUPS:
            v = r["g"].get(gid, 0)
            w = BAR * v
            if w < 0.6:
                continue
            gap = 2 if w > 3 else 0
            out.append(f'<rect class="tseg" x="{x:.1f}" y="{y + 3}" width="{max(w - gap, 0.6):.1f}" height="16" rx="1.5" '
                       f'style="fill:var(--og-{gid})"></rect>')
            if w > 40:
                out.append(f'<text class="tlab" x="{x + 5:.1f}" y="{y + 15}">{v * 100:.0f}%</text>')
            x += w
        lead = max((g for g, _ in OWN_GROUPS), key=lambda g: r["g"].get(g, 0))
        out.append(f'<text class="sval" x="{x0 + BAR + 14}" y="{y + 15}">{esc(dict(OWN_GROUPS)[lead])} '
                   f'{r["g"].get(lead, 0) * 100:.0f}%</text></g>')
    out.append("</svg>")
    return "".join(out)


def own_key():
    return "".join(f'<span class="dk"><i class="gk" style="background:var(--og-{g})"></i>{esc(n)}</span>'
                   for g, n in OWN_GROUPS) + '<span class="dk"><i class="gk" style="background:var(--surface-2);' \
                                             'box-shadow:inset 0 0 0 1px var(--rule)"></i>Not classified</span>'


def owners_table(owners, facs):
    if not owners:
        return ""
    n = {}
    for f in facs:
        p = f["properties"]
        if p["kind"] == "mine" and p["minerals"] != ["other"] and p["status"] in OWN_STATUS:
            for o in p["owners"]:
                n[o["name"]] = n.get(o["name"], 0) + 1
    rows = []
    for o in sorted(owners, key=lambda o: -n.get(o["name"], 0)):
        rows.append(f'<tr><td class="name">{esc(o["name"])}</td><td class="num">{n.get(o["name"], 0)}</td>'
                    f'<td>{esc(cname(o["home"])) if o.get("home") else "<span class=dim>not classified</span>"}'
                    f'{" · state" if o.get("state") else ""}</td><td>{esc(o.get("parent") or "")}</td>'
                    f'<td>{esc(o.get("note") or "")}{" " + src_link(o["source"], "Source") if o.get("source") else ""}</td></tr>')
    return ('<details class="tblbox review"><summary>Owners as classified for this page, for review '
            f'({len(owners)})</summary><div class="tbl"><table><caption>Every operator and owner of the mines above, '
            'with the home country of its ultimate parent in 2018 as classified for this page; mines working or being '
            'built in 2018 that it holds a stake in</caption><thead><tr>'
            '<th>Owner</th><th class="num">Mines</th><th>Home</th><th>Parent</th><th>Note</th></tr></thead><tbody>'
            f'{"".join(rows)}</tbody></table></div></details>')


# -------------------------------------------------------------- the page

def build_page(pack, sites, ree, facs, exps, owners):
    L = latest(pack)
    T = trends(pack, L)
    chart, order = share_chart(L)
    res = reserves_rows(pack, L)
    # the mines and plants of the page's minerals; cement, steel, salt, coal and
    # the other industrial-mineral sites stay in the data file, off the map
    facs = [f for f in facs if f["properties"]["minerals"] != ["other"]]
    exps = [f for f in exps if f["properties"]["minerals"] != ["other"]]
    sites, facs, exps = number(sites), number(facs), number(exps)
    ree_map, ree_table, ree_payload = ree_parts(ree, sites)
    tr = pack.get("trade")
    cls = owner_index(owners)
    own_rows, own_owner_tips = ownership(facs, cls)
    marks = map_marks(sites, facs, exps)
    payload = {"names": {**WORLD_NAMES, **CC}, "share": share_payload(L),
               "shareSlot": {iso: i + 1 for i, iso in enumerate(share_countries(L))},
               "map": map_payload(L, sites, facs, exps, {n: c["home"] for n, c in cls.items() if c.get("home")}),
               "own": {"rows": own_rows, "groups": OWN_GROUPS, "owners": own_owner_tips},
               "trends": T, "res": {r["key"]: {k: r[k] for k in ("name", "prod", "res", "res_af", "world_res",
                                                                  "res_unit", "other_res")} for r in res},
               "trade": ({"groups": tr["groups"], "year": tr["year"], "uae": tr.get("uae_missing"),
                          "m": {k: {"label": m["label"], "total": m["total"], "what": m["what"], "hs": m["hs"],
                                    "by": m["by_exporter"], "top": m["top_buyer"]} for k, m in tr["minerals"].items()}}
                         if tr else None),
               "ree": ree_payload}

    n50 = [r for r in L.values() if r["africa"] >= 0.5]
    tokens = {
        "__BGS_YEAR__": str(pack["bgs"]["last_year"]), "__BGS_FIRST__": str(pack["bgs"]["first_year"]),
        "__MCS_YEAR__": str(pack["mcs"]["year"]), "__N_MINERALS__": str(len(L)),
        "__N_DEPOSITS__": f"{len(sites):,}", "__N_DEP_COUNTRIES__": str(len({f['properties']['iso'] for f in sites})),
        "__N_HALF__": WORDS.get(len(n50), str(len(n50))),
        "__HALF_LIST__": esc(", ".join(r["name"].lower() for r in sorted(n50, key=lambda r: -r["africa"]))),
        "__FETCHED__": fmt_date(pack["fetched"]),
        "__MAP_W__": f"{MAP_W:.0f}", "__MAP_H__": f"{MAP_H:.0f}", "__BASEMAP__": basemap(), "__DEPOSITS__": marks,
        "__CHIPS__": chip_html(), "__SHARE_CHART__": chart, "__SHARE_TABLE__": share_table(L),
        "__SHARE_KEY__": share_key(L),
        "__TRENDS__": trend_panels(L, T), "__RES_CHART__": reserves_chart(res),
        "__N_RES__": str(len(res)),
        "__TRADE_CHART__": trade_chart(pack) if tr else "", "__TRADE_KEY__": trade_key(pack) if tr else "",
        "__TRADE_TABLE__": trade_table(pack) if tr else "", "__TRADE_YEAR__": str(tr["year"]) if tr else "n/a",
        "__TRADE_LEDE__": trade_lede(pack), "__UAE_NOTE__": refined_note(pack) + uae_note(pack),
        "__COUNTRY_TABLE__": country_table(pack, L, sites, facs),
        "__N_FACS__": f"{len(facs):,}", "__N_MINES__": f"{sum(1 for f in facs if f['properties']['kind'] == 'mine'):,}",
        "__N_PLANTS__": f"{sum(1 for f in facs if f['properties']['kind'] == 'plant'):,}",
        "__N_EXPS__": f"{len(exps):,}",
        "__OWN_CHART__": own_chart(own_rows), "__OWN_KEY__": own_key(),
        "__OWN_TABLE__": owners_table(owners, facs),
        "__N_OWN_MINES__": str(own_rows[0]["n"]) if own_rows else "0",
        "__OWN_CLASSIFIED__": pct(own_rows[0]["classified"]) if own_rows else "0%",
        "__N_OWNERS__": str(len(owners or [])),
        **{f"__OWN_{r['key'].upper()}_{g.upper()}__": pct(r["g"].get(g, 0)) for r in own_rows for g, _ in OWN_GROUPS},
        "__REE_MAP__": ree_map, "__REE_TABLE__": ree_table, "__REE_FACTS__": ree_facts(ree),
        "__REE_N__": str(len(ree["projects"])) if ree else "0",
        "__REE_COMPILED__": fmt_date(ree["compiled"]) if ree else "",
        **{f"__REE_{k.upper()}__": WORDS.get(v, str(v)) for k, v in (ree_payload.get("stage_n") or {}).items()},
        "__REE_STAGE_KEY__": "".join(f'<span class="dk"><span class="st {s}"><i></i>{esc(n)}</span></span>'
                                     for s, n in STAGE.values()),
    }
    for k, r in L.items():
        K = k.upper()
        tokens[f"__S_{K}__"] = pct(r["africa"])
        if r["af"]:
            tokens[f"__TOP_{K}__"] = esc(cname(r["af"][0][0]))
            tokens[f"__TOPS_{K}__"] = pct(r["af"][0][2])
    for r in res:
        tokens[f"__R_{r['key'].upper()}__"] = pct(r["res"])
        tokens[f"__RP_{r['key'].upper()}__"] = pct(r["prod"])
    for k, u in pack["mcs"]["minerals"].items():
        for iso, v in u["prod"].items():
            tokens[f"__MCS_{k.upper()}_{iso}__"] = f"{v:,.0f}"
        for iso, v in u["res"].items():
            tokens[f"__MCSR_{k.upper()}_{iso}__"] = f"{v:,.0f}"
        if u.get("world_prod"):
            tokens[f"__MCS_{k.upper()}_WORLD__"] = f"{u['world_prod']:,.0f}"
        if u.get("world_res"):
            tokens[f"__MCSR_{k.upper()}_WORLD__"] = f"{u['world_res']:,.0f}"
    if tr:
        allv = {g["id"]: sum(m["total"].get(g["id"], 0) for m in tr["minerals"].values()) for g in tr["groups"]}
        tot = sum(allv.values())
        tokens["__T_TOTAL__"] = usd(tot)
        for g, v in allv.items():
            tokens[f"__T_ALL_{g.upper()}__"] = pct(v / tot)
        for k, m in tr["minerals"].items():
            t = sum(m["total"].values())
            tokens[f"__T_{k.upper()}__"] = usd(t)
            for g, v in m["total"].items():
                tokens[f"__T_{k.upper()}_{g.upper()}__"] = pct(v / t) if t else "0%"
    return tokens, payload


def jsonld(path):
    page = {"@context": "https://schema.org", "@type": "WebPage", "@id": site_url(path), "url": site_url(path),
            "name": TITLE, "description": DESCRIPTION, "inLanguage": "en",
            "isPartOf": {"@type": "WebSite", "@id": site_url("#website"), "name": SITE_NAME, "url": SITE_URL},
            "author": {"@type": "Person", "name": AUTHOR_NAME, "url": WEB_URL, "sameAs": [AUTHOR_URL]},
            "about": {"@type": "Place", "name": "Africa"}}
    return ('<script type="application/ld+json">'
            + json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n")


def build():
    pack, sites, ree, facs, exps, owners = load()
    tokens, payload = build_page(pack, sites, ree, facs, exps, owners)
    tokens.update({"__TITLE__": esc(TITLE), "__DATA_URL__": site_url("data/minerals.json"),
                   "__SITES_URL__": site_url("data/minerals_sites.geojson"),
                   "__REE_URL__": site_url("data/minerals_ree.json"),
                   "__FACS_URL__": site_url("data/minerals_facilities.geojson"),
                   "__EXPS_URL__": site_url("data/minerals_exploration.geojson"),
                   "__OWNERS_URL__": site_url("data/minerals_owners.json"),
                   "__DATA_FILE__": "minerals.json", "__BUILT__": fmt_date(today())})
    page = FRAME.read_text().replace("<!--__BODY__-->", head_wrap(FRAG.read_text(), minerals_figure(latest(pack), cname)), 1)
    # the longest tokens first, so __S_CO__ never eats the head of __S_COBALT__
    for k in sorted(tokens, key=len, reverse=True):
        page = page.replace(k, tokens[k])
    page = page.replace("/*__MPAYLOAD__*/", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                        .replace("</", "<\\/"), 1)
    # the frame's own map script looks for #map; this page draws #mmap itself
    page = page.replace("/*__PAYLOAD__*/", json.dumps({"charts": {}}), 1)
    page = brand_assets(page, donor=SLUG)
    left = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]*__", page)))
    if left:
        sys.exit(f"minerals: unfilled tokens {', '.join(left)}")
    path = f"{SLUG}/index.html"
    doc = wrap_document(page, title=TITLE, description=DESCRIPTION, path=path, kind="profile",
                        extra_head=jsonld(path))
    if NOINDEX[0] not in doc:
        sys.exit("minerals: the robots meta changed in shared.wrap_document; update NOINDEX")
    doc = doc.replace(*NOINDEX)
    (DOCS / SLUG).mkdir(parents=True, exist_ok=True)
    (DOCS / SLUG / "index.html").write_text(doc)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    for f in (SRC, SITES, REE, FACS, EXPS, OWNERS):
        if f.exists():
            shutil.copy(f, DOCS / "data" / f.name)
    print(f"→ docs/{path}  {len(doc.encode()) / 1024:.0f} KB  (+ docs/data/{SRC.name}, {SITES.name}"
          f"{', ' + REE.name if REE.exists() else ''})")


if __name__ == "__main__":
    build()
