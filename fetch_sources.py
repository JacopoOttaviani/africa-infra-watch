#!/usr/bin/env python3
"""
Populate africa-infra-watch from the three verified sources.

Writes one normalised GeoJSON per layer into ./data/, all sharing a common
`dash_status` vocabulary so a single dashboard filter works across all three.

Every endpoint here was tested live on 2026-09-07. See the dataset evaluation
for the reasoning and the known gotchas.

Usage:
    python3 fetch_sources.py            # all three layers
    python3 fetch_sources.py gem osm    # only the named layers
"""

import csv
import io
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from shared import today, update_meta

DATA = pathlib.Path(__file__).parent / "data"
UA = {"User-Agent": "africa-infra-watch/0.1 (dataset evaluation)"}

# The 54 ISO-3166-1 alpha-2 codes. Used to clip OSM (a bounding box pulls in
# Turkey and Spain) and to filter World Bank results (region names are unstable).
AFRICA_ISO = [
    "DZ", "AO", "BJ", "BW", "BF", "BI", "CM", "CV", "CF", "TD", "KM", "CG",
    "CD", "DJ", "EG", "GQ", "ER", "SZ", "ET", "GA", "GM", "GH", "GN", "GW",
    "CI", "KE", "LS", "LR", "LY", "MG", "MW", "ML", "MR", "MU", "MA", "MZ",
    "NA", "NE", "NG", "RW", "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SD",
    "TZ", "TG", "TN", "UG", "ZM", "ZW",
]

AFRICA_NAMES = {
    "Algeria", "Angola", "Benin", "Botswana", "Burkina Faso", "Burundi",
    "Cameroon", "Cape Verde", "Cabo Verde", "Central African Republic", "Chad",
    "Comoros", "Congo", "Democratic Republic of Congo", "DR Congo", "Djibouti",
    "Egypt", "Equatorial Guinea", "Eritrea", "Eswatini", "Ethiopia", "Gabon",
    "Gambia", "Ghana", "Guinea", "Guinea-Bissau", "Ivory Coast", "Cote d'Ivoire",
    "Côte d'Ivoire", "Kenya", "Lesotho", "Liberia", "Libya", "Madagascar",
    "Malawi", "Mali", "Mauritania", "Mauritius", "Morocco", "Mozambique",
    "Namibia", "Niger", "Nigeria", "Rwanda", "Sao Tome and Principe", "Senegal",
    "Seychelles", "Sierra Leone", "Somalia", "South Africa", "South Sudan",
    "Sudan", "Tanzania", "Togo", "Tunisia", "Uganda", "Zambia", "Zimbabwe",
    "Western Sahara", "Republic of the Congo",
}

# Shared vocabulary. Keep these five values stable — the dashboard filters on them.
ANNOUNCED, APPROVED, BUILDING, OPERATING, STALLED = (
    "announced", "approved", "under_construction", "operating", "stalled")

GEM_STATUS = {
    "announced": ANNOUNCED,
    "pre-construction": APPROVED,
    "permitted": APPROVED,
    "construction": BUILDING,
    "operating": OPERATING,
    "cancelled": STALLED,
    "shelved": STALLED,
    "mothballed": STALLED,
    "retired": OPERATING,
}

IATI_STATUS = {
    "1": ANNOUNCED,     # pipeline / identification
    "2": BUILDING,      # implementation
    "3": OPERATING,     # finalisation
    "4": OPERATING,     # closed
    "5": STALLED,       # cancelled
    "6": STALLED,       # suspended
}


def get(url, timeout=180, data=None):
    req = urllib.request.Request(url, headers=UA, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def write_layer(name, features):
    DATA.mkdir(exist_ok=True)
    path = DATA / f"{name}.geojson"
    path.write_text(json.dumps(
        {"type": "FeatureCollection", "features": features}), encoding="utf-8")
    print(f"  -> {path.relative_to(path.parent.parent)}  "
          f"{len(features):,} features")
    return path


# ---------------------------------------------------------------- GEM (assets)

GEM_BUCKET = "https://publicgemdata.nyc3.cdn.digitaloceanspaces.com"


def gem_latest_csv():
    """Resolve the current release from the listable bucket.

    GEM's own map config still points at a deleted 2026-03 path, so never
    hardcode a release URL — discover it.
    """
    listing = get(
        f"{GEM_BUCKET}/?list-type=2&prefix=Current_maps/integrated-power/"
        "&max-keys=1000", timeout=90).decode("utf-8", "replace")
    keys = [k for k in re.findall(r"<Key>([^<]+)</Key>", listing)
            if k.endswith(".csv")]
    if not keys:
        raise RuntimeError("no integrated-power CSV found in GEM bucket")
    return f"{GEM_BUCKET}/{urllib.parse.quote(sorted(keys)[-1])}"


def fetch_gem():
    url = gem_latest_csv()
    release = urllib.parse.unquote(url.rsplit('/', 1)[-1]).rsplit('.', 1)[0]
    print(f"GEM  release: {release}")
    raw = get(url, timeout=600).decode("utf-8", "replace")

    feats = []
    for row in csv.DictReader(io.StringIO(raw)):
        if (row.get("country-area1") or "").strip() not in AFRICA_NAMES:
            continue
        try:
            lon, lat = float(row["Longitude"]), float(row["Latitude"])
        except (TypeError, ValueError, KeyError):
            continue
        status = (row.get("status") or "").strip().lower()
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "source": "GEM",
                "layer": "assets",
                "name": row.get("name") or row.get("unit-name"),
                "unit": row.get("unit-name"),
                "country": row.get("country-area1"),
                "subnational": row.get("subnational") or None,
                "sector": "energy",
                "tech": row.get("tech-type") or row.get("fuel"),
                "capacity_mw": row.get("capacity") or None,
                "start_year": row.get("start-year") or None,
                "owner": row.get("owner") or None,
                "raw_status": status,
                "dash_status": GEM_STATUS.get(status),
                "geo_precision": row.get("location-accuracy") or None,
                "project_id": row.get("project-id") or None,
                "url": row.get("url") or None,
            },
        })
    out = write_layer("gem_power_assets", feats)
    update_meta("assets", fetched=today(), fresh=None, release=release, records=len(feats))
    return out


# ------------------------------------------------------------- IATI (finance)

REGISTRY = "https://iatiregistry.org/api/3/action/package_search"
IATI_INFRA_DAC = ("210", "230", "140", "321", "322", "323", "331", "410", "220")


def fetch_iati(publisher="afdb", infra_only=True):
    """AfDB publishes 57 per-country files; every location carries a <point>.

    The IATI Datastore API (api.iatistandard.org) needs a subscription key and
    returns 401 without one, so go via the registry to the publisher's XML.
    """
    meta = json.loads(get(
        f"{REGISTRY}?q=organization:{publisher}&rows=200", timeout=90))
    urls = [r["url"] for p in meta["result"]["results"] for r in p["resources"]]
    print(f"IATI {publisher}: {len(urls)} datasets")

    feats = []
    for i, u in enumerate(urls, 1):
        try:
            xml = get(u, timeout=180)
        except Exception as e:                                # noqa: BLE001
            print(f"  ! skipped {u.rsplit('/', 1)[-1]}: {e}")
            continue
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            print(f"  ! unparseable {u.rsplit('/', 1)[-1]}: {e}")
            continue

        for act in root.iter("iati-activity"):
            sectors = [s.get("code") for s in act.iter("sector") if s.get("code")]
            if infra_only and not any(
                    c.startswith(IATI_INFRA_DAC) for c in sectors):
                continue

            st = act.find("activity-status")
            code = st.get("code") if st is not None else None
            title = act.find("title/narrative")
            ident = act.find("iati-identifier")
            country = act.find("recipient-country")

            # Money: use transactions, NOT <budget>. AfDB repeats the same
            # value in a <budget> element per quarter, so "first budget"
            # understates and "sum of budgets" is only accidentally right.
            # transaction-type 2 = outgoing commitment, 3 = disbursement.
            # Values carry no currency attribute — they inherit the
            # activity's default-currency, which for AfDB is XDR (IMF SDR).
            currency = act.get("default-currency")
            commitment = disbursed = 0.0
            for tx in act.iter("transaction"):
                tt = tx.find("transaction-type")
                v = tx.find("value")
                if tt is None or v is None or not v.text:
                    continue
                try:
                    amt = float(v.text)
                except ValueError:
                    continue
                if tt.get("code") == "2":
                    commitment += amt
                elif tt.get("code") == "3":
                    disbursed += amt
                currency = v.get("currency") or currency

            for loc in act.iter("location"):
                pos = loc.find("point/pos")
                if pos is None or not (pos.text or "").strip():
                    continue
                try:                       # IATI <pos> is "lat lon"
                    lat, lon = (float(x) for x in pos.text.split()[:2])
                except ValueError:
                    continue
                ex = loc.find("exactness")
                nm = loc.find("name/narrative")
                feats.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "source": publisher.upper(),
                        "layer": "finance",
                        "name": title.text if title is not None else None,
                        "location_name": nm.text if nm is not None else None,
                        "country": country.get("code") if country is not None else None,
                        "sector": "infrastructure",
                        "dac_sectors": sectors,
                        "raw_status": code,
                        "dash_status": IATI_STATUS.get(code),
                        # exactness 1 = exact; 2 = approximate (often a country
                        # centroid). Filter to "1" for a map that isn't pinned
                        # to the middle of each country.
                        "geo_precision": ex.get("code") if ex is not None else None,
                        "commitment": round(commitment, 2) or None,
                        "disbursed": round(disbursed, 2) or None,
                        "currency": currency,
                        "iati_id": ident.text if ident is not None else None,
                    },
                })
        if i % 15 == 0:
            print(f"  … {i}/{len(urls)} files, {len(feats):,} located so far")

    out = write_layer(f"iati_{publisher}_finance", feats)
    update_meta("finance", fetched=today(), fresh=None, datasets=len(urls), records=len(feats),
                activities=len({f["properties"]["iati_id"] for f in feats}))
    return out


# --------------------------------------------------------- OSM (ground truth)

# The main instance rate-limits hard (429, then refused connections) when you
# walk 54 countries. These are global-coverage mirrors, tried in order.
# Note overpass.osm.ch is Switzerland-only — it answers, but with an empty
# database for Africa, which is worse than an error. Do not add it.
OVERPASS_ENDPOINTS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OSM_STATUS = {"construction": BUILDING, "proposed": ANNOUNCED}


# Only classes that represent an infrastructure project. Without this filter
# the query is dominated by residential street stubs inside housing estates —
# 15,291 of 21,470 in an unfiltered run — which would badly overstate any
# "projects under construction" headline.
SIGNIFICANT = "motorway|trunk|primary|secondary|motorway_link|trunk_link|primary_link"


def fetch_osm(retries=5):
    """Fetch significant works across Africa, then clip to land locally.

    Overpass `area[...]` lookups are expensive and the mirrors time out on
    them when you walk 54 countries. Bounding boxes are cheap, so this
    queries latitude bands over the continent and does the Africa clip
    locally against the same country polygons the dashboard draws — which
    removes the Turkey/Spain/Gulf overspill a raw bbox count suffers from.
    """
    # Calibrated against the mirrors: rail and aeroway are cheap enough for a
    # single continental bbox, but the road regex over the whole continent
    # times out (504). Roads therefore go band by band.
    AFRICA_BBOX = "-36,-18,39,52"
    queries = [
        ("rail", f'way["railway"~"^(construction|proposed)$"]({AFRICA_BBOX});'),
        ("air", f'way["aeroway"="construction"]({AFRICA_BBOX});'),
    ]
    lat = -36.0
    while lat < 39.0:
        hi = min(lat + 7.5, 39.0)
        queries.append((
            f"road {lat:.0f}..{hi:.0f}",
            f'way["highway"="construction"]["construction"~"^({SIGNIFICANT})$"]'
            f'({lat},-18,{hi},52);'
            f'way["highway"="proposed"]["proposed"~"^({SIGNIFICANT})$"]'
            f'({lat},-18,{hi},52);'))
        lat = hi

    raw = []
    for label, body in queries:
        q = f"[out:json][timeout:280];({body});out tags geom;"
        print(f"OSM  {label}")
        res = None
        for attempt in range(retries + 1):
            ep = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
            try:
                res = json.loads(get(ep, timeout=320, data=q.encode()))
                break
            except Exception as e:                           # noqa: BLE001
                print(f"  ! {ep.split('/')[2]} attempt {attempt + 1}: {e}")
                if attempt < retries:
                    wait = 10 * (2 ** min(attempt, 3))
                    print(f"    backing off {wait}s, rotating mirror")
                    time.sleep(wait)
        if res is None:
            print(f"  !! GIVING UP on {label}")
            continue
        got = res.get("elements", [])
        raw.extend(got)
        print(f"     +{len(got):,} ways (raw, pre-clip)")
        time.sleep(3)

    feats = []
    dropped = 0
    for el in raw:
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        mid = geom[len(geom) // 2]
        if not _in_africa(mid["lon"], mid["lat"]):
            dropped += 1
            continue
        t = el.get("tags", {})
        # Precedence matters: a level crossing carries both highway= and
        # railway=, and only the railway value is the construction/proposed
        # one the query matched. Check the gating tags first.
        kind = ""
        for tag in ("railway", "aeroway", "highway"):
            v = t.get(tag)
            if v in ("construction", "proposed"):
                kind = v
                break
        kind = kind or t.get("highway") or t.get("railway") or ""
        sector = ("rail" if t.get("railway")
                  else "air" if t.get("aeroway") else "road")
        feats.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[p["lon"], p["lat"]] for p in geom],
            },
            "properties": {
                "source": "OSM",
                "layer": "ground_truth",
                "name": t.get("name"),
                "sector": sector,
                "eventual_class": t.get("construction") or t.get("proposed"),
                "operator": t.get("operator"),
                "opening_date": t.get("opening_date"),
                "raw_status": kind,
                "dash_status": OSM_STATUS.get(kind),
                "wikidata": t.get("wikidata"),
                "osm_id": f"way/{el.get('id')}",
            },
        })
    print(f"\n  clipped out {dropped:,} ways outside Africa "
          f"(Turkey, Spain, Arabian peninsula)")
    out = write_layer("osm_construction", feats)
    update_meta("ground", fetched=today(), fresh=None, records=len(feats))
    return out


_AFRICA_POLYS = None


def _in_africa(lon, lat):
    """Point-in-polygon against the same outlines the dashboard renders."""
    global _AFRICA_POLYS
    if _AFRICA_POLYS is None:
        bm = DATA / "africa_basemap.json"
        if not bm.exists():
            raise SystemExit("data/africa_basemap.json needed to clip OSM")
        cs = json.loads(bm.read_text())["countries"]
        _AFRICA_POLYS = []
        for c in cs:
            for poly in c["p"]:
                xs = [q[0] for q in poly[0]]
                ys = [q[1] for q in poly[0]]
                _AFRICA_POLYS.append(
                    (min(xs), min(ys), max(xs), max(ys), poly))
    for x0, y0, x1, y1, poly in _AFRICA_POLYS:
        if not (x0 <= lon <= x1 and y0 <= lat <= y1):
            continue
        if _ring(lon, lat, poly[0]) and not any(
                _ring(lon, lat, h) for h in poly[1:]):
            return True
    return False


def _ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


# ------------------------------------------------------------------ entrypoint

LAYERS = {
    "gem": fetch_gem,
    "iati": fetch_iati,
    "osm": fetch_osm,
}

if __name__ == "__main__":
    want = [a.lower() for a in sys.argv[1:]] or list(LAYERS)
    unknown = [w for w in want if w not in LAYERS]
    if unknown:
        sys.exit(f"unknown layer(s): {', '.join(unknown)}\n"
                 f"available: {', '.join(LAYERS)}")
    for key in want:
        print(f"\n=== {key} ===")
        LAYERS[key]()
    print("\nDone. Layers share the `dash_status` field: "
          f"{ANNOUNCED} / {APPROVED} / {BUILDING} / {OPERATING} / {STALLED}")
