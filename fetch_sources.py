#!/usr/bin/env python3
"""
Populate AfricaWatch from the ten verified sources.

Writes one normalised GeoJSON per layer into ./data/, all sharing a common
`dash_status` vocabulary so a single filter works across every layer.

Every endpoint here was tested live on 2026-09-07 (power, AfDB, OSM),
2026-09-18 (pipelines, cables) and 2026-09-19 (AidData). See the dataset
evaluation and the README for the reasoning and the known gotchas.

Usage:
    python3 fetch_sources.py                 # all ten sources
    python3 fetch_sources.py gem osm         # only the named layers
    python3 fetch_sources.py pipes cables    # the two line layers added Sep 2026
    python3 fetch_sources.py wb              # World Bank, second lender in the finance layer
    python3 fetch_sources.py china           # AidData, Chinese official finance 2000-2023
    python3 fetch_sources.py eu              # European Commission and EIB, via IATI
    python3 fetch_sources.py mattei          # Italy's Piano Mattei, from the Government's project portal
"""

import concurrent.futures
import csv
import html as html_mod
import io
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from fetch_basemap import dp
from shared import EUR_USD, fmt_date, today, update_meta

from region import AFRICA_ISO, AFRICA_NAMES, REGION, ROOT_DATA  # noqa: E402,F401  (AFRICA_* re-exported for fetch_minerals)

# this edition's data directory (data/, or data/sea/ for Southeast Asia)
DATA = REGION.data_dir
UA = {"User-Agent": "africa-project-atlas/0.1 (dataset evaluation)"}

# The region's ISO-3166-1 alpha-2 codes (Africa's 54, Southeast Asia's 11) and
# the publishers' spellings of its countries' names (region.py). Used to clip
# OSM (a bounding box pulls in Turkey and Spain, or southern China) and to
# filter the global files (GEM, the pipeline trackers, AidData).
REGION_ISO = REGION.iso
REGION_NAMES = REGION.fetch_names

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


def _bucket_list(prefix, delimiter=None):
    """Every <Contents> (key, LastModified day) and <CommonPrefixes> under a
    prefix, following continuation tokens: one page holds 1,000 keys, and a
    single power release ships thousands of map tiles, so the first page alone
    never reaches the next release's folder."""
    keys, prefixes, token = {}, [], None
    while True:
        q = f"{GEM_BUCKET}/?list-type=2&prefix={urllib.parse.quote(prefix)}&max-keys=1000"
        if delimiter:
            q += f"&delimiter={urllib.parse.quote(delimiter)}"
        if token:
            q += f"&continuation-token={urllib.parse.quote(token)}"
        listing = get(q, timeout=90).decode("utf-8", "replace")
        for c in re.findall(r"<Contents>(.*?)</Contents>", listing, re.S):
            k = re.search(r"<Key>([^<]+)</Key>", c)
            m = re.search(r"<LastModified>(\d{4}-\d\d-\d\d)", c)
            if k:
                keys[html_mod.unescape(k.group(1))] = m.group(1) if m else None
        prefixes += [html_mod.unescape(p) for p in re.findall(
            r"<CommonPrefixes>\s*<Prefix>([^<]+)</Prefix>", listing)]
        t = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", listing)
        if not t or "<IsTruncated>true</IsTruncated>" not in listing:
            return keys, prefixes
        token = html_mod.unescape(t.group(1))


def _release_key(folder):
    """Order GEM release folders: 2026-08 < 2026-08-v2 < 2026-08-v3 < 2026-09.
    A plain string sort puts 2026-08/ after 2026-08-v3/ ('-' < '/')."""
    m = re.match(r"(\d{4})-(\d\d)(?:-v(\d+))?$", folder)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)) if m else (0, 0, 0)


def gem_latest_csv():
    """Resolve the current release from the listable bucket.

    GEM's own map config still points at a deleted 2026-03 path, so never
    hardcode a release URL — discover it. GEM_RELEASE=2026-08-v2 in the
    environment pins a release, so a rebuild can reproduce an earlier one.
    """
    root = "Current_maps/integrated-power/"
    _, folders = _bucket_list(root, delimiter="/")
    names = [f[len(root):].strip("/") for f in folders if f.startswith(root) and f != root]
    pin = (os.environ.get("GEM_RELEASE") or "").strip()
    order = [pin] if pin else sorted((n for n in names if _release_key(n) != (0, 0, 0)),
                                     key=_release_key, reverse=True)
    for release in order:
        keys, _ = _bucket_list(f"{root}{release}/")
        csvs = sorted(k for k in keys if k.endswith(".csv"))
        if csvs:
            return f"{GEM_BUCKET}/{urllib.parse.quote(csvs[-1])}", keys[csvs[-1]]
    raise RuntimeError(f"no integrated-power CSV found in GEM bucket ({pin or 'any release'})")


def fetch_gem():
    url, uploaded = gem_latest_csv()
    # the release is the folder (2026-08-v2); the file's upload day is when
    # GEM published it, which is what "data as of" should say
    release = urllib.parse.unquote(url).rsplit('/', 2)[-2]
    print(f"GEM  release: {release}, published {uploaded}")
    raw = get(url, timeout=600).decode("utf-8", "replace")

    feats = []
    for row in csv.DictReader(io.StringIO(raw)):
        if (row.get("country-area1") or "").strip() not in REGION_NAMES:
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
    update_meta("assets", fetched=today(), fresh=fmt_date(uploaded) if uploaded else None,
                release=release, records=len(feats))
    return out


# ------------------------------------------------------------- IATI (finance)

REGISTRY = "https://iatiregistry.org/api/3/action/package_search"
# DAC purpose-code prefixes that count as infrastructure. Energy is the whole
# 23x block: the 3-digit "230" only matched the legacy code 23010 and dropped
# every 5-digit energy code (23110 policy, 23210 solar, 23630 distribution…),
# which is how the World Bank's energy portfolio first went missing.
IATI_INFRA_DAC = ("210", "23", "140", "321", "322", "323", "331", "410", "220")

# Commitments a publisher's file states wrongly, by activity id: the figure
# the bank's own project page gives, and why. Checked by hand on the date in
# the note; the card shows the file's figure beside the counted one, like any
# other counting correction.
IATI_AMOUNT_FIX = {
    # ADB's Indonesia file carries 44,229,000,000 for Loan 4708-INO, a figure
    # larger than the Bank lends in a year; its Project Data Sheet says US$ 300 million
    "XM-DAC-46004-56017-001-LN4708": (300_000_000.0, "ADB's file states USD 44,229 million for this loan; "
                                      "the Bank's Project Data Sheet puts it at USD 300 million (checked 17 Oct 2026), "
                                      "which is counted"),
}


# The two lenders in the finance layer: the region's development bank (the
# AfDB in Africa, the ADB in Southeast Asia; region.py) and the World Bank.
# All publish IATI 2.03 per-country files through the registry; the fetcher is
# the same, the conventions differ:
#   AfDB       57 files, XDR (IMF SDR) amounts, exactness 1 on real sites
#   ADB        one file per borrowing country plus a regional one, USD amounts,
#              every location exactness 2 and named: a province, a town, or the
#              country itself (GeoNames ids, no location-class); a named one is
#              flagged location_named so the builders draw it as a named place
#   World Bank 148 files worldwide (50 African countries plus two regional
#              files, 289 South of Sahara and 298 Africa regional), USD
#              amounts, every location marked exactness 2 (approximate) with
#              the precision carried by location-class instead: 4 = site,
#              2 = populated place, 1 = administrative region. Activities
#              with no location still carry one, "No Data Available" at
#              <pos>0 0</pos> (Null Island, in the Gulf of Guinea), and a
#              few dozen are geocoded to the wrong continent; place_iati()
#              below deals with both.
IATI_PUBLISHERS = {
    REGION.bank["publisher"]: {"lender": REGION.bank["code"], "meta": "finance", "files": REGION.bank["files"]},
    "worldbank": {"lender": "World Bank", "meta": "finance_wb", "files": REGION.wb_files},
}


# Cabo Verde to Mauritius, Tunis to the Cape. Wider than the continent so a
# site on an island is kept, narrower than check_data's window so that the
# Gulf of Guinea's Null Island, Kosovo (a Guinea project) and Nepal (three
# Mozambican districts) are not.
IATI_WINDOW = REGION.iati_window   # lon0, lat0, lon1, lat1


def place_iati(feats):
    """Drop the locations a publisher could not place, and pin what is left
    of the activity to its country.

    A location is kept when its point is in IATI_WINDOW and not exactly
    0 0. An activity that loses every location is re-pinned to the interior
    point of its recipient country, marked exactness 2 / location-class 1
    so the map draws it as a country centroid, when it names one that the
    basemap has; the regional files' activities name a region and no
    country, and those are dropped."""
    kept, lost = [], {}
    x0, y0, x1, y1 = IATI_WINDOW
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        if (lon, lat) == (0.0, 0.0) or not (x0 <= lon <= x1 and y0 <= lat <= y1):
            lost.setdefault(f["properties"].get("iati_id"), f)
        else:
            kept.append(f)
    n_lost = len(feats) - len(kept)
    placed = {f["properties"].get("iati_id") for f in kept}
    recentred = dropped = 0
    for iid, f in lost.items():
        if iid in placed:               # the activity still has a good location
            continue
        iso = f["properties"].get("country")
        lon, lat = _country_centre(iso) if iso else (None, None)
        if lon is None:
            dropped += 1
            continue
        kept.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": dict(f["properties"], location_name=None,
                               geo_precision="2", location_class="1"),
        })
        recentred += 1
    if n_lost:
        print(f"  {n_lost} location(s) at 0 0 or off the continent dropped; "
              f"{recentred} activity(ies) re-pinned to the country's centre, "
              f"{dropped} with no country left off the map")
    return kept


def fetch_iati(publisher=None, infra_only=True):
    """One GeoJSON point per <location> with a <point>, per activity.

    The IATI Datastore API (api.iatistandard.org) needs a subscription key and
    returns 401 without one, so go via the registry to the publisher's XML.
    """
    publisher = publisher or REGION.bank["publisher"]
    conf = IATI_PUBLISHERS[publisher]
    # the names a country's own location carries, so a location named after
    # the country is told apart from a named province or town (ADB)
    own_names = {}
    for n, i in REGION.names.items():
        own_names.setdefault(i, set()).add(n.lower())
    meta = json.loads(get(
        f"{REGISTRY}?q=organization:{publisher}&rows=300", timeout=90))
    pkgs = meta["result"]["results"]
    if conf["files"]:
        pkgs = [pk for pk in pkgs if pk["name"].rsplit("-", 1)[-1].lower() in conf["files"]]
    urls = [r["url"] for pk in pkgs for r in pk["resources"]]
    print(f"IATI {publisher}: {len(urls)} datasets")

    feats, n_budget, n_counterpart, n_fixed = [], 0, 0, 0
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
            # Budget support (aid-type A01 general, A02 sector) is left out:
            # a development-policy loan tagged with one energy code is a loan
            # to a treasury, not a project. The World Bank tags 230-odd of
            # its African activities so, the AfDB a few dozen.
            aid = {d.get("code") for d in act.iter("default-aid-type") if d.get("vocabulary") in (None, "1")}
            aid |= {d.get("code") for tx in act.iter("transaction") for d in tx.iter("aid-type")
                    if d.get("vocabulary") in (None, "1")}
            if infra_only and aid & {"A01", "A02"}:
                n_budget += 1
                continue
            # The share of the activity that is infrastructure, by the
            # publisher's own sector percentages (5-digit codes, else 3-digit).
            # A project that is 60% schools and 40% roads counts 40% of its
            # commitment; the card shows the whole figure beside it.
            pct = []
            for vocab in ((None, "1"), ("2",)):
                pct = [(s.get("code"), _num(s.get("percentage"))) for s in act.iter("sector")
                       if s.get("code") and s.get("vocabulary") in vocab and _num(s.get("percentage"))]
                if pct:
                    break
            pct_total = sum(p for _, p in pct)
            share = (sum(p for c, p in pct if c.startswith(IATI_INFRA_DAC)) / pct_total) if pct_total else 1.0
            share = min(1.0, share)
            # list the codes largest share first, so the label and the code
            # the card shows are the activity's main infrastructure sector
            weight = {c: p for c, p in pct}
            sectors = sorted(dict.fromkeys(sectors), key=lambda c: (not c.startswith(IATI_INFRA_DAC),
                                                                   -weight.get(c, 0)))

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
            # The AfDB also files the borrowing government's own counterpart
            # funds as a commitment (provider-org XX-COA-GOV): Medupi's three
            # are two AfDB loans and South Africa's UA 5.44bn. That money is
            # not the Bank's and is left out, as MapAfrica's own
            # total_commitments_nongov leaves it out.
            currency = act.get("default-currency")
            commitment = disbursed = counterpart = 0.0
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
                    prov = tx.find("provider-org")
                    if prov is not None and (prov.get("ref") or "").upper().endswith("-COA-GOV"):
                        counterpart += amt
                        continue
                    commitment += amt
                elif tt.get("code") == "3":
                    disbursed += amt
                currency = v.get("currency") or currency
            # What the totals add up: the infrastructure share of the
            # lender's own commitment, nothing for a cancelled or suspended
            # activity (the money was promised, then withdrawn or frozen).
            stalled = IATI_STATUS.get(code) == STALLED
            # The AfDB leaves an activity at status 1 (pipeline) after its
            # board has approved it: a commitment transaction is on record,
            # often signed. That is approved, not a record of intent.
            dash = IATI_STATUS.get(code)
            if code == "1" and commitment > 0:
                dash = APPROVED
            counted = None if stalled else commitment * share
            counted_dis = None if stalled else disbursed * share
            notes = []
            if stalled:
                notes.append("cancelled or suspended, so not counted in totals")
            elif share < 0.995:
                notes.append(f"{share:.0%} of its sectors are infrastructure; that share is counted")
            if counterpart:
                notes.append("the borrowing government's own contribution is not counted")
            n_counterpart += bool(counterpart)

            iid = ident.text.strip() if ident is not None and ident.text else None
            if iid in IATI_AMOUNT_FIX and not stalled:
                fixed, why = IATI_AMOUNT_FIX[iid]
                counted = fixed * share
                notes.append(why)
                n_fixed += 1
            project_url = None
            if publisher == "worldbank" and iid and "-P" in iid:
                project_url = ("https://projects.worldbank.org/en/projects-operations/"
                               f"project-detail/{iid.rsplit('-', 1)[-1]}")
            elif publisher == "asdb" and iid:
                # XM-DAC-46004-39603-012-GRNT0034: the project number is 39603-012
                m = re.match(r"XM-DAC-46004-(\d{5}-\d{3})", iid)
                if m:
                    project_url = f"https://www.adb.org/projects/{m.group(1)}/main"
            iso_here = country.get("code") if country is not None else None

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
                # ADB names every location and marks all of them exactness 2:
                # one named after the country is the country's point, any
                # other a province or a town
                named = (publisher == "asdb" and nm is not None and bool((nm.text or "").strip())
                         and (nm.text or "").strip().lower() not in own_names.get(iso_here, set()))
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
                        "dash_status": dash,
                        # exactness 1 = exact; 2 = approximate (often a country
                        # centroid). Filter to "1" for a map that isn't pinned
                        # to the middle of each country. The World Bank marks
                        # everything 2 and says how close in location-class.
                        "geo_precision": ex.get("code") if ex is not None else None,
                        "location_class": lc.get("code") if lc is not None else None,
                        "location_named": True if named else None,
                        # counted (what totals add up) and, where it differs,
                        # the lender's own figure as published
                        "commitment": round(counted, 2) if counted else None,
                        "disbursed": round(counted_dis, 2) if counted_dis else None,
                        "commitment_published": round(commitment, 2) or None
                            if (counted is None or abs(commitment - counted) > 0.5) else None,
                        "disbursed_published": round(disbursed, 2) or None
                            if (counted_dis is None or abs(disbursed - counted_dis) > 0.5) else None,
                        "infra_share": round(share, 3) if share < 0.995 else None,
                        "counterpart": round(counterpart, 2) or None,
                        "counted_note": "; ".join(notes) or None,
                        "currency": currency,
                        "iati_id": iid,
                        "project_url": project_url,
                    },
                })
        if i % 15 == 0:
            print(f"  … {i}/{len(urls)} files, {len(feats):,} located so far")

    print(f"  left out {n_budget:,} budget-support activities (aid-type A01/A02); "
          f"{n_counterpart:,} carry a government counterpart commitment, not counted"
          + (f"; {n_fixed} amount(s) corrected from IATI_AMOUNT_FIX" if n_fixed else ""))
    feats = place_iati(feats)
    out = write_layer(f"iati_{publisher}_finance", feats)
    update_meta(conf["meta"], fetched=today(), fresh=None, datasets=len(urls), records=len(feats),
                activities=len({f["properties"]["iati_id"] for f in feats}), budget_support=n_budget,
                amount_fixes=n_fixed)
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
# the query is dominated by residential street stubs inside housing estates:
# in October 2026 an unfiltered run found about nine times as many road
# segments (47,830 against 5,328), two thirds of them residential, which
# would badly overstate any "projects under construction" headline.
SIGNIFICANT = "motorway|trunk|primary|secondary|motorway_link|trunk_link|primary_link"


def fetch_osm(retries=5):
    """Fetch significant works across Africa, then clip to land locally.

    Overpass `area[...]` lookups are expensive and the mirrors time out on
    them when you walk 54 countries. Bounding boxes are cheap, so this
    queries latitude bands over the continent and does the Africa clip
    locally against the same country polygons the dashboard draws — which
    removes the Turkey/Spain/Gulf overspill a raw bbox count suffers from.
    """
    # Every query covers a latitude band of the continent's box, so one the
    # mirrors keep timing out on can be split and asked again.
    osm = REGION.osm
    def band(kind, lo, hi, x0=osm["lon0"], x1=osm["lon1"]):
        box = f"({lo},{x0},{hi},{x1})"
        body = {
            "rail": f'way["railway"~"^(construction|proposed)$"]{box};',
            # a runway or terminal outline under works is aeroway=construction;
            # a whole new airport is usually landuse=construction with
            # construction=aerodrome, or construction:aeroway=*
            "air": (f'way["aeroway"~"^(construction|proposed)$"]{box};'
                    f'way["construction"="aerodrome"]{box};'
                    f'way["construction:aeroway"]{box};'
                    f'way["proposed:aeroway"]{box};'),
            "road": (f'way["highway"="construction"]["construction"~"^({SIGNIFICANT})$"]{box};'
                     f'way["highway"="proposed"]["proposed"~"^({SIGNIFICANT})$"]{box};'),
        }[kind]
        label = f"{kind} {lo:g}..{hi:g}" + (f" × {x0:g}..{x1:g}" if (x0, x1) != (osm["lon0"], osm["lon1"]) else "")
        return (label, body, (kind, lo, hi, x0, x1))

    # rail and aeroway are cheap enough for one continental band; the road
    # regex over the whole continent times out (504), so roads start in bands
    queries = [band("rail", osm["lat0"], osm["lat1"]), band("air", osm["lat0"], osm["lat1"])]
    lat = osm["lat0"]
    while lat < osm["lat1"]:
        hi = min(lat + osm["band"], osm["lat1"])
        queries.append(band("road", lat, hi))
        lat = hi

    # A band the mirrors keep timing out on is split in two and queued again,
    # by latitude down to bands of under two degrees, then by longitude down to
    # boxes under six degrees wide (a dense band such as Bangkok to Manila);
    # past that the fetch stops without writing, so a gap never replaces a
    # complete layer.
    raw, seen = [], set()
    while queries:
        label, body, where = queries.pop(0)
        q = f"[out:json][timeout:280];({body});out tags geom;"
        print(f"OSM  {label}")
        res = None
        # a wide band gets three tries before it is split; the narrowest, all of them
        tries = retries + 1 if where[2] - where[1] <= 2 and where[4] - where[3] <= 6 else 3
        for attempt in range(tries):
            ep = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
            try:
                res = json.loads(get(ep, timeout=320, data=q.encode()))
                break
            except Exception as e:                           # noqa: BLE001
                print(f"  ! {ep.split('/')[2]} attempt {attempt + 1}: {e}")
                if attempt < tries - 1:
                    wait = 10 * (2 ** min(attempt, 3))
                    print(f"    backing off {wait}s, rotating mirror")
                    time.sleep(wait)
        if res is None:
            kind, lo, hi, x0, x1 = where
            if hi - lo > 2:
                mid = round((lo + hi) / 2, 2)
                print(f"  !! {label} failed; splitting it into {lo:g}..{mid:g} and {mid:g}..{hi:g}")
                queries[:0] = [band(kind, lo, mid, x0, x1), band(kind, mid, hi, x0, x1)]
                continue
            if x1 - x0 > 6:
                xm = round((x0 + x1) / 2, 2)
                print(f"  !! {label} failed; splitting it by longitude into {x0:g}..{xm:g} and {xm:g}..{x1:g}")
                queries[:0] = [band(kind, lo, hi, x0, xm), band(kind, lo, hi, xm, x1)]
                continue
            raise SystemExit(f"OSM: {label} failed on every mirror; nothing written, the previous layer stays")
        # a way that crosses a band's edge comes back from both bands
        got = [el for el in res.get("elements", []) if el.get("id") not in seen]
        seen.update(el.get("id") for el in got)
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
        if not _in_region(mid["lon"], mid["lat"]):
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
        airport = bool(t.get("aeroway") or t.get("construction") == "aerodrome"
                       or t.get("construction:aeroway") or t.get("proposed:aeroway"))
        if not kind and airport and (t.get("landuse") == "construction" or t.get("construction:aeroway")):
            kind = "construction"
        if not kind and t.get("proposed:aeroway"):
            kind = "proposed"
        kind = kind or t.get("highway") or t.get("railway") or ""
        sector = ("rail" if t.get("railway")
                  else "air" if airport else "road")
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
    print(f"\n  clipped out {dropped:,} ways outside {REGION.name} "
          f"(the bounding box's overspill into the neighbours)")
    out = write_layer("osm_construction", feats)
    update_meta("ground", fetched=today(), fresh=None, records=len(feats))
    return out


_AFRICA_POLYS = None


def _in_region(lon, lat):
    """Point-in-polygon against the same outlines the dashboard renders."""
    global _AFRICA_POLYS
    if _AFRICA_POLYS is None:
        bm = DATA / REGION.basemap_110
        if not bm.exists():
            raise SystemExit(f"{bm.relative_to(ROOT_DATA.parent)} needed to clip OSM; run fetch_basemap.py first")
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
# Lengths that are wrong in the releases the site reads, by GEM ProjectID,
# with where the corrected figure comes from. Each is GEM's own error; report
# it through the error form on the tracker's page and drop the entry once a
# release fixes it. fetch_pipelines() also prints any segment whose stated
# length is more than three times, or under a third of, GEM's own estimate,
# so the next one surfaces.
PIPE_LENGTH_FIX = {
    "P0484": (524.6, "GEM wiki, Wafa-Mellitah gas pipeline: 524.6 km; the tracker's 5,246 km "
                     "drops a decimal (its own estimate is 525.7 km)"),
    "P1313": (614.0, "GEM wiki, Trans Nigeria Gas Pipeline: the AKK pipeline is 614 km; the tracker's "
                     "1,300 km is the whole system, whose phases 2 and 3 are a record of their own"),
    "P1879": (40.0, "GEM wiki, Egbin Node-Alagbado gas pipeline: 40 km"),
    "P6647": (427.0, "Medgaz's onshore leg is 547 km from Hassi R'Mel to Beni Saf (GEM wiki), "
                     "less the 120 km Mocta Douz-Beni Saf segment"),
}
# Segments whose published route is not the pipeline. They are left undrawn
# and counted with the unrouted ones rather than drawn somewhere they are not.
PIPE_ROUTE_DROP = {
    "P2055": "Medgaz offshore (Beni Saf-Almería): the tracker's route runs 805 km overland "
             "from near Hassi Messaoud to Oran and never crosses the sea",
}


def gem_latest_pipeline_geojson(tracker):
    """Newest release folder, newest GeoJSON inside it. Folder names carry the
    release month (2026-07), so a plain sort finds the latest."""
    listing, _ = _bucket_list(f"Input_geojson_files/{tracker}/")
    keys = [k for k in listing if k.lower().endswith(".geojson")]
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
    feats, unrouted, releases, updated, fixed, dropped_by_hand = [], 0, [], [], 0, 0
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
            # a pipeline counts if ANY country on its route is in the region,
            # so Medgaz (Algeria–Spain) and Transmed (Tunisia–Italy) stay in
            if not any(c in REGION_NAMES for c in countries):
                continue
            n_af += 1
            pid = (p.get("ProjectID") or "").strip()
            dropped_by_hand += pid in PIPE_ROUTE_DROP
            parts = [] if pid in PIPE_ROUTE_DROP else _line_parts(f.get("geometry"))
            if not parts:
                unrouted += 1
                continue
            status = (p.get("Status") or "").strip().lower()
            name = (p.get("PipelineName") or "").strip()
            seg = (p.get("SegmentName") or "").strip()
            length = _num(p.get("LengthMergedKm")) or _num(p.get("LengthKnownKm")) \
                or _num(p.get("LengthEstimateKm"))
            length_note = None
            if pid in PIPE_LENGTH_FIX:
                length, length_note = PIPE_LENGTH_FIX[pid]
                fixed += 1
            else:
                known, est = _num(p.get("LengthKnownKm")), _num(p.get("LengthEstimateKm"))
                if known and est and not 1 / 3 <= known / est <= 3:
                    print(f"  ? {pid} {name} {seg}: stated {known:,.0f} km, GEM's estimate {est:,.0f} km")
            if p.get("LastUpdated"):
                updated.append(str(p["LastUpdated"])[:10])
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
                    "length_km": length,
                    "length_note": length_note,
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
        print(f"     {n_af:,} {REGION.adj} segments in {tracker.upper()}")
    print(f"  {unrouted:,} {REGION.adj} segments have no usable route and are not drawn "
          f"({dropped_by_hand} of them by hand: a published route that is not the pipeline); "
          f"{fixed} length(s) corrected from PIPE_LENGTH_FIX")
    out = write_layer("gem_oil_gas_pipelines", feats)
    # "data as of" is the newest record update in the two files, not the
    # download day: GEM's map files carry no release date of their own
    newest = max((d for d in updated if re.match(r"\d{4}-\d\d-\d\d$", d)), default=None)
    update_meta("pipelines", fetched=today(), fresh=fmt_date(newest) if newest else None,
                release=" · ".join(releases), records=len(feats), unrouted=unrouted,
                length_fixes=fixed, route_drops=dropped_by_hand)
    return out


# ------------------------------------------------ TeleGeography (submarine cables)

# The Submarine Cable Map's own JSON API. Undocumented but stable for years;
# every endpoint here was tested live on 2026-09-18. Cable routes come as one
# GeoJSON, landing points as another, and the per-cable detail (owners,
# suppliers, ready-for-service year, planned flag, landing points with
# country) as one small JSON per cable. Licence: TeleGeography puts its maps,
# map URLs and screen captures under CC BY-SA 4.0, attribution "TeleGeography"
# (www2.telegeography.com/cite-telegeography-map), but says its underlying
# databases are for paying subscribers and sells the map's JSON under an
# annual licence (its submarine cable FAQ, checked 14 Oct 2026). The site
# therefore draws the routes and cards from this feed and does not publish
# the layer as a download.
TG_API = "https://www.submarinecablemap.com/api/v3"
# TeleGeography's own spellings for the region's countries and islands -> ISO
# 3166-1 (region.py). The cable detail carries a country per landing point;
# landing-point names read "City, Country" with commas inside some countries
# ("Congo, Dem. Rep."), so the fallback matches by suffix.
TG_ISO = REGION.tg_iso


def _route_km(parts):
    """Great-circle length of a route's parts, in km."""
    import math
    total = 0.0
    for part in parts:
        for (x0, y0, *_), (x1, y1, *_) in zip(part, part[1:]):
            p0, p1, dl = math.radians(y0), math.radians(y1), math.radians(x1 - x0)
            a = math.sin((p1 - p0) / 2) ** 2 + math.cos(p0) * math.cos(p1) * math.sin(dl / 2) ** 2
            total += 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))
    return total


def _tg_country(name):
    for c in sorted(TG_ISO, key=len, reverse=True):
        if name.endswith(", " + c):
            return c
    return None


def fetch_cables(pause=0.1):
    """Every cable with at least one landing point in the region.

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
            print(f"  … {i}/{len(ids)} cables, {len(feats)} {REGION.adj} so far")
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
            print(f"  ! {cid}: {REGION.adj} landing but no route geometry; skipped")
            continue
        planned = bool(d.get("is_planned"))
        rfs = d.get("rfs_year")
        # TeleGeography has two states, planned and in service. A planned
        # cable due by the end of next year (the fetch year + 1) is being
        # manufactured or laid; one further out is a record of intent.
        # Documented in the Methodology.
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
                # TeleGeography leaves the length blank for a few systems
                # (Umoja, FEA, ReuNION…): the drawn route's length stands in
                # for ranking and is labelled an estimate wherever it shows
                "length_km_est": None if _num((d.get("length") or "").replace("km", ""))
                                 else round(_route_km(parts)),
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
    # landings count a cable at a point (282 in Oct 2026); landing sites count
    # each point once however many cables come ashore there (127)
    update_meta("cables", fetched=today(), fresh=None, records=len(feats),
                landing_points=sum(len(f["properties"]["landing_points"]) for f in feats),
                landing_sites=len({lp["id"] for f in feats for lp in f["properties"]["landing_points"]}),
                length_estimated=sum(1 for f in feats if f["properties"]["length_km_est"]))
    return out


# ------------------------------------------------- AidData (Chinese official finance)

# AidData's China's Global Loans and Grants Dataset 1.0 (CLG-Global 1.0,
# November 2025): every known project supported by an official loan or grant
# from China, commitments 2000-2023 and implementation followed to 2025, in
# constant 2023 US dollars, one Excel workbook (ODC-By). It succeeds the Global
# Chinese Development Finance Dataset 3.0 (GCDF 3.0, 2000-2021) and keeps its
# record IDs, but ships no location fields, and AidData has published no
# geospatial companion for it yet. So GCDF 3.0 is still read, for locations
# only: its precision field and ADM1/ADM2 centroids, and the footprints of its
# Geospatial companion (GeoGCDF v3, on GitHub), one GeoJSON per project, a
# MultiPolygon in which points and lines were buffered by about a metre and
# dissolved, so a road arrives as a two-metre-wide sliver (ODbL, because the
# geometry is OSM's). The project pages at china.aiddata.org now show the CLG
# record behind each ID, with its sources.
AIDDATA_CLG_ZIP = "https://docs.aiddata.org/ad4/datasets/AidDatas_CLG_Global_Dataset_v1.0.zip"
AIDDATA_CLG_SHEET = "CLG-Global 1.0_Records"
CHINA_BASE_YEAR = 2023            # CLG 1.0's constant dollars
AIDDATA_ZIP = ("https://docs.aiddata.org/ad4/datasets/"
               "AidDatas_Global_Chinese_Development_Finance_Dataset_Version_3_0.zip")
AIDDATA_SHEET = "GCDF_3.0"
GEOGCDF_RAW = "https://raw.githubusercontent.com/aiddata/gcdf-geospatial-data/main/latest"
GEOGCDF_API = "https://api.github.com/repos/aiddata/gcdf-geospatial-data/releases/latest"
# the workbooks and footprints are shared by every edition
AIDDATA_CACHE = ROOT_DATA / ".aiddata_cache"
# AidData records the recipient as an ISO-3 code; the rest of the site speaks ISO-2.
ISO3_TO_ISO2 = REGION.iso3
# AidData's six statuses onto the shared five. A pledge (letter of intent,
# MoU, announcement) is a record of intent, like GEM "announced"; a commitment
# is a signed, binding agreement not yet in implementation, like AfDB's
# post-approval stage; "Completion" is the asset in use.
CHINA_STATUS = {
    "Pipeline: Pledge": ANNOUNCED,
    "Pipeline: Commitment": APPROVED,
    "Implementation": BUILDING,
    "Completion": OPERATING,
    "Suspended": STALLED,
    "Cancelled": STALLED,
}
# OECD three-digit sector codes onto the site's sector vocabulary. Beyond the
# sectors the IATI filter keeps, social ones appear here because AidData flags
# hospitals, schools, stadiums and ministry buildings as infrastructure, and
# Chinese finance built a great many of them.
CHINA_SECTOR = {
    110: "education", 120: "health", 130: "health", 140: "water", 150: "government",
    160: "social", 210: "transport", 220: "ict", 230: "energy", 310: "agriculture",
    320: "industry", 330: "trade", 410: "environment",
}
# a footprint ring narrower than ~20 m is a buffered OSM node: the marker says it all
FOOTPRINT_MIN_DEG = 0.0002
FOOTPRINT_TOL = 0.0004          # Douglas-Peucker, ~45 m; the builds thin further
FOOTPRINT_MAX_VERTICES = 2000
# a footprint whose interior point falls outside this window is a mislinked
# OSM feature (one buyer's credit sits in Colombia); the record falls back to
# its country's centre
AFRICA_WINDOW = REGION.aiddata_window


def read_xlsx_sheet(path, sheet):
    """Rows of one worksheet as lists (str, int, float or None), from the
    standard library alone: an .xlsx is a zip of XML. Dates arrive as Excel
    serial numbers, which is fine here because only years are used."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    z = zipfile.ZipFile(path)
    rels = {r.get("Id"): r.get("Target")
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    target = None
    for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(ns + "sheet"):
        if sh.get("name") == sheet:
            target = rels[sh.get(rns + "id")].lstrip("/")
    if not target:
        raise KeyError(f"no sheet {sheet!r} in {path}")
    if not target.startswith("xl/"):
        target = "xl/" + target
    strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(ns + "si"):
            strings.append("".join(t.text or "" for t in si.iter(ns + "t")))

    def col(ref):
        n = 0
        for ch in ref:
            if not ch.isalpha():
                break
            n = n * 26 + ord(ch.upper()) - 64
        return n - 1

    with z.open(target) as f:
        row = []
        for ev, el in ET.iterparse(f, events=("start", "end")):
            if ev == "start" and el.tag == ns + "row":
                row = []
            elif ev == "end" and el.tag == ns + "c":
                i = col(el.get("r", ""))
                while len(row) < i:
                    row.append(None)
                t, v = el.get("t"), el.find(ns + "v")
                if t == "s":
                    val = strings[int(v.text)] if v is not None else None
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in el.iter(ns + "t"))
                elif v is None or v.text is None:
                    val = None
                elif t in ("str", "e"):
                    val = v.text
                else:
                    try:
                        val = float(v.text)
                        if val.is_integer() and "." not in v.text and "E" not in v.text.upper():
                            val = int(val)
                    except ValueError:
                        val = v.text
                row.append(val)
                el.clear()
            elif ev == "end" and el.tag == ns + "row":
                yield row
                el.clear()


_COUNTRY_POLYS = None


def _country_polys():
    """(iso, bbox, polygon) for every country of the region in the dashboard basemap."""
    global _COUNTRY_POLYS
    if _COUNTRY_POLYS is None:
        bm = DATA / REGION.basemap_110
        if not bm.exists():
            raise SystemExit(f"{bm.relative_to(ROOT_DATA.parent)} needed to place records; run fetch_basemap.py first")
        _COUNTRY_POLYS = []
        for c in json.loads(bm.read_text())["countries"]:
            for poly in c["p"]:
                xs = [q[0] for q in poly[0]]
                ys = [q[1] for q in poly[0]]
                _COUNTRY_POLYS.append((c["iso"], (min(xs), min(ys), max(xs), max(ys)), poly))
    return _COUNTRY_POLYS


def _country_at(lon, lat):
    for iso, (x0, y0, x1, y1), poly in _country_polys():
        if x0 <= lon <= x1 and y0 <= lat <= y1 and _ring(lon, lat, poly[0]) \
                and not any(_ring(lon, lat, h) for h in poly[1:]):
            return iso
    return None


def _ring_centroid(ring):
    """Area centroid of a closed ring (shoelace); the mean vertex if degenerate."""
    a = cx = cy = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i][:2]
        x1, y1 = ring[(i + 1) % n][:2]
        w = x0 * y1 - x1 * y0
        a += w
        cx += (x0 + x1) * w
        cy += (y0 + y1) * w
    if abs(a) < 1e-14:
        return sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n
    return cx / (3 * a), cy / (3 * a)


def _interior_point(ring):
    """A point inside the ring: its centroid when that lies inside (a building,
    a district), otherwise the middle of the longest inside span along the
    centroid's latitude (a horseshoe-shaped country), otherwise the vertex
    nearest the centroid (a thin road sliver, where every vertex is on the road)."""
    cx, cy = _ring_centroid(ring)
    if _ring(cx, cy, ring):
        return cx, cy
    xs = []
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i][:2]
        x1, y1 = ring[(i + 1) % n][:2]
        if (y0 > cy) != (y1 > cy):
            xs.append(x0 + (cy - y0) * (x1 - x0) / (y1 - y0))
    xs.sort()
    best, bw = None, 0.0
    for a, b in zip(xs[0::2], xs[1::2]):
        if b - a > bw:
            best, bw = (a + b) / 2, b - a
    if best is not None and bw > 0.02:
        return best, cy
    v = min(ring, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    return v[0], v[1]


def _country_centre(iso):
    """Interior point of a country's largest polygon, for records AidData
    places no finer than the country."""
    best, ba = None, -1.0
    for i, _, poly in _country_polys():
        if i != iso:
            continue
        a = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly[0], poly[0][1:] + poly[0][:1])))
        if a > ba:
            best, ba = poly[0], a
    return _interior_point(best) if best else (None, None)


def _footprint(polys):
    """The exterior rings of a GeoGCDF MultiPolygon, simplified for the map.
    Buffered points collapse to nothing and are dropped; a buffered road stays
    as a closed sliver, which the page strokes, so it reads as a line."""
    tol = FOOTPRINT_TOL
    while True:
        rings, total = [], 0
        for poly in polys:
            ring = [tuple(p[:2]) for p in poly[0]]
            xs, ys = [p[0] for p in ring], [p[1] for p in ring]
            if max(xs) - min(xs) < FOOTPRINT_MIN_DEG and max(ys) - min(ys) < FOOTPRINT_MIN_DEG:
                continue
            q = []
            for x, y in dp(ring, tol):
                v = [round(x, 5), round(y, 5)]
                if not q or q[-1] != v:
                    q.append(v)
            if len(q) >= 4:
                rings.append(q)
                total += len(q)
        if total <= FOOTPRINT_MAX_VERTICES or tol > 0.02:
            return rings
        tol *= 2


def _geogcdf(pid, cache, retries=3):
    """One project's GeoGCDF feature, cached on disk; None when GitHub has none."""
    path = cache / f"{pid}.geojson"
    if path.exists():
        return json.loads(path.read_text()) if path.stat().st_size else None
    for attempt in range(retries):
        try:
            raw = get(f"{GEOGCDF_RAW}/geojsons/{pid}.geojson", timeout=120)
            path.write_bytes(raw)
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                path.write_bytes(b"")
                return None
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))
        except Exception:                                     # noqa: BLE001
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def _clean(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s[:n] or None


def _pipe(s, n, sep="; "):
    parts = [p.strip() for p in str(s or "").split("|") if p.strip()]
    return _clean(sep.join(dict.fromkeys(parts)), n)


def _aiddata_zip(url, name):
    """A cached AidData zip: downloaded once into the cache, read from there
    after. Delete the file to force a fresh download."""
    path = AIDDATA_CACHE / name
    if not path.exists() or not path.stat().st_size:
        print(f"AidData  downloading {url.rsplit('/', 1)[-1]} …")
        path.write_bytes(get(url, timeout=900))
    return zipfile.ZipFile(path)


def _xlsx_from(z, name):
    """Unpack the zip's workbook into the cache (once) and return its path."""
    xlsx = [n for n in z.namelist() if n.endswith(".xlsx") and "__MACOSX" not in n][0]
    path = AIDDATA_CACHE / name
    if not path.exists() or path.stat().st_size != z.getinfo(xlsx).file_size:
        path.write_bytes(z.read(xlsx))
    return path


def fetch_aiddata(workers=8):
    """One record per Chinese official commitment to a country of the region in an
    infrastructure sector, from AidData's China's Global Loans and Grants
    Dataset 1.0 (commitments 2000-2023), placed as precisely as AidData can.

    Kept: every non-umbrella record with a status of Pipeline: Commitment,
    Implementation, Completion, Suspended or Cancelled that AidData flags as
    infrastructure (building, extending or maintaining a physical structure).
    Left out: umbrella agreements (their money reappears in the projects
    under them), pledges (MoUs and letters of intent, which AidData excludes
    from aggregates, so the layer has no "announced" records), everything
    AidData does not flag as physical infrastructure (cash, equipment and
    vehicle donations, scholarships, most oil-backed credit lines to state
    companies) and the loans that buy a stake (M_A). An infrastructure loan
    AidData marks commodity-backed is kept and counted in meta. Suspended and
    cancelled commitments stay on the map but out of the totals, which is
    exactly what AidData's Recommended_for_Aggregates does to the kept set.

    Location: CLG 1.0 ships no location fields and has no geospatial
    companion yet, but keeps GCDF 3.0's record IDs. A record carried over
    from GCDF 3.0 takes that release's location (its precision field, its
    ADM1/ADM2 centroids and the GeoGCDF v3 footprint); a record new in CLG
    sits at its country's centre, flagged as new."""
    AIDDATA_CACHE.mkdir(parents=True, exist_ok=True)
    zc = _aiddata_zip(AIDDATA_CLG_ZIP, "clg1.zip")
    clg_path = _xlsx_from(zc, "clg1.xlsx")
    zg = _aiddata_zip(AIDDATA_ZIP, "gcdf3.zip")
    gcdf_path = _xlsx_from(zg, "gcdf3.xlsx")

    # GCDF 3.0, read for locations only: precision and footprint flags by ID,
    # and the ADM1/ADM2 centroids it publishes beside the workbook
    old = {}
    g = read_xlsx_sheet(gcdf_path, AIDDATA_SHEET)
    gh = {str(h): i for i, h in enumerate(next(g))}
    gcol = lambda r, name: r[gh[name]] if gh[name] < len(r) else None  # noqa: E731
    for r in g:
        if r and r[0] is not None:
            old[int(r[0])] = (gcol(r, "Geospatial Feature Available"),
                              gcol(r, "Geographic Level of Precision Available"))
    adm = {}
    for level in ("ADM2", "ADM1"):        # finest first: a project keeps its first hit
        for n in zg.namelist():
            if n.endswith(f"GCDF_3.0_{level}_Locations.csv") and "__MACOSX" not in n:
                for r in csv.DictReader(io.StringIO(zg.read(n).decode("utf-8-sig"))):
                    adm.setdefault(r["id"], []).append(r)
    try:
        geo_release = json.loads(get(GEOGCDF_API, timeout=60)).get("tag_name")
    except Exception:                                         # noqa: BLE001
        geo_release = None
    geo_version = get(f"{GEOGCDF_RAW}/version.txt", timeout=60).decode().strip()
    cache = AIDDATA_CACHE / geo_version
    cache.mkdir(exist_ok=True)
    print(f"AidData  CLG-Global 1.0 records; locations from GCDF 3.0 and GeoGCDF {geo_release or ''} ({geo_version})")

    rows = read_xlsx_sheet(clg_path, AIDDATA_CLG_SHEET)
    hdr = [str(h) for h in next(rows)]
    ix = {h: i for i, h in enumerate(hdr)}
    col = lambda r, name: r[ix[name]] if ix[name] < len(r) else None  # noqa: E731
    keep, skipped = [], {"pledge": 0, "umbrella": 0, "not_infra": 0, "acquisition": 0}
    for r in rows:
        if not r or r[0] is None or col(r, "Region_of_Activity") not in REGION.aiddata_regions:
            continue
        # a region that is part of AidData's (Southeast Asia within "Asia"):
        # the recipient must be one of its countries, or the region itself
        if REGION.aiddata_by_iso3 and (col(r, "Country_of_Activity_ISO3") or "") not in ISO3_TO_ISO2 \
                and str(col(r, "Country_of_Activity") or "") not in ("Asia, regional",):
            continue
        if col(r, "Umbrella") == "Yes":
            skipped["umbrella"] += 1
            continue
        status = col(r, "Status")
        if status == "Pipeline: Pledge":
            skipped["pledge"] += 1
            continue
        if col(r, "Infrastructure") != "Yes":
            skipped["not_infra"] += 1
            continue
        # a loan to buy a stake in a mine or an LNG vessel builds nothing,
        # whatever the sector of what it buys: AidData flags those M_A
        if col(r, "M_A") == "Yes":
            skipped["acquisition"] += 1
            continue
        keep.append(r)
    print(f"  {len(keep):,} {REGION.adj} infrastructure commitments "
          f"(left out: {skipped['umbrella']:,} umbrella agreements, {skipped['pledge']:,} pledges, "
          f"{skipped['not_infra']:,} not physical infrastructure, {skipped['acquisition']:,} acquisitions)")
    # the kept set's stalled records are exactly the ones AidData's own
    # Recommended_for_Aggregates leaves out
    rfa_no = {int(col(r, "AidData_Record_ID")) for r in keep if col(r, "Recommended_for_Aggregates") != "Yes"}
    stalled = {int(col(r, "AidData_Record_ID")) for r in keep if CHINA_STATUS.get(col(r, "Status")) == STALLED}
    if rfa_no != stalled:
        print(f"  ! Recommended_for_Aggregates and the stalled statuses disagree on "
              f"{len(rfa_no ^ stalled)} record(s); totals follow the statuses")

    ids = [int(col(r, "AidData_Record_ID")) for r in keep]
    with_geo = [i for i in ids if i in old and old[i][0] == "Yes"]
    print(f"  {sum(1 for i in ids if i in old):,} carried over from GCDF 3.0, "
          f"{sum(1 for i in ids if i not in old):,} new in CLG 1.0; fetching {len(with_geo):,} GeoGCDF "
          f"footprints ({workers} at a time, cached in {cache.relative_to(DATA.parent)})")
    feats_geo, failed = {}, 0
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(_geogcdf, pid, cache): pid for pid in with_geo}
        for i, fut in enumerate(concurrent.futures.as_completed(futs), 1):
            pid = futs[fut]
            try:
                feats_geo[pid] = fut.result()
            except Exception as e:                            # noqa: BLE001
                failed += 1
                print(f"  ! {pid}: {e}")
            if i % 500 == 0:
                print(f"  … {i}/{len(with_geo)}")
    if failed:
        print(f"  ! {failed} footprint(s) could not be read")

    feats, n_fp, n_prec, n_approx, n_country, n_new, unlocated, mislinked = [], 0, 0, 0, 0, 0, 0, 0
    n_cb, cb_usd = 0, 0.0
    for r in keep:
        pid = int(col(r, "AidData_Record_ID"))
        iso = ISO3_TO_ISO2.get(col(r, "Country_of_Activity_ISO3") or "")
        new = pid not in old
        level = None if new else old[pid][1]
        geom, lon, lat, place, osm_links, n_feat = None, None, None, None, None, None
        bad_geo = False                  # a footprint outside the region: its ADM rows are as wrong
        fc = feats_geo.get(pid)
        if fc and fc.get("features"):
            f0 = fc["features"][0]
            g = f0.get("geometry") or {}
            polys = g.get("coordinates") if g.get("type") == "MultiPolygon" else \
                [g.get("coordinates")] if g.get("type") == "Polygon" else []
            polys = [p for p in polys if p and len(p[0]) >= 4]
            if polys:
                largest = max(polys, key=lambda p: ring_area_deg(p[0]))
                lon, lat = _interior_point([tuple(q[:2]) for q in largest[0]])
                x0, y0, x1, y1 = AFRICA_WINDOW
                if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                    print(f"  ! {pid}: footprint at {lon:.2f}, {lat:.2f} is not in {REGION.name}; "
                          f"placed at the country's centre instead")
                    lon = lat = None
                    bad_geo = True
                    mislinked += 1
                else:
                    p0 = f0.get("properties") or {}
                    osm_links = [u for u in str(p0.get("osm_links") or "").split(",") if u.strip()][:4] or None
                    n_feat = p0.get("feature_count")
                    if level == "Precise":
                        rings = _footprint(polys)
                        if rings:
                            geom = {"type": "MultiLineString", "coordinates": rings}
                            n_fp += 1
        if lon is None and not bad_geo and not new and str(pid) in adm:
            best = max(adm[str(pid)], key=lambda a: float(a.get("intersection_ratio") or 0))
            lon, lat = float(best["centroid_longitude"]), float(best["centroid_latitude"])
            level = level if level in ("Admin Level", "Within 5km") else "Admin Level"
            others = len(adm[str(pid)]) - 1
            place = best["shapeName"] + (f" +{others}" if others > 0 else "")
        elif not new and str(pid) in adm and level != "Precise" and not bad_geo:
            best = max(adm[str(pid)], key=lambda a: float(a.get("intersection_ratio") or 0))
            others = len(adm[str(pid)]) - 1
            place = best["shapeName"] + (f" +{others}" if others > 0 else "")
        if lon is None:
            if not iso:
                unlocated += 1
                continue
            # the 1:110m basemap has no polygon for the island states
            lon, lat = ISLAND_POINT.get(iso) or _country_centre(iso)
            place = None
            if lon is None:
                unlocated += 1
                continue
            level = "Country"
        if level == "Precise":
            precision, n_prec = "precise", n_prec + 1
        elif level == "Within 5km":
            precision, n_approx = "within_5km", n_approx + 1
        elif level == "Country":
            precision, n_country = "country", n_country + 1
            n_new += new
        else:
            precision, n_approx = "admin", n_approx + 1
        if not iso:
            iso = _country_at(lon, lat)      # "Africa, regional" projects with a footprint
            if not iso:                      # a regional project located outside the region
                unlocated += 1
                continue
        amount = col(r, "Adjusted_Amount_Constant_USD_2023")
        if amount is None:
            amount = col(r, "Amount_Constant_USD_2023")
        nominal = col(r, "Adjusted_Amount_Nominal_USD")
        if nominal is None:
            nominal = col(r, "Amount_Nominal_USD")
        try:
            sector_code = int(col(r, "Sector_Code") or 0)
        except (TypeError, ValueError):
            sector_code = 0
        yr = lambda name: int(col(r, name)) if isinstance(col(r, name), (int, float)) else None  # noqa: E731
        num = lambda name: float(col(r, name)) if isinstance(col(r, name), (int, float)) else None  # noqa: E731
        status = col(r, "Status")
        amount = round(float(amount), 2) if isinstance(amount, (int, float)) else None
        # a suspended or cancelled commitment stays on the map but out of the
        # totals, as AidData's own Recommended_for_Aggregates leaves it out
        withdrawn = CHINA_STATUS.get(status) == STALLED and amount is not None
        backed = col(r, "Commodity_backed") == "Yes"
        n_cb += backed
        cb_usd += (amount or 0) if backed and not withdrawn else 0
        feats.append({
            "type": "Feature",
            "geometry": geom or {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": {
                "source": "AidData",
                "layer": "china",
                "aiddata_id": pid,
                "name": _clean(col(r, "Title"), 200),
                "country": iso,
                "recipient": _clean(col(r, "Country_of_Activity"), 60),
                "lon": round(lon, 5), "lat": round(lat, 5),
                "geo_precision": precision,
                "new_in_clg": new or None,
                "place": _clean(place, 60),
                "osm_links": osm_links,
                "feature_count": n_feat,
                "raw_status": status,
                "dash_status": CHINA_STATUS.get(status),
                "sector_code": sector_code or None,
                "sector": CHINA_SECTOR.get(sector_code, "other"),
                "sector_name": _clean(col(r, "Sector_Name"), 60),
                "infrastructure": col(r, "Infrastructure") == "Yes",
                "intent": _clean(col(r, "Intent"), 20),
                "flow_type": _clean(col(r, "Flow_Type"), 60),
                "flow_simple": _clean(col(r, "Flow_Type_Simplified"), 20),
                "flow_class": _clean(col(r, "Flow_Class"), 30),
                "funders": _pipe(col(r, "Funding_Agencies"), 400),
                "funder_types": _pipe(col(r, "Funding_Agencies_Type"), 200),
                "implementers": _pipe(col(r, "Implementing_Agencies"), 400),
                "cofinanced": col(r, "Cofinanced") == "Yes",
                "cofinanciers": _pipe(col(r, "Cofinancing_Agencies"), 200),
                # constant dollars of meta.china.base_year (2023 for CLG 1.0)
                "amount_usd_const": None if withdrawn else amount,
                "amount_usd_const_published": amount if withdrawn else None,
                "counted_note": f"{status.lower()}, so not counted in totals" if withdrawn else None,
                "commodity_backed": backed or None,
                "amount_nominal_usd": round(float(nominal), 2) if isinstance(nominal, (int, float)) else None,
                "amount_estimated": col(r, "Amount_Estimated") == "Yes",
                "commitment_year": yr("Commitment_Year"),
                "start_year": yr("Implementation_Start_Year"),
                "completion_year": yr("Completion_Year"),
                "maturity_years": num("Maturity"),
                # the rate at signing: a fixed rate, or a variable one's
                # reference rate plus margin on the commitment date
                "interest_rate": num("Interest_at_T0"),
                "grace_years": num("Grace_Period"),
                "grant_element": num("Grant_Element_OECD_Grant_Equiv"),
                "financial_distress": col(r, "Financial_Distress") == "Yes",
                "location_narrative": _clean(col(r, "Location_Narrative"), 240),
                "url": f"https://china.aiddata.org/projects/{pid}/",
            },
        })
    years = [f["properties"]["commitment_year"] for f in feats if f["properties"]["commitment_year"]]
    print(f"  {n_fp:,} footprints drawn · {n_prec:,} precise, {n_approx:,} approximate (5 km or "
          f"administrative), {n_country:,} at the country's centre ({n_new:,} of them new in CLG 1.0) · "
          f"{unlocated:,} regional records without a location dropped · {mislinked} footprint(s) outside {REGION.name} ignored")
    out = write_layer("aiddata_china_finance", feats)
    update_meta("china", fetched=today(), fresh="Nov 2025 · to 2023",
                release=f"CLG-Global 1.0 · locations from GCDF 3.0 and GeoGCDF {geo_release or geo_version}",
                base_year=CHINA_BASE_YEAR, years=[min(years), max(years)] if years else None,
                records=len(feats), footprints=n_fp, precise=n_prec, approximate=n_approx,
                country_level=n_country, new_records=n_new, unlocated=unlocated, mislinked=mislinked,
                umbrella=skipped["umbrella"], pledges=skipped["pledge"],
                not_infrastructure=skipped["not_infra"], acquisitions=skipped["acquisition"],
                commodity_backed=n_cb, commodity_backed_usd=round(cb_usd))
    return out


def ring_area_deg(ring):
    a = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i][:2]
        x1, y1 = ring[(i + 1) % n][:2]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


# ------------------------------------------------- EU institutions (finance)

# The European Union's own money in Africa, from the two institutions that
# publish it project by project to IATI: the European Commission (DG INTPA
# for sub-Saharan Africa and the continental programmes, DG NEAR for the five
# North African neighbours) and the European Investment Bank. Member states'
# agencies (AFD, KfW, Enabel…) are national, not EU, and are not here.
#
# The Commission publishes two levels in the same per-country files:
# financing decisions (hierarchy 1: the action the Commission adopted, with
# its whole envelope) and the contracts under them (hierarchy 2: a grant to
# an NGO, a delegation agreement with the EIB or KfW, a works contract),
# linked by <related-activity type="1">. Money sits at both levels, so one
# record is a contract, and a decision is kept only when none of its
# contracts is in the set: an action still in the pipeline is one announced
# record, and nothing is counted twice. Locations carry no exactness: a point
# is either the Commission's default for the country (one point per country,
# used by most of its activities; "AFRICA", in Chad, for the regional files)
# or a named place.
#
# The EIB publishes one global file with no locations at all, and repeats its
# commitment transaction once per contract or tranche record (same date,
# same value, four to seven times for one loan): the signed amount is the sum
# of the distinct ones, which matches the Bank's project pages. Sectors are
# the Bank's own NACE-like codes (vocabulary 99), mapped below to the same
# buckets the DAC filter yields for the other lenders.
# the publishers and files for the region (region.py): for Africa INTPA's
# country files and its 289, 298 and 1027–1030 regional files, NEAR's five
# North African neighbours and 189, and the EIB's global file; for Southeast
# Asia INTPA's country files and its 789 and 798 regional files, and the EIB
EU_PUBLISHERS = REGION.eu_publishers
# the DAC regional codes INTPA publishes as files of their own: for Africa
# North of Sahara, South of Sahara, Africa regional and the four sub-regions
EU_REGIONS = REGION.eu_regions
EU_AFRICA_POINT = REGION.eu_region_point   # lon, lat: the Commission's point for region-wide activities
# island states the coarse basemap has no polygon for: a point on the main island
ISLAND_POINT = REGION.island_point
# EIB sector codes: the two leading digits decide. Everything else (global
# loans and SME credit lines, funds, health, education, agriculture, finance)
# is left out, as the DAC filter leaves it out for the other lenders.
EIB_SECTOR = [((5, 9), "industry"), ((10, 33), "industry"), ((35, 35), "energy"), ((36, 38), "water"),
              ((39, 39), "environment"), ((41, 43), "industry"), ((49, 52), "transport"), ((60, 63), "ict")]
# EIB operations that are not infrastructure although their sector codes say
# so: investments in funds (the codes are the fund's target sectors) and
# framework loans that are credit lines to banks. Left out, as the DAC filter
# leaves funds and credit lines out for the other lenders. By EIB project
# number; each is https://www.eib.org/en/projects/all/<number>. Checked
# 14 Oct 2026 against the Bank's project pages.
EIB_NOT_INFRA = {
    "20230942": "fund: Global Gateway Copenhagen Growth Markets Fund II",
    "20210726": "fund: African Infrastructure Investment Fund 4",
    "20210671": "fund: Alcazar Energy Partners II",
    "20220074": "fund: SunFunder Gigaton Clean Energy SME Fund",
    "20220585": "fund: Pembani Remgro Infrastructure Fund II",
    "20230725": "fund: LeapFrog Asia and Africa Climate Transition Fund",
    "20200816": "fund: Emerging Market Climate Action Fund (EMCAF)",
    "20210191": "fund: EMCAF, junior participation",
    "20200085": "fund: The Urban Resilience Fund (TURF) B",
    "20200800": "fund: The Urban Resilience Fund (TURF) B, local-currency facility",
    "20230795": "fund: ACP Infrastructure Climate Resilient Fund",
    "20220394": "fund: Evolution III",
    "20170177": "fund: Evolution II",
    "20190120": "fund: Metier Sustainable Capital Fund II",
    "20220159": "fund: ACRE Export Finance Fund I",
    "20210690": "fund: Eiffel Energy Transition Africa Fund",
    "20170404": "fund: Denham International Power Fund",
    "20170638": "fund: Arch Africa Renewable Power Fund",
    "20190170": "fund: Arch Cold Chain Solutions East Africa Fund",
    "20140518": "fund: Meridiam Infrastructure Africa Fund",
    "20180638": "fund: Meridiam Infrastructure Africa Fund, top-up",
    "20180476": "fund: responsAbility Access to Clean Power Fund",
    "20190011": "fund: responsAbility Access to Clean Power Fund, local-currency facility",
    "20230258": "fund: Amethis Africa Fund III",
    "20210485": "fund: AfriGreen Debt Fund",
    "20190307": "fund: Green for Growth Fund IV",
    "20160492": "fund: Green for Growth Fund III",
    "20170817": "fund: Green for Growth Fund, local-currency facility",
    "20160182": "fund: Green for Growth Fund, CAMENA",
    "20160898": "fund: International Housing Solutions Fund II",
    "20190782": "fund: Convergence Partners Digital Fund III",
    "20140272": "fund: Agri-Vie Fund II",
    "20170443": "fund: Africa Food Security Fund",
    "20200522": "fund: Water Access Acceleration Fund",
    "20210788": "fund: SSA Sustainable Energy Platform",
    "20230046": "fund: Mirova Gigaton Fund, local-currency facility",
    "20230334": "fund: Seedstars Africa Ventures 1",
    "20200199": "fund: DWS Universal Green Energy Access Programme",
    "20220361": "credit line: EBID ECOWAS Climate Action framework loan",
    "20220180": "credit line: Afreximbank Africa Health Resilience framework loan",
    "20220792": "credit line: BRD Green Finance framework loan",
    "20130648": "credit line: PAMIGA, through microfinance institutions",
}
# EIB operations whose money is not the Bank's (participating-org role 1):
# the Commission's blending grants, which the Commission publishes again as
# its own contracts with the EIB, and a member state's agency (AECID, Spain),
# which is national money like AFD's or KfW's.
EIB_OTHER_FUNDERS = {"MS-EC", "AECID"}
# implementing organisations the Commission names only by their IATI ref
EU_IMPL_REF = {"XM-DAC-42004": "European Investment Bank"}
EU_INSTRUMENT = {"110": "grant", "111": "grant", "210": "grant", "411": "loan", "412": "loan", "421": "loan",
                 "510": "equity", "511": "equity", "512": "equity", "520": "equity"}
EU_AID_TYPE = {"A01": "general budget support", "A02": "sector budget support", "B01": "core contribution",
               "B02": "core contribution", "B03": "contribution to a programme or fund",
               "B04": "basket fund", "C01": "project-type intervention", "D01": "donor personnel",
               "D02": "technical assistance", "E01": "scholarships", "F01": "debt relief",
               "G01": "administrative costs", "H01": "development awareness", "H02": "refugees in donor country"}


def _narr(e, path):
    x = e.find(path)
    return (x.text or "").strip() if x is not None and x.text else None


def _eib_bucket(code):
    try:
        n = int((code or "")[:2])
    except ValueError:
        return None
    for (lo, hi), bucket in EIB_SECTOR:
        if lo <= n <= hi:
            return bucket
    return None


def _clean_place(name, iso):
    """"KE - Tharaka Nithi county" -> "Tharaka Nithi county"; a contract
    number ("KE - 419705-4"), a bare country or "AFRICA" -> None."""
    s = re.sub(r"^[A-Z0-9]{2,3}\s*-\s*", "", (name or "").strip())
    s = re.sub(r"^[A-Z]{1,4}_", "", s)                           # "AA_Ethiopia"
    if not s or s.upper() in ("AFRICA", REGION.name.upper(), "ACTION LOCATION", "N/A") or s.upper() == (iso or "").upper():
        return None
    if re.fullmatch(r"[\dA-Z_\-\. ]*\d[\dA-Z_\-\. ]*", s):      # a code, not a place
        return None
    if s.title() in REGION_NAMES or len(s) > 40:                 # the country itself, or a title
        return None
    if s.isupper() and len(s) > 3:
        s = s.title()
    return s[:60]


def _eu_activity(act, conf):
    """One parsed activity, or None when it is not infrastructure in the region."""
    pub = conf["pub"]
    share = 1.0              # the infrastructure share, by the publisher's sector percentages
    iid0 = _narr(act, "iati-identifier") or ""
    excluded = None
    if pub == "EIB":
        m = re.match(r"XM-DAC-918-3-(\d{8})", iid0)
        funders = {(_narr(po, "narrative") or "").strip() for po in act.iter("participating-org")
                   if po.get("role") == "1"}
        if m and m.group(1) in EIB_NOT_INFRA:
            excluded = "left_out"
        elif funders & EIB_OTHER_FUNDERS:
            excluded = "other_funder"
        codes = [(s.get("code") or "", _narr(s, "narrative"), _num(s.get("percentage")))
                 for s in act.iter("sector") if s.get("vocabulary") == "99"]
        buckets = [b for b in (_eib_bucket(c) for c, _, _ in codes) if b]
        if not buckets:
            return None
        # the largest infrastructure code names the sector
        main = max((c for c in codes if _eib_bucket(c[0])), key=lambda c: c[2] or 0)
        sector, sector_codes = _eib_bucket(main[0]), [c for c, _, _ in codes]
        sector_label = main[1]
        if sector_label:                        # the Bank's file carries cp1252 dashes
            sector_label = sector_label.replace("\x96", "–").replace("\x97", "—")
        total = sum(c[2] or 0 for c in codes)
        if total:
            share = min(1.0, sum(c[2] or 0 for c in codes if _eib_bucket(c[0])) / total)
    else:
        pct = [(s.get("code"), _num(s.get("percentage"))) for s in act.iter("sector")
               if s.get("code") and s.get("vocabulary") in (None, "1")]
        sector_codes = [c for c, _ in pct]
        if not any(c.startswith(IATI_INFRA_DAC) for c in sector_codes):
            return None
        total = sum(p or 0 for _, p in pct)
        if total:
            share = min(1.0, sum(p or 0 for c, p in pct if c.startswith(IATI_INFRA_DAC)) / total)
            weight = dict(pct)
            sector_codes = sorted(sector_codes, key=lambda c: (not c.startswith(IATI_INFRA_DAC), -(weight.get(c) or 0)))
        sector, sector_label = None, None       # the builder maps DAC codes

    countries = []
    for rc in act.iter("recipient-country"):
        try:
            pct = float(rc.get("percentage") or 100)
        except ValueError:
            pct = 100.0
        countries.append((rc.get("code"), pct))
    regions = [(rr.get("code"), _num(rr.get("percentage"))) for rr in act.iter("recipient-region")]
    african = [c for c in countries if c[0] in REGION_ISO]
    if not african and not ({r for r, _ in regions} & EU_REGIONS):
        return None
    if excluded:              # counted only once it is known to be the region's infrastructure
        return excluded
    iso = max(african, key=lambda c: c[1])[0] if african else None
    # the region's share, by the publisher's recipient percentages: an EIB
    # loan to IFAD is 50% Africa, 12% America and 38% Asia
    rec = [(c, p) for c, p in countries] + [(r, p if p is not None else 100.0) for r, p in regions]
    rec_total = sum(p for _, p in rec)
    africa_share = 1.0
    if rec_total and len(rec) > 1:
        africa_share = min(1.0, sum(p for c, p in rec if c in REGION_ISO or c in EU_REGIONS) / rec_total)
    regions = [r for r, _ in regions]

    st = act.find("activity-status")
    code = st.get("code") if st is not None else None
    if not IATI_STATUS.get(code):
        return None

    currency = act.get("default-currency") or "EUR"
    seen, commitment, disbursed, mixed, refs2 = set(), 0.0, 0.0, False, set()
    for tx in act.iter("transaction"):
        tt, v = tx.find("transaction-type"), tx.find("value")
        if tt is None or v is None or not v.text:
            continue
        try:
            amt = float(v.text)
        except ValueError:
            continue
        cur = v.get("currency") or currency
        if cur == "USD":
            amt, mixed = amt / EUR_USD, True
        elif cur != "EUR":
            mixed = True
            continue
        td = tx.find("transaction-date")
        key = (tt.get("code"), td.get("iso-date") if td is not None else None, v.text, cur)
        if pub == "EIB" and key in seen:        # the Bank's repeated tranche records
            continue
        seen.add(key)
        if tt.get("code") == "2":
            commitment += amt
            ref = tx.get("ref") or ""
            if ref.startswith(iid0 + "-"):       # the Commission prefixes each copy's own id
                ref = ref[len(iid0) + 1:]
            if ref:
                refs2.add(ref)
        elif tt.get("code") == "3":
            disbursed += amt

    locs = []
    for loc in act.iter("location"):
        pos = _narr(loc, "point/pos")
        if not pos:
            continue
        try:
            lat, lon = (float(x) for x in pos.split()[:2])
        except ValueError:
            continue
        locs.append((lon, lat, _narr(loc, "name/narrative")))

    dates = {d.get("type"): (d.get("iso-date") or "")[:4] for d in act.iter("activity-date") if d.get("iso-date")}
    impl = []
    for po in act.iter("participating-org"):
        if po.get("role") == "4":
            n = (_narr(po, "narrative") or "").strip(" *") or EU_IMPL_REF.get(po.get("ref") or "", "")
            if n and n.title() not in impl:
                impl.append(n.title() if n.isupper() else n)
    aid = next((d.get("code") for d in act.iter("default-aid-type")), None)
    fin = next((d.get("code") for d in act.iter("default-finance-type")), None)
    iid = _narr(act, "iati-identifier")
    purl = None
    if pub == "EIB" and iid:
        m = re.match(r"XM-DAC-918-3-(\d{8})", iid)
        if m:
            purl = f"https://www.eib.org/en/projects/all/{m.group(1)}"
    title = _narr(act, "title/narrative") or ""
    if pub == "EIB" and title.isupper():
        title = title.title()
    return {
        "pub": pub, "lender": conf["lender"], "id": iid, "hierarchy": act.get("hierarchy") or "1",
        "parents": [ra.get("ref") for ra in act.iter("related-activity") if ra.get("type") == "1" and ra.get("ref")],
        "name": title, "desc": (_narr(act, "description/narrative") or "")[:300] or None,
        "country": iso, "countries": [c for c, _ in african] or None, "regions": regions,
        "sector": sector, "sector_codes": sector_codes, "sector_label": sector_label,
        "raw_status": code, "dash_status": IATI_STATUS.get(code),
        "commitment": round(commitment, 2) or None, "disbursed": round(disbursed, 2) or None,
        "share": share, "africa_share": africa_share, "refs2": sorted(refs2),
        "mixed_currency": mixed, "locs": locs,
        "start_year": dates.get("2") or dates.get("1"), "end_year": dates.get("4") or dates.get("3"),
        "implementers": "; ".join(impl)[:600] or None,
        "aid_type": aid, "instrument": EU_INSTRUMENT.get(fin or "", "budget support" if (aid or "").startswith("A") else None),
        "project_url": purl,
    }


def fetch_eu():
    """European Commission (INTPA, and NEAR in Africa) and EIB activities in the region, one
    GeoJSON point per record, from the publishers' IATI files via the registry."""
    acts, n_files, dropped, generated = [], 0, {"left_out": 0, "other_funder": 0}, {}
    for publisher, conf in EU_PUBLISHERS.items():
        meta = json.loads(get(f"{REGISTRY}?q=organization:{publisher}&rows=300", timeout=90))
        pkgs = [pk for pk in meta["result"]["results"]
                if pk["name"].rsplit("-", 1)[-1].lower() in conf["files"]]
        urls = [r["url"] for pk in pkgs for r in pk["resources"]]
        print(f"IATI {publisher}: {len(urls)} datasets")
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
            n_files += 1
            g = (root.get("generated-datetime") or "")[:10]
            if g:
                generated.setdefault(conf["pub"], []).append(g)
            for act in root.iter("iati-activity"):
                a = _eu_activity(act, conf)
                if isinstance(a, str):
                    dropped[a] += 1
                elif a:
                    acts.append(a)
            if i % 15 == 0 or i == len(urls):
                print(f"  … {i}/{len(urls)} files, {len(acts):,} infrastructure activities in {REGION.name} so far")

    # one record per contract; a decision only when none of its contracts is here
    ec = [a for a in acts if a["pub"] != "EIB"]
    parents = {p for a in ec if a["hierarchy"] == "2" for p in a["parents"]}
    by_id = {a["id"]: a for a in ec}
    kept = [a for a in acts if a["pub"] == "EIB" or a["hierarchy"] == "2" or a["id"] not in parents]
    # A multi-country decision is published as sub-activities (-01, -02…),
    # and each repeats the whole envelope under the same commitment
    # transaction ref. Copies that share a ref are one envelope: when any of
    # them has contracts, the contracts carry the money and every uncontracted
    # copy goes; when none has, one copy stays, for all the copies' countries.
    root_of = lambda i: (re.match(r"(.*ACT-D-\d+)-\d\d$", i or "") or [None, i])[1]  # noqa: E731
    decisions = [a for a in ec if a["hierarchy"] != "2" and a["refs2"]]
    group = {a["id"]: a["id"] for a in decisions}

    def find(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i
    by_ref = {}
    for a in decisions:
        for ref in a["refs2"]:
            other = by_ref.setdefault((root_of(a["id"]), ref), a["id"])
            group[find(a["id"])] = find(other)
    members = {}
    for a in decisions:
        members.setdefault(find(a["id"]), []).append(a)
    drop, n_env = set(), 0
    for mem in members.values():
        if len(mem) < 2:
            continue
        live = [a for a in mem if a["id"] not in parents]
        if not live:
            continue
        if any(a["id"] in parents for a in mem):
            drop |= {a["id"] for a in live}
        else:
            keep1 = max(live, key=lambda a: a["commitment"] or 0)
            cts = [c for a in mem for c in (a["countries"] or [])]
            keep1["countries"] = list(dict.fromkeys(cts)) or None
            if keep1["countries"] and len(keep1["countries"]) > 1:
                keep1["country"] = None          # drawn at the Commission's region-wide point
            drop |= {a["id"] for a in live if a is not keep1}
        n_env += 1
    kept = [a for a in kept if a["id"] not in drop]
    print(f"  {len(drop):,} repeated copies of {n_env:,} multi-country envelopes dropped; "
          f"{dropped['left_out']:,} EIB fund investments and credit lines and "
          f"{dropped['other_funder']:,} EIB operations funded by the Commission or a member state left out")
    n_contracts = sum(1 for a in kept if a["pub"] != "EIB" and a["hierarchy"] == "2")
    n_decisions = sum(1 for a in kept if a["pub"] != "EIB" and a["hierarchy"] != "2")
    n_folded = len(ec) - n_contracts - n_decisions - len(drop)
    print(f"  {n_contracts:,} contracts, {n_decisions:,} decisions without a contract, "
          f"{n_folded:,} decisions folded into their contracts; {len(kept) - n_contracts - n_decisions:,} EIB operations")

    # the Commission's default point per country: the position most of a
    # country's located activities share
    x0, y0, x1, y1 = IATI_WINDOW
    in_win = lambda lon, lat: x0 <= lon <= x1 and y0 <= lat <= y1 and (lon, lat) != (0.0, 0.0)
    tally = {}
    for a in ec:
        for lon, lat, _ in a["locs"]:
            tally.setdefault(a["country"], {}).setdefault((lon, lat), 0)
            tally[a["country"]][(lon, lat)] += 1
    default = {}
    for iso, c in tally.items():
        pos, n = max(c.items(), key=lambda kv: kv[1])
        if n >= 2:
            default[iso] = pos

    feats, prec_n, unplaced = [], {1: 0, 2: 0, 3: 0}, 0
    for a in kept:
        iso = a["country"]
        pts = [(lon, lat, nm) for lon, lat, nm in a["locs"] if in_win(lon, lat)]
        named = [p for p in pts if (p[0], p[1]) != default.get(iso) and (p[0], p[1]) != EU_AFRICA_POINT
                 and (iso or _country_at(p[0], p[1]))]
        place, locs = None, None
        if named:
            lon, lat, nm = named[0]
            prec, place = 1, _clean_place(nm, iso)
            if not iso:
                iso = _country_at(lon, lat)
            if len(named) > 1:
                locs = [[round(x, 5), round(y, 5), _clean_place(n, iso) or ""] for x, y, n in named[:16]]
        elif iso:
            if pts and (pts[0][0], pts[0][1]) == default.get(iso):
                lon, lat = pts[0][0], pts[0][1]          # the Commission's own country point
            else:
                lon, lat = ISLAND_POINT.get(iso) or _country_centre(iso)
            if lon is None:
                unplaced += 1
                continue
            prec = 2
        else:
            lon, lat = EU_AFRICA_POINT
            prec = 3
        prec_n[prec] += 1
        parent = next((by_id[p] for p in a["parents"] if p in by_id), None)
        # What the totals add up: the infrastructure share of the region's
        # share of the commitment; nothing for a cancelled or suspended record
        stalled = a["dash_status"] == STALLED
        factor = a["share"] * a["africa_share"]
        com, dis = a["commitment"], a["disbursed"]
        counted = None if stalled or com is None else round(com * factor, 2)
        counted_dis = None if stalled or dis is None else round(dis * factor, 2)
        notes = []
        if stalled:
            notes.append("cancelled or suspended, so not counted in totals")
        else:
            if a["share"] < 0.995:
                notes.append(f"{a['share']:.0%} of its sectors are infrastructure")
            if a["africa_share"] < 0.995:
                notes.append(f"{a['africa_share']:.0%} of it goes to {REGION.name}")
            if notes:
                notes = ["; ".join(notes) + "; that share is counted"]
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": {
                "source": "EC-" + a["pub"] if a["pub"] != "EIB" else "EIB",
                "publisher": a["pub"], "lender": a["lender"], "layer": "eu",
                "kind": "operation" if a["pub"] == "EIB" else ("contract" if a["hierarchy"] == "2" else "decision"),
                "name": a["name"] or None, "description": a["desc"],
                "parent_id": parent["id"] if parent else (a["parents"][0] if a["parents"] else None),
                "parent_name": parent["name"] if parent else None,
                "country": iso, "countries": a["countries"], "region": next(iter(set(a["regions"]) & EU_REGIONS), None),
                "sector": a["sector"], "sector_codes": a["sector_codes"], "sector_label": a["sector_label"],
                "raw_status": a["raw_status"], "dash_status": a["dash_status"],
                "geo_precision": prec, "location_name": place, "locations": locs,
                "commitment": counted or None, "disbursed": counted_dis or None, "currency": "EUR",
                "commitment_published": com if com and counted != com else None,
                "disbursed_published": dis if dis and counted_dis != dis else None,
                "counted_note": "; ".join(notes) or None,
                "mixed_currency": a["mixed_currency"] or None,
                "implementers": a["implementers"], "aid_type": a["aid_type"],
                "aid_type_name": EU_AID_TYPE.get(a["aid_type"] or ""), "instrument": a["instrument"],
                "start_year": a["start_year"], "end_year": a["end_year"],
                "iati_id": a["id"], "project_url": a["project_url"],
            },
        })
    print(f"  placed: {prec_n[1]:,} on a named place, {prec_n[2]:,} at the country's point, "
          f"{prec_n[3]:,} {REGION.wide} at the Commission's regional point; {unplaced} could not be placed")
    out = write_layer("iati_eu_finance", feats)
    # "data as of": the oldest file's own generation date, since the EIB's
    # and DG NEAR's files can be more than a year older than the download
    gen = {k: (min(v), max(v)) for k, v in generated.items()}
    oldest = min((v[0] for v in gen.values()), default=None)
    update_meta("eu", fetched=today(), fresh=fmt_date(oldest) if oldest else None,
                generated={k: v[1] for k, v in gen.items()},
                envelopes_dropped=len(drop), eib_left_out=dropped["left_out"],
                eib_other_funder=dropped["other_funder"],
                datasets=n_files, records=len(feats),
                contracts=n_contracts, decisions=n_decisions, decisions_folded=n_folded,
                eib=len(feats) - n_contracts - n_decisions, named_place=prec_n[1],
                country_point=prec_n[2], regional=prec_n[3], unplaced=unplaced, eur_usd=EUR_USD)
    return out


# ------------------------------------------------------------ Piano Mattei
#
# Italy's "Piano Mattei per l'Africa" is a political label, like the EU's
# Global Gateway, but unlike the Global Gateway's PDF flagship list the
# Italian Government publishes its projects as a portal with one page per
# project (governo.it/it/piano-mattei/progetti/): title, the plan's
# directive(s), objective, countries, implementing body, partners, funding
# source, a stated amount and a five-step progress bar. No coordinates. The
# layer is that list, one record per page, in the portal's English version
# where it has one, with the Italian page as the record of reference. The
# pages are server-rendered Next.js, so the fields are read from the HTML
# itself; each Italian page links to its English translation (the two lists
# are not in the same order, and the English slugs are translated).
#
# Location: the portal gives none, so a record sits on the place its
# description names, when it names one (a hand-kept gazetteer below, with
# coordinates from OpenStreetMap), on the country's interior point for a
# bilateral project without a named place, and, for a project that lists
# several countries or none, at one Africa-wide point for the layer, the mean
# of the plan's partner countries' points, which is not a site and is said to
# be none on the card (a mean of the project's own countries lands at sea for
# a Senegal-Ghana-Mozambique programme, and reads as a place).
MATTEI_SITE = "https://www.governo.it"
MATTEI_LIST = "/{lang}/piano-mattei/progetti/"
MATTEI_UA = {"User-Agent": "Mozilla/5.0 africa-project-atlas/0.1 (dataset build)"}
# the portal's progress bar; the active step is the one not drawn grey
MATTEI_STAGE = {"Identificato": ("Identified", ANNOUNCED), "Formulato": ("Formulated", ANNOUNCED),
                "Approvato": ("Approved", APPROVED), "In corso": ("Ongoing", BUILDING),
                "Concluso": ("Completed", OPERATING)}
# the portal's six directives (English labels) -> the map's sector buckets;
# "Physical and digital infrastructure" is decided per project below
MATTEI_SECTOR = {"Energy": "energy", "Water": "water", "Health": "health",
                 "Education/Training/Culture": "education", "Agriculture/Fisheries": "agriculture",
                 "Physical and digital infrastructure": None}
# per-project sector where the first directive is "infrastructure" or the
# project spans all six (a budget-support loan, a fund): by what it builds
MATTEI_SECTOR_BY_ID = {
    "progetto-lobito-economic-corridor-development-project": "transport",
    "progetto-digital-flagship-dell-italia-con-l-africa": "ict",
    "progetto-ai-hub-for-sustainable-development": "ict",
    "progetto-supporto-al-rafforzamento-dei-servizi-digitali-in-etiopia-attraverso-la-creazione-di-un-centro-d-incub-1763c944": "ict",
    "progetto-a-roadmap-to-connect-africa-to-europe-for-clean-energy-production": "energy",
    "progetto-programma-di-sostegno-alla-repubblica-federale-democratica-d-etiopia-per-lo-sviluppo-ambientale-e-la-g-c2dd01d8": "water",
    "progetto-tandem-italia-tunisia-finanziamento-nell-ambito-della-sicurezza-agroalimentare-e-idrica-tanit": "water",
    "progetto-g7-adaptation-accelerator-hub": "environment",
    "progetto-finanziamentoin-favore-di-exchange-traded-commodities-group-etc-per-attivita-connesse-alla-catena-di-a-aa53e41b": "agriculture",
    "progetto-area-africa-rafforzamento-degli-ecosistemi-agro-alimentari-in-africa-in-partenariato-con-il-sistema-pr-cd21711f": "agriculture",
}
# the portal's country names (English pages) -> ISO; anything else is dropped
MATTEI_ISO = {
    "Algeria": "DZ", "Angola": "AO", "Benin": "BJ", "Burkina Faso": "BF", "Côte d'Ivoire": "CI",
    "Cote d'Ivoire": "CI", "Democratic Republic of the Congo": "CD", "Egypt": "EG", "Ethiopia": "ET",
    "Gabon": "GA", "Ghana": "GH", "Guinea-Bissau": "GW", "Kenya": "KE", "Malawi": "MW", "Mali": "ML",
    "Mauritania": "MR", "Mauritius": "MU", "Morocco": "MA", "Mozambique": "MZ", "Niger": "NE",
    "Republic of the Congo": "CG", "Rwanda": "RW", "Senegal": "SN", "South Africa": "ZA",
    "Tanzania": "TZ", "Togo": "TG", "Tunisia": "TN", "Uganda": "UG", "Zambia": "ZM",
}
# the plan's partner countries, as the portal lists them on its continental
# programmes (nine pilots of 2024, five added in 2025, four in 2026); a
# project with no country at all is drawn at the mean of their points
MATTEI_PARTNERS = ["DZ", "AO", "CI", "CD", "EG", "ET", "GA", "GH", "KE", "MR", "MA", "MZ", "CG", "RW", "SN", "TZ", "TN", "ZM"]
# Where a description names a place: label, lon, lat, tier (1 site or town,
# 2 administrative area at its centre), and other named places for the card.
# Coordinates are OpenStreetMap's (Nominatim, 7 Oct 2026), ODbL.
MATTEI_PLACES = {
    "progetto-recupero-terreni-semi-aridi-per-la-produzione-agricola-in-algeria":
        ("Timimoun", 0.2286, 29.2605, 1, []),
    "progetto-supporto-al-progetto-di-sviluppo-rurale-per-il-polo-agro-industriale-nel-nord-est-della-costa-d-avorio-2pai-ne":
        ("Zanzan district", -2.7993, 8.0843, 2, []),
    "progetto-supporto-alla-realizzazione-di-un-impianto-fotovoltaico-in-egitto-abydos-ii-plafond-africa":
        ("Benban, Aswan", 32.73, 24.46, 1, []),
    "progetto-tandem-italia-tunisia-finanziamento-nell-ambito-della-sicurezza-agroalimentare-e-idrica-tanit":
        ("Tunis (El Attar plant)", 10.1858, 36.8002, 1, [("Enfidha", 10.378, 36.1341), ("Sfax", 10.7604, 34.7394)]),
    "progetto-finanziamento-sovrano-a-supporto-del-programma-di-rafforzamento-del-sistema-elettrico-nazionale-in-rep-7d281773":
        ("Brazzaville", 15.2712, -4.2694, 1, [("Pointe-Noire", 11.8503, -4.7975)]),
    "progetto-creazione-del-centro-algero-italiano-di-eccellenza-per-la-formazione-la-ricerca-e-l-innovazione-in-agr-f2b6585a":
        ("Sidi Bel Abbès", -0.6341, 35.1907, 1, []),
    "progetto-rafforzamento-del-settore-sanitario":
        ("Abobo, Abidjan", -4.0202, 5.4263, 1, [("Abengourou", -3.4968, 6.7269)]),
    "progetto-programma-di-sostegno-alla-repubblica-federale-democratica-d-etiopia-per-lo-sviluppo-ambientale-e-la-g-c2dd01d8":
        ("Jimma, Lake Boye", 36.8479, 7.6756, 1, []),
    "progetto-sostegno-settore-sanitario-nella-regione-settentrionale-del-tigray":
        ("Shire", 38.2825, 14.1024, 1, [("Adwa", 38.8912, 14.1671), ("Gondar", 37.4668, 12.6104)]),
    "progetto-supporto-al-rafforzamento-dei-servizi-digitali-in-etiopia-attraverso-la-creazione-di-un-centro-d-incub-1763c944":
        ("Addis Ababa", 38.7524, 9.0358, 1, []),
    "progetto-laboratorio-dei-talenti":
        ("Meru County (Chaaria)", 37.65, 0.047, 2, []),
    "progetto-istituzione-di-un-polo-agroalimentare-nella-provincia-di-manica-centro-agroalimentare-di-manica-caam":
        ("Manica province", 33.478, -19.1437, 2, []),
    "progetto-progetti-di-ampliamento-struttura-ed-equipaggiamenti-istituto-don-bosco-di-maputo":
        ("Maputo", 32.5675, -25.9662, 1, []),
    "progetto-programma-integrato-di-sviluppo-delle-filiere-agroalimentari-pideca":
        ("Matam region", -13.6992, 15.2681, 2, [("Louga region", -15.6779, 15.3967), ("Kolda region", -14.4181, 13.1292), ("Sédhiou region", -15.553, 12.9103)]),
    "progetto-formazione-professionale-di-qualita-nel-settore-turistico-alberghiero-dell-arcipelago-di-zanzibar-fo-pr-alb":
        ("Zanzibar", 39.2074, -6.1665, 2, []),
    "progetto-polo-patrimonio-tunisia-formazione-conservazione-e-valorizzazione-nei-siti-archeologici-di-kerkpuane-p-d5b7db2d":
        ("Kerkouane", 11.099, 36.946, 1, [("Neapolis (Nabeul)", 10.7356, 36.4513), ("Pupput (Hammamet)", 10.5573, 36.4013)]),
    "progetto-bleue-tunisie-programma-di-sostegno-all-economia-blu-per-lo-sviluppo-sostenibile-delle-comunita-costiere":
        ("Sidi Daoud port", 10.9134, 37.0213, 1, [("El Kraten", 11.2554, 34.8171), ("Mahres", 10.4984, 34.5218), ("Skhira", 10.0689, 34.3004)]),
    "progetto-gemellaggio-tra-il-parco-archeologico-di-pompei-e-la-citta-antica-di-timgad-in-algeria":
        ("Timgad", 6.4668, 35.4836, 1, []),
    "progetto-gemellaggio-tra-il-parco-archeologico-del-colosseo-e-l-anfiteatro-di-el-jem-e-valorizzazione-del-patri-3a2f9a1e":
        ("El Jem", 10.7128, 35.2966, 1, []),
    "progetto-ethiopia-borana-resilient-water-development-for-improved-livelihood-programme-borana-rwdp-ii":
        ("Borana zone", 38.095, 4.8926, 2, []),
    "progetto-eastern-region-agricultural-value-chain-development-project-eravcdp":
        ("Six eastern provinces (at Luena, Moxico)", 19.9123, -11.779, 2, [("Dundo, Lunda Norte", 20.8338, -7.3811), ("Saurimo, Lunda Sul", 20.3981, -9.6589), ("Menongue, Cuando Cubango", 17.682, -14.6611)]),
    "progetto-lobito-economic-corridor-development-project":
        ("Lobito", 13.5464, -12.3507, 1, []),
    "progetto-terna-innovation-zone":
        ("Tunis", 10.1858, 36.8002, 1, []),
    "progetto-elmed":
        ("Mlaabi, Cap Bon (near Menzel Temime)", 10.9939, 36.7807, 1, []),
    "progetto-centro-di-eccellenza-panafricano-per-la-formazione-sulle-energie-rinnovabili-e-la-transizione-energetica":
        ("Ben Guerir (UM6P campus)", -7.9462, 32.2328, 1, [("Nairobi", 36.8173, -1.289), ("Pretoria", 28.188, -25.746)]),
    "progetto-finanziamento-alla-banque-ouest-africaine-de-developpement":
        ("Lomé (BOAD headquarters)", 1.2158, 6.1304, 1, []),
}


def _mattei_text(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_mod.unescape(s).replace("\xa0", " ")
    return re.sub(r"\n{2,}", "\n", s).strip()


def _mattei_list(lang):
    """The project slugs in the order the list page shows them."""
    page = get(f"{MATTEI_SITE}{MATTEI_LIST.format(lang=lang)}", timeout=90).decode("utf-8", "replace")
    out = []
    for m in re.finditer(rf'href="/{lang}/piano-mattei/progetti/progetto/([^"/]+)/"', page):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def _mattei_page(lang, slug):
    """The fields of one project page, from its server-rendered HTML."""
    req = urllib.request.Request(f"{MATTEI_SITE}/{lang}/piano-mattei/progetti/progetto/{slug}/", headers=MATTEI_UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        s = r.read().decode("utf-8", "replace")
    d = {"slug": slug}
    other = "en" if lang == "it" else "it"
    m = re.search(rf'hrefLang="{other}"[^>]*href="/{other}/piano-mattei/progetti/progetto/([^"/]+)/"', s)
    d["other_slug"] = m.group(1) if m else None
    m = re.search(r'<h3 class="project-subtitle[^"]*">(.*?)</h3>\s*<h1 id="project-heading"[^>]*>(.*?)</h1>', s, re.S)
    d["title"] = _mattei_text(m.group(2)) if m else None
    m = re.search(r'<div class="[^"]*markdown-text"[^>]*>(.*?)</div><div class="mt-4 w-100" role="list"', s, re.S)
    d["desc"] = _mattei_text(m.group(1)) if m else None
    m = re.search(r'role="list" aria-label="[^"]*direttric[^"]*">(.*?)</div></div></div><div class="col-12 col-lg-4', s, re.S)
    d["directives"] = [_mattei_text(x) for x in re.findall(
        r'<span class="fw-semibold text-base font-titillium text-truncate[^"]*"[^>]*>(.*?)</span>', m.group(1) if m else "", re.S)]
    for k, v in re.findall(r'<dt class="text-muted[^"]*">(.*?)</dt><dd[^>]*>(.*?)</dd>', s, re.S):
        k = _mattei_text(k)
        steps = re.findall(r'background:(#[0-9A-Fa-f]{6})"></span><span class="text-base text-center">(.*?)</span>', v)
        if steps:
            d["stage"] = next((_mattei_text(n) for c, n in steps if c.upper() != "#C5C7C9"), None)
        else:
            d[k] = _mattei_text(v)
    d["gallery"] = len(re.findall(r'<li class="splide__slide', s))
    return d


def _mattei_amount(text):
    """"EUR 1.4 billion" -> (1.4e9, "EUR"); "$75 million" -> (75e6, "USD");
    the first figure in the text, or None. Parts joined by " / " are summed
    when each states its own amount in one currency: TANIT prints "EUR 250
    million for TANIT infrastructure / EUR 36.5 million for TANIT KT"."""
    parts = [x for x in (text or "").split(" / ") if x.strip()]
    if len(parts) > 1:
        got = [_mattei_amount(x) for x in parts]
        if all(v for v, _ in got) and len({c for _, c in got}) == 1:
            return sum(v for v, _ in got), got[0][1]
    t = (text or "").replace(" ", " ")
    m = re.search(r"(EUR|USD|€|\$)?\s*(\d[\d,]*(?:\.\d+)?)\s*(billion|million|thousand)?", t)
    if not m or not m.group(2):
        return None, None
    try:
        v = float(m.group(2).replace(",", ""))
    except ValueError:
        return None, None
    v *= {"billion": 1e9, "million": 1e6, "thousand": 1e3, None: 1}[m.group(3)]
    cur = "USD" if m.group(1) in ("USD", "$") else "EUR"
    return v, cur


def fetch_mattei(workers=4):
    """The Italian Government's Piano Mattei project portal, one GeoJSON
    point per project, read from the portal's project pages."""
    it_slugs = _mattei_list("it")
    print(f"Piano Mattei portal: {len(it_slugs)} projects listed")
    pages = {}
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        for slug, d in zip(it_slugs, ex.map(lambda sl: _mattei_page("it", sl), it_slugs)):
            pages[("it", slug)] = d
    pair = {sl: pages[("it", sl)]["other_slug"] for sl in it_slugs if pages[("it", sl)].get("other_slug")}
    en_slugs = sorted(set(pair.values()))
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        for slug, d in zip(en_slugs, ex.map(lambda sl: _mattei_page("en", sl), en_slugs)):
            pages[("en", slug)] = d
    print(f"  {len(it_slugs)} Italian pages read, {len(en_slugs)} English translations linked from them")

    feats, tiers, stages, n_amount, total_eur, n_sector = [], {1: 0, 2: 0, 3: 0, 4: 0}, {}, 0, 0.0, {}
    partner_pts = [p for p in (_country_centre(i) for i in MATTEI_PARTNERS) if p[0] is not None]
    continent = (sum(p[0] for p in partner_pts) / len(partner_pts), sum(p[1] for p in partner_pts) / len(partner_pts))
    for slug in it_slugs:
        it = pages[("it", slug)]
        en = pages.get(("en", pair.get(slug))) or {}
        stage_it = it.get("stage")
        stage_en, status = MATTEI_STAGE.get(stage_it or "", (None, None))
        if not status:
            print(f"  ! {slug}: no stage read, skipped")
            continue
        stages[stage_en] = stages.get(stage_en, 0) + 1
        names = [c.strip() for c in re.split(r",\s*", en.get("Countries") or "") if c.strip()]
        isos = []
        for n in names:
            if MATTEI_ISO.get(n) and MATTEI_ISO[n] not in isos:
                isos.append(MATTEI_ISO[n])
        if not isos and not en:          # no English page: read the Italian list through the ISO table's values
            names = [c.strip() for c in re.split(r",\s*", it.get("Nazioni") or "") if c.strip()]
        directives = en.get("directives") or it.get("directives") or []
        sector = MATTEI_SECTOR_BY_ID.get(slug)
        if not sector:
            sector = "other" if len(directives) >= 6 else (MATTEI_SECTOR.get(directives[0]) if directives else None) or "other"
        n_sector[sector] = n_sector.get(sector, 0) + 1
        amount_text = en.get("Amount") or it.get("Importo") or ""
        value, cur = _mattei_amount(amount_text)
        shared = bool(re.search(r"\(Algeria, Egypt, Tunisia, Ethiopia\)", amount_text))   # one envelope printed on four records
        eur = None
        if value:
            eur = round(value / EUR_USD, 2) if cur == "USD" else value
            if shared:
                m = re.search(r"(?:EUR|and)\s*(\d[\d,]*)\s*for the promotion", amount_text)
                eur = float(m.group(1).replace(",", "")) if m else None
            if eur:
                n_amount += 1
                total_eur += eur
        place = MATTEI_PLACES.get(slug)
        locs = None
        if place:
            label, lon, lat, tier, others = place
            if others:
                locs = [[round(x, 5), round(y, 5), n] for n, x, y in others]
            # the portal's own country wins (Brazzaville falls into the DRC on
            # the 1:110m basemap); point-in-polygon only decides for a
            # multi-country project with a named site
            iso = isos[0] if len(isos) == 1 else (_country_at(lon, lat) or (isos[0] if isos else None))
        elif len(isos) == 1:
            label, tier, iso = None, 3, isos[0]
            lon, lat = ISLAND_POINT.get(iso) or _country_centre(iso)
        else:
            label, tier, iso = None, 4, None
            lon, lat = continent
        tiers[tier] += 1
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": {
                "source": "Piano Mattei portal", "layer": "mattei", "id": slug,
                "name": (en.get("title") or it.get("title") or "").strip() or None,
                "name_it": (it.get("title") or "").strip() or None,
                "description": (en.get("desc") or it.get("desc") or "")[:600] or None,
                "directives": directives, "sector": sector,
                "objective": en.get("Objective") or it.get("Obiettivo") or None,
                "country": iso, "countries": isos if len(isos) > 1 else None,
                "country_names": names or None,
                "stage": stage_en, "stage_it": stage_it, "dash_status": status,
                "amount_text": amount_text or None, "amount_eur": eur, "amount_currency": cur,
                "amount_shared": shared or None,
                # a line break in this field is the portal wrapping a long
                # name ("United Nations Development Programme / (UNDP)"),
                # never a separator between bodies
                "implementer": re.sub(r"\s*\n\s*", " ", en.get("Implementing body") or it.get("Ente esecutore") or "")
                               or None,
                "partnerships": en.get("Partnerships") or it.get("Partenariati") or None,
                "international_partners": en.get("International partners") or it.get("Partner internazionali") or None,
                "resources": en.get("Resources") or it.get("Risorse") or None,
                "geo_precision": tier, "location_name": label, "locations": locs,
                "gallery": it.get("gallery") or 0,
                "url": f"{MATTEI_SITE}/it/piano-mattei/progetti/progetto/{slug}/",
                "url_en": f"{MATTEI_SITE}/en/piano-mattei/progetti/progetto/{pair[slug]}/" if slug in pair else None,
            },
        })
    for p in feats:   # a "—" is the portal's empty value
        for k in ("implementer", "partnerships", "international_partners", "resources", "objective"):
            if p["properties"].get(k) in ("—", "-", ""):
                p["properties"][k] = None
    print(f"  stages: " + ", ".join(f"{k} {v}" for k, v in sorted(stages.items(), key=lambda kv: -kv[1])))
    print(f"  placed: {tiers[1]} on a named site or town, {tiers[2]} on a named administrative area, "
          f"{tiers[3]} at the country's point, {tiers[4]} multi-country at the layer's Africa-wide point "
          f"({continent[0]:.2f}, {continent[1]:.2f}, in {_country_at(*continent) or 'the sea'})")
    print(f"  {n_amount} of {len(feats)} carry a stated amount, €{total_eur / 1e9:,.2f}bn in all")
    out = write_layer("piano_mattei", feats)
    update_meta("mattei", fetched=today(), fresh=None, records=len(feats),
                stages=stages, named_place=tiers[1], named_area=tiers[2], country_point=tiers[3],
                multi_country=tiers[4], with_amount=n_amount, total_eur=round(total_eur),
                partner_countries=len(MATTEI_PARTNERS), eur_usd=EUR_USD,
                continent_point=[round(continent[0], 3), round(continent[1], 3)])
    return out


# ------------------------------------------------------------------ entrypoint

LAYERS = {
    "gem": fetch_gem,
    "iati": fetch_iati,                 # the region's development bank: AfDB, or ADB
    "wb": lambda: fetch_iati("worldbank"),
    "osm": fetch_osm,
    "pipes": fetch_pipelines,
    "cables": fetch_cables,
    "china": fetch_aiddata,
    "eu": fetch_eu,
    "mattei": fetch_mattei,
}
# the layers this edition has (no Piano Mattei outside Africa)
LAYERS = {k: f for k, f in LAYERS.items() if k != "mattei" or "mattei" in REGION.layers}

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
