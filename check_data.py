#!/usr/bin/env python3
"""
Gate before a build: refuse a data snapshot that looks broken.

The fetcher tolerates partial failure by design — an Overpass mirror that
refuses one latitude band still yields a file, just a smaller one. Deploying
that would silently empty part of the map. So before building, compare each
layer against the last committed snapshot (`git show HEAD:data/meta.json`) and
against an absolute floor, and check that the geometry sits in Africa.

Exit 0 when the snapshot is sane, 1 with a list of reasons otherwise.
"""

import json
import pathlib
import subprocess
import sys

from region import REGION

ROOT = pathlib.Path(__file__).parent
DATA = REGION.data_dir

# file stem -> (meta key, minimum plausible feature count), for Africa; a
# smaller region's floors are scaled down (Southeast Asia has eleven
# countries to Africa's 54)
LAYERS = {
    "gem_power_assets": ("assets", 1000),
    f"iati_{REGION.bank['publisher']}_finance": ("finance", 300),
    "iati_worldbank_finance": ("finance_wb", 500),
    "iati_afd_finance": ("finance_afd", 250),
    "iati_bmz_finance": ("finance_bmz", 1000),
    "osm_construction": ("ground", 500),
    "gem_oil_gas_pipelines": ("pipelines", 150),
    "telegeography_cables": ("cables", 40),
    "aiddata_china_finance": ("china", 1000),
    "iati_eu_finance": ("eu", 800),
    "piano_mattei": ("mattei", 50),
}
LAYERS = {k: v for k, v in LAYERS.items() if v[0] in REGION.layers or v[0] == "finance_wb"
          or (v[0] == "finance_afd" and getattr(REGION, "afd_files", None))
          or (v[0] == "finance_bmz" and getattr(REGION, "bmz_files", None))}
FLOOR_SCALE = 1.0 if REGION.key == "africa" else 0.25
MAX_DROP = 0.20          # refuse if a layer lost more than a fifth of its records
WINDOW = REGION.data_window   # lon0, lat0, lon1, lat1


def committed_meta():
    try:
        out = subprocess.run(["git", "show", f"HEAD:{DATA.relative_to(ROOT)}/meta.json"],
                             capture_output=True, text=True, check=True, cwd=ROOT)
        return json.loads(out.stdout)
    except Exception:  # noqa: BLE001 — no git, no commit yet: compare to nothing
        return {}


def points(geom):
    """Every vertex of a geometry, whatever its nesting."""
    c = geom.get("coordinates")
    if not isinstance(c, list):
        return
    stack = [c]
    while stack:
        x = stack.pop()
        if x and isinstance(x[0], list):
            stack.extend(x)
        elif isinstance(x, list) and len(x) >= 2:
            yield x


def in_window(p):
    return WINDOW[0] <= p[0] <= WINDOW[2] and WINDOW[1] <= p[1] <= WINDOW[3]


def inside(geom):
    """A point must sit in the region's window. A line must touch it: a cable
    that lands in Mombasa and Mumbai, or a pipeline into Spain, is African
    without every vertex being so."""
    geom = geom or {}
    if geom.get("type") == "Point":
        p = geom.get("coordinates")
        return isinstance(p, list) and len(p) >= 2 and in_window(p)
    return any(in_window(p) for p in points(geom))


def main():
    prev = committed_meta()
    problems = []
    for stem, (key, floor) in LAYERS.items():
        floor = int(floor * FLOOR_SCALE)
        path = DATA / f"{stem}.geojson"
        if not path.exists():
            problems.append(f"{stem}: file missing")
            continue
        feats = json.loads(path.read_text())["features"]
        n = len(feats)
        outside = sum(1 for f in feats if not inside(f.get("geometry")))
        before = (prev.get(key) or {}).get("records")
        line = f"  {stem:22s} {n:>7,} features"
        if before:
            line += f"  (committed snapshot: {before:,})"
        print(line)
        if n < floor:
            problems.append(f"{stem}: only {n:,} features, below the floor of {floor:,}")
        if before and n < (1 - MAX_DROP) * before:
            problems.append(f"{stem}: {n:,} features, down from {before:,} — more than "
                            f"{int(MAX_DROP * 100)}% lost; a source or mirror probably failed")
        if n and outside > 0.01 * n:
            problems.append(f"{stem}: {outside:,} features outside the {REGION.name} window")
        null_island = sum(1 for f in feats if (f.get("geometry") or {}).get("type") == "Point"
                          and (f["geometry"].get("coordinates") or [None])[:2] == [0.0, 0.0])
        if null_island:      # inside the window, but a publisher's "no location" placeholder
            problems.append(f"{stem}: {null_island:,} point(s) at 0 0 (Null Island)")
    if problems:
        print("\nREFUSING to build from this snapshot:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("data snapshot looks sane")


if __name__ == "__main__":
    main()
