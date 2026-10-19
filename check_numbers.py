#!/usr/bin/env python3
"""
After a build: check that every number the site states agrees with the data it
was built from, and with every other place it is stated.

    python3 check_numbers.py          print the failures and a summary
    python3 check_numbers.py -v       print every check
    python3 check_numbers.py <dir>    check another checkout (a `git archive` of HEAD, say)

check_data.py guards the snapshot before the build; this guards what the build
wrote. Most figures on the pages are computed from the payload and cannot
drift, but some are not: the README's counts, the hand-written proportions in
the crawler text and the templates ("about a fifth"), the lender packs that the
profiles, the comparison and the debt page each re-cut, and the artifact builds
beside the site build. The counts here are recomputed from data/ and from the
payloads the pages ship, never taken from shared.site_facts, so a builder bug
shows up as a disagreement rather than being checked against itself.

A failure names the figure, what it says and what the data says. The usual
fix is a hand-written figure in README.md, a fragment in donors/ or sections/,
or a template; rebuild and rerun. When the README's wording changes, a check
reports "pattern not found": update its pattern in section 7 below.

Exit 0 when everything agrees, 1 with the list of disagreements otherwise.
"""

import collections
import json
import pathlib
import re
import sys

VERBOSE = "-v" in sys.argv[1:]
_dirs = [a for a in sys.argv[1:] if not a.startswith("-")]
ROOT = pathlib.Path(_dirs[0]).resolve() if _dirs else pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import shared  # noqa: E402
from fetch_donors import AFRICA  # noqa: E402
from region import REGIONS  # noqa: E402

DATA, DOCS = ROOT / "data", ROOT / "docs"
OKS, FAILS = [], []

WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven "
                                     "twelve thirteen fourteen fifteen".split())}
FRAC = {"half": 1 / 2, "a third": 1 / 3, "two thirds": 2 / 3, "a quarter": 1 / 4,
        "a fifth": 1 / 5, "a sixth": 1 / 6}


def check(label, got, want, ok=None):
    ok = (got == want) if ok is None else ok
    (OKS if ok else FAILS).append(label)
    if ok and not VERBOSE:
        return
    g, w = repr(got), repr(want)
    if len(g) > 160:
        g = g[:157] + "..."
    print(f"{'OK  ' if ok else 'FAIL'} {label}: {g}" + ("" if ok else f"  (expected {w[:400]})"))


def section(title):
    if VERBOSE:
        print(f"\n== {title}")


def num(s):
    return float(s.replace(",", ""))


def inline_payload(path):
    """The `const DATA = {...}` a built page carries inline."""
    s = path.read_text(encoding="utf-8")
    i = s.index("const DATA = ") + len("const DATA = ")
    return json.JSONDecoder().raw_decode(s[i:])[0]


def rows(layer):
    if isinstance(layer, dict) and "rows" in layer:
        return layer["rows"], layer["cols"]
    return list(layer), None


def col(layer, name):
    r, c = rows(layer)
    if c is None:
        return [x.get(name) for x in r]
    i = c.index(name)
    return [x[i] for x in r]


def main():
    meta = json.loads((DATA / "meta.json").read_text())
    feats = {f[:-8]: json.loads((DATA / f).read_text())["features"] for f in shared.LAYER_FILE.values()}
    key_of = {f[:-8]: k for k, f in shared.LAYER_FILE.items()}
    ch, eu, pm = meta["china"], meta["eu"], meta["mattei"]
    debt = json.loads((DATA / "debt.json").read_text())
    packs = {p.stem: json.loads(p.read_text()) for p in sorted((DATA / "donors").glob("*.json"))}
    y_debt = str(debt["data_to"])

    # ------------------------------------------------------------------
    section("1. data/*.geojson against data/meta.json")
    for stem, fs in feats.items():
        k = key_of[stem]
        check(f"{stem}: features == meta.{k}.records", len(fs), meta[k]["records"])
    for stem, k in (("iati_afdb_finance", "finance"), ("iati_worldbank_finance", "finance_wb")):
        check(f"{stem}: distinct iati_id == meta.{k}.activities",
              len({f["properties"].get("iati_id") for f in feats[stem]}), meta[k]["activities"])
    check("china: precise + approximate + country_level == records (unlocated are left out)",
          ch["precise"] + ch["approximate"] + ch["country_level"], ch["records"])
    check("china: footprints == non-point features", ch["footprints"],
          sum(1 for f in feats["aiddata_china_finance"] if f["geometry"]["type"] != "Point"))
    check("eu: contracts + decisions + eib == records", eu["contracts"] + eu["decisions"] + eu["eib"], eu["records"])
    check("eu: placement tiers sum to records",
          eu["named_place"] + eu["country_point"] + eu["regional"] + eu["unplaced"], eu["records"])
    check("mattei: stages sum to records", sum(pm["stages"].values()), pm["records"])
    check("mattei: placement tiers sum to records",
          pm["named_place"] + pm["named_area"] + pm["country_point"] + pm["multi_country"], pm["records"])
    # EUR_USD is applied at fetch time (EU, Mattei) and again at build time
    check("eu and mattei were fetched at shared.EUR_USD", (eu["eur_usd"], pm["eur_usd"]),
          (shared.EUR_USD, shared.EUR_USD))
    check("EUR_NOTE states EUR_USD", str(shared.EUR_USD) in shared.EUR_NOTE, True)
    check("SDR_NOTE states SDR_USD", str(shared.SDR_USD) in shared.SDR_NOTE, True)
    check("debt: meta.debt.records == countries in debt.json", meta["debt"]["records"], len(debt["countries"]))
    check("debt: meta.debt.creditors == creditors used",
          meta["debt"]["creditors"], len({c for v in debt["countries"].values() for c in v["creditors"]}))
    check("debt: meta.debt.data_to == debt.json", meta["debt"]["data_to"], debt["data_to"])
    check("debt: reporters + missing == every African country", len(debt["countries"]) + len(debt["missing"]), len(AFRICA))

    # ------------------------------------------------------------------
    section("2. lender packs against meta, the layers and the debt pack")
    mkey = {s: s + "_profile" for s in ("china", "eu", "usa", "germany", "france", "spain", "japan", "gulf", "nordics")}
    for slug, pk in packs.items():
        m = meta.get(mkey.get(slug, slug)) or {}
        check(f"{slug}: pack fetched == meta", pk["fetched"], m.get("fetched"))
        for part in ("gem", "pipelines", "cables", "works", "nuclear", "mattei"):
            if part in pk and part in m:
                check(f"{slug}: len(pack.{part}) == meta.{part}", len(pk[part]), m[part])
        if "crs" in pk and "crs_activities" in m:
            check(f"{slug}: pack.crs.n == meta.crs_activities", int(pk["crs"]["n"]), m["crs_activities"])
        if "ids" in pk and "ids_updated" in m:
            check(f"{slug}: IDS release == meta", pk["ids"]["updated"], m["ids_updated"])
            check(f"{slug}: IDS release == debt.json's", pk["ids"]["updated"], debt["updated"])
        # a profile's debt is the debt page's figure: DPPG by counterpart, the
        # same codes, the same year; the bilateral part sits beside it
        for key in ("ids", "ids_eu", "ids_funds"):
            blk = pk.get(key)
            if not blk:
                continue
            codes = list(blk["counterparts"])
            want = sum(c["creditors"].get(k, {}).get(y_debt, 0) for c in debt["countries"].values() for k in codes)
            got = blk["continent"].get(y_debt, 0)
            check(f"{slug}.{key} ({blk.get('series')}, {','.join(codes)}) {y_debt}, USD m == debt.json",
                  round(got / 1e6), round(want / 1e6), ok=blk.get("series") == "DPPG" and abs(got - want) < 1e6)
        if pk.get("ids_bilateral"):
            check(f"{slug}.ids_bilateral is BLAT", pk["ids_bilateral"].get("series"), "BLAT")
    check("china_profile.projects == china layer", meta["china_profile"]["projects"], ch["records"])
    check("italy.mattei == mattei layer", meta["italy"]["mattei"], pm["records"])
    if packs["italy"].get("aics"):
        ai = packs["italy"]["aics"]
        check("italy.aics == pack aics.n", meta["italy"].get("aics"), ai["n"])
        check("italy aics.n == activities listed", ai["n"], len(ai["activities"]))
    check("eu_profile.layer_records == eu layer", meta["eu_profile"]["layer_records"], eu["records"])
    check("china pack aid.n == china layer", packs["china"]["aid"].get("n"), ch["records"])
    check("eu pack layer.n == eu layer", packs["eu"]["layer"].get("n"), eu["records"])

    cmp_path = DOCS / "data" / "compare.json"
    if cmp_path.exists():
        cmp = json.loads(cmp_path.read_text())
        for lender in cmp["lenders"]:
            sl = lender["slug"]
            check(f"compare {sl}: fetched == pack", lender["fetched"], packs[sl]["fetched"])
            a = cmp["aid"].get(sl)
            if a:
                want_n = int(packs[sl]["crs"]["n"]) if packs[sl].get("crs") else packs[sl]["aid"]["n"]
                check(f"compare {sl}: aid n == pack", int(a["n"]), want_n)
            tot = sum(v[-1] for v in (cmp["debt"].get(sl) or {}).values())
            prof = packs[sl]["ids"]["continent"].get(y_debt, 0) + \
                (packs[sl].get("ids_eu") or {}).get("continent", {}).get(y_debt, 0)
            check(f"compare {sl}: debt {y_debt} == the profile's (USD m)", round(tot), round(prof / 1e6),
                  ok=abs(tot - prof / 1e6) < 2)

    # ------------------------------------------------------------------
    section("3. the map payload (docs/data/map.json) against meta")
    mp = json.loads((DOCS / "data" / "map.json").read_text())
    ln = collections.Counter(col(mp["finance"], "ln"))
    check("map: AfDB rows == meta.finance.activities", ln["AfDB"], meta["finance"]["activities"])
    check("map: World Bank rows == meta.finance_wb.activities", ln["WB"], meta["finance_wb"]["activities"])
    for k in ("assets", "pipelines", "cables", "china", "eu", "mattei"):
        check(f"map: {k} rows == meta.{k}.records", len(rows(mp[k])[0]), meta[k]["records"])
    check("map: source cards == shared.sources(meta)", mp["meta"]["sources"], shared.sources(meta))
    check("map: SDR and EUR notes == shared", (mp["meta"]["sdr_note"], mp["meta"]["eur_note"]),
          (shared.SDR_NOTE, shared.EUR_NOTE))
    for part, src in (("eu_meta", eu), ("mattei_meta", pm), ("china_left_out", ch)):
        check(f"map: {part} == meta", mp["meta"][part], {k: src.get(k) for k in mp["meta"][part]})

    counts = {"assets": len(rows(mp["assets"])[0]), "finance": ln["AfDB"], "finance_wb": ln["WB"],
              "ground": len(rows(mp["ground"])[0])}
    for k in ("pipelines", "cables", "china", "eu", "mattei"):
        counts[k] = len(rows(mp[k])[0])

    # ------------------------------------------------------------------
    section("4. every other build ships the same records")
    builds = {"docs/dashboard.html": DOCS / "dashboard.html",
              "map.html (artifact)": ROOT / "map.html", "dashboard.html (artifact)": ROOT / "dashboard.html"}
    dash = None
    for label, path in builds.items():
        if not path.exists():      # the artifact builds are not committed
            print(f"  (skipped {label}: not built)")
            continue
        p = inline_payload(path)
        if label == "docs/dashboard.html":
            dash = p
        lnx = collections.Counter(col(p["finance"], "ln"))
        got = {"assets": len(rows(p["assets"])[0]), "finance": lnx["AfDB"], "finance_wb": lnx["WB"],
               "ground": len(rows(p["ground"])[0])}
        for k in ("pipelines", "cables", "china", "eu", "mattei"):
            got[k] = len(rows(p[k])[0]) if k in p else None
        check(f"{label}: layer counts == map payload", got, counts)
        srcs = (p.get("meta") or {}).get("sources")
        if srcs is not None:
            check(f"{label}: source cards == map payload", srcs, mp["meta"]["sources"])
    if dash and "debt" in dash:
        d = dash["debt"]
        check("dashboard debt box: countries == debt.json", len(d.get("countries") or d.get("c") or {}),
              len(debt["countries"]))

    # ------------------------------------------------------------------
    section("5. crawler text (description, noscript, JSON-LD, llms.txt) states the payload's counts")
    lns = col(mp["finance"], "ln")
    usd = col(mp["finance"], "usd_m")
    total = lambda layer, c: sum((x or 0) for x in col(mp[layer], c))
    patterns = [
        (r"(\d[\d,]*) power units tracked", counts["assets"]),
        (r"(\d[\d,]*) projects financed by the African Development Bank", counts["finance"]),
        (r"and (\d[\d,]*) by the World Bank", counts["finance_wb"]),
        (r"(\d[\d,]*) construction works traced", counts["ground"]),
        (r"(\d[\d,]*) oil and gas pipeline segments", counts["pipelines"]),
        (r"(\d[\d,]*) submarine cables landing", counts["cables"]),
        (r"(\d[\d,]*) infrastructure projects financed by Chinese", counts["china"]),
        (r"(\d[\d,]*) infrastructure projects financed by the European Union", counts["eu"]),
        (r"the (\d[\d,]*) projects of Italy", counts["mattei"]),
        (r"about (\d[\d,]*) GW of generating", round(total("assets", "mw") / 1000)),
        (r"USD (\d[\d,.]*) billion of AfDB commitments",
         round(sum((u or 0) for u, l in zip(usd, lns) if l == "AfDB") / 1000, 1)),
        (r"USD (\d[\d,.]*) billion of World Bank", round(sum((u or 0) for u, l in zip(usd, lns) if l == "WB") / 1000, 1)),
        (r"USD (\d[\d,.]*) billion of Chinese official", round(total("china", "usd_m") / 1000, 1)),
        (r"USD (\d[\d,.]*) billion of European Union", round(total("eu", "usd_m") / 1000, 1)),
        (r"EUR (\d[\d,.]*) billion of stated Piano Mattei", round(total("mattei", "eur_m") / 1000, 2)),
        (r"(1 SDR = [\d.]+ USD \([^)]*\))", shared.SDR_NOTE),
        (r"(1 EUR = [\d.]+ USD \([^)]*\))", shared.EUR_NOTE),
    ]
    texts = {"docs/index.html": DOCS / "index.html", "docs/dashboard.html": DOCS / "dashboard.html",
             "docs/llms.txt": DOCS / "llms.txt", "map.html": ROOT / "map.html", "dashboard.html": ROOT / "dashboard.html"}
    for label, path in texts.items():
        if not path.exists():
            continue
        s = re.sub(r"const DATA = .*", "", path.read_text(encoding="utf-8"))   # the payload is not prose
        for pat, want in patterns:
            found = re.findall(pat, s)
            if found:
                vals = sorted({(f if isinstance(want, str) else num(f)) for f in found}, key=str)
                check(f"{label}: '{pat[:40]}' ×{len(found)}", vals, [want])

    # ------------------------------------------------------------------
    section("6. profiles, debt and compare pages")
    for slug in packs:
        s = (DOCS / slug / "index.html").read_text(encoding="utf-8")
        check(f"docs/{slug}/: no unfilled tokens", sorted(set(re.findall(r"__[A-Z][A-Z0-9_]+__", s))), [])
        check(f"docs/data/donors/{slug}.json == data/donors/{slug}.json",
              (DOCS / "data" / "donors" / f"{slug}.json").read_bytes() == (DATA / "donors" / f"{slug}.json").read_bytes(), True)
    for page in ("debt", "compare"):
        s = (DOCS / page / "index.html").read_text(encoding="utf-8")
        check(f"docs/{page}/: no unfilled tokens", sorted(set(re.findall(r"__[A-Z][A-Z0-9_]+__", s))), [])
    check("docs/data/debt.json == data/debt.json",
          (DOCS / "data" / "debt.json").read_bytes() == (DATA / "debt.json").read_bytes(), True)
    check("docs/data/meta.json == data/meta.json", json.loads((DOCS / "data" / "meta.json").read_text()) == meta, True)
    for stem in feats:
        if key_of[stem] in shared.NO_DOWNLOAD:     # drawn, not offered as a file
            check(f"docs/data/{stem}.geojson is not published", (DOCS / "data" / f"{stem}.geojson").exists(), False)
            continue
        check(f"docs/data/{stem}.geojson ships data/'s features",
              len(json.loads((DOCS / "data" / f"{stem}.geojson").read_text())["features"]), len(feats[stem]))
    cont = sum(c["total"].get(y_debt, 0) for c in debt["countries"].values())
    m = re.search(r"USD (\d[\d,.]*) bn abroad at the end of (\d{4})", (DOCS / "debt" / "index.html").read_text(encoding="utf-8"))
    check("debt page headline == continent total", [num(m.group(1)), int(m.group(2))] if m else None,
          [round(cont / 1e9), debt["data_to"]])

    # ------------------------------------------------------------------
    section("7. README figures")
    rd = (ROOT / "README.md").read_text(encoding="utf-8")

    def claim(label, pat, want, conv=num, rel=0.0):
        """`rel` > 0 for a rounded figure ("about 1,400"): it passes within
        that relative distance of the data."""
        m = re.search(pat, rd, re.S)
        if not m:
            check(f"README {label}", "pattern not found", want, ok=False)
            return
        got = [conv(g) for g in m.groups()] if len(m.groups()) > 1 else conv(m.group(1))
        if rel:
            g, w = (got, want) if isinstance(want, list) else ([got], [want])
            check(f"README {label}", got, want, ok=all(abs(a - b) <= rel * abs(b) for a, b in zip(g, w)))
        else:
            check(f"README {label}", got, want)

    claim("table: power units", r"Tracker \| (\d[\d,]*) power units", counts["assets"])
    claim("table: AfDB projects", r"African Development Bank, IATI 2\.03 activity files \| (\d[\d,]*) projects", counts["finance"])
    claim("table: World Bank files + projects", r"\((\d+) African country files \+ (\d+) regional\) \| (\d[\d,]*) projects",
          [meta["finance_wb"]["datasets"] - 2, 2, counts["finance_wb"]])
    claim("table: OSM works", r"Overpass \| (\d[\d,]*) works", counts["ground"])
    claim("table: pipeline segments", r"\| (\d[\d,]*) routed segments", counts["pipelines"])
    claim("table: cables", r"\| (\d[\d,]*) cables \|", counts["cables"])
    claim("table: AidData projects", r"Geospatial GCDF 3\.0 \| (\d[\d,]*) projects", counts["china"])
    claim("table: EU files + records", r"\((\d+) African country and regional files\).*?\| (\d[\d,]*) records \|",
          [meta["eu"]["datasets"] - 1, counts["eu"]])
    claim("table: Mattei pages + projects", r"(\d+) project pages in Italian and English \| (\d+) projects",
          [counts["mattei"], counts["mattei"]])
    edu = sum(1 for d in col(mp["mattei"], "dirs") if d and "educat" in d.lower())
    claim("Mattei: N of the M projects carry education", r"(\d+) of the\s+(\d+) projects\s+carry the education",
          [edu, counts["mattei"]])
    claim("Mattei: partner countries", r"the plan's (\d+) partner", pm["partner_countries"])
    claim("Mattei: 'The N partner countries'", r"The (\d+) partner countries are", pm["partner_countries"])
    claim("AidData: umbrella", r"Left out: (\d[\d,]*) umbrella", ch["umbrella"])
    claim("AidData: pledges", r"(\d[\d,]*) pledges \(MoUs", ch["pledges"])
    claim("AidData: not infrastructure", r"(\d[\d,]*) records that\s+are not physical", ch["not_infrastructure"])
    claim("AidData: footprints", r"precise \(on the OSM feature; (\d[\d,]*) of these", ch["footprints"])
    claim("Russia: GEM records", r"the (\w+) Global Energy\s+Monitor records with a Russian", meta["russia"]["gem"],
          conv=lambda w: WORDS.get(w, w))
    claim("Russia: Rosatom agreements", r"the\s+(\d+)\s+Rosatom agreements", meta["russia"]["nuclear"])
    claim("Turkey: placed works", r"(\d+) placed works", meta["turkey"]["works"])
    claim("Turkey: Turkish-owned units", r"the (\d+) Turkish-owned", meta["turkey"]["gem"])
    it = packs["italy"]
    years = int(it["crs"]["to"]) - int(it["crs"]["from"]) + 1
    claim("Italy: activities a year (about)", r"about (\d[\d,]*) African activities a year",
          int(it["crs"]["n"]) / years, rel=0.05)
    claim("Italy: distinct titles (about)", r"(\d[\d,]*) distinct\s+titles", int(it["crs"]["titles"]), rel=0.05)
    fy = it["fdi"]["to"]
    fdi_af = sum((v.get(str(fy)) or 0) for v in it["fdi"]["countries"].values()) / 1000
    claim(f"Italy: FDI stock, USD bn, end-{fy}", r"USD ([\d.]+) bn in\s+Africa at end-(\d{4})", [round(fdi_af, 1), int(fy)])
    claim("Italy: IDS debtors", r"\((\d+) debtors\)", len(it["ids"]["countries"]))
    cn = packs["china"]
    ao_b = next(c for c in cn["ids_bilateral"]["countries"] if c["iso"] == "AO")
    ao_a = next(c for c in cn["ids"]["countries"] if c["iso"] == "AO")
    claim("China: Angola bilateral vs all", r"Angola:\s+USD ([\d.]+) bn bilateral,\s+USD ([\d.]+) bn all Chinese\s+creditors at end-(\d{4})",
          [round(ao_b["latest_stock"] / 1e9, 1), round(ao_a["latest_stock"] / 1e9, 1), ao_a["latest_year"]])
    us = packs["usa"]
    claim(f"USA: African activities in {us['crs']['to']} (about)", r"(\d[\d,]*) African activities in (\d{4})",
          [us["crs"]["years"][str(us["crs"]["to"])]["n"], int(us["crs"]["to"])], rel=0.05)
    claim("EU pass: Commission files", r"The eu pass reads (\d+) Commission files", meta["eu"]["datasets"] - 1)
    claim("Mattei pass: project pages (EN + IT)", r"page and (\d+) project pages", 2 * counts["mattei"])
    claim("AfDB: XML files", r"catalogue plus (\d+) XML files", meta["finance"]["datasets"])
    claim("AfDB: multinational activities", r"empty recipient country; (\d+) activities",
          sum(1 for i, l in zip(col(mp["finance"], "iso"), lns) if l == "AfDB" and not i))
    claim("Debt: non-reporters", r"\. ([A-Z][a-z]+), ([A-Z][a-z]+), ([A-Z][a-z]+) and\s+(South Sudan) do not report",
          sorted(debt["missing"]), conv=str)
    claim("profiles: how many", r"\((\w+) so far: Russia", len(shared.DONORS), conv=lambda w: WORDS.get(w, w))
    claim("profiles: the docs/ list", r"one folder per lender profile \(([^)]*)\)",
          ", ".join(f"`{d['slug']}/`" for d in shared.DONORS), conv=str)
    mb = lambda p: round(p.stat().st_size / 1e6, 1)
    if (ROOT / "map.html").exists() and (ROOT / "dashboard.html").exists():
        claim("artifact sizes, MB (map, dashboard)", r"inside the page \((\d+\.\d) MB and\s+(\d+\.\d) MB",
              [mb(ROOT / "map.html"), mb(ROOT / "dashboard.html")], rel=0.15)
    # the other editions' folders (docs/se-asia/) are snapshots of their own
    editions = {DOCS / r.slug for r in REGIONS.values() if r.slug}
    claim("docs/ size per snapshot, MB", r"About (\d+) MB per\s+snapshot",
          round(sum(f.stat().st_size for f in DOCS.rglob("*")
                    if f.is_file() and not any(e in f.parents for e in editions)) / 1e6), rel=0.15)

    # ------------------------------------------------------------------
    section("8. hand-written proportions in the prose")

    def share(label, text, pat, actual):
        m = re.search(pat, text, re.S)
        if not m:
            check(label, "pattern not found", actual, ok=False)
            return
        word = m.group(1).lower()
        check(f"{label}: '{word}' (the data: {actual:.0%})", word, min(FRAC, key=lambda w: abs(FRAC[w] - actual)))

    noscript = (DOCS / "index.html").read_text(encoding="utf-8")
    llms = (DOCS / "llms.txt").read_text(encoding="utf-8")
    dtpl = (ROOT / "dashboard.template.html").read_text(encoding="utf-8")
    # the region markers (<!--__IF:africa__-->…<!--__ENDIF__-->) carry other
    # editions' wording; resolve them for Africa, as the build does
    mtpl = shared.regionalize((ROOT / "map.template.html").read_text(encoding="utf-8"))
    china_cty = ch["country_level"] / ch["records"]
    unrouted = meta["pipelines"]["unrouted"] / (meta["pipelines"]["records"] + meta["pipelines"]["unrouted"])
    # the crawler text states these two as computed percentages, of markers
    # (one per activity, as the map draws them), not of location points; the
    # dashboard fills its own from the payload at run time
    fl = mp["finance"]
    afdb_marks = [pr for pr, l in zip(col(fl, "prec"), col(fl, "ln")) if l == "AfDB"]
    afdb_marker_approx = sum(1 for pr in afdb_marks if (pr or 0) > 0) / len(afdb_marks)

    def pct(label, text, pat, actual):
        m = re.search(pat, text, re.S)
        if not m:
            check(label, "pattern not found", actual, ok=False)
            return
        check(f"{label}: {m.group(1)}% (the data: {actual:.1%})", int(m.group(1)), round(100 * actual))
    pct("noscript: Chinese projects at a country point", noscript, r"about (\d+)% of the Chinese-financed", china_cty)
    pct("llms.txt: Chinese projects at a country point", llms, r"about (\d+)% have no published location", china_cty)
    pct("noscript: AfDB markers approximate", noscript, r"about (\d+)%\s+of AfDB locations", afdb_marker_approx)
    pct("llms.txt: AfDB markers approximate", llms, r"About (\d+)% of AfDB locations", afdb_marker_approx)
    share("llms.txt: pipeline segments without a route", llms, r"\(about (a \w+) of GEM's African segments\)", unrouted)
    share("map: pipeline segments without a route", mtpl, r"About (a \w+) of GEM's African segments carry no route", unrouted)
    share("map: Mattei multi-country", mtpl, r"(A third) are programmes across several countries",
          pm["multi_country"] / pm["records"])
    share("map: Mattei at a country point", mtpl, r"drawn at one point; (a third) sit at a country's point",
          pm["country_point"] / pm["records"])
    if packs["usa"].get("ids_bilateral"):
        share("README: US bilateral share of US creditors", rd, r"for the\s+United States it is (a \w+) of the whole",
              packs["usa"]["ids_bilateral"]["continent"][y_debt] / packs["usa"]["ids"]["continent"][y_debt])

    print(f"\n{len(OKS)} numbers agree, {len(FAILS)} disagree" + ("" if VERBOSE else "  (-v lists every check)"))
    if FAILS:
        sys.exit(1)


if __name__ == "__main__":
    main()
