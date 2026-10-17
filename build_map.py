#!/usr/bin/env python3
"""
Compile the eight ingested layers plus the 1:10m basemap into the map page.
The record builders for pipelines, cables, Chinese and EU finance and the Piano Mattei live in
build_dashboard.py, so both pages compile the same rows; only the geometry
simplification differs.

Reads   data/*.geojson  +  data/africa_basemap_10m.json  (+ africa_basemap.json
        for the fast country lookup); with AIW_REGION=sea, data/sea/ and the
        Southeast Asia basemaps, written under docs/se-asia/ (region.py)
Writes  map.html            payload inlined — for the Claude artifact, whose
                            sandbox blocks fetch() and any tile server
        docs/index.html     the same page as a complete HTML document that
                            loads docs/data/map.json at runtime — for GitHub Pages
        docs/data/          the compiled payload, the raw layers and meta.json,
                            so the site also publishes its data

The whole map — coastlines, rivers, cities, every project record, every
traced construction way, pipeline route and submarine cable — is one
column-wise JSON payload either way.
"""

import hashlib
import json
import pathlib
import re
import shutil
import sys

from region import REGION  # noqa: E402

ROOT = pathlib.Path(__file__).parent
DATA = REGION.data_dir
TEMPLATE = ROOT / "map.template.html"
OUT = ROOT / "map.html"

# Shared with build_dashboard.py so the two pages quote the same figure.
from build_dashboard import (  # noqa: E402
    NAME_TO_ISO, ISO_TO_NAME, DAC_SECTOR, SDR_USD,
    build_lookup, locate, load, build_pipelines, build_cables, build_china, build_eu, eu_summary,
    build_mattei, mattei_summary,
)
from fetch_basemap import dp  # noqa: E402
from shared import (  # noqa: E402
    BANK, DOCS, LOCAL_NOTE, LOCAL_USD, SITE_NAME, SITE_WORDMARK, brand_assets, china_span, inline_vendor, load_meta, payload_meta,
    site_facts,
    wrap_document, write_site_index,
)


def r(v, d=4):
    return round(v, d)


def simplify(coords, tol=0.0003):
    pts = dp(coords, tol)
    out = []
    for x, y in pts:
        q = [r(x), r(y)]
        if not out or out[-1] != q:
            out.append(q)
    if len(out) < 2:
        # a stub shorter than the 4-decimal rounding (~11 m): keep both ends so
        # the record survives — canvas draws it as a dot with round line caps
        out = [[r(coords[0][0]), r(coords[0][1])], [r(coords[-1][0]), r(coords[-1][1])]]
    return out


# ------------------------------------------------------------------ layers

def build_assets():
    rows = []
    for f in load("gem_power_assets.geojson"):
        p = f["properties"]
        iso = NAME_TO_ISO.get((p.get("country") or "").strip())
        if not iso:
            continue
        lon, lat = f["geometry"]["coordinates"]
        try:
            cap = round(float(p["capacity_mw"]), 1) if p.get("capacity_mw") else None
        except (TypeError, ValueError):
            cap = None
        yr = None
        if p.get("start_year"):
            m = re.match(r"(\d{4})", str(p["start_year"]))
            yr = int(m.group(1)) if m else None
        rows.append([
            (p.get("name") or "").strip()[:90], iso, r(lon), r(lat),
            p.get("dash_status"), (p.get("tech") or "").strip()[:26] or None,
            cap, yr, p.get("project_id") or None, p.get("url") or None,
            (p.get("owner") or "").strip()[:80] or None,
            (p.get("unit") or "").strip()[:40] or None,
            (p.get("subnational") or "").strip()[:40] or None,
            1 if p.get("geo_precision") == "exact" else 0,
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "tech", "mw", "yr",
                     "pid", "url", "owner", "unit", "sub", "exact"],
            "rows": rows}


# The finance layer's two lenders: file, short lender code as the payload
# carries it, and how their amounts reach US dollars. AfDB reports in XDR
# (IMF SDR); ADB and the World Bank in USD.
FINANCE_FILES = [(f"iati_{REGION.bank['publisher']}_finance.geojson", BANK), ("iati_worldbank_finance.geojson", "WB")]
TO_USD = {"XDR": SDR_USD, "USD": 1.0, **LOCAL_USD}
# raw layers drawn on the map but not offered as downloads in docs/data
NOT_REDISTRIBUTED = {"telegeography_cables.geojson"}


def build_finance():
    """One record per activity per lender; every precise location kept for
    the detail view, the best one used as the marker.

    Precision rank per location: 0 = exact site (IATI exactness 1, AfDB);
    1 = a named place or site (World Bank location-class 2 or 4, which the
    Bank still marks exactness 2; an ADB location named after a province or
    a town rather than the country); 2 = a country or region centroid."""
    best = {}
    for fname, ln in FINANCE_FILES:
        if not (DATA / fname).exists():
            print(f"   ! {fname} missing, lender {ln} skipped")
            continue
        for f in load(fname):
            p = f["properties"]
            pid = p.get("iati_id")
            if not pid:
                continue
            lon, lat = f["geometry"]["coordinates"]
            if p.get("geo_precision") == "1":
                rank = 0
            elif p.get("location_class") in ("2", "4") or p.get("location_named"):
                rank = 1
            else:
                rank = 2
            rec = best.setdefault((ln, pid), {"p": p, "pt": None, "rank": 9, "locs": [], "ln": ln})
            if rank < rec["rank"]:
                rec["rank"], rec["pt"], rec["p"] = rank, (lon, lat), p
            if rank <= 1:
                rec["locs"].append([r(lon), r(lat), (p.get("location_name") or "")[:40]])
    rows = []
    for (ln, pid), rec in best.items():
        p = rec["p"]
        lon, lat = rec["pt"]
        sector = None
        codes = p.get("dac_sectors") or []
        for code in codes:
            for pre, s in DAC_SECTOR:
                if code.startswith(pre):
                    sector = s
                    break
            if sector:
                break
        com, dis = p.get("commitment"), p.get("disbursed")
        pub, pub_dis = p.get("commitment_published"), p.get("disbursed_published")
        cur = p.get("currency") or (REGION.bank["currency"] if ln == BANK else "USD")
        rate = TO_USD.get(cur)
        cnote = p.get("counted_note")
        if cur in LOCAL_USD:      # a loan published in the borrower's currency
            cnote = "; ".join(x for x in (cnote, f"published in {cur}, converted at 1 {cur} = {LOCAL_USD[cur]:g} USD ({LOCAL_NOTE})") if x)
        locs = rec["locs"]
        if len(locs) <= 1:
            locs = None
        else:
            locs = locs[:16]
        rows.append([
            (p.get("name") or "").strip()[:100], p.get("country") or "",
            r(lon), r(lat), p.get("dash_status"), sector or "other",
            round(com * rate / 1e6, 2) if com and rate else None,
            round(dis * rate / 1e6, 2) if dis and rate else None,
            rec["rank"], (p.get("location_name") or "")[:40] or None,
            pid, codes[0] if codes else None, locs, ln, p.get("project_url") or None,
            # the lender's own figures where the counted ones differ, and why
            round(pub * rate / 1e6, 2) if pub and rate else None,
            round(pub_dis * rate / 1e6, 2) if pub_dis and rate else None, cnote,
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "sector", "usd_m",
                     "dis_m", "prec", "place", "iid", "dac", "locs", "ln", "purl", "pub_m", "pub_dis_m", "cnote"],
            "rows": rows}


def build_ground(idx):
    feats = load("osm_construction.geojson")
    groups, loose = {}, []
    for f in feats:
        p = f["properties"]
        g = f["geometry"]["coordinates"]
        if len(g) < 2:
            continue
        key = (p.get("name"), p.get("sector")) if p.get("name") else None
        if key:
            groups.setdefault(key, {"p": p, "parts": [], "ids": []})
            groups[key]["parts"].append(g)
            groups[key]["ids"].append(p.get("osm_id"))
        else:
            loose.append((p, [g], [p.get("osm_id")]))
    items = [(v["p"], v["parts"], v["ids"]) for v in groups.values()] + loose

    rows, skipped = [], 0
    for p, parts, ids in items:
        if not p.get("dash_status"):
            skipped += 1
            continue
        parts = sorted(parts, key=len, reverse=True)
        geoms = [simplify(part) for part in parts]
        geoms = [g for g in geoms if len(g) >= 2]
        if not geoms:
            continue
        # length in degrees, for sizing the list and picking a representative
        length_km = 0.0
        for g in geoms:
            for a, b in zip(g, g[1:]):
                dx = (b[0] - a[0]) * 111.32 * abs(__import__("math").cos(__import__("math").radians(a[1])))
                dy = (b[1] - a[1]) * 110.57
                length_km += (dx * dx + dy * dy) ** 0.5
        # the middle vertex of the longest raw part, as build_dashboard
        # takes it, so a coastal or border work lands in the same country on
        # both pages (a simplified line's middle can fall at sea)
        raw_mid = parts[0][len(parts[0]) // 2]
        mid = [r(raw_mid[0]), r(raw_mid[1])]
        iso, _ = locate(mid[0], mid[1], idx)
        rows.append([
            (p.get("name") or "").strip()[:90] or None, iso, mid[0], mid[1],
            p.get("dash_status"), p.get("sector"), p.get("eventual_class"),
            (p.get("operator") or "").strip()[:60] or None,
            (p.get("opening_date") or "").strip()[:20] or None,
            p.get("wikidata") or None,
            (ids[0] or "").replace("way/", "") or None, len(ids),
            round(length_km, 1), geoms,
        ])
    if skipped:
        print(f"   dropped {skipped} unnamed stub(s) with no resolved status")
    return {"cols": ["name", "iso", "lon", "lat", "status", "sector", "cls",
                     "operator", "opening", "wd", "oid", "ways", "km", "g"],
            "rows": rows}


# ------------------------------------------------------------------- build

def main():
    base110 = json.loads((DATA / REGION.basemap_110).read_text())
    idx = build_lookup(base110["countries"])
    bm_path = DATA / REGION.basemap_10m
    if not bm_path.exists():
        sys.exit(f"missing {bm_path} — run fetch_basemap.py first")
    basemap = json.loads(bm_path.read_text())

    print("assets  …")
    assets = build_assets()
    print(f"   {len(assets['rows']):,} power units")
    print("finance …")
    finance = build_finance()
    fc = finance["cols"]
    multi = sum(1 for x in finance["rows"] if x[fc.index("locs")])
    by_ln = {ln: sum(1 for x in finance["rows"] if x[fc.index("ln")] == ln) for ln in (BANK, "WB")}
    print(f"   {len(finance['rows']):,} projects ({by_ln[BANK]:,} {BANK}, {by_ln['WB']:,} World Bank; "
          f"{multi:,} with several precise sites)")
    print("ground  …")
    ground = build_ground(idx)
    located = sum(1 for g in ground["rows"] if g[1])
    print(f"   {len(ground['rows']):,} works ({located:,} located to a country)")
    print("pipes   …")
    pipelines = build_pipelines(idx, lambda part: [simplify(part, 0.001)])
    pkm = sum(x[pipelines["cols"].index("km")] or 0 for x in pipelines["rows"])
    print(f"   {len(pipelines['rows']):,} pipeline segments, {pkm:,.0f} km")
    print("cables  …")
    cables = build_cables(idx, lambda part: [simplify(part, 0.001)], rnd=r)
    nlp = sum(len(x[cables["cols"].index("lps")] or []) for x in cables["rows"])
    print(f"   {len(cables['rows']):,} submarine cables, {nlp:,} {REGION.adj} landing points")
    print("china   …")
    # footprints keep every ring (a hospital block is visible at the closest
    # zoom), thinned at ~150 m and to at most 400 vertices per record
    china = build_china(idx, lambda part: [simplify(part, 0.0015)], rnd=r, cap=400, min_extent=0)
    cc = china["cols"]
    cusd = sum(x[cc.index("usd_m")] or 0 for x in china["rows"]) / 1000
    cfp = sum(1 for x in china["rows"] if x[cc.index("g")])
    cprec = {k: sum(1 for x in china["rows"] if x[cc.index("prec")] == k) for k in range(4)}
    print(f"   {len(china['rows']):,} Chinese-financed projects, ${cusd:,.1f}bn ({china_span()[2]} USD); "
          f"{cfp:,} footprints; precise {cprec[0]:,}, ~5 km {cprec[1]:,}, admin {cprec[2]:,}, country {cprec[3]:,}")

    print("eu      …")
    eu = build_eu(idx, rnd=r)
    print(f"   {eu_summary(eu)}")

    mattei = None
    if "mattei" in REGION.layers:
        print("mattei  …")
        mattei = build_mattei(idx, rnd=r)
        print(f"   {mattei_summary(mattei)}")

    names = {}
    for c in basemap["countries"]:
        if c["af"] and c["iso"]:
            names[c["iso"]] = c["n"]
    # the region's display names (for Africa: Natural Earth's Somaliland and
    # Western Sahara labelled plainly, and the islands only submarine cables reach)
    names.update(REGION.display)
    for iso, n in ISO_TO_NAME.items():
        names.setdefault(iso, n)

    payload = {
        "meta": payload_meta(load_meta()),
        "names": names,
        "basemap": basemap,
        "assets": assets,
        "finance": finance,
        "ground": ground,
        "pipelines": pipelines,
        "cables": cables,
        "china": china,
        "eu": eu,
        "mattei": mattei,
    }
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    html = inline_vendor(brand_assets(TEMPLATE.read_text(), here="map"))
    marker = "<script>\nconst DATA = /*__PAYLOAD__*/;"
    if marker not in html:
        sys.exit("template missing the payload marker")

    # 1. Artifact build: payload inlined, classic script.
    OUT.write_text(html.replace("/*__PAYLOAD__*/", blob))
    kb = OUT.stat().st_size / 1024
    print(f"\npayload {len(blob.encode()) / 1024:.0f} KB → {OUT.name} {kb:.0f} KB")
    for k in ("basemap", "assets", "finance", "ground", "pipelines", "cables", "china", "eu", "mattei"):
        if payload.get(k) is not None:
            print(f"   {k:8s} {len(json.dumps(payload[k], separators=(',', ':'), ensure_ascii=False).encode()) / 1024:6.0f} KB")

    # 2. GitHub Pages build: complete document, payload fetched at runtime by a
    #    module script (top-level await), with a loading state until it lands.
    n_records = sum(len(x["rows"]) for x in (assets, finance, ground, pipelines, cables, china, eu, mattei) if x)
    # The data URL carries a digest of the payload. Pages and CDN caches keep
    # index.html and map.json for ten minutes each, independently; without
    # this a freshly deployed page can load the previous deploy's data and
    # draw a layer with zero records.
    digest = hashlib.sha1(blob.encode()).hexdigest()[:10]
    loader = f'''<div class="loading" id="loading" role="status">
  <div class="lbox"><b>{SITE_WORDMARK}</b>
  <span>Loading the basemap and {n_records:,} records, about {len(blob.encode()) / 1024 / 1024:.0f} MB…</span><i></i></div>
</div>
<script>
async function loadPayload(){{
  const box = document.getElementById("loading");
  try{{
    const res = await fetch("data/map.json?v={digest}");
    if(!res.ok) throw new Error(res.status + " " + res.statusText);
    const data = await res.json();
    box.remove();
    return data;
  }}catch(e){{
    box.classList.add("err");
    box.querySelector(".lbox > span").textContent = "The map data could not be loaded (" + e.message + "). Reload to try again.";
    throw e;
  }}
}}
</script>
<div class="app">'''
    pages = html.replace('<div class="app">', loader, 1)
    pages = pages.replace(marker, '<script type="module">\nconst DATA = await loadPayload();', 1)
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data").mkdir(exist_ok=True)
    facts = site_facts(assets, finance, ground, pipelines, cables, china, eu, mattei)
    (DOCS / "index.html").write_text(wrap_document(
        pages, title=SITE_NAME, path="", kind="map", facts=facts,
        description=f"Interactive open-data map of infrastructure across {REGION.name}: power plants and "
                    f"oil and gas pipelines (Global Energy Monitor), {REGION.bank['name']} "
                    f"and World Bank projects, Chinese-financed infrastructure {china_span()[0]}–{china_span()[1]} (AidData), "
                    "European Union finance (European Commission and EIB), "
                    + ("Italy's Piano Mattei projects, " if mattei is not None else "") +
                    "construction works traced in OpenStreetMap and submarine cables "
                    "(TeleGeography). Filter by country, status and sector."))
    write_site_index(facts)
    (DOCS / "data" / "map.json").write_text(blob)
    # every raw layer as a download, except TeleGeography's: its terms put
    # the map under CC BY-SA but keep the underlying data for subscribers
    for f in sorted(DATA.glob("*.geojson")) + [DATA / "meta.json", DATA / REGION.basemap_10m]:
        if f.name in NOT_REDISTRIBUTED:
            (DOCS / "data" / f.name).unlink(missing_ok=True)
            continue
        shutil.copy(f, DOCS / "data" / f.name)
    (DOCS / ".nojekyll").write_text("")
    total = sum(p.stat().st_size for p in DOCS.rglob("*") if p.is_file()) / 1024 / 1024
    print(f"→ {DOCS.relative_to(ROOT)}/  index.html + dashboard.html + sitemap.xml + llms.txt + data/ ({total:.1f} MB for GitHub Pages)")
    if not (DOCS / "social.png").exists():
        print("   ! docs/social.png missing — run build_social.py for the link-preview image")


if __name__ == "__main__":
    main()
