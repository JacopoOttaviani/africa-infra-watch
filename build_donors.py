#!/usr/bin/env python3
"""
Build the lender profiles: docs/<slug>/index.html for every entry in
shared.DONORS, from

    donor.template.html      the frame every profile shares (chrome, map and
                             chart code, the same buttons as the map)
    donors/<slug>.html       that profile's prose and section order, with
                             __TOKENS__ for every figure it states
    data/donors/<slug>.json  its data pack, from fetch_donors.py

The tables are rendered here, in Python, so a crawler reads the substance
without scripts; the map and the charts are drawn by the page from the same
pack, inlined. The pack is also copied to docs/data/donors/, so the site
publishes what the page shows.

    python3 build_donors.py           every profile
    python3 build_donors.py russia    one
"""

import html
import json
import pathlib
import re
import shutil
import sys

from shared import (DATA, DOCS, DONORS, SITE_NAME, AUTHOR_NAME, AUTHOR_URL, WEB_URL, SITE_URL,
                    brand_assets, wrap_document, fmt_date, today, site_url)

ROOT = pathlib.Path(__file__).parent
FRAME = ROOT / "donor.template.html"
# the site's country names (fetch_donors keeps them beside the ISO table)
from fetch_donors import NAME as NAMES

# Equirectangular, like the dashboard's map; wide enough for Cabo Verde and
# Mauritius, the islands the debt table reaches.
LON0, LON1, LAT0, LAT1 = -26.0, 60.0, -36.0, 38.0
SC = 10.0
MAP_W, MAP_H = (LON1 - LON0) * SC, (LAT1 - LAT0) * SC


def px(lon, lat):
    return round((lon - LON0) * SC, 1), round((LAT1 - lat) * SC, 1)


def land_paths():
    """Every African country of the 1:110m basemap as one <path>, named."""
    bm = json.loads((DATA / "africa_basemap.json").read_text())
    out = []
    for c in bm["countries"]:
        d = []
        for poly in c["p"]:
            for ring in poly:
                d.append("M" + " L".join(f"{x} {y}" for x, y in (px(a, b) for a, b in ring)) + " Z")
        out.append(f'<path class="land" d="{" ".join(d)}"><title>{html.escape(c["n"])}</title></path>')
    return "\n".join(out)


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def m(v, dp=1):
    """USD million, formatted."""
    return f"{v / 1e6:,.{dp}f}"


STATUS = {"announced": "Announced", "approved": "Approved", "under_construction": "Under construction",
          "operating": "Operating", "stalled": "Stalled", "cancelled": "Cancelled", "sold": "Sold",
          "exited": "Exited", "exploration": "Exploration"}


def st(status):
    return f'<span class="st {esc(status)}"><i></i>{esc(STATUS.get(status, status))}</span>'


def table(caption, head, rows, cls=""):
    th = "".join(f'<th{" class=num" if h.startswith("#") else ""}>{esc(h.lstrip("#"))}</th>' for h in head)
    body = "".join("<tr>" + "".join(cells) + "</tr>" for cells in rows)
    return (f'<div class="tbl"><table{(" class=" + cls) if cls else ""}><caption>{caption}</caption>'
            f'<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>')


def td(v, cls=""):
    return f'<td{(" class=" + chr(34) + cls + chr(34)) if cls else ""}>{v}</td>'


# -------------------------------------------------------------- Russia

def build_russia(pack):
    ids = pack["ids"]
    cs = ids["countries"]
    data_to = ids["data_to"]
    cont = {int(k): v for k, v in ids["continent"].items()}
    first_year = min(cont)
    stock_latest = cont[data_to]
    egy = next((c["latest_stock"] for c in cs if c["iso"] == "EG"), 0)
    low_year = min((y for y in cont if 2005 <= y <= 2017), key=cont.get)
    coms = [(c, k) for c in cs for k in c["commitments"]]
    with_stock = [c for c in cs if c["latest_stock"] > 0]

    # ---- tables
    order = sorted(cs, key=lambda c: (-c["latest_stock"], c["name"]))
    rows = []
    for c in order:
        com = "<br>".join(
            f'<span class="m">{k["year"]} · USD {m(k["usd"])} m</span>: {esc(k["purpose"])}' for k in c["commitments"]
        ) or '<span class="dim">none</span>'
        rows.append([
            td(esc(c["name"]), "name"),
            td(m(c["latest_stock"]) if c["latest_stock"] else "–", "num"),
            td(c["latest_year"] or "–", "num"),
            td(m(c["peak_stock"]) if c["peak_stock"] else "–", "num"),
            td(c["peak_year"] or "–", "num"),
            td(com),
            td(m(c["ussr_peak"], 0) if c["ussr_peak"] else "–", "num"),
        ])
    t_ids = table(
        f"Debt owed to the Russian Federation by African governments, USD million, latest reported year; "
        f"{len(cs)} countries. World Bank International Debt Statistics, release of {fmt_date(ids['updated'])}.",
        ["Country", "#Owed to Russia, latest", "#Year", "#Peak stock", "#Peak year",
         "Russian loans since 2000 and what is known of their purpose", "#Soviet-era claim, peak"], rows)

    rows = []
    for g in pack["gem"]:
        where = f' <span class="dim">({esc(g["note"])})</span>' if g.get("on_site") else ""
        note = f'<br><span class="dim">{esc(g["note"])}</span>' if g["note"] and not g.get("on_site") else ""
        rows.append([td(esc(g["name"]) + where, "name"), td(esc(pack_name(pack, g["iso"]))), td(esc(g["what"])),
                     td(esc(g["role"]) + note), td(st(g["status"])),
                     td(f'<a href="{esc(g["url"])}" target="_blank" rel="noopener noreferrer">{esc(g["src"])}</a>')])
    t_gem = table("Records in Global Energy Monitor's trackers with a Russian vendor, owner or parent.",
                  ["Asset", "Country", "What", "Russian role", "Status", "Source"], rows)

    rows = []
    for n in sorted(pack["nuclear"], key=lambda r: (r["year"], r["country"])):
        rows.append([td(esc(n["country"]), "name"), td(n["year"], "num"), td(esc(n["what"])), td(esc(n["status"]))])
    t_nuc = table("Rosatom's African agreements as the World Nuclear Association records them; one row per country.",
                  ["Country", "#First", "What the WNA records", "Where it stands"], rows)

    def cbr_cell(v):
        if v == "C":
            return '<span class="chip warn" title="Confidential, suppressed by the Bank of Russia">C</span>'
        if v in ("-", None, ""):
            return "–"
        return f"{float(v):,.2f}"
    conf = [r for r in pack["cbr"] if r["v2021"] == "C"]
    rest = sorted((r for r in pack["cbr"] if r["v2021"] != "C"),
                  key=lambda r: -abs(float(r["v2021"])) if isinstance(r["v2021"], (int, float)) else 0)
    rows = [[td(esc(r["country"]), "name"), td(cbr_cell(r["v2014"]), "num"), td(cbr_cell(r["v2021"]), "num")]
            for r in conf + rest]
    t_cbr = table("Russian outward direct investment positions by African partner country, USD million, directional "
                  "principle. Bank of Russia, table updated 17 May 2023; the series ends at 1 January 2022. "
                  "C: confidential.", ["Partner country", "#1 Jan 2014", "#1 Jan 2021"], rows)

    rows = []
    for r in pack["corp"]:
        rows.append([td(esc(r["name"]), "name"), td(esc(r["country"])), td(esc(r["who"])), td(st(r["status"])),
                     td(esc(r["note"]) or '<span class="dim">–</span>'),
                     td(f'<a href="{esc(r["url"])}" target="_blank" rel="noopener noreferrer">{esc(r["src"])}</a>')])
    t_corp = table("Russian corporate holdings in African mining and energy as the press and the companies describe "
                   "them. Not a dataset; every row carries its source.",
                   ["Holding", "Country", "Owner", "Status", "Note", "Source"], rows)

    tokens = {
        "__N_COUNTRIES__": str(len(cs)),
        "__DATA_TO__": str(data_to),
        "__FIRST_YEAR__": str(first_year),
        "__STOCK_FIRST__": f"{cont[first_year] / 1e9:.1f}",
        "__STOCK_LATEST__": f"{stock_latest / 1e9:.2f}",
        "__EGY_SHARE__": f"{egy / stock_latest * 100:.0f}",
        "__LOW__": f"{cont[low_year] / 1e9:.2f}",
        "__LOW_YEAR__": str(low_year),
        "__N_COMMIT__": str(len(coms)),
        "__N_COMMIT_COUNTRIES__": str(len({c["iso"] for c, _ in coms})),
        "__COMMIT_SUM__": f"{sum(k['usd'] for _, k in coms) / 1e9:.1f}",
        "__N_GEM__": str(len(pack["gem"])),
        "__N_NUC__": str(len(pack["nuclear"])),
        "__IDS_UPDATED__": fmt_date(ids["updated"]),
        "__FETCHED__": fmt_date(pack["fetched"]),
        "__TABLE_IDS__": t_ids, "__TABLE_GEM__": t_gem, "__TABLE_NUC__": t_nuc,
        "__TABLE_CBR__": t_cbr, "__TABLE_CORP__": t_corp,
    }

    # ---- what the page draws
    def pt(r):
        x, y = px(r["lon"], r["lat"])
        return {"x": x, "y": y}
    bars = sorted(with_stock, key=lambda c: -c["latest_stock"])[:12]

    def loan_tip(c):
        com = ("<br>New loans since 2000: " + "; ".join(f"{k['year']} {usd(k['usd'])}" for k in c["commitments"])
               if c["commitments"] else "<br>No new Russian loan since 2000")
        return (f"<b>{esc(c['name'])}</b>Owed: {usd(c['latest_stock'])} ({c['latest_year']})"
                f"<br>Peak: {usd(c['peak_stock'])} in {c['peak_year']}{com}")
    payload = {
        "map": {"groups": [
            {"id": "g-loan", "kind": "circle", "cls": "loan",
             "items": [{**pt(c), "r": r_scale(c["latest_stock"]), "tip": loan_tip(c),
                        "label": c["name"] if c["latest_stock"] >= 50e6 else None}
                       for c in with_stock if c["lon"] is not None]},
            {"id": "g-corp", "kind": "square", "cls": "corp", "spread": True, "dy": 14,
             "items": [{**pt(r), "tip": f"<b>{esc(r['name'])}</b>{esc(r['country'])} · {esc(r['who'])}<br>"
                                        f"{esc(STATUS.get(r['status'], r['status']).lower())}{(' · ' + esc(r['note'])) if r['note'] else ''}<br>Source: {esc(r['src'])}"}
                       for r in pack["corp"] if r["lon"] is not None]},
            {"id": "g-nuc", "kind": "ring", "cls": "ring", "dy": 14,
             "items": [{**pt(n), "r": 6, "tip": f"<b>{esc(n['country'])} · Rosatom, from {n['year']}</b>{esc(n['what'])}<br>Where it stands: {esc(n['status'])}"}
                       for n in pack["nuclear"] if n["lon"] is not None]},
            {"id": "g-asset", "kind": "diamond",
             "items": [{**pt(g), "cls": g["status"], "tip": f"<b>{esc(g['name'])}</b>{esc(g['what'])}<br>"
                                                             f"{esc(STATUS.get(g['status'], g['status']).lower())} · {esc(g['role'])}<br>{esc(g['src'])}"}
                       for g in pack["gem"]]},
        ]},
        "charts": {
            "c-line": {"type": "line", "series": {str(y): v for y, v in sorted(cont.items())}, "label": "owed to Russia",
                       "notes": [
                           {"year": first_year, "text": f"USD {cont[first_year] / 1e9:.1f} bn: Soviet-era claims taken over", "dx": 8, "dy": -4, "anchor": "start"},
                           {"year": low_year, "text": f"USD {cont[low_year] / 1e9:.2f} bn after write-offs", "dx": 0, "dy": -10, "anchor": "middle"},
                           {"year": data_to, "text": f"USD {stock_latest / 1e9:.1f} bn, El Dabaa drawdowns", "dx": -8, "dy": -8, "anchor": "end"}]},
            "c-bar": {"type": "bars", "rows": [
                {"label": c["name"] + (f" ({c['latest_year']})" if c["latest_year"] < 2020 else ""),
                 "value": c["latest_stock"], "text": f"{c['latest_stock'] / 1e6:,.0f}",
                 "dim": c["latest_year"] < 2020} for c in bars]},
        },
    }
    return tokens, payload


def usd(v):
    v = v or 0
    a = abs(v)
    s = f"{v / 1e9:.2f} bn" if a >= 1e9 else f"{v / 1e6:.1f} m" if a >= 1e6 else f"{v / 1e3:.0f} k"
    return "USD " + s


def r_scale(v):
    """Bubble radius for a dollar amount: square-root, floor of 3 px."""
    return round(max(3.0, (v / 1e6) ** 0.5 * 0.45), 1)


def pack_name(pack, iso):
    for c in pack["ids"]["countries"]:
        if c["iso"] == iso:
            return c["name"]
    for r in pack["nuclear"] + pack["cbr"] + pack["corp"]:
        if r["iso"] == iso:
            return r["country"]
    return iso


# ------------------------------------------ the OECD-backed profiles share these

WORK_KIND = {"rail": "Railway", "tram": "Tramway", "power": "Power", "water": "Water", "convention": "Convention centre",
             "sports": "Stadium", "mixed": "Mixed-use", "logistics": "Logistics", "energy": "Energy equipment",
             "airport": "Airport", "road": "Road", "hospitality": "Hotel", "residential": "Housing", "stadium": "Stadium",
             "education": "Campus", "commercial": "Commercial", "government": "Government buildings", "retail": "Retail",
             "industrial": "Industrial", "culture": "Culture", "urban": "Urban"}
WORK_LABEL = {"built": "Built", "operating": "Operating", "building": "Under construction", "announced": "Planned",
              "ended": "Contract ended", "unknown": "Equipment export"}


def _name(iso):
    return NAMES.get(iso, iso)


def _crs_row(a):
    where = _name(a["iso"]) if a["iso"] else a["recipient"]
    d = esc(a["title"]) + (f'<br><span class="dim">{esc(a["desc"][:220])}{"…" if len(a["desc"]) > 220 else ""}</span>'
                           if a["desc"] and a["desc"].strip().lower() != a["title"].strip().lower() else "")
    return [td(a["year"], "num"), td(esc(where), "name"), td(f"{a['usd']:,.2f}", "num"),
            td(f'{esc(a["sector"])} <span class="dim m">{esc(a["code"])}</span>'), td(d), td(f'<span class="m dim">{esc(a["id"])}</span>')]


def _oecd_tables(crs, oda, fdi, ids, lender):
    """The tables every OECD-backed profile carries: largest aid records, the
    records that build something, FDI stock, net ODA, debt owed."""
    t_large = table(f"Largest {lender} CRS activities in Africa, {crs['from']}–{crs['to']}, commitments in USD million (current prices).",
                    ["#Year", "Recipient", "#USD m", "Purpose", "Title · description", "CRS id"],
                    [_crs_row(a) for a in crs["largest"][:15]])
    t_hard = table(f"Largest activities that build, renovate, equip or drill something: {crs['hard']['n']:,} of {crs['n']:,} "
                   f"activities, USD {crs['hard']['usd']:,.1f} m of USD {crs['usd']:,.1f} m.",
                   ["#Year", "Recipient", "#USD m", "Purpose", "Title · description", "CRS id"],
                   [_crs_row(a) for a in crs["hard"]["rows"][:12]])

    cs = ids["countries"]
    rows = []
    for c in sorted(cs, key=lambda c: (-c["latest_stock"], c["name"])):
        com = "<br>".join(f'<span class="m">{k["year"]} · USD {m(k["usd"])} m</span>' for k in c["commitments"][-6:]) or '<span class="dim">none</span>'
        if len(c["commitments"]) > 6:
            com = f'<span class="dim">{len(c["commitments"]) - 6} earlier, then</span><br>' + com
        ld = c.get("largest_disbursement")
        rows.append([td(esc(c["name"]), "name"), td(m(c["latest_stock"]) if c["latest_stock"] else "–", "num"),
                     td(c["latest_year"] or "–", "num"), td(m(c["peak_stock"]), "num"), td(c["peak_year"] or "–", "num"),
                     td(m(ld["usd"]) if ld else "–", "num"), td(ld["year"] if ld else "–", "num"), td(com)])
    t_ids = table(f"Debt owed to {lender} by African governments, USD million. World Bank International Debt Statistics, "
                  f"counterpart {list(ids['counterparts'])[0]}, release of {fmt_date(ids['updated'])}.",
                  ["Debtor", "#Owed, latest", "#Year", "#Peak stock", "#Peak year", "#Largest annual disbursement", "#Year",
                   f"New loans since {ids['since']}"], rows)

    t_fdi = ""
    if fdi:
        yrs = sorted({str(y) for y in (fdi["from"], 2019, fdi["to"] - 1, fdi["to"]) if fdi["from"] <= y <= fdi["to"]})
        rows = []
        for iso, s in sorted(fdi["countries"].items(), key=lambda kv: -max(abs(v) for v in kv[1].values()))[:16]:
            if max(abs(v) for v in s.values()) == 0:
                continue
            rows.append([td(esc(_name(iso)), "name")] + [td(f"{s[y]:,.1f}" if y in s else "–", "num") for y in yrs]
                        + [td(esc(", ".join(f"{y}: {f}" for y, f in sorted(fdi["flags"].get(iso, {}).items()))) or "", "dim")])
        t_fdi = table(f"{lender} outward direct-investment stock by African partner country, USD million, end of year. "
                      f"OECD FDI positions (BMD4), net, all resident units, immediate counterpart.",
                      ["Partner country"] + ["#" + y for y in yrs] + ["Flags"], rows)

    oda_to = str(oda["to"])
    oda_c = sorted(((iso, s.get(oda_to, 0), sum(s.values())) for iso, s in oda["countries"].items()), key=lambda r: -r[2])
    rows = [[td(esc(_name(iso)), "name"), td(f"{v24:,.2f}", "num"), td(f"{tot:,.1f}", "num")] for iso, v24, tot in oda_c[:16]]
    t_oda = table(f"Net ODA disbursements from {lender} by recipient, USD million, current prices. OECD DAC2a, measure 206.",
                  ["Recipient", f"#{oda_to}", f"#{oda['from']}–{oda['to']}"], rows)
    return {"__TABLE_LARGE__": t_large, "__TABLE_HARD__": t_hard, "__TABLE_IDS__": t_ids,
            "__TABLE_FDI__": t_fdi, "__TABLE_ODA__": t_oda}


def _oecd_tokens(pack, crs, oda, fdi, ids):
    cs = ids["countries"]
    data_to = ids["data_to"]
    stock_latest = ids["continent"].get(str(data_to), 0)
    fdi = fdi or {"to": 0, "from": 0, "countries": {}}
    fdi_to = str(fdi["to"])
    fdi_latest = {iso: s.get(fdi_to) for iso, s in fdi["countries"].items() if s.get(fdi_to) is not None}
    fdi_total = sum(fdi_latest.values())   # net: a few counterparts carry a negative position
    fdi_top = sorted(fdi_latest.items(), key=lambda kv: -kv[1])
    oda_to = str(oda["to"])
    grants = sum(n for name, n in crs["finance"] if "grant" in name.lower())
    agencies = crs.get("agencies") or []
    crs_c = sorted(crs["countries"].items(), key=lambda kv: -kv[1]["usd"])
    return {
        "__CRS_TOP_SECTOR__": esc(crs["sectors"][0]["name"]) if crs["sectors"] else "–",
        "__CRS_TOP_SECTOR_USD__": f"{crs['sectors'][0]['usd']:,.0f}" if crs["sectors"] else "–",
        "__CRS_TOP_COUNTRY__": _name(crs_c[0][0]) if crs_c else "–",
        "__CRS_TOP_COUNTRY_USD__": f"{crs_c[0][1]['usd']:,.0f}" if crs_c else "–",
        "__CRS_TOP2_COUNTRY__": _name(crs_c[1][0]) if len(crs_c) > 1 else "–",
        "__CRS_TOP3_COUNTRY__": _name(crs_c[2][0]) if len(crs_c) > 2 else "–",
        "__CRS_AGENCY_TOP__": esc(agencies[0][0]) if agencies else "–",
        "__CRS_AGENCY_TOP_PCT__": f"{100 * agencies[0][1] / max(crs['n'], 1):.0f}" if agencies else "–",
        "__CRS_LOANS_N__": f"{sum(n for name, n in crs['measures'] if 'Loan' in name):,}",
        "__CRS_OOF_N__": f"{sum(n for name, n in crs['measures'] if 'Other Official' in name or 'Private sector' in name):,}",
        "__CRS_N__": f"{crs['n']:,}", "__CRS_USD__": f"{crs['usd']:,.0f}", "__CRS_USD_BN__": f"{crs['usd'] / 1000:,.2f}",
        "__CRS_FROM__": str(crs["from"]), "__CRS_TO__": str(crs["to"]),
        "__CRS_TITLES__": f"{crs['titles']:,}", "__CRS_COUNTRIES__": str(len(crs["countries"])),
        "__CRS_HARD_N__": f"{crs['hard']['n']:,}", "__CRS_HARD_USD__": f"{crs['hard']['usd']:,.0f}",
        "__CRS_PLACED__": f"{crs['named_place']:,}",
        "__CRS_GRANT_PCT__": f"{100 * grants / max(crs['n'], 1):.0f}",
        "__CRS_PER_YEAR__": f"{crs['n'] / max(len(crs['years']), 1):,.0f}",
        "__IDS_STOCK__": f"{stock_latest / 1e6:,.0f}", "__IDS_STOCK_BN__": f"{stock_latest / 1e9:,.2f}", "__IDS_TO__": str(data_to),
        "__IDS_N__": str(sum(1 for c in cs if c["latest_year"] == data_to and c["latest_stock"] > 0)),
        "__IDS_N_ALL__": str(len(cs)), "__IDS_UPDATED__": fmt_date(ids["updated"]), "__IDS_SINCE__": str(ids["since"]),
        "__IDS_TOP__": max(cs, key=lambda c: c["latest_stock"] if c["latest_year"] == data_to else 0)["name"] if cs else "–",
        "__FDI_STOCK__": f"{fdi_total:,.0f}", "__FDI_STOCK_BN__": f"{fdi_total / 1000:,.1f}", "__FDI_TO__": fdi_to, "__FDI_FROM__": str(fdi["from"]),
        "__FDI_TOP__": _name(fdi_top[0][0]) if fdi_top else "–",
        "__FDI_TOP_PCT__": f"{100 * fdi_top[0][1] / fdi_total:.0f}" if fdi_top and fdi_total else "–",
        "__FDI_TOP2__": _name(fdi_top[1][0]) if len(fdi_top) > 1 else "–",
        "__FDI_TOP2_PCT__": f"{100 * fdi_top[1][1] / fdi_total:.0f}" if len(fdi_top) > 1 and fdi_total else "–",
        "__FDI_TOP3__": _name(fdi_top[2][0]) if len(fdi_top) > 2 else "–",
        "__ODA_TO__": oda_to, "__ODA_FROM__": str(oda["from"]),
        "__ODA_LATEST__": f"{oda['africa'].get(oda_to, 0):,.0f}",
        "__ODA_SUM__": f"{sum(oda['africa'].values()) / 1000:,.2f}",
        "__ODA_SOM__": f"{sum(oda['countries'].get('SO', {}).values()) / 1000:,.2f}",
        "__ODA_TOP__": _name(max(oda["countries"], key=lambda k: sum(oda["countries"][k].values()))) if oda["countries"] else "–",
        "__FETCHED__": fmt_date(pack["fetched"]),
    }


def _aid_bubbles(crs, ids, lender):
    """One bubble per recipient country, sized by commitments over the window."""
    from fetch_donors import centre
    centres = {c["iso"]: (c["lon"], c["lat"]) for c in ids["countries"]}
    crs_c = sorted(crs["countries"].items(), key=lambda kv: -kv[1]["usd"])
    top = crs_c[0][1]["usd"] if crs_c else 1
    items = []
    for iso, v in crs_c:
        lon, lat = centres.get(iso) or centre(iso)
        if lon is None:
            continue
        x, y = px(lon, lat)
        items.append({"x": x, "y": y, "r": round(4 + 18 * (v["usd"] / top) ** 0.5, 1),
                      "label": _name(iso) if v["usd"] >= top / 15 else None,
                      "tip": f"<b>{esc(_name(iso))}</b>{v['n']:,} {lender} aid activities {crs['from']}–{crs['to']}"
                             f"<br>USD {v['usd']:,.1f} m committed<br>Drawn at the country's interior point"})
    return items


def _agency_chart(crs, n=8):
    return {"type": "bars", "fmt": "n", "rows": [{"label": (a[:34] + "…") if len(a) > 35 else a, "value": k, "text": f"{k:,}"}
                                                  for a, k in (crs.get("agencies") or [])[:n]]}


def _oecd_charts(crs, oda, fdi):
    fdi = fdi or {"to": 0, "countries": {}}
    fdi_to = str(fdi["to"])
    fdi_latest = sorted(((iso, s.get(fdi_to, 0)) for iso, s in fdi["countries"].items()), key=lambda kv: -kv[1])
    crs_c = sorted(crs["countries"].items(), key=lambda kv: -kv[1]["usd"])
    return {
        "c-acts": {"type": "columns", "fmt": "n", "rows": [{"x": y, "value": v["n"], "text": f"{v['n']:,}"} for y, v in crs["years"].items()]},
        "c-usd": {"type": "columns", "rows": [{"x": y, "value": v["usd"] * 1e6, "text": f"{v['usd']:,.0f}"} for y, v in crs["years"].items()]},
        "c-oda": {"type": "columns", "rows": [{"x": y, "value": v * 1e6, "text": f"{v:,.0f}"} for y, v in oda["africa"].items()]},
        "c-fdi": {"type": "bars", "rows": [{"label": _name(iso), "value": v * 1e6, "text": f"{v:,.0f}", "dim": v < 0} for iso, v in fdi_latest[:12] if v != 0]},
        "c-sect": {"type": "bars", "rows": [{"label": (s["name"][:34] + "…") if len(s["name"]) > 35 else s["name"], "value": s["usd"] * 1e6, "text": f"{s['usd']:,.0f}"} for s in crs["sectors"][:10]]},
        "c-ctry": {"type": "bars", "rows": [{"label": _name(iso), "value": v["usd"] * 1e6, "text": f"{v['usd']:,.0f}"} for iso, v in crs_c[:12]]},
    }


def _pt(r):
    x, y = px(r["lon"], r["lat"])
    return {"x": x, "y": y}


def _gem_items(gem, note):
    return [{**_pt(g), "cls": g["status"] or "announced",
             "tip": f"<b>{esc(g['name'])}</b>{esc(g['country'])} · {(g['mw'] or 0):,.0f} MW · {esc(g['tech'] or '')}<br>"
                    f"{esc(STATUS.get(g['status'], g['status'] or ''))} · owner {esc(g['owner'])}<br>Global Energy Monitor; {note}"}
            for g in gem]


def _debt_rings(ids, lender):
    return [{**_pt(c), "r": r_scale(c["latest_stock"]) + 2,
             "tip": f"<b>{esc(c['name'])}</b>Owed to {lender}: {usd(c['latest_stock'])} ({c['latest_year']})<br>Peak: {usd(c['peak_stock'])} in {c['peak_year']}"}
            for c in ids["countries"] if c["latest_stock"] > 0 and c["lon"] is not None]


# -------------------------------------------------------------- Turkey

def build_turkey(pack):
    crs, oda, fdi, ids = pack["crs"], pack["oda"], pack["fdi"], pack["ids"]
    works, gem = pack["works"], pack["gem"]
    n_works = len(works) + len(gem)

    def work_row(w, src, kind, year, status_cls, status_lbl, detail, url, srcname):
        return [td(esc(srcname), "name"), td(esc(w)), td(esc(_name(src))), td(esc(kind)), td(esc(year), "num"),
                td(f'<span class="st {status_cls}"><i></i>{esc(status_lbl)}</span>'), td(detail),
                td(f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">source</a>' if url else "–")]
    rows = []
    for w in sorted(works, key=lambda w: (w["srcname"], w["country"], w["name"])):
        detail = esc(w["note"]) + (f' <span class="dim">{esc(w["amount"])}</span>' if w.get("amount") else "")
        rows.append(work_row(w["name"], w["iso"], WORK_KIND.get(w["kind"], w["kind"].capitalize()), w["year"],
                             w["site_status"], WORK_LABEL.get(w["status"], w["status"]), detail, w["url"], w["srcname"]))
    for g in sorted(gem, key=lambda g: (g["country"], g["name"])):
        detail = esc(f"{(g['mw'] or 0):,.0f} MW, {g['tech'] or 'technology not stated'}; owner {g['owner']}")
        unit = f" (unit {g['unit']})" if g.get("unit") and g["unit"] not in ("1-1", "1", None) else ""
        rows.append(work_row(g["name"] + unit, g["iso"], "Power unit", g["year"] or "–", g["status"] or "announced",
                             STATUS.get(g["status"], g["status"] or "–"), detail + ' <span class="dim">(in the map\'s power layer)</span>', g["url"], "Global Energy Monitor"))
    t_works = table(f"{n_works} Turkish-built, Turkish-financed or Turkish-owned works with a place: the publishers' own pages, "
                    f"read 7 October 2026, and Global Energy Monitor's power tracker as the map draws it.",
                    ["Source", "Work", "Country", "Kind", "#Year", "Status", "Detail", "Link"], rows)

    tokens = _oecd_tokens(pack, crs, oda, fdi, ids)
    tokens.update(_oecd_tables(crs, oda, fdi, ids, "Turkey"))
    tokens.update({"__N_WORKS__": str(n_works), "__N_WORKS_HAND__": str(len(works)), "__N_GEM__": str(len(gem)),
                   "__TABLE_WORKS__": t_works})
    payload = {
        "map": {"groups": [
            {"id": "g-aid", "kind": "circle", "cls": "loan", "items": _aid_bubbles(crs, ids, "Turkish")},
            {"id": "g-debt", "kind": "ring", "cls": "ring", "items": _debt_rings(ids, "Turkey")},
            {"id": "g-works", "kind": "diamond",
             "items": [{**_pt(w), "cls": w["site_status"],
                        "tip": f"<b>{esc(w['name'])}</b>{esc(w['country'])} · {esc(WORK_KIND.get(w['kind'], w['kind']))} · {esc(str(w['year']))}<br>"
                               f"{esc(WORK_LABEL.get(w['status'], w['status']))}{(' · ' + esc(w['note'])) if w['note'] else ''}<br>Source: {esc(w['srcname'])}"}
                       for w in works]},
            {"id": "g-gem", "kind": "triangle", "items": _gem_items(gem, "in the map's power layer")},
        ]},
        "charts": _oecd_charts(crs, oda, fdi),
    }
    return tokens, payload


def _pipe_groups(pipes):
    """Pipeline segments grouped by pipeline name and countries."""
    groups = {}
    for pp in pipes:
        g = groups.setdefault((pp["pipeline"] or pp["name"], tuple(pp["countries"])),
                              {"segments": 0, "status": set(), "fuel": pp["fuel"], "owner": pp["parent"] or pp["owner"],
                               "km": 0.0, "url": pp["url"], "year": pp["year"]})
        g["segments"] += 1
        g["status"].add(pp["status"])
        g["km"] += pp["km"] or 0
    return groups


def _energy_table(gem, pipes, cables, caption):
    """GEM power units, pipelines (segments grouped) and cables with the
    lender's companies among the owners, as the map's own layers carry them."""
    order = ["announced", "approved", "under_construction", "operating", "stalled"]
    rows = []
    for g in sorted(gem, key=lambda g: (g["country"] or "", g["name"])):
        unit = f" (unit {g['unit']})" if g.get("unit") and g["unit"] not in ("1-1", "1", None) else ""
        rows.append([td(esc(g["name"] + unit), "name"), td(esc(g["country"])), td("Power unit"), td(esc(g["owner"])),
                     td(st(g["status"] or "announced")),
                     td(esc(f"{(g['mw'] or 0):,.0f} MW, {g['tech'] or 'technology not stated'}" + (f", from {g['year']}" if g["year"] else ""))),
                     td(f'<a href="{esc(g["url"])}" target="_blank" rel="noopener noreferrer">GEM</a>' if g["url"] else "–")])
    for (name, ctry), g in sorted(_pipe_groups(pipes).items(), key=lambda kv: (kv[0][1], kv[0][0])):
        stt = sorted(g["status"], key=lambda x: order.index(x) if x in order else 9)
        rows.append([td(esc(name), "name"), td(esc(", ".join(ctry))), td(f'{esc((g["fuel"] or "").capitalize())} pipeline'),
                     td(esc(g["owner"] or "")), td(" ".join(st(x) for x in stt if x)),
                     td(esc(f"{g['segments']} segment{'s' if g['segments'] != 1 else ''}" + (f", {g['km']:,.0f} km drawn" if g["km"] else "") + (f", from {g['year']}" if g["year"] else ""))),
                     td(f'<a href="{esc(g["url"])}" target="_blank" rel="noopener noreferrer">GEM</a>' if g["url"] else "–")])
    for c in sorted(cables, key=lambda c: c["name"]):
        af = [lp["name"] for lp in c["landing_points"] if lp.get("iso") in NAMES]
        rows.append([td(esc(c["name"]), "name"), td(esc(", ".join(sorted({lp["country"] for lp in c["landing_points"] if lp.get("iso") in NAMES})))),
                     td("Submarine cable"), td(esc(c["owners"] or "")), td(st(c["status"] or "announced")),
                     td(esc((f"ready for service {c['rfs']}" if c["rfs"] else "") + (f", {c['km']:,.0f} km" if c["km"] else "") + (f"; African landings: {', '.join(af)}" if af else ""))),
                     td(f'<a href="{esc(c["url"])}" target="_blank" rel="noopener noreferrer">TeleGeography</a>' if c["url"] else "–")])
    return table(caption, ["Asset", "Country", "Kind", "Owners", "Status", "Detail", "Link"], rows)


def _line_items(recs, cls_from_status):
    """Pipelines or cables as projected SVG paths with a tooltip each."""
    out = []
    for r in recs:
        if "tip" not in r:
            if "fuel" in r:
                r["tip"] = (f"<b>{esc(r['name'])}</b>{esc(', '.join(r['countries']))} · {esc((r['fuel'] or '').capitalize())} pipeline"
                            f"<br>{esc(STATUS.get(r['status'], r['status'] or ''))} · {esc(r.get('parent') or r.get('owner') or '')}<br>Global Energy Monitor; in the map's pipelines layer")
            else:
                r["tip"] = (f"<b>{esc(r['name'])}</b>{esc(r.get('owners') or '')}<br>{esc(STATUS.get(r['status'], r['status'] or ''))}"
                            f"{(' · ready for service ' + str(r['rfs'])) if r.get('rfs') else ''}<br>TeleGeography; in the map's cables layer")
        d = " ".join("M" + " L".join(f"{px(lon, lat)[0]} {px(lon, lat)[1]}" for lon, lat in part) for part in r["parts"] if part)
        out.append({"d": d, "cls": (r["status"] or "") if cls_from_status else "", "tip": r["tip"]})
    return out


# --------------------------------------------------------------- Italy

MATTEI_SECTOR = {"education": "Education and training", "energy": "Energy", "agriculture": "Agriculture",
                 "water": "Water", "health": "Health", "ict": "Digital", "transport": "Transport", "other": "Other"}


def build_italy(pack):
    crs, oda, fdi, ids = pack["crs"], pack["oda"], pack["fdi"], pack["ids"]
    mattei, gem, pipes, cables = pack["mattei"], pack["gem"], pack["pipelines"], pack["cables"]
    eur_total = sum(x["amount_eur"] or 0 for x in mattei)
    with_amount = sum(1 for x in mattei if x["amount_eur"])
    by_sector = {}
    for x in mattei:
        d = by_sector.setdefault(x["sector"] or "other", {"n": 0, "eur": 0.0})
        d["n"] += 1
        d["eur"] += x["amount_eur"] or 0
    sectors = sorted(by_sector.items(), key=lambda kv: -kv[1]["eur"])
    countries = sorted({c for x in mattei for c in x["countries"]})

    # ---- Piano Mattei table
    rows = []
    for x in sorted(mattei, key=lambda x: (x["countries"][0] if x["countries"] else "zz", x["name"])):
        where = ", ".join(x["countries"]) if len(x["countries"]) <= 3 else f"{len(x['countries'])} countries"
        amt = (f"{x['amount_eur'] / 1e6:,.1f}" + (' <span class="dim" title="an envelope shared with other projects">*</span>' if x["amount_shared"] else "")) if x["amount_eur"] else "–"
        rows.append([td(esc(x["name"]), "name"), td(esc(where)),
                     td(f'{esc(MATTEI_SECTOR.get(x["sector"], x["sector"]))}<br><span class="dim">{esc("; ".join(x["directives"]))}</span>'),
                     td(st(x["status"]) + f'<br><span class="dim">{esc(x["stage"])}</span>'), td(amt, "num"),
                     td(esc(x["implementer"] or "–")),
                     td(f'<a href="{esc(x["url"])}" target="_blank" rel="noopener noreferrer">portal</a>' if x["url"] else "–")])
    t_mattei = table(f"The Italian Government's Piano Mattei project list, {len(mattei)} projects as the portal states them; "
                     f"the amount is the portal's own figure, whole-project value or Italy's share, in EUR million (* shared envelope).",
                     ["Project", "Country", "Sector · directive", "Stage", "#EUR m stated", "Implementer", "Link"], rows)

    t_energy = _energy_table(gem, pipes, cables,
        "Energy and connectivity assets with an Italian owner, as the map's own layers carry them: Global Energy Monitor's "
        "power units and pipeline segments (Eni, Enel, Snam, Edison, Building Energy, Renco), TeleGeography's cables (Sparkle).")
    groups = _pipe_groups(pipes)
    tokens = _oecd_tokens(pack, crs, oda, fdi, ids)
    tokens.update(_oecd_tables(crs, oda, fdi, ids, "Italy"))
    tokens.update({
        "__MATTEI_N__": str(len(mattei)), "__MATTEI_EUR_BN__": f"{eur_total / 1e9:,.2f}", "__MATTEI_WITH_AMOUNT__": str(with_amount),
        "__MATTEI_COUNTRIES__": str(len(countries)),
        "__MATTEI_STAGES__": ", ".join(f"{n} {k.lower()}" for k, n in sorted(__import__('collections').Counter(x["stage"] for x in mattei).items(), key=lambda kv: -kv[1])),
        "__MATTEI_TOP_SECTOR__": MATTEI_SECTOR.get(sectors[0][0], sectors[0][0]).lower() if sectors else "–",
        "__MATTEI_TOP_SECTOR_N__": str(max(by_sector.items(), key=lambda kv: kv[1]["n"])[1]["n"]) if by_sector else "–",
        "__MATTEI_TOP_SECTOR_BY_N__": MATTEI_SECTOR.get(max(by_sector.items(), key=lambda kv: kv[1]["n"])[0], "").lower() if by_sector else "–",
        "__N_GEM__": str(len(gem)), "__N_PIPE_SEG__": str(len(pipes)), "__N_PIPES__": str(len(groups)), "__N_CABLES__": str(len(cables)),
        "__GEM_MW__": f"{sum(g['mw'] or 0 for g in gem if g['status'] == 'operating'):,.0f}",
        "__CRS_AGENCY_TOP__": esc(crs["agencies"][0][0]) if crs["agencies"] else "–",
        "__CRS_AGENCY_TOP_PCT__": f"{100 * crs['agencies'][0][1] / max(crs['n'], 1):.0f}" if crs["agencies"] else "–",
        "__TABLE_MATTEI__": t_mattei, "__TABLE_ENERGY__": t_energy,
    })

    charts = _oecd_charts(crs, oda, fdi)
    charts["c-mattei"] = {"type": "bars", "rows": [{"label": MATTEI_SECTOR.get(k, k), "value": v["eur"], "text": f"{v['eur'] / 1e6:,.0f} ({v['n']})"} for k, v in sectors]}
    charts["c-agency"] = _agency_chart(crs)
    payload = {
        "map": {"groups": [
            {"id": "g-aid", "kind": "circle", "cls": "loan", "items": _aid_bubbles(crs, ids, "Italian")},
            {"id": "g-debt", "kind": "ring", "cls": "ring", "items": _debt_rings(ids, "Italy")},
            {"id": "g-cables", "kind": "line", "cls": "cable", "items": _line_items(cables, False)},
            {"id": "g-pipes", "kind": "line", "cls": "pipe", "items": _line_items(pipes, True)},
            {"id": "g-mattei", "kind": "hex",
             "items": [{**_pt(x), "cls": x["status"] or "announced",
                        "tip": f"<b>{esc(x['name'])}</b>{esc(', '.join(x['countries'][:3]))}{' and others' if len(x['countries']) > 3 else ''} · {esc(MATTEI_SECTOR.get(x['sector'], x['sector'] or ''))}"
                               f"<br>{esc(x['stage'])}{(' · EUR ' + f'{x['amount_eur'] / 1e6:,.0f} m stated') if x['amount_eur'] else ''}"
                               f"<br>Piano Mattei portal; {esc(x['precision'] or '')}"} for x in mattei]},
            {"id": "g-gem", "kind": "triangle", "items": _gem_items(gem, "in the map's power layer")},
        ]},
        "charts": charts,
    }
    return tokens, payload


# --------------------------------------------------------------- China

def build_china(pack):
    aid, ids, idb = pack["aid"], pack["ids"], pack["ids_bilateral"]
    gem, pipes, cables = pack["gem"], pack["pipelines"], pack["cables"]
    cs = ids["countries"]
    data_to = ids["data_to"]
    all_now = ids["continent"].get(str(data_to), 0)
    bl_now = idb["continent"].get(str(data_to), 0)
    cont = {int(k): v for k, v in ids["continent"].items()}
    peak_year = max(cont, key=cont.get)
    now = [c for c in cs if c["latest_year"] == data_to and c["latest_stock"] > 0]
    top_debtor = max(now, key=lambda c: c["latest_stock"]) if now else None
    bl_by = {c["iso"]: c for c in idb["countries"]}
    ctry = sorted(aid["countries"].items(), key=lambda kv: -kv[1]["usd"])
    exim = next((f for f in aid["funders"] if "Eximbank" in f["funder"]), None)
    precise = aid["precision"].get("precise", 0) + aid["precision"].get("within_5km", 0)

    # ---- tables
    rows = []
    for r in aid["largest"]:
        terms = []
        if r["rate"] is not None:
            terms.append(f"{r['rate']:g}% interest")
        if r["maturity"]:
            terms.append(f"{r['maturity']:g} years")
        if r["grace"]:
            terms.append(f"{r['grace']:g} grace")
        rows.append([td(r["year"] or "–", "num"), td(esc(r["recipient"]), "name"),
                     td(f"{(r['usd_2021'] or 0) / 1e6:,.0f}" + (' <span class="dim" title="amount estimated by AidData">~</span>' if r["estimated"] else ""), "num"),
                     td(esc(r["name"]) + (f'<br><span class="dim">{esc(r["funders"] or "")}{(" · " + esc(r["implementers"])) if r["implementers"] else ""}</span>')),
                     td(f'{esc(r["flow"] or "")}<br><span class="dim">{esc("; ".join(terms))}</span>'), td(st(r["status"])),
                     td(f'<a href="{esc(r["url"])}" target="_blank" rel="noopener noreferrer">AidData</a>')])
    t_large = table(f"Largest Chinese official commitments to African infrastructure, {aid['from']}–{aid['to']}, in constant 2021 USD million "
                    f"(~ estimated by AidData). One row is one commitment; a railway financed in three tranches is three rows.",
                    ["#Year", "Recipient", "#USD m (2021)", "Project · funder · implementer", "Flow · terms", "Status", "Link"], rows)

    rows = [[td(esc(f["funder"]), "name"), td(esc(f["type"] or "")), td(f"{f['n']:,}", "num"), td(f"{f['usd']:,.0f}", "num")]
            for f in aid["funders"]]
    t_fund = table("Chinese official lenders and agencies behind the commitments; a co-financed commitment is split evenly between its funders.",
                   ["Funder", "Type", "#Commitments", "#USD m (2021)"], rows)

    rows = []
    for c in sorted(cs, key=lambda c: (-c["latest_stock"], c["name"])):
        b = bl_by.get(c["iso"])
        ld = c.get("largest_disbursement")
        rows.append([td(esc(c["name"]), "name"), td(m(c["latest_stock"], 0) if c["latest_stock"] else "–", "num"),
                     td(m(b["latest_stock"], 0) if b and b["latest_stock"] and b["latest_year"] == c["latest_year"] else "–", "num"),
                     td(c["latest_year"] or "–", "num"), td(m(c["peak_stock"], 0), "num"), td(c["peak_year"] or "–", "num"),
                     td(m(ld["usd"], 0) if ld else "–", "num"), td(ld["year"] if ld else "–", "num")])
    t_ids = table(f"Public and publicly guaranteed debt owed by African governments to Chinese creditors, USD million: all Chinese creditors "
                  f"(counterpart 730, series DPPG) and, beside it, the bilateral official part (series BLAT). World Bank International Debt "
                  f"Statistics, release of {fmt_date(ids['updated'])}.",
                  ["Debtor", "#Owed to all Chinese creditors", "#of which bilateral official", "#Year", "#Peak (all)", "#Peak year",
                   "#Largest annual disbursement", "#Year"], rows)

    t_energy = _energy_table(gem, pipes, cables,
        "Energy and connectivity assets with a Chinese owner, as the map's own layers carry them: Global Energy Monitor's power units and "
        "pipeline segments (state and provincial companies, CNPC, CNOOC, Sinopec), TeleGeography's cables (China Mobile, China Telecom, "
        "China Unicom, PEACE Cable).")

    lo = aid["left_out"]
    tokens = {
        "__AID_N__": f"{aid['n']:,}", "__AID_USD_BN__": f"{aid['usd'] / 1000:,.1f}", "__AID_FROM__": str(aid["from"]), "__AID_TO__": str(aid["to"]),
        "__AID_LOANS_N__": f"{aid['loans_n']:,}", "__AID_LOANS_BN__": f"{aid['loans_usd'] / 1000:,.1f}",
        "__AID_GRANTS_N__": f"{aid['grants_n']:,}", "__AID_GRANTS_BN__": f"{aid['grants_usd'] / 1000:,.1f}",
        "__AID_COUNTRIES__": str(len(aid["countries"])), "__AID_FUNDERS__": str(len(aid["funders"])),
        "__AID_EXIM_PCT__": f"{100 * exim['usd'] / aid['usd']:.0f}" if exim else "–",
        "__AID_TOP_COUNTRY__": _name(ctry[0][0]) if ctry else "–", "__AID_TOP_COUNTRY_BN__": f"{ctry[0][1]['usd'] / 1000:,.1f}" if ctry else "–",
        "__AID_TOP2_COUNTRY__": _name(ctry[1][0]) if len(ctry) > 1 else "–", "__AID_TOP3_COUNTRY__": _name(ctry[2][0]) if len(ctry) > 2 else "–",
        "__AID_TOP_SECTOR__": aid["sectors"][0]["sector"] if aid["sectors"] else "–",
        "__AID_TOP_SECTOR_BN__": f"{aid['sectors'][0]['usd'] / 1000:,.1f}" if aid["sectors"] else "–",
        "__AID_DISTRESS__": f"{aid['distress_n']:,}", "__AID_ESTIMATED__": f"{aid['estimated_n']:,}", "__AID_COFIN__": f"{aid['cofinanced_n']:,}",
        "__AID_PRECISE__": f"{precise:,}", "__AID_PRECISE_PCT__": f"{100 * precise / aid['n']:.0f}",
        "__AID_COUNTRY_ONLY__": f"{aid['precision'].get('country', 0):,}", "__AID_FOOTPRINTS__": f"{aid['footprints'] or 0:,}",
        "__AID_OPERATING__": f"{aid['status'].get('operating', 0):,}", "__AID_BUILDING__": f"{aid['status'].get('under_construction', 0):,}",
        "__AID_APPROVED__": f"{aid['status'].get('approved', 0):,}", "__AID_STALLED__": f"{aid['status'].get('stalled', 0):,}",
        "__AID_UMBRELLA__": f"{lo.get('umbrella') or 0:,}", "__AID_PLEDGES__": f"{lo.get('pledges') or 0:,}",
        "__AID_NOT_INFRA__": f"{lo.get('not_infrastructure') or 0:,}", "__AID_RELEASE__": esc(aid["release"] or ""),
        "__AID_ODA_LIKE__": f"{aid['flow_class'].get('ODA-like', 0):,}", "__AID_OOF_LIKE__": f"{aid['flow_class'].get('OOF-like', 0):,}",
        "__IDS_ALL_BN__": f"{all_now / 1e9:,.1f}", "__IDS_BL_BN__": f"{bl_now / 1e9:,.1f}", "__IDS_N__": str(len(now)),
        "__IDS_N_ALL__": str(len(cs)), "__IDS_TO__": str(data_to), "__IDS_UPDATED__": fmt_date(ids["updated"]),
        "__IDS_TOP__": top_debtor["name"] if top_debtor else "–", "__IDS_TOP_BN__": f"{top_debtor['latest_stock'] / 1e9:,.1f}" if top_debtor else "–",
        "__IDS_PEAK_YEAR__": str(peak_year), "__IDS_PEAK_BN__": f"{cont[peak_year] / 1e9:,.1f}",
        "__IDS_2000_BN__": f"{cont.get(2000, 0) / 1e9:,.1f}",
        "__N_GEM__": str(len(gem)), "__N_PIPE_SEG__": str(len(pipes)), "__N_PIPES__": str(len(_pipe_groups(pipes))), "__N_CABLES__": str(len(cables)),
        "__GEM_MW__": f"{sum(g['mw'] or 0 for g in gem if g['status'] == 'operating'):,.0f}",
        "__FETCHED__": fmt_date(pack["fetched"]),
        "__TABLE_LARGE__": t_large, "__TABLE_FUNDERS__": t_fund, "__TABLE_IDS__": t_ids, "__TABLE_ENERGY__": t_energy,
    }

    # ---- what the page draws
    from fetch_donors import centre
    centres = {c["iso"]: (c["lon"], c["lat"]) for c in cs}
    top_usd = ctry[0][1]["usd"] if ctry else 1
    bubbles = []
    for iso, v in ctry:
        lon, lat = centres.get(iso) or centre(iso)
        if lon is None:
            continue
        x, y = px(lon, lat)
        bubbles.append({"x": x, "y": y, "r": round(4 + 18 * (v["usd"] / top_usd) ** 0.5, 1),
                        "label": _name(iso) if v["usd"] >= top_usd / 15 else None,
                        "tip": f"<b>{esc(_name(iso))}</b>{v['n']:,} Chinese official commitments {aid['from']}–{aid['to']}"
                               f"<br>USD {v['usd'] / 1000:,.1f} bn (2021 USD), of which loans USD {v['loans'] / 1000:,.1f} bn<br>Drawn at the country's interior point"})
    biggest = sorted(aid["largest"], key=lambda r: -(r["usd_2021"] or 0))
    projects = [{**_pt(r), "cls": r["status"],
                 "tip": f"<b>{esc(r['name'][:140])}</b>{esc(r['recipient'])} · {r['year']} · USD {(r['usd_2021'] or 0) / 1e6:,.0f} m (2021)"
                        f"<br>{esc(STATUS.get(r['status'], r['status']))} · {esc(r['funders'] or '')}<br>AidData; {esc(r['precision'])} location"}
                for r in sorted(pack["aid"]["largest"], key=lambda r: -(r["usd_2021"] or 0))]
    # the 150 largest records beyond the table's 20, read back from the layer
    import json as _json
    allrecs = _json.loads((DATA / "aiddata_china_finance.geojson").read_text())["features"]
    big = sorted(allrecs, key=lambda f: -(f["properties"]["amount_usd_2021"] or 0))[:150]
    projects = [{**_pt({"lon": f["properties"]["lon"], "lat": f["properties"]["lat"]}), "cls": f["properties"]["dash_status"],
                 "tip": f"<b>{esc(f['properties']['name'][:140])}</b>{esc(f['properties']['recipient'])} · {f['properties']['commitment_year']} · "
                        f"USD {(f['properties']['amount_usd_2021'] or 0) / 1e6:,.0f} m (2021)<br>{esc(STATUS.get(f['properties']['dash_status'], ''))} · "
                        f"{esc(f['properties']['funders'] or '')}<br>AidData; {esc(f['properties']['geo_precision'])} location"}
                for f in big if f["properties"]["lon"] is not None]
    charts = {
        "c-usd": {"type": "columns", "rows": [{"x": y, "value": v["usd"] * 1e6, "text": f"{v['usd'] / 1000:,.1f}"} for y, v in aid["years"].items()]},
        "c-n": {"type": "columns", "fmt": "n", "rows": [{"x": y, "value": v["n"], "text": f"{v['n']:,}"} for y, v in aid["years"].items()]},
        "c-debt": {"type": "line", "series": {str(y): v for y, v in sorted(cont.items()) if y >= 2000}, "label": "owed to Chinese creditors",
                   "notes": [{"year": peak_year, "text": f"USD {cont[peak_year] / 1e9:,.0f} bn peak", "dx": 0, "dy": -10, "anchor": "middle"},
                             {"year": data_to, "text": f"USD {all_now / 1e9:,.0f} bn", "dx": -8, "dy": 14, "anchor": "end"}]},
        "c-owe": {"type": "bars", "rows": [{"label": c["name"], "value": c["latest_stock"], "text": f"{c['latest_stock'] / 1e9:,.1f} bn"}
                                           for c in sorted(now, key=lambda c: -c["latest_stock"])[:12]]},
        "c-fund": {"type": "bars", "rows": [{"label": (f["funder"].split(" (")[0][:34] + "…") if len(f["funder"].split(" (")[0]) > 35 else f["funder"].split(" (")[0],
                                             "value": f["usd"] * 1e6, "text": f"{f['usd'] / 1000:,.1f} bn"} for f in aid["funders"][:10]]},
        "c-sect": {"type": "bars", "rows": [{"label": s_["sector"].capitalize(), "value": s_["usd"] * 1e6, "text": f"{s_['usd'] / 1000:,.1f} bn ({s_['n']})"} for s_ in aid["sectors"][:10]]},
        "c-ctry": {"type": "bars", "rows": [{"label": _name(iso), "value": v["usd"] * 1e6, "text": f"{v['usd'] / 1000:,.1f} bn"} for iso, v in ctry[:12]]},
        "c-status": {"type": "bars", "fmt": "n", "rows": [{"label": STATUS.get(k, k), "value": n, "text": f"{n:,}"} for k, n in sorted(aid["status"].items(), key=lambda kv: -kv[1])]},
    }
    payload = {
        "map": {"groups": [
            {"id": "g-aid", "kind": "circle", "cls": "loan", "items": bubbles},
            {"id": "g-debt", "kind": "ring", "cls": "ring", "items": _debt_rings(ids, "Chinese creditors")},
            {"id": "g-cables", "kind": "line", "cls": "cable", "items": _line_items(cables, False)},
            {"id": "g-pipes", "kind": "line", "cls": "pipe", "items": _line_items(pipes, True)},
            {"id": "g-proj", "kind": "triangle", "items": projects},
            {"id": "g-gem", "kind": "diamond", "items": _gem_items(gem, "in the map's power layer")},
        ]},
        "charts": charts,
    }
    return tokens, payload


# ------------------------------------- the generic OECD-backed profile (US, Germany)

def build_oecd_profile(pack, lender, adj, energy_caption):
    crs, oda, fdi, ids = pack["crs"], pack["oda"], pack.get("fdi"), pack["ids"]
    gem, pipes, cables = pack.get("gem") or [], pack.get("pipelines") or [], pack.get("cables") or []
    tokens = _oecd_tokens(pack, crs, oda, fdi, ids)
    tokens.update(_oecd_tables(crs, oda, fdi, ids, lender))
    tokens.update({"__N_GEM__": str(len(gem)), "__N_PIPE_SEG__": str(len(pipes)), "__N_PIPES__": str(len(_pipe_groups(pipes))),
                   "__N_CABLES__": str(len(cables)),
                   "__GEM_MW__": f"{sum(g['mw'] or 0 for g in gem if g['status'] == 'operating'):,.0f}",
                   "__TABLE_ENERGY__": _energy_table(gem, pipes, cables, energy_caption) if (gem or pipes or cables) else ""})
    charts = _oecd_charts(crs, oda, fdi)
    charts["c-agency"] = _agency_chart(crs)
    groups = [{"id": "g-aid", "kind": "circle", "cls": "loan", "items": _aid_bubbles(crs, ids, adj)},
              {"id": "g-debt", "kind": "ring", "cls": "ring", "items": _debt_rings(ids, lender)}]
    if cables:
        groups.append({"id": "g-cables", "kind": "line", "cls": "cable", "items": _line_items(cables, False)})
    if pipes:
        groups.append({"id": "g-pipes", "kind": "line", "cls": "pipe", "items": _line_items(pipes, True)})
    if gem:
        groups.append({"id": "g-gem", "kind": "diamond", "items": _gem_items(gem, "in the map's power layer")})
    return tokens, {"map": {"groups": groups}, "charts": charts}


def build_usa(pack):
    return build_oecd_profile(pack, "the United States", "US",
        "Energy and connectivity assets with a United States owner, as the map's own layers carry them: Global Energy Monitor's "
        "power units and pipeline segments (the oil majors, General Electric, Symbion, AES), TeleGeography's cables (Google, Meta, AT&T).")


def build_germany(pack):
    return build_oecd_profile(pack, "Germany", "German",
        "Energy and connectivity assets with a German owner, as the map's own layers carry them: Global Energy Monitor's power "
        "units (juwi, ib vogt, BayWa r.e., Siemens) and TeleGeography's cables.")


# ------------------------------------------------------ European Union

def _two_series_ids_table(ids_a, ids_b, label_a, label_b, caption):
    by_b = {c["iso"]: c for c in ids_b["countries"]}
    rows = []
    isos = {c["iso"] for c in ids_a["countries"]} | set(by_b)
    by_a = {c["iso"]: c for c in ids_a["countries"]}
    for iso in sorted(isos, key=lambda i: -((by_a.get(i) or {}).get("latest_stock", 0) + (by_b.get(i) or {}).get("latest_stock", 0))):
        a, b = by_a.get(iso), by_b.get(iso)
        name = (a or b)["name"]
        ld = (a or {}).get("largest_disbursement")
        rows.append([td(esc(name), "name"),
                     td(m(a["latest_stock"], 0) if a and a["latest_stock"] else "–", "num"), td(a["latest_year"] if a and a["latest_year"] else "–", "num"),
                     td(m(b["latest_stock"], 0) if b and b["latest_stock"] else "–", "num"), td(b["latest_year"] if b and b["latest_year"] else "–", "num"),
                     td(m(a["peak_stock"], 0) if a and a["peak_stock"] else "–", "num"), td(a["peak_year"] if a and a["peak_year"] else "–", "num"),
                     td(m(ld["usd"], 0) if ld else "–", "num"), td(ld["year"] if ld else "–", "num")])
    return table(caption, ["Debtor", f"#Owed to {label_a}", "#Year", f"#Owed to {label_b}", "#Year", f"#Peak ({label_a})", "#Peak year",
                           f"#Largest annual disbursement ({label_a})", "#Year"], rows)


def build_eu(pack):
    from shared import EUR_NOTE
    crs, oda, ids, ids_eu, layer = pack["crs"], pack["oda"], pack["ids"], pack["ids_eu"], pack["layer"]
    tokens = _oecd_tokens(pack, crs, oda, None, ids)
    tokens.update(_oecd_tables(crs, oda, None, ids, "the EU institutions"))
    data_to = ids["data_to"]
    eu_now = ids_eu["continent"].get(str(data_to), 0)
    pubs = {x["publisher"]: x for x in layer["publishers"]}
    ec = pubs.get("European Commission", {"n": 0, "usd": 0})
    eib = pubs.get("European Investment Bank", {"n": 0, "usd": 0})
    sect = [x for x in layer["sectors"] if x["sector"] != "other"]
    tokens["__TABLE_IDS__"] = _two_series_ids_table(ids, ids_eu, "the EIB", "the EU budget, EDF and EEC",
        f"Public and publicly guaranteed debt owed by African governments to the European Investment Bank (counterpart 919) and to the "
        f"European Union's budget, the European Development Fund and the former EEC (975, 918, 917), USD million. World Bank "
        f"International Debt Statistics, release of {fmt_date(ids['updated'])}.")

    rows = []
    for r in layer["largest"]:
        where = NAMES.get(r["iso"], r["iso"]) if r["iso"] else (", ".join(NAMES.get(c, c) for c in r["countries"][:3]) + (" and others" if len(r["countries"]) > 3 else "")) if r["countries"] else "regional"
        rows.append([td(r["year"] or "–", "num"), td(esc(where), "name"), td(f"{r['eur'] / 1e6:,.1f}", "num"),
                     td(esc(r["name"]) + f'<br><span class="dim">{esc(r["lender"])} · {esc(r["kind"])}{(" · " + esc(r["implementers"][:80])) if r["implementers"] else ""}</span>'),
                     td(esc(r["sector"].capitalize())), td(st(r["status"])),
                     td(f'<a href="{esc(r["url"])}" target="_blank" rel="noopener noreferrer">record</a>' if r["url"] else f'<span class="m dim">{esc(r["id"] or "")}</span>')])
    t_layer = table(f"Largest records in the map's EU finance layer: European Commission contracts and financing decisions and EIB operations "
                    f"for infrastructure, from the institutions' IATI files, in EUR million as published ({EUR_NOTE} where converted).",
                    ["#Start", "Where", "#EUR m", "Record · institution · implementer", "Sector", "Status", "Link"], rows)
    tokens.update({
        "__LAYER_N__": f"{layer['n']:,}", "__LAYER_EUR_BN__": f"{layer['eur'] / 1000:,.1f}", "__LAYER_USD_BN__": f"{layer['usd'] / 1000:,.1f}",
        "__LAYER_EC_N__": f"{ec['n']:,}", "__LAYER_EIB_N__": f"{eib['n']:,}", "__LAYER_EIB_USD_BN__": f"{eib['usd'] / 1000:,.1f}",
        "__LAYER_EC_USD_BN__": f"{ec['usd'] / 1000:,.1f}",
        "__LAYER_CONTRACTS__": f"{layer['kind'].get('contract', 0):,}", "__LAYER_DECISIONS__": f"{layer['kind'].get('decision', 0):,}",
        "__LAYER_OPERATIONS__": f"{layer['kind'].get('operation', 0):,}",
        "__LAYER_NAMED__": f"{layer['precision'].get('1', 0):,}", "__LAYER_COUNTRY__": f"{layer['precision'].get('2', 0):,}",
        "__LAYER_REGIONAL__": f"{layer['precision'].get('3', 0):,}",
        "__LAYER_TOP_SECTOR__": sect[0]["sector"] if sect else "–", "__LAYER_TOP_SECTOR_BN__": f"{sect[0]['usd'] / 1000:,.2f}" if sect else "–",
        "__LAYER_FROM__": str(layer["from"]), "__LAYER_TO__": str(layer["to"]),
        "__IDS_EU_BN__": f"{eu_now / 1e9:,.2f}", "__IDS_EU_N__": str(sum(1 for c in ids_eu["countries"] if c["latest_year"] == data_to and c["latest_stock"] > 0)),
        "__IDS_EIB_BN__": f"{ids['continent'].get(str(data_to), 0) / 1e9:,.1f}",
        "__TABLE_LAYER__": t_layer,
    })
    charts = _oecd_charts(crs, oda, None)
    charts.pop("c-fdi", None)
    charts["c-agency"] = _agency_chart(crs, 6)
    charts["c-layer-year"] = {"type": "columns", "rows": [{"x": y, "value": v["usd"] * 1e6, "text": f"{v['usd']:,.0f}"} for y, v in layer["years"].items() if int(y) >= 2010]}
    charts["c-layer-sect"] = {"type": "bars", "rows": [{"label": x["sector"].capitalize(), "value": x["usd"] * 1e6, "text": f"{x['usd']:,.0f} ({x['n']})"} for x in layer["sectors"][:9]]}
    charts["c-owe"] = {"type": "bars", "rows": [{"label": c["name"], "value": c["latest_stock"], "text": f"{c['latest_stock'] / 1e6:,.0f}"}
                                                for c in sorted((c for c in ids["countries"] if c["latest_year"] == data_to), key=lambda c: -c["latest_stock"])[:12]]}
    # the layer's commitments by country are the bubbles; the 150 largest records are stars, as on the map
    from fetch_donors import centre
    lc = sorted(layer["countries"].items(), key=lambda kv: -kv[1]["usd"])
    top = lc[0][1]["usd"] if lc else 1
    bubbles = []
    for iso, v in lc:
        lon, lat = centre(iso)
        if lon is None:
            continue
        x, y = px(lon, lat)
        bubbles.append({"x": x, "y": y, "r": round(4 + 18 * (v["usd"] / top) ** 0.5, 1), "label": _name(iso) if v["usd"] >= top / 15 else None,
                        "tip": f"<b>{esc(_name(iso))}</b>{v['n']:,} EU finance records in the map's layer<br>USD {v['usd']:,.0f} m committed (EUR converted at the stated rate)<br>Drawn at the country's interior point"})
    stars = [{**_pt(r), "cls": r["status"],
              "tip": f"<b>{esc(r['name'])}</b>{esc(r['country'])} · {r['year'] or ''} · USD {r['usd_m']:,.0f} m<br>{esc(STATUS.get(r['status'], r['status'] or ''))} · {esc(r['lender'])}, {esc(r['kind'])}<br>IATI; location tier {r['precision']}"}
             for r in layer["points"] if r["lon"] is not None]
    payload = {"map": {"groups": [
        {"id": "g-aid", "kind": "circle", "cls": "loan", "items": bubbles},
        {"id": "g-debt", "kind": "ring", "cls": "ring", "items": _debt_rings(ids, "the EIB")},
        {"id": "g-layer", "kind": "star", "items": stars},
    ]}, "charts": charts}
    return tokens, payload


def build_france(pack):
    return build_oecd_profile(pack, "France", "French",
        "Energy and connectivity assets with a French owner, as the map's own layers carry them: Global Energy Monitor's power units and "
        "pipeline segments (TotalEnergies, EDF, Engie, Qair, Voltalia, Perenco, Meridiam), TeleGeography's cables (Orange).")


def build_spain(pack):
    return build_oecd_profile(pack, "Spain", "Spanish",
        "Energy and connectivity assets with a Spanish owner, as the map's own layers carry them: Global Energy Monitor's power units "
        "(Acciona, Sener, Elecnor, Abengoa, Cobra) and pipeline segments (Naturgy, Enagás, Repsol), TeleGeography's cables (Telefónica).")


def build_japan(pack):
    return build_oecd_profile(pack, "Japan", "Japanese",
        "Energy assets with a Japanese owner, as the map's own layers carry them: Global Energy Monitor's power units (Eurus, Toyota Tsusho, "
        "Sumitomo) and pipeline segments (Sojitz).")


def build_nordics(pack):
    tokens, payload = build_oecd_profile(pack, "the Nordic countries", "Nordic",
        "Energy assets with a Nordic owner, as the map's own layers carry them: Global Energy Monitor's power units (Scatec, Frontier Energy, "
        "Norsk Hydro, Finnfund, KLP, Wärtsilä) and pipeline segments (Equinor).")
    prov = pack["crs"].get("providers") or []
    tokens["__PROVIDERS__"] = ", ".join(f"{esc(k)} {n:,}" for k, n, _ in prov)
    tokens["__PROVIDERS_USD__"] = ", ".join(f"{esc(k)} USD {u:,.0f} m" for k, _, u in sorted(prov, key=lambda r: -r[2]))
    payload["charts"]["c-prov"] = {"type": "bars", "rows": [{"label": k, "value": u * 1e6, "text": f"{u:,.0f} ({n:,})"} for k, n, u in sorted(prov, key=lambda r: -r[2])]}
    return tokens, payload


def build_gulf(pack):
    tokens, payload = build_oecd_profile(pack, "the Gulf states", "Gulf",
        "Energy and connectivity assets with a Gulf owner, as the map's own layers carry them: Global Energy Monitor's power units and "
        "pipeline segments (ACWA Power, AMEA Power, Masdar, TAQA, Phanes, Al Nowais, Alcazar, Aramco), TeleGeography's cables "
        "(STC's center3, Mobily, du, Etisalat, Ooredoo, Zain).")
    ids, funds = pack["ids"], pack["ids_funds"]
    data_to = ids["data_to"]
    prov = pack["crs"].get("providers") or []
    tokens["__PROVIDERS__"] = ", ".join(f"{esc(k)} {n:,}" for k, n, _ in prov)
    tokens["__PROVIDERS_USD__"] = ", ".join(f"{esc(k)} USD {u:,.0f} m" for k, _, u in sorted(prov, key=lambda r: -r[2]))
    tokens["__IDS_FUNDS_BN__"] = f"{funds['continent'].get(str(data_to), 0) / 1e9:,.2f}"
    tokens["__IDS_FUNDS_N__"] = str(sum(1 for c in funds["countries"] if c["latest_year"] == data_to and c["latest_stock"] > 0))
    tokens["__IDS_STATES_BN__"] = f"{ids['continent'].get(str(data_to), 0) / 1e9:,.2f}"
    tokens["__TABLE_IDS__"] = _two_series_ids_table(ids, funds, "the four states", "the Gulf-based funds",
        f"Public and publicly guaranteed debt owed by African governments to the United Arab Emirates, Saudi Arabia, Kuwait and Qatar "
        f"(counterparts 576, 566, 552, 561, summed) and to the Gulf-based development funds (the Arab Fund for Economic and Social "
        f"Development, the OPEC Fund, the Islamic Development Bank, BADEA and the Arab technical-assistance fund for Africa: 921, 951, 976, 953, 980), "
        f"USD million. World Bank International Debt Statistics, release of {fmt_date(ids['updated'])}.")
    payload["charts"]["c-prov"] = {"type": "bars", "rows": [{"label": k, "value": u * 1e6, "text": f"{u:,.0f} ({n:,})"} for k, n, u in sorted(prov, key=lambda r: -r[2])]}
    payload["charts"]["c-funds"] = {"type": "bars", "rows": [{"label": c["name"], "value": c["latest_stock"], "text": f"{c['latest_stock'] / 1e6:,.0f}"}
                                                            for c in sorted((c for c in funds["countries"] if c["latest_year"] == data_to), key=lambda c: -c["latest_stock"])[:12]]}
    return tokens, payload


BUILDERS = {"russia": build_russia, "turkey": build_turkey, "italy": build_italy, "china": build_china,
            "eu": build_eu, "usa": build_usa, "germany": build_germany,
            "france": build_france, "spain": build_spain, "japan": build_japan, "nordics": build_nordics, "gulf": build_gulf}


# --------------------------------------------------------------- build

def jsonld(d, path):
    page = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebPage", "@id": site_url(path), "url": site_url(path), "name": d["title"],
             "description": d["description"], "inLanguage": "en",
             "isPartOf": {"@type": "WebSite", "@id": site_url("#website"), "name": SITE_NAME, "url": SITE_URL},
             "author": {"@type": "Person", "name": AUTHOR_NAME, "url": WEB_URL, "sameAs": [AUTHOR_URL]},
             "about": {"@type": "Country", "name": d["name"]},
             "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": [
                 {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": SITE_URL},
                 {"@type": "ListItem", "position": 2, "name": d["name"], "item": site_url(path)}]}},
        ]}
    return ('<script type="application/ld+json">'
            + json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n")


def build(d, land):
    slug = d["slug"]
    src = DATA / "donors" / f"{slug}.json"
    if not src.exists():
        sys.exit(f"missing {src.relative_to(ROOT)} — run fetch_donors.py {slug} first")
    pack = json.loads(src.read_text())
    frag = (ROOT / "donors" / f"{slug}.html").read_text()
    tokens, payload = BUILDERS[slug](pack)
    tokens.update({
        "__TITLE__": esc(d["title"]),
        "__MAP_W__": f"{MAP_W:.0f}", "__MAP_H__": f"{MAP_H:.0f}",
        "__DATA_URL__": site_url(f"data/donors/{slug}.json"),
        "__DATA_FILE__": f"{slug}.json",
        "__BUILT__": fmt_date(today()),
    })
    page = FRAME.read_text().replace("<!--__BODY__-->", frag, 1)
    for k, v in tokens.items():
        page = page.replace(k, v)
    page = page.replace("<!--__LAND__-->", land, 1)
    page = page.replace("/*__PAYLOAD__*/", json.dumps(payload, ensure_ascii=False, separators=(",", ":")), 1)
    page = brand_assets(page, donor=slug)
    left = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]*__", page)))
    if left:
        sys.exit(f"{slug}: unfilled tokens {', '.join(left)}")
    path = f"{slug}/index.html"
    doc = wrap_document(page, title=d["title"], description=d["description"], path=path, kind="profile",
                        extra_head=jsonld(d, path))
    out = DOCS / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(doc)
    (DOCS / "data" / "donors").mkdir(parents=True, exist_ok=True)
    shutil.copy(src, DOCS / "data" / "donors" / src.name)
    print(f"→ docs/{path}  {len(doc.encode()) / 1024:.0f} KB  (+ docs/data/donors/{src.name})")


def main(argv):
    wanted = argv or [d["slug"] for d in DONORS]
    by_slug = {d["slug"]: d for d in DONORS}
    unknown = [w for w in wanted if w not in by_slug or w not in BUILDERS]
    if unknown:
        sys.exit(f"no profile for {', '.join(unknown)}; known: {', '.join(BUILDERS)}")
    land = land_paths()
    for slug in wanted:
        build(by_slug[slug], land)


if __name__ == "__main__":
    main(sys.argv[1:])
