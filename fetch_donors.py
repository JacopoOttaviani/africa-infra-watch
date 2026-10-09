#!/usr/bin/env python3
"""
The data behind the lender profiles (docs/<slug>/): one JSON per profile in
data/donors/, written by one function per lender below. A pack is what the
profile page needs and nothing more: a country-year backbone fetched from an
open API at run time, plus the hand-kept tables that no API publishes (the
energy assets where that lender has a role, its agreements, the press list),
each with the source beside every row.

    python3 fetch_donors.py           every profile in shared.DONORS
    python3 fetch_donors.py russia    one

Russia
    World Bank International Debt Statistics, source 6: public and publicly
    guaranteed debt owed by each African government to the Russian Federation
    (counterpart-area 087) and, before 1992, to the USSR (078): stock,
    commitments and disbursements by year. Open (CC BY 4.0), refreshed every
    December. The rest of the pack (GEM assets with a Russian role, Rosatom
    agreements from the World Nuclear Association, the Bank of Russia's outward
    investment table, corporate holdings from the press) is kept by hand in
    this file: see the notes above each table.
"""

import json
import re
import sys

from fetch_sources import get, _country_centre
from shared import DATA, DONORS, load_meta, today, update_meta

OUT = DATA / "donors"

# ------------------------------------------------------------- geography

# ISO 3166-1 alpha-3 (what the World Bank API speaks) to alpha-2 (what the
# site speaks) for every African country, and the names the site uses.
AFRICA = {
    "DZA": "DZ", "AGO": "AO", "BEN": "BJ", "BWA": "BW", "BFA": "BF", "BDI": "BI", "CMR": "CM",
    "CPV": "CV", "CAF": "CF", "TCD": "TD", "COM": "KM", "COD": "CD", "COG": "CG", "CIV": "CI",
    "DJI": "DJ", "EGY": "EG", "GNQ": "GQ", "ERI": "ER", "SWZ": "SZ", "ETH": "ET", "GAB": "GA",
    "GMB": "GM", "GHA": "GH", "GIN": "GN", "GNB": "GW", "KEN": "KE", "LSO": "LS", "LBR": "LR",
    "LBY": "LY", "MDG": "MG", "MWI": "MW", "MLI": "ML", "MRT": "MR", "MUS": "MU", "MAR": "MA",
    "MOZ": "MZ", "NAM": "NA", "NER": "NE", "NGA": "NG", "RWA": "RW", "STP": "ST", "SEN": "SN",
    "SYC": "SC", "SLE": "SL", "SOM": "SO", "ZAF": "ZA", "SSD": "SS", "SDN": "SD", "TZA": "TZ",
    "TGO": "TG", "TUN": "TN", "UGA": "UG", "ZMB": "ZM", "ZWE": "ZW",
}
NAME = {
    "DZ": "Algeria", "AO": "Angola", "BJ": "Benin", "BW": "Botswana", "BF": "Burkina Faso",
    "BI": "Burundi", "CM": "Cameroon", "CV": "Cabo Verde", "CF": "Central African Republic",
    "TD": "Chad", "KM": "Comoros", "CD": "DR Congo", "CG": "Republic of the Congo",
    "CI": "Côte d'Ivoire", "DJ": "Djibouti", "EG": "Egypt", "GQ": "Equatorial Guinea",
    "ER": "Eritrea", "SZ": "Eswatini", "ET": "Ethiopia", "GA": "Gabon", "GM": "The Gambia",
    "GH": "Ghana", "GN": "Guinea", "GW": "Guinea-Bissau", "KE": "Kenya", "LS": "Lesotho",
    "LR": "Liberia", "LY": "Libya", "MG": "Madagascar", "MW": "Malawi", "ML": "Mali",
    "MR": "Mauritania", "MU": "Mauritius", "MA": "Morocco", "MZ": "Mozambique", "NA": "Namibia",
    "NE": "Niger", "NG": "Nigeria", "RW": "Rwanda", "ST": "São Tomé and Príncipe", "SN": "Senegal",
    "SC": "Seychelles", "SL": "Sierra Leone", "SO": "Somalia", "ZA": "South Africa",
    "SS": "South Sudan", "SD": "Sudan", "TZ": "Tanzania", "TG": "Togo", "TN": "Tunisia",
    "UG": "Uganda", "ZM": "Zambia", "ZW": "Zimbabwe",
}
# Islands the 1:110m basemap does not draw, so they have no interior point there.
ISLANDS = {"CV": (-23.6, 15.1), "KM": (43.3, -11.7), "MU": (57.55, -20.3), "SC": (55.45, -4.65),
           "ST": (6.6, 0.25)}


def centre(iso):
    """A country's interior point from the dashboard basemap, or the island table."""
    if iso in ISLANDS:
        return ISLANDS[iso]
    lon, lat = _country_centre(iso)
    return (round(lon, 4), round(lat, 4)) if lon is not None else (None, None)


def place(rows):
    for r in rows:
        if r.get("lon") is None:
            r["lon"], r["lat"] = centre(r["iso"])
    return rows


# ----------------------------------------------------- World Bank IDS

IDS = ("https://api.worldbank.org/v2/sources/6/country/all/series/{series}"
       "/counterpart-area/{cp}/time/all?format=json&per_page=30000&page={page}")


def ids_series(series, cp):
    """{iso2: {year: value}} for one IDS series and one creditor, African
    debtors only, null cells dropped. Returns the API's 'lastupdated' too.
    Several counterpart codes (a tuple) are fetched one by one and summed."""
    if isinstance(cp, (list, tuple)):
        out, updated = {}, None
        for one in cp:
            part, upd = ids_series(series, one)
            updated = upd or updated
            for iso, years in part.items():
                for y, v in years.items():
                    out.setdefault(iso, {})[y] = out.get(iso, {}).get(y, 0) + v
        return out, updated
    out, page, updated = {}, 1, None
    while True:
        d = json.loads(get(IDS.format(series=series, cp=cp, page=page), timeout=180))
        updated = d.get("lastupdated") or updated
        for row in d["source"]["data"]:
            v = row.get("value")
            if v is None:
                continue
            var = {x["concept"]: x for x in row["variable"]}
            iso3 = var["Country"]["id"]
            if iso3 not in AFRICA:
                continue
            year = int(var["Time"]["value"])
            out.setdefault(AFRICA[iso3], {})[year] = float(v)
        if page >= int(d.get("pages") or 1):
            break
        page += 1
    return out, updated


# -------------------------------------------------------------- Russia

# What a Russian commitment in the IDS paid for, where a public source says so.
# The IDS itself records money, not purpose. (iso2, commitment year) -> text.
RUSSIA_LOAN_PURPOSE = {
    ("EG", 2015): "El Dabaa nuclear plant: a USD 25 bn Russian state export loan covering 85% of "
                  "the plant's cost (Africa Center for Strategic Studies; GEM)",
    ("AO", 2011): "Angosat-1 communications satellite: USD 278.5 m, 13-year loan from Roseximbank, "
                  "VEB, VTB and Gazprombank (RussianSpaceWeb; Telecompaper)",
    ("ZM", 2018): "not stated in the IDS; Rosatom's contract for Zambia's Centre for Nuclear "
                  "Science and Technology was signed in May 2018 (SAIIA)",
    ("MZ", 2013): "not stated in the IDS; press reported a 2013 agreement converting Mozambique's "
                  "USD 144 m debt to Russia into development projects",
}

# Records in Global Energy Monitor's trackers with a Russian vendor, owner or
# parent. GEM's owner field alone misses El Dabaa (booked under Egypt's own
# authority); the Russian role there is in the reactor model and the wiki page.
# Checked 2026-10-07 against the Global Nuclear Power Tracker (2026-08 map file),
# the Global Integrated Power Tracker 2026-08 and the Global Gas Infrastructure
# Tracker 2025-11. Status uses the site's vocabulary.
RUSSIA_GEM = [
    {"name": "El Dabaa nuclear power plant", "iso": "EG", "lon": 28.4978, "lat": 31.0442,
     "what": "4 × 1,200 MW VVER-1200, Rosatom (Atomstroyexport) as engineering and construction contractor",
     "mw": 4800, "status": "under_construction",
     "role": "Reactor vendor and builder; financed by the USD 25 bn Russian state loan of 2015",
     "src": "GEM Global Nuclear Power Tracker 2026-08", "url": "https://www.gem.wiki/El_Dabaa_nuclear_power_plant",
     "on_site": False,
     "note": "GEM's owner field says Nuclear Power Plants Authority 100%; the Russian role is in the model field and the wiki page"},
    {"name": "Itu nuclear power plant", "iso": "NG", "lon": 7.9861, "lat": 5.2016,
     "what": "2 × 1,200 MW, owner listed as Nigeria Atomic Energy Commission with Rosatom",
     "mw": 2400, "status": "stalled", "role": "Rosatom named as co-owner; GEM status shelved",
     "src": "GEM Global Nuclear Power Tracker 2026-08", "url": "https://www.gem.wiki/Itu_nuclear_power_plant",
     "on_site": False, "note": ""},
    {"name": "Lurio hydroelectric plant", "iso": "MZ", "lon": 40.2166, "lat": -13.4782,
     "what": "120 MW hydro, Electricidade de Moçambique with Inter RAO Export",
     "mw": 120, "status": "approved", "role": "Inter RAO Export, the Russian state utility's export arm, as co-owner",
     "src": "GEM Global Integrated Power Tracker 2026-08", "url": "https://www.gem.wiki/Lurio_hydroelectric_plant",
     "on_site": True, "note": "in the map's power layer"},
    {"name": "Arab Gas Pipeline, Arish–Taba segment", "iso": "EG", "lon": 33.8887, "lat": 31.1435,
     "what": "Gas pipeline, 10.3 bcm a year, owner Egyptian Natural Gas Holding",
     "mw": None, "status": "operating", "role": "Gazprom PJSC listed among the parent shareholders, share not stated",
     "src": "GEM Global Gas Infrastructure Tracker 2025-11", "url": "https://www.gem.wiki/Arab_Gas_Pipeline",
     "on_site": True, "note": "in the map's pipelines layer"},
]

# Rosatom's African agreements as the World Nuclear Association's "Emerging
# nuclear energy countries" profile records them (world-nuclear.org, read
# 2026-10-07). A narrative page, not a dataset: almost every entry is a
# memorandum with no money, no site and no date of works. Only Egypt has a
# contract and a construction site.
RUSSIA_NUCLEAR = [
    {"iso": "DZ", "year": 2007, "what": "Agreement to investigate nuclear power; further agreements in 2014 and 2016 (VVER for hot climates)", "status": "no construction; focus moved to non-power uses"},
    {"iso": "NG", "year": 2009, "what": "2009 cooperation agreement including uranium; 2011 agreement; 2012 memorandum; preferred sites Geregu and Itu, two reactors each", "status": "Itu shelved per GEM; Geregu announced"},
    {"iso": "GH", "year": 2012, "what": "2012 nuclear cooperation agreement; 2015 contractual and legal framework agreement", "status": "no construction; GEM lists Nsuban as pre-construction with no vendor"},
    {"iso": "TN", "year": 2015, "what": "June 2015 cooperation agreement; 2016 intergovernmental agreement", "status": "no construction"},
    {"iso": "EG", "year": 2015, "what": "November 2015 contracts for El Dabaa, 4 × 1,200 MW; construction from 2022", "status": "under construction"},
    {"iso": "KE", "year": 2016, "what": "May 2016 agreement on nuclear infrastructure development", "status": "no construction"},
    {"iso": "ZM", "year": 2016, "what": "2016–2017 agreements; May 2018 contract for a Centre for Nuclear Science and Technology with a 10 MW research reactor", "status": "infrastructure development phase"},
    {"iso": "UG", "year": 2016, "what": "October 2016 framework; June 2017 agreement; August 2023 Russia (with South Korea) selected to build plants, 15 GWe combined", "status": "site studies"},
    {"iso": "ET", "year": 2017, "what": "2017 agreement on research centres; 2019 intergovernmental agreement; September 2025 action plan; March 2026 strategic roadmap for two ~1,200 MWe units, 2032–2034", "status": "planning"},
    {"iso": "SD", "year": 2017, "what": "June 2017 agreement: a science centre with a research reactor and a feasibility study of 1–2 × 600 MWe", "status": "halted since the April 2023 war"},
    {"iso": "RW", "year": 2018, "what": "December 2018 intergovernmental agreement; July 2026 small-modular-reactor cooperation roadmap", "status": "SMR targeted for the early 2030s"},
    {"iso": "BF", "year": 2023, "what": "Memorandum and roadmap with Rosatom for a nuclear power plant and workforce (Sochi, October 2023)", "status": "memorandum only"},
    {"iso": "ML", "year": 2023, "what": "Memorandum with Rosatom towards a nuclear power plant", "status": "memorandum only"},
    {"iso": "TZ", "year": 2025, "what": "Pilot uranium plant at Mkuju River (Uranium One, a Rosatom company) commissioned July 2025; 3,000 tU a year main plant due 2029", "status": "pilot operating"},
    {"iso": "NA", "year": 2026, "what": "January 2026 discussions with Rosatom", "status": "no agreement"},
]

# Bank of Russia, outward direct investment positions by partner country
# (directional principle), USD million: cbr.ru, table 16e-dir_inv.xlsx, last
# updated 17 May 2023 and ending at 1 January 2022. "C" is the Bank's own
# confidentiality mark; "-" is no position. The only official Russian figure
# per African country, and too thin and too old to draw.
RUSSIA_CBR = [
    {"iso": "DZ", "v2014": "C", "v2021": "C"}, {"iso": "AO", "v2014": "C", "v2021": "C"},
    {"iso": "BW", "v2014": "-", "v2021": "-"}, {"iso": "GH", "v2014": 0, "v2021": 0.65},
    {"iso": "GN", "v2014": 0, "v2021": 0.34}, {"iso": "EG", "v2014": 62.22, "v2021": 61.58},
    {"iso": "ZM", "v2014": 0, "v2021": 0.06}, {"iso": "ZW", "v2014": 0, "v2021": 0.37},
    {"iso": "CV", "v2014": "-", "v2021": "-"}, {"iso": "CM", "v2014": 0, "v2021": 0.06},
    {"iso": "KE", "v2014": 1.04, "v2021": 3.06}, {"iso": "KM", "v2014": "-", "v2021": -0.05},
    {"iso": "CG", "v2014": "C", "v2021": "C"}, {"iso": "CD", "v2014": 0, "v2021": "C"},
    {"iso": "CI", "v2014": 0, "v2021": 0.31}, {"iso": "LS", "v2014": "-", "v2021": -0.01},
    {"iso": "LR", "v2014": "C", "v2021": "C"}, {"iso": "LY", "v2014": 30, "v2021": "C"},
    {"iso": "MU", "v2014": 5.36, "v2021": 45.09}, {"iso": "MR", "v2014": 0, "v2021": 3.12},
    {"iso": "MG", "v2014": 0, "v2021": 0.07}, {"iso": "MA", "v2014": "C", "v2021": "C"},
    {"iso": "MZ", "v2014": 0, "v2021": "C"}, {"iso": "NA", "v2014": 1.1, "v2021": 1.1},
    {"iso": "NE", "v2014": 0, "v2021": 0.04}, {"iso": "NG", "v2014": 0, "v2021": 0.09},
    {"iso": "SC", "v2014": 30.2, "v2021": -211.73}, {"iso": "SD", "v2014": 0, "v2021": 0.08},
    {"iso": "SL", "v2014": 0, "v2021": 0.14}, {"iso": "TZ", "v2014": 0, "v2021": 0.77},
    {"iso": "TG", "v2014": "-", "v2021": "-"}, {"iso": "TN", "v2014": 0, "v2021": 1.12},
    {"iso": "UG", "v2014": 0, "v2021": -0.04}, {"iso": "ET", "v2014": 0, "v2021": 0.6},
    {"iso": "ZA", "v2014": 35.92, "v2021": 33.33}, {"iso": "SS", "v2014": 0, "v2021": 0.11},
]

# Russian corporate holdings in African mining and energy as the press and the
# companies describe them. No open tracker covers these; every row carries its
# source, several are exits rather than investments, and none is drawn on the
# map by default. Read 2026-10-07.
RUSSIA_CORP = [
    {"name": "Rusal bauxite complex (Dian-Dian, CBK Kindia, Friguia refinery)", "iso": "GN", "sector": "mining", "status": "operating", "who": "Rusal", "note": "Dian-Dian is 42% of Rusal's bauxite capacity", "src": "Billionaires.Africa, 2 Jun 2026", "url": "https://www.billionaires.africa/2026/06/02/russian-billionaires-with-africa-exposure-the-oligarchs-mining-the-continents-wealth/"},
    {"name": "Lefa gold mine", "iso": "GN", "sector": "mining", "status": "operating", "who": "Nordgold", "note": "15-year permit to 2034, USD 360 m planned", "src": "Mining.com", "url": "https://www.mining.com/russias-nordgold-invest-360m-guinea-mine-2034/"},
    {"name": "Bissa and Bouly gold mines; Jilbey Niou deposit", "iso": "BF", "sector": "mining", "status": "operating", "who": "Nordgold", "note": "Niou licensed April 2025, 85% Jilbey Burkina", "src": "Billionaires.Africa, 2 Jun 2026", "url": "https://www.billionaires.africa/2026/06/02/russian-billionaires-with-africa-exposure-the-oligarchs-mining-the-continents-wealth/"},
    {"name": "Catoca diamond mine, 41% stake", "iso": "AO", "sector": "mining", "status": "sold", "who": "Alrosa", "note": "Stake divested May 2025 after Angola ended the partnership in 2024", "src": "Billionaires.Africa; IFRI", "url": "https://www.billionaires.africa/2026/06/02/russian-billionaires-with-africa-exposure-the-oligarchs-mining-the-continents-wealth/"},
    {"name": "United Manganese of Kalahari, 49% via NAMI", "iso": "ZA", "sector": "mining", "status": "operating", "who": "Renova", "note": "", "src": "Billionaires.Africa, 2 Jun 2026", "url": "https://www.billionaires.africa/2026/06/02/russian-billionaires-with-africa-exposure-the-oligarchs-mining-the-continents-wealth/"},
    {"name": "Great Dyke Investments, Darwendale platinum", "iso": "ZW", "sector": "mining", "status": "exited", "who": "Vi Holding, Rostec, VEB", "note": "Vi Holding ceded its 50% to Kuvimba Mining House in 2022; a USD 3 bn project", "src": "News24, 6 Jun 2022", "url": "https://www.news24.com/business/companies/russians-quit-large-zim-platinum-project-which-mugabe-took-from-implats-20220606"},
    {"name": "Mkuju River uranium project (Mantra Tanzania)", "iso": "TZ", "sector": "mining", "status": "under_construction", "who": "Uranium One (Rosatom)", "note": "Pilot plant commissioned July 2025; a USD 1 bn project; main plant due 2029", "src": "The Citizen; WNA", "url": "https://thecitizen.co.tz/tanzania/business/it-s-race-against-time-for-the-strategic-1-billion-mkuju-uranium-project-5484274"},
    {"name": "Diamond exploration licences", "iso": "ZW", "sector": "mining", "status": "exploration", "who": "Alrosa", "note": "40 exclusive exploration licences", "src": "Bloomberg, 14 Jan 2019", "url": "https://www.bloomberg.com/news/articles/2019-01-14/russian-diamond-giant-alrosa-is-going-back-to-zimbabwe"},
    {"name": "Mossel Bay gas-to-liquids restart", "iso": "ZA", "sector": "energy", "status": "cancelled", "who": "Gazprombank", "note": "Deal terminated after one year", "src": "GIS Reports, 2025", "url": "https://www.gisreportsonline.com/r/russias-africa-footprint/"},
    {"name": "Oil exploration cooperation memorandum", "iso": "CG", "sector": "energy", "status": "announced", "who": "Lukoil (also holds 25% of Marine XII)", "note": "Memorandum with the Ministry of Hydrocarbons, September 2024", "src": "AEC Week, Mar 2025", "url": "https://aecweek.com/news/russias-energy-push-africa-means-continents-future"},
]


def ids_pack(cp, name, purposes=None, old_cp=None, old_name=None, from_year=None, since=2000, kind="BLAT"):
    """The debt block of a profile: for one bilateral creditor, every African
    debtor's stock, peak, new commitments since `since` (with a purpose where a
    public source states one) and disbursements, plus the continent-wide stock
    by year. `old_cp` is a predecessor creditor (the USSR for Russia) whose
    stock is reported separately; `from_year` trims reporting artefacts before
    the creditor existed."""
    stock, updated = ids_series(f"DT.DOD.{kind}.CD", cp)
    commit, _ = ids_series(f"DT.COM.{kind}.CD", cp)
    disb, _ = ids_series(f"DT.DIS.{kind}.CD", cp)
    old, _ = ids_series(f"DT.DOD.{kind}.CD", old_cp) if old_cp else ({}, None)
    # the stock series ends at the last reported year; the flow series carry
    # projections beyond it, which are not data
    data_to = max(y for s in stock.values() for y, v in s.items() if v > 0)
    purposes = purposes or {}

    countries = []
    for iso in sorted(set(stock) | set(old), key=lambda i: NAME[i]):
        s = {y: v for y, v in stock.get(iso, {}).items() if (from_year or 0) <= y <= data_to}
        pos = {y: v for y, v in s.items() if v > 0}
        u = {y: v for y, v in old.get(iso, {}).items() if v > 0}
        if not pos and not u:
            continue
        coms = [{"year": y, "usd": v, "purpose": purposes.get((iso, y), "not stated in the IDS")}
                for y, v in sorted(commit.get(iso, {}).items()) if v > 0 and since <= y <= data_to]
        d = {y: v for y, v in disb.get(iso, {}).items() if v > 0 and (from_year or 0) <= y <= data_to}
        lon, lat = centre(iso)
        countries.append({
            "iso": iso, "name": NAME[iso], "lon": lon, "lat": lat,
            "latest_year": max(pos) if pos else None,
            "latest_stock": pos[max(pos)] if pos else 0,
            "peak_stock": max(pos.values()) if pos else 0,
            "peak_year": max(pos, key=pos.get) if pos else None,
            "first_year": min(pos) if pos else None,
            "commitments": coms,
            "disbursed_since": sum(v for y, v in d.items() if y >= since),
            "largest_disbursement": ({"year": max(d, key=d.get), "usd": max(d.values())} if d else None),
            "ussr_peak": max(u.values()) if u else 0,
            "ussr_peak_year": max(u, key=u.get) if u else None,
            "stock": {str(y): v for y, v in sorted(s.items())},
        })
    years = sorted({y for c in countries for y in map(int, c["stock"])})
    continent = {}
    for y in years:
        t = sum(c["stock"].get(str(y), 0) for c in countries)
        if continent or t > 0:
            continent[str(y)] = round(t, 1)
    cps = {c: name for c in (cp if isinstance(cp, (list, tuple)) else [cp])}
    if old_cp:
        cps[old_cp] = old_name
    first = cp[0] if isinstance(cp, (list, tuple)) else cp
    return {"source": "World Bank International Debt Statistics, source 6",
            "url": "https://data.worldbank.org/products/ids", "licence": "CC BY 4.0",
            "api": IDS.split("?")[0].replace("{series}", f"DT.DOD.{kind}.CD").replace("{cp}", first),
            "series": kind, "updated": updated, "data_to": data_to, "since": since, "counterparts": cps,
            "countries": countries, "continent": continent}


def fetch_russia():
    print("russia  … World Bank IDS, counterpart 087 (Russian Federation) and 078 (USSR)")
    # Before 1991 the creditor was the USSR (078): the odd pre-1991 cell under
    # 087 is a reporting artefact, so the Russian Federation series starts in 1991.
    ids = ids_pack("087", "Russian Federation", RUSSIA_LOAN_PURPOSE, old_cp="078", old_name="USSR", from_year=1991)
    countries, continent, data_to, updated = ids["countries"], ids["continent"], ids["data_to"], ids["updated"]
    pack = {
        "slug": "russia", "fetched": today(),
        "ids": ids,
        "gem": place([dict(r) for r in RUSSIA_GEM]),
        "nuclear": place([{**r, "country": NAME[r["iso"]]} for r in RUSSIA_NUCLEAR]),
        "cbr": place([{**r, "country": NAME[r["iso"]]} for r in RUSSIA_CBR]),
        "corp": place([{**r, "country": NAME[r["iso"]]} for r in RUSSIA_CORP]),
    }
    n_pos = sum(1 for c in countries if c["latest_stock"] > 0)
    print(f"   {len(countries)} African debtors on record ({n_pos} with a stock above zero), "
          f"data to {data_to}, IDS updated {updated}; continent stock {continent[str(data_to)] / 1e9:,.2f} bn")
    update_meta("russia", fetched=today(), ids_updated=updated, data_to=data_to,
                countries=len(countries), gem=len(RUSSIA_GEM), nuclear=len(RUSSIA_NUCLEAR))
    return pack


# ------------------------------------------------------------- Turkey

# OECD Creditor Reporting System, Turkey as provider (DAC donor 55 / TUR),
# activity-level microdata through the OECD's SDMX API (the bulk files sit
# behind a browser challenge). Recipients are ISO3 codes; the F*_X codes are
# the "Africa unspecified" regions. MD_DIM=DD selects the microdata rows.
CRS_AFRICA = ("DZA AGO BEN BWA BFA BDI CMR CPV CAF TCD COM COG COD CIV DJI EGY GNQ ERI SWZ ETH GAB GMB "
              "GHA GIN GNB KEN LSO LBR LBY MDG MWI MLI MRT MUS MAR MOZ NAM NER NGA RWA STP SEN SYC SLE "
              "SOM ZAF SSD SDN TZA TGO TUN UGA ZMB ZWE").split()
CRS_REGIONS = {"F_X": "Africa unspecified", "F6_X": "Sub-Saharan Africa unspecified",
               "F4_X": "Northern Africa unspecified", "F3_X": "Eastern Africa unspecified",
               "F5_X": "Middle Africa unspecified", "F7_X": "Southern Africa unspecified",
               "F8_X": "Western Africa unspecified"}
CRS = ("https://sdmx.oecd.org/dcd-public/rest/data/OECD.DCD.FSD,DSD_CRS@DF_CRS,1.6/"
       "{donor}.{recipients}.......DD..?format=csvfilewithlabels&startPeriod={y0}&endPeriod={y1}")
# DAC purpose codes for physical infrastructure (transport, communications,
# energy, water) plus the facility codes of the social sectors: the "hard" subset
CRS_HARD_PREFIX = ("21", "22", "23", "14")
CRS_HARD_CODES = {"12230", "11120"}   # basic health infrastructure, education facilities and training
CRS_HARD_WORDS = re.compile(r"\bCONSTRUCT|\bRENOVAT|\bREHABILITAT|\bWELL(S)?\b|WATER (SUPPLY|SYSTEM|NETWORK)|\bROAD\b|\bBRIDGE\b|"
                            r"\bBUILDING OF\b|\bBUILT\b|\bDRILL|\bHOSPITAL\b|\bCLINIC\b|\bIRRIGAT", re.I)

# DAC purpose codes folded into broad sectors for the lender comparison
# (build_compare.py): the leading digits of a purpose code are the DAC's own
# sector headings (11x education, 21x transport, 23x energy ...).
CRS_GROUPS = [
    ("education", "Education", ("11",)),
    ("health", "Health and population", ("12", "13")),
    ("water", "Water and sanitation", ("14",)),
    ("government", "Government, civil society, peace", ("15",)),
    ("social", "Other social services", ("16",)),
    ("transport", "Transport and storage", ("21",)),
    ("comms", "Communications", ("22",)),
    ("energy", "Energy", ("23",)),
    ("finance", "Banking, business, trade", ("24", "25", "33")),
    ("agriculture", "Agriculture, forestry, fishing", ("31",)),
    ("industry", "Industry, mining, construction", ("32",)),
    ("environment", "Environment and multisector", ("41", "43")),
    ("budget", "Budget support, food aid, debt relief", ("51", "52", "53", "60")),
    ("humanitarian", "Humanitarian", ("7",)),
    ("other", "Other and unallocated", ()),
]


def crs_group(code):
    code = str(code or "")
    for key, _, prefixes in CRS_GROUPS:
        if any(code.startswith(p) for p in prefixes):
            return key
    return "other"


# OECD DAC2a: net ODA disbursements (measure 206) by recipient, current prices
DAC2A = ("https://sdmx.oecd.org/public/rest/data/OECD.DCD.FSD,DSD_DAC2@DF_DAC2A,1.4/"
         "{donor}..206..?format=csvfilewithlabels&startPeriod={y0}")
# OECD FDI positions by partner country (BMD4): Turkey's outward stock, USD,
# net, all resident units, immediate counterpart, all activities, annual
FDI = ("https://sdmx.oecd.org/public/rest/data/OECD.DAF.INV,DSD_FDI@DF_FDI_POS_CTRY,1.0/"
       "{donor}.LE_FA_F.USD_EXC.DO.NET_FDI.ALL.D.S1..IMC._T.A.CTRY_IND?format=csvfilewithlabels&startPeriod={y0}")
ISO3_TO_2 = AFRICA

# Turkish owners in Global Energy Monitor's power tracker, matched on the
# owner field of the site's own assets layer (data/gem_power_assets.geojson)
TURKISH_OWNER = re.compile(r"karpower|karadeniz|aksa|turkish industry|çalık|calik|limak|yapı merkezi|yapi merkezi|summa|enka|zorlu", re.I)

# Turkish-built or Turkish-financed works with a place, read from the
# publishers' own pages on 2026-10-07: Türk Eximbank's "sample transactions"
# page (the bank publishes no loan register), Yapı Merkezi's and Summa's
# project portfolios, Karpowership's country pages. Coordinates are the
# company's where its page gives them, otherwise the named town, corridor or
# port placed by hand. GEM's Turkish-owned power units are read live instead.
TURKEY_WORKS = [
    {"src": "exim", "name": "Awash–Weldiya railway (phase 1)", "iso": "ET", "lon": 39.73, "lat": 11.08, "kind": "rail", "year": "2017", "note": "Türk Eximbank loan USD 300m of a USD 1.7bn project; built by Yapı Merkezi", "amount": "USD 300m loan / 1,700m cost", "url": "https://www.eximbank.gov.tr/en/product-and-services/buyer-s-credits/sample-transactions", "status": "built"},
    {"src": "exim", "name": "Kintélé congress complex and Brazzaville city centre", "iso": "CG", "lon": 15.3, "lat": -4.15, "kind": "convention", "year": "2016", "note": "EUR 66.7m loan of EUR 200m cost; operational 2017", "amount": "EUR 66.7m loan / 200m cost", "url": "https://www.eximbank.gov.tr/en/product-and-services/buyer-s-credits/sample-transactions", "status": "built"},
    {"src": "exim", "name": "Akim Oda, Akwatia and Winneba water works", "iso": "GH", "lon": -0.98, "lat": 5.93, "kind": "water", "year": "2017", "note": "USD 133m loan of USD 165m cost; treatment plant, 2m m³ reservoir, mains", "amount": "USD 133m loan / 165m cost", "url": "https://www.eximbank.gov.tr/en/product-and-services/buyer-s-credits/sample-transactions", "status": "built"},
    {"src": "exim", "name": "Dakar International Conference Centre (CICAD)", "iso": "SN", "lon": -17.195, "lat": 14.74, "kind": "convention", "year": "2014", "note": "EUR 49m loan of EUR 73m cost; built by Summa", "amount": "EUR 49m loan / 73m cost", "url": "https://www.eximbank.gov.tr/en/product-and-services/buyer-s-credits/sample-transactions", "status": "built"},
    {"src": "exim", "name": "Japoma sports complex, Douala", "iso": "CM", "lon": 9.816, "lat": 4.012, "kind": "sports", "year": "2019", "note": "USD 188.7m loan of USD 232m cost; 50,000-seat stadium for AFCON", "amount": "USD 188.7m loan / 232m cost", "url": "https://www.eximbank.gov.tr/en/product-and-services/buyer-s-credits/sample-transactions", "status": "built"},
    {"src": "exim", "name": "CICAD business hotel, expo centre and Dakar Arena, Diamniadio", "iso": "SN", "lon": -17.18, "lat": 14.73, "kind": "mixed", "year": "2018", "note": "EUR 134m loan of EUR 147.5m cost", "amount": "EUR 134m loan / 147.5m cost", "url": "https://www.eximbank.gov.tr/en/product-and-services/buyer-s-credits/sample-transactions", "status": "built"},
    {"src": "exim", "name": "Market of National Interest and truck station, Diamniadio", "iso": "SN", "lon": -17.17, "lat": 14.72, "kind": "logistics", "year": "2019", "note": "USD 88.9m loan of USD 105.9m cost", "amount": "USD 88.9m loan / 105.9m cost", "url": "https://www.eximbank.gov.tr/en/product-and-services/buyer-s-credits/sample-transactions", "status": "built"},
    {"src": "exim", "name": "Geothermal drilling equipment, Djibouti", "iso": "DJ", "lon": 43.15, "lat": 11.59, "kind": "energy", "year": "n/a", "note": "Sovereign-guaranteed buyer's credit, six-year maturity; equipment export, not a site", "amount": None, "url": "https://www.eximbank.gov.tr/en/product-and-services/buyer-s-credits/sample-transactions", "status": "unknown"},
    {"src": "ym", "name": "Dar es Salaam–Morogoro SGR (lot 1)", "iso": "TZ", "lon": 38.2, "lat": -6.75, "kind": "rail", "year": "completed", "note": "Standard-gauge railway, 300 km, with Portugal's Mota-Engil", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Major-Projects/Dar-Es-Salaam-Morogoro-RAILWAY", "status": "built"},
    {"src": "ym", "name": "Morogoro–Makutupora SGR (lot 2)", "iso": "TZ", "lon": 36.4, "lat": -6.4, "kind": "rail", "year": "ongoing", "note": "422 km", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Ongoing-Projects/Morogoro-Makutupora-Railway", "status": "building"},
    {"src": "ym", "name": "Makutupora–Tabora SGR (lot 3)", "iso": "TZ", "lon": 34.3, "lat": -5.6, "kind": "rail", "year": "ongoing", "note": "Started March 2022", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Ongoing-Projects/MAKUTUPORA-TABORA-RAILWAY", "status": "building"},
    {"src": "ym", "name": "Tabora–Isaka SGR (lot 4)", "iso": "TZ", "lon": 32.9, "lat": -4.5, "kind": "rail", "year": "ongoing", "note": "", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Ongoing-Projects/TABORA-ISAKA-RAILWAY", "status": "building"},
    {"src": "ym", "name": "Malaba–Kampala SGR", "iso": "UG", "lon": 33.6, "lat": 0.6, "kind": "rail", "year": "ongoing", "note": "About USD 3bn, Government of Uganda", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Ongoing-Projects/Malaba-Kampala-RAILWAY", "status": "building"},
    {"src": "ym", "name": "Awash–Kombolcha–Hara Gebeya railway", "iso": "ET", "lon": 39.9, "lat": 11.3, "kind": "rail", "year": "ongoing", "note": "392 km; the Eximbank-financed line above", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Ongoing-Projects/Awash-Kombolcha-Hara-Gebaya-Railway", "status": "building"},
    {"src": "ym", "name": "Sidi Bel Abbès tramway", "iso": "DZ", "lon": -0.63, "lat": 35.19, "kind": "tram", "year": "in progress", "note": "", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Major-Projects/Sidi-Bel-Abbes-Tramway", "status": "building"},
    {"src": "ym", "name": "Bir Touta–Zéralda railway", "iso": "DZ", "lon": 2.84, "lat": 36.71, "kind": "rail", "year": "completed", "note": "", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Major-Projects/Bir-Touta-Zeralda-Railway", "status": "built"},
    {"src": "ym", "name": "Casablanca tramway line 2", "iso": "MA", "lon": -7.59, "lat": 33.57, "kind": "tram", "year": "completed", "note": "", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Major-Projects/The-Second-Tramline-of-Casablanca", "status": "built"},
    {"src": "ym", "name": "Sétif tramway", "iso": "DZ", "lon": 5.41, "lat": 36.19, "kind": "tram", "year": "in progress", "note": "", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Major-Projects/Setif-Tramway", "status": "building"},
    {"src": "ym", "name": "Dakar–AIBD airport railway", "iso": "SN", "lon": -17.1, "lat": 14.7, "kind": "rail", "year": "planned", "note": "", "amount": None, "url": "http://yapimerkezi.com.tr/En/Projects/Major-Projects/Dakar-AIBD-NEW-AIRPORT-RAILWAY", "status": "announced"},
    {"src": "kp", "name": "Powership, Ghana (Sekondi)", "iso": "GH", "lon": -1.7, "lat": 4.93, "kind": "power", "year": "2015", "note": "470 MW on indigenous gas; 23% of national demand", "amount": "470 MW", "url": "https://www.karpowership.com/ghana", "status": "operating"},
    {"src": "kp", "name": "Powership, Dakar (Bel Air)", "iso": "SN", "lon": -17.42, "lat": 14.68, "kind": "power", "year": "2019", "note": "335 MW, LNG-to-power; 20% of demand", "amount": "335 MW", "url": "https://www.karpowership.com/senegal", "status": "operating"},
    {"src": "kp", "name": "Powership, Nacala", "iso": "MZ", "lon": 40.67, "lat": -14.54, "kind": "power", "year": "2018", "note": "35 MW (from 48); 3% of demand; cross-border supply to Zambia 2016–18 (115 MW)", "amount": "35 MW", "url": "https://www.karpowership.com/mozambique", "status": "operating"},
    {"src": "kp", "name": "Powership, Freetown", "iso": "SL", "lon": -13.23, "lat": 8.49, "kind": "power", "year": "2018", "note": "30 MW, up to 60% of demand", "amount": "30 MW", "url": "https://www.karpowership.com/sierra-leone", "status": "operating"},
    {"src": "kp", "name": "Powership, Banjul", "iso": "GM", "lon": -16.58, "lat": 13.45, "kind": "power", "year": "2018", "note": "36 MW, 40% of demand; extended 2020 and 2022", "amount": "36 MW", "url": "https://www.karpowership.com/the-gambia", "status": "operating"},
    {"src": "kp", "name": "Powership, Bissau", "iso": "GW", "lon": -15.59, "lat": 11.86, "kind": "power", "year": "2019", "note": "35 MW, 100% of demand, completed", "amount": "35 MW", "url": "https://www.karpowership.com/guinea-bissau", "status": "ended"},
    {"src": "kp", "name": "Powership, Conakry", "iso": "GN", "lon": -13.7, "lat": 9.52, "kind": "power", "year": "2019", "note": "105 MW to 2023; new 150 MW agreement 2024", "amount": "150 MW", "url": "https://www.karpowership.com/guinea-conakry", "status": "operating"},
    {"src": "kp", "name": "Powership, Abidjan", "iso": "CI", "lon": -4.01, "lat": 5.3, "kind": "power", "year": "2022", "note": "135 MW, four-year contract; 7.5% of demand", "amount": "135 MW", "url": "https://www.karpowership.com/cote-d-ivoire", "status": "operating"},
    {"src": "kp", "name": "Powership, Libreville", "iso": "GA", "lon": 9.5, "lat": 0.29, "kind": "power", "year": "2025", "note": "150 MW on gas from Sept 2025, five years; 25% of demand", "amount": "150 MW", "url": "https://www.karpowership.com/gabon", "status": "operating"},
    {"src": "kp", "name": "Powership Rauf Bey, Port Sudan", "iso": "SD", "lon": 37.22, "lat": 19.62, "kind": "power", "year": "2018", "note": "150 MW, three years, extended 2021; 10% of national need", "amount": "150 MW", "url": "https://www.karpowership.com/sudan", "status": "operating"},
    {"src": "summa", "name": "Abu Nawas Resort", "iso": "LY", "lon": 13.19, "lat": 32.89, "kind": "mixed use", "year": "", "note": "Turnkey & Build Turnkey Of; client Alinmaa Holding Construction and Real Estate Development; placed on city (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/abu-nawas-resort.htm", "status": "built"},
    {"src": "summa", "name": "African Leadership University", "iso": "RW", "lon": 30.13, "lat": -1.93, "kind": "education", "year": "2019–2020", "note": "Build; client Innovation City Campus Ltd; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/african-leadership-university.htm", "status": "built"},
    {"src": "summa", "name": "Amahoro Stadium", "iso": "RW", "lon": 30.11, "lat": -1.95, "kind": "sports", "year": "2022–2024", "note": "Design & Build Turnkey; client Rwanda Housing Authority; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/amahoro-stadium.htm", "status": "built"},
    {"src": "summa", "name": "Blaise Diagne International Airport", "iso": "SN", "lon": -17.067711, "lat": 14.671116, "kind": "aviation & transport", "year": "2016–2017", "note": "Design & Build Turnkey; client AIBD SA; placed on site (company map)", "amount": None, "url": "https://www.summa.com.tr/en/projects/blaise-diagne-international-airport.htm", "status": "built"},
    {"src": "summa", "name": "Burj Al Baher Mixed Use Complex Phase 1", "iso": "LY", "lon": 13.19, "lat": 32.89, "kind": "mixed use", "year": "", "note": "Turnkey & Build Turnkey; client Burj Al Baher Tourism Investment JSC; placed on city (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/burj-al-baher-mixed-use-complex-phase-1.htm", "status": "built"},
    {"src": "summa", "name": "Burj Al Baher Mixed Use Complex Phase 2", "iso": "LY", "lon": 13.19, "lat": 32.89, "kind": "mixed use", "year": "", "note": "Turnkey & Build Turnkey Of; client Burj Al Baher Tourism Investment JSC; placed on city (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/burj-al-baher-mixed-use-complex-phase-2.htm", "status": "built"},
    {"src": "summa", "name": "Burj Bulayla", "iso": "LY", "lon": 13.19, "lat": 32.89, "kind": "offices", "year": "", "note": "Design & Build Turnkey Construction; client Al Tadamon Company for Real Estate Investment; placed on city (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/burj-bulayla.htm", "status": "built"},
    {"src": "summa", "name": "City of Democracy", "iso": "GA", "lon": 9.45, "lat": 0.39, "kind": "convention", "year": "2023–Ongoing", "note": "Design & Build Turnkey; client Presidency of the Republic; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/city-of-democracy.htm", "status": "building"},
    {"src": "summa", "name": "Courtyard Dakar Diamniadio", "iso": "SN", "lon": -17.18, "lat": 14.72, "kind": "hotel & resort", "year": "2023–2024", "note": "Design, Build, Own & Operate; client Summa; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/courtyard-dakar-diamniadio.htm", "status": "built"},
    {"src": "summa", "name": "Dakar Arena", "iso": "SN", "lon": -17.18, "lat": 14.73, "kind": "sports", "year": "", "note": "Design & Build Turnkey; client Republique du Senegal Presidence de la Republique SOGIP SA; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/dakar-arena.htm", "status": "built"},
    {"src": "summa", "name": "Dakar Expo Center", "iso": "SN", "lon": -17.185, "lat": 14.735, "kind": "convention", "year": "", "note": "Design & Build Turnkey; client Republique Du Senegal Presidence De La Republique SOGIP SA; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/dakar-expo-center.htm", "status": "built"},
    {"src": "summa", "name": "Dakar International Conference Center", "iso": "SN", "lon": -17.19517, "lat": 14.739737, "kind": "convention", "year": "October 2014", "note": "client Republic of Senegal Office of President Ministry of Finance of Senegal, Delegation of La Francophonie; placed on site (company map)", "amount": None, "url": "https://www.summa.com.tr/en/projects/dakar-international-conference-center.htm", "status": "built"},
    {"src": "summa", "name": "Diffa Airport", "iso": "NE", "lon": 13.32, "lat": 12.61, "kind": "aviation & transport", "year": "2020–2021", "note": "Design & Build; client Ministry of Transport; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/diffa-airport.htm", "status": "built"},
    {"src": "summa", "name": "Diori Hamani International Airport", "iso": "NE", "lon": 2.17868, "lat": 13.477095, "kind": "aviation & transport", "year": "2018–2019", "note": "BOT; client Ministry of Transport; placed on site (company map)", "amount": None, "url": "https://www.summa.com.tr/en/projects/diori-hamani-international-airport.htm", "status": "built"},
    {"src": "summa", "name": "Doutchi - Tsernaoua Road", "iso": "NE", "lon": 4.03, "lat": 13.64, "kind": "aviation & transport", "year": "2021–2023", "note": "Build; client Ministry of Equipment; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/doutchi-tsernaoua-road.htm", "status": "built"},
    {"src": "summa", "name": "Freetown International Airport", "iso": "SL", "lon": -13.2, "lat": 8.62, "kind": "aviation & transport", "year": "2021–2023", "note": "BOT; client Ministry of Transport; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/freetown-international-airport.htm", "status": "built"},
    {"src": "summa", "name": "Haiti Street Office Building", "iso": "LY", "lon": 13.19, "lat": 32.89, "kind": "offices", "year": "", "note": "Turnkey & Build Turnkey Of; client Alinmaa Holding Construction and Real Estate Development; placed on city (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/haiti-street-office-building.htm", "status": "built"},
    {"src": "summa", "name": "Kigali Arena", "iso": "RW", "lon": 30.115657, "lat": -1.953114, "kind": "sports", "year": "2019–2019", "note": "Design & Build Turnkey; client Rwanda Housing Authority & Ministry of Sports and Culture; placed on site (company map)", "amount": None, "url": "https://www.summa.com.tr/en/projects/kigali-arena.htm", "status": "built"},
    {"src": "summa", "name": "Kigali Convention Center and Hotel", "iso": "RW", "lon": 30.087938, "lat": -1.952143, "kind": "mixed use", "year": "April 2016", "note": "client Ultimate Concepts Limited; placed on site (company map)", "amount": None, "url": "https://www.summa.com.tr/en/projects/kigali-convention-center-and-hotel.htm", "status": "built"},
    {"src": "summa", "name": "Ministry of Finance Building", "iso": "NE", "lon": 2.106335, "lat": 13.517435, "kind": "government buildings", "year": "2019–2020", "note": "Design & Build Turnkey; client Ministry of Finance; placed on site (company map)", "amount": None, "url": "https://www.summa.com.tr/en/projects/ministry-of-finance-building.htm", "status": "built"},
    {"src": "summa", "name": "Osvaldo Vieira International Airport", "iso": "GW", "lon": -15.65, "lat": 11.89, "kind": "aviation & transport", "year": "2023–Ongoing", "note": "BOT; client Ministry of Transport & Communications; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/osvaldo-vieira-international-airport.htm", "status": "building"},
    {"src": "summa", "name": "Radisson Blu Al Mahary Hotel", "iso": "LY", "lon": 13.19, "lat": 32.89, "kind": "hotel & resort", "year": "", "note": "Turnkey Construction; client New York Investment; placed on city (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/radisson-blu-al-mahary-hotel.htm", "status": "built"},
    {"src": "summa", "name": "Radisson Blu Hotel & Conference Center", "iso": "NE", "lon": 2.104287, "lat": 13.512594, "kind": "hotel & resort", "year": "2018–2019", "note": "Design, Build, Own & Operate; client Summa; placed on site (company map)", "amount": None, "url": "https://www.summa.com.tr/en/projects/radisson-blu-hotel-conference-center.htm", "status": "built"},
    {"src": "summa", "name": "Radisson Hotel Dakar Diamniadio", "iso": "SN", "lon": -17.19, "lat": 14.74, "kind": "hotel & resort", "year": "", "note": "Design & Build Turnkey; client Republique Du Senegal Presidence De La Republique SOGIP SA; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/radisson-hotel-dakar-diamniadio.htm", "status": "built"},
    {"src": "summa", "name": "Senegal Stadium", "iso": "SN", "lon": -17.17, "lat": 14.72, "kind": "sports", "year": "2020–2022", "note": "Design & Build Turnkey; client SOGIP SA; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/senegal-stadium.htm", "status": "built"},
    {"src": "summa", "name": "Sipopo Congress Center", "iso": "GQ", "lon": 8.902245, "lat": 3.752997, "kind": "convention", "year": "June 2011", "note": "client Government of Equatorial Guinea; placed on site (company map)", "amount": None, "url": "https://www.summa.com.tr/en/projects/sipopo-congress-center.htm", "status": "built"},
    {"src": "summa", "name": "Sipopo Mall", "iso": "GQ", "lon": 8.9, "lat": 3.75, "kind": "shopping mall", "year": "", "note": "Turnkey Construction; client GE Proyektos; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/sipopo-mall.htm", "status": "built"},
    {"src": "summa", "name": "Sofitel Hotel & Cotonou International Conference Center", "iso": "BJ", "lon": 2.42, "lat": 6.35, "kind": "hotel & resort", "year": "2021–2023", "note": "Turnkey Construction; client Ministry of Finance & Economy; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/sofitel-hotel-cotonou-international-conference-center.htm", "status": "built"},
    {"src": "summa", "name": "TER AIBD Station", "iso": "SN", "lon": -17.07, "lat": 14.67, "kind": "aviation & transport", "year": "2022–2023", "note": "Design & Build Turnkey; client APIX SA; placed on town (hand-placed)", "amount": None, "url": "https://www.summa.com.tr/en/projects/ter-aibd-station.htm", "status": "built"},
]

WORK_SOURCE = {"exim": "Türk Eximbank", "ym": "Yapı Merkezi", "kp": "Karpowership", "summa": "Summa", "gem": "Global Energy Monitor"}
WORK_STATUS = {"built": "operating", "operating": "operating", "building": "under_construction",
               "announced": "announced", "ended": "stalled", "unknown": "announced"}


def _csv_rows(url, label, tries=6):
    """One OECD CSV; the public endpoint answers bursts with HTTP 429, so a
    refused call waits and tries again."""
    import csv, io, time, urllib.error
    for attempt in range(tries):
        try:
            raw = get(url, timeout=300)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < tries - 1:
                wait = 20 * (attempt + 1)
                print(f"   {label}: throttled (429), waiting {wait} s")
                time.sleep(wait)
                continue
            if e.code == 404:
                print(f"   {label}: no records (404)")
                return []
            raise
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    print(f"   {label}: {len(rows):,} rows, {len(raw) / 1024 / 1024:.1f} MB")
    return rows


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def crs_activities(donor, y0, y1, per_year=False):
    """One provider's CRS activities with an African recipient, one record per
    activity, commitments and disbursements in current USD million. The
    endpoint gives four rows per activity (commitment and disbursement, current
    and constant prices) and the commitment and disbursement rows carry
    different microdata ids, so the activity is keyed on the OECD id they share.
    A large provider is fetched one year at a time (Italy: 12 MB a year)."""
    rec = "+".join(CRS_AFRICA + list(CRS_REGIONS))
    if per_year:
        rows = []
        for y in range(y0, y1 + 1):
            rows += _csv_rows(CRS.format(donor=donor, recipients=rec, y0=y, y1=y), f"OECD CRS {y}")
    else:
        rows = _csv_rows(CRS.format(donor=donor, recipients=rec, y0=y0, y1=y1), "OECD CRS")
    acts = {}
    for r in rows:
        if r["PRICE_BASE"] != "V":
            continue
        # a few rows carry no OECD id; their commitment and disbursement rows
        # are matched on everything else they state
        key = donor + ":" + (r["OECD_ID"] or "|".join((r["TIME_PERIOD"], r["RECIPIENT"], r["SECTOR"], r["PROJECT_TITLE"] or "",
                                                       r["SHORT_DESCRIPTION"] or "", r["LONG_DESCRIPTION"] or "",
                                                       r["CHANNELDELIVERY_NAME"] or "", r["FINANCETYPE_NAME"] or "")))
        a = acts.setdefault(key, {
            "id": r["OECD_ID"] or r["MD_ID"], "donor": r.get("Donor") or donor, "year": int(r["TIME_PERIOD"]), "iso": ISO3_TO_2.get(r["RECIPIENT"]),
            "recipient": r["Recipient"], "code": r["SECTOR"], "sector": r["Sector"],
            "title": r["PROJECT_TITLE"] or "", "short": r["SHORT_DESCRIPTION"] or "", "desc": r["LONG_DESCRIPTION"] or "",
            "channel": r["CHANNELDELIVERY_NAME"] or "", "finance": r["FINANCETYPE_NAME"] or "", "measure": r["Measure"],
            "agency": r.get("Donor agency") or r.get("DONOR_AGENCY") or "",
            "commit": None, "disb": None})
        v = _num(r["OBS_VALUE"])
        if r["FLOW_TYPE"] == "C":
            a["commit"] = v
        elif r["FLOW_TYPE"] == "D":
            a["disb"] = v
    return list(acts.values())


def _hard(a):
    """Does the activity build, renovate or drill something? Purpose code
    first, then the words of the title and descriptions."""
    t = a["title"] + " " + a["short"] + " " + a["desc"]
    return a["code"][:2] in CRS_HARD_PREFIX or a["code"] in CRS_HARD_CODES or CRS_HARD_WORDS.search(t) is not None


def _rec(a):
    return {"year": a["year"], "iso": a["iso"], "recipient": a["recipient"], "usd": round(a["commit"] or a["disb"] or 0, 3),
            "code": a["code"], "sector": a["sector"], "title": a["title"], "desc": a["desc"], "id": a["id"],
            "channel": a["channel"], "finance": a["finance"]}


def crs_block(acts, y0, y1, donor_label):
    """The aid block of a profile: counts and dollars by year, country and
    purpose, the largest records, the subset that builds something."""
    import collections
    amt = lambda a: a["commit"] or a["disb"] or 0
    by_year = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    by_c = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    by_sec = collections.defaultdict(lambda: {"n": 0, "usd": 0.0, "name": ""})
    regional = {"n": 0, "usd": 0.0}
    for a in acts:
        by_year[a["year"]]["n"] += 1
        by_year[a["year"]]["usd"] += amt(a)
        if a["iso"]:
            by_c[a["iso"]]["n"] += 1
            by_c[a["iso"]]["usd"] += amt(a)
        else:
            regional["n"] += 1
            regional["usd"] += amt(a)
        s = by_sec[a["code"]]
        s["n"] += 1
        s["usd"] += amt(a)
        s["name"] = a["sector"]
    hard = [a for a in acts if _hard(a)]
    finance = collections.Counter(a["finance"] for a in acts)
    channels = collections.Counter(a["channel"] for a in acts)
    measures = collections.Counter(a["measure"] for a in acts)
    agencies = collections.Counter(a["agency"] for a in acts)
    providers = collections.Counter(a.get("donor") or "" for a in acts)
    # every purpose folded into the broad groups, and the money (not only the
    # count) by measure: what the lender comparison reads, kept whole
    by_grp = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    for a in acts:
        g = by_grp[crs_group(a["code"])]
        g["n"] += 1
        g["usd"] += amt(a)
    measures_usd = collections.defaultdict(float)
    for a in acts:
        measures_usd[a["measure"]] += amt(a)
    crs = {
        "source": f"OECD Creditor Reporting System (CRS), {donor_label} as provider, activity-level microdata",
        "url": "https://data-explorer.oecd.org/?fs[0]=Topic%2C1%7CDevelopment%23DEV%23&pg=0&snb=24&df[ds]=dsDisseminateFinalDMZ&df[id]=DSD_CRS%40DF_CRS&df[ag]=OECD.DCD.FSD",
        "api": CRS.split("?")[0], "licence": "OECD terms of use (free reuse with attribution)",
        "from": y0, "to": y1, "n": len(acts), "usd": round(sum(amt(a) for a in acts), 2),
        "titles": len({a["title"] for a in acts}),
        "named_place": 0,
        "years": {str(y): {"n": v["n"], "usd": round(v["usd"], 2)} for y, v in sorted(by_year.items())},
        "countries": {iso: {"name": NAME[iso], "n": v["n"], "usd": round(v["usd"], 2)} for iso, v in by_c.items()},
        "regional": {"n": regional["n"], "usd": round(regional["usd"], 2)},
        "sectors": sorted([{"code": k, "name": v["name"], "n": v["n"], "usd": round(v["usd"], 2)} for k, v in by_sec.items()],
                          key=lambda r: -r["usd"])[:14],
        "largest": [_rec(a) for a in sorted(acts, key=lambda a: -amt(a))[:20]],
        "hard": {"n": len(hard), "usd": round(sum(amt(a) for a in hard), 2),
                 "rows": [_rec(a) for a in sorted(hard, key=lambda a: -amt(a))[:14]]},
        "finance": finance.most_common(6), "channels": channels.most_common(6), "measures": measures.most_common(4),
        "agencies": agencies.most_common(10),
        "groups": {k: {"n": v["n"], "usd": round(v["usd"], 2)} for k, v in sorted(by_grp.items())},
        "measures_usd": {k: round(v, 2) for k, v in sorted(measures_usd.items())},
        "providers": [[k, n, round(sum(amt(a) for a in acts if (a.get("donor") or "") == k), 1)] for k, n in providers.most_common()],
    }
    # a title that names a town or a site would be a placeable record; count them
    towns = re.compile(r"\b(?:IN|AT|OF)\s+[A-Z][a-z]+", 0)
    crs["named_place"] = sum(1 for a in acts if re.search(r"\b(?:in|at)\s+[A-Z][a-z]{3,}", a["title"] + " " + a["desc"]) and "Africa" not in a["title"])
    print(f"   CRS: {len(acts):,} African activities {y0}–{y1}, USD {crs['usd']:,.0f} m committed; "
          f"{len(by_c)} countries, {crs['titles']} distinct titles, {len(hard):,} that build something")
    return crs


def oda_block(donor, donor_label):
    """Net ODA by recipient (DAC2a measure 206, current prices) since 2010."""
    import collections
    rows = _csv_rows(DAC2A.format(donor=donor, y0=2010), f"OECD DAC2a {donor}")
    oda_c, oda_reg, oda_oecd = collections.defaultdict(dict), collections.defaultdict(dict), {}
    for r in rows:
        if r["PRICE_BASE"] != "V" or r["OBS_VALUE"] in ("", None):
            continue
        v = round(float(r["OBS_VALUE"]), 3)
        rc = r["RECIPIENT"]
        if rc in ISO3_TO_2:
            oda_c[ISO3_TO_2[rc]][r["TIME_PERIOD"]] = v
        elif rc in CRS_REGIONS:
            oda_reg[rc][r["TIME_PERIOD"]] = v
        elif rc == "F":
            oda_oecd[r["TIME_PERIOD"]] = v
    years = sorted({y for s in list(oda_c.values()) + list(oda_reg.values()) for y in s}) or ["2010"]
    africa = {y: round(sum(s.get(y, 0) for s in oda_c.values()) + sum(s.get(y, 0) for s in oda_reg.values()), 2) for y in years}
    oda = {"source": f"OECD DAC2a, net ODA disbursements (measure 206), current prices, {donor_label} as provider",
           "api": DAC2A.split("?")[0], "licence": "OECD terms of use (free reuse with attribution)",
           "from": int(years[0]), "to": int(years[-1]),
           "africa": africa, "regional": {k: {y: s[y] for y in sorted(s)} for k, s in oda_reg.items()},
           "africa_oecd_aggregate": {y: oda_oecd[y] for y in sorted(oda_oecd)},
           "countries": {iso: {k: s[k] for k in sorted(s)} for iso, s in oda_c.items()}}
    print(f"   DAC2a: {len(oda_c)} recipients + {len(oda_reg)} regional rows, {oda['from']}–{oda['to']}; "
          f"Africa {oda['to']}: USD {africa[str(oda['to'])]:,.1f} m (OECD's own Africa aggregate: {oda_oecd.get(str(oda['to']), 0):,.1f})")
    return oda


def oda_block_multi(donors, label):
    """Net ODA of several providers, summed per recipient and year."""
    blocks = [oda_block(d, label) for d in donors]
    out = dict(blocks[0])
    out["africa"] = {}
    out["countries"] = {}
    out["regional"] = {}
    out["africa_oecd_aggregate"] = {}
    out["from"], out["to"] = min(b["from"] for b in blocks), max(b["to"] for b in blocks)
    for b in blocks:
        for y, v in b["africa"].items():
            out["africa"][y] = round(out["africa"].get(y, 0) + v, 2)
        for iso, sr in b["countries"].items():
            d = out["countries"].setdefault(iso, {})
            for y, v in sr.items():
                d[y] = round(d.get(y, 0) + v, 3)
    out["africa"] = {y: out["africa"][y] for y in sorted(out["africa"])}
    out["source"] = f"OECD DAC2a, net ODA disbursements (measure 206), current prices, {label} summed"
    return out


def fdi_block_multi(donors, label):
    """FDI stock of several reporters, summed per partner and year; a reporter
    with no African partners (Norway, Sweden publish none at this level) adds nothing."""
    blocks = [fdi_block(d, label) for d in donors]
    blocks = [b for b in blocks if b["countries"]]
    if not blocks:
        return None
    out = dict(blocks[0])
    out["countries"], out["flags"] = {}, {}
    out["from"], out["to"] = min(b["from"] for b in blocks), max(b["to"] for b in blocks)
    for b in blocks:
        for iso, sr in b["countries"].items():
            d = out["countries"].setdefault(iso, {})
            for y, v in sr.items():
                d[y] = round(d.get(y, 0) + v, 2)
    out["source"] = f"OECD FDI positions by partner country (BMD4), {label} outward, summed over the reporters"
    out["reporters"] = [d for d in donors]
    return out


def fdi_block(donor, donor_label):
    """Outward direct-investment stock by African partner country (BMD4)."""
    import collections
    rows = _csv_rows(FDI.format(donor=donor, y0=2015), f"OECD FDI positions {donor}")
    fdi_c, fdi_flag = collections.defaultdict(dict), collections.defaultdict(dict)
    for r in rows:
        ca = r["COUNTERPART_AREA"]
        if ca not in ISO3_TO_2 or r["OBS_VALUE"] in ("", None):
            continue
        fdi_c[ISO3_TO_2[ca]][r["TIME_PERIOD"]] = round(float(r["OBS_VALUE"]), 2)
        if r.get("OBS_STATUS") not in ("A", "", None) or r.get("CONF_STATUS") not in ("F", "", None):
            fdi_flag[ISO3_TO_2[ca]][r["TIME_PERIOD"]] = (r.get("OBS_STATUS") or "") + (r.get("CONF_STATUS") or "")
    fdi_years = sorted({y for s in fdi_c.values() for y in s}) or ["0"]
    fdi = {"source": f"OECD FDI positions by partner country (BMD4), {donor_label} outward, net, all resident units, immediate counterpart",
           "api": FDI.split("?")[0], "licence": "OECD terms of use (free reuse with attribution)",
           "from": int(fdi_years[0]), "to": int(fdi_years[-1]),
           "countries": {iso: {k: s[k] for k in sorted(s)} for iso, s in fdi_c.items()},
           "flags": {iso: f for iso, f in fdi_flag.items()}}
    print(f"   FDI: {len(fdi_c)} counterparts {fdi['from']}–{fdi['to']}; "
          f"Africa {fdi['to']}: USD {sum(s.get(str(fdi['to']), 0) for s in fdi_c.values()):,.0f} m")
    return fdi


def gem_owned(pattern):
    """Power units in the site's own assets layer whose owner matches."""
    out = []
    for f in json.loads((DATA / "gem_power_assets.geojson").read_text())["features"]:
        p = f["properties"]
        if not pattern.search(str(p.get("owner") or "")):
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        iso = next((k for k, v in NAME.items() if v == p.get("country")), None) or ISO3_TO_2.get(p.get("country"), p.get("country"))
        out.append({"name": p["name"], "unit": p.get("unit"), "iso": iso, "country": p.get("country"),
                    "lon": lon, "lat": lat, "mw": _num(p.get("capacity_mw")), "tech": p.get("tech"),
                    "status": p.get("dash_status"), "raw_status": p.get("raw_status"),
                    "year": p.get("start_year"), "owner": p.get("owner"), "url": p.get("url")})
    return out


def fetch_turkey():
    print("turkey  … OECD CRS microdata (donor TUR), DAC2a net ODA, FDI positions; World Bank IDS counterpart 055")
    # Turkey has reported at activity level since 2018; 2015–2017 are
    # "semi-aggregates", a hundred rows a year, so the window starts in 2018
    y0, y1 = 2018, 2024
    acts = crs_activities("TUR", y0, y1)
    crs = crs_block(acts, y0, y1, "Turkey")
    oda = oda_block("TUR", "Turkey")
    fdi = fdi_block("TUR", "Turkey")

    # --- sovereign debt owed to Turkey
    ids = ids_pack("055", "Turkey", since=2010)
    print(f"   IDS: {len(ids['countries'])} debtors, data to {ids['data_to']}, "
          f"stock {ids['continent'].get(str(ids['data_to']), 0) / 1e6:,.0f} m")

    # --- GEM units with a Turkish owner, from the site's own assets layer
    gem = gem_owned(TURKISH_OWNER)
    print(f"   GEM: {len(gem)} units with a Turkish owner in the assets layer")

    works = [{**w, "country": NAME[w["iso"]], "srcname": WORK_SOURCE[w["src"]],
              "site_status": WORK_STATUS.get(w["status"], "announced")} for w in TURKEY_WORKS]
    pack = {
        "slug": "turkey", "fetched": today(),
        "crs": crs, "oda": oda, "fdi": fdi, "ids": ids, "gem": gem, "works": works,
        "context": {
            # Turkish Contractors Association / Ministry of Trade statistics, 2025 edition: totals only
            "tmb": {"all_usd_bn": 534.4, "all_projects": 12478, "africa_share_pct": 18.1, "period": "1972–2024",
                    "src": "Turkish Contractors Association, overseas contracting statistics 2025"},
            # TİKA's own news feed by country (WordPress API, Turkish-language site), posts not projects
            "tika_posts": 645, "tika_countries": 25,
        },
    }
    update_meta("turkey", fetched=today(), crs_from=y0, crs_to=y1, crs_activities=len(acts),
                ids_updated=ids["updated"], data_to=ids["data_to"], works=len(works), gem=len(gem))
    return pack


# --------------------------------------------------------------- Italy

# Italian owners in Global Energy Monitor's trackers and TeleGeography's cable
# owners, matched as whole words (Perenco, Amarenco and Rencore are not Renco)
ITALIAN_OWNER = re.compile(r"\b(Eni|Enel|Enel Green Power|Building Energy|Renco Tek|Renco|Edison|Snam|Italgen|"
                           r"Falck Renewables|Saipem|Sparkle|Telecom Italia)\b", re.I)


def _line_path(geom, step=3):
    """A GeoJSON LineString or MultiLineString as a list of parts, each a list
    of (lon, lat), thinned to every `step`-th vertex (the profile map is small)."""
    coords = geom["coordinates"]
    parts = [coords] if geom["type"] == "LineString" else coords
    out = []
    for part in parts:
        pts = part[::step]
        if pts[-1] != part[-1]:
            pts = pts + [part[-1]]
        out.append([(round(x, 3), round(y, 3)) for x, y, *_ in pts])
    return out


def fetch_italy():
    print("italy   … OECD CRS microdata (donor ITA, one year at a time), DAC2a net ODA, FDI positions; "
          "World Bank IDS counterpart 006; Piano Mattei, GEM, pipelines and cables from the site's own layers")
    y0, y1 = 2018, 2024
    acts = crs_activities("ITA", y0, y1, per_year=True)
    crs = crs_block(acts, y0, y1, "Italy")
    oda = oda_block("ITA", "Italy")
    fdi = fdi_block("ITA", "Italy")
    ids = ids_pack("006", "Italy", since=2000)
    print(f"   IDS: {len(ids['countries'])} debtors, data to {ids['data_to']}, "
          f"stock {ids['continent'].get(str(ids['data_to']), 0) / 1e6:,.0f} m")

    # --- Piano Mattei, the Italian Government's own project list, as the map draws it
    mattei = []
    for f in json.loads((DATA / "piano_mattei.geojson").read_text())["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        mattei.append({"id": p["id"], "name": p["name"], "iso": p.get("country"), "countries": p.get("country_names") or [],
                       "lon": lon, "lat": lat, "directives": p.get("directives") or [], "sector": p.get("sector"),
                       "objective": p.get("objective"), "stage": p.get("stage"), "status": p.get("dash_status"),
                       "amount_eur": p.get("amount_eur"), "amount_text": p.get("amount_text"),
                       "amount_shared": p.get("amount_shared"), "implementer": p.get("implementer"),
                       "partners": p.get("partnerships") or p.get("international_partners"),
                       "resources": p.get("resources"), "precision": p.get("geo_precision"),
                       "place": p.get("location_name"), "url": p.get("url_en") or p.get("url")})
    print(f"   Piano Mattei: {len(mattei)} projects, EUR {sum(m['amount_eur'] or 0 for m in mattei) / 1e6:,.0f} m stated")

    gem = gem_owned(ITALIAN_OWNER)
    print(f"   GEM: {len(gem)} power units with an Italian owner in the assets layer")

    pipes = []
    for f in json.loads((DATA / "gem_oil_gas_pipelines.geojson").read_text())["features"]:
        p = f["properties"]
        if not ITALIAN_OWNER.search(str(p.get("owner") or "") + " " + str(p.get("parent") or "")):
            continue
        pipes.append({"name": p["name"], "pipeline": p.get("pipeline"), "segment": p.get("segment"), "fuel": p.get("fuel"),
                      "countries": p.get("countries") or [], "owner": p.get("owner"), "parent": p.get("parent"),
                      "status": p.get("dash_status") or p.get("status"), "year": p.get("start_year"),
                      "capacity": p.get("capacity"), "capacity_units": p.get("capacity_units"),
                      "km": p.get("km") or p.get("length_km"), "url": p.get("url"), "parts": _line_path(f["geometry"])})
    print(f"   pipelines: {len(pipes)} segments with Eni, Snam or Edison among the owners")

    cables = []
    for f in json.loads((DATA / "telegeography_cables.geojson").read_text())["features"]:
        p = f["properties"]
        if not ITALIAN_OWNER.search(str(p.get("owners") or "")):
            continue
        lps = [lp for lp in (p.get("landing_points") or []) if isinstance(lp, dict)]
        cables.append({"name": p["name"], "owners": p.get("owners"), "countries": p.get("countries") or [],
                       "rfs": p.get("rfs_year") or p.get("rfs"), "status": p.get("dash_status") or p.get("status"),
                       "km": p.get("length_km"), "url": p.get("url"), "landing_points": lps,
                       "parts": _line_path(f["geometry"], step=4)})
    print(f"   cables: {len(cables)} with Sparkle among the owners")

    pack = {"slug": "italy", "fetched": today(), "crs": crs, "oda": oda, "fdi": fdi, "ids": ids,
            "mattei": mattei, "gem": gem, "pipelines": pipes, "cables": cables}
    update_meta("italy", fetched=today(), crs_from=y0, crs_to=y1, crs_activities=len(acts),
                ids_updated=ids["updated"], data_to=ids["data_to"], mattei=len(mattei), gem=len(gem),
                pipelines=len(pipes), cables=len(cables))
    return pack


# --------------------------------------------------------------- China

# Chinese owners in Global Energy Monitor's trackers and TeleGeography's cable
# owners: state firms, provincial companies and the three carriers
CHINESE_OWNER = re.compile(
    r"\b(China|Chinese|Sinohydro|PowerChina|Power Construction Corporation of China|CHINT|CGN|Three Gorges|Gezhouba|"
    r"CMEC|Huaneng|Huadian|Datang|Shanghai Electric|Dongfang|Harbin|CNPC|PetroChina|Sinopec|CNOOC|Hanergy|Jinko|LONGi|"
    r"Trina|Goldwind|Shenzhen|Guangdong|Hunan|Hebei|Jiangsu|Zhejiang|Sichuan|Yunnan|Chongqing|Beijing|Xinjiang|Shandong|"
    r"Jiangxi|Anhui|Hong Kong|HMN|Huawei|PEACE Cable|Peace Cable|China Mobile|China Telecom|China Unicom|CCCC|CRBC|CRCC|"
    r"CSCEC|CITIC|CAMC|Norinco|Sino)\b", re.I)


def fetch_china():
    import collections
    print("china   … AidData GCDF 3.0 as the map draws it; World Bank IDS counterpart 730 (bilateral and all PPG); "
          "GEM, pipelines and cables from the site's own layers")
    recs = []
    for f in json.loads((DATA / "aiddata_china_finance.geojson").read_text())["features"]:
        p = f["properties"]
        recs.append({"id": p["aiddata_id"], "name": p["name"], "iso": p["country"], "recipient": p["recipient"],
                     "lon": p["lon"], "lat": p["lat"], "precision": p["geo_precision"], "place": p["place"],
                     "status": p["dash_status"], "raw_status": p["raw_status"], "sector": p["sector"],
                     "sector_name": p["sector_name"], "flow": p["flow_simple"], "flow_class": p["flow_class"],
                     "intent": p["intent"], "funders": p["funders"], "funder_types": p["funder_types"],
                     "implementers": p["implementers"], "cofinanced": p["cofinanced"],
                     "usd_2021": p["amount_usd_2021"], "usd_nominal": p["amount_nominal_usd"], "estimated": p["amount_estimated"],
                     "year": p["commitment_year"], "start": p["start_year"], "completion": p["completion_year"],
                     "maturity": p["maturity_years"], "rate": p["interest_rate"], "grace": p["grace_years"],
                     "grant_element": p["grant_element"], "distress": p["financial_distress"], "url": p["url"]})
    amt = lambda r: r["usd_2021"] or 0
    by_year = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    by_c = collections.defaultdict(lambda: {"n": 0, "usd": 0.0, "loans": 0.0})
    by_sec = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    by_fund = collections.defaultdict(lambda: {"n": 0, "usd": 0.0, "type": ""})
    by_impl = collections.Counter()
    for r in recs:
        if r["year"]:
            by_year[r["year"]]["n"] += 1
            by_year[r["year"]]["usd"] += amt(r)
        by_c[r["iso"]]["n"] += 1
        by_c[r["iso"]]["usd"] += amt(r)
        if r["flow"] == "Loan":
            by_c[r["iso"]]["loans"] += amt(r)
        by_sec[r["sector"]]["n"] += 1
        by_sec[r["sector"]]["usd"] += amt(r)
        for fu in (r["funders"] or "").split(";"):
            fu = fu.strip()
            if fu:
                by_fund[fu]["n"] += 1
                by_fund[fu]["usd"] += amt(r) / max(len((r["funders"] or "").split(";")), 1)
        for im in (r["implementers"] or "").split(";"):
            if im.strip():
                by_impl[im.strip()] += 1
    for fu, d in by_fund.items():
        d["type"] = next((r["funder_types"] for r in recs if fu in (r["funders"] or "")), "")
    china_meta = (load_meta().get("china") or {})
    aid = {
        "source": "AidData, Global Chinese Development Finance Dataset 3.0 with the Geospatial GCDF 3.0 footprints, as the map draws it",
        "url": "https://www.aiddata.org/data/aiddatas-global-chinese-development-finance-dataset-version-3-0",
        "licence": "ODC-By 1.0 (footprints ODbL)", "release": china_meta.get("release"), "fresh": china_meta.get("fresh"),
        "from": min(by_year), "to": max(by_year), "n": len(recs), "usd": round(sum(amt(r) for r in recs) / 1e6, 1),
        "loans_n": sum(1 for r in recs if r["flow"] == "Loan"), "loans_usd": round(sum(amt(r) for r in recs if r["flow"] == "Loan") / 1e6, 1),
        "grants_n": sum(1 for r in recs if r["flow"] == "Grant"), "grants_usd": round(sum(amt(r) for r in recs if r["flow"] == "Grant") / 1e6, 1),
        "estimated_n": sum(1 for r in recs if r["estimated"]), "cofinanced_n": sum(1 for r in recs if r["cofinanced"]),
        "distress_n": sum(1 for r in recs if r["distress"]),
        "status": dict(collections.Counter(r["status"] for r in recs)),
        "precision": dict(collections.Counter(r["precision"] for r in recs)),
        "flow_class": dict(collections.Counter(r["flow_class"] for r in recs)),
        "intent": dict(collections.Counter(r["intent"] for r in recs)),
        "years": {str(y): {"n": v["n"], "usd": round(v["usd"] / 1e6, 1)} for y, v in sorted(by_year.items())},
        "countries": {iso: {"name": NAME.get(iso, iso), "n": v["n"], "usd": round(v["usd"] / 1e6, 1), "loans": round(v["loans"] / 1e6, 1)} for iso, v in by_c.items()},
        "sectors": sorted([{"sector": k, "n": v["n"], "usd": round(v["usd"] / 1e6, 1)} for k, v in by_sec.items()], key=lambda r: -r["usd"]),
        "funders": sorted([{"funder": k, "type": v["type"], "n": v["n"], "usd": round(v["usd"] / 1e6, 1)} for k, v in by_fund.items()], key=lambda r: -r["usd"])[:14],
        "implementers": by_impl.most_common(12),
        "largest": sorted(recs, key=lambda r: -amt(r))[:20],
        "left_out": {k: china_meta.get(k) for k in ("umbrella", "pledges", "not_infrastructure", "unlocated")},
        "footprints": china_meta.get("footprints"),
    }
    print(f"   AidData: {len(recs):,} projects {aid['from']}–{aid['to']}, USD {aid['usd'] / 1000:,.1f} bn (2021 USD); "
          f"{aid['loans_n']:,} loans USD {aid['loans_usd'] / 1000:,.1f} bn; {len(by_c)} countries")

    ids_all = ids_pack("730", "China", since=2000, kind="DPPG")
    ids_bl = ids_pack("730", "China", since=2000, kind="BLAT")
    print(f"   IDS: all PPG debt to Chinese creditors {ids_all['continent'].get(str(ids_all['data_to']), 0) / 1e9:,.1f} bn "
          f"({len(ids_all['countries'])} debtors), bilateral official {ids_bl['continent'].get(str(ids_bl['data_to']), 0) / 1e9:,.1f} bn, data to {ids_all['data_to']}")

    gem = gem_owned(CHINESE_OWNER)
    print(f"   GEM: {len(gem)} power units with a Chinese owner in the assets layer")
    pipes = []
    for f in json.loads((DATA / "gem_oil_gas_pipelines.geojson").read_text())["features"]:
        p = f["properties"]
        if not CHINESE_OWNER.search(str(p.get("owner") or "") + " " + str(p.get("parent") or "")):
            continue
        pipes.append({"name": p["name"], "pipeline": p.get("pipeline"), "segment": p.get("segment"), "fuel": p.get("fuel"),
                      "countries": p.get("countries") or [], "owner": p.get("owner"), "parent": p.get("parent"),
                      "status": p.get("dash_status"), "year": p.get("start_year"), "km": p.get("length_km"),
                      "url": p.get("url"), "parts": _line_path(f["geometry"])})
    print(f"   pipelines: {len(pipes)} segments with a Chinese owner or parent")
    cables = []
    for f in json.loads((DATA / "telegeography_cables.geojson").read_text())["features"]:
        p = f["properties"]
        if not CHINESE_OWNER.search(str(p.get("owners") or "")):
            continue
        lps = [lp for lp in (p.get("landing_points") or []) if isinstance(lp, dict)]
        cables.append({"name": p["name"], "owners": p.get("owners"), "countries": p.get("countries") or [],
                       "rfs": p.get("rfs_year") or p.get("rfs"), "status": p.get("dash_status"), "km": p.get("length_km"),
                       "url": p.get("url"), "landing_points": lps, "parts": _line_path(f["geometry"], step=4)})
    print(f"   cables: {len(cables)} with a Chinese carrier or company among the owners")

    pack = {"slug": "china", "fetched": today(), "aid": aid, "ids": ids_all, "ids_bilateral": ids_bl,
            "gem": gem, "pipelines": pipes, "cables": cables}
    update_meta("china_profile", fetched=today(), projects=len(recs), ids_updated=ids_all["updated"],
                data_to=ids_all["data_to"], gem=len(gem), pipelines=len(pipes), cables=len(cables))
    return pack


# ------------------------------------------------------ European Union

# DAC purpose-code prefixes -> the map's sector buckets, as the dashboard build uses them
DAC_SECTOR = [("210", "transport"), ("220", "ict"), ("23", "energy"), ("140", "water"), ("321", "industry"),
              ("322", "industry"), ("323", "industry"), ("331", "trade"), ("410", "environment")]


def _dac_bucket(codes):
    for c in codes or []:
        for pre, bucket in DAC_SECTOR:
            if str(c).startswith(pre):
                return bucket
    return "other"


def layer_block(path, lender_label, money_key, currency_rate, year_key="start_year"):
    """A profile's block from one of the map's own finance layers: records by
    year, country, sector bucket, publisher and status, the largest records,
    the placement tiers. Money in USD million at the stated rate."""
    import collections
    from shared import EUR_NOTE
    recs = []
    for f in json.loads((DATA / path).read_text())["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        eur = p.get(money_key) or 0
        recs.append({"id": p.get("iati_id") or p.get("id"), "name": p["name"], "iso": p.get("country"),
                     "countries": p.get("countries") or ([p["country"]] if p.get("country") else []),
                     "lon": lon, "lat": lat, "publisher": p.get("publisher"), "lender": p.get("lender"), "kind": p.get("kind"),
                     "status": p.get("dash_status"), "sector": p.get("sector") or _dac_bucket(p.get("sector_codes")),
                     "sector_label": p.get("sector_label"), "codes": p.get("sector_codes") or [],
                     "eur": eur, "usd_m": round(eur * currency_rate / 1e6, 3), "disbursed": p.get("disbursed"),
                     "year": int(p[year_key]) if p.get(year_key) else None, "end_year": p.get("end_year"),
                     "precision": p.get("geo_precision"), "place": p.get("location_name"),
                     "implementers": p.get("implementers"), "instrument": p.get("instrument"),
                     "aid_type": p.get("aid_type_name"), "url": p.get("project_url") or ""})
    by_year = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    by_c = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    by_sec = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    by_pub = collections.defaultdict(lambda: {"n": 0, "usd": 0.0})
    regional = {"n": 0, "usd": 0.0}
    for r in recs:
        if r["year"]:
            by_year[r["year"]]["n"] += 1
            by_year[r["year"]]["usd"] += r["usd_m"]
        if r["iso"]:
            by_c[r["iso"]]["n"] += 1
            by_c[r["iso"]]["usd"] += r["usd_m"]
        elif r["countries"]:
            for iso in r["countries"]:
                by_c[iso]["n"] += 1
                by_c[iso]["usd"] += r["usd_m"] / len(r["countries"])
        else:
            regional["n"] += 1
            regional["usd"] += r["usd_m"]
        by_sec[r["sector"]]["n"] += 1
        by_sec[r["sector"]]["usd"] += r["usd_m"]
        by_pub[r["lender"] or r["publisher"]]["n"] += 1
        by_pub[r["lender"] or r["publisher"]]["usd"] += r["usd_m"]
    return {
        "source": f"{lender_label}, as the map draws it", "rate_note": EUR_NOTE, "n": len(recs),
        "usd": round(sum(r["usd_m"] for r in recs), 1), "eur": round(sum(r["eur"] for r in recs) / 1e6, 1),
        "from": min(by_year) if by_year else None, "to": max(by_year) if by_year else None,
        "status": dict(collections.Counter(r["status"] for r in recs)),
        "kind": dict(collections.Counter(r["kind"] for r in recs)),
        "precision": dict(collections.Counter(str(r["precision"]) for r in recs)),
        "years": {str(y): {"n": v["n"], "usd": round(v["usd"], 1)} for y, v in sorted(by_year.items())},
        "countries": {iso: {"name": NAME.get(iso, iso), "n": v["n"], "usd": round(v["usd"], 1)} for iso, v in by_c.items() if iso in NAME},
        "regional": {"n": regional["n"], "usd": round(regional["usd"], 1)},
        "sectors": sorted([{"sector": k, "n": v["n"], "usd": round(v["usd"], 1)} for k, v in by_sec.items()], key=lambda r: -r["usd"]),
        "publishers": sorted([{"publisher": k, "n": v["n"], "usd": round(v["usd"], 1)} for k, v in by_pub.items()], key=lambda r: -r["usd"]),
        "largest": sorted(recs, key=lambda r: -r["usd_m"])[:20],
        "points": [{"name": r["name"][:140], "lon": r["lon"], "lat": r["lat"], "status": r["status"], "usd_m": r["usd_m"],
                    "lender": r["lender"], "kind": r["kind"], "year": r["year"], "precision": r["precision"],
                    "country": NAME.get(r["iso"], r["iso"]) if r["iso"] else "regional"}
                   for r in sorted(recs, key=lambda r: -r["usd_m"])[:150]],
    }


def fetch_eu():
    from shared import EUR_USD
    print("eu      … OECD CRS microdata (EU institutions, 4EU001, one year at a time), DAC2a net ODA; "
          "World Bank IDS counterparts 919 (EIB) and 975+918+917 (EU budget, EDF, EEC); the map's EU finance layer")
    y0, y1 = 2018, 2024
    acts = crs_activities("4EU001", y0, y1, per_year=True)
    crs = crs_block(acts, y0, y1, "the EU institutions")
    oda = oda_block("4EU001", "the EU institutions")
    ids = ids_pack("919", "European Investment Bank", since=2000, kind="DPPG")
    ids_eu = ids_pack(("975", "918", "917"), "European Union, European Development Fund and EEC", since=2000, kind="DPPG")
    print(f"   IDS: owed to the EIB {ids['continent'].get(str(ids['data_to']), 0) / 1e9:,.1f} bn ({len(ids['countries'])} debtors), "
          f"to the EU budget, EDF and EEC {ids_eu['continent'].get(str(ids_eu['data_to']), 0) / 1e9:,.2f} bn, data to {ids['data_to']}")
    layer = layer_block("iati_eu_finance.geojson", "European Commission contracts and decisions and EIB operations from IATI", "commitment", EUR_USD)
    print(f"   EU layer: {layer['n']:,} records, EUR {layer['eur'] / 1000:,.1f} bn committed; publishers {[(x['publisher'], x['n']) for x in layer['publishers']]}")
    pack = {"slug": "eu", "fetched": today(), "crs": crs, "oda": oda, "fdi": None, "ids": ids, "ids_eu": ids_eu, "layer": layer}
    update_meta("eu_profile", fetched=today(), crs_from=y0, crs_to=y1, crs_activities=len(acts),
                ids_updated=ids["updated"], data_to=ids["data_to"], layer_records=layer["n"])
    return pack


# -------------------------------------------------------- United States

# United States owners in GEM's trackers and the cable owners: the oil majors,
# the utilities and equipment makers that keep stakes, the platforms that own cables
US_OWNER = re.compile(r"\b(ExxonMobil|Exxon Mobil|Exxon|Chevron|Apache Corp|APA Corp|Kosmos|Hess Corp|Marathon Oil|ConocoPhillips|"
                      r"Occidental|Noble Energy|Anadarko|General Electric|GE Vernova|AES Corp|Symbion|Caterpillar|Bechtel|"
                      r"Google|Meta|Facebook|AT&T|Verizon|Microsoft|Amazon)\b", re.I)


def fetch_usa():
    print("usa     … OECD CRS microdata (donor USA, one year at a time, ~55 MB a year), DAC2a net ODA, FDI positions; "
          "World Bank IDS counterpart 302; GEM, pipelines and cables from the site's own layers")
    y0, y1 = 2018, 2024
    acts = crs_activities("USA", y0, y1, per_year=True)
    crs = crs_block(acts, y0, y1, "the United States")
    oda = oda_block("USA", "the United States")
    fdi = fdi_block("USA", "United States")
    ids = ids_pack("302", "United States", since=2000)
    print(f"   IDS: {len(ids['countries'])} debtors, data to {ids['data_to']}, stock {ids['continent'].get(str(ids['data_to']), 0) / 1e6:,.0f} m")
    gem = gem_owned(US_OWNER)
    pipes = [pp for pp in _pipes_owned(US_OWNER)]
    cables = _cables_owned(US_OWNER)
    print(f"   GEM {len(gem)} power units, {len(pipes)} pipeline segments, {len(cables)} cables with a US owner")
    pack = {"slug": "usa", "fetched": today(), "crs": crs, "oda": oda, "fdi": fdi, "ids": ids,
            "gem": gem, "pipelines": pipes, "cables": cables}
    update_meta("usa_profile", fetched=today(), crs_from=y0, crs_to=y1, crs_activities=len(acts),
                ids_updated=ids["updated"], data_to=ids["data_to"], gem=len(gem), pipelines=len(pipes), cables=len(cables))
    return pack


# -------------------------------------------------------------- Germany

GERMAN_OWNER = re.compile(r"\b(Siemens|RWE|EnBW|Uniper|E\.ON|Wintershall|juwi|Juwi|BayWa|ib vogt|Deutsche Telekom|DEG|KfW|"
                          r"Nordex|Enercon|Hochtief|Bilfinger|ThyssenKrupp|Thyssenkrupp|Bosch|MAN Energy)\b", re.I)


def fetch_germany():
    print("germany … OECD CRS microdata (donor DEU, one year at a time, ~27 MB a year), DAC2a net ODA, FDI positions; "
          "World Bank IDS counterpart 005; GEM, pipelines and cables from the site's own layers")
    y0, y1 = 2018, 2024
    acts = crs_activities("DEU", y0, y1, per_year=True)
    crs = crs_block(acts, y0, y1, "Germany")
    oda = oda_block("DEU", "Germany")
    fdi = fdi_block("DEU", "Germany")
    ids = ids_pack("005", "Germany", since=2000)
    print(f"   IDS: {len(ids['countries'])} debtors, data to {ids['data_to']}, stock {ids['continent'].get(str(ids['data_to']), 0) / 1e6:,.0f} m")
    gem = gem_owned(GERMAN_OWNER)
    pipes = _pipes_owned(GERMAN_OWNER)
    cables = _cables_owned(GERMAN_OWNER)
    print(f"   GEM {len(gem)} power units, {len(pipes)} pipeline segments, {len(cables)} cables with a German owner")
    pack = {"slug": "germany", "fetched": today(), "crs": crs, "oda": oda, "fdi": fdi, "ids": ids,
            "gem": gem, "pipelines": pipes, "cables": cables}
    update_meta("germany_profile", fetched=today(), crs_from=y0, crs_to=y1, crs_activities=len(acts),
                ids_updated=ids["updated"], data_to=ids["data_to"], gem=len(gem), pipelines=len(pipes), cables=len(cables))
    return pack


def _pipes_owned(pattern):
    out = []
    for f in json.loads((DATA / "gem_oil_gas_pipelines.geojson").read_text())["features"]:
        p = f["properties"]
        if not pattern.search(str(p.get("owner") or "") + " " + str(p.get("parent") or "")):
            continue
        out.append({"name": p["name"], "pipeline": p.get("pipeline"), "segment": p.get("segment"), "fuel": p.get("fuel"),
                    "countries": p.get("countries") or [], "owner": p.get("owner"), "parent": p.get("parent"),
                    "status": p.get("dash_status"), "year": p.get("start_year"), "km": p.get("length_km"),
                    "url": p.get("url"), "parts": _line_path(f["geometry"])})
    return out


def _cables_owned(pattern):
    out = []
    for f in json.loads((DATA / "telegeography_cables.geojson").read_text())["features"]:
        p = f["properties"]
        if not pattern.search(str(p.get("owners") or "")):
            continue
        lps = [lp for lp in (p.get("landing_points") or []) if isinstance(lp, dict)]
        out.append({"name": p["name"], "owners": p.get("owners"), "countries": p.get("countries") or [],
                    "rfs": p.get("rfs_year") or p.get("rfs"), "status": p.get("dash_status"), "km": p.get("length_km"),
                    "url": p.get("url"), "landing_points": lps, "parts": _line_path(f["geometry"], step=4)})
    return out


# ------------------------------------------- France, Spain, Japan, the Nordics, the Gulf

FRENCH_OWNER = re.compile(r"\b(TotalEnergies|Total SA|Total E&P|EDF|Électricité de France|Engie|ENGIE|Voltalia|Perenco|Orange|Vinci|"
                          r"Bouygues|Eiffage|Meridiam|Proparco|Akuo|Neoen|Qair|Maurel|Schneider Electric|Alstom|Veolia|Suez|Eramet|"
                          r"Bolloré|Bollore|CMA CGM|Technip)\b", re.I)
SPANISH_OWNER = re.compile(r"\b(Naturgy|Iberdrola|Acciona|Repsol|Enagás|Enagas|Elecnor|Abengoa|Cepsa|Telefónica|Telefonica|SENER|Sener|"
                           r"Cobra|Grupo TSK|Endesa|Prodiel|Grenergy|Zelestra|Solarpack|Soltec)\b", re.I)
JAPANESE_OWNER = re.compile(r"\b(Toyota Tsusho|Eurus|Marubeni|Mitsubishi|Sumitomo|Mitsui|JERA|Sojitz|Itochu|Hitachi|Toshiba|JGC|Chiyoda|"
                            r"INPEX|JOGMEC|Kansai Electric|Kyushu Electric|Tokyo Gas|Osaka Gas|NTT|KDDI|SoftBank|Komatsu|Yokogawa)\b", re.I)
NORDIC_OWNER = re.compile(r"\b(Scatec|Norfund|Equinor|Statoil|Statkraft|Vestas|Ørsted|Orsted|Aker|Telenor|Finnfund|Fortum|Wärtsilä|Wartsila|"
                          r"Vattenfall|Ericsson|IFU|Swedfund|Climate Investor|KLP|Frontier Energy|Norsk Hydro|Yara|Maersk)\b", re.I)
# the Gulf's companies in GEM's power and pipeline layers; the carriers' names in cable ownership
GULF_OWNER = re.compile(r"\b(Masdar|AMEA Power|AMEA|ACWA Power|ACWA|TAQA|Mubadala|Abu Dhabi|ADNOC|Alpha Dhabi|QatarEnergy|Qatar Petroleum|"
                        r"Qatar Investment|QIA|Dubai|DP World|Phanes|Al Nowais|Alcazar|Yellow Door|Saudi Aramco|Aramco|Kuwait Petroleum|"
                        r"Kuwait Foreign Petroleum|KUFPEC|Crescent Petroleum|Dana Gas|Emirates National Oil|ENOC|Gulf Energy)\b", re.I)
GULF_CABLE_OWNER = re.compile(r"\b(du|e&|Etisalat|Mobily|STC|Saudi Telecom|center3|Ooredoo|Zain|Omantel|Batelco|Qatar)\b", re.I)

PROFILES = {
    "france": {"label": "France", "adj": "French", "donors": ["FRA"], "per_year": True, "cp": "004", "since": 2000,
               "gem": FRENCH_OWNER, "cables": FRENCH_OWNER},
    "spain": {"label": "Spain", "adj": "Spanish", "donors": ["ESP"], "per_year": True, "cp": "050", "since": 2000,
              "gem": SPANISH_OWNER, "cables": SPANISH_OWNER},
    "japan": {"label": "Japan", "adj": "Japanese", "donors": ["JPN"], "per_year": True, "cp": "701", "since": 2000,
              "gem": JAPANESE_OWNER, "cables": JAPANESE_OWNER},
    "nordics": {"label": "the Nordic countries", "adj": "Nordic", "donors": ["DNK", "FIN", "ISL", "NOR", "SWE"], "per_year": True,
                "cp": ("003", "018", "020", "008", "010"), "since": 2000, "gem": NORDIC_OWNER, "cables": NORDIC_OWNER,
                "fdi_donors": ["DNK", "FIN", "ISL", "NOR", "SWE"]},
    "gulf": {"label": "the Gulf states", "adj": "Gulf", "donors": ["ARE", "SAU", "KWT", "QAT"], "per_year": False,
             "cp": ("576", "566", "552", "561"), "since": 2000, "gem": GULF_OWNER, "cables": GULF_CABLE_OWNER,
             "fdi_donors": [],   # none of the four reports to the OECD's FDI collection
             "funds": ("921", "951", "976", "953", "980")},   # the Gulf-based funds: Arab Fund, OPEC Fund, Islamic Development Bank, BADEA, Arab technical-assistance fund
}


def fetch_profile(slug):
    spec = PROFILES[slug]
    label, donors = spec["label"], spec["donors"]
    print(f"{slug:8s}… OECD CRS microdata ({', '.join(donors)}), DAC2a net ODA, FDI positions; World Bank IDS; the site's own layers")
    y0, y1 = 2018, 2024
    acts = []
    for d in donors:
        acts += crs_activities(d, y0, y1, per_year=spec["per_year"])
    crs = crs_block(acts, y0, y1, label)
    oda = oda_block(donors[0], label) if len(donors) == 1 else oda_block_multi(donors, label)
    fdi_donors = spec.get("fdi_donors", donors)
    fdi = None if not fdi_donors else (fdi_block(fdi_donors[0], label) if len(fdi_donors) == 1 else fdi_block_multi(fdi_donors, label))
    if fdi and not fdi["countries"]:
        fdi = None
    ids = ids_pack(spec["cp"], label, since=spec["since"])
    print(f"   IDS: {len(ids['countries'])} debtors, data to {ids['data_to']}, stock {ids['continent'].get(str(ids['data_to']), 0) / 1e6:,.0f} m")
    pack = {"slug": slug, "fetched": today(), "crs": crs, "oda": oda, "fdi": fdi, "ids": ids,
            "gem": gem_owned(spec["gem"]), "pipelines": _pipes_owned(spec["gem"]), "cables": _cables_owned(spec["cables"])}
    if spec.get("funds"):
        pack["ids_funds"] = ids_pack(spec["funds"], "the Gulf-based development funds", since=spec["since"], kind="DPPG")
        print(f"   IDS funds: {len(pack['ids_funds']['countries'])} debtors, stock {pack['ids_funds']['continent'].get(str(ids['data_to']), 0) / 1e9:,.2f} bn")
    print(f"   layers: {len(pack['gem'])} power units, {len(pack['pipelines'])} pipeline segments, {len(pack['cables'])} cables")
    update_meta(slug + "_profile", fetched=today(), crs_from=y0, crs_to=y1, crs_activities=len(acts),
                ids_updated=ids["updated"], data_to=ids["data_to"], gem=len(pack["gem"]),
                pipelines=len(pack["pipelines"]), cables=len(pack["cables"]))
    return pack


FETCH = {"russia": fetch_russia, "turkey": fetch_turkey, "italy": fetch_italy, "china": fetch_china,
         "eu": fetch_eu, "usa": fetch_usa, "germany": fetch_germany}
FETCH.update({slug: (lambda s=slug: fetch_profile(s)) for slug in PROFILES})


def main(argv):
    wanted = argv or [d["slug"] for d in DONORS]
    unknown = [w for w in wanted if w not in FETCH]
    if unknown:
        sys.exit(f"no fetcher for {', '.join(unknown)}; known: {', '.join(FETCH)}")
    OUT.mkdir(parents=True, exist_ok=True)
    for slug in wanted:
        pack = FETCH[slug]()
        path = OUT / f"{slug}.json"
        path.write_text(json.dumps(pack, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"  -> {path.relative_to(path.parent.parent.parent)}  {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main(sys.argv[1:])
