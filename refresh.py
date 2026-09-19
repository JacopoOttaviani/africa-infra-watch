#!/usr/bin/env python3
"""
The twice-a-year update, as one command.

    python3 refresh.py             fetch all three sources, gate, rebuild docs/
    python3 refresh.py --build     rebuild docs/ from the data already in data/
    python3 refresh.py --basemap   also rebuild the Natural Earth basemap
    python3 refresh.py --force     build even if check_data.py objects

Afterwards, look at the result locally

    python3 -m http.server 8791 --directory docs

then commit and push; GitHub Pages redeploys main:/docs within a minute or two.

The fetch takes ~15 minutes, most of it the OpenStreetMap pass, which walks
the continent in latitude bands to stay inside Overpass's rate limits. If one
source fails, fix or retry that layer alone (`python3 fetch_sources.py osm`)
and rerun with --build.
"""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
BASEMAP = ROOT / "data" / "africa_basemap_10m.json"


def run(label, script):
    print(f"\n=== {label}", flush=True)   # flush: the children write to the same pipe
    return subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT).returncode


def main():
    args = set(sys.argv[1:])
    unknown = args - {"--build", "--basemap", "--force"}
    if unknown:
        sys.exit(f"unknown option(s): {' '.join(sorted(unknown))}\n{__doc__}")

    if "--build" not in args:
        if run("Fetch the three sources", "fetch_sources.py") != 0:
            sys.exit("\nfetch failed — nothing was rebuilt. Retry the failing layer alone, "
                     "then `python3 refresh.py --build`.")

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
    for script in ("build_dashboard.py", "build_map.py"):
        if run(f"Build {script}", script) != 0:
            sys.exit(f"\n{script} failed")

    print("""
=== Done. Next:

  python3 -m http.server 8791 --directory docs      # look at it: http://localhost:8791/
  git add -A && git commit -m "data refresh" && git push

GitHub Pages redeploys https://jacopoottaviani.com/africa-infra-watch/ from main:/docs.""")


if __name__ == "__main__":
    main()
