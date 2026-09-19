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

DATA = pathlib.Path(__file__).parent / "data"

# file stem -> (meta key, minimum plausible feature count)
LAYERS = {
    "gem_power_assets": ("assets", 1000),
    "iati_afdb_finance": ("finance", 300),
    "iati_worldbank_finance": ("finance_wb", 500),
    "osm_construction": ("ground", 500),
    "gem_oil_gas_pipelines": ("pipelines", 150),
    "telegeography_cables": ("cables", 40),
    "aiddata_china_finance": ("china", 1000),
}
MAX_DROP = 0.20          # refuse if a layer lost more than a fifth of its records
WINDOW = (-30, -45, 70, 45)   # lon0, lat0, lon1, lat1


def committed_meta():
    try:
        out = subprocess.run(["git", "show", "HEAD:data/meta.json"],
                             capture_output=True, text=True, check=True, cwd=DATA.parent)
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
    """A point must sit in the Africa window. A line must touch it: a cable
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
            problems.append(f"{stem}: {outside:,} features outside the Africa window")
    if problems:
        print("\nREFUSING to build from this snapshot:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("data snapshot looks sane")


if __name__ == "__main__":
    main()
