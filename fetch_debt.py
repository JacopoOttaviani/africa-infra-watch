#!/usr/bin/env python3
"""
The data behind the debt section (docs/debt/) and the dashboard's "Who it
owes" box: what every African government owes, creditor by creditor, year by
year, from the World Bank's International Debt Statistics.

    python3 fetch_debt.py            -> data/debt.json

World Bank International Debt Statistics (IDS), API source 6, series
DT.DOD.DPPG.CD: public and publicly guaranteed (PPG) external debt
outstanding, current USD, by counterpart ("Counterpart-Area"): every lending
country (its government and its banks and suppliers together), every
multilateral institution, bondholders as one anonymous counterpart, and
"multiple lenders" for syndicated loans. One request per debtor returns every
creditor for every year in a few seconds, and the creditors add up exactly to
the World total. Open (CC BY 4.0), refreshed every December.

Use of IMF credit is a separate series (DT.DOD.DIMF.CD) that also carries the
SDR allocations of 2009 and 2021, which are not loans; it is fetched beside
the creditor table and shown beside it, never inside it.

Private debt that no government guarantees is not here: the IDS does not split
it by creditor. Nor is domestic debt.
"""

import concurrent.futures
import json
import sys
import time

from fetch_donors import AFRICA, NAME, centre
from fetch_sources import get as _get
from shared import DATA, today, update_meta

OUT = DATA / "debt.json"
FIRST_YEAR = 2000          # the pack keeps 2000 onwards; the API goes back to 1970

API = "https://api.worldbank.org/v2/sources/6"
BY_CREDITOR = (API + "/country/{iso3}/series/DT.DOD.DPPG.CD/counterpart-area/all/time/all"
               "?format=json&per_page=30000")
IMF = (API + "/country/all/series/DT.DOD.DIMF.CD/counterpart-area/WLD/time/all"
       "?format=json&per_page=30000&page={page}")
CREDITORS = API + "/counterpart-area?format=json&per_page=1000"

# ------------------------------------------------------------ creditor groups
#
# The IDS names a creditor by country, institution or "bondholders". The groups
# below are the site's, chosen for the geopolitical question ("whose money is
# it?"), and every creditor keeps its own name in the pack, so a reader can
# regroup. A country code stands for all lenders resident there: China (730)
# is its policy banks and its commercial banks together.

INSTITUTIONS = {"019", "237", "877", "878", "887", "888", "890", "892", "893", "895", "896", "897",
                "898", "899"} | {f"{n:03d}" for n in range(802, 820)}   # 801 Australia, 820 NZ are states
MULTIPLE = {"994", "FCW"}
EUROPE = {"001", "002", "003", "004", "005", "006", "007", "008", "009", "010", "011", "012", "018",
          "020", "021", "022", "025", "026", "030", "035", "040", "044", "045", "050", "060", "061",
          "062", "063", "064", "065", "066", "068", "069", "071", "072", "073", "074", "075", "076",
          "077", "082", "083", "084"}
GULF = {"530", "552", "558", "561", "566", "576"}
AFRICAN_STATES = {f"{n:03d}" for n in range(130, 289)} - {"237"}

GROUPS = [
    # id, label; the order is the stacking order on the page and in the box
    ("multi", "Multilateral lenders"),
    ("bonds", "Bondholders"),
    ("china", "China"),
    ("europe", "Europe"),
    ("us", "United States"),
    ("japan", "Japan and Korea"),
    ("gulf", "Gulf states"),
    ("india", "India"),
    ("russia", "Russia"),
    ("turkey", "Turkey"),
    ("africa", "Other African states"),
    ("other", "Other countries"),
    ("multiple", "Multiple lenders"),
]

# Names the IDS spells for a database, not a reader.
CREDITOR_NAME = {
    "901": "World Bank (IBRD)", "905": "World Bank (IDA)", "913": "African Development Bank",
    "919": "European Investment Bank", "976": "Islamic Development Bank", "BND": "Bondholders",
    "994": "Multiple lenders", "FCW": "Other multiple lenders", "005": "Germany",
    "055": "Turkey", "087": "Russia", "078": "USSR", "730": "China", "742": "South Korea",
    "247": "Côte d'Ivoire", "234": "Republic of the Congo", "235": "DR Congo",
    "273": "Somalia", "268": "São Tomé and Príncipe", "240": "The Gambia",
    "540": "Iran", "580": "Yemen", "463": "Venezuela", "740": "North Korea",
    "815": "Afreximbank", "817": "Trade and Development Bank (TDB)", "896": "Africa Finance Corporation",
    "951": "OPEC Fund", "953": "Arab Bank for Economic Development in Africa (BADEA)",
    "921": "Arab Fund for Economic and Social Development", "957": "West African Development Bank (BOAD)",
    "993": "Development Bank of Central African States (BDEAC)", "988": "IFAD",
    "918": "European Development Fund", "975": "European Union", "899": "Asian Infrastructure Investment Bank",
}


def get(url, timeout=180):
    """The World Bank API drops the odd request under load; try three times."""
    for attempt in range(3):
        try:
            return _get(url, timeout=timeout)
        except OSError:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def group_of(code):
    if code == "BND":
        return "bonds"
    if code in MULTIPLE:
        return "multiple"
    if code in INSTITUTIONS or (code.isdigit() and int(code) >= 901):
        return "multi"
    if code == "730":
        return "china"
    if code in EUROPE:
        return "europe"
    if code == "302":
        return "us"
    if code in ("701", "742"):
        return "japan"
    if code in GULF:
        return "gulf"
    if code == "646":
        return "india"
    if code in ("087", "078"):
        return "russia"
    if code == "055":
        return "turkey"
    if code in AFRICAN_STATES:
        return "africa"
    return "other"


def creditor_names():
    d = json.loads(get(CREDITORS, timeout=120))
    out = {}
    for v in d["source"][0]["concept"][0]["variable"]:
        code = v["id"]
        if code == "WLD":
            continue
        out[code] = CREDITOR_NAME.get(code) or " ".join(v["value"].split())
    return out


def by_creditor(iso3):
    """{creditor code: {year: USD}} for one debtor, plus the World total and
    the API's last-updated date."""
    for attempt in range(3):
        body = get(BY_CREDITOR.format(iso3=iso3), timeout=240)
        try:
            d = json.loads(body)
            break
        except ValueError:
            # the API answers an empty body for a debtor outside the Debtor
            # Reporting System (Libya, Namibia, Seychelles, South Sudan) and,
            # now and then, under load; three empty answers mean no data
            if attempt == 2:
                return iso3, {}, {}, None
            time.sleep(3)
    series, world = {}, {}
    for row in (d.get("source") or {}).get("data") or []:
        v = row.get("value")
        if v is None:
            continue
        var = {x["concept"]: x for x in row["variable"]}
        year = int(var["Time"]["value"])
        if year < FIRST_YEAR:
            continue
        code = var["Counterpart-Area"]["id"]
        if code == "WLD":
            world[year] = float(v)
        elif v:
            series.setdefault(code, {})[year] = float(v)
    return iso3, series, world, d.get("lastupdated")


def imf_credit():
    out, page = {}, 1
    while True:
        d = json.loads(get(IMF.format(page=page), timeout=240))
        for row in d["source"]["data"]:
            v = row.get("value")
            var = {x["concept"]: x for x in row["variable"]}
            iso3 = var["Country"]["id"]
            if v is None or iso3 not in AFRICA:
                continue
            year = int(var["Time"]["value"])
            if year >= FIRST_YEAR:
                out.setdefault(AFRICA[iso3], {})[year] = float(v)
        if page >= int(d.get("pages") or 1):
            return out
        page += 1


def main():
    print("World Bank IDS: debt by creditor for 54 African debtors")
    names = creditor_names()
    countries, updated, missing = {}, None, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for iso3, series, world, upd in pool.map(by_creditor, sorted(AFRICA)):
            iso = AFRICA[iso3]
            updated = upd or updated
            if not world:
                missing.append(NAME[iso])
                continue
            # the creditors must add up to the World total, or the split is not usable
            last = max(world)
            parts = sum(s.get(last, 0) for s in series.values())
            if abs(parts - world[last]) > max(1e6, world[last] * 1e-6):
                sys.exit(f"{NAME[iso]}: creditors sum to {parts:,.0f}, World is {world[last]:,.0f} in {last}")
            lon, lat = centre(iso)
            countries[iso] = {
                "name": NAME[iso], "lon": lon, "lat": lat, "total": world,
                "creditors": {c: {str(y): round(v) for y, v in sorted(s.items())} for c, s in series.items()},
            }
            print(f"  {NAME[iso]:<26} {len(series):>3} creditors  {world[last] / 1e9:7.2f} bn ({last})")
    imf = imf_credit()
    for iso, c in countries.items():
        c["imf"] = {str(y): round(v) for y, v in sorted(imf.get(iso, {}).items())}
        c["total"] = {str(y): round(v) for y, v in sorted(c["total"].items())}
    used = {code for c in countries.values() for code in c["creditors"]}
    data_to = max(int(y) for c in countries.values() for y in c["total"])
    pack = {
        "source": "World Bank International Debt Statistics, series DT.DOD.DPPG.CD by counterpart "
                  "and DT.DOD.DIMF.CD; CC BY 4.0",
        "fetched": today(), "updated": updated, "data_to": data_to, "first_year": FIRST_YEAR,
        "groups": [{"id": g, "name": n} for g, n in GROUPS],
        "creditors": {c: {"name": names.get(c, c), "group": group_of(c)} for c in sorted(used)},
        "countries": dict(sorted(countries.items())),
        "missing": sorted(missing),
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, separators=(",", ":")))
    print(f"-> {OUT.relative_to(DATA.parent)}  {OUT.stat().st_size / 1024:.0f} KB  "
          f"{len(countries)} debtors, {len(used)} creditors, to {data_to}; no data: {', '.join(missing) or 'none'}")
    update_meta("debt", fetched=today(), fresh=updated, data_to=data_to,
                records=len(countries), creditors=len(used))


if __name__ == "__main__":
    main()
