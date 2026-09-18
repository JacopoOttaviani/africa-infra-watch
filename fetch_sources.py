#!/usr/bin/env python3
"""
Populate africa-infra-watch from the six verified sources.

Writes one normalised GeoJSON per layer into ./data/, all sharing a common
`dash_status` vocabulary so a single filter works across every layer.

Every endpoint here was tested live on 2026-09-07 (power, AfDB, OSM) and
2026-09-18 (pipelines, cables). See the dataset evaluation and the README for
the reasoning and the known gotchas.

Usage:
    python3 fetch_sources.py                 # all six layers
    python3 fetch_sources.py gem osm         # only the named layers
    python3 fetch_sources.py pipes cables    # the two line layers added Sep 2026
    python3 fetch_sources.py wb              # World Bank, second lender in the finance layer
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
# DAC purpose-code prefixes that count as infrastructure. Energy is the whole
# 23x block: the 3-digit "230" only matched the legacy code 23010 and dropped
# every 5-digit energy code (23110 policy, 23210 solar, 23630 distribution…),
# which is how the World Bank's energy portfolio first went missing.
IATI_INFRA_DAC = ("210", "23", "140", "321", "322", "323", "331", "410", "220")


# The two lenders in the finance layer. Both publish IATI 2.03 per-country
# files through the registry; the fetcher is the same, the conventions differ:
#   AfDB       57 files, XDR (IMF SDR) amounts, exactness 1 on real sites
#   World Bank 148 files worldwide (50 African countries plus two regional
#              files, 289 South of Sahara and 298 Africa regional), USD
#              amounts, every location marked exactness 2 (approximate) with
#              the precision carried by location-class instead: 4 = site,
#              2 = populated place, 1 = administrative region
IATI_PUBLISHERS = {
    "afdb": {"lender": "AfDB", "meta": "finance", "files": None},
    "worldbank": {"lender": "World Bank", "meta": "finance_wb",
                  "files": [c.lower() for c in AFRICA_ISO] + ["289", "298"]},
}


def fetch_iati(publisher="afdb", infra_only=True):
    """One GeoJSON point per <location> with a <point>, per activity.

    The IATI Datastore API (api.iatistandard.org) needs a subscription key and
    returns 401 without one, so go via the registry to the publisher's XML.
    """
    conf = IATI_PUBLISHERS[publisher]
    meta = json.loads(get(
        f"{REGISTRY}?q=organization:{publisher}&rows=300", timeout=90))
    pkgs = meta["result"]["results"]
    if conf["files"]:
        pkgs = [pk for pk in pkgs if pk["name"].rsplit("-", 1)[-1].lower() in conf["files"]]
    urls = [r["url"] for pk in pkgs for r in pk["resources"]]
    print(f"IATI {publisher}: {len(urls)} datasets")

    feats = []
    for i, u in enumerate(urls, 1):
        try:
            xml = get(u, timeout=300)
        except Exception as e:                                # noqa: BLE001
            print(f"  ! skipped {u.rsplit('/', 1)[-1]}: {e}")
            continue
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            print(f"  ! unparseable {u.rsplit('/', 1)[-1]}: {e}")
            continue

        for act in root.iter("iati-activity"):
            # DAC purpose codes only (vocabulary 1, or unstated). The World
            # Bank also publishes its own theme and sector codes as
            # vocabularies 98 and 99; those are kept out of the filter.
            sectors = [s.get("code") for s in act.iter("sector")
                       if s.get("code") and s.get("vocabulary") in (None, "1", "2")]
            if infra_only and not any(
                    c.startswith(IATI_INFRA_DAC) for c in sectors):
                continue

            st = act.find("activity-status")
            code = st.get("code") if st is not None else None
            title = act.find("title/narrative")
            ident = act.find("iati-identifier")
            country = act.find("recipient-country")
            region = act.find("recipient-region")

            # Money: use transactions, NOT <budget>. AfDB repeats the same
            # value in a <budget> element per quarter, so "first budget"
            # understates and "sum of budgets" is only accidentally right.
            # transaction-type 2 = outgoing commitment, 3 = disbursement
            # (5 and 6, interest and loan repayments, are ignored).
            # Values carry no currency attribute — they inherit the
            # activity's default-currency: XDR (IMF SDR) for AfDB, USD for
            # the World Bank.
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

            iid = ident.text.strip() if ident is not None and ident.text else None
            project_url = None
            if publisher == "worldbank" and iid and "-P" in iid:
                project_url = ("https://projects.worldbank.org/en/projects-operations/"
                               f"project-detail/{iid.rsplit('-', 1)[-1]}")

            for loc in act.iter("location"):
                pos = loc.find("point/pos")
                if pos is None or not (pos.text or "").strip():
                    continue
                try:                       # IATI <pos> is "lat lon"
                    lat, lon = (float(x) for x in pos.text.split()[:2])
                except ValueError:
                    continue
                ex = loc.find("exactness")
                lc = loc.find("location-class")
                nm = loc.find("name/narrative")
                feats.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "source": publisher.upper(),
                        "lender": conf["lender"],
                        "layer": "finance",
                        "name": title.text if title is not None else None,
                        "location_name": nm.text if nm is not None else None,
                        "country": country.get("code") if country is not None else None,
                        "region": region.get("code") if region is not None else None,
                        "sector": "infrastructure",
                        "dac_sectors": sectors,
                        "raw_status": code,
                        "dash_status": IATI_STATUS.get(code),
                        # exactness 1 = exact; 2 = approximate (often a country
                        # centroid). Filter to "1" for a map that isn't pinned
                        # to the middle of each country. The World Bank marks
                        # everything 2 and says how close in location-class.
                        "geo_precision": ex.get("code") if ex is not None else None,
                        "location_class": lc.get("code") if lc is not None else None,
                        "commitment": round(commitment, 2) or None,
                        "disbursed": round(disbursed, 2) or None,
                        "currency": currency,
                        "iati_id": iid,
                        "project_url": project_url,
                    },
                })
        if i % 15 == 0:
            print(f"  … {i}/{len(urls)} files, {len(feats):,} located so far")

    out = write_layer(f"iati_{publisher}_finance", feats)
    update_meta(conf["meta"], fetched=today(), fresh=None, datasets=len(urls), records=len(feats),
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


# ------------------------------------------------- GEM (oil & gas pipelines)

# GEM's pipeline trackers are two datasets: the Global Gas Infrastructure
# Tracker (GGIT, gas transmission pipelines) and the Global Oil Infrastructure
# Tracker (GOIT, crude and NGL pipelines). Their official download is a form on
# globalenergymonitor.org; the route geometry that the same site's maps draw
# sits in the public bucket, but NOT under Current_maps/ like the power
# tracker: under Input_geojson_files/<tracker>/<release>/. Same licence
# (CC BY 4.0), same status vocabulary, plus "proposed".
PIPE_TRACKERS = {"ggit": "gas", "goit": "oil"}
PIPE_STATUS = {**GEM_STATUS, "proposed": ANNOUNCED, "idle": STALLED}


def gem_latest_pipeline_geojson(tracker):
    """Newest release folder, newest GeoJSON inside it. Folder names carry the
    release month (2026-07), so a plain sort finds the latest."""
    listing = get(
        f"{GEM_BUCKET}/?list-type=2&prefix=Input_geojson_files/{tracker}/"
        "&max-keys=1000", timeout=90).decode("utf-8", "replace")
    keys = [k for k in re.findall(r"<Key>([^<]+)</Key>", listing)
            if k.lower().endswith(".geojson")]
    if not keys:
        raise RuntimeError(f"no {tracker} GeoJSON found in GEM bucket")
    # sort by the release folder, then by file name, so 2026-07 beats 2026-06.1
    keys.sort(key=lambda k: (k.split("/")[2], k))
    key = keys[-1]
    return f"{GEM_BUCKET}/{urllib.parse.quote(key)}", key.split("/")[2]


def _line_parts(geom):
    """Flatten any GeoJSON geometry into a list of coordinate lists (lines).
    GGIT ships 712 features whose geometry is an EMPTY GeometryCollection —
    segments with no published route — which come back as []."""
    if not geom:
        return []
    t = geom.get("type")
    if t == "LineString":
        return [geom["coordinates"]] if len(geom.get("coordinates") or []) >= 2 else []
    if t == "MultiLineString":
        return [c for c in geom.get("coordinates") or [] if len(c) >= 2]
    if t == "GeometryCollection":
        return [p for g in geom.get("geometries") or [] for p in _line_parts(g)]
    return []


def _num(s):
    try:
        return float(str(s).replace(",", "")) if s not in (None, "") else None
    except ValueError:
        return None


def fetch_pipelines():
    feats, unrouted, releases = [], 0, []
    for tracker, fuel_group in PIPE_TRACKERS.items():
        url, release = gem_latest_pipeline_geojson(tracker)
        releases.append(f"{tracker.upper()} {release}")
        print(f"GEM  {tracker.upper()} release {release}: "
              f"{urllib.parse.unquote(url.rsplit('/', 1)[-1])}")
        raw = json.loads(get(url, timeout=900))
        n_af = 0
        for f in raw.get("features", []):
            p = f.get("properties") or {}
            countries = [c.strip() for c in (p.get("CountriesOrAreas") or "").split(",")
                         if c.strip()]
            # a pipeline counts if ANY country on its route is African, so
            # Medgaz (Algeria–Spain) and Transmed (Tunisia–Italy) stay in
            if not any(c in AFRICA_NAMES or c == "The Gambia" for c in countries):
                continue
            n_af += 1
            parts = _line_parts(f.get("geometry"))
            if not parts:
                unrouted += 1
                continue
            status = (p.get("Status") or "").strip().lower()
            name = (p.get("PipelineName") or "").strip()
            seg = (p.get("SegmentName") or "").strip()
            feats.append({
                "type": "Feature",
                "geometry": {"type": "MultiLineString", "coordinates": parts},
                "properties": {
                    "source": "GEM",
                    "layer": "pipelines",
                    "tracker": tracker.upper(),
                    "name": f"{name} · {seg}" if seg and seg != name else name,
                    "pipeline": name,
                    "segment": seg or None,
                    "fuel": (p.get("Fuel") or fuel_group).strip(),
                    "countries": countries,
                    "sector": "energy",
                    "owner": (p.get("Owner") or "").strip() or None,
                    "parent": (p.get("Parent") or "").strip() or None,
                    "start_year": (p.get("StartYear1") or "").strip() or None,
                    "capacity": _num(p.get("Capacity")),
                    "capacity_units": (p.get("CapacityUnits") or "").strip() or None,
                    "capacity_bcm_y": _num(p.get("CapacityBcm/y")),
                    "capacity_boed": _num(p.get("CapacityBOEd")),
                    "length_km": _num(p.get("LengthMergedKm")) or _num(p.get("LengthKnownKm"))
                                 or _num(p.get("LengthEstimateKm")),
                    "diameter": (f"{p.get('Diameter')} {p.get('DiameterUnits') or ''}".strip()
                                 if p.get("Diameter") else None),
                    "start_location": (p.get("StartLocation") or "").strip() or None,
                    "end_location": (p.get("EndLocation") or "").strip() or None,
                    "raw_status": status,
                    "dash_status": PIPE_STATUS.get(status),
                    "project_id": p.get("ProjectID") or None,
                    "url": (p.get("Wiki") or "").strip() or None,
                    "last_updated": p.get("LastUpdated") or None,
                    "release": release,
                },
            })
        print(f"     {n_af:,} African segments in {tracker.upper()}")
    print(f"  {unrouted:,} African segments have no published route and are not drawn")
    out = write_layer("gem_oil_gas_pipelines", feats)
    update_meta("pipelines", fetched=today(), fresh=None, release=" · ".join(releases),
                records=len(feats), unrouted=unrouted)
    return out


# ------------------------------------------------ TeleGeography (submarine cables)

# The Submarine Cable Map's own JSON API. Undocumented but stable for years;
# every endpoint here was tested live on 2026-09-18. Cable routes come as one
# GeoJSON, landing points as another, and the per-cable detail (owners,
# suppliers, ready-for-service year, planned flag, landing points with
# country) as one small JSON per cable. Licence: CC BY-SA 4.0 (TeleGeography's
# FAQ), attribution "TeleGeography".
TG_API = "https://www.submarinecablemap.com/api/v3"
# TeleGeography's own spellings for Africa and its islands -> ISO 3166-1. The
# cable detail carries a country per landing point; landing-point names read
# "City, Country" with commas inside some countries ("Congo, Dem. Rep."), so
# the fallback matches by suffix.
TG_ISO = {
    "Algeria": "DZ", "Angola": "AO", "Benin": "BJ", "Cameroon": "CM", "Cape Verde": "CV",
    "Comoros": "KM", "Congo, Dem. Rep.": "CD", "Congo, Rep.": "CG", "Côte d'Ivoire": "CI",
    "Djibouti": "DJ", "Egypt": "EG", "Equatorial Guinea": "GQ", "Eritrea": "ER", "Gabon": "GA",
    "Gambia": "GM", "Ghana": "GH", "Guinea": "GN", "Guinea-Bissau": "GW", "Kenya": "KE",
    "Liberia": "LR", "Libya": "LY", "Madagascar": "MG", "Mauritania": "MR", "Mauritius": "MU",
    "Mayotte": "YT", "Morocco": "MA", "Mozambique": "MZ", "Namibia": "NA", "Nigeria": "NG",
    "Réunion": "RE", "Saint Helena, Ascension and Tristan da Cunha": "SH",
    "Sao Tome and Principe": "ST", "Senegal": "SN", "Seychelles": "SC", "Sierra Leone": "SL",
    "Somalia": "SO", "South Africa": "ZA", "Sudan": "SD", "Tanzania": "TZ", "Togo": "TG",
    "Tunisia": "TN", "Uganda": "UG", "Western Sahara": "EH",
}


def _tg_country(name):
    for c in sorted(TG_ISO, key=len, reverse=True):
        if name.endswith(", " + c):
            return c
    return None


def fetch_cables(pause=0.1):
    """Every cable with at least one African landing point.

    Walks every cable's detail record (about 700 small requests, a few
    minutes) rather than going through landing points: a landing point that
    TeleGeography marks "to be determined" (Cape Town for Umoja, say) has no
    detail record of its own, so the shorter route misses whole cables."""
    lp_geo = json.loads(get(f"{TG_API}/landing-point/landing-point-geo.json", timeout=120))
    lp_xy = {}
    for f in lp_geo.get("features", []):
        p = f.get("properties") or {}
        if p.get("id") and f.get("geometry"):
            lp_xy[p["id"]] = f["geometry"]["coordinates"][:2]
    print(f"TG   {len(lp_xy):,} landing points with coordinates")

    geo = json.loads(get(f"{TG_API}/cable/cable-geo.json", timeout=120))
    routes = {}
    for f in geo.get("features", []):
        cid = (f.get("properties") or {}).get("id")
        if cid:
            routes.setdefault(cid, []).extend(_line_parts(f.get("geometry")))

    ids = [c["id"] for c in json.loads(get(f"{TG_API}/cable/all.json", timeout=120)) if c.get("id")]
    print(f"TG   {len(ids):,} cable systems worldwide; reading each one")
    year = int(today()[:4])
    feats, missing, failed = [], 0, 0
    for i, cid in enumerate(ids, 1):
        d = None
        for attempt in range(3):
            try:
                d = json.loads(get(f"{TG_API}/cable/{cid}.json", timeout=60))
                break
            except Exception as e:                            # noqa: BLE001
                if attempt == 2:
                    print(f"  ! cable {cid}: {e}")
                    failed += 1
                else:
                    time.sleep(2 + 3 * attempt)
        if i % 100 == 0:
            print(f"  … {i}/{len(ids)} cables, {len(feats)} African so far")
        time.sleep(pause)
        if not d:
            continue
        landings = [lp for lp in d.get("landing_points", []) if lp.get("id")]
        african = []
        for lp in landings:
            c = lp.get("country") or _tg_country(lp.get("name") or "")
            if c in TG_ISO and lp["id"] in lp_xy:
                lon, lat = lp_xy[lp["id"]]
                african.append({"id": lp["id"], "name": lp.get("name"), "country": c,
                                "iso": TG_ISO[c], "lon": lon, "lat": lat,
                                "tbd": bool(lp.get("is_tbd"))})
        if not african:
            continue
        parts = routes.get(cid) or []
        if not parts:
            missing += 1
            print(f"  ! {cid}: African landing but no route geometry; skipped")
            continue
        planned = bool(d.get("is_planned"))
        rfs = d.get("rfs_year")
        # TeleGeography has two states, planned and in service. A planned
        # cable due within about a year is being manufactured or laid; one
        # further out is a record of intent. Documented in the Methodology.
        if not planned:
            status = OPERATING
        elif isinstance(rfs, int) and rfs <= year + 1:
            status = BUILDING
        else:
            status = ANNOUNCED
        countries = sorted({lp.get("country") for lp in landings if lp.get("country")})
        feats.append({
            "type": "Feature",
            "geometry": {"type": "MultiLineString", "coordinates": parts},
            "properties": {
                "source": "TeleGeography",
                "layer": "cables",
                "cable_id": cid,
                "name": d.get("name") or cid,
                "sector": "ict",
                "rfs_year": rfs,
                "rfs": d.get("rfs") or None,
                "is_planned": planned,
                "length_km": _num((d.get("length") or "").replace("km", "")),
                "owners": d.get("owners") or None,
                "suppliers": d.get("suppliers") or None,
                "url": d.get("url") or None,
                "notes": d.get("notes") or None,
                "countries": countries,
                "landing_total": len(landings),
                "landing_points": african,
                "raw_status": "planned" if planned else "in service",
                "dash_status": status,
                "map_url": f"https://www.submarinecablemap.com/submarine-cable/{cid}",
            },
        })
    if failed:
        print(f"  ! {failed} cable record(s) could not be read")
    if missing:
        print(f"  ! {missing} cable(s) had no route geometry and were skipped")
    out = write_layer("telegeography_cables", feats)
    update_meta("cables", fetched=today(), fresh=None, records=len(feats),
                landing_points=sum(len(f["properties"]["landing_points"]) for f in feats))
    return out


# ------------------------------------------------------------------ entrypoint

LAYERS = {
    "gem": fetch_gem,
    "iati": fetch_iati,
    "wb": lambda: fetch_iati("worldbank"),
    "osm": fetch_osm,
    "pipes": fetch_pipelines,
    "cables": fetch_cables,
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
