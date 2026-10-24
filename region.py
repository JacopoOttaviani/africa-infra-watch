#!/usr/bin/env python3
"""
The region an edition of the site covers.

One codebase, several editions: the fetchers, the builders and the templates
read everything that depends on the part of the world being mapped from
REGION, which this module picks from the AIW_REGION environment variable
(default "africa", the original site). A plain `python3 build_map.py` is the
Africa build, byte for byte; `AIW_REGION=sea python3 build_map.py` is the
Southeast Asia edition, which keeps its data in data/sea/ and its pages in
docs/se-asia/.

    AIW_REGION=sea python3 fetch_basemap.py       # once: the region's two basemaps
    AIW_REGION=sea python3 fetch_sources.py       # the layers the region has
    AIW_REGION=sea python3 check_data.py
    AIW_REGION=sea python3 build_dashboard.py && AIW_REGION=sea python3 build_map.py

What a region holds, and who reads it:
  countries     ISO codes, the publishers' spellings of the names, the dashboard
                display names, islands too small for the coarse basemap
  windows       the basemap's detail window, the OSM bands, the IATI and AidData
                placement windows, the dashboard frame and line window, the map's
                home view and zoom window, the social card's window
  lenders       the regional development bank (AfDB or ADB: its IATI publisher,
                files and conventions), the World Bank's country files, the
                Commission's country and regional files, the Commission's point
                for region-wide programmes
  layers        which of the site's layers the edition has (no Piano Mattei or
                Global Gateway flagships outside Africa, no debt box, no deep dives)
  words         the name, adjective and kicker the pages print

The Africa literals here are the ones the scripts carried until the Southeast
Asia edition (October 2026); the scripts import them back under their old
names, so the Africa build is unchanged.
"""

import os
import pathlib

ROOT = pathlib.Path(__file__).parent
# the repository's data directory: the Africa edition's data, and the caches
# every edition shares (.ne_cache, .aiddata_cache)
ROOT_DATA = ROOT / "data"
ROOT_DOCS = ROOT / "docs"


class Region:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __repr__(self):
        return f"Region({self.key})"


# ------------------------------------------------------------------ Africa

AFRICA_ISO = [
    "DZ", "AO", "BJ", "BW", "BF", "BI", "CM", "CV", "CF", "TD", "KM", "CG",
    "CD", "DJ", "EG", "GQ", "ER", "SZ", "ET", "GA", "GM", "GH", "GN", "GW",
    "CI", "KE", "LS", "LR", "LY", "MG", "MW", "ML", "MR", "MU", "MA", "MZ",
    "NA", "NE", "NG", "RW", "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SD",
    "TZ", "TG", "TN", "UG", "ZM", "ZW",
]

# the publishers' spellings the fetchers filter on (GEM's country field, the
# pipeline trackers' country lists)
AFRICA_NAMES = {
    "Algeria", "Angola", "Benin", "Botswana", "Burkina Faso", "Burundi",
    "Cameroon", "Cape Verde", "Cabo Verde", "Central African Republic", "Chad",
    "Comoros", "Congo", "Democratic Republic of Congo", "DR Congo", "Djibouti",
    "Egypt", "Equatorial Guinea", "Eritrea", "Eswatini", "Ethiopia", "Gabon",
    "Gambia", "The Gambia", "Ghana", "Guinea", "Guinea-Bissau", "Ivory Coast", "Cote d'Ivoire",
    "Côte d'Ivoire", "Kenya", "Lesotho", "Liberia", "Libya", "Madagascar",
    "Malawi", "Mali", "Mauritania", "Mauritius", "Morocco", "Mozambique",
    "Namibia", "Niger", "Nigeria", "Rwanda", "Sao Tome and Principe", "Senegal",
    "Seychelles", "Sierra Leone", "Somalia", "South Africa", "South Sudan",
    "Sudan", "Tanzania", "Togo", "Tunisia", "Uganda", "Zambia", "Zimbabwe",
    "Western Sahara", "Republic of the Congo",
}

# GEM uses country names; IATI uses ISO-3166-1 alpha-2. Bridge them. The
# order matters: the builders derive ISO -> name by first wins.
AFRICA_NAME_TO_ISO = {
    "Algeria": "DZ", "Angola": "AO", "Benin": "BJ", "Botswana": "BW",
    "Burkina Faso": "BF", "Burundi": "BI", "Cameroon": "CM",
    "Cape Verde": "CV", "Cabo Verde": "CV", "Central African Republic": "CF",
    "Chad": "TD", "Comoros": "KM", "Congo": "CG",
    "Republic of the Congo": "CG", "Democratic Republic of Congo": "CD",
    "DR Congo": "CD", "Djibouti": "DJ", "Egypt": "EG",
    "Equatorial Guinea": "GQ", "Eritrea": "ER", "Eswatini": "SZ",
    "Ethiopia": "ET", "Gabon": "GA", "Gambia": "GM", "Ghana": "GH",
    "Guinea": "GN", "Guinea-Bissau": "GW", "Ivory Coast": "CI",
    "Cote d'Ivoire": "CI", "Côte d'Ivoire": "CI", "Kenya": "KE",
    "Lesotho": "LS", "Liberia": "LR", "Libya": "LY", "Madagascar": "MG",
    "Malawi": "MW", "Mali": "ML", "Mauritania": "MR", "Mauritius": "MU",
    "Morocco": "MA", "Mozambique": "MZ", "Namibia": "NA", "Niger": "NE",
    "Nigeria": "NG", "Rwanda": "RW", "Sao Tome and Principe": "ST",
    "Senegal": "SN", "Seychelles": "SC", "Sierra Leone": "SL",
    "Somalia": "SO", "South Africa": "ZA", "South Sudan": "SS",
    "Sudan": "SD", "Tanzania": "TZ", "Togo": "TG", "Tunisia": "TN",
    "Uganda": "UG", "Zambia": "ZM", "Zimbabwe": "ZW",
    "Western Sahara": "EH", "The Gambia": "GM", "Democratic Republic of the Congo": "CD",
}

# the names the two pages display, over Natural Earth's and the GEM alias
# table's (which yields some exonyms); Somaliland and Western Sahara are
# labelled plainly as Natural Earth draws them, and three islands only
# submarine cables reach
AFRICA_DISPLAY = {"CI": "Côte d'Ivoire", "CV": "Cabo Verde", "CD": "DR Congo",
                  "CG": "Republic of the Congo", "-99": "Somaliland",
                  "EH": "Western Sahara", "TZ": "Tanzania", "SZ": "Eswatini",
                  "ST": "São Tomé and Príncipe", "GM": "The Gambia",
                  "YT": "Mayotte", "RE": "Réunion", "SH": "Saint Helena"}

# Islands too small to appear in Natural Earth 110m, drawn by the dashboard
# as markers so their projects don't float in blank ocean.
AFRICA_ISLANDS = [
    {"n": "Cabo Verde", "iso": "CV", "lon": -23.6, "lat": 15.1},
    {"n": "São Tomé and Príncipe", "iso": "ST", "lon": 6.6, "lat": 0.25},
    {"n": "Comoros", "iso": "KM", "lon": 43.3, "lat": -11.6},
    {"n": "Mauritius", "iso": "MU", "lon": 57.55, "lat": -20.3},
    {"n": "Seychelles", "iso": "SC", "lon": 55.5, "lat": -4.6},
]
# the same island states, for the fetchers: a point on the main island, since
# the coarse basemap has no polygon to take an interior point from
AFRICA_ISLAND_POINT = {"CV": (-23.6, 15.1), "ST": (6.6, 0.3), "SC": (55.45, -4.65), "MU": (57.55, -20.3), "KM": (43.35, -11.7)}

# AidData records the recipient as an ISO-3 code; the rest of the site speaks ISO-2.
AFRICA_ISO3 = {
    "DZA": "DZ", "AGO": "AO", "BEN": "BJ", "BWA": "BW", "BFA": "BF", "BDI": "BI", "CMR": "CM",
    "CPV": "CV", "CAF": "CF", "TCD": "TD", "COM": "KM", "COG": "CG", "COD": "CD", "DJI": "DJ",
    "EGY": "EG", "GNQ": "GQ", "ERI": "ER", "SWZ": "SZ", "ETH": "ET", "GAB": "GA", "GMB": "GM",
    "GHA": "GH", "GIN": "GN", "GNB": "GW", "CIV": "CI", "KEN": "KE", "LSO": "LS", "LBR": "LR",
    "LBY": "LY", "MDG": "MG", "MWI": "MW", "MLI": "ML", "MRT": "MR", "MUS": "MU", "MAR": "MA",
    "MOZ": "MZ", "NAM": "NA", "NER": "NE", "NGA": "NG", "RWA": "RW", "STP": "ST", "SEN": "SN",
    "SYC": "SC", "SLE": "SL", "SOM": "SO", "ZAF": "ZA", "SSD": "SS", "SDN": "SD", "TZA": "TZ",
    "TGO": "TG", "TUN": "TN", "UGA": "UG", "ZMB": "ZM", "ZWE": "ZW", "ESH": "EH",
}

# TeleGeography's own spellings for Africa and its islands -> ISO 3166-1. The
# cable detail carries a country per landing point; landing-point names read
# "City, Country" with commas inside some countries ("Congo, Dem. Rep."), so
# the fetcher's fallback matches by suffix.
AFRICA_TG_ISO = {
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

AFRICA = Region(
    key="africa", slug="", url_slug="",
    name="Africa", adj="African", kicker="Geopolitics of Africa",
    # "Africa, regional" on a record with no country; "African landings" on a cable
    regional_label="Africa, regional", landings_label="African landings", wide="Africa-wide",
    land="the continent", eu_point_note="the Commission's point for Africa, in Chad",
    whole="Whole continent",                     # the reset-view button's title
    data_dir=ROOT_DATA, docs_dir=ROOT_DOCS,
    basemap_110="africa_basemap.json", basemap_10m="africa_basemap_10m.json",
    iso=AFRICA_ISO, fetch_names=AFRICA_NAMES, names=AFRICA_NAME_TO_ISO, display=AFRICA_DISPLAY,
    islands=AFRICA_ISLANDS, island_point=AFRICA_ISLAND_POINT, iso3=AFRICA_ISO3, tg_iso=AFRICA_TG_ISO,
    # Natural Earth files Mauritius and Seychelles under "Seven seas"
    ne_member=lambda p: p["CONTINENT"] == "Africa" or p["ADM0_A3"] in ("MUS", "SYC"),
    # Detail window of the basemap: the continent plus enough margin that the
    # Mediterranean, the Arabian peninsula and the Mascarene islands are drawn
    # with the same care.
    win=(-27.0, -41.0, 66.0, 43.0),
    # Cabo Verde to Mauritius, Tunis to the Cape: wider than the continent so a
    # site on an island is kept, narrower than the data window so that the Gulf
    # of Guinea's Null Island, Kosovo and Nepal are not.
    iati_window=(-30.0, -40.0, 65.0, 40.0),
    data_window=(-30, -45, 70, 45),             # check_data.py
    aiddata_window=(-30.0, -45.0, 70.0, 45.0),  # a footprint outside it is a mislinked OSM feature
    line_window=(-32.0, -48.0, 66.0, 50.0),     # the dashboard clips pipeline and cable routes to it
    zoom_win=(-30.0, -45.0, 70.0, 45.0),        # the map's "zoom to" fits the part of a route inside it
    osm={"lat0": -36.0, "lat1": 39.0, "lon0": -18, "lon1": 52, "band": 7.5},
    bounds={"x0": -19, "y0": -36, "x1": 53, "y1": 39},   # the dashboard frame
    center=(17, 2),                              # the map's opening centre, and the world copy that holds the region
    home_exclude=["CV", "MU", "SC"],             # far islands left out of the map's home view
    geo_box="-35.5 -25.5 37.8 57.9",             # schema.org GeoShape, south west north east
    social_win=(-18.5, 52.0, -35.5, 37.8),       # lon0, lon1, lat0, lat1 of the link-preview card
    bank={"publisher": "afdb", "code": "AfDB", "name": "African Development Bank",
          "group": "African Development Bank Group", "home": "https://www.afdb.org/",
          "registry": "https://d-portal.iatistandard.org/ctrack.html?publisher=XM-DAC-46002#view=main", "lic": "CC BY (per the IATI Registry)",
          "files": None, "currency": "XDR", "logo": "african-development-bank"},
    wb_files=[c.lower() for c in AFRICA_ISO] + ["289", "298"],
    # the Agence française de développement, a third lender in the finance
    # layer: one IATI file per country (afd-sn …); its multi-country file
    # (afd-multipays) mixes African and other recipients and is left out
    afd_files=[c.lower() for c in AFRICA_ISO],
    # Germany's development ministry (BMZ): one IATI file per partner
    # country (bmz-ke …), every project it pays for, with the agency that
    # carries it out (GIZ, KfW, or an NGO, church or UN agency) named as
    # the extending organisation. Its regional files (189, 289, 298) place
    # nothing and are left out; there is no file for GQ, KM, MU or SC.
    bmz_files=[c.lower() for c in AFRICA_ISO],
    eu_publishers={
        "ec-intpa": {"pub": "INTPA", "lender": "European Commission",
                     "files": [c.lower() for c in AFRICA_ISO] + ["289", "298", "1027", "1028", "1029", "1030"]},
        "ec-near": {"pub": "NEAR", "lender": "European Commission",
                    "files": ["dz", "eg", "ly", "ma", "tn", "189"]},
        "eib": {"pub": "EIB", "lender": "European Investment Bank", "files": ["act"]},
    },
    # North of Sahara, South of Sahara, Africa regional, and the DAC's Eastern,
    # Middle, Southern and Western Africa, which INTPA publishes as files of their own
    eu_regions={"189", "289", "298", "1027", "1028", "1029", "1030"},
    eu_region_point=(17.7578122, 11.5024338),   # lon, lat: the Commission's point for Africa-wide activities
    eu_point_where="in Chad",
    aiddata_regions={"Africa"}, aiddata_by_iso3=False,
    layers=("assets", "finance", "ground", "pipelines", "cables", "china", "eu", "mattei", "gateway"),
    debt=True, noindex=False,
)


# ---------------------------------------------------------- Southeast Asia

# The ten ASEAN members and Timor-Leste.
SEA_ISO = ["BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN"]

# GEM's spellings (checked against the September 2026 power CSV: Brunei,
# Cambodia, Indonesia, Laos, Malaysia, Myanmar, Philippines, Singapore,
# Thailand, Timor-Leste, Vietnam) first, then the forms other publishers use.
SEA_NAME_TO_ISO = {
    "Brunei": "BN", "Brunei Darussalam": "BN",
    "Cambodia": "KH",
    "Indonesia": "ID",
    "Laos": "LA", "Lao PDR": "LA", "Lao People's Democratic Republic": "LA",
    "Malaysia": "MY",
    "Myanmar": "MM", "Myanmar (Burma)": "MM", "Burma": "MM",
    "Philippines": "PH",
    "Singapore": "SG",
    "Thailand": "TH",
    "Timor-Leste": "TL", "East Timor": "TL", "Timor Leste": "TL",
    "Vietnam": "VN", "Viet Nam": "VN",
}
SEA_ISO3 = {"BRN": "BN", "KHM": "KH", "IDN": "ID", "LAO": "LA", "MYS": "MY", "MMR": "MM",
            "PHL": "PH", "SGP": "SG", "THA": "TH", "TLS": "TL", "VNM": "VN"}
# TeleGeography's spellings (its landing-point feed, October 2026)
SEA_TG_ISO = {"Brunei": "BN", "Cambodia": "KH", "Indonesia": "ID", "Malaysia": "MY", "Myanmar": "MM",
              "Philippines": "PH", "Singapore": "SG", "Thailand": "TH", "Timor-Leste": "TL", "Vietnam": "VN"}

SEA = Region(
    key="sea", slug="se-asia", url_slug="se-asia/",
    name="Southeast Asia", adj="Southeast Asian", kicker="Geopolitics of Southeast Asia",
    regional_label="Asia, regional", landings_label="Southeast Asian landings", wide="region-wide",
    land="the region", eu_point_note="the Commission's point for the ASEAN region, in Cambodia",
    whole="Whole region",
    data_dir=ROOT_DATA / "sea", docs_dir=ROOT_DOCS / "se-asia",
    basemap_110="sea_basemap.json", basemap_10m="sea_basemap_10m.json",
    iso=SEA_ISO, fetch_names=set(SEA_NAME_TO_ISO), names=SEA_NAME_TO_ISO,
    display={"TL": "Timor-Leste", "LA": "Laos", "VN": "Vietnam", "MM": "Myanmar", "BN": "Brunei"},
    # the region's coarse basemap is cut from the 1:10m file, so Singapore has
    # a polygon of its own and no island markers are needed
    islands=[], island_point={"SG": (103.82, 1.35)}, iso3=SEA_ISO3, tg_iso=SEA_TG_ISO,
    ne_member=lambda p: p["ADM0_A3"] in {"BRN", "KHM", "IDN", "LAO", "MYS", "MMR", "PHL", "SGP", "THA", "TLS", "VNM"},
    # the Andaman Sea to western New Guinea, Timor to the Myanmar–China border
    win=(88.0, -14.0, 146.0, 30.0),
    iati_window=(88.0, -14.0, 146.0, 30.0),
    data_window=(85, -16, 150, 33),
    aiddata_window=(85.0, -16.0, 150.0, 33.0),
    line_window=(84.0, -17.0, 150.0, 34.0),
    zoom_win=(84.0, -17.0, 150.0, 34.0),
    osm={"lat0": -11.0, "lat1": 29.0, "lon0": 92, "lon1": 142, "band": 7.5},
    bounds={"x0": 91, "y0": -12, "x1": 142, "y1": 29},
    center=(116, 8),
    home_exclude=[],
    geo_box="-11 92 28.5 141",
    social_win=(92.0, 141.0, -11.0, 28.5),
    # ADB publishes IATI 2.03 files per borrowing country (asdb-id, asdb-kh …)
    # and one regional file (asdb-reg), in US dollars, every location marked
    # exactness 2 and named (a province, a town, or the country itself);
    # Malaysia, Singapore and Brunei have no file
    bank={"publisher": "asdb", "code": "ADB", "name": "Asian Development Bank",
          "group": "Asian Development Bank", "home": "https://www.adb.org/",
          "registry": "https://iatiregistry.org/publisher/asdb", "lic": "CC BY (per the IATI Registry)",
          "files": [c.lower() for c in SEA_ISO] + ["reg"], "currency": "USD", "logo": "asian-development-bank"},
    # the World Bank's files: the eight borrowers (no file for Brunei, Malaysia
    # or Singapore); its Asian regional files (619, 679) are South and Central Asia
    wb_files=[c.lower() for c in SEA_ISO],
    eu_publishers={
        "ec-intpa": {"pub": "INTPA", "lender": "European Commission",
                     "files": [c.lower() for c in SEA_ISO] + ["789", "798"]},
        "eib": {"pub": "EIB", "lender": "European Investment Bank", "files": ["act"]},
    },
    # the DAC's Far East Asia regional and Asia regional files; South and
    # Central Asia (619, 679, 689) are left out
    eu_regions={"789", "798"},
    # the point the Commission's Asia-regional file gives its "ASEAN region"
    # activities, which is its point for Cambodia
    eu_region_point=(104.869423, 13.5066394),
    eu_point_where="in Cambodia",
    aiddata_regions={"Asia"}, aiddata_by_iso3=True,
    layers=("assets", "finance", "ground", "pipelines", "cables", "china", "eu"),
    debt=False,
    # an edition in the making: built and served, linked from nowhere, kept out
    # of search until it is published (flip to False then)
    noindex=True,
)

REGIONS = {r.key: r for r in (AFRICA, SEA)}


def pick():
    key = (os.environ.get("AIW_REGION") or "africa").strip().lower()
    if key not in REGIONS:
        raise SystemExit(f"AIW_REGION={key!r}: unknown region; one of {', '.join(REGIONS)}")
    return REGIONS[key]


REGION = pick()


# The BMZ file's lender codes, by the agency that carries the project out:
# GIZ (technical cooperation), KfW (financial cooperation), and BMZ for
# every other channel (German NGOs, churches, foundations, UN agencies)
BMZ_LENDERS = ("GIZ", "KfW", "BMZ")


def region_payload(region=REGION):
    """What the two templates read as DATA.region: the words, the frame and
    the lenders of this edition. Every field has the Africa value as its
    default in the templates, so an older payload still draws."""
    bank = region.bank
    afd = bool(getattr(region, "afd_files", None))
    bmz = bool(getattr(region, "bmz_files", None))
    lenders = ([bank["code"], "WB"] + (["AFD"] if afd else []) + (list(BMZ_LENDERS) if bmz else [])
               + ["EC", "EIB", "CN"] + (["IT"] if "mattei" in region.layers else [])
               + (["GG"] if "gateway" in region.layers else []))
    family = [["Multilateral banks", [bank["code"], "WB"]], ["European Union", ["EC", "EIB"]], ["China", ["CN"]]]
    if afd:
        family.append(["France", ["AFD"]])
    if bmz:
        family.append(["Germany", list(BMZ_LENDERS)])
    if "mattei" in region.layers:
        family.append(["Italy", ["IT"]])
    # the Commission's flagship list: no money, so a family of its own beside the EU's lenders
    if "gateway" in region.layers:
        family.append(["Global Gateway", ["GG"]])
    return {
        "key": region.key, "name": region.name, "adj": region.adj, "kicker": region.kicker,
        "regional": region.regional_label, "landings": region.landings_label, "wide": region.wide,
        "land": region.land, "eu_point_note": region.eu_point_note,
        "whole": region.whole,
        "layers": list(region.layers), "lenders": lenders, "family": family,
        "bank": {"code": bank["code"], "name": bank["name"], "group": bank["group"], "currency": bank["currency"],
                 "file": f"iati_{bank['publisher']}_finance.geojson", "logo": bank["logo"], "home": bank["home"]},
        "center": list(region.center), "zoom_win": list(region.zoom_win),
        "bounds": region.bounds, "home_exclude": region.home_exclude,
        "eu_point_where": region.eu_point_where,
    }
