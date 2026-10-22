#!/usr/bin/env python3
"""
The twice-a-year update, as one command.

    python3 refresh.py             fetch every source, gate, rebuild docs/, cross-check the numbers
    python3 refresh.py --build     rebuild docs/ from the data already in data/
    python3 refresh.py --basemap   also rebuild the Natural Earth basemap
    python3 refresh.py --force     build even if check_data.py objects

    AIW_REGION=sea python3 refresh.py          the same for the Southeast Asia edition
                                               (data/sea/, docs/se-asia/; no lender profiles,
                                               debt, comparison or corridors, which are Africa's)

Afterwards, look at the result locally

    python3 -m http.server 8791 --directory docs

then commit and push; GitHub Pages redeploys main:/docs within a minute or two.

The fetch takes well over an hour (1 h 45 min in October 2026: 80 minutes for
the ten map sources, then 25 for debt and the lender profiles), most of it the
OpenStreetMap pass, which walks the continent in latitude bands to stay inside
Overpass's rate limits. If one
source fails, fix or retry that layer alone (`python3 fetch_sources.py osm`)
and rerun with --build.
"""

import pathlib
import subprocess
import sys

from region import REGION

ROOT = pathlib.Path(__file__).parent
BASEMAP = REGION.data_dir / REGION.basemap_10m
# the deep dives (lender profiles, debt, comparison, corridors) and the
# cross-check of the figures they state are the Africa edition's
AFRICA_ONLY = REGION.key != "africa"


def run(label, script):
    print(f"\n=== {label}", flush=True)   # flush: the children write to the same pipe
    return subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT).returncode


def main():
    args = set(sys.argv[1:])
    unknown = args - {"--build", "--basemap", "--force"}
    if unknown:
        sys.exit(f"unknown option(s): {' '.join(sorted(unknown))}\n{__doc__}")

    if "--build" not in args:
        if run("Fetch the map sources", "fetch_sources.py") != 0:
            sys.exit("\nfetch failed — nothing was rebuilt. Retry the failing layer alone, "
                     "then `python3 refresh.py --build`.")
        if not AFRICA_ONLY and run("Fetch the lender-profile data", "fetch_donors.py") != 0:
            print("\nfetch_donors.py failed — the profiles are rebuilt from the data already in data/donors/", flush=True)
        if not AFRICA_ONLY and run("Fetch debt by creditor (World Bank IDS)", "fetch_debt.py") != 0:
            print("\nfetch_debt.py failed — the debt section is rebuilt from data/debt.json", flush=True)

    if "--basemap" in args or not BASEMAP.exists():
        if run("Build the Natural Earth basemap", "fetch_basemap.py") != 0:
            sys.exit("\nbasemap build failed")
    else:
        print(f"\n=== Basemap: keeping {BASEMAP.relative_to(ROOT)} (pass --basemap to rebuild)", flush=True)

    if run("Sanity-check the data snapshot", "check_data.py") != 0:
        if "--force" in args:
            print("\n--force given: building anyway", flush=True)
        else:
            sys.exit("\ncheck_data.py refused this snapshot. Look at data/ and the message above; "
                     "rerun the failing layer, or `python3 refresh.py --build --force` to publish regardless.")

    # The link-preview image (docs/social.png) redraws the new records. It needs a
    # Chrome to rasterise; without one the committed PNG stays, which is fine. It
    # goes first: the pages embed a digest of the image in its URL, so the image
    # must be the one they ship with.
    if run("Build the link-preview image", "build_social.py") != 0:
        print("\nbuild_social.py failed — the previous docs/social.png stays", flush=True)
    scripts = ["build_dashboard.py", "build_map.py"]
    if not AFRICA_ONLY:
        scripts += ["build_donors.py", "build_debt.py", "build_compare.py", "build_corridors.py"]
    for script in scripts:
        if run(f"Build {script}", script) != 0:
            sys.exit(f"\n{script} failed")

    # Every number the pages state, checked against the data and against every
    # other place it is stated: the README, the hand-written proportions, the
    # profiles, the comparison and the debt page. A disagreement unbuilds
    # nothing, but the snapshot is not ready to publish.
    if not AFRICA_ONLY and run("Cross-check the numbers", "check_numbers.py") != 0:
        sys.exit("\ncheck_numbers.py found figures that disagree (listed above). The pages are built but not "
                 "ready to publish: fix each figure where it is written (README.md, donors/, sections/ or a "
                 "template), then `python3 refresh.py --build`.")

    print("""
=== Done. Next:

  python3 -m http.server 8791 --directory docs      # look at it: http://localhost:8791/
  git add -A && git commit -m "data refresh" && git push

GitHub Pages redeploys https://jacopoottaviani.com/africa-infra-watch/ from main:/docs.""")


if __name__ == "__main__":
    main()
