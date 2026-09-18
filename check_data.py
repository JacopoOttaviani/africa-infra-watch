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
    "osm_construction": ("ground", 500),
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


def first_point(geom):
    c = geom.get("coordinates")
    while isinstance(c, list) and c and isinstance(c[0], list):
        c = c[0]
    return c if isinstance(c, list) and len(c) >= 2 else None


def inside(geom):
    p = first_point(geom or {})
    return bool(p) and WINDOW[0] <= p[0] <= WINDOW[2] and WINDOW[1] <= p[1] <= WINDOW[3]


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
