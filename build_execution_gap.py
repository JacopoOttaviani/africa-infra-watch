#!/usr/bin/env python3
"""
Build the execution-gap page, docs/execution-gap/index.html: what is announced
against what breaks ground in Africa's power pipeline, drawn from two datasets
the site already holds, Global Energy Monitor's Global Integrated Power
Tracker (data/gem_power_assets.geojson) and AidData's China's Global Loans and
Grants Dataset 1.0 (data/aiddata_china_finance.geojson).

    python3 build_execution_gap.py

The page is the prototype of the first investor niche in
brand/investor-niches.md (survey of 2026-10-17): hypotheses 1, 2, 4 and 5 of
that note, each as one view. It is not linked from the site: it is in no menu,
not in the sitemap or llms.txt, and its <meta robots> says noindex, nofollow.
To publish it, add ("execution-gap", TITLE, ..., "execution_gap.json") to
DEEP_THEMES in shared.py, add this script to refresh.py's build list and drop
the NOINDEX swap below.

Every figure on the page is recomputed here from the two GeoJSON files; the
page writes its own payload, docs/data/execution_gap.json, with the tables
behind every chart, and touches no other file. It wears the lender profiles'
frame (donor.template.html), as build_debt.py and build_corridors.py do; the
charts are drawn here as inline SVG, so the page reads without scripts, and
the section's own script only shows their tooltips.
"""

import json
import pathlib
import re
import statistics
import sys

from build_donors import FRAME, esc, table, td
from fetch_donors import (CHINESE_OWNER, FRENCH_OWNER, GERMAN_OWNER, GULF_OWNER, ITALIAN_OWNER, JAPANESE_OWNER,
                          NAME, NORDIC_OWNER, SPANISH_OWNER, TURKISH_OWNER, US_OWNER)
from headmap import africa_map, figure, head_wrap
from shared import (AUTHOR_NAME, AUTHOR_URL, DATA, DOCS, SITE_NAME, SITE_URL, WEB_URL, brand_assets, fmt_date,
                    load_meta, site_url, today, wrap_document)

ROOT = pathlib.Path(__file__).parent
GEM = DATA / "gem_power_assets.geojson"
AIDDATA = DATA / "aiddata_china_finance.geojson"
FRAG = ROOT / "sections" / "execution_gap.html"
SLUG = "execution-gap"
PAYLOAD_FILE = "execution_gap.json"
TITLE = "The execution gap"
DESCRIPTION = ("Africa's power pipeline, announced against built: how many gigawatts are on paper, under "
               "construction, operating or stalled, by technology, country and owner, from Global Energy "
               "Monitor's tracker, and how long a Chinese-financed project takes from commitment to completion, "
               "from AidData.")

# Copied from build_lobito.py: the robots meta wrap_document writes, and what
# an unlinked page says instead.
NOINDEX = ('<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">',
           '<meta name="robots" content="noindex,nofollow">')

# the site's status vocabulary, in pipeline order
STATUSES = ["announced", "approved", "under_construction", "operating", "stalled"]
ST_NAME = {"announced": "Announced", "approved": "Approved", "under_construction": "Under construction",
           "operating": "Operating", "stalled": "Stalled"}
PAPER = ("announced", "approved")

# GEM's own statuses and how fetch_sources.GEM_STATUS folds them into the five;
# printed on the page, never changed here.
GEM_FOLD = [("announced", "announced"), ("pre-construction, permitted", "approved"), ("construction", "under_construction"),
            ("operating, retired", "operating"), ("cancelled, shelved, mothballed", "stalled")]

# ------------------------------------------------------------ technologies

# GEM's `tech` field (its tech-type, or the fuel where the tracker has no
# type) folded into nine groups. The wind tracker writes "Unknown" where the
# mount type is not known and the geothermal tracker "unknown type"; both are
# checked against the unit's name at build time. A lower-case "unknown" is a
# unit GEM gives no technology at all: those are sorted by the words in their
# name (NAME_RULE) and the rest stay "not stated".
TECH_GROUP = {
    "PV": "solar", "Assumed PV": "solar",
    "Solar Thermal": "csp",
    "Onshore": "wind", "Offshore mount unknown": "wind", "Offshore floating": "wind", "Unknown": "wind",
    "gas turbine": "gasoil", "combined cycle": "gasoil", "steam turbine": "gasoil", "internal combustion": "gasoil",
    "ICCC": "gasoil", "ISCC": "gasoil",
    "subcritical": "coal", "supercritical": "coal", "ultra-supercritical": "coal",
    "run-of-river": "hydro", "conventional storage": "hydro", "pumped storage": "hydro",
    "conventional and run-of-river": "hydro",
    "pressurized water reactor": "nuclear",
    "flash steam - single": "geo", "flash steam - unknown": "geo", "binary cycle": "geo", "unknown type": "geo",
}
PLACEHOLDER_CHECK = {"Unknown": r"wind", "unknown type": r"geotherm"}
NAME_RULE = [("nuclear", r"nuclear"), ("hydro", r"hydro"), ("coal", r"coal"), ("wind", r"\bwind"),
             ("solar", r"solar|photovolta"), ("geo", r"geotherm"), ("gasoil", r"\bgas\b|\bLNG\b|diesel|\bHFO\b|\boil\b")]
TECH_NAME = {"solar": "Solar PV", "wind": "Wind", "gasoil": "Gas and oil", "coal": "Coal", "hydro": "Hydro",
             "nuclear": "Nuclear", "csp": "Solar thermal", "geo": "Geothermal", "bio": "Bioenergy",
             "unknown": "Not stated"}


def tech_group(p):
    t = (p.get("tech") or "").strip()
    if t.startswith("bioenergy"):
        return "bio", False
    if t in TECH_GROUP:
        return TECH_GROUP[t], False
    name = p.get("name") or ""
    for g, rx in NAME_RULE:
        if re.search(rx, name, re.I):
            return g, True
    return "unknown", True


# ------------------------------------------------------------ owner groups

# The lender profiles' owner lists (fetch_donors.py), in the order a unit
# that matches several is coloured by. A unit counts in every group its owner
# string matches, which is how the survey's figures were reached.
OWNER_GROUPS = [("china", "China", CHINESE_OWNER), ("gulf", "Gulf states", GULF_OWNER),
                ("france", "France", FRENCH_OWNER), ("nordics", "Nordic countries", NORDIC_OWNER),
                ("italy", "Italy", ITALIAN_OWNER), ("germany", "Germany", GERMAN_OWNER),
                ("spain", "Spain", SPANISH_OWNER), ("turkey", "Türkiye", TURKISH_OWNER),
                ("usa", "United States", US_OWNER), ("japan", "Japan", JAPANESE_OWNER)]
G_NAME = {k: n for k, n, _ in OWNER_GROUPS}
# the colour groups of the solar chart: three validated hues (China, Europe,
# the Gulf), a fourth for the other states only if one appears, grey for a
# named owner no list resolves, hollow for no owner at all
HOME = {"china": "china", "gulf": "gulf", "france": "europe", "nordics": "europe", "italy": "europe",
        "germany": "europe", "spain": "europe", "turkey": "other", "usa": "other", "japan": "other"}
HOME_ORDER = ["china", "europe", "gulf", "other", "unresolved", "blank"]
HOME_NAME = {"china": "China", "europe": "Europe", "gulf": "Gulf states", "other": "Other states",
             "unresolved": "Named owner, home not on the lists", "blank": "No owner stated"}

# Green-hydrogen schemes, by name: GEM files their solar and wind halves as
# ordinary units. Each match is listed in the payload so the tag can be checked.
H2_RE = re.compile(r"hydrogen|hydrog[eè]ne|\bH2\b|Megaton Moon|\bAMAN\b|Conjuncta|Project Nour|Hyphen|Zhero|NAYRAH|"
                   r"White Dunes|Tsau", re.I)

# Owner names the lists miss, and one they catch wrongly: named in the
# caveats with their capacity on paper, read from the data at build time.
MISSES = [("Total Eren", re.compile(r"Total Eren", re.I)),
          ("HDF Energy", re.compile(r"HDF Energy|Hydrog[eè]ne de France", re.I)),
          ("Copenhagen Infrastructure Partners", re.compile(r"Copenhagen Infrastructure", re.I))]
FALSE_POSITIVE = ("Libyan General Electric Company", re.compile(r"Libyan General Electric", re.I))

NAME2ISO = {v: k for k, v in NAME.items()}
NAME2ISO.update({"Western Sahara": "EH", "Sao Tome and Principe": "ST"})


# ------------------------------------------------------------ the data

def mw(p):
    try:
        return float(p.get("capacity_mw") or 0)
    except (TypeError, ValueError):
        return 0.0


def gw(v, dp=None):
    """Megawatts as gigawatts: one decimal under 1,000 GW, none above, so
    that the parts a sentence states add up to the total it states."""
    g = v / 1000
    if dp is None:
        dp = 1 if g < 1000 else 0
    return f"{g:,.{dp}f}"


def pct(part, whole):
    return part / whole * 100 if whole else 0.0


def load():
    for f in (GEM, AIDDATA):
        if not f.exists():
            sys.exit(f"missing {f.relative_to(ROOT)} — run fetch_sources.py first")
    units = [f["properties"] for f in json.loads(GEM.read_text())["features"]]
    recs = [f["properties"] for f in json.loads(AIDDATA.read_text())["features"]]
    for p in units:
        if p.get("dash_status") not in ST_NAME:
            sys.exit(f"execution-gap: unknown status {p.get('dash_status')!r} on {p.get('name')!r}")
        t = (p.get("tech") or "").strip()
        if t in PLACEHOLDER_CHECK and not re.search(PLACEHOLDER_CHECK[t], p.get("name") or "", re.I):
            sys.exit(f"execution-gap: GEM tech {t!r} is read as a placeholder but {p.get('name')!r} is not one")
        p["_mw"] = mw(p)
        p["_tech"], p["_by_name"] = tech_group(p)
        owner = str(p.get("owner") or "").strip()
        p["_owner"] = owner
        p["_groups"] = [k for k, _, rx in OWNER_GROUPS if rx.search(owner)]
        p["_home"] = HOME[p["_groups"][0]] if p["_groups"] else ("unresolved" if owner else "blank")
        p["_h2"] = bool(H2_RE.search((p.get("name") or "") + " " + owner))
    return units, recs


def short_owner(o):
    """'Scatec ASA [50%]; other [2%]; Greenstreet' → 'Scatec ASA +2'."""
    parts = [re.sub(r"\s*\[[^\]]*\]?\s*", " ", x).strip() for x in o.split(";")]
    parts = [x for x in parts if x and x.lower() not in ("other", "unknown")]
    if not parts:
        return "Unnamed"
    head = re.sub(r"\s*\((.*?)\)\s*$", "", parts[0]).strip()
    return head + (f" +{len(parts) - 1}" if len(parts) > 1 else "")


def prose_owner(o):
    """'Conjuncta; Infinity Power AS' → 'Conjuncta and Infinity Power AS', shares dropped."""
    parts = [re.sub(r"\s*\[[^\]]*\]?\s*", " ", x).strip() for x in o.split(";")]
    parts = [x for x in parts if x and x.lower() not in ("other", "unknown")]
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + (parts[-1] if parts else "Unnamed")


WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def times(a, b):
    """A ratio as prose: 'three times', 'half', '12 times'."""
    if not b:
        return "–"
    r = a / b
    if r < 0.75:
        return f"{WORDS.get(round(1 / r), round(1 / r))} times less than" if r else "none of"
    n = round(r)
    return f"{WORDS.get(n, n)} times" if n > 1 else "about as much as"


# ------------------------------------------------------------ SVG helpers

def text_w(s, size=11):
    return len(s) * size * 0.58


def svg_open(id_, W, H, label, cls="eg"):
    return f'<svg id="{id_}" class="{cls}" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">'


def seg_rect(x, w, y, h, cls, style="", gap=2):
    """A stacked segment with a surface gap on its left; a segment thinner
    than the gap keeps half a pixel so the stack still shows it."""
    x0, w0 = x + gap / 2, max(w - gap, 0.5)
    return f'<rect class="{cls}" x="{x0:.1f}" y="{y:.1f}" width="{w0:.1f}" height="{h:.1f}"{style}></rect>'


def tip_rows(rows):
    return "<br>".join(rows)


# ------------------------------------------------------------ view 1: by stage

def status_totals(units):
    tot = {s: 0.0 for s in STATUSES}
    n = {s: 0 for s in STATUSES}
    for p in units:
        tot[p["dash_status"]] += p["_mw"]
        n[p["dash_status"]] += 1
    return tot, n


def headline_bar(tot, n):
    """One bar of the whole tracker, every unit's capacity by stage."""
    W, H, L, R = 880, 92, 4, 4
    y0, bh = 40, 26
    total = sum(tot.values())
    out = [svg_open("c-head", W, H, f"One bar of Africa's {gw(total)} GW of power capacity in GEM's tracker, split "
                                    f"by stage: announced, approved, under construction, operating, stalled")]
    x = L
    paper_w = 0.0
    for s in STATUSES:
        w = tot[s] / total * (W - L - R)
        tip = f"<b>{ST_NAME[s]}</b>{gw(tot[s])} GW in {n[s]:,} units · {pct(tot[s], total):.0f}% of the tracker"
        out.append(f'<g data-tip="{esc(tip)}">{seg_rect(x, w, y0, bh, f"seg {s}")}')
        label = f"{ST_NAME[s]} {gw(tot[s])} GW"
        if w >= text_w(label, 11) + 14:
            out.append(f'<text class="inl on-{s}" x="{x + w / 2:.1f}" y="{y0 + bh / 2 + 4:.1f}" '
                       f'text-anchor="middle">{esc(label)}</text>')
        elif w >= text_w(gw(tot[s]), 11) + 10:
            out.append(f'<text class="inl on-{s}" x="{x + w / 2:.1f}" y="{y0 + bh / 2 + 4:.1f}" '
                       f'text-anchor="middle">{gw(tot[s])}</text>')
        out.append("</g>")
        if s in PAPER:
            paper_w += w
        x += w
    paper = tot["announced"] + tot["approved"]
    # a bracket over the two paper stages
    out.append(f'<path class="brk" d="M{L + 1} {y0 - 10} v-8 H{L + paper_w - 1:.1f} v8"></path>'
               f'<text class="brl" x="{L + paper_w / 2:.1f}" y="{y0 - 22}" text-anchor="middle">On paper: {gw(paper)} GW, '
               f'{pct(paper, total):.0f}% of everything GEM tracks</text>')
    # a bracket under under-construction
    uc_x0 = L + paper_w
    uc_w = tot["under_construction"] / total * (W - L - R)
    out.append(f'<path class="brk" d="M{uc_x0 + 1:.1f} {y0 + bh + 8} v6 H{uc_x0 + uc_w - 1:.1f} v-6"></path>'
               f'<text class="brl" x="{uc_x0 + uc_w / 2:.1f}" y="{y0 + bh + 26}" text-anchor="middle">Being built: '
               f'{gw(tot["under_construction"])} GW</text>')
    out.append("</svg>")
    return "".join(out)


def tech_rows(units):
    rows = {}
    for p in units:
        r = rows.setdefault(p["_tech"], {"gw": {s: 0.0 for s in STATUSES}, "n": {s: 0 for s in STATUSES}, "by_name": 0})
        r["gw"][p["dash_status"]] += p["_mw"]
        r["n"][p["dash_status"]] += 1
        r["by_name"] += p["_by_name"]
    order = sorted(rows, key=lambda g: (g == "unknown", -sum(rows[g]["gw"].values())))
    return [(g, rows[g]) for g in order]


def tech_svg(rows):
    W, L, R, T, rowH, bh = 880, 118, 76, 8, 30, 18
    H = T + rowH * len(rows) + 6
    vmax = max(sum(r["gw"].values()) for _, r in rows)
    sc = (W - L - R) / vmax
    out = [svg_open("c-tech", W, H, "Stacked bars of power capacity by technology, each split by stage")]
    for i, (g, r) in enumerate(rows):
        y = T + i * rowH
        total = sum(r["gw"].values())
        units_n = sum(r["n"].values())
        tip = tip_rows([f"<b>{esc(TECH_NAME[g])}</b>{gw(total)} GW in {units_n:,} units"] + [
            f'<i class="k {s}"></i>{ST_NAME[s]}: {gw(r["gw"][s])} GW ({r["n"][s]:,})' for s in STATUSES if r["gw"][s] > 0])
        out.append(f'<text class="rl" x="{L - 10}" y="{y + bh / 2 + 4}" text-anchor="end">{esc(TECH_NAME[g])}</text>')
        out.append(f'<g class="row" data-tip="{esc(tip)}"><rect class="hitrow" x="0" y="{y - 4}" width="{W}" height="{rowH}"></rect>')
        x = L
        for s in STATUSES:
            w = r["gw"][s] * sc
            if w <= 0:
                continue
            stip = f"<b>{esc(TECH_NAME[g])} · {ST_NAME[s]}</b>{gw(r['gw'][s])} GW in {r['n'][s]:,} units"
            out.append(f'<g data-tip="{esc(stip)}">{seg_rect(x, w, y, bh, f"seg {s}")}')
            lab = gw(r["gw"][s])
            if w >= text_w(lab, 10.5) + 12:
                out.append(f'<text class="inl on-{s}" x="{x + w / 2:.1f}" y="{y + bh / 2 + 3.5:.1f}" '
                           f'text-anchor="middle">{lab}</text>')
            out.append("</g>")
            x += w
        out.append(f'<text class="end" x="{x + 8:.1f}" y="{y + bh / 2 + 4}">{gw(total)} GW</text></g>')
    out.append("</svg>")
    return "".join(out)


def tech_table(rows, tot):
    body = []
    for g, r in rows:
        total = sum(r["gw"].values())
        paper = r["gw"]["announced"] + r["gw"]["approved"]
        body.append([td(esc(TECH_NAME[g]), "name")] + [td(gw(r["gw"][s]) if r["gw"][s] else "–", "num") for s in STATUSES]
                    + [td(gw(total), "num"), td(f"{sum(r['n'].values()):,}", "num"),
                       td(f"{pct(paper, total):.0f}%" if total else "–", "num")])
    total = sum(tot.values())
    body.append([td("<b>All technologies</b>")] + [td(f"<b>{gw(tot[s])}</b>", "num") for s in STATUSES]
                + [td(f"<b>{gw(total)}</b>", "num"), td("", "num"),
                   td(f"<b>{pct(tot['announced'] + tot['approved'], total):.0f}%</b>", "num")])
    t = table("Capacity by technology and stage, GW. “On paper” is announced plus approved as a share of the row. "
              "“Not stated” is a unit GEM gives no technology and whose name says none.",
              ["Technology"] + [f"#{ST_NAME[s]}" for s in STATUSES] + ["#Total", "#Units", "#On paper"], body, cls="eg-t")
    return t.replace('<div class="tbl">', '<div class="tbl" data-allrows>', 1)


# ------------------------------------------------------------ view 2: solar on paper

def pv_rows(units, top=10, fold_under=1000.0):
    """Announced or approved solar PV by country, each country's capacity cut
    into one segment per owner (owners under fold_under MW folded into one
    segment per home group), in a fixed home-group order."""
    pv = [p for p in units if p["_tech"] == "solar" and p.get("tech") in ("PV", "Assumed PV") and p["dash_status"] in PAPER]
    byc = {}
    for p in pv:
        c = byc.setdefault(p["country"], {"gw": 0.0, "owners": {}})
        c["gw"] += p["_mw"]
        o = c["owners"].setdefault(p["_owner"], {"gw": 0.0, "home": p["_home"], "units": [], "h2": False})
        o["gw"] += p["_mw"]
        o["units"].append(p)
        o["h2"] = o["h2"] or p["_h2"]
    order = sorted(byc, key=lambda c: -byc[c]["gw"])
    rows = []
    for c in order[:top]:
        rows.append((c, byc[c]["gw"], segments(byc[c]["owners"], fold_under)))
    rest = order[top:]
    if rest:
        owners = {}
        for c in rest:
            for o, d in byc[c]["owners"].items():
                m = owners.setdefault(o, {"gw": 0.0, "home": d["home"], "units": [], "h2": d["h2"]})
                m["gw"] += d["gw"]
                m["units"] += d["units"]
        rows.append((f"{len(rest)} other countries", sum(byc[c]["gw"] for c in rest), segments(owners, fold_under)))
    return pv, byc, rows


def segments(owners, fold_under):
    segs = []
    for home in HOME_ORDER:
        mine = sorted(((o, d) for o, d in owners.items() if d["home"] == home), key=lambda t: -t[1]["gw"])
        big = [(o, d) for o, d in mine if d["gw"] >= fold_under or home == "blank"]
        small = [(o, d) for o, d in mine if d["gw"] < fold_under and home != "blank"]
        for o, d in big:
            segs.append({"home": home, "label": short_owner(o) if home != "blank" else "No owner stated", "owner": o,
                         "gw": d["gw"], "units": d["units"], "h2": d["h2"], "folded": 0})
        if small:
            segs.append({"home": home, "label": f"{len(small)} smaller owners", "owner": None,
                         "gw": sum(d["gw"] for _, d in small), "units": [u for _, d in small for u in d["units"]],
                         "h2": any(d["h2"] for _, d in small), "folded": len(small)})
    return segs


def unit_line(p):
    tag = " <b>H₂</b>" if p["_h2"] else ""
    unit = f" · {p['unit']}" if p.get("unit") else ""
    return f"{esc(p['name'])}{esc(unit)} · {gw(p['_mw'])} GW · {ST_NAME[p['dash_status']].lower()}{tag}"


def fit_label(name, w, tag, value, size=10.5, pad=12):
    """The label a segment of width w can carry: name, tag and value when
    they fit, then name and tag, then the name cut to the room there is
    (never under nine characters), else nothing (the tooltip has it)."""
    room = (w - pad) / (size * 0.58)
    for text in (f"{name}{tag} · {value}", f"{name}{tag}"):
        if len(text) <= room:
            return text
    cut = int(room) - len(tag) - 1
    return f"{name[:cut].rstrip()}…{tag}" if cut >= 9 and len(name) > cut else None


def pv_svg(rows):
    W, L, R, T, rowH, bh = 880, 132, 78, 8, 32, 20
    H = T + rowH * len(rows) + 6
    vmax = max(g for _, g, _ in rows)
    sc = (W - L - R) / vmax
    out = [svg_open("c-pv", W, H, "Stacked bars of announced or approved solar PV capacity by country, each bar split "
                                  "by owner and coloured by the owner's home")]
    for i, (country, total, segs) in enumerate(rows):
        y = T + i * rowH
        rtip = tip_rows([f"<b>{esc(country)}</b>{gw(total)} GW of solar PV announced or approved"] + [
            f'<i class="k h-{s["home"]}"></i>{esc(s["label"])}: {gw(s["gw"])} GW{" <b>H₂</b>" if s["h2"] else ""}'
            for s in segs[:8]] + ([f"… and {len(segs) - 8} more"] if len(segs) > 8 else []))
        out.append(f'<text class="rl" x="{L - 10}" y="{y + bh / 2 + 4}" text-anchor="end">{esc(country)}</text>')
        out.append(f'<g class="row" data-tip="{esc(rtip)}"><rect class="hitrow" x="0" y="{y - 4}" width="{W}" height="{rowH}"></rect>')
        x = L
        for s in segs:
            w = s["gw"] * sc
            units = sorted(s["units"], key=lambda p: -p["_mw"])
            lines = [unit_line(p) for p in units[:6]] + ([f"… and {len(units) - 6} more units"] if len(units) > 6 else [])
            stip = tip_rows([f"<b>{esc(s['label'])}</b>{gw(s['gw'])} GW · {esc(HOME_NAME[s['home']])}"] + lines)
            home = s["home"]
            out.append(f'<g data-tip="{esc(stip)}">{seg_rect(x, w, y, bh, f"seg h-{home}")}')
            lab = fit_label(s["label"], w, " H₂" if s["h2"] and s["owner"] else "", gw(s["gw"]))
            if lab:
                out.append(f'<text class="inl on-{home}" x="{x + w / 2:.1f}" '
                           f'y="{y + bh / 2 + 3.5:.1f}" text-anchor="middle">{esc(lab)}</text>')
            out.append("</g>")
            x += w
        out.append(f'<text class="end" x="{x + 8:.1f}" y="{y + bh / 2 + 4}">{gw(total)} GW</text></g>')
    out.append("</svg>")
    return "".join(out)


def pv_table(pv, n=40):
    """The largest units of the solar pipeline, one row each."""
    body = []
    for p in sorted(pv, key=lambda p: -p["_mw"])[:n]:
        groups = ", ".join(G_NAME[g] for g in p["_groups"]) or ("not on the lists" if p["_owner"] else "none stated")
        body.append([td(f'<a href="{esc(p["url"])}" target="_blank" rel="noopener noreferrer">{esc(p["name"])}</a>'
                        f'{(" <span class=dim>" + esc(p["unit"]) + "</span>") if p.get("unit") else ""}'
                        f'{" <span class=chip warn>H₂</span>" if p["_h2"] else ""}', "name"),
                     td(esc(p["country"])), td(esc(short_owner(p["_owner"])) if p["_owner"] else '<span class="dim">–</span>'),
                     td(esc(groups)), td(f'<span class="st {p["dash_status"]}"><i></i>{ST_NAME[p["dash_status"]]}</span>'),
                     td(gw(p["_mw"]), "num")])
    return table(f"The {n} largest announced or approved solar PV units, as GEM files them. “Home” is the lender-profile "
                 f"owner list the owner's name matches; H₂ marks a unit whose name or owner belongs to a green-hydrogen "
                 f"scheme. Each name opens GEM's page.",
                 ["Unit", "Country", "Owner", "Home", "Stage", "#GW"], body)


# ------------------------------------------------------------ view 3: owners × stage

def owner_matrix(units):
    rows = {k: {"gw": {s: 0.0 for s in STATUSES}, "n": {s: 0 for s in STATUSES}} for k, _, _ in OWNER_GROUPS}
    rows["unresolved"] = {"gw": {s: 0.0 for s in STATUSES}, "n": {s: 0 for s in STATUSES}}
    rows["blank"] = {"gw": {s: 0.0 for s in STATUSES}, "n": {s: 0 for s in STATUSES}}
    for p in units:
        keys = p["_groups"] or (["unresolved"] if p["_owner"] else ["blank"])
        for k in keys:
            rows[k]["gw"][p["dash_status"]] += p["_mw"]
            rows[k]["n"][p["dash_status"]] += 1
    order = sorted((k for k, _, _ in OWNER_GROUPS), key=lambda k: -sum(rows[k]["gw"].values()))
    return [(k, rows[k]) for k in order + ["unresolved", "blank"]]


def matrix_html(mat):
    names = dict(G_NAME, unresolved="Owner named, home not on the lists", blank="No owner stated")
    head = "".join(f'<th class="num"><span class="dk"><i class="sk {s}"></i>{ST_NAME[s]}</span></th>' for s in STATUSES)
    body = []
    for k, r in mat:
        total = sum(r["gw"].values())
        cells = []
        for s in STATUSES:
            v, n = r["gw"][s], r["n"][s]
            share = pct(v, total)
            if v <= 0:
                cells.append('<td class="mx num"><span class="dim">–</span></td>')
                continue
            shown = gw(v) if v >= 50 else "<0.1"
            cells.append(f'<td class="mx num" title="{esc(ST_NAME[s])}: {gw(v)} GW in {n:,} unit{"s" if n != 1 else ""}, '
                         f'{share:.0f}% of the group">'
                         f'<span class="cell"><i class="shb {s}" style="width:{max(share * 0.76, 2):.1f}px"></i>'
                         f'<b>{shown}</b><span class="n">{n:,} unit{"s" if n != 1 else ""}</span></span></td>')
        cls = ' class="sep"' if k == "unresolved" else ""
        body.append(f'<tr{cls}><td class="name">{esc(names[k])}</td>{"".join(cells)}<td class="num">{gw(total)}</td>'
                    f'<td class="num">{sum(r["n"].values()):,}</td></tr>')
    return (f'<div class="tbl mxwrap" data-allrows><table class="matrix"><caption>Capacity by owner group and stage, GW, with '
            f'the number of units. The bar in each cell is the stage\'s share of the group\'s capacity, so a row '
            f'reads as a mix. A unit whose owner string matches two lists counts in both, so the rows do not add up to '
            f'the tracker\'s total.</caption><thead><tr><th>Owner group</th>{head}<th class="num">Total GW</th>'
            f'<th class="num">Units</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>')


# ------------------------------------------------------------ view 4: the lag

FUNDER_RULES = [("China Eximbank", r"Eximbank"), ("Ministry of Commerce", r"Ministry of Commerce"),
                ("China Development Bank", r"China Development Bank"),
                ("Unspecified government body", r"Unspecified Chinese Government"),
                ("State commercial banks", r"ICBC|Bank of China|Construction Bank|CITIC|Agricultural Bank"),
                ("Chinese embassy", r"Embassy")]


def funder_group(p):
    first = (p.get("funders") or "").split(";")[0]
    for name, rx in FUNDER_RULES:
        if re.search(rx, first, re.I):
            return name
    return "Other funders"


def quartiles(vals):
    if len(vals) < 2:
        return vals[0], vals[0], vals[0]
    q = statistics.quantiles(vals, n=4, method="inclusive")
    return q[0], statistics.median(vals), q[2]


def lag_stats(recs):
    both = [p for p in recs if p.get("commitment_year") and p.get("completion_year")]
    lags = [p["completion_year"] - p["commitment_year"] for p in both]
    hist = {}
    for v in lags:
        hist[v] = hist.get(v, 0) + 1
    q1, med, q3 = quartiles(lags)
    by_sector, by_funder = {}, {}
    for p in both:
        lag = p["completion_year"] - p["commitment_year"]
        by_sector.setdefault(p["sector"], []).append(lag)
        by_funder.setdefault((funder_group(p), p.get("flow_simple") or "Vague"), []).append(lag)
    no_completion = {s: 0 for s in STATUSES}
    for p in recs:
        if not p.get("completion_year"):
            no_completion[p["dash_status"]] += 1
    young = [p for p in recs if (p.get("commitment_year") or 0) >= 2021]
    return {"n": len(recs), "n_lag": len(both), "lags": lags, "hist": hist, "q1": q1, "median": med, "q3": q3,
            "mean": statistics.mean(lags), "negative": sum(1 for v in lags if v < 0),
            "by_sector": by_sector, "by_funder": by_funder, "no_completion": no_completion,
            "young": len(young), "young_done": sum(1 for p in young if p.get("completion_year")),
            "years": (min(p["commitment_year"] for p in recs if p.get("commitment_year")),
                      max(p["commitment_year"] for p in recs if p.get("commitment_year")))}


def hist_svg(L_):
    W, H, L, R, T, B = 880, 220, 46, 12, 18, 30
    bins = ["<0"] + list(range(0, max(L_["hist"]) + 1))
    vals = [sum(c for v, c in L_["hist"].items() if v < 0)] + [L_["hist"].get(v, 0) for v in bins[1:]]
    vmax = max(vals)
    step = 50 if vmax <= 300 else 100
    top = step * ((vmax + step - 1) // step)
    slot = (W - L - R) / len(bins)
    bw = min(slot * 0.68, 24)
    yv = lambda v: T + (1 - v / top) * (H - T - B)
    out = [svg_open("c-hist", W, H, f"Columns of {L_['n_lag']:,} Chinese-financed projects by the years from commitment "
                                    f"to completion, median {L_['median']:.0f}")]
    v = 0
    while v <= top:
        out.append(f'<line class="gl" x1="{L}" x2="{W - R}" y1="{yv(v):.1f}" y2="{yv(v):.1f}"></line>'
                   f'<text class="ax" x="{L - 6}" y="{yv(v) + 4:.1f}" text-anchor="end">{v}</text>')
        v += step
    out.append(f'<text class="ax" x="{L - 6}" y="{T - 6}" text-anchor="end">projects</text>')
    for i, (b, c) in enumerate(zip(bins, vals)):
        cx = L + slot * (i + 0.5)
        y1 = yv(c)
        tip = f"<b>{'Completed before the commitment year' if b == '<0' else f'{b} year' + ('s' if b != 1 else '')}</b>{c:,} projects · {pct(c, L_['n_lag']):.0f}%"
        out.append(f'<g data-tip="{esc(tip)}"><rect class="hitcol" x="{cx - slot / 2:.1f}" y="{T}" width="{slot:.1f}" height="{H - T - B}"></rect>'
                   f'<rect class="col" x="{cx - bw / 2:.1f}" y="{y1:.1f}" width="{bw:.1f}" height="{max(yv(0) - y1, 0.5):.1f}" rx="3"></rect>')
        if b == L_["median"] or c == vmax:
            out.append(f'<text class="bval" x="{cx:.1f}" y="{y1 - 5:.1f}" text-anchor="middle">{c:,}</text>')
        out.append(f'<text class="ax" x="{cx:.1f}" y="{H - 10}" text-anchor="middle">{b}</text></g>')
    out.append(f'<text class="ax" x="{W - R}" y="{H - 10}" text-anchor="end">years</text>')
    mi = bins.index(L_["median"])
    mx = L + slot * (mi + 0.5)
    out.append(f'<line class="med" x1="{mx:.1f}" x2="{mx:.1f}" y1="{T - 4}" y2="{yv(0):.1f}"></line>'
               f'<text class="medl" x="{mx + 6:.1f}" y="{T - 6}">median {L_["median"]:.0f} years</text>')
    out.append("</svg>")
    return "".join(out)


SECTOR_NAME = {"transport": "Transport", "education": "Education", "energy": "Energy", "social": "Social", "health": "Health",
               "ict": "Communications", "industry": "Industry", "government": "Government buildings", "water": "Water",
               "agriculture": "Agriculture", "other": "Other", "trade": "Trade", "environment": "Environment"}


def range_rows(groups, min_n, label_of):
    rows = []
    for k, vals in groups.items():
        if len(vals) < min_n:
            continue
        q1, med, q3 = quartiles(vals)
        rows.append({"key": k, "label": label_of(k), "n": len(vals), "q1": q1, "median": med, "q3": q3,
                     "mean": statistics.mean(vals)})
    rows.sort(key=lambda r: (-r["median"], -r["q3"], -r["n"]))
    return rows


def range_svg(id_, rows, label, L=168, xmax=8):
    W, R, T, rowH = 520, 56, 10, 26
    H = T + rowH * len(rows) + 26
    sc = (W - L - R) / xmax
    xv = lambda v: L + max(0, min(v, xmax)) * sc
    out = [svg_open(id_, W, H, label)]
    for t in range(0, xmax + 1, 2):
        out.append(f'<line class="gl" x1="{xv(t):.1f}" x2="{xv(t):.1f}" y1="{T}" y2="{H - 22}"></line>'
                   f'<text class="ax" x="{xv(t):.1f}" y="{H - 8}" text-anchor="middle">{t}</text>')
    out.append(f'<text class="ax" x="{W - R + 16}" y="{H - 8}">years</text>')
    for i, r in enumerate(rows):
        y = T + i * rowH + rowH / 2
        tip = (f"<b>{esc(r['label'])}</b>{r['n']:,} projects with both years<br>median {r['median']:.0f} years · "
               f"quartiles {r['q1']:.0f} to {r['q3']:.0f} · mean {r['mean']:.1f}")
        out.append(f'<g class="row" data-tip="{esc(tip)}"><rect class="hitrow" x="0" y="{y - rowH / 2:.1f}" width="{W}" height="{rowH}"></rect>'
                   f'<text class="rl" x="{L - 10}" y="{y + 4:.1f}" text-anchor="end">{esc(r["label"])}</text>'
                   f'<rect class="iqr" x="{xv(r["q1"]):.1f}" y="{y - 5:.1f}" width="{max(xv(r["q3"]) - xv(r["q1"]), 2):.1f}" height="10" rx="2"></rect>'
                   f'<circle class="med" cx="{xv(r["median"]):.1f}" cy="{y:.1f}" r="5"></circle>'
                   f'<text class="nn" x="{W - R + 4}" y="{y + 4:.1f}">n {r["n"]:,}</text></g>')
    out.append("</svg>")
    return "".join(out)


def lag_table(sect_rows, fund_rows):
    body = []
    for r in sect_rows:
        body.append([td(esc(r["label"]), "name"), td("sector"), td(f"{r['n']:,}", "num"), td(f"{r['median']:.0f}", "num"),
                     td(f"{r['q1']:.0f}–{r['q3']:.0f}", "num"), td(f"{r['mean']:.1f}", "num")])
    for r in fund_rows:
        body.append([td(esc(r["label"]), "name"), td("funder and flow"), td(f"{r['n']:,}", "num"), td(f"{r['median']:.0f}", "num"),
                     td(f"{r['q1']:.0f}–{r['q3']:.0f}", "num"), td(f"{r['mean']:.1f}", "num")])
    t = table("Years from the commitment year to the completion year, AidData records with both. Quartiles by the "
              "inclusive method. Funder is the first institution AidData names on the record.",
              ["Group", "Kind", "#Projects", "#Median", "#Quartiles", "#Mean"], body)
    return t.replace('<div class="tbl">', '<div class="tbl" data-allrows>', 1)


# ------------------------------------------------------------ the page

def legend(items):
    return "".join(f'<span class="dk"><i class="sk {cls}"></i>{esc(n)}</span>' for cls, n in items)


def build_page(units, recs, meta):
    tot, n_st = status_totals(units)
    total = sum(tot.values())
    paper = tot["announced"] + tot["approved"]
    trows = tech_rows(units)
    pv, byc, prows = pv_rows(units)
    mat = owner_matrix(units)
    L_ = lag_stats(recs)

    # ---- the head map: countries with more capacity on paper than running
    byc_all = {}
    for p in units:
        c = byc_all.setdefault(p["country"], {s: 0.0 for s in STATUSES})
        c[p["dash_status"]] += p["_mw"]
    more = {c for c, d in byc_all.items() if d["announced"] + d["approved"] > d["operating"]}
    fill = {NAME2ISO[c]: "var(--accent)" for c in more if c in NAME2ISO}
    titles = {NAME2ISO[c]: f"{c}: {gw(d['announced'] + d['approved'])} GW on paper, {gw(d['operating'])} GW operating"
              for c, d in byc_all.items() if c in NAME2ISO}
    headmap = figure(
        africa_map(fill, titles, f"Map of Africa with the {len(more)} countries shaded whose announced or approved power "
                                 f"capacity exceeds what is operating"),
        f"{len(more)} of {len(byc_all)}",
        "countries and territories in GEM's tracker have more generating capacity announced or approved than "
        "operating. Shaded where paper outweighs the grid; hover a country for both figures.")

    # ---- figures the prose states
    pv_total = sum(c["gw"] for c in byc.values())
    top6 = sorted(byc.items(), key=lambda t: -t[1]["gw"])[:6]
    mr = byc.get("Mauritania", {"gw": 0, "owners": {}})
    mr_h2 = sorted(((prose_owner(o), d["gw"]) for o, d in mr["owners"].items() if d["h2"]), key=lambda t: -t[1])
    h2_big = max((p for p in units if p["_h2"]), key=lambda p: p["_mw"], default=None)
    h2_units = [p for p in units if p["_h2"]]
    h2_pv_paper = sum(p["_mw"] for p in pv if p["_h2"])
    h2_all_paper = sum(p["_mw"] for p in units if p["_h2"] and p["dash_status"] in PAPER)
    resolved = [p for p in units if p["_groups"]]
    blank = [p for p in units if not p["_owner"]]
    multi = [p for p in units if len(p["_groups"]) > 1]
    cn = dict(mat)["china"]
    gulf = dict(mat)["gulf"]
    unres = dict(mat)["unresolved"]
    cn_stalled = {}
    for p in units:
        if "china" in p["_groups"] and p["dash_status"] == "stalled":
            cn_stalled[p["name"]] = cn_stalled.get(p["name"], 0) + p["_mw"]
    cn_big = sorted(cn_stalled.items(), key=lambda t: -t[1])[:4]
    rule_units = [p for p in units if p["_by_name"]]
    rule_sorted = [p for p in rule_units if p["_tech"] != "unknown"]
    misses = []
    for name, rx in MISSES:
        v = sum(p["_mw"] for p in units if rx.search(p["_owner"]) and p["dash_status"] in PAPER)
        if v:
            misses.append(f"{name} ({gw(v)} GW on paper)")
    fp_gw = sum(p["_mw"] for p in units if FALSE_POSITIVE[1].search(p["_owner"]) and "usa" in p["_groups"])
    sect_rows = range_rows(L_["by_sector"], 10, lambda k: SECTOR_NAME.get(k, k))
    fund_rows = range_rows(L_["by_funder"], 30, lambda k: f"{k[0]}, {k[1].lower()}s" if k[1] != "Vague" else f"{k[0]}, flow not stated")
    dropped = sorted((SECTOR_NAME.get(k, k), len(v)) for k, v in L_["by_sector"].items() if len(v) < 10)
    by_f = {r["key"]: r for r in fund_rows}
    exim = by_f.get(("China Eximbank", "Loan"))
    mofcom = by_f.get(("Ministry of Commerce", "Grant"))
    unspec = by_f.get(("Unspecified government body", "Grant"))
    slowest, fastest = sect_rows[0], sect_rows[-1]

    def lst(items, key=lambda t: t):
        items = list(items)
        return ", ".join(key(x) for x in items[:-1]) + (" and " if len(items) > 1 else "") + (key(items[-1]) if items else "")

    gm, am = meta.get("assets", {}), meta.get("china", {})
    tokens = {
        "__HEADMAP__": headmap,
        "__GEM_RELEASE__": esc(gm.get("release", "–")), "__GEM_FRESH__": esc(gm.get("fresh", "–")),
        "__GEM_FETCHED__": fmt_date(gm["fetched"]) if gm.get("fetched") else "–",
        "__AD_RELEASE__": esc((am.get("release") or "–").split(" · ")[0]), "__AD_FRESH__": esc(am.get("fresh", "–")),
        "__AD_FETCHED__": fmt_date(am["fetched"]) if am.get("fetched") else "–",
        "__N_UNITS__": f"{len(units):,}", "__N_COUNTRIES__": str(len(byc_all)),
        "__GW_ALL__": gw(total), "__GW_PAPER__": gw(paper), "__GW_ANN__": gw(tot["announced"]), "__GW_APPR__": gw(tot["approved"]),
        "__GW_UC__": gw(tot["under_construction"]), "__GW_OP__": gw(tot["operating"]), "__GW_ST__": gw(tot["stalled"]),
        "__N_UC__": f"{n_st['under_construction']:,}", "__N_ST__": f"{n_st['stalled']:,}",
        "__PAPER_SHARE__": f"{pct(paper, total):.0f}", "__UC_SHARE__": f"{pct(tot['under_construction'], total):.0f}",
        "__PAPER_TO_UC__": f"{paper / tot['under_construction']:.0f}" if tot["under_construction"] else "–",
        "__PAPER_OF_PIPELINE__": f"{pct(paper, paper + tot['under_construction']):.0f}",
        "__ST_TO_UC__": times(tot["stalled"], tot["under_construction"]),
        "__H2_BIGGEST__": (f"{h2_big['name']}{', ' + h2_big['unit'] if h2_big.get('unit') else ''}, alone is {gw(h2_big['_mw'])} GW"
                           if h2_big else "–"),
        "__N_PAPER_MORE__": str(len(more)),
        "__GW_PV_PAPER__": gw(pv_total), "__N_PV_PAPER__": f"{len(pv):,}",
        "__PV_SHARE_OF_PAPER__": f"{pct(pv_total, paper):.0f}",
        "__PV_TOP6_SHARE__": f"{pct(sum(c['gw'] for _, c in top6), pv_total):.0f}",
        "__PV_TOP6__": lst(top6, lambda t: f"{t[0]} ({gw(t[1]['gw'])} GW)"),
        "__MR_GW__": gw(mr["gw"]), "__MR_H2__": lst(mr_h2, lambda t: f"{t[0]} ({gw(t[1])} GW)"),
        "__N_MR_H2__": str(len(mr_h2)),
        "__N_H2__": str(len({p["name"] for p in h2_units})), "__GW_H2_PV__": gw(h2_pv_paper), "__GW_H2_ALL__": gw(h2_all_paper),
        "__H2_SHARE_PV__": f"{pct(h2_pv_paper, pv_total):.0f}",
        "__N_RESOLVED__": str(len(resolved)), "__N_BLANK__": f"{len(blank):,}", "__GW_BLANK__": gw(sum(p["_mw"] for p in blank)),
        "__N_MULTI__": str(len(multi)), "__N_GROUPS__": str(len(OWNER_GROUPS)),
        "__CN_ST_N__": str(cn["n"]["stalled"]), "__CN_ST_GW__": gw(cn["gw"]["stalled"]),
        "__CN_OP_N__": str(cn["n"]["operating"]), "__CN_OP_GW__": gw(cn["gw"]["operating"]),
        "__CN_UC_GW__": gw(cn["gw"]["under_construction"]), "__CN_PAPER_GW__": gw(cn["gw"]["announced"] + cn["gw"]["approved"]),
        "__CN_STALLED_BIG__": lst(cn_big, lambda t: f"{t[0]} ({t[1]:,.0f} MW)"),
        "__GULF_APPR_GW__": gw(gulf["gw"]["approved"]), "__GULF_UC_GW__": gw(gulf["gw"]["under_construction"]),
        "__GULF_OP_GW__": gw(gulf["gw"]["operating"]),
        "__UNRES_UC_GW__": gw(unres["gw"]["under_construction"]), "__UNRES_N__": f"{sum(unres['n'].values()):,}",
        "__BLANK_UC_GW__": gw(dict(mat)["blank"]["gw"]["under_construction"]),
        "__MISSES__": lst(misses), "__FP_GW__": gw(fp_gw), "__FP_NAME__": FALSE_POSITIVE[0],
        "__AD_N__": f"{L_['n']:,}", "__AD_N_LAG__": f"{L_['n_lag']:,}", "__AD_MEDIAN__": f"{L_['median']:.0f}",
        "__AD_MEAN__": f"{L_['mean']:.1f}", "__AD_Q1__": f"{L_['q1']:.0f}", "__AD_Q3__": f"{L_['q3']:.0f}",
        "__AD_NEG__": str(L_["negative"]), "__AD_NO_COMPLETION__": f"{L_['n'] - L_['n_lag']:,}",
        "__AD_UC_NOC__": str(L_["no_completion"]["under_construction"]), "__AD_APPR_NOC__": str(L_["no_completion"]["approved"]),
        "__AD_ST_NOC__": str(L_["no_completion"]["stalled"]), "__AD_OP_NOC__": str(L_["no_completion"]["operating"]),
        "__AD_FROM__": str(L_["years"][0]), "__AD_TO__": str(L_["years"][1]),
        "__AD_YOUNG__": str(L_["young"]), "__AD_YOUNG_DONE__": str(L_["young_done"]),
        "__SLOWEST_SECTOR__": slowest["label"], "__SLOWEST_MED__": f"{slowest['median']:.0f}", "__SLOWEST_N__": f"{slowest['n']:,}",
        "__FASTEST_SECTOR__": fastest["label"].lower(), "__FASTEST_MED__": f"{fastest['median']:.0f}", "__FASTEST_N__": f"{fastest['n']:,}",
        "__EXIM_MED__": f"{exim['median']:.0f}" if exim else "–", "__EXIM_N__": f"{exim['n']:,}" if exim else "–",
        "__EXIM_Q__": f"{exim['q1']:.0f} to {exim['q3']:.0f}" if exim else "–",
        "__MOFCOM_MED__": f"{mofcom['median']:.0f}" if mofcom else "–", "__MOFCOM_N__": f"{mofcom['n']:,}" if mofcom else "–",
        "__UNSPEC_MED__": f"{unspec['median']:.0f}" if unspec else "–", "__UNSPEC_N__": f"{unspec['n']:,}" if unspec else "–",
        "__DROPPED_SECTORS__": lst(dropped, lambda t: f"{t[0].lower()} ({t[1]})") or "none",
        "__N_RULE__": str(len(rule_units)), "__N_RULE_SORTED__": str(len(rule_sorted)),
        "__GW_NOT_STATED__": gw(sum(p["_mw"] for p in units if p["_tech"] == "unknown")),
        "__N_NOT_STATED__": str(sum(1 for p in units if p["_tech"] == "unknown")),
        "__N_WIND_PH__": str(sum(1 for p in units if p.get("tech") == "Unknown")),
        "__N_GEO_PH__": str(sum(1 for p in units if p.get("tech") == "unknown type")),
        "__GEM_FOLD__": "".join(f"<li><b>{esc(a)}</b> → {ST_NAME[b].lower()}</li>" for a, b in GEM_FOLD),
        "__HEADLINE_BAR__": headline_bar(tot, n_st),
        "__CHART_TECH__": tech_svg(trows), "__TABLE_TECH__": tech_table(trows, tot),
        "__CHART_PV__": pv_svg(prows), "__TABLE_PV__": pv_table(pv),
        "__MATRIX__": matrix_html(mat),
        "__CHART_HIST__": hist_svg(L_),
        "__CHART_SECTOR__": range_svg("c-sector", sect_rows, "Range chart of years from commitment to completion by sector: "
                                                             "the box runs from the first to the third quartile, the dot is the median"),
        "__CHART_FUNDER__": range_svg("c-funder", fund_rows, "Range chart of years from commitment to completion by funder and "
                                                             "kind of flow", L=236),
        "__TABLE_LAG__": lag_table(sect_rows, fund_rows),
        "__STATUS_KEY__": legend([(s, ST_NAME[s]) for s in STATUSES]),
        "__OWNER_KEY__": legend([(f"h-{h}", HOME_NAME[h]) for h in HOME_ORDER
                                 if any(s["home"] == h for _, _, segs in prows for s in segs)]),
        "__OWNER_LISTS__": lst([n for _, n, _ in OWNER_GROUPS]),
    }

    payload = {
        "built": today(), "page": site_url(f"{SLUG}/"),
        "sources": {"gem": gm, "aiddata": am},
        "rules": {"status_fold": GEM_FOLD, "tech_groups": TECH_GROUP, "tech_name_rule": NAME_RULE,
                  "owner_lists": [n for _, n, _ in OWNER_GROUPS], "hydrogen_regex": H2_RE.pattern,
                  "quartiles": "statistics.quantiles(method='inclusive')"},
        "status_totals_gw": {s: round(tot[s] / 1000, 2) for s in STATUSES},
        "status_units": n_st,
        "by_technology": [{"group": g, "name": TECH_NAME[g], "gw": {s: round(r["gw"][s] / 1000, 2) for s in STATUSES},
                           "units": r["n"], "sorted_by_name": r["by_name"]} for g, r in trows],
        "paper_over_operating": sorted(more),
        "solar_pv_on_paper": {
            "total_gw": round(pv_total / 1000, 2), "units": len(pv),
            "by_country": [{"country": c, "gw": round(d["gw"] / 1000, 2),
                            "owners": [{"owner": o, "gw": round(x["gw"] / 1000, 3), "home": x["home"], "hydrogen": x["h2"],
                                        "units": len(x["units"])} for o, x in sorted(d["owners"].items(), key=lambda t: -t[1]["gw"])]}
                           for c, d in sorted(byc.items(), key=lambda t: -t[1]["gw"])]},
        "hydrogen_tagged": sorted({(p["name"], p["country"]) for p in h2_units}),
        "owner_matrix": [{"group": k, "name": dict(G_NAME, unresolved="named, unresolved", blank="no owner")[k],
                          "gw": {s: round(r["gw"][s] / 1000, 2) for s in STATUSES}, "units": r["n"]} for k, r in mat],
        "multi_list_units": [{"name": p["name"], "unit": p.get("unit"), "owner": p["_owner"], "lists": p["_groups"]} for p in multi],
        "owner_list_misses": {"unresolved_examples": misses, "false_positive": f"{FALSE_POSITIVE[0]}: {gw(fp_gw)} GW read as United States"},
        "aiddata_lag": {"records": L_["n"], "with_both_years": L_["n_lag"], "median": L_["median"], "q1": L_["q1"], "q3": L_["q3"],
                        "mean": round(L_["mean"], 2), "negative": L_["negative"],
                        "histogram": {str(k): v for k, v in sorted(L_["hist"].items())},
                        "without_completion_year": L_["no_completion"],
                        "by_sector": [{k: v for k, v in r.items() if k != "key"} for r in sect_rows],
                        "by_funder_flow": [{"funder": r["key"][0], "flow": r["key"][1], **{k: v for k, v in r.items() if k not in ("key", "label")}}
                                           for r in fund_rows],
                        "dropped_sectors": dropped},
    }
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
    units, recs = load()
    tokens, payload = build_page(units, recs, load_meta())
    tokens.update({"__TITLE__": esc(TITLE), "__DATA_URL__": site_url(f"data/{PAYLOAD_FILE}"), "__DATA_FILE__": PAYLOAD_FILE,
                   "__BUILT__": fmt_date(today())})
    page = FRAME.read_text().replace("<!--__BODY__-->", head_wrap(FRAG.read_text(), "__HEADMAP__"), 1)
    for k, v in tokens.items():
        page = page.replace(k, v)
    # every chart is drawn above; the frame's own chart script gets nothing to draw
    page = page.replace("/*__PAYLOAD__*/", json.dumps({"charts": {}}), 1)
    # "execution-gap" is in no menu, so the Deep dives menu marks nothing current
    page = brand_assets(page, donor=SLUG)
    left = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]*__", page)))
    if left:
        sys.exit(f"execution-gap: unfilled tokens {', '.join(left)}")
    path = f"{SLUG}/index.html"
    doc = wrap_document(page, title=TITLE, description=DESCRIPTION, path=path, kind="profile", extra_head=jsonld(path))
    if NOINDEX[0] not in doc:
        sys.exit("execution-gap: the robots meta changed in shared.wrap_document; update NOINDEX")
    doc = doc.replace(*NOINDEX)
    (DOCS / SLUG).mkdir(parents=True, exist_ok=True)
    (DOCS / SLUG / "index.html").write_text(doc)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    (DOCS / "data" / PAYLOAD_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"→ docs/{path}  {len(doc.encode()) / 1024:.0f} KB  (+ docs/data/{PAYLOAD_FILE})")


if __name__ == "__main__":
    build()
