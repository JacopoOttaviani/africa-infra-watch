#!/usr/bin/env python3
"""
Build the debt section, docs/debt/index.html, and the payload of the
dashboard's "Who it owes" box, both from data/debt.json (fetch_debt.py).

    python3 build_debt.py

The page wears the lender profiles' frame (donor.template.html) and borrows
build_donors.py's helpers; its prose and section order are in
sections/debt.html, with __TOKENS__ for every figure it states. The chart,
the map and the tables are drawn here, in Python, so the page reads without
scripts; the frame's own script only toggles the map's groups and shows
their tooltips.

The creditor groups on the page are seven: six hues and a grey "other". The
pack keeps every creditor under its own name and a finer group (Japan and
Korea, India, Russia, Turkey, other African states, other countries, multiple
lenders), which the page folds into "Other lenders" and names in its tables.
"""

import json
import math
import pathlib
import re
import shutil
import sys

from build_donors import FRAME, MAP_H, MAP_W, esc, land_paths, px, table, td
from shared import (AUTHOR_NAME, AUTHOR_URL, DATA, DOCS, DONORS, SITE_NAME, SITE_URL, WEB_URL,
                    brand_assets, fmt_date, site_url, today, wrap_document)

ROOT = pathlib.Path(__file__).parent
SRC = DATA / "debt.json"
FRAG = ROOT / "sections" / "debt.html"
SLUG = "debt"
TITLE = "Who Africa owes"
DESCRIPTION = ("What every African government owes abroad, creditor by creditor, 2000 to the latest year: "
               "multilateral lenders, bondholders, China, Europe, the Gulf states, the United States and "
               "every other lending country, from the World Bank's International Debt Statistics, with the "
               "IMF's credit beside it.")

# The page's seven groups, in stacking order (bottom first). Colours are the
# --dg-* tokens, defined in sections/debt.html and in dashboard.template.html.
DISPLAY = [("multi", "Multilateral lenders"), ("bonds", "Bondholders"), ("china", "China"),
           ("europe", "Europe"), ("gulf", "Gulf states"), ("us", "United States"), ("other", "Other lenders")]
DG = [g for g, _ in DISPLAY]
DG_NAME = dict(DISPLAY)
FOLD = {"japan": "other", "india": "other", "russia": "other", "turkey": "other", "africa": "other",
        "multiple": "other"}
NON_BILATERAL = {"multi", "bonds", "multiple"}


def bn(v, dp=1):
    return f"{v / 1e9:,.{dp}f}"


def pct(part, whole):
    return part / whole * 100 if whole else 0.0


def pc(part, whole):
    """A share as printed: '<1%' rather than a misleading '0%'."""
    p = pct(part, whole)
    return "<1%" if 0 < p < 1 else f"{p:.0f}%"


def load():
    if not SRC.exists():
        sys.exit("missing data/debt.json — run fetch_debt.py first")
    return json.loads(SRC.read_text())


def shape(pack):
    """Everything the page and the box read, computed once.

    by_c[iso][year] = {display group: USD}; cont[year] the same summed over
    the continent; latest[iso] = [(creditor code, USD)] in the last year."""
    cr = pack["creditors"]
    dg_of = {code: FOLD.get(c["group"], c["group"]) for code, c in cr.items()}
    years = list(range(pack["first_year"], pack["data_to"] + 1))
    by_c, cont, latest = {}, {y: dict.fromkeys(DG, 0.0) for y in years}, {}
    for iso, c in pack["countries"].items():
        rows = {y: dict.fromkeys(DG, 0.0) for y in years}
        for code, s in c["creditors"].items():
            for y, v in s.items():
                y = int(y)
                if y in rows:
                    rows[y][dg_of[code]] += v
                    cont[y][dg_of[code]] += v
        by_c[iso] = rows
        y = pack["data_to"]
        latest[iso] = sorted(((code, s.get(str(y), 0)) for code, s in c["creditors"].items() if s.get(str(y))),
                             key=lambda t: -t[1])
    return {"cr": cr, "dg_of": dg_of, "years": years, "by_c": by_c, "cont": cont, "latest": latest}


# -------------------------------------------------------------- the chart

def nice_step(v):
    p = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v / p <= m:
            return m * p
    return 10 * p


def stack_svg(cont, years, data_to):
    """Stacked columns of the stock by group, year by year, drawn at build
    time. Each column is one <g> carrying its tooltip; the shares of the four
    largest groups are labelled at the last column."""
    W, H, L, R, T, B = 880, 300, 50, 150, 12, 26
    totals = {y: sum(cont[y].values()) for y in years}
    step = nice_step(max(totals.values()) / 4)
    top = step * math.ceil(max(totals.values()) / step)
    slot = (W - L - R) / len(years)
    bw = slot * 0.74
    yv = lambda v: T + (1 - v / top) * (H - T - B)
    out = [f'<svg id="c-stack" viewBox="0 0 {W} {H}" role="img" aria-label="Stacked columns of African '
           f'governments\' external debt by creditor group, {years[0]} to {data_to}">']
    v = 0
    while v <= top + 1e-6:
        out.append(f'<line class="gl" x1="{L}" x2="{W - R}" y1="{yv(v):.1f}" y2="{yv(v):.1f}"></line>'
                   f'<text class="ax" x="{L - 6}" y="{yv(v) + 4:.1f}" text-anchor="end">{v / 1e9:,.0f}</text>')
        v += step
    out.append(f'<text class="ax" x="{L - 6}" y="{T - 2}" text-anchor="end">USD bn</text>')
    for i, y in enumerate(years):
        x = L + slot * i + (slot - bw) / 2
        tot = totals[y]
        tip = (f"<b>{y}</b>USD {bn(tot)} bn owed abroad<br>" + "<br>".join(
            f'<i class="k" style="background:var(--dg-{g})"></i>{esc(DG_NAME[g])}: {bn(cont[y][g])} bn '
            f'({pct(cont[y][g], tot):.0f}%)' for g in DG if cont[y][g] >= 5e8))
        segs, base = [], 0.0
        for g in DG:
            val = cont[y][g]
            if val <= 0:
                continue
            y0, y1 = yv(base), yv(base + val)
            segs.append(f'<rect class="seg" x="{x:.1f}" y="{y1:.1f}" width="{bw:.1f}" height="{max(y0 - y1, .5):.1f}" '
                        f'style="fill:var(--dg-{g})"></rect>')
            base += val
        out.append(f'<g class="col" data-tip="{esc(tip)}"><rect class="hitcol" x="{L + slot * i:.1f}" y="{T}" '
                   f'width="{slot:.1f}" height="{H - T - B}"></rect>{"".join(segs)}</g>')
        if y % 4 == 0 or y == data_to:
            out.append(f'<text class="ax" x="{x + bw / 2:.1f}" y="{H - 8}" text-anchor="middle">{y}</text>')
    # direct labels at the last column, for the groups big enough to read
    last, tot, base, labels = years[-1], totals[years[-1]], 0.0, []
    for g in DG:
        val = cont[last][g]
        if val > 0 and pct(val, tot) >= 8:
            labels.append([yv(base + val / 2), g, val])
        base += val
    labels.sort(key=lambda t: -t[0])               # bottom first
    for i in range(1, len(labels)):                 # keep 13 px between labels
        labels[i][0] = min(labels[i][0], labels[i - 1][0] - 13)
    xl = L + slot * (len(years) - 1) + (slot + bw) / 2 + 8
    for ly, g, val in labels:
        out.append(f'<rect x="{xl:.1f}" y="{ly - 4.5:.1f}" width="9" height="9" rx="2" style="fill:var(--dg-{g})"></rect>'
                   f'<text class="dl" x="{xl + 14:.1f}" y="{ly + 3.5:.1f}">{esc(DG_NAME[g])} '
                   f'<tspan class="dv">{pct(val, tot):.0f}%</tspan></text>')
    out.append("</svg>")
    return "".join(out)


def legend_html():
    return "".join(f'<span class="dk"><i style="background:var(--dg-{g})"></i>{esc(n)}</span>' for g, n in DISPLAY)


def mix_bar(groups, total):
    """A 100% bar of one country's creditor mix, as spans (no script needed)."""
    if not total:
        return ""
    return ('<span class="mix" aria-hidden="true">' + "".join(
        f'<i style="width:{pct(groups[g], total):.2f}%;background:var(--dg-{g})" title="{esc(DG_NAME[g])} '
        f'{pct(groups[g], total):.0f}%"></i>' for g in DG if groups[g] > 0) + "</span>")


# -------------------------------------------------------------- the page

def build_page(pack, sh):
    cr, years, by_c, cont, latest = sh["cr"], sh["years"], sh["by_c"], sh["cont"], sh["latest"]
    y1, y0 = pack["data_to"], pack["first_year"]
    C = pack["countries"]
    tot = {iso: sum(by_c[iso][y1].values()) for iso in C}
    T = sum(cont[y1].values())
    T0 = sum(cont[y0].values())
    china = {y: cont[y]["china"] for y in years}
    cpeak_y = max(years, key=china.get)
    imf = sum(c["imf"].get(str(y1), 0) for c in C.values())

    def biggest_bilateral(iso):
        return next(((code, v) for code, v in latest[iso] if cr[code]["group"] not in NON_BILATERAL), (None, 0))
    china_top = sorted((C[iso]["name"] for iso in C if biggest_bilateral(iso)[0] == "730"))
    lead_group = {iso: max(DG, key=lambda g: by_c[iso][y1][g]) for iso in C if tot[iso]}
    bonds_lead = sorted(C[iso]["name"] for iso, g in lead_group.items() if g == "bonds")
    china_lead = sorted(C[iso]["name"] for iso, g in lead_group.items() if g == "china")

    # ---- the country table
    profile = {"087": "russia", "055": "turkey", "006": "italy", "730": "china", "302": "usa",
               "005": "germany", "975": "eu", "919": "eu", "918": "eu", "004": "france", "050": "spain",
               "701": "japan", "003": "nordics", "018": "nordics", "020": "nordics", "008": "nordics",
               "010": "nordics", "576": "gulf", "566": "gulf", "552": "gulf", "561": "gulf"}
    live = {d["slug"] for d in DONORS}

    def cname(code):
        n = esc(cr[code]["name"])
        slug = profile.get(code)
        return f'<a href="{SITE_URL}{slug}/">{n}</a>' if slug in live else n

    rows = []
    for iso in sorted(C, key=lambda i: -tot[i]):
        g, t = by_c[iso][y1], tot[iso]
        code, v = biggest_bilateral(iso)
        im = C[iso]["imf"].get(str(y1), 0)
        rows.append([
            td(f'<a href="{SITE_URL}dashboard.html#c={iso}" title="Open {esc(C[iso]["name"])} in the dashboard">'
               f'{esc(C[iso]["name"])}</a>', "name"),
            td(bn(t), "num"),
            td(mix_bar(g, t)),
            td(pc(g["multi"], t) if g["multi"] else "–", "num"),
            td(pc(g["bonds"], t) if g["bonds"] else "–", "num"),
            td(pc(g["china"], t) if g["china"] else "–", "num"),
            td(f'{cname(code)} <span class="dim m">{bn(v)}</span>' if code else '<span class="dim">none</span>'),
            td(bn(im) if im else "–", "num"),
        ])
    t_countries = table(
        f"Public and publicly guaranteed external debt of {len(C)} African governments at the end of {y1}, "
        f"USD billion, by creditor. The IMF column is not part of the total. Click a country to open it in "
        f"the dashboard.",
        ["Country", "#Owed abroad", "Creditor mix", "#Multilateral", "#Bondholders", "#China",
         "Largest bilateral creditor, USD bn", "#IMF credit"], rows, cls="debt")

    # ---- the creditor table
    agg = {}
    for iso in C:
        for code, v in latest[iso]:
            a = agg.setdefault(code, {"v": 0.0, "n": 0, "who": []})
            a["v"] += v
            a["n"] += 1
            a["who"].append((v, iso))
    then = {}
    ref = 2015 if 2015 in years else years[0]
    for iso, c in C.items():
        for code, s in c["creditors"].items():
            then[code] = then.get(code, 0) + s.get(str(ref), 0)
    top = sorted(agg.items(), key=lambda t: -t[1]["v"])[:30]
    rows = []
    for code, a in top:
        g = sh["dg_of"][code]
        who = ", ".join(f'{esc(C[iso]["name"])} <span class="dim m">{bn(v)}</span>'
                        for v, iso in sorted(a["who"], reverse=True)[:3])
        chg = a["v"] - then.get(code, 0)
        rows.append([td(cname(code), "name"),
                     td(f'<span class="dk"><i style="background:var(--dg-{g})"></i>{esc(DG_NAME[g])}</span>'),
                     td(bn(a["v"]), "num"), td(str(a["n"]), "num"), td(who),
                     td(("+" if chg >= 0 else "−") + bn(abs(chg)), "num")])
    t_creditors = table(
        f"The thirty largest creditors of African governments at the end of {y1}, USD billion. A country "
        f"stands for every lender resident there, public and private. Change against the end of {ref}.",
        ["Creditor", "Group", f"#Owed, {y1}", "#Debtors", "Largest debtors, USD bn", f"#Since {ref}"], rows)

    # ---- the map: a ring per country sized by the total, a disc inside it
    # sized by what is owed to one group (China by default), on one scale
    vmax = max(tot.values())

    def rad(v):
        return round(max(1.8, 34 * math.sqrt(v / vmax)), 1) if v > 0 else 0

    def where(iso):
        x, y = px(C[iso]["lon"], C[iso]["lat"])
        return {"x": x, "y": y}

    def tip(iso):
        g, t = by_c[iso][y1], tot[iso]
        lines = "<br>".join(f"{esc(DG_NAME[k])}: {bn(g[k])} bn ({pct(g[k], t):.0f}%)"
                            for k in sorted(DG, key=lambda k: -g[k]) if g[k] >= 1e7)
        code, v = biggest_bilateral(iso)
        big = f"<br>Largest bilateral creditor: {esc(cr[code]['name'])}, {bn(v)} bn" if code else ""
        im = C[iso]["imf"].get(str(y1), 0)
        imf_line = f"<br>Plus IMF credit: {bn(im)} bn" if im else ""
        return f"<b>{esc(C[iso]['name'])}</b>Owed abroad, end-{y1}: USD {bn(t)} bn<br>{lines}{big}{imf_line}"

    groups = []
    for g, cls, on in (("china", "dchina", True), ("bonds", "dbonds", False), ("multi", "dmulti", False)):
        groups.append({"id": f"g-{g}", "kind": "circle", "cls": cls, "items": [
            {**where(iso), "r": rad(by_c[iso][y1][g]), "tip": tip(iso)}
            for iso in sorted(C, key=lambda i: -by_c[i][y1][g]) if by_c[iso][y1][g] > 0]})
    groups.append({"id": "g-total", "kind": "circle", "cls": "dring", "items": [
        {**where(iso), "r": rad(tot[iso]), "tip": tip(iso),
         "label": C[iso]["name"] if tot[iso] >= 15e9 else None}
        for iso in sorted(C, key=lambda i: -tot[i])]})

    cbar = sorted(C, key=lambda i: -by_c[i][y1]["china"])[:12]
    bbar = sorted(C, key=lambda i: -by_c[i][y1]["bonds"])[:12]
    payload = {"map": {"groups": groups}, "charts": {
        "c-china": {"type": "bars", "rows": [{"label": C[i]["name"], "value": by_c[i][y1]["china"],
                                              "text": f"{bn(by_c[i][y1]['china'])} bn"} for i in cbar]},
        "c-bonds": {"type": "bars", "rows": [{"label": C[i]["name"], "value": by_c[i][y1]["bonds"],
                                              "text": f"{bn(by_c[i][y1]['bonds'])} bn"} for i in bbar]},
    }}

    eu0, eu1 = pct(cont[y0]["europe"], T0), pct(cont[y1]["europe"], T)
    tokens = {
        "__DATA_TO__": str(y1), "__FIRST_YEAR__": str(y0), "__REF_YEAR__": str(ref),
        "__N_COUNTRIES__": str(len(C)), "__MISSING__": ", ".join(pack["missing"]) or "none",
        "__N_CREDITORS__": str(len(cr)),
        "__TOTAL__": bn(T, 0), "__TOTAL_FIRST__": bn(T0, 0),
        "__MULTI_SHARE__": f"{pct(cont[y1]['multi'], T):.0f}",
        "__BONDS_SHARE__": f"{pct(cont[y1]['bonds'], T):.0f}", "__BONDS_SHARE_FIRST__": f"{pct(cont[y0]['bonds'], T0):.0f}",
        "__BONDS__": bn(cont[y1]["bonds"], 0), "__BONDS_FIRST__": bn(cont[y0]["bonds"], 0),
        "__N_BONDS_LEAD__": str(len(bonds_lead)), "__BONDS_LEAD__": ", ".join(bonds_lead),
        "__CHINA_SHARE__": f"{pct(cont[y1]['china'], T):.0f}", "__CHINA__": bn(cont[y1]["china"]),
        "__CHINA_PEAK__": bn(china[cpeak_y]), "__CHINA_PEAK_YEAR__": str(cpeak_y),
        "__N_CHINA_TOP__": str(len(china_top)), "__N_CHINA_LEAD__": str(len(china_lead)),
        "__CHINA_LEAD__": ", ".join(china_lead),
        "__EUROPE_FIRST__": f"{eu0:.0f}", "__EUROPE__": f"{eu1:.0f}",
        "__US__": bn(cont[y1]["us"]), "__GULF__": bn(cont[y1]["gulf"]),
        "__IMF__": bn(imf, 0),
        "__IDS_UPDATED__": fmt_date(pack["updated"]) if pack.get("updated") else "–",
        "__FETCHED__": fmt_date(pack["fetched"]),
        "__CHART_STACK__": stack_svg(cont, years, y1), "__LEGEND__": legend_html(),
        "__TABLE_COUNTRIES__": t_countries, "__TABLE_CREDITORS__": t_creditors,
    }
    return tokens, payload


def jsonld(path):
    page = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": site_url(path), "url": site_url(path), "name": TITLE,
         "description": DESCRIPTION, "inLanguage": "en",
         "isPartOf": {"@type": "WebSite", "@id": site_url("#website"), "name": SITE_NAME, "url": SITE_URL},
         "author": {"@type": "Person", "name": AUTHOR_NAME, "url": WEB_URL, "sameAs": [AUTHOR_URL]},
         "about": {"@type": "Place", "name": "Africa"},
         "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": SITE_URL},
             {"@type": "ListItem", "position": 2, "name": TITLE, "item": site_url(path)}]}},
        {"@type": "Dataset", "name": "External debt of African governments by creditor",
         "description": DESCRIPTION, "license": "https://creativecommons.org/licenses/by/4.0/",
         "creator": {"@type": "Organization", "name": "World Bank"},
         "distribution": {"@type": "DataDownload", "encodingFormat": "application/json",
                          "contentUrl": site_url("data/debt.json")}}]}
    return ('<script type="application/ld+json">'
            + json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n")


# The debt section is a theme of the top bar's Deep dives menu
# (shared.donor_nav); brand_assets(page, donor="debt") marks it current.


def build():
    pack = load()
    sh = shape(pack)
    tokens, payload = build_page(pack, sh)
    tokens.update({"__TITLE__": esc(TITLE), "__MAP_W__": f"{MAP_W:.0f}", "__MAP_H__": f"{MAP_H:.0f}",
                   "__DATA_URL__": site_url("data/debt.json"), "__DATA_FILE__": "debt.json",
                   "__BUILT__": fmt_date(today())})
    page = FRAME.read_text().replace("<!--__BODY__-->", FRAG.read_text(), 1)
    for k, v in tokens.items():
        page = page.replace(k, v)
    page = page.replace("<!--__LAND__-->", land_paths(), 1)
    page = page.replace("/*__PAYLOAD__*/", json.dumps(payload, ensure_ascii=False, separators=(",", ":")), 1)
    page = brand_assets(page, donor="debt")
    left = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]*__", page)))
    if left:
        sys.exit(f"debt: unfilled tokens {', '.join(left)}")
    path = f"{SLUG}/index.html"
    doc = wrap_document(page, title=TITLE, description=DESCRIPTION, path=path, kind="profile",
                        extra_head=jsonld(path))
    (DOCS / SLUG).mkdir(parents=True, exist_ok=True)
    (DOCS / SLUG / "index.html").write_text(doc)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC, DOCS / "data" / SRC.name)
    print(f"→ docs/{path}  {len(doc.encode()) / 1024:.0f} KB  (+ docs/data/{SRC.name})")


# -------------------------------------------------------- the dashboard box

def dashboard_payload():
    """What the dashboard's "Who it owes" box needs, in USD million: for the
    continent and for each country, the latest total and its seven groups,
    the groups year by year, the largest named creditors and the IMF's
    credit. None when the debt pack has not been fetched."""
    if not SRC.exists():
        return None
    pack = json.loads(SRC.read_text())
    sh = shape(pack)
    years, y1 = sh["years"], pack["data_to"]
    mm = lambda v: round(v / 1e6)

    def block(rows, top, imf):
        return {"g": [mm(rows[y1][g]) for g in DG], "s": [[mm(rows[y][g]) for g in DG] for y in years],
                "top": [[code, mm(v)] for code, v in top[:8]], "imf": mm(imf)}
    out = {"from": years[0], "to": y1, "updated": pack.get("updated"),
           "groups": [[g, n] for g, n in DISPLAY], "c": {}, "none": [], "names": {}}
    agg = {}
    for iso, c in pack["countries"].items():
        out["c"][iso] = block(sh["by_c"][iso], sh["latest"][iso], c["imf"].get(str(y1), 0))
        for code, v in sh["latest"][iso]:
            agg[code] = agg.get(code, 0) + v
    out["africa"] = block(sh["cont"], sorted(agg.items(), key=lambda t: -t[1]),
                          sum(c["imf"].get(str(y1), 0) for c in pack["countries"].values()))
    out["africa"]["n"] = len(pack["countries"])
    used = {code for b in [out["africa"], *out["c"].values()] for code, _ in b["top"]}
    out["names"] = {code: pack["creditors"][code]["name"] for code in sorted(used)}
    out["group_of"] = {code: sh["dg_of"][code] for code in sorted(used)}
    from fetch_donors import AFRICA, NAME
    out["none"] = sorted(iso for iso in NAME if iso not in pack["countries"])
    return out


if __name__ == "__main__":
    build()
