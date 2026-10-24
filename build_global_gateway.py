#!/usr/bin/env python3
"""
Build the Global Gateway deep dive, docs/global-gateway/index.html: the
European Union's Global Gateway flagship projects in Africa as the European
Commission lists them, where they are, which areas of partnership they
belong to, who in Team Europe is named behind each one, and what the EU's
own money records on the map say about Global Gateway.

    python3 build_global_gateway.py           build the page from data/global_gateway.geojson
    python3 build_global_gateway.py --fetch   reread the Commission's map, tracker and project pages first

Two outputs. The data file, data/global_gateway.geojson, feeds the map's
and the dashboard's Global Gateway layer (build_dashboard.build_gateway).
The page, published on 2026-10-24, is a deep dive in DEEP_THEMES (shared.py),
so it is in the menu bar, the footer, the sitemap and llms.txt. refresh.py
runs this script with --fetch in its fetch stage and plainly in its build
stage, so the menus every page carries list it.

Sources, all the Commission's own (content of the EU's websites is CC BY 4.0
unless marked otherwise, commission.europa.eu/legal-notice_en):

  * The map on the Commission's Global Gateway page
    (commission.europa.eu/topics/international-partnerships/global-gateway_en)
    is a Europa webtools widget whose data file, WIDGET below, lists the
    flagships country by country: an identifier, title, scope (country
    level, regional, global), area of partnership, a sentence and a link to
    the project's page. Regional flagships appear under every country they
    name and under eight regional points. No amounts, no stage and no place
    finer than one point per country.
  * Each flagship's page on international-partnerships.ec.europa.eu: its
    "Key information" list (areas of partnership, type of initiative,
    geographical focus, countries, Team Europe members involved, Initiative
    ID) and its milestones. The pages are server-rendered Drupal; the site
    throttles bursts (HTTP 429), so the fetch waits between pages and backs
    off, and keeps them in data/.gg_cache/ (not committed).
  * The Commission's Global Gateway tracker (a chart widget on the
    international-partnerships Global Gateway page, TRACKER below): investment
    "mobilised" 2021–2024 by region, in EUR million. Only its regional split
    is used: its two other sheets (by Commission service, by institution) do
    not add up to its total and the widget does not say what the rest is.
  * The map's EU finance layer (data/iati_eu_finance.geojson, the Commission's
    and the EIB's IATI files) for the records that name Global Gateway in
    their title, description or parent decision. The IATI files carry no
    flagship identifier, so a flagship and a contract are joined only where a
    match was checked by hand (MATCHES below).

One record is one flagship: one Commission identifier (the map's
"project_id"; a few flagships carry a list of them, kept as one record).
A flagship is African when the Commission's map lists it under an African
country or its Sub-Saharan Africa point, or under its Mediterranean point
(which mixes North Africa with the Middle East) with an African country or
a North African focus on its page. Only those flagships' pages are fetched. The page draws every flagship at each African
country it names, at that country's interior point (the Commission's map has
one point per country too), spread around the point so each can be pointed
at; a flagship that names no country sits at the Commission's Africa-wide
point in Chad, the one the map's EU layer uses for regional programmes.
data/global_gateway.geojson keeps one point per flagship, which is what the
map's Global Gateway layer draws (build_dashboard.build_gateway): the
country's point for a one-country flagship, the Africa-wide point otherwise
(geo_precision 2 or 3), with the countries kept for the country filter.

The page wears the lender profiles' frame (donor.template.html). It imports
pure helpers from build_donors.py, build_lobito.py and headmap.py and edits
none of them.
"""

import collections
import hashlib
import html
import json
import math
import pathlib
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile

from build_donors import FRAME, MAP_H, MAP_W, land_paths, px, table, td
from build_lobito import esc
from fetch_donors import NAME, centre
from headmap import africa_map, figure, head_wrap
from region import REGION
from shared import (AUTHOR_NAME, AUTHOR_URL, DATA, DOCS, EUR_NOTE, EUR_USD, SITE_NAME, SITE_URL, WEB_URL,
                    brand_assets, fmt_date, site_url, today, wrap_document)

ROOT = pathlib.Path(__file__).parent
OUT = DATA / "global_gateway.geojson"
CACHE = DATA / ".gg_cache"
EU_LAYER = DATA / "iati_eu_finance.geojson"
FRAG = ROOT / "sections" / "global_gateway.html"
SLUG = "global-gateway"
TITLE = "Global Gateway in Africa"
DESCRIPTION = ("The European Union's Global Gateway flagship projects in Africa as the European Commission lists "
               "them: where they are, what they are for, which Team Europe members are named behind each, and "
               "what the EU's own contract records say, with no amounts or stages the Commission does not publish.")

GG_PAGE = "https://commission.europa.eu/topics/international-partnerships/global-gateway_en"
LIST_PAGE = "https://international-partnerships.ec.europa.eu/policies/global-gateway/global-gateway-projects_en"
TRACKER_PAGE = "https://international-partnerships.ec.europa.eu/policies/global-gateway_en"
LEGAL = "https://commission.europa.eu/legal-notice_en"
WIDGET = "https://europa.eu/assets/wcloud/widgets/202304/b6d05c30-e01d-11ed-8046-5576014d81c0/data.json"
TRACKER = ("https://europa.eu/assets/wcloud/widgets/202509/4fdde490-9df6-11f0-9f6c-0163186d0523/"
           "global-gateway-tracker-data.xlsx")
UA = {"User-Agent": "Mozilla/5.0 africa-project-atlas/0.1 (dataset build)"}

AF = set(NAME)
# The Commission's spellings, on its map and on the project pages, that are
# not the site's (fetch_donors.NAME). "Congo" alone is the Republic: the
# list's country filter has it beside "Democratic Republic of the Congo".
ALIAS = {"Congo (Republic)": "CG", "Congo": "CG", "Republic of Congo": "CG", "Republic of the Congo": "CG",
         "Democratic Republic of the Congo": "CD", "Democratic Republic of Congo": "CD", "DRC": "CD",
         "Côte d’Ivoire": "CI", "Cote d'Ivoire": "CI", "Ivory Coast": "CI", "Gambia": "GM",
         "Republic of Malawi": "MW", "Republic of Rwanda": "RW", "Cape Verde": "CV",
         "Sao Tome and Principe": "ST", "São Tomé and Príncipe": "ST", "Swaziland": "SZ",
         "United Republic of Tanzania": "TZ"}
ISO = {**{v: k for k, v in NAME.items()}, **ALIAS}
AFRICAN_FOCUS = {"Sub-Saharan Africa", "North Africa"}
# the two regional points of the Commission's map that can hold African
# flagships, by the names the widget gives them (lon/lat as it gives them,
# kept for reference only: the layer and the page draw such flagships at
# REGION.eu_region_point, in Chad)
REGION_POINT = {"Sub-Saharan Africa": (22.5, 7.013668), "Mediterranean region": (27.727415, 32.103266)}

AREAS = ["Climate and energy", "Transport", "Digital", "Health", "Education and research"]
AREA_KEY = {"Climate and energy": "energy", "Transport": "transport", "Digital": "digital", "Health": "health",
            "Education and research": "edu"}
# The map's sector for a flagship: the Commission's area of partnership, read
# as the map's sectors read the DAC codes. "Climate and energy" takes in water,
# conservation, farming and raw materials, so those flagships are set by hand
# from their title and sentence (checked 2026-10-24); the card says the sector
# comes from the Commission's area.
AREA_SECTOR = {"Climate and energy": "energy", "Transport": "transport", "Digital": "ict", "Health": "health",
               "Education and research": "education"}
SECTOR_FIX = {
    # water and sanitation
    "IDI053-3": "water", "IDI010-1": "water", "IDI019-1": "water", "IDI114-1": "water", "IDI028-2": "water",
    "IDI017-3": "water", "IDI041-3": "water",
    # conservation, adaptation, coasts
    "IDI158-5": "environment", "IDI045-2": "environment", "GGPID98": "environment", "IDI238-1": "environment",
    "IDI017-2": "environment", "GGPID137": "environment",
    # farming and food
    "IDI055-1": "agriculture", "IDI053-1": "agriculture", "IDI120-1": "agriculture", "IDI015-1": "agriculture",
    "GGPID115": "agriculture", "IDI060-2": "agriculture",
    # raw materials and industry
    "GGPID89": "industry", "IDI175-1": "industry", "IDI289-4": "industry", "IDI316-1": "industry",
    "IDI183-1": "industry",
    # a market, a municipal fund, a water-food-energy nexus
    "IDI051-1": "trade", "IDI138-5": "other", "GGPID128": "other",
}
MEMBER_FIX = {"The Netherlands": "Netherlands", "Czechia": "Czech Republic",
              "European Investment Bank": "EIB", "European Bank for Reconstruction and Development": "EBRD"}
BANKS = {"EIB", "EBRD"}

# Flagships joined by hand to records of the map's EU finance layer: the
# flagship's identifier → IATI identifiers whose title, or the decision above
# them, names the same works, plant, programme or corridor. Checked on
# 2026-10-24 against what candidates() prints and a search on the proper
# nouns of each flagship's title and sentence; a candidate not listed here
# did not plainly name the same thing (a solar plant in the same country, a
# different interconnector, skills on the same corridor). Only records the
# layer keeps are searched, so a health or education flagship's contracts
# are mostly outside it. The Commission's records are here, the EIB's in
# EIB_MATCHES; the page and the cards keep the two institutions' money apart.
MATCHES = {
    "IDI138-6": ["XI-IATI-EC_INTPA-2023-PC-27119"],                                   # Kakono hydropower
    "IDI037-1": ["XI-IATI-EC_INTPA-2024-ACT-61744"],                                  # Eastern Backbone, Malawi
    "IDI045-3": ["XI-IATI-EC_INTPA-2022-PC-19794"],                                   # energy control centre, Mozambique
    "IDI138-8": ["XI-IATI-EC_INTPA-2024-PC-40666", "XI-IATI-EC_INTPA-2025-PC-35484",
                 "XI-IATI-EC_INTPA-2025-PC-43036"],                                   # Nalubaale-Kiira
    "IDI138-2": ["XI-IATI-EC_INTPA-2024-PC-27270", "XI-IATI-EC_INTPA-2026-PC-77041"],  # WASUNA
    "IDI017-1": ["XI-IATI-EC_INTPA-2026-PC-53751", "XI-IATI-EC_INTPA-2018-PCC-402240",
                 "XI-IATI-EC_INTPA-2012-PCC-306863", "XI-IATI-EC_INTPA-2012-PCC-308300"],  # Ruzizi III (not IV)
    "GGPID120": ["XI-IATI-EC_INTPA-2025-PC-49389"],                                   # Transgabonais railway
    "IDI239-4": ["XI-IATI-EC_INTPA-2022-PCC-432585"],                                 # Dakar BRT
    "IDI260-1": ["XI-IATI-EC_INTPA-2023-PC-26109", "XI-IATI-EC_INTPA-2023-PC-26111"],  # Nairobi BRT
    "IDI173-1": ["XI-IATI-EC_INTPA-2018-PCC-397675"],                                 # Port of Pointe-Noire
    "IDI065-1": ["XI-IATI-EC_INTPA-2023-PC-32405"],                                   # WASH in schools, Uganda
    "IDI034-1": ["XI-IATI-EC_INTPA-2023-PC-25947", "XI-IATI-EC_INTPA-2023-PC-25936"],  # VaMoz Digital
    "IDI134-1": ["XI-IATI-EC_INTPA-2022-PC-19845"],                                   # TESS for MAV+
    "IDI139-1": ["XI-IATI-EC_INTPA-2026-PC-76511"],                                   # OP-VET, South Sudan
    "GGPID108": ["XI-IATI-EC_INTPA-2023-PC-26505"],                                   # sustainable aviation fuels
    "IDI175-2": ["XI-IATI-EC_INTPA-2026-PC-87559", "XI-IATI-EC_INTPA-2021-ACT-63570",
                 "XI-IATI-EC_INTPA-2025-PC-48068", "XI-IATI-EC_INTPA-2025-PC-54060",
                 "XI-IATI-EC_INTPA-2021-ACT-63560", "XI-IATI-EC_INTPA-2021-ACT-63581",
                 "XI-IATI-EC_INTPA-2026-PC-81339"],                                   # Lobito corridor
    "IDI053-3": ["XI-IATI-EC_INTPA-2024-PC-36350", "XI-IATI-EC_INTPA-2024-PC-36338",
                 "XI-IATI-EC_INTPA-2019-PCC-409580"],                                 # Hann Bay cleanup
    "IDI033-1": ["XI-IATI-EC_INTPA-2026-PC-76092"],                                   # Volobe hydropower, Madagascar
    "GGPID86": ["XI-IATI-EC_INTPA-2020-PCC-413656", "XI-IATI-EC_INTPA-2025-PC-48168"],  # Zambia-Tanzania leg of ZTK
    "IDI067-1": ["XI-IATI-EC_INTPA-2025-PC-52304", "XI-IATI-EC_INTPA-2025-PC-51602",
                 "XI-IATI-EC_INTPA-2024-PC-44872", "XI-IATI-EC_INTPA-2022-PC-22671",
                 "XI-IATI-EC_INTPA-2024-PC-36871", "XI-IATI-EC_INTPA-2025-PC-62271"],  # Kariba dam
    "IDI053-2": ["XI-IATI-EC_INTPA-2021-ACT-63498", "XI-IATI-EC_INTPA-2024-PC-36489"],  # JETP Senegal
    "IDI158-2": ["XI-IATI-EC_INTPA-2026-PC-62902"],                                   # JETP South Africa
    "GGPID92": ["XI-IATI-EC_INTPA-2024-PC-37650", "XI-IATI-EC_INTPA-2024-PC-37989",
                "XI-IATI-EC_INTPA-2024-PC-35851", "XI-IATI-EC_INTPA-2024-PC-36723"],  # digital regulators
    "IDI048-3": ["XI-IATI-EC_INTPA-2026-PC-72554"],                                   # Nigeria digital package
    "IDI029-1": ["XI-IATI-EC_INTPA-2026-PC-77114"],                                   # last-mile fibre, Kenya
    "IDI158-3": ["XI-IATI-EC_INTPA-2024-PC-36916", "XI-IATI-EC_INTPA-2024-PC-36918",
                 "XI-IATI-EC_INTPA-2024-PC-42954", "XI-IATI-EC_INTPA-2024-PC-43325",
                 "XI-IATI-EC_INTPA-2026-PC-87868", "XI-IATI-EC_INTPA-2026-PC-76942",
                 "XI-IATI-EC_INTPA-2024-PC-36596"],                                   # Africa-EU space partnership
    "IDI257-1": ["XI-IATI-EC_INTPA-2025-PC-52458"],                                   # Yaoundé bypass studies
    # NaturAfrica: every record whose title or decision names the programme
    "IDI238-1": "NaturAfrica",
}
# The EIB's operations that name the same works as a flagship, checked by hand
# on 2026-10-24 the same way (the Bank's titles are short: a plant, a line, a
# programme). Left out: the Olkaria I extension (the same plant, earlier works
# than the flagship's uprating), the Rabat-Salé tram extension (the flagship is
# a bus network), Kenya Power's last-mile electricity (the flagship is digital)
# and a 2024 Guinea-Bissau road-corridor loan that probably, but not plainly,
# covers the Bissau-Senegal border road.
EIB_MATCHES = {
    "IDI166-1": ["XM-DAC-918-3-20150526-85142"],    # Nachtigal hydropower plant
    "IDI024-2": ["XM-DAC-918-3-20180417-89754"],    # Kpong dam retrofit
    "IDI239-4": ["XM-DAC-918-3-20161007-87292"],    # Dakar BRT
    "IDI239-1": ["XM-DAC-918-3-20210403-93698"],    # Dakar public transport network
    "GGPID111": ["XM-DAC-918-3-20210449-93759"],    # ONCF rail rehabilitation
    "GGPID126": ["XM-DAC-918-3-20080432-87503"],    # Port Victoria
    "GGPID107": ["XM-DAC-918-3-20180764-90359"],    # Tanta-El Mansoura-Damietta railway
    "IDI316-1": ["XM-DAC-918-3-20210635-94002"],    # Green Sustainable Industries, Egypt
    "IDI353-1": ["XM-DAC-918-3-20170028-87375"],    # ELMED, filed as STEG's Tunisia-Italy interconnection
    "IDI427-1": ["XM-DAC-918-3-20210166-93435"],    # Medusa cable (cancelled or suspended: not counted)
}


def nfold(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def area_of(s):
    s = nfold(s).lower()
    for a in AREAS:
        if s == a.lower():
            return a
    return nfold(s).capitalize() if s else None


# ------------------------------------------------------------ fetch

def get(url, timeout=90, tries=10):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read(), r.headers.get("Last-Modified")
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            wait = int(float(e.headers.get("Retry-After") or 0)) or 30 * (attempt + 1)
            print(f"   429, waiting {max(min(wait, 300), 60)} s")
            time.sleep(max(min(wait, 300), 60))
    sys.exit(f"gave up on {url}: still throttled")


def page_path(url):
    return CACHE / "pages" / (hashlib.md5(url.encode()).hexdigest()[:12] + ".html")


def african_listing(places):
    """Whether the Commission's map lists a flagship anywhere that can be
    African: an African country, or its Sub-Saharan Africa or Mediterranean
    region point. Only these flagships' pages are read."""
    return any(ISO.get(p) in AF or p in REGION_POINT for p in places)


def fetch():
    (CACHE / "pages").mkdir(parents=True, exist_ok=True)
    body, lm = get(WIDGET)
    (CACHE / "widget.json").write_bytes(body)
    body2, lm2 = get(TRACKER)
    (CACHE / "tracker.xlsx").write_bytes(body2)
    (CACHE / "fetched.json").write_text(json.dumps({"fetched": today(), "widget_modified": lm,
                                                    "tracker_modified": lm2}))
    w = json.loads(body)
    places = collections.defaultdict(list)
    for layer in ("country_layer", "regional_layer"):
        for f in w[layer]["features"]:
            for p in f["properties"]["projects"]:
                places[(p["projects_link"] or "").strip()].append(nfold(f["properties"]["country"]))
    links = sorted(u for u, pl in places.items() if u and african_listing(pl))
    todo = [u for u in links if not page_path(u).exists()]
    print(f"widget: {len(links)} project pages, {len(todo)} not cached")
    for i, u in enumerate(todo, 1):
        try:
            page_path(u).write_bytes(get(u)[0])
        except (urllib.error.URLError, TimeoutError) as e:
            # a dead link on the map: the flagship keeps the map's own fields
            print(f"   skipped {u}: {e}")
        if i % 25 == 0:
            print(f"   {i}/{len(todo)}")
        time.sleep(4)


def clean(s):
    s = re.sub(r"<br\s*/?>|</(p|li)>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    return [nfold(x) for x in s.split("\n") if nfold(x)]


def parse_page(s):
    """A project page's "Key information" list and its milestones."""
    out = {}
    m = re.search(r'<dl\s+class="ecl-description-list[^"]*"[^>]*>(.*?)</dl>', s, re.S)
    if m:
        for dt, dd in re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", m.group(1), re.S):
            out[" ".join(clean(dt))] = clean(dd)
    ms = re.search(r'>Milestones</h2>.*?<div class="ecl">(.*?)</div>', s, re.S)
    out["Milestones"] = clean(ms.group(1)) if ms else []
    return out


def split_list(vals):
    return [nfold(x) for v in vals for x in re.split(r"\s*;\s*", v) if nfold(x)]


def tracker_regions():
    """The tracker's first sheet: region, EUR million (its 'Commission' and
    'Rest of Team Europe' columns summed; the first is 0 throughout)."""
    z = zipfile.ZipFile(CACHE / "tracker.xlsx")
    strs = [re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S)]
    rows = []
    for row in re.findall(r"<row[^>]*>(.*?)</row>", z.read("xl/worksheets/sheet1.xml").decode(), re.S):
        cells = []
        for attrs, body in re.findall(r"<c ([^>]*)>(.*?)</c>", row, re.S):
            v = re.search(r"<v>(.*?)</v>", body)
            v = v.group(1) if v else ""
            cells.append(strs[int(v)] if 't="s"' in attrs else v)
        rows.append(cells)
    head, out = rows[0], {}
    assert head[0] == "Region", f"tracker sheet changed: {head}"
    for r in rows[1:]:
        out[html.unescape(r[0])] = sum(float(x or 0) for x in r[1:])
    return out


def records():
    """The African flagships, one per Commission identifier."""
    w = json.loads((CACHE / "widget.json").read_text())
    meta = json.loads((CACHE / "fetched.json").read_text())
    by_id, unknown, title_clash = {}, collections.Counter(), []
    for layer in ("country_layer", "regional_layer"):
        for f in w[layer]["features"]:
            where = nfold(f["properties"]["country"])
            iso = ISO.get(where)
            if layer == "country_layer" and not iso:
                unknown[where] += 1
            for p in f["properties"]["projects"]:
                pid = nfold(p["project_id"])
                r = by_id.get(pid)
                if r is None:
                    r = by_id[pid] = {"id": pid, "title": nfold(p["title"]), "description": nfold(p["description"]),
                                      "scope": nfold(p["scope"]), "area_map": area_of(p["areas_of_partnerships"]),
                                      "url": (p["projects_link"] or "").strip() or None, "listed_in": [], "listed_iso": []}
                elif nfold(p["title"]) != r["title"]:
                    title_clash.append((pid, r["title"], nfold(p["title"])))
                r["listed_in"].append(where)
                if iso:
                    r["listed_iso"].append(iso)
                if not r["url"] and p["projects_link"]:
                    r["url"] = p["projects_link"].strip()
    page_names = collections.Counter()
    out = []
    for r in by_id.values():
        info = {}
        if r["url"] and page_path(r["url"]).exists():
            info = parse_page(page_path(r["url"]).read_text(encoding="utf-8", errors="replace"))
        named = split_list(info.get("Countries", []))
        for n in named:
            if n not in ISO:
                page_names[n] += 1
        focus = split_list(info.get("Geographical focus", []))
        isos = list(dict.fromkeys([i for i in r["listed_iso"] if i in AF] + [ISO[n] for n in named if ISO.get(n) in AF]))
        regions = [x for x in r["listed_in"] if x in REGION_POINT]
        if not african_listing(r["listed_in"]):
            continue
        # the Mediterranean point mixes North Africa with the Middle East: keep those its page puts in Africa
        if (not any(i in AF for i in r["listed_iso"]) and "Sub-Saharan Africa" not in regions
                and not (isos or AFRICAN_FOCUS & set(focus))):
            continue
        team = list(dict.fromkeys(MEMBER_FIX.get(m, m) for m in split_list(info.get("Team Europe members involved", []))))
        areas = [area_of(a) for a in split_list(info.get("Global Gateway areas of partnerships", []))] or [r["area_map"]]
        kind = nfold(" ".join(info.get("Type of initiative", []))) or r["scope"]
        out.append({
            "id": r["id"], "ids": [x.strip() for x in r["id"].split(",") if x.strip()],
            "initiative_id": nfold(" ".join(info.get("Initiative ID", []))) or None,
            "title": r["title"], "description": r["description"], "areas": areas, "area": areas[0],
            "type": kind, "focus": focus, "countries": isos,
            "countries_outside": [n for n in named if n in ISO and ISO[n] not in AF] + [n for n in named if n not in ISO],
            "regions": regions, "team": team, "milestones": info.get("Milestones", []),
            "url": r["url"], "page_read": bool(info),
        })
    out.sort(key=lambda x: (AREAS.index(x["area"]) if x["area"] in AREAS else 9, x["title"]))
    # every name that is not African lands here; read the lists after a fetch for a new spelling of an African one
    if unknown and "--verbose" in sys.argv:
        print("   map names not matched (taken as outside Africa):", ", ".join(sorted(unknown)))
    if page_names and "--verbose" in sys.argv:
        print("   page country names not matched (outside Africa?):", ", ".join(sorted(page_names)))
    for pid, a, b in title_clash:
        print(f"   {pid}: two titles on the map, kept the first: {a!r} / {b!r}")
    return out, meta


def point_of(x):
    """The one point the data file keeps per flagship: precision 2 the
    country's interior point, 3 for a flagship of several countries or none,
    the Commission's Africa-wide point in Chad that the map's EU layer uses
    for regional programmes (one point for all of them, never one at sea)."""
    if len(x["countries"]) == 1:
        lon, lat = centre(x["countries"][0])
        return (lon, lat), 2, NAME[x["countries"][0]]
    return REGION.eu_region_point, 3, REGION.eu_point_note


def write_geojson(recs, meta):
    feats = []
    for x in recs:
        (lon, lat), prec, where = point_of(x)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {
            "source": "European Commission, Global Gateway flagship projects", "publisher": "European Commission",
            "layer": "global_gateway", "kind": "flagship", "name": x["title"], "description": x["description"],
            "country": x["countries"][0] if len(x["countries"]) == 1 else None, "countries": x["countries"],
            "countries_outside": x["countries_outside"], "region": x["focus"][0] if x["focus"] else None,
            "sector": SECTOR_FIX.get(x["id"]) or AREA_SECTOR.get(x["area"], "other"), "area": x["area"],
            "areas": x["areas"], "initiative_type": x["type"], "geo_precision": prec,
            "location_name": where, "team_europe": x["team"], "milestones": x["milestones"],
            "project_id": x["id"], "project_ids": x["ids"], "initiative_id": x["initiative_id"],
            "listed_under": x["regions"], "project_url": x["url"], "page_read": x["page_read"],
            "commitment": None, "dash_status": None}})
    regions = tracker_regions()
    doc = {"type": "FeatureCollection",
           "meta": {"fetched": meta["fetched"], "widget": WIDGET, "widget_modified": meta["widget_modified"],
                    "tracker": TRACKER, "tracker_modified": meta["tracker_modified"],
                    "tracker_eur_m": regions, "licence": "CC BY 4.0", "licence_url": LEGAL,
                    "attribution": "© European Union; flagship list, project pages and tracker of the European Commission"},
           "features": feats}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    print(f"→ {OUT.relative_to(ROOT)}  {len(feats)} flagships")


# ------------------------------------------------------------ the EU layer

def eu_layer():
    return [f["properties"] for f in json.loads(EU_LAYER.read_text())["features"]]


def matched(recs, layer):
    """The layer's records paired with each flagship (MATCHES, then
    EIB_MATCHES), the Commission's first; an identifier the layer no longer
    has is reported and dropped."""
    by_id = {p["iati_id"]: p for p in layer}
    known = {x["id"] for x in recs}
    out = {}
    for table, name in ((MATCHES, "MATCHES"), (EIB_MATCHES, "EIB_MATCHES")):
        for fid, ids in table.items():
            if fid not in known:
                print(f"   {name}: flagship {fid} is not on the list any more")
                continue
            if isinstance(ids, str):
                rows = [p for p in layer if p["lender"] == "European Commission"
                        and re.search(ids, html.unescape((p["name"] or "") + " " + (p.get("parent_name") or "")), re.I)]
            else:
                gone = [i for i in ids if i not in by_id]
                if gone:
                    print(f"   {name}: {fid}: not in the EU layer any more: {', '.join(gone)}")
                rows = [by_id[i] for i in ids if i in by_id]
            if rows:
                out.setdefault(fid, []).extend(rows)
    return out


def stamp_pairs(recs, layer):
    """Write each flagship's paired records into the data file, one
    institution at a time (count, euros counted, records with no counted
    amount, identifiers), so the map's layer can show them on the card. Run on
    every build: a change to MATCHES or to the EU layer reaches the file."""
    pairs = matched(recs, layer)
    doc = json.loads(OUT.read_text())
    for f in doc["features"]:
        p = f["properties"]
        ec, eib = split(pairs.get(p["project_id"]) or [])
        for key, rows in (("paired_ec", ec), ("paired_eib", eib)):
            p[key] = ({"records": len(rows), "eur_m": round(eur_m(rows), 2),
                       "not_counted": sum(1 for r in rows if not r["commitment"]),
                       "iati_ids": [r["iati_id"] for r in rows]} if rows else None)
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    if text != OUT.read_text():
        OUT.write_text(text)
        print(f"   paired records written to {OUT.name}: {sum(1 for f in doc['features'] if f['properties']['paired_ec'])} "
              f"flagships with Commission records, {sum(1 for f in doc['features'] if f['properties']['paired_eib'])} with EIB")


def is_eib(p):
    return p["lender"] != "European Commission"


def split(rows):
    """A flagship's paired records as (Commission's, EIB's)."""
    return [p for p in rows if not is_eib(p)], [p for p in rows if is_eib(p)]


def names_gg(p):
    return bool(re.search(r"global\s+gateway", " ".join(str(p.get(k) or "") for k in ("name", "description", "parent_name")), re.I))


STOP = set("""about across africa african along also among based between build building capacity centre city
climate construction corridor countries country development digital economic education energy expansion
european financing gateway global green health improve improving increase infrastructure initiative investment
investments national network networks partnership phase plant power programme project projects public region
regional renewable research rural sector services skills support supporting sustainable system systems through
transport water while within youth access local level which their other first second third """.split())


def candidates(recs, layer):
    """Possible flagship-to-record pairs for a hand check: same country, and a
    distinctive word of the flagship's title in the record's title or parent."""
    words = lambda s: {w for w in re.findall(r"[a-zà-ÿ]{5,}", html.unescape(s or "").lower()) if w not in STOP}
    names = {n.lower() for n in list(NAME.values()) + list(ALIAS)}
    ec = [p for p in layer if p["lender"] == "European Commission"]
    text = {id(p): words((p["name"] or "") + " " + (p.get("parent_name") or "")) for p in ec}
    df = collections.Counter(w for t in text.values() for w in t)
    out = []
    for x in recs:
        # a word of the title that few records share: a place, a plant, a programme's name
        tw = {w for w in words(x["title"]) - {w for n in names for w in n.split()} if df[w] <= 6}
        if not tw:
            continue
        for p in ec:
            if x["countries"] and p["country"] and p["country"] not in x["countries"]:
                continue
            hit = tw & text[id(p)]
            if hit:
                out.append((x["id"], x["title"], p["iati_id"], p["name"], p["country"], p["commitment"], sorted(hit)))
    return out


# ------------------------------------------------------------ the page

def cname(iso):
    return NAME.get(iso, iso)


def spread(n, i, step=7.0):
    """The i-th of n markers around a point, a sunflower spiral (px)."""
    if n == 1:
        return 0.0, 0.0
    r = step * math.sqrt(i + 0.5)
    a = i * 2.39996323
    return r * math.cos(a), r * math.sin(a)


def eur_m(rows):
    return sum(p["commitment"] or 0 for p in rows) / 1e6


def paired_text(rows):
    """The paired records' money, one institution at a time, never summed."""
    ec, eib = split(rows)
    parts = []
    if ec:
        n0 = sum(1 for p in ec if not p["commitment"])
        parts.append(f"Commission EUR {eur_m(ec):,.1f} m in {len(ec)} record{'s' if len(ec) != 1 else ''}"
                     + (f", {n0} with no amount yet" if n0 else ""))
    if eib:
        n0 = sum(1 for p in eib if not p["commitment"])
        parts.append(f"EIB EUR {eur_m(eib):,.1f} m in {len(eib)} operation{'s' if len(eib) != 1 else ''}"
                     + (f", {n0} not counted (cancelled or suspended)" if n0 else ""))
    return "; ".join(parts)


def tip(x, iso=None, rows=None):
    others = [cname(i) for i in x["countries"] if i != iso]
    where = cname(iso) if iso else (x["regions"][0] if x["regions"] else "Africa-wide")
    if others:
        where += (" and " if len(others) == 1 else ", with ") + (others[0] if len(others) == 1 else f"{len(others)} more")
    team = ", ".join(x["team"]) if x["team"] else "not given"
    money = f"<br>EU records on the map: {esc(paired_text(rows))}" if rows else ""
    return (f"<b>{esc(x['title'])}</b>{esc(where)} · {esc(x['area'] or '')}<br>{esc(x['type'])} flagship · "
            f"Team Europe: {esc(team)}{money}<br>Commission id {esc(x['id'])}")


def map_groups(recs, pairs):
    pts = collections.defaultdict(list)
    for x in recs:
        if x["countries"]:
            for iso in x["countries"]:
                pts[iso].append((x, iso))
        else:
            pts["africa"].append((x, None))
    groups = {(a, r): [] for a in AREAS for r in (False, True)}
    for key, items in pts.items():
        lon, lat = REGION.eu_region_point if key == "africa" else centre(key)
        cx, cy = px(lon, lat)
        items.sort(key=lambda t: (len(t[0]["countries"]) > 1, AREAS.index(t[0]["area"]) if t[0]["area"] in AREAS else 9))
        right = max(range(len(items)), key=lambda i: spread(len(items), i)[1])
        for i, (x, iso) in enumerate(items):
            dx, dy = spread(len(items), i)
            regional = len(x["countries"]) != 1
            area = x["area"] if x["area"] in AREAS else "Climate and energy"
            it = {"x": round(cx + dx, 1), "y": round(cy + dy, 1), "r": 4.6 if regional else 5,
                  "cls": f"ga {AREA_KEY[area]}" + (" gr" if regional else ""), "tip": tip(x, iso, pairs.get(x["id"]))}
            # the Africa-wide stack is not a country's: say so beside its lowest dot
            if key == "africa" and i == right:
                it["label"] = f"{len(items)} Africa-wide"
            groups[(area, regional)].append(it)
    out = []
    for (a, r), items in groups.items():
        if items:
            out.append({"id": f"g-{AREA_KEY[a]}{'-r' if r else ''}", "kind": "circle", "items": items})
    return out


def team_counts(recs):
    c = collections.Counter(m for x in recs for m in x["team"])
    return c.most_common()


def flagship_table(recs, pairs):
    rows = []
    for x in sorted(recs, key=lambda x: (cname(x["countries"][0]) if len(x["countries"]) == 1 else "~", x["title"])):
        where = (", ".join(cname(i) for i in x["countries"]) if x["countries"]
                 else esc(x["regions"][0] if x["regions"] else "Africa-wide"))
        if x["countries_outside"]:
            where += f' <span class="dim">+ {esc(", ".join(x["countries_outside"]))}</span>'
        title = (f'<a href="{esc(x["url"])}" target="_blank" rel="noopener noreferrer">{esc(x["title"])}</a>'
                 if x["url"] else esc(x["title"]))
        ms = x["milestones"]
        mtext = (esc(ms[0]) + (f' <span class="dim">(+{len(ms) - 1})</span>' if len(ms) > 1 else "")) if ms else "–"
        mattr = f' title="{esc(" · ".join(ms))}"' if len(ms) > 1 else ""
        ec, eib = split(pairs.get(x["id"]) or [])
        rows.append([td(title, "name"), td(where),
                     td(f'<i class="gk ga-{AREA_KEY.get(x["area"], "energy")}"></i>{esc(x["area"])}', "area"),
                     td(esc(x["type"])), td(esc(", ".join(x["team"])) if x["team"] else "–"),
                     td(f'<span class="mono">{esc(x["initiative_id"] or x["id"])}</span>'),
                     f'<td{mattr}>{mtext}</td>',
                     td(f'{eur_m(ec):,.1f}' if ec else "–", "num"), td(f'{eur_m(eib):,.1f}' if eib else "–", "num")])
    return table(f"The {len(recs)} Global Gateway flagships the Commission lists in Africa",
                 ["Flagship", "Countries", "Area", "Type", "Team Europe members named", "Id", "Milestones on the page",
                  "#Commission records, EUR m", "#EIB operations, EUR m"], rows)


def paired_table(recs, pairs):
    by = {x["id"]: x for x in recs}
    rows = []
    # the larger institution's figure orders the rows; the two are never added
    for fid, prs in sorted(pairs.items(), key=lambda kv: -max(eur_m(s) for s in split(kv[1]))):
        x = by[fid]
        ec, eib = split(prs)
        names = "; ".join(("EIB: " if is_eib(p) else "") + nfold(html.unescape(p["name"] or ""))[:80] for p in (eib + ec)[:3])
        if len(prs) > 3:
            names += f" … and {len(prs) - 3} more"
        cell = lambda rs: (td(str(len(rs)), "num"), td(f"{eur_m(rs):,.1f}", "num")) if rs else (td("–", "num"), td("–", "num"))
        rows.append([td(esc(x["title"]), "name"),
                     td(", ".join(cname(i) for i in x["countries"]) or esc(x["regions"][0] if x["regions"] else "Africa-wide")),
                     *cell(ec), *cell(eib), td(str(sum(1 for p in prs if not p["commitment"])) or "0", "num"),
                     td(first_year(prs), "num"), td(esc(names))])
    return table(f"The {len(pairs)} flagships paired with the EU institutions' records on the map",
                 ["Flagship", "Countries", "#Commission records", "#Commission EUR m", "#EIB operations",
                  "#EIB EUR m", "#Not counted", "#First start", "The records"], rows)


def first_year(rows):
    """The earliest start year among the records; the Commission files 2100
    for activities still in preparation, which is no year."""
    ys = [int(p["start_year"]) for p in rows if str(p["start_year"] or "").isdigit() and int(p["start_year"]) < 2100]
    return str(min(ys)) if ys else "–"


def layer_table(rows):
    out = []
    for p in sorted(rows, key=lambda p: -(p["commitment"] or 0)):
        link = (f'<a href="https://d-portal.org/ctrack.html?aid={esc(p["iati_id"])}" target="_blank" '
                f'rel="noopener noreferrer">IATI</a>')
        out.append([td(esc(nfold(html.unescape(p["name"] or "")))[:140], "name"),
                    td(esc(cname(p["country"])) if p["country"] else '<span class="dim">regional</span>'),
                    td(esc(nfold(html.unescape(p.get("parent_name") or ""))[:90]) or "–"),
                    td(f'{p["commitment"] / 1e6:,.1f}' if p["commitment"] else "–", "num"),
                    td(esc(p["start_year"] or "–"), "num"), td(link)])
    return table(f"The {len(rows)} records of the map's EU layer that name Global Gateway",
                 ["Record", "Country", "Under the decision", "#EUR m", "#Start", "Source"], out)


def head_figure(recs):
    n = collections.Counter(i for x in recs for i in x["countries"])
    fill = {iso: ("var(--gg-3)" if v >= 6 else "var(--gg-2)" if v >= 3 else "var(--gg-1)") for iso, v in n.items()}
    titles = {iso: f"{cname(iso)}: {v} flagship{'s' if v != 1 else ''}" for iso, v in n.items()}
    svg = africa_map(fill, titles, "Map of Africa with the countries the Commission's Global Gateway flagships name, "
                                   "shaded by how many")
    keys = ('<span class="keys"><span class="dk"><i class="gk" style="background:var(--gg-1)"></i>1–2</span>'
            '<span class="dk"><i class="gk" style="background:var(--gg-2)"></i>3–5</span>'
            '<span class="dk"><i class="gk" style="background:var(--gg-3)"></i>6 or more</span></span>')
    return figure(svg, f"{len(n)} countries", "named by at least one flagship on the Commission's list, shaded by how many",
                  keys)


def build_page(recs, meta, layer):
    n = len(recs)
    countries = collections.Counter(i for x in recs for i in x["countries"])
    by_area = collections.Counter(x["area"] for x in recs)
    by_type = collections.Counter(x["type"] for x in recs)
    team = team_counts(recs)
    with_team = [x for x in recs if x["team"]]
    beyond = [x for x in with_team if set(x["team"]) - {"European Commission"}]
    states = [x for x in with_team if set(x["team"]) - {"European Commission"} - BANKS]
    banks = [x for x in with_team if set(x["team"]) & BANKS]
    ms = sum(1 for x in recs if x["milestones"])
    gg = [p for p in layer if names_gg(p)]
    gg_eur = sum(p["commitment"] or 0 for p in gg)
    gg_noamount = sum(1 for p in gg if not p["commitment"])
    reg = meta["tracker_eur_m"]
    total = sum(reg.values())
    ssa = reg.get("Sub-Saharan Africa", 0)
    mena = next((v for k, v in reg.items() if k.startswith("Middle East")), 0)
    top_ctry = countries.most_common(3)
    top_area = by_area.most_common(1)[0]
    member_states = [m for m, _ in team if m not in BANKS | {"European Commission"}]
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
    pairs = matched(recs, layer)
    paired = list({p["iati_id"]: p for rows in pairs.values() for p in rows}.values())
    p_ec, p_eib = split(paired)
    f_ec = [f for f, rows in pairs.items() if split(rows)[0]]
    f_eib = [f for f, rows in pairs.items() if split(rows)[1]]
    old = [p for p in paired if str(p["start_year"] or "").isdigit() and int(p["start_year"]) < 2021]
    o_ec, o_eib = split(old)
    no_page = sum(1 for x in recs if not x["page_read"])
    regional = sum(1 for x in recs if len(x["countries"]) != 1)
    no_country = sum(1 for x in recs if not x["countries"])
    tokens = {
        "__N__": str(n), "__N_COUNTRIES__": str(len(countries)),
        "__N_COUNTRY_LEVEL__": str(by_type.get("Country level", 0)), "__N_REGIONAL__": str(by_type.get("Regional", 0)),
        "__N_GLOBAL__": words.get(by_type.get("Global", 0), str(by_type.get("Global", 0))),
        "__N_DRAWN_REGIONAL__": str(regional),
        "__N_NOCTRY__": words.get(no_country, str(no_country)).capitalize() if no_country < 10 else str(no_country),
        "__TOP_AREA__": top_area[0].lower(), "__TOP_AREA_N__": str(top_area[1]),
        "__TOP_AREA_PCT__": f"{100 * top_area[1] / n:.0f}",
        "__AREA_LIST__": ", ".join(f"{a.lower()} {by_area.get(a, 0)}" for a in AREAS),
        "__TOP_CTRY__": ", ".join(f"{cname(i)} ({v})" for i, v in top_ctry),
        "__N_TEAM__": str(len(with_team)), "__N_BEYOND__": str(len(beyond)), "__N_STATES__": str(len(states)),
        "__N_BANKS__": str(len(banks)), "__N_MEMBERS__": str(len(member_states)),
        "__TOP_MEMBERS__": ", ".join(f"{m} ({v})" for m, v in [t for t in team if t[0] != "European Commission"][:6]),
        "__N_EC__": str(dict(team).get("European Commission", 0)),
        "__N_MILESTONES__": str(ms), "__N_NO_PAGE__": words.get(no_page, str(no_page)),
        "__TRACKER_TOTAL__": f"{total / 1000:,.1f}", "__TRACKER_SSA__": f"{ssa / 1000:,.1f}",
        "__TRACKER_SSA_PCT__": f"{100 * ssa / total:.0f}", "__TRACKER_MENA__": f"{mena / 1000:,.1f}",
        "__TRACKER_SSA_USD__": f"{ssa * EUR_USD / 1000:,.1f}",
        "__GG_N__": str(len(gg)), "__GG_EUR_M__": f"{gg_eur / 1e6:,.0f}", "__GG_NOAMOUNT__": str(gg_noamount),
        "__GG_USD_M__": f"{gg_eur * EUR_USD / 1e6:,.0f}", "__EUR_NOTE__": esc(EUR_NOTE),
        "__N_MATCHED__": str(len(pairs)),
        "__N_MATCHED_EC__": str(len(f_ec)), "__MATCHED_EC_RECS__": str(len(p_ec)),
        "__MATCHED_EC_EUR_M__": f"{eur_m(p_ec):,.0f}", "__MATCHED_EC_NOAMOUNT__": str(sum(1 for p in p_ec if not p["commitment"])),
        "__N_MATCHED_EIB__": words.get(len(f_eib), str(len(f_eib))), "__MATCHED_EIB_RECS__": str(len(p_eib)),
        "__MATCHED_EIB_EUR_M__": f"{eur_m(p_eib):,.0f}",
        "__MATCHED_EIB_NOAMOUNT__": str(sum(1 for p in p_eib if not p["commitment"])),
        "__MATCHED_BOTH__": (lambda k: "none has" if k == 0 else "one has" if k == 1
                             else f"{words.get(k, str(k))} have")(len(set(f_ec) & set(f_eib))),
        "__MATCHED_OLD__": (f"{words.get(len(old), str(len(old))).capitalize()} of these records started before 2021, the first "
                            f"year the tracker counts (the Commission's EUR {eur_m(o_ec):,.1f} m and the EIB's EUR "
                            f"{eur_m(o_eib):,.1f} m): the list takes in works the EU was funding before Global Gateway "
                            f"began." if old else "None of these records started before 2021, the first year the tracker counts."),
        "__MATCHED_GG__": (lambda k: "none of them is" if k == 0 else "one of them is" if k == 1
                           else f"{words.get(k, k)} of them are")(sum(1 for p in paired if names_gg(p))),
        "__TABLE_PAIRED__": paired_table(recs, pairs),
        "__FETCHED__": fmt_date(meta["fetched"]),
        "__WIDGET_MODIFIED__": esc(meta["widget_modified"] or "not stated"),
        "__TRACKER_MODIFIED__": esc(meta["tracker_modified"] or "not stated"),
        "__GG_PAGE__": esc(GG_PAGE), "__LIST_PAGE__": esc(LIST_PAGE), "__TRACKER_PAGE__": esc(TRACKER_PAGE),
        "__LEGAL__": esc(LEGAL), "__WIDGET__": esc(WIDGET),
        "__TABLE_FLAGSHIPS__": flagship_table(recs, pairs), "__TABLE_LAYER__": layer_table(gg),
        "__LEGEND__": "".join(
            f'<label><input type="checkbox" data-g="g-{AREA_KEY[a]},g-{AREA_KEY[a]}-r" checked>'
            f'<span class="sw ga-{AREA_KEY[a]}"></span>{esc(a)} <span class="dim">{by_area.get(a, 0)}</span></label>'
            for a in AREAS),
    }
    charts = {
        "c-area": {"type": "bars", "fmt": "n", "rows": [{"label": a, "value": by_area.get(a, 0),
                                                        "text": str(by_area.get(a, 0))} for a in AREAS]},
        "c-ctry": {"type": "bars", "fmt": "n", "rows": [{"label": cname(i), "value": v, "text": str(v)}
                                                       for i, v in countries.most_common(14)]},
        "c-team": {"type": "bars", "fmt": "n", "rows": [{"label": m, "value": v, "text": str(v)}
                                                       for m, v in team[:14]]},
    }
    return tokens, {"map": {"groups": map_groups(recs, pairs)}, "charts": charts}


def jsonld(path):
    page = {"@context": "https://schema.org", "@type": "WebPage", "@id": site_url(path), "url": site_url(path),
            "name": TITLE, "description": DESCRIPTION, "inLanguage": "en",
            "isPartOf": {"@type": "WebSite", "@id": site_url("#website"), "name": SITE_NAME, "url": SITE_URL},
            "author": {"@type": "Person", "name": AUTHOR_NAME, "url": WEB_URL, "sameAs": [AUTHOR_URL]},
            "about": {"@type": "Place", "name": "Africa"},
            "isBasedOn": {"@type": "Dataset", "name": "Global Gateway flagship projects", "url": LIST_PAGE,
                          "publisher": {"@type": "Organization", "name": "European Commission"},
                          "license": "https://creativecommons.org/licenses/by/4.0/"}}
    return ('<script type="application/ld+json">'
            + json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n")


def load():
    doc = json.loads(OUT.read_text())
    recs = []
    for f in doc["features"]:
        p = f["properties"]
        recs.append({"id": p["project_id"], "ids": p["project_ids"], "initiative_id": p["initiative_id"],
                     "title": p["name"], "description": p["description"], "areas": p["areas"], "area": p["area"],
                     "type": p["initiative_type"], "focus": [p["region"]] if p["region"] else [],
                     "countries": p["countries"], "countries_outside": p["countries_outside"],
                     "regions": p["listed_under"], "team": p["team_europe"], "milestones": p["milestones"],
                     "url": p["project_url"], "page_read": p["page_read"]})
    return recs, doc["meta"]


def build():
    if "--fetch" in sys.argv:
        fetch()
    if "--fetch" in sys.argv or "--parse" in sys.argv or not OUT.exists():
        if not (CACHE / "widget.json").exists():
            sys.exit("no cached Commission map: run python3 build_global_gateway.py --fetch")
        recs, meta = records()
        write_geojson(recs, meta)
    recs, meta = load()
    layer = eu_layer()
    stamp_pairs(recs, layer)
    if "--candidates" in sys.argv:
        for c in candidates(recs, layer):
            print(" | ".join(str(v) for v in c))
        return
    tokens, payload = build_page(recs, meta, layer)
    tokens.update({"__TITLE__": esc(TITLE), "__MAP_W__": f"{MAP_W:.0f}", "__MAP_H__": f"{MAP_H:.0f}",
                   "__DATA_URL__": site_url("data/global_gateway.geojson"), "__DATA_FILE__": "global_gateway.geojson",
                   "__BUILT__": fmt_date(today())})
    page = FRAME.read_text().replace("<!--__BODY__-->", head_wrap(FRAG.read_text(), head_figure(recs)), 1)
    # the longest tokens first, so __N__ never eats the head of a longer one
    for k in sorted(tokens, key=len, reverse=True):
        page = page.replace(k, tokens[k])
    page = page.replace("<!--__LAND__-->", land_paths(), 1)
    page = page.replace("/*__PAYLOAD__*/", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                        .replace("</", "<\\/"), 1)
    page = brand_assets(page, donor=SLUG)
    left = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]*__", page)))
    if left:
        sys.exit(f"global gateway: unfilled tokens {', '.join(left)}")
    path = f"{SLUG}/index.html"
    doc = wrap_document(page, title=TITLE, description=DESCRIPTION, path=path, kind="profile", extra_head=jsonld(path))
    (DOCS / SLUG).mkdir(parents=True, exist_ok=True)
    (DOCS / SLUG / "index.html").write_text(doc)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(OUT, DOCS / "data" / OUT.name)
    print(f"→ docs/{path}  {len(doc.encode()) / 1024:.0f} KB  (+ docs/data/{OUT.name})")


if __name__ == "__main__":
    build()
