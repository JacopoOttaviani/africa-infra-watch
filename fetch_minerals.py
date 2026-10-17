#!/usr/bin/env python3
"""
The data behind the minerals deep dive (docs/minerals/, build_minerals.py):
what Africa mines, where, how much of the world's supply that is, what is
left in the ground and where it is shipped. Four official sources, fetched
and reduced to two files:

    python3 fetch_minerals.py            -> data/minerals.json, data/minerals_sites.geojson
    python3 fetch_minerals.py bgs mcs    # only the named parts (bgs, mcs, sites, trade, facilities)

bgs    British Geological Survey, World Mineral Statistics (OGC API,
       ogcapi.bgs.ac.uk), mine production by country and year, 2000-2024.
       It names every producing country, so Africa's share is a full share,
       not a lower bound. BGS terms: non-commercial use with acknowledgement.
mcs    USGS Mineral Commodity Summaries 2026 (pubs.usgs.gov, public domain):
       2025 mine production and reserves, read from the PDF's "World Mine
       Production and Reserves" tables. Footnote markers are set in smaller
       type and fuse with the numbers in a plain text dump ("121,400" for
       footnote 12 + 1,400), so the tables are read character by character
       and every character under 7.5 pt is dropped. The USGS folds many
       small producers into "Other countries", so an African share computed
       from it is a lower bound: the page uses it for reserves, for 2025,
       and for the three minerals whose BGS series mix ore and content
       (lithium, tantalum, rare earths).
sites  USGS geolocated deposits: "Major mineral deposits of Africa and the
       Middle East" (Open-File Report 2005-1294) and "Global distribution of
       selected mines, deposits and districts of critical minerals"
       (Professional Paper 1802, 2017), both from the USGS ArcGIS server.
       Deposits, not operating mines: many are mined, some never were.
       Each point is placed in a country by point-in-polygon on the site's
       1:10m basemap, since the two datasets spell countries their own way.
trade  UN Comtrade (public preview API, no key): 2024 imports reported by
       every country from each African country, for the ores and first
       products of each mineral (mirror data: importers report more fully
       and sooner than many African customs do).

The richest geolocated source, the USGS "Compilation of Geospatial Data for
the Mineral Industries and Related Infrastructure of Africa" (2021, DOI
10.5066/P97EQWXP: 2,408 operating facilities with owners, status and
capacity), sits on ScienceBase behind a bot check this script does not try
to pass. Download it by hand and the facilities layer can be added.

Needs pdfplumber for the USGS PDF. Downloads are cached in
data/.minerals_cache/ (not committed).
"""

import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from fetch_sources import AFRICA_ISO
from fetch_sources import get as _get
from shared import DATA, today

OUT = DATA / "minerals.json"
SITES = DATA / "minerals_sites.geojson"
CACHE = DATA / ".minerals_cache"
AF = set(AFRICA_ISO) | {"EH"}

FIRST_YEAR = 2000
BGS_API = "https://ogcapi.bgs.ac.uk/collections/world-mineral-statistics/items"
BGS_PAGE = "https://www.bgs.ac.uk/mineralsuk/statistics/world-mineral-statistics/"
MCS_PDF = "https://pubs.usgs.gov/periodicals/mcs2026/mcs2026.pdf"
MCS_PAGE = "https://doi.org/10.3133/mcs2026"
USGS_ARC = "https://energy.usgs.gov/arcgis/rest/services/Hosted"
OFR_LAYER = USGS_ARC + "/Major_mineral_deposits/FeatureServer/0"
PP_LAYER = USGS_ARC + "/Global_distribution_of_selected_critical_minerals/FeatureServer/2"
OFR_DOI = "https://doi.org/10.3133/ofr20051294"
PP_DOI = "https://doi.org/10.5066/F7GH9GQR"
COMTRADE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
COMTRADE_REF = "https://comtradeapi.un.org/files/v1/app/reference/{}.json"
TRADE_YEAR = 2024

# ------------------------------------------------------------- minerals
#
# The page's minerals, in the page's order (by family), each with where its
# production series comes from. bgs: (yearbook table, sub-commodities). A
# sub-commodity of None takes the rows without one; "partition" means the
# subs split the total (a country reports either the total or its parts, so
# the parts are summed only when the total is missing). src "usgs" takes the
# 2025 figure from the MCS instead, for the minerals whose BGS table mixes
# ores, concentrates and contained metal country by country.

MINERALS = [
    # family, key, name, unit (as the page writes it), source
    dict(fam="battery", key="cobalt", name="Cobalt", unit="t cobalt content",
         bgs=("Mine production of cobalt", [None])),
    dict(fam="battery", key="copper", name="Copper", unit="t copper content",
         bgs=("Mine production of copper", [None])),
    dict(fam="battery", key="manganese", name="Manganese ore", unit="t ore",
         bgs=("Production of manganese ore", "partition")),
    dict(fam="battery", key="graphite", name="Graphite", unit="t",
         bgs=("Production of graphite", "partition")),
    dict(fam="battery", key="lithium", name="Lithium", unit="t lithium content", src="usgs"),
    dict(fam="battery", key="nickel", name="Nickel", unit="t nickel content",
         bgs=("Mine production of nickel", [None])),
    dict(fam="pgm", key="platinum", name="Platinum", unit="kg",
         bgs=("Mine production of platinum group metals", ["Platinum"])),
    dict(fam="pgm", key="palladium", name="Palladium", unit="kg",
         bgs=("Mine production of platinum group metals", ["Palladium"])),
    dict(fam="pgm", key="rhodium", name="Rhodium", unit="kg",
         bgs=("Mine production of platinum group metals", ["Rhodium"])),
    dict(fam="steel", key="chromium", name="Chromium ore", unit="t ore",
         bgs=("Production of chromium ores and concentrates", "partition")),
    dict(fam="steel", key="vanadium", name="Vanadium", unit="t vanadium content",
         bgs=("Mine production of vanadium", [None])),
    dict(fam="steel", key="iron", name="Iron ore", unit="t ore",
         bgs=("Production of iron ore", "partition")),
    dict(fam="tech", key="tantalum", name="Tantalum", unit="t tantalum content", src="usgs"),
    dict(fam="tech", key="tin", name="Tin", unit="t tin content",
         bgs=("Mine production of tin", [None])),
    dict(fam="tech", key="ree", name="Rare earths", unit="t rare-earth oxide", src="usgs"),
    dict(fam="sands", key="titanium", name="Titanium minerals", unit="t ilmenite, rutile and leucoxene",
         bgs=("Production of titanium minerals", "sum")),
    dict(fam="sands", key="zircon", name="Zircon", unit="t",
         bgs=("Production of zirconium minerals", "partition")),
    dict(fam="ores", key="bauxite", name="Bauxite", unit="t",
         bgs=("Production of bauxite", "partition")),
    dict(fam="ores", key="phosphate", name="Phosphate rock", unit="t",
         bgs=("Production of phosphate rock", [None])),
    dict(fam="precious", key="gold", name="Gold", unit="kg",
         bgs=("Mine production of gold", [None])),
    dict(fam="precious", key="diamond", name="Diamonds", unit="carats",
         bgs=("Production of diamond", "partition")),
    dict(fam="energy", key="uranium", name="Uranium", unit="t uranium content",
         bgs=("Mine production of uranium", [None])),
]

FAMILIES = [
    ("battery", "Battery and grid metals"),
    ("pgm", "Platinum-group metals"),
    ("steel", "Steel and alloy metals"),
    ("tech", "Electronics and magnets"),
    ("sands", "Mineral sands"),
    ("ores", "Bulk ores"),
    ("precious", "Gold and diamonds"),
    ("energy", "Nuclear fuel"),
]

# USGS MCS 2026 chapters: which column holds 2025 production and which the
# reserves (columns counted left to right among the numbers of each row),
# and the units the chapter states. Read off the PDF's tables.
MCS = {
    "cobalt": ("COBALT", 1, 2, "t cobalt content", "t"),
    "copper": ("COPPER", 1, 4, "thousand t copper content", "thousand t"),
    "manganese": ("MANGANESE", 1, 2, "thousand t manganese content", "thousand t manganese content"),
    "graphite": ("GRAPHITE (NATURAL)", 1, 2, "t", "t"),
    "lithium": ("LITHIUM", 1, 2, "t lithium content", "t lithium content"),
    "nickel": ("NICKEL", 1, 2, "t nickel content", "t nickel content"),
    "platinum": ("PLATINUM-GROUP METALS", 3, 4, "kg", "kg of all platinum-group metals"),
    "palladium": ("PLATINUM-GROUP METALS", 1, 4, "kg", "kg of all platinum-group metals"),
    "chromium": ("CHROMIUM", 1, 2, "thousand t chromium content", "thousand t shipping-grade ore"),
    "vanadium": ("VANADIUM", 1, 2, "t vanadium content", "thousand t vanadium content"),
    "iron": ("IRON ORE", 1, 5, "thousand t usable ore", "million t iron content"),
    "tantalum": ("TANTALUM", 1, 2, "t tantalum content", "t tantalum content"),
    "tin": ("TIN", 1, 2, "t tin content", "t tin content"),
    "ree": ("RARE EARTHS", 1, 2, "t rare-earth oxide", "t rare-earth oxide"),
    "titanium": ("TITANIUM MINERAL CONCENTRATES", 1, 2, "thousand t TiO2 content (ilmenite)",
                 "thousand t TiO2 content (ilmenite)"),
    "zircon": ("ZIRCONIUM AND HAFNIUM", 1, 2, "thousand t zirconium mineral concentrates",
               "thousand t ZrO2 content"),
    "bauxite": ("BAUXITE AND ALUMINA", 3, 4, "thousand dry t bauxite", "thousand t bauxite"),
    "phosphate": ("PHOSPHATE ROCK", 1, 2, "thousand t marketable rock", "thousand t marketable rock"),
    "gold": ("GOLD", 1, 2, "t gold content", "t gold content"),
    "diamond": ("DIAMOND (INDUSTRIAL)", 1, 2, "million carats (industrial)", "million carats (industrial)"),
    "gem_diamond": ("GEMSTONES", 1, 2, "thousand carats (gem-quality diamonds)", None),
}

# the MCS's country names -> ISO2 (Africa only matters; the rest are named
# so a typo in a new edition shows up as unmatched rather than silently lost)
MCS_ISO = {
    "Algeria": "DZ", "Angola": "AO", "Botswana": "BW", "Burkina Faso": "BF", "Burundi": "BI",
    "Cameroon": "CM", "Congo (Brazzaville)": "CG", "Congo (Kinshasa)": "CD", "Côte d’Ivoire": "CI",
    "Côte d'Ivoire": "CI", "Egypt": "EG", "Eritrea": "ER", "Ethiopia": "ET", "Gabon": "GA",
    "Ghana": "GH", "Guinea": "GN", "Kenya": "KE", "Lesotho": "LS", "Liberia": "LR", "Madagascar": "MG",
    "Malawi": "MW", "Mali": "ML", "Mauritania": "MR", "Morocco": "MA", "Mozambique": "MZ",
    "Namibia": "NA", "Niger": "NE", "Nigeria": "NG", "Rwanda": "RW", "Senegal": "SN",
    "Sierra Leone": "SL", "South Africa": "ZA", "Sudan": "SD", "Tanzania": "TZ", "Togo": "TG",
    "Tunisia": "TN", "Uganda": "UG", "Zambia": "ZM", "Zimbabwe": "ZW",
    "United States": "US", "Australia": "AU", "Brazil": "BR", "Burma": "MM", "Canada": "CA",
    "China": "CN", "Chile": "CL", "Peru": "PE", "Russia": "RU", "India": "IN", "Indonesia": "ID",
    "Kazakhstan": "KZ", "Malaysia": "MY", "Philippines": "PH", "Turkey": "TR", "Vietnam": "VN",
    "Argentina": "AR", "Mexico": "MX", "Finland": "FI", "Greenland": "GL", "Thailand": "TH",
    "Cuba": "CU", "Papua New Guinea": "PG", "Jamaica": "JM", "Guinea-Bissau": "GW",
    "Saudi Arabia": "SA", "Jordan": "JO", "Iran": "IR", "Ukraine": "UA", "Norway": "NO",
    "Portugal": "PT", "Bolivia": "BO", "Korea, North": "KP", "Sri Lanka": "LK", "Uzbekistan": "UZ",
    "Korea, Republic of": "KR", "Germany": "DE", "Japan": "JP", "Poland": "PL", "New Caledonia": "NC",
    "Sweden": "SE", "Laos": "LA", "Greece": "GR", "Ireland": "IE", "Spain": "ES",
    "United Arab Emirates": "AE", "Israel": "IL", "Syria": "SY",
}


# --------------------------------------------------------------- helpers

def get(url, timeout=180, tries=3, wait=4):
    for attempt in range(tries):
        try:
            return _get(url, timeout=timeout)
        except (OSError, urllib.error.URLError):
            if attempt == tries - 1:
                raise
            time.sleep(wait * (attempt + 1))


def cached(name, url, timeout=300):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        path.write_bytes(get(url, timeout=timeout))
    return path


def load():
    return json.loads(OUT.read_text()) if OUT.exists() else {}


# ------------------------------------------------------------------ BGS

def bgs_rows(table):
    """Every production row of one BGS yearbook table, all years."""
    rows, offset = [], 0
    while True:
        q = {"f": "json", "limit": 10000, "offset": offset, "yearbook_table_trans": table,
             "bgs_statistic_type_trans": "Production"}
        d = json.loads(get(BGS_API + "?" + urllib.parse.urlencode(q), timeout=240))
        rows += [f["properties"] for f in d["features"]]
        if len(d["features"]) < 10000:
            return rows
        offset += 10000


def bgs_series(m, rows):
    """{iso2: {year: quantity}} for one mineral, per its sub-commodity rule."""
    _, subs = m["bgs"]
    per = {}
    for r in rows:
        y = int(r["year"][:4])
        iso = r["country_iso2_code"]
        if y < FIRST_YEAR or not iso or r["quantity"] is None:
            continue
        per.setdefault((iso, y), []).append((r.get("bgs_sub_commodity_trans"), r["quantity"]))
    out = {}
    for (iso, y), vals in per.items():
        if subs == "sum":
            q = sum(v for _, v in vals)
        elif subs == "partition":
            tot = [v for s, v in vals if s is None]
            q = tot[0] if tot else sum(v for _, v in vals)
        else:
            q = sum(v for s, v in vals if s in subs)
        if q:
            out.setdefault(iso, {})[y] = q
    return out


def fetch_bgs():
    out, units, years = {}, {}, set()
    tables = {}
    for m in MINERALS:
        if "bgs" not in m:
            continue
        t = m["bgs"][0]
        if t not in tables:
            print(f"  BGS  {t}")
            tables[t] = bgs_rows(t)
        rows = tables[t]
        s = bgs_series(m, rows)
        ys = sorted({y for v in s.values() for y in v})
        years |= set(ys)
        world = {y: sum(v.get(y, 0) for v in s.values()) for y in ys}
        afr = {y: sum(v.get(y, 0) for iso, v in s.items() if iso in AF) for y in ys}
        units[m["key"]] = sorted({r["units"] for r in rows})
        out[m["key"]] = {
            "years": ys,
            "world": [round(world[y], 3) for y in ys],
            "africa": [round(afr[y], 3) for y in ys],
            # every African producer's series, and the world's five largest
            # producers of the last year, for the page's context lines
            "countries": {iso: [round(v.get(y, 0), 3) for y in ys] for iso, v in sorted(s.items())
                          if iso in AF or iso in top_non_african(s, ys[-1])},
        }
        last = ys[-1]
        print(f"     {m['key']:10s} {last}: Africa {afr[last] / world[last] * 100:5.1f}% of {world[last]:,.0f}"
              f"  ({len([1 for iso, v in s.items() if iso in AF and v.get(last)])} African producers)")
    return {"source": "British Geological Survey, World Mineral Statistics", "url": BGS_PAGE,
            "api": BGS_API, "fetched": today(), "first_year": min(years), "last_year": max(years),
            "units": units, "minerals": out,
            "credit": "Contains British Geological Survey materials © UKRI 2026"}


def top_non_african(s, year, n=5):
    rank = sorted(((v.get(year, 0), iso) for iso, v in s.items() if iso not in AF), reverse=True)
    return {iso for _, iso in rank[:n]}


# ------------------------------------------------------------ USGS MCS

NUM = re.compile(r"^(>?[\d,]+(\.\d+)?|—|NA|W|XX)$")


def _lines(page):
    """A PDF page's lines as lists of word tokens, superscripts dropped."""
    rows = {}
    for c in page.chars:
        if c["size"] >= 7.5:
            rows.setdefault(round(c["top"] / 2.5), []).append(c)
    out = []
    for k in sorted(rows):
        cs = sorted(rows[k], key=lambda c: c["x0"])
        toks, cur = [], None
        for c in cs:
            if cur and c["x0"] - cur["x1"] < 2.2:
                cur["t"] += c["text"]
                cur["x1"] = c["x1"]
            else:
                if cur:
                    toks.append(cur)
                cur = {"t": c["text"], "x0": c["x0"], "x1": c["x1"]}
        if cur:
            toks.append(cur)
        toks = [dict(t, t=t["t"].strip()) for t in toks if t["t"].strip()]
        if toks:
            out.append(toks)
    return out


def _num(s):
    s = s.replace(" ", "")
    if s in ("—",):
        return 0.0
    if not re.match(r"^>?[\d,]+(\.\d+)?$", s):
        return None
    return float(s.lstrip(">").replace(",", ""))


def mcs_tables(path):
    import pdfplumber
    tables = {}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[30:]:
            L = _lines(page)
            if len(L) < 3:
                continue
            title = " ".join(t["t"] for t in L[1])
            start = next((j for j, toks in enumerate(L)
                          if re.match(r"World .*(Production|production|Capacity).*:", " ".join(t["t"] for t in toks))),
                         None)
            if start is None or title in tables:
                continue
            rows = []
            for toks in L[start + 1:]:
                s = " ".join(t["t"] for t in toks)
                if s.startswith("World Resources"):
                    break
                nums = [t["t"] for t in toks[1:] if NUM.match(t["t"].replace(" ", ""))]
                if s.startswith("World total"):
                    # "World total (ilmenite, rounded)" wraps its label over two tokens
                    rows.append(("World total", nums))
                    break
                if toks[0]["x0"] < 60 and nums and len(nums) == len(toks) - 1:
                    rows.append((toks[0]["t"], nums))
            tables[title] = rows
    return tables


def fetch_mcs():
    path = cached("mcs2026.pdf", MCS_PDF, timeout=600)
    tables = mcs_tables(path)
    out = {}
    for key, (chapter, pc, rc, punit, runit) in MCS.items():
        rows = tables.get(chapter)
        if not rows:
            sys.exit(f"MCS: chapter {chapter!r} not found")
        prod, res, other_p, other_r, unmatched = {}, {}, None, None, []
        world_p = world_r = None
        for name, nums in rows:
            p = _num(nums[pc]) if pc < len(nums) else None
            r = _num(nums[rc]) if rc is not None and rc < len(nums) else None
            if name.startswith("World total"):
                world_p, world_r = p, r
                continue
            if name.startswith("Other"):
                other_p, other_r = p, r
                continue
            iso = MCS_ISO.get(name.split(" (")[0].strip()) or MCS_ISO.get(name)
            if not iso:
                unmatched.append(name)
                continue
            if p is not None:
                prod[iso] = prod.get(iso, 0) + p
            if r is not None:
                res[iso] = res.get(iso, 0) + r
        africa_p = sum(v for k, v in prod.items() if k in AF)
        africa_r = sum(v for k, v in res.items() if k in AF)
        out[key] = {"chapter": chapter, "year": 2025, "prod_unit": punit, "res_unit": runit,
                    "world_prod": world_p, "world_res": world_r, "other_prod": other_p, "other_res": other_r,
                    "prod": {k: v for k, v in sorted(prod.items()) if v},
                    "res": {k: v for k, v in sorted(res.items()) if v} if runit else {},
                    "africa_prod": africa_p, "africa_res": africa_r if runit else None}
        msg = f"  MCS  {key:11s} 2025 Africa {africa_p:,.0f} of {world_p or 0:,.0f}"
        if runit and world_r:
            msg += f"; reserves {africa_r:,.0f} of {world_r:,.0f}"
        if unmatched:
            msg += f"   (not matched: {', '.join(unmatched)})"
        print(msg)
    return {"source": "U.S. Geological Survey, Mineral Commodity Summaries 2026", "url": MCS_PAGE,
            "pdf": MCS_PDF, "fetched": today(), "year": 2025, "minerals": out}


# ---------------------------------------------------------------- sites

# the two datasets' commodity names -> the page's minerals; anything else
# is kept as "other" with its own name
OFR_KEY = {
    "Gold": "gold", "Gold)": "gold", "Copper": "copper", "Cooper": "copper", "Copper-gold": "copper",
    "Copper-gold-molybdenum": "copper", "PGE": "pgm", "Iron": "iron", "Chromium": "chromium",
    "Phosphate": "phosphate", "Phosphorous-rare earths": "phosphate", "Manganese": "manganese",
    "Nickel": "nickel", "Diamond": "diamond", "Uranium": "uranium", "Titanium": "titanium",
    "Zirconium": "zircon", "Cobalt": "cobalt", "Columbium (Niobium)": "tantalum", "Tantalum": "tantalum",
    "Tin": "tin", "Aluminum": "bauxite", "REE": "ree", "Graphite": "graphite", "Lithium": "lithium",
    "Vanadium": "vanadium",
}
PP_KEY = {
    "Cobalt": "cobalt", "Platinum-Group Elements": "pgm", "Niobium and Tantalum": "tantalum",
    "Tin": "tin", "Lithium": "lithium", "Vanadium": "vanadium", "Rare-Earth Elements": "ree",
    "Graphite": "graphite", "Manganese": "manganese", "Titanium": "titanium",
    "Zirconium and Hafnium": "zircon",
}


def arc_geojson(layer):
    feats, offset = [], 0
    while True:
        q = {"where": "1=1", "outFields": "*", "geometry": "-26,-47,64,38", "geometryType": "esriGeometryEnvelope",
             "inSR": 4326, "outSR": 4326, "f": "geojson", "resultOffset": offset, "resultRecordCount": 1000}
        d = json.loads(get(layer + "/query?" + urllib.parse.urlencode(q), timeout=240))
        feats += d["features"]
        if len(d["features"]) < 1000:
            return feats
        offset += 1000


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class Countries:
    """Point-in-country on the site's 1:10m basemap, nearest border for a
    point just offshore (beach sands, a coastal mine)."""

    def __init__(self):
        bm = json.loads((DATA / "africa_basemap_10m.json").read_text())
        self.c = []
        for c in bm["countries"]:
            polys = c["p"]
            xs = [x for poly in polys for ring in poly for x, _ in ring]
            ys = [y for poly in polys for ring in poly for _, y in ring]
            self.c.append((c["iso"], polys, (min(xs), min(ys), max(xs), max(ys))))

    def at(self, lon, lat):
        for iso, polys, (x0, y0, x1, y1) in self.c:
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            for poly in polys:
                if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
                    return iso
        best, bd = None, 0.35          # degrees: about 35 km
        for iso, polys, (x0, y0, x1, y1) in self.c:
            if not (x0 - bd <= lon <= x1 + bd and y0 - bd <= lat <= y1 + bd):
                continue
            for poly in polys:
                for x, y in poly[0]:
                    d = math.hypot(x - lon, (y - lat))
                    if d < bd:
                        best, bd = iso, d
        return best


def fetch_sites():
    where = Countries()
    out = []
    print("  USGS major deposits (OFR 2005-1294)")
    for f in arc_geojson(OFR_LAYER):
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        iso = where.at(lon, lat)
        if iso not in AF:
            continue
        com = (p.get("commodity") or "").strip().rstrip(",")
        # one commodity or several ("Titanium, Zirconium, REE"), each mapped
        keys = sorted({OFR_KEY.get(c.strip(), "other") for c in com.split(",") if c.strip()} or {"other"})
        out.append({"name": p["dep_name"], "iso": iso, "lon": round(lon, 4), "lat": round(lat, 4),
                    "minerals": keys, "commodity": com,
                    "type": " · ".join(x for x in (p.get("dep_type"), p.get("type_detail")) if x and x != "None"),
                    "src": "ofr", "url": p.get("url") if p.get("url") not in (None, "None") else OFR_DOI})
    print("  USGS critical-mineral deposits (PP 1802)")
    for f in arc_geojson(PP_LAYER):
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        iso = where.at(lon, lat)
        if iso not in AF:
            continue
        coms = [c.strip() for c in (p.get("mineral") or "").split(";") if c.strip()]
        keys = sorted({PP_KEY.get(c, "other") for c in coms})
        out.append({"name": p["dep_name"], "iso": iso, "lon": round(lon, 4), "lat": round(lat, 4),
                    "minerals": keys, "commodity": "; ".join(coms),
                    "type": p.get("dep_type") if p.get("dep_type") not in (None, "None") else "",
                    "src": "pp1802", "url": PP_DOI})
    # the same deposit in both datasets: one point, both sources
    merged = []
    for s in out:
        twin = next((m for m in merged if m["src"] != s["src"]
                     and (set(m["minerals"]) & set(s["minerals"])) - {"other"}
                     and abs(m["lon"] - s["lon"]) < 0.08 and abs(m["lat"] - s["lat"]) < 0.08), None)
        if twin:
            twin["also"] = {"name": s["name"], "src": s["src"], "commodity": s["commodity"], "url": s["url"]}
            twin["minerals"] = sorted(set(twin["minerals"]) | set(s["minerals"]))
            continue
        merged.append(s)
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [s.pop("lon"), s.pop("lat")]},
              "properties": s} for s in merged]
    SITES.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False,
                                separators=(",", ":")))
    print(f"  -> {SITES.relative_to(DATA.parent)}  {len(feats)} deposits ({len(out) - len(merged)} merged twins)")
    return {"sources": [
        {"id": "ofr", "name": "USGS Open-File Report 2005-1294, Major mineral deposits of Africa and the Middle East",
         "url": OFR_DOI, "service": OFR_LAYER},
        {"id": "pp1802", "name": "USGS Professional Paper 1802 (2017), global distribution of critical-mineral "
                                 "mines, deposits and districts", "url": PP_DOI, "service": PP_LAYER}],
        "fetched": today(), "count": len(feats)}


# ---------------------------------------------------------------- trade

# What leaves the continent, mineral by mineral: the HS headings of the ore
# and of the first product made from it near the mine. Mirror data: what
# importers report from each African country of origin. Rare earths are not
# here: Africa's concentrates ship under headings shared with other ores
# (2530.90, 2617), and its trade in rare-earth compounds (2846) is nil.
TRADE = [
    # key, label, HS codes, what they hold, the page's minerals whose African
    # producers are asked about, and other countries of origin worth asking
    ("cobalt", "Cobalt", ["2605", "8105", "282200"], "ores, hydroxide and other intermediates, unwrought metal",
     ["cobalt"], {"ZA"}),
    ("copper", "Copper", ["2603", "7402", "7403"], "ores, blister and anodes, refined cathodes", ["copper"], set()),
    ("pgm", "Platinum-group metals", ["7110"], "unwrought and semi-manufactured", ["platinum", "palladium"], set()),
    ("manganese", "Manganese", ["2602"], "ores and concentrates", ["manganese"], set()),
    ("chromium", "Chromium", ["2610", "720241", "720249"], "ores, concentrates and ferrochrome", ["chromium"], set()),
    ("bauxite", "Bauxite", ["2606"], "aluminium ores and concentrates", ["bauxite"], set()),
    ("iron", "Iron ore", ["2601"], "ores, concentrates and pellets", ["iron"], set()),
    ("lithium", "Lithium", ["253090", "283691", "282520"],
     "spodumene and other ores (HS 2530.90, which also holds other minerals), carbonate, hydroxide",
     ["lithium"], {"NG", "NA", "MZ", "RW", "CD", "ET", "ZA"}),
    ("graphite", "Graphite", ["2504"], "natural graphite", ["graphite"], {"TZ", "MZ", "MG"}),
    ("tantalum", "Tantalum, niobium, tin", ["261590", "2609"], "niobium-tantalum ores, tin ores",
     ["tantalum", "tin"], {"UG", "SL", "NA", "ET", "MZ"}),
    ("sands", "Titanium and zircon", ["2614", "261510"], "titanium ores, zirconium ores",
     ["titanium", "zircon"], set()),
    ("uranium", "Uranium", ["2612", "284410"], "ores, concentrates and natural uranium", ["uranium"], {"MW"}),
    ("phosphate", "Phosphate rock", ["2510"], "natural phosphates", ["phosphate"], set()),
    ("gold", "Gold", ["7108"], "non-monetary gold, unwrought or semi-manufactured", ["gold"], set()),
    ("diamond", "Diamonds", ["7102"], "rough and polished, unmounted", ["diamond"], set()),
]


def producers(pack, keys):
    """The African countries that mine any of these minerals, per the BGS
    series (any year since 2015) or the USGS tables."""
    out = set()
    for k in keys:
        b = pack.get("bgs", {}).get("minerals", {}).get(k)
        if b:
            n = len(b["years"])
            out |= {iso for iso, s in b["countries"].items() if iso in AF and any(s[max(0, n - 10):])}
        u = pack.get("mcs", {}).get("minerals", {}).get(k)
        if u:
            out |= {iso for iso in u["prod"] if iso in AF}
    return out

EU27 = set("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())
GULF = {"AE", "SA", "QA", "OM", "KW", "BH"}
DEST = [
    # group, label, members; the order is the stacking order on the page
    ("china", "China", {"CN", "HK", "MO"}),
    ("europe", "Europe", EU27 | {"GB", "CH", "NO", "IS", "LI"}),
    ("gulf", "Gulf states", GULF),
    ("india", "India", {"IN"}),
    ("us", "United States", {"US"}),
    ("eastasia", "Japan and South Korea", {"JP", "KR"}),
    ("africa", "Other African countries", AF),
    ("other", "Everywhere else", None),
]


def dest_of(iso):
    for g, _, members in DEST:
        if members is not None and iso in members:
            return g
    return "other"


def comtrade(params):
    """One preview call, cached on disk: the preview allows about one call a
    second and answers 429 past it, so a rerun picks up where it stopped."""
    url = COMTRADE + "?" + urllib.parse.urlencode(params, safe=",")
    path = CACHE / "comtrade" / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".json")
    if path.exists():
        return json.loads(path.read_text())
    for attempt in range(12):
        try:
            d = json.loads(get(url, timeout=120, tries=1))
            if "data" in d:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(d["data"]))
                time.sleep(1.5)
                return d["data"]
        except urllib.error.HTTPError as e:
            # 429: too fast, try again in a second or two; 403 with Retry-After:
            # the hourly call quota is spent, wait for it to refill
            wait = int(e.headers.get("Retry-After") or 0) if e.headers else 0
            if e.code == 403 and 0 < wait <= 3700:
                print(f"    Comtrade call quota spent; waiting {wait // 60 + 1} min for it to refill", flush=True)
                time.sleep(wait + 5)
                continue
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(min(90, 6 * (attempt + 1)))
    sys.exit(f"Comtrade: no answer for {url} (rerun: answers so far are cached)")


def fetch_trade(pack):
    ref = json.loads(get(COMTRADE_REF.format("partnerAreas")))["results"]
    rep = json.loads(get(COMTRADE_REF.format("Reporters")))["results"]
    m49 = {x["PartnerCodeIsoAlpha2"]: x["PartnerCode"] for x in ref
           if x.get("PartnerCodeIsoAlpha2") and not x.get("isGroup")}
    iso_of = {x["reporterCode"]: x.get("reporterCodeIsoAlpha2") for x in rep if not x.get("isGroup")}
    out, seen = {}, set()      # seen: every country that reported imports this year
    for key, label, codes, what, mins, extra in TRADE:
        partners = [(iso, m49[iso]) for iso in sorted(producers(pack, mins) | extra) if iso in m49]
        flows = {}             # exporter -> destination group -> USD
        tops = {}              # exporter -> importer -> USD (for the tooltip's leading buyer)
        kg = {}                # exporter -> net weight, kg

        def run(chunk):
            rows = comtrade({"period": TRADE_YEAR, "partnerCode": ",".join(str(c) for _, c in chunk),
                             "cmdCode": ",".join(codes), "flowCode": "M"})
            if len(rows) >= 500 and len(chunk) > 1:        # the preview's cap: split and ask again
                half = len(chunk) // 2
                run(chunk[:half])
                run(chunk[half:])
                return
            back = {c: iso for iso, c in chunk}
            for r in rows:
                if r.get("partner2Code") not in (0, None) or r.get("motCode") not in (0, None) \
                        or r.get("customsCode") not in ("C00", None):
                    continue
                exp, imp = back.get(r["partnerCode"]), iso_of.get(r["reporterCode"])
                v = r.get("primaryValue") or 0
                if not exp or not imp or imp == exp or not v:
                    continue
                seen.add(imp)
                kg[exp] = kg.get(exp, 0) + (r.get("netWgt") or 0)
                g = dest_of(imp)
                flows.setdefault(exp, {}).setdefault(g, 0)
                flows[exp][g] += v
                tops.setdefault(exp, {}).setdefault(imp, 0)
                tops[exp][imp] += v

        for i in range(0, len(partners), 12):
            run(partners[i:i + 12])
        total = {g: round(sum(f.get(g, 0) for f in flows.values())) for g, _, _ in DEST}
        out[key] = {"label": label, "hs": codes, "what": what, "total": total,
                    "asked": [iso for iso, _ in partners], "kg": {e: round(v) for e, v in sorted(kg.items()) if v},
                    "by_exporter": {e: {g: round(v) for g, v in f.items()} for e, f in sorted(flows.items())},
                    "top_buyer": {e: max(t.items(), key=lambda kv: kv[1])[0] for e, t in tops.items()}}
        s = sum(total.values())
        print(f"  Comtrade {key:10s} {s / 1e9:7.2f} bn USD  China {total['china'] / s * 100 if s else 0:4.1f}%"
              f"  Europe {total['europe'] / s * 100 if s else 0:4.1f}%")
    # The United Arab Emirates, the first stop for much of Africa's gold and
    # many of its diamonds, had not reported 2024 to UN Comtrade when this was
    # fetched. Its last reported year is kept apart, for the page's notes,
    # never added into the bars.
    uae = None
    reporters = seen
    if "AE" not in reporters:
        m49_af = ",".join(str(m49[iso]) for iso in sorted(AF) if iso in m49)
        back = {m49[iso]: iso for iso in AF if iso in m49}
        for year in (TRADE_YEAR - 1, TRADE_YEAR - 2):
            rows = comtrade({"reporterCode": 784, "period": year, "partnerCode": m49_af, "cmdCode": "7108,7102",
                             "flowCode": "M"})
            rows = [r for r in rows if r.get("partner2Code") in (0, None) and r.get("motCode") in (0, None)
                    and r.get("customsCode") in ("C00", None)]
            if rows:
                uae = {"year": year}
                for code, key in (("7108", "gold"), ("7102", "diamond")):
                    by = {}
                    for r in rows:
                        if r["cmdCode"] == code and r.get("primaryValue"):
                            iso = back.get(r["partnerCode"])
                            by[iso] = by.get(iso, 0) + r["primaryValue"]
                    uae[key] = {"total": round(sum(by.values())), "by": {k: round(v) for k, v in by.items() if k}}
                print(f"  UAE not in {TRADE_YEAR}; its {year} imports from Africa: gold {uae['gold']['total'] / 1e9:.1f} bn,"
                      f" diamonds {uae['diamond']['total'] / 1e9:.1f} bn USD")
                break
    return {"source": "UN Comtrade (public preview API), imports reported by partner countries",
            "url": "https://comtradeplus.un.org/", "year": TRADE_YEAR, "fetched": today(),
            "groups": [{"id": g, "label": lab} for g, lab, _ in DEST], "minerals": out,
            "reporters": sorted(r for r in reporters if r), "uae_missing": uae}


# ----------------------------------------------------------- facilities
#
# The USGS "Compilation of Geospatial Data (GIS) for the Mineral Industries
# and Related Infrastructure of Africa" (2021, DOI 10.5066/P97EQWXP): every
# mine and processing plant in the USGS Minerals Yearbook country chapters,
# located, with operator, equity owners, capacity and status, for the 2018
# reference year. ScienceBase serves it behind a bot check, so it is
# downloaded by hand: put "Africa_GIS Supporting Data.zip" in data/ (it is
# gitignored, ~490 MB). Its shapefiles' attribute tables (.dbf) are read
# straight from the nested zips; the coordinates are in the attributes.

AFRICA_GIS = DATA / "Africa_GIS Supporting Data.zip"
AFRICA_GIS_DOI = "https://doi.org/10.5066/P97EQWXP"
FACILITIES = DATA / "minerals_facilities.geojson"
EXPLORATION = DATA / "minerals_exploration.geojson"

# the facilities' commodity names -> the page's minerals; a facility with
# none of these is "other" (cement, salt, aggregates, steel, coal...)
FAC_KEY = {
    "Cobalt": "cobalt", "Copper": "copper", "Platinum": "pgm", "Palladium": "pgm", "Rhodium": "pgm",
    "Iridium": "pgm", "Ruthenium": "pgm", "Manganese": "manganese", "Ferromanganese": "manganese",
    "Chromium": "chromium", "Gold": "gold", "Diamond": "diamond", "Bauxite": "bauxite", "Alumina": "bauxite",
    "Aluminum": "bauxite", "Iron ore": "iron", "Phosphate": "phosphate", "Titanium": "titanium",
    "Zirconium": "zircon", "Lithium": "lithium", "Graphite": "graphite", "Tantalum": "tantalum",
    "Niobium (columbium)": "tantalum", "Niobium (columbium) and tantalum": "tantalum",
    "Tantalum and niobium (columbium)": "tantalum", "Tin": "tin", "Rare Earth elements (REE)": "ree",
    "Uranium": "uranium", "Vanadium": "vanadium", "Nickel": "nickel",
}
# the exploration sites spell commodities their own way
EXP_KEY = dict(FAC_KEY, **{
    "Platinum-group elements (PGE)": "pgm", "Iron Ore": "iron", "Chromium (chromite)": "chromium",
    "Diamonds": "diamond", "Rutile": "titanium", "Ilmenite": "titanium", "Zircon": "zircon",
    "Heavy minerals": "titanium", "Heavy Minerals": "titanium",
})
FUEL_KEPT = {"Coal", "Uranium"}          # mined fuels; oil and gas are not this page's
FAC_TYPE = {"Mines and Quarries": "mine", "Brine": "mine", "Mineral Processing Plants": "plant"}
USGS_COUNTRY = dict(MCS_ISO, **{"Eswatini": "SZ", "Cabo Verde": "CV", "Western Sahara": "EH", "Libya": "LY",
                                "Chad": "TD", "Benin": "BJ", "Djibouti": "DJ", "Equatorial Guinea": "GQ",
                                "Central African Republic": "CF", "Somalia": "SO", "Seychelles": "SC",
                                "Mauritius": "MU", "South Sudan": "SS", "Reunion": "RE", "Gambia, The": "GM",
                                "The Gambia": "GM", "Guinea-Bissau": "GW", "Sao Tome and Principe": "ST",
                                "Comoros": "KM", "Lesotho": "LS", "Eritrea": "ER"})


def read_dbf(data, enc="utf-8"):
    """The records of a dBase III table, as dicts; numbers as floats."""
    import struct
    n, hlen, rlen = struct.unpack("<xxxxIHH", data[:12])
    fields, pos = [], 32
    while data[pos] != 0x0D:
        fields.append((data[pos:pos + 11].split(b"\0")[0].decode(), chr(data[pos + 11]), data[pos + 16]))
        pos += 32
    rows = []
    for i in range(n):
        rec = data[hlen + i * rlen: hlen + (i + 1) * rlen]
        if rec[:1] == b"*":                 # deleted
            continue
        p, row = 1, {}
        for name, typ, ln in fields:
            raw = rec[p:p + ln].decode(enc, "replace").strip()
            p += ln
            if typ in "NF":
                try:
                    raw = float(raw) if raw else None
                except ValueError:
                    raw = None
            elif raw in ("<null>", "NA", "<< empty cell >>"):
                raw = ""
            row[name] = raw
        rows.append(row)
    return rows


def africa_gis_table(stem):
    import io
    import zipfile
    with zipfile.ZipFile(AFRICA_GIS) as outer:
        inner = next(n for n in outer.namelist() if n.endswith(f"/{stem}.shp.zip"))
        with zipfile.ZipFile(io.BytesIO(outer.read(inner))) as z:
            return read_dbf(z.read(f"{stem}.dbf"))


def _owner(v):
    m = re.match(r"^(.*?)\s*\[([\d.]+)\s*%?\]\s*$", v or "")
    if m:
        return {"name": m.group(1).strip(), "stake": float(m.group(2))}
    return {"name": (v or "").strip(), "stake": None}


def fetch_facilities():
    if not AFRICA_GIS.exists():
        print(f"  {AFRICA_GIS.name} not in data/: download it by hand from {AFRICA_GIS_DOI} (ScienceBase)")
        return None
    where = Countries()
    rows = africa_gis_table("AFR_Mineral_Facilities")
    print(f"  USGS mineral facilities: {len(rows)} rows")
    by = {}
    for r in rows:
        kind = FAC_TYPE.get(r["FeatureTyp"])
        com = r["DsgAttr02"]
        if not kind or (r["DsgAttr01"] == "Fuel" and com not in FUEL_KEPT):
            continue
        lon, lat = r["Longitude"], r["Latitude"]
        if lon is None or lat is None:
            continue
        iso = USGS_COUNTRY.get(r["Country"]) or where.at(lon, lat)
        k = (r["FeatureNam"], iso, round(lat, 3), round(lon, 3))
        f = by.setdefault(k, {"name": r["FeatureNam"], "iso": iso, "lon": round(lon, 4), "lat": round(lat, 4),
                              "kind": kind, "ids": [], "minerals": set(), "items": [], "status": set(),
                              "operator": r["OperateNam"], "owners": [], "year": int(r["DsgAttr06"] or 0),
                              "approx": r["LocConfid"] == "E", "where": r["MemoLoc"], "adm1": r["ADM1"],
                              "source": r["InfSource1"]})
        if kind == "mine":
            f["kind"] = "mine"              # a site with a mine and a plant counts as a mine
        f["ids"].append(r["FeatureUID"])
        f["minerals"].add(FAC_KEY.get(com, "other"))
        f["status"].add(r["LocOpStat"])
        cap = r["DsgAttr07"]
        f["items"].append({"commodity": com, "product": r["DsgAttr03"] if r["DsgAttr03"] != "Unspecified" else "",
                           "capacity": cap if cap not in (None, -999) else None,
                           "unit": r["DsgAttr08"] if r["DsgAttr08"] not in ("", "NA") else "",
                           "shared": bool(r["DsgAttr10"]), "note": r["MemoOther"]})
        for k2 in ("OwnerName1", "OwnerName2", "OwnerName3", "OwnerName4"):
            o = _owner(r[k2])
            if o["name"] and o["name"] not in {x["name"] for x in f["owners"]}:
                f["owners"].append(o)
    feats = []
    for f in by.values():
        st = f.pop("status")
        # one status per site: the least active one reported for any of its lines
        for s in ("Closed", "Suspended", "C&M", "Construction", "Development", "Active", "Assumed Active"):
            if s in st:
                f["status"] = s
        mins = f.pop("minerals")
        f["minerals"] = sorted(mins - {"other"}) or ["other"]
        if not f["owners"] and f["operator"]:
            f["owners"] = [{"name": f["operator"], "stake": None}]
        lon, lat = f.pop("lon"), f.pop("lat")
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": f})
    FACILITIES.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False,
                                     separators=(",", ":")))
    n_mine = sum(1 for f in feats if f["properties"]["kind"] == "mine")
    print(f"  -> {FACILITIES.relative_to(DATA.parent)}  {len(feats)} sites ({n_mine} mines, {len(feats) - n_mine} plants)")

    exp = []
    for r in africa_gis_table("AFR_Mineral_Exploration"):
        lon, lat = r["Longitude"], r["Latitude"]
        if lon is None or lat is None:
            continue
        coms = [r[f"DsgAttr0{i}"] for i in range(1, 9) if r.get(f"DsgAttr0{i}")]
        keys = sorted({EXP_KEY.get(c, "other") for c in coms} - {"other"}) or ["other"]
        exp.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 4), round(lat, 4)]},
                    "properties": {"name": r["FeatureNam"], "iso": USGS_COUNTRY.get(r["Country"]) or where.at(lon, lat),
                                   "stage": r["LocOpStat"], "commodity": ", ".join(coms), "minerals": keys,
                                   "owner": r["OwnerName"], "owner_type": r["DsgAttr09"],
                                   "share": r["DsgAttr10"] or None,
                                   "verified": int(r["DsgAttr11"]) if r["DsgAttr11"] else None}})
    EXPLORATION.write_text(json.dumps({"type": "FeatureCollection", "features": exp}, ensure_ascii=False,
                                      separators=(",", ":")))
    print(f"  -> {EXPLORATION.relative_to(DATA.parent)}  {len(exp)} exploration and development sites")
    return {"source": "USGS, Compilation of Geospatial Data (GIS) for the Mineral Industries and Related "
                      "Infrastructure of Africa (2021)", "url": AFRICA_GIS_DOI, "reference_year": 2018,
            "fetched": today(), "sites": len(feats), "mines": n_mine, "exploration": len(exp)}


# ------------------------------------------------------------------ main

def main():
    parts = sys.argv[1:] or ["bgs", "mcs", "sites", "trade", "facilities"]
    pack = load()
    pack.update({"about": "Minerals and mining in Africa, from official statistics: BGS, USGS, UN Comtrade.",
                 "minerals": [{k: m[k] for k in ("key", "name", "fam", "unit")} | {"src": m.get("src", "bgs")}
                              for m in MINERALS],
                 "families": [{"id": f, "label": lab} for f, lab in FAMILIES]})
    if "bgs" in parts:
        print("BGS world mineral statistics")
        pack["bgs"] = fetch_bgs()
    if "mcs" in parts:
        print("USGS Mineral Commodity Summaries 2026")
        pack["mcs"] = fetch_mcs()
    if "sites" in parts:
        print("USGS deposits")
        pack["sites"] = fetch_sites()
    if "trade" in parts:
        print(f"UN Comtrade, {TRADE_YEAR}")
        pack["trade"] = fetch_trade(pack)
    if "facilities" in parts:
        print("USGS mineral facilities of Africa (2018 reference year)")
        fac = fetch_facilities()
        if fac:
            pack["facilities"] = fac
    pack["fetched"] = today()
    OUT.write_text(json.dumps(pack, ensure_ascii=False, separators=(",", ":")))
    print(f"-> {OUT.relative_to(DATA.parent)}  {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
