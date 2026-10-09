#!/usr/bin/env python3
"""
Build the lender comparison, docs/compare/index.html, from the seven lender
packs (data/donors/*.json) and the debt pack (data/debt.json).

    python3 build_compare.py

No fetching: everything here is a re-cut of what the profiles and the debt
section already hold, so the comparison cannot disagree with them. The page
wears the profiles' frame (donor.template.html) with sections/compare.html as
its body. The summary table and the figures in the prose are rendered here,
in Python, so a crawler reads the substance; the maps and the charts are
drawn by the page's own script from the payload inlined at /*__CMP__*/ and
redrawn as the reader filters by lender, region or country, year and
measure. The payload is also written to docs/data/compare.json.

Amounts are USD million throughout the payload. Debt is the World Bank's
stock by creditor (public and publicly guaranteed, current USD); aid is the
OECD CRS commitments of the five lenders that report to the DAC and AidData's
commitments for China; net ODA is OECD DAC2a; FDI positions are the OECD's.
"""

import json
import pathlib
import re
import shutil
import sys

from build_donors import FRAME, MAP_H, MAP_W, esc, px, table, td
from fetch_donors import CRS_GROUPS, NAME, centre, crs_group
from shared import (AUTHOR_NAME, AUTHOR_URL, DATA, DOCS, DONORS, SITE_NAME, SITE_URL, WEB_URL,
                    brand_assets, fmt_date, site_url, today, wrap_document)

ROOT = pathlib.Path(__file__).parent
FRAG = ROOT / "sections" / "compare.html"
SLUG = "compare"
TITLE = "Seven lenders, side by side"
DESCRIPTION = ("China, the European Union, the United States, Germany, Italy, Turkey and Russia compared as "
               "lenders to Africa: where each one's money goes, country by country, what it funds, how it is "
               "lent and how its exposure moved since 2000, with filters by lender, region or country, year and "
               "measure, from the World Bank's International Debt Statistics, the OECD's Creditor Reporting "
               "System and AidData.")

# Display order and colour slot of each lender. The order is the categorical
# palette's validated order (blue, orange, aqua, yellow, magenta, green,
# violet: the --ld-* tokens in sections/compare.html), so neighbours stay apart
# under colour blindness; China, the EU and the United States keep the hues the
# debt section gives their creditor groups. Colour never carries identity
# alone: every mark on the page is labelled with the lender's name or badge.
LENDERS = ["italy", "turkey", "china", "eu", "russia", "usa", "germany"]

# World Bank IDS counterpart codes in data/debt.json, per lender. The EU is
# the European Investment Bank plus the EU budget, the European Development
# Fund and the old EEC loans, as the EU profile counts them.
DEBT_CODES = {"russia": ["087"], "turkey": ["055"], "italy": ["006"], "china": ["730"],
              "eu": ["919", "975", "918", "917"], "usa": ["302"], "germany": ["005"]}

# The UN geoscheme's five African subregions, the page's region filter.
REGIONS = [("north", "North Africa", "DZ EG LY MA SD TN"),
           ("west", "West Africa", "BJ BF CV CI GM GH GN GW LR ML MR NE NG SN SL TG"),
           ("central", "Central Africa", "AO CM CF TD CG CD GQ GA ST"),
           ("east", "East Africa", "BI KM DJ ER ET KE MG MW MU MZ RW SC SO SS TZ UG ZM ZW"),
           ("southern", "Southern Africa", "BW SZ LS NA ZA")]
REGION_OF = {iso: rid for rid, _, isos in REGIONS for iso in isos.split()}
assert set(REGION_OF) == set(NAME), sorted(set(NAME) ^ set(REGION_OF))

# AidData's sectors onto the DAC groups, so China's row reads on the same grid
AIDDATA_GROUP = {"transport": "transport", "energy": "energy", "industry": "industry", "ict": "comms",
                 "social": "social", "water": "water", "other": "other", "government": "government",
                 "education": "education", "agriculture": "agriculture", "health": "health",
                 "trade": "finance", "environment": "environment"}

# CRS delivery channels folded into five kinds, the "who delivers it" grid
CHANNEL_KINDS = [("own", "Own government and agencies"), ("recipient", "Recipient government"),
                 ("ngo", "NGOs"), ("private", "Private sector"), ("other", "Universities, multilaterals, other")]


def channel_kind(name):
    n = (name or "").lower()
    if "donor govt" in n or n == "donor government" or "in donor country" in n:
        return "own"
    if "recipient govt" in n or n == "recipient government":
        return "recipient"
    if "ngo" in n:
        return "ngo"
    if "private sector" in n:
        return "private"
    return "other"


def load():
    debt_path = DATA / "debt.json"
    if not debt_path.exists():
        sys.exit("missing data/debt.json — run fetch_debt.py first")
    packs = {}
    for slug in LENDERS:
        p = DATA / "donors" / f"{slug}.json"
        if not p.exists():
            sys.exit(f"missing {p.relative_to(ROOT)} — run fetch_donors.py {slug} first")
        packs[slug] = json.loads(p.read_text())
    return packs, json.loads(debt_path.read_text())


# ----------------------------------------------------------------- geometry

def land_defs():
    """Every country of the 1:110m basemap as one <path id="p-XX"> in a
    <defs>, drawn once and reused by every small map with <use>; the
    territories without a profile row (Western Sahara, Somaliland) go into
    one context path."""
    bm = json.loads((DATA / "africa_basemap.json").read_text())
    defs, ctx = [], []
    for c in bm["countries"]:
        d = []
        for poly in c["p"]:
            for ring in poly:
                d.append("M" + " L".join(f"{x} {y}" for x, y in (px(a, b) for a, b in ring)) + " Z")
        if c.get("iso") in NAME:
            defs.append(f'<path id="p-{c["iso"]}" d="{" ".join(d)}"/>')
        else:
            ctx.append(" ".join(d))
    defs.append(f'<path id="p-ctx" d="{" ".join(ctx)}"/>')
    return "\n".join(defs)


# ------------------------------------------------------------------ payload

def m2(v):
    return round(v, 2)


def debt_block(debt):
    years = list(range(debt["first_year"], debt["data_to"] + 1))
    out, total = {}, {}
    for iso, c in debt["countries"].items():
        total[iso] = [m2(c["total"].get(str(y), 0) / 1e6) for y in years]
    for slug, codes in DEBT_CODES.items():
        rows = {}
        for iso, c in debt["countries"].items():
            s = [m2(sum(c["creditors"].get(code, {}).get(str(y), 0) for code in codes) / 1e6) for y in years]
            if any(v > 0 for v in s):
                rows[iso] = s
        out[slug] = rows
    return years, out, total


def series_block(packs, key, years):
    """Per lender, per country, one value a year (USD m) from an OECD block
    with {iso: {year: value}}; None where the year is missing."""
    out, extra = {}, {}
    for slug in LENDERS:
        blk = packs[slug].get(key)
        if not blk:
            continue
        rows = {}
        for iso, s in blk["countries"].items():
            vals = [s.get(str(y)) for y in years]
            if any(v is not None for v in vals):
                rows[iso] = [None if v is None else m2(v) for v in vals]
        out[slug] = rows
        if key == "oda":
            extra[slug] = [m2(sum(s.get(str(y), 0) for s in blk["regional"].values())) for y in years]
    return out, extra


def aid_block(packs):
    out = {}
    for slug in LENDERS:
        p = packs[slug]
        if p.get("crs"):
            c = p["crs"]
            out[slug] = {"src": "OECD CRS commitments", "from": c["from"], "to": c["to"], "n": c["n"], "usd": m2(c["usd"]),
                         "unit": "current USD",
                         "countries": {iso: {"n": v["n"], "usd": m2(v["usd"])} for iso, v in c["countries"].items()},
                         "regional": {"n": c["regional"]["n"], "usd": m2(c["regional"]["usd"])}}
        elif p.get("aid"):
            a = p["aid"]
            out[slug] = {"src": "AidData commitments, infrastructure projects only", "from": a["from"], "to": a["to"],
                         "n": a["n"], "usd": m2(a["usd"]), "unit": "constant 2021 USD",
                         "countries": {iso: {"n": v["n"], "usd": m2(v["usd"]), "loans": m2(v.get("loans", 0))}
                                       for iso, v in a["countries"].items()},
                         "regional": {"n": 0, "usd": 0}}
        else:
            out[slug] = None
    return out


def sectors_block(packs):
    groups = [[k, label] for k, label, _ in CRS_GROUPS]
    out = {}
    for slug in LENDERS:
        p = packs[slug]
        if p.get("crs"):
            c = p["crs"]
            usd, n = {}, {}
            if c.get("groups"):   # a pack fetched after the groups were added: complete
                for k, v in c["groups"].items():
                    usd[k] = usd.get(k, 0) + v["usd"]
                    n[k] = n.get(k, 0) + v["n"]
                rest_usd = rest_n = 0.0
                cover = 100.0
            else:                 # the fourteen largest purposes, grouped; the rest as one column
                for s in c["sectors"]:
                    k = crs_group(s["code"])
                    usd[k] = usd.get(k, 0) + s["usd"]
                    n[k] = n.get(k, 0) + s["n"]
                rest_usd = max(c["usd"] - sum(usd.values()), 0)
                rest_n = max(c["n"] - sum(n.values()), 0)
                cover = 100 * sum(usd.values()) / c["usd"] if c["usd"] else 0
            out[slug] = {"src": "OECD CRS", "from": c["from"], "to": c["to"], "cover": round(cover, 1),
                         "usd": {k: m2(v) for k, v in usd.items()}, "n": n,
                         "rest_usd": m2(rest_usd), "rest_n": rest_n, "total_usd": m2(c["usd"]), "total_n": c["n"]}
        elif p.get("aid"):
            a = p["aid"]
            usd, n = {}, {}
            for s in a["sectors"]:
                k = AIDDATA_GROUP.get(s["sector"], "other")
                usd[k] = usd.get(k, 0) + s["usd"]
                n[k] = n.get(k, 0) + s["n"]
            out[slug] = {"src": "AidData, infrastructure projects only", "from": a["from"], "to": a["to"], "cover": 100.0,
                         "usd": {k: m2(v) for k, v in usd.items()}, "n": n, "rest_usd": 0, "rest_n": 0,
                         "total_usd": m2(a["usd"]), "total_n": a["n"]}
        else:
            out[slug] = None
    return {"groups": groups, "by": out}


def instruments_block(packs):
    out = {}
    for slug in LENDERS:
        p = packs[slug]
        if p.get("crs"):
            c = p["crs"]
            if c.get("measures_usd"):
                mu = c["measures_usd"]
                grant, loan = mu.get("ODA Grants", 0), mu.get("ODA Loans", 0)
                total = sum(mu.values())
                out[slug] = {"basis": "usd", "grant": m2(grant), "loan": m2(loan), "other": m2(total - grant - loan), "total": m2(total)}
            else:
                ms = dict(c["measures"])
                grant, loan = ms.get("ODA Grants", 0), ms.get("ODA Loans", 0)
                total = c["n"]
                out[slug] = {"basis": "activities", "grant": grant, "loan": loan, "other": total - grant - loan, "total": total}
        elif p.get("aid"):
            a = p["aid"]
            out[slug] = {"basis": "usd", "grant": m2(a["grants_usd"]), "loan": m2(a["loans_usd"]),
                         "other": m2(a["usd"] - a["grants_usd"] - a["loans_usd"]), "total": m2(a["usd"])}
        else:
            out[slug] = None
    return out


def hard_block(packs):
    out = {}
    for slug in LENDERS:
        p = packs[slug]
        if p.get("crs"):
            c = p["crs"]
            out[slug] = {"n": c["hard"]["n"], "usd": m2(c["hard"]["usd"]),
                         "pct": round(100 * c["hard"]["usd"] / c["usd"], 1) if c["usd"] else 0,
                         "pct_n": round(100 * c["hard"]["n"] / c["n"], 1) if c["n"] else 0}
        elif p.get("aid"):
            out[slug] = {"n": p["aid"]["n"], "usd": m2(p["aid"]["usd"]), "pct": None, "pct_n": None,
                         "note": "by construction: AidData's dataset holds infrastructure projects only"}
        else:
            out[slug] = None
    return out


def channels_block(packs):
    kinds = [list(k) for k in CHANNEL_KINDS]
    out = {}
    for slug in LENDERS:
        c = packs[slug].get("crs")
        if not c:
            out[slug] = None
            continue
        by = {}
        for name, n in c["channels"]:
            k = channel_kind(name)
            by[k] = by.get(k, 0) + n
        out[slug] = {"n": by, "rest": max(c["n"] - sum(by.values()), 0), "total": c["n"],
                     "named": [[name or "(not stated)", n] for name, n in c["channels"]]}
    return {"kinds": kinds, "by": out}


def payload(packs, debt):
    by_slug = {d["slug"]: d for d in DONORS}
    debt_years, debt_rows, debt_total = debt_block(debt)
    oda_years = list(range(2010, max(p["oda"]["to"] for p in packs.values() if p.get("oda")) + 1))
    fdi_years = list(range(min(p["fdi"]["from"] for p in packs.values() if p.get("fdi")),
                           max(p["fdi"]["to"] for p in packs.values() if p.get("fdi")) + 1))
    oda, oda_reg = series_block(packs, "oda", oda_years)
    fdi, _ = series_block(packs, "fdi", fdi_years)
    countries = {}
    for iso, name in NAME.items():
        lon, lat = centre(iso)
        x, y = px(lon, lat)
        countries[iso] = {"n": name, "r": REGION_OF[iso], "x": x, "y": y}
    return {
        "built": fmt_date(today()),
        "lenders": [{"slug": s, "name": by_slug[s]["name"], "badge": by_slug[s]["badge"],
                     "url": site_url(s + "/"), "fetched": packs[s]["fetched"]} for s in LENDERS],
        "regions": [[rid, name] for rid, name, _ in REGIONS],
        "countries": countries,
        "years": {"debt": debt_years, "oda": oda_years, "fdi": fdi_years},
        "debt": debt_rows, "debt_total": debt_total,
        "debt_meta": {"updated": debt.get("updated"), "missing": debt.get("missing", [])},
        "oda": oda, "oda_regional": oda_reg, "fdi": fdi,
        "aid": aid_block(packs),
        "sectors": sectors_block(packs),
        "instruments": instruments_block(packs),
        "hard": hard_block(packs),
        "channels": channels_block(packs),
    }


# -------------------------------------------------------------------- facts

def facts(pl):
    """The Africa-wide figures the prose and the summary table state."""
    L = {l["slug"]: l for l in pl["lenders"]}
    yi = len(pl["years"]["debt"]) - 1
    f = {}
    lead = {s: 0 for s in LENDERS}
    for iso in pl["countries"]:
        best, bv = None, 0
        for s in LENDERS:
            v = (pl["debt"][s].get(iso) or [0] * (yi + 1))[yi]
            if v > bv:
                best, bv = s, v
        if best:
            lead[best] += 1
    for s in LENDERS:
        d = pl["debt"][s]
        stock = sum(v[yi] for v in d.values())
        aid = pl["aid"][s]
        row = {"name": L[s]["name"], "debt": stock, "debt_n": sum(1 for v in d.values() if v[yi] > 0), "lead": lead[s]}
        if aid:
            cs = sorted(aid["countries"].items(), key=lambda kv: -kv[1]["usd"])
            in_c = sum(v["usd"] for _, v in cs)
            row.update({"aid": aid["usd"], "aid_from": aid["from"], "aid_to": aid["to"], "aid_n": len(cs),
                        "aid_top": cs[0][0] if cs else None,
                        "aid_top_pct": 100 * cs[0][1]["usd"] / in_c if cs and in_c else 0,
                        "aid_top3_pct": 100 * sum(v["usd"] for _, v in cs[:3]) / in_c if in_c else 0,
                        "aid_src": aid["src"]})
        ins = pl["instruments"][s]
        if ins and ins["total"]:
            row["grant_pct"] = 100 * ins["grant"] / ins["total"]
            row["loan_pct"] = 100 * ins["loan"] / ins["total"]
            row["basis"] = ins["basis"]
        hd = pl["hard"][s]
        if hd:
            row["hard_pct"] = hd["pct"]
        if s in pl["oda"]:
            oi = len(pl["years"]["oda"]) - 1
            row["oda"] = sum((v[oi] or 0) for v in pl["oda"][s].values()) + pl["oda_regional"][s][oi]
        if s in pl["fdi"]:
            fi = len(pl["years"]["fdi"]) - 1
            row["fdi"] = sum((v[fi] or 0) for v in pl["fdi"][s].values())
        sec = pl["sectors"]["by"][s]
        if sec and sec["usd"]:
            k = max(sec["usd"], key=sec["usd"].get)
            row["top_sector"] = dict((g, lbl) for g, lbl in pl["sectors"]["groups"])[k]
            row["top_sector_pct"] = 100 * sec["usd"][k] / sec["total_usd"] if sec["total_usd"] else 0
        f[s] = row
    return f


def bn(v, dp=1):
    return f"{v / 1000:,.{dp}f}"


def summary_table(pl, f):
    y_debt = pl["years"]["debt"][-1]
    y_oda = pl["years"]["oda"][-1]
    y_fdi = pl["years"]["fdi"][-1]
    rows = []
    for s in LENDERS:
        r = f[s]
        name = f'<a href="{esc(site_url(s + "/"))}">{esc(r["name"])}</a>'
        aid = (f'{bn(r["aid"])} <span class="dim">{r["aid_from"]}–{r["aid_to"]}</span>' if "aid" in r else '<span class="dim">not reported</span>')
        top = (f'{esc(NAME[r["aid_top"]])} <span class="dim">{r["aid_top_pct"]:.0f}%</span>' if r.get("aid_top") else "–")
        hard = (f'{r["hard_pct"]:.0f}%' if r.get("hard_pct") is not None
                else ('<span class="dim">all, by construction</span>' if "aid" in r else "–"))
        grants = (f'{r["grant_pct"]:.0f}% <span class="dim">{"of money" if r["basis"] == "usd" else "of activities"}</span>'
                  if "grant_pct" in r else "–")
        rows.append([td(f'<span class="lk lk-{s}"></span>' + name, "name"), td(bn(r["debt"]), "num"), td(f'{r["debt_n"]}', "num"),
                     td(f'{r["lead"]}', "num"), td(aid, "num"), td(f'{r.get("aid_n", "–")}', "num"), td(top),
                     td(hard, "num"), td(grants, "num"),
                     td(bn(r["oda"]) if "oda" in r else "–", "num"), td(bn(r["fdi"]) if "fdi" in r else "–", "num")])
    return table(f"The seven lenders, Africa-wide. Debt at the end of {y_debt}; aid commitments over each source's window; "
                 f"net ODA {y_oda}; FDI stock {y_fdi}. USD bn.",
                 ["Lender", f"#Owed to it, {y_debt}", "#Debtor states", "#Largest creditor in", "#Aid committed",
                  "#Recipient states", "Largest recipient", "#Builds things", "#Grants", f"#Net ODA {y_oda}",
                  f"#FDI stock {y_fdi}"], rows, cls="cmp")


def tokens(pl, f):
    y = pl["years"]["debt"][-1]
    top = max(LENDERS, key=lambda s: f[s]["debt"])
    others = sum(f[s]["debt"] for s in LENDERS if s != top)
    ratio = f[top]["debt"] / others if others else 0
    if ratio >= 1.05:
        vs = f"{ratio:.1f} times what the other six are owed together (USD {bn(others)} bn)"
    else:
        vs = f"against USD {bn(others)} bn for the other six together"
    crs = [s for s in LENDERS if f[s].get("aid_src", "").startswith("OECD")]
    aid_top = max(crs, key=lambda s: f[s]["aid"])
    aid_least = min(crs, key=lambda s: f[s]["aid"])
    hard = [s for s in crs if f[s].get("hard_pct") is not None]
    hard_max, hard_min = max(hard, key=lambda s: f[s]["hard_pct"]), min(hard, key=lambda s: f[s]["hard_pct"])
    foc = [s for s in LENDERS if "aid_top3_pct" in f[s]]
    foc_max, foc_min = max(foc, key=lambda s: f[s]["aid_top3_pct"]), min(foc, key=lambda s: f[s]["aid_top3_pct"])
    leads = sorted(((f[s]["lead"], f[s]["name"]) for s in LENDERS if f[s]["lead"]), reverse=True)
    lead_sentence = ", ".join(f"{name} in {n}" for n, name in leads)
    cover = sorted(((pl["sectors"]["by"][s]["cover"], f[s]["name"]) for s in crs), reverse=True)
    cover_note = ("; ".join(f"{c:.0f}% of {('the ' if name in ('European Union', 'United States') else '')}{name}'s"
                            for c, name in cover))
    fetched = max([l["fetched"] for l in pl["lenders"]])
    ch = f["china"]
    return {
        "__DEBT_TO__": str(y), "__DEBT_FROM__": str(pl["years"]["debt"][0]),
        "__TOP_CREDITOR__": esc(f[top]["name"]), "__TOP_CREDITOR_BN__": bn(f[top]["debt"]),
        "__TOP_CREDITOR_N__": str(f[top]["debt_n"]), "__TOP_CREDITOR_VS__": esc(vs), "__TOP_CREDITOR_LEAD__": str(f[top]["lead"]),
        "__LEAD_SENTENCE__": esc(lead_sentence),
        "__AID_FROM__": str(f[aid_top]["aid_from"]), "__AID_TO__": str(f[aid_top]["aid_to"]),
        "__AID_TOP__": esc(f[aid_top]["name"]), "__AID_TOP_BN__": bn(f[aid_top]["aid"]),
        "__AID_TOP_N__": str(f[aid_top]["aid_n"]), "__AID_TOP_GRANT__": f"{f[aid_top]['grant_pct']:.0f}",
        "__AID_LEAST__": esc(f[aid_least]["name"]), "__AID_LEAST_BN__": bn(f[aid_least]["aid"], 2),
        "__AID_LEAST_TOP__": esc(NAME[f[aid_least]["aid_top"]]), "__AID_LEAST_TOP_PCT__": f"{f[aid_least]['aid_top_pct']:.0f}",
        "__HARD_MAX__": esc(f[hard_max]["name"]), "__HARD_MAX_PCT__": f"{f[hard_max]['hard_pct']:.0f}",
        "__HARD_MIN__": esc(f[hard_min]["name"]), "__HARD_MIN_PCT__": f"{f[hard_min]['hard_pct']:.0f}",
        "__FOCUS_MAX__": esc(f[foc_max]["name"]), "__FOCUS_MAX_PCT__": f"{f[foc_max]['aid_top3_pct']:.0f}",
        "__FOCUS_MAX_TOP__": esc(NAME[f[foc_max]["aid_top"]]),
        "__FOCUS_MIN__": esc(f[foc_min]["name"]), "__FOCUS_MIN_PCT__": f"{f[foc_min]['aid_top3_pct']:.0f}",
        "__CHINA_AID_BN__": bn(ch["aid"], 0), "__CHINA_FROM__": str(ch["aid_from"]), "__CHINA_TO__": str(ch["aid_to"]),
        "__CHINA_LOAN_PCT__": f"{ch['loan_pct']:.0f}", "__CHINA_AID_N__": str(ch["aid_n"]),
        "__CHINA_DEBT_BN__": bn(f["china"]["debt"]), "__CHINA_TOP_SECTOR__": esc(ch.get("top_sector", "–")),
        "__COVER_NOTE__": cover_note,
        "__N_CRS__": str(len(crs)), "__ODA_TO__": str(pl["years"]["oda"][-1]), "__ODA_FROM__": str(pl["years"]["oda"][0]),
        "__FDI_TO__": str(pl["years"]["fdi"][-1]), "__FDI_FROM__": str(pl["years"]["fdi"][0]),
        "__IDS_UPDATED__": fmt_date(pl["debt_meta"]["updated"]), "__FETCHED__": fmt_date(fetched),
        "__MISSING__": esc(", ".join(pl["debt_meta"]["missing"])),
        "__TABLE__": summary_table(pl, f),
        "__TITLE__": esc(TITLE), "__MAP_W__": f"{MAP_W:.0f}", "__MAP_H__": f"{MAP_H:.0f}",
        "__DATA_URL__": site_url("data/compare.json"), "__DATA_FILE__": "compare.json",
        "__BUILT__": fmt_date(today()),
    }


def jsonld(path):
    page = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": site_url(path), "url": site_url(path), "name": TITLE,
         "description": DESCRIPTION, "inLanguage": "en",
         "isPartOf": {"@type": "WebSite", "@id": site_url("#website"), "name": SITE_NAME, "url": SITE_URL},
         "author": {"@type": "Person", "name": AUTHOR_NAME, "url": WEB_URL, "sameAs": [AUTHOR_URL]},
         "about": [{"@type": "Country", "name": d["name"]} for d in DONORS],
         "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": [
             {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": SITE_URL},
             {"@type": "ListItem", "position": 2, "name": TITLE, "item": site_url(path)}]}},
        {"@type": "Dataset", "name": "Seven lenders to Africa compared: debt, aid, ODA and FDI by country",
         "description": DESCRIPTION, "creator": {"@type": "Person", "name": AUTHOR_NAME, "url": WEB_URL},
         "isBasedOn": ["https://data.worldbank.org/products/ids",
                       "https://data-explorer.oecd.org/", "https://www.aiddata.org/data/aiddatas-global-chinese-development-finance-dataset-version-3-0"],
         "distribution": {"@type": "DataDownload", "encodingFormat": "application/json",
                          "contentUrl": site_url("data/compare.json")}}]}
    return ('<script type="application/ld+json">'
            + json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n")


# The comparison is the last entry of the top bar's Lenders menu
# (shared.donor_nav); brand_assets(page, donor="compare") marks it current.


def build():
    packs, debt = load()
    pl = payload(packs, debt)
    f = facts(pl)
    toks = tokens(pl, f)
    page = FRAME.read_text().replace("<!--__BODY__-->", FRAG.read_text(), 1)
    for k, v in toks.items():
        page = page.replace(k, v)
    page = page.replace("<!--__LAND_DEFS__-->", land_defs(), 1)
    page = page.replace("/*__CMP__*/{}", json.dumps(pl, ensure_ascii=False, separators=(",", ":")), 1)
    page = page.replace("/*__PAYLOAD__*/", "{}", 1)
    page = brand_assets(page, donor="compare")
    left = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]*__", page)))
    if left:
        sys.exit(f"compare: unfilled tokens {', '.join(left)}")
    path = f"{SLUG}/index.html"
    doc = wrap_document(page, title=TITLE, description=DESCRIPTION, path=path, kind="profile",
                        extra_head=jsonld(path))
    (DOCS / SLUG).mkdir(parents=True, exist_ok=True)
    (DOCS / SLUG / "index.html").write_text(doc)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    (DOCS / "data" / "compare.json").write_text(json.dumps(pl, ensure_ascii=False, separators=(",", ":")))
    print(f"→ docs/{path}  {len(doc.encode()) / 1024:.0f} KB  (+ docs/data/compare.json)")
    for s in LENDERS:
        r = f[s]
        print(f"   {r['name']:16s} debt {bn(r['debt']):>7} bn / {r['debt_n']:2d} states, leads {r['lead']:2d}"
              + (f" · aid {bn(r['aid']):>7} bn {r['aid_from']}–{r['aid_to']} / {r['aid_n']} states, top {NAME[r['aid_top']]} {r['aid_top_pct']:.0f}%"
                 if 'aid' in r else " · no aid data")
              + (f" · builds {r['hard_pct']:.0f}%" if r.get('hard_pct') is not None else "")
              + (f" · grants {r['grant_pct']:.0f}% ({r['basis']})" if 'grant_pct' in r else ""))


if __name__ == "__main__":
    build()
