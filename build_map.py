#!/usr/bin/env python3
"""
Compile the three ingested layers plus the 1:10m basemap into the map page.

Reads   data/*.geojson  +  data/africa_basemap_10m.json  (+ africa_basemap.json
        for the fast country lookup)
Writes  map.html            payload inlined — for the Claude artifact, whose
                            sandbox blocks fetch() and any tile server
        docs/index.html     the same page as a complete HTML document that
                            loads docs/data/map.json at runtime — for GitHub Pages
        docs/data/          the compiled payload, the raw layers and meta.json,
                            so the site also publishes its data

The whole map — coastlines, rivers, cities, every project record and every
traced construction way — is one column-wise JSON payload either way.
"""

import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "data"
TEMPLATE = ROOT / "map.template.html"
OUT = ROOT / "map.html"

# Shared with build_dashboard.py so the two pages quote the same figure.
from build_dashboard import (  # noqa: E402
    NAME_TO_ISO, ISO_TO_NAME, DAC_SECTOR, SDR_USD,
    build_lookup, locate, load,
)
from fetch_basemap import dp  # noqa: E402
from shared import DOCS, brand_assets, load_meta, payload_meta, wrap_document  # noqa: E402


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


def build_finance():
    """One record per AfDB activity; every exact location kept for the detail
    view, the best one used as the marker."""
    best = {}
    for f in load("iati_afdb_finance.geojson"):
        p = f["properties"]
        pid = p.get("iati_id")
        if not pid:
            continue
        lon, lat = f["geometry"]["coordinates"]
        exact = p.get("geo_precision") == "1"
        rec = best.setdefault(pid, {"p": p, "pt": None, "rank": 9, "locs": []})
        rank = 0 if exact else 1
        if rank < rec["rank"]:
            rec["rank"], rec["pt"], rec["p"] = rank, (lon, lat), p
        if exact:
            rec["locs"].append([r(lon), r(lat), (p.get("location_name") or "")[:40]])
    rows = []
    for pid, rec in best.items():
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
        locs = rec["locs"]
        if len(locs) <= 1:
            locs = None
        else:
            locs = locs[:16]
        rows.append([
            (p.get("name") or "").strip()[:100], p.get("country") or "",
            r(lon), r(lat), p.get("dash_status"), sector or "other",
            round(com * SDR_USD / 1e6, 2) if com else None,
            round(dis * SDR_USD / 1e6, 2) if dis else None,
            1 if rec["rank"] == 0 else 0, (p.get("location_name") or "")[:40] or None,
            pid, codes[0] if codes else None, locs,
        ])
    return {"cols": ["name", "iso", "lon", "lat", "status", "sector", "usd_m",
                     "dis_m", "exact", "place", "iid", "dac", "locs"],
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
        mid = geoms[0][len(geoms[0]) // 2]
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
    base110 = json.loads((DATA / "africa_basemap.json").read_text())
    idx = build_lookup(base110["countries"])
    bm_path = DATA / "africa_basemap_10m.json"
    if not bm_path.exists():
        sys.exit("missing data/africa_basemap_10m.json — run fetch_basemap.py first")
    basemap = json.loads(bm_path.read_text())

    print("assets  …")
    assets = build_assets()
    print(f"   {len(assets['rows']):,} power units")
    print("finance …")
    finance = build_finance()
    multi = sum(1 for x in finance["rows"] if x[-1])
    print(f"   {len(finance['rows']):,} projects ({multi:,} with several exact sites)")
    print("ground  …")
    ground = build_ground(idx)
    located = sum(1 for g in ground["rows"] if g[1])
    print(f"   {len(ground['rows']):,} works ({located:,} located to a country)")

    names = {}
    for c in basemap["countries"]:
        if c["af"] and c["iso"]:
            names[c["iso"]] = c["n"]
    names.update({"CI": "Côte d'Ivoire", "CV": "Cabo Verde", "CD": "DR Congo",
                  "CG": "Republic of the Congo", "-99": "Somaliland",
                  "EH": "Western Sahara", "TZ": "Tanzania", "SZ": "Eswatini",
                  "ST": "São Tomé and Príncipe", "GM": "The Gambia"})
    for iso, n in ISO_TO_NAME.items():
        names.setdefault(iso, n)

    payload = {
        "meta": payload_meta(load_meta()),
        "names": names,
        "basemap": basemap,
        "assets": assets,
        "finance": finance,
        "ground": ground,
    }
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    html = brand_assets(TEMPLATE.read_text())
    marker = "<script>\nconst DATA = /*__PAYLOAD__*/;"
    if marker not in html:
        sys.exit("template missing the payload marker")

    # 1. Artifact build: payload inlined, classic script.
    OUT.write_text(html.replace("/*__PAYLOAD__*/", blob))
    kb = OUT.stat().st_size / 1024
    print(f"\npayload {len(blob.encode()) / 1024:.0f} KB → {OUT.name} {kb:.0f} KB")
    for k in ("basemap", "assets", "finance", "ground"):
        print(f"   {k:8s} {len(json.dumps(payload[k], separators=(',', ':'), ensure_ascii=False).encode()) / 1024:6.0f} KB")

    # 2. GitHub Pages build: complete document, payload fetched at runtime by a
    #    module script (top-level await), with a loading state until it lands.
    n_records = len(assets["rows"]) + len(finance["rows"]) + len(ground["rows"])
    loader = f'''<div class="loading" id="loading" role="status">
  <div class="lbox"><b>Africa Infrastructure Map</b>
  <span>Loading the basemap and {n_records:,} records, about {len(blob.encode()) / 1024 / 1024:.0f} MB…</span><i></i></div>
</div>
<script>
async function loadPayload(){{
  const box = document.getElementById("loading");
  try{{
    const res = await fetch("data/map.json");
    if(!res.ok) throw new Error(res.status + " " + res.statusText);
    const data = await res.json();
    box.remove();
    return data;
  }}catch(e){{
    box.classList.add("err");
    box.querySelector("span").textContent = "The map data could not be loaded (" + e.message + "). Reload to try again.";
    throw e;
  }}
}}
</script>
<div class="app">'''
    pages = html.replace('<div class="app">', loader, 1)
    pages = pages.replace(marker, '<script type="module">\nconst DATA = await loadPayload();', 1)
    DOCS.mkdir(exist_ok=True)
    (DOCS / "data").mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(wrap_document(
        pages, title="Africa Infrastructure Map", path="",
        description="Interactive map of announced, approved and ongoing infrastructure across Africa: "
                    "power assets, AfDB-financed projects and construction works traced in OpenStreetMap."))
    (DOCS / "data" / "map.json").write_text(blob)
    for f in sorted(DATA.glob("*.geojson")) + [DATA / "meta.json", DATA / "africa_basemap_10m.json"]:
        shutil.copy(f, DOCS / "data" / f.name)
    (DOCS / ".nojekyll").write_text("")
    total = sum(p.stat().st_size for p in DOCS.rglob("*") if p.is_file()) / 1024 / 1024
    print(f"→ docs/  index.html + dashboard.html + data/ ({total:.1f} MB for GitHub Pages)")


if __name__ == "__main__":
    main()
