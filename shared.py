#!/usr/bin/env python3
"""
Pieces shared by the two page builds and the fetcher.

  data/meta.json     when each layer was fetched, which release, how many records
  payload_meta()     the `meta` block both pages read (build date, SDR note, sources)
  wrap_document()    turns an artifact-style fragment into a full HTML document
                     for GitHub Pages (doctype, head, social tags)
  brand_assets()     inlines the favicon and header mark from brand/ into a page

Named `shared` rather than `site` because `site` is a Python standard-library
module and would shadow it.
"""

import datetime
import html
import json
import os
import pathlib
import re
import shutil
import urllib.parse

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"

# AfDB publishes in SDR. One place, stated on both pages, so the figure is
# auditable rather than an invented conversion.
SDR_USD = 1.37
SDR_NOTE = "1 SDR = 1.37 USD (IMF, Sep 2026)"

# Where the site lives. Canonical and social-preview URLs point here; the pages
# themselves use only relative links, so they also work at any other address.
SITE_URL = os.environ.get("AIW_SITE_URL", "https://jacopoottaviani.com/africa-infra-watch/")
# Personal links carried by both pages (support button, byline). Change here, rebuild.
COFFEE_URL = os.environ.get("AIW_COFFEE_URL", "https://ko-fi.com/jacopoottaviani")
AUTHOR_URL = os.environ.get("AIW_AUTHOR_URL", "https://www.linkedin.com/in/jacopo-ottaviani/")

# What the site is called in search results, link previews and structured data.
SITE_NAME = "Africa Infra Watch"
AUTHOR_NAME = "Jacopo Ottaviani"
# The link-preview image, docs/social.png, drawn by build_social.py.
SOCIAL_IMAGE = "social.png"
SOCIAL_W, SOCIAL_H = 1200, 630

# The repository the site is deployed from, linked from the Methodology tab
# when set (e.g. "https://github.com/<user>/africa-infra-watch"). Optional.
REPO_URL = os.environ.get("AIW_REPO_URL", "").strip()

SOURCE_INFO = {
    "assets": {"name": "Global Energy Monitor", "lic": "CC BY 4.0",
               "url": "https://globalenergymonitor.org/projects/global-integrated-power-tracker/"},
    "finance": {"name": "African Development Bank", "lic": "Open, per publisher",
                "url": "https://iatiregistry.org/publisher/afdb"},
    "ground": {"name": "OpenStreetMap", "lic": "ODbL 1.0",
               "url": "https://www.openstreetmap.org/copyright"},
    "pipelines": {"name": "Global Energy Monitor", "lic": "CC BY 4.0",
                  "url": "https://globalenergymonitor.org/projects/global-gas-infrastructure-tracker/"},
    "cables": {"name": "TeleGeography", "lic": "CC BY-SA 4.0",
               "url": "https://www.submarinecablemap.com/"},
}
# The layers each page draws. The dashboard predates the two line layers and
# still shows three; the map shows all five.
MAP_LAYERS = ("assets", "finance", "ground", "pipelines", "cables")
DASHBOARD_LAYERS = ("assets", "finance", "ground")


# ------------------------------------------------------------------ meta.json

def load_meta():
    p = DATA / "meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_meta(meta):
    DATA.mkdir(exist_ok=True)
    (DATA / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")


def update_meta(layer, **fields):
    meta = load_meta()
    meta.setdefault(layer, {}).update(fields)
    save_meta(meta)
    return meta


def today():
    return datetime.date.today().isoformat()


def fmt_date(iso):
    """2026-09-18 -> 18 Sep 2026; anything unparseable comes back as given."""
    try:
        d = datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or "—"
    return f"{d.day} {d.strftime('%b %Y')}"


def sources(meta, keys=MAP_LAYERS):
    a, f, g = meta.get("assets", {}), meta.get("finance", {}), meta.get("ground", {})
    p, c = meta.get("pipelines", {}), meta.get("cables", {})
    rows = [
        {"k": "assets", **SOURCE_INFO["assets"],
         "detail": f"Global Integrated Power Tracker, release {a.get('release', 'unknown')}",
         "fresh": a.get("fresh") or fmt_date(a.get("fetched"))},
        {"k": "finance", **SOURCE_INFO["finance"],
         "detail": f"IATI 2.03 activity files, {f.get('datasets', '?')} country datasets",
         "fresh": f.get("fresh") or fmt_date(f.get("fetched"))},
        {"k": "ground", **SOURCE_INFO["ground"],
         "detail": "Overpass API, significant road/rail/air classes",
         "fresh": g.get("fresh") or fmt_date(g.get("fetched"))},
        {"k": "pipelines", **SOURCE_INFO["pipelines"],
         "detail": f"Global Gas and Global Oil Infrastructure Trackers, releases {p.get('release', 'unknown')}",
         "fresh": p.get("fresh") or fmt_date(p.get("fetched"))},
        {"k": "cables", **SOURCE_INFO["cables"],
         "detail": "Submarine Cable Map, cables with an African landing point",
         "fresh": c.get("fresh") or fmt_date(c.get("fetched"))},
    ]
    return [r for r in rows if r["k"] in keys]


def payload_meta(meta, keys=MAP_LAYERS):
    return {"built": fmt_date(today()), "sdr_note": SDR_NOTE,
            "sources": sources(meta, keys), "repo": REPO_URL or None,
            # GEM segments that exist in the tracker but carry no route, so the
            # Methodology can say how much of the layer is not drawn
            "unrouted_pipelines": (meta.get("pipelines") or {}).get("unrouted")}


# ------------------------------------------------------------ HTML document

BRAND = ROOT / "brand"

# The mark (brand/option-a-cutout-rose.svg, "option A"): the continent traced from
# data/africa_basemap.json with a compass rose cut out. brand/logos.py generates
# the two derived files used here; edit there, not in the templates.
FAVICON = "data:image/svg+xml," + urllib.parse.quote((BRAND / "favicon.svg").read_text().strip())
LOGO_MARK = re.sub(r"<svg ", '<svg class="mark" aria-hidden="true" focusable="false" ',
                   (BRAND / "mark.svg").read_text().strip(), count=1)


# Monochrome marks of the data sources (brand/sources/*.svg, see the README
# there): every fill is currentColor, so they take the page's ink colour in
# both themes. Inlined as a JS object where a template carries the marker.
SOURCE_LOGOS = {p.stem: p.read_text().strip() for p in sorted((BRAND / "sources").glob("*.svg"))}


def brand_assets(page):
    """Fill the brand markers a template carries: the inline favicon link in
    its head, the header mark next to each <h1>, the mark's home link and,
    where the template asks for them, the data-source logos.
    The home link is the absolute site URL so it also works from an artifact;
    wrap_document makes it relative for the Pages build."""
    for marker in ("<!--__FAVICON__-->", "<!--__LOGO__-->", "__HOME_URL__"):
        if marker not in page:
            raise SystemExit(f"template missing the {marker} marker")
    return (page.replace("<!--__FAVICON__-->", f'<link rel="icon" href="{FAVICON}">')
                .replace("<!--__LOGO__-->", LOGO_MARK)
                .replace("/*__SOURCE_LOGOS__*/{}", json.dumps(SOURCE_LOGOS, ensure_ascii=False))
                .replace("__HOME_URL__", SITE_URL)
                .replace("__COFFEE_URL__", COFFEE_URL)
                .replace("__AUTHOR_URL__", AUTHOR_URL))


def site_url(path=""):
    return SITE_URL.rstrip("/") + "/" + path.lstrip("/")


# ------------------------------------------------------- what the site says

# The same facts feed the <meta description>, the JSON-LD, the <noscript>
# fallback, llms.txt and the sitemap, so search engines, link previews and
# language-model crawlers all read one story, with this snapshot's figures.

KEYWORDS = ["Africa infrastructure", "infrastructure projects Africa", "Africa power plants map",
            "African Development Bank projects", "AfDB finance", "construction Africa map",
            "energy Africa", "Global Energy Monitor", "OpenStreetMap construction",
            "oil and gas pipelines Africa", "submarine cables Africa", "TeleGeography",
            "open data Africa", "infrastructure investment Africa", "interactive map"]

LICENSE_URL = {"CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
               "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
               "ODbL 1.0": "https://opendatacommons.org/licenses/odbl/1-0/"}

LAYER_FILE = {"assets": "gem_power_assets.geojson", "finance": "iati_afdb_finance.geojson",
              "ground": "osm_construction.geojson", "pipelines": "gem_oil_gas_pipelines.geojson",
              "cables": "telegeography_cables.geojson"}


def _rows(layer):
    """A layer is either {"cols": [...], "rows": [[...]]} (map payload) or a
    list of dicts (dashboard ground layer). Return (rows, cols)."""
    if isinstance(layer, dict) and "rows" in layer:
        return layer["rows"], layer.get("cols", [])
    return list(layer), []


def site_facts(assets, finance, ground, pipelines=None, cables=None, meta=None):
    """Counts and totals of the snapshot being built, for the crawlable text.
    A page that does not draw a layer (the dashboard) passes None for it and
    the count comes from meta.json, so the JSON-LD still describes every file
    the site publishes."""
    meta = load_meta() if meta is None else meta
    a, ac = _rows(assets)
    f, fc = _rows(finance)
    g, _ = _rows(ground)
    mw = sum((r[ac.index("mw")] or 0) for r in a) if "mw" in ac else 0
    usd = sum((r[fc.index("usd_m")] or 0) for r in f) if "usd_m" in fc else 0

    def count(layer, key):
        if layer is None:
            return (meta.get(key) or {}).get("records") or 0
        return len(_rows(layer)[0])

    def total(layer, col):
        if layer is None:
            return 0
        rows, cols = _rows(layer)
        return sum((r[cols.index(col)] or 0) for r in rows) if col in cols else 0

    return {"assets": len(a), "finance": len(f), "ground": len(g),
            "pipelines": count(pipelines, "pipelines"), "cables": count(cables, "cables"),
            "pipe_km": total(pipelines, "km"),
            "gw": mw / 1000, "usd_bn": usd / 1000,
            "sources": sources(meta), "built": today(), "meta": meta}


def facts_sentence(facts):
    s = (f"{facts['assets']:,} power units tracked by Global Energy Monitor, "
         f"{facts['finance']:,} projects financed by the African Development Bank, "
         f"{facts['ground']:,} construction works traced in OpenStreetMap")
    if facts.get("pipelines"):
        s += f", {facts['pipelines']:,} oil and gas pipeline segments from Global Energy Monitor"
    if facts.get("cables"):
        s += f" and {facts['cables']:,} submarine cables landing in Africa from TeleGeography"
    return s


def facts_totals(facts):
    parts = []
    if facts["gw"]:
        parts.append(f"about {facts['gw']:,.0f} GW of generating capacity across all statuses")
    if facts["usd_bn"]:
        parts.append(f"USD {facts['usd_bn']:,.1f} billion of AfDB commitments, converted at {SDR_NOTE}")
    return "; ".join(parts)


def structured_data(facts, *, path, title, description, kind):
    """schema.org JSON-LD: the site, this page, the author and the data as a
    Dataset with one part per source, each with its licence and GeoJSON
    download. Google Dataset Search and the AI crawlers both read this."""
    person = {"@type": "Person", "@id": site_url("#author"), "name": AUTHOR_NAME,
              "url": AUTHOR_URL, "sameAs": [AUTHOR_URL, COFFEE_URL]}
    website = {"@type": "WebSite", "@id": site_url("#website"), "name": SITE_NAME,
               "url": SITE_URL, "inLanguage": "en",
               "description": "An interactive map and dashboard of announced, approved and "
                              "ongoing infrastructure in Africa, compiled from open data.",
               "author": {"@id": person["@id"]}, "publisher": {"@id": person["@id"]}}
    place = {"@type": "Place", "name": "Africa",
             "geo": {"@type": "GeoShape", "box": "-35.5 -25.5 37.8 57.9"}}
    parts = []
    for src in facts["sources"]:
        k = src["k"]
        n = facts.get(k) or 0
        what = {"assets": "Power generation units in Africa (announced, pre-construction, "
                          "under construction, operating, cancelled or shelved) with technology, "
                          "capacity in MW, owner and coordinates.",
                "finance": "African Development Bank projects from its IATI 2.03 activity files: "
                           "title, recipient country, status, DAC sector, commitment and "
                           "disbursement, and geocoded locations where published.",
                "ground": "Roads (motorway to secondary), railways and airports under "
                          "construction or proposed in Africa, traced by OpenStreetMap mappers, "
                          "as line geometries with status, operator and opening date.",
                "pipelines": "Oil, NGL and gas transmission pipelines with an African country on "
                             "their route (proposed, under construction, operating, shelved or "
                             "cancelled), as route geometries with fuel, capacity, length, owner "
                             "and start year, from Global Energy Monitor's Global Gas and Global "
                             "Oil Infrastructure Trackers.",
                "cables": "Submarine telecommunications cables with at least one landing point "
                          "in Africa, planned or in service, as route geometries with owners, "
                          "suppliers, ready-for-service year, length and African landing points, "
                          "from TeleGeography's Submarine Cable Map."}[k]
        d = {"@type": "Dataset", "@id": site_url(f"#dataset-{k}"),
             "name": f"{SITE_NAME}: {src['name']} layer",
             "description": f"{what} {n:,} records in this snapshot. {src['detail']}.",
             "url": SITE_URL, "isBasedOn": src["url"],
             "creator": {"@type": "Organization", "name": src["name"], "url": src["url"]},
             "spatialCoverage": place, "isAccessibleForFree": True,
             "dateModified": facts["meta"].get(k, {}).get("fetched") or facts["built"],
             "distribution": [{"@type": "DataDownload", "encodingFormat": "application/geo+json",
                               "contentUrl": site_url("data/" + LAYER_FILE[k])}]}
        if src["lic"] in LICENSE_URL:
            d["license"] = LICENSE_URL[src["lic"]]
        parts.append(d)
    dataset = {"@type": "Dataset", "@id": site_url("#dataset"),
               "name": f"{SITE_NAME}: infrastructure projects across Africa",
               "description": f"Five open datasets on infrastructure in Africa, kept as separate "
                              f"layers because they share no project identifier: {facts_sentence(facts)}. "
                              f"Each source's lifecycle is mapped onto five shared statuses (announced, "
                              f"approved, under construction, operating, stalled).",
               "url": SITE_URL, "keywords": KEYWORDS, "creator": {"@id": person["@id"]},
               "spatialCoverage": place, "isAccessibleForFree": True,
               "dateModified": facts["built"], "hasPart": [{"@id": d["@id"]} for d in parts],
               "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json",
                                 "contentUrl": site_url("data/map.json")},
                                {"@type": "DataDownload", "encodingFormat": "application/json",
                                 "contentUrl": site_url("data/meta.json")}]}
    page = {"@type": ["WebPage", "WebApplication"] if kind == "map" else "WebPage",
            "@id": site_url(path), "url": site_url(path), "name": title,
            "headline": title, "description": description, "inLanguage": "en",
            "isPartOf": {"@id": website["@id"]}, "about": {"@id": dataset["@id"]},
            "mainEntity": {"@id": dataset["@id"]}, "author": {"@id": person["@id"]},
            "dateModified": facts["built"], "keywords": ", ".join(KEYWORDS),
            "primaryImageOfPage": {"@type": "ImageObject", "url": site_url(SOCIAL_IMAGE),
                                   "width": SOCIAL_W, "height": SOCIAL_H}}
    if kind == "map":
        page["applicationCategory"] = "Map"
        page["operatingSystem"] = "Any (web browser)"
        page["offers"] = {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
    graph = [website, person, page, dataset, *parts]
    if path:
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Africa Infrastructure Map", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": title, "item": site_url(path)}]})
    return {"@context": "https://schema.org", "@graph": graph}


def crawl_fallback(facts, *, kind):
    """What a reader without JavaScript, and a crawler that does not run it,
    gets: the page's substance as plain HTML. Real content, nothing hidden
    from people who do run scripts; browsers simply skip <noscript>."""
    e = lambda x: html.escape(str(x), quote=True)
    other = ('<a href="dashboard.html">the dashboard view</a>' if kind == "map"
             else '<a href="index.html">the interactive map</a>')
    rows = "".join(
        f"<tr><td>{e(s['name'])}</td><td>{e(s['detail'])}</td>"
        f"<td>{facts[s['k']]:,}</td><td>{e(s['lic'])}</td><td>{e(s['fresh'])}</td>"
        f"<td><a href=\"data/{LAYER_FILE[s['k']]}\">GeoJSON</a></td></tr>"
        for s in facts["sources"])
    lede = ("This page is an interactive map" if kind == "map" else "This page is a dashboard, with charts and a table,")
    return f"""<noscript>
<article style="max-width:72ch;margin:0 auto;padding:24px 16px;font:16px/1.5 Georgia,serif">
<h2>{e(SITE_NAME)}: announced, approved and ongoing infrastructure in Africa</h2>
<p>{lede} of infrastructure projects across Africa, built from five open datasets:
{e(facts_sentence(facts))}. Together they describe {e(facts_totals(facts))}.
The page needs JavaScript to draw; without it, this summary, the data files below
and {other} are what is here.</p>
<p>The sources share no project identifier, so they are kept as separate layers
and are never added up: an AfDB-financed power plant can legitimately appear in several.
Each source's own lifecycle is mapped onto five shared statuses: announced, approved,
under construction, operating and stalled.</p>
<table>
<caption>The layers in this snapshot</caption>
<thead><tr><th>Source</th><th>Dataset</th><th>Records</th><th>Licence</th><th>Data as of</th><th>Download</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p>Limits: money is AfDB only, so totals are AfDB exposure, not investment in Africa;
about two thirds of AfDB locations sit on a country or region centroid; OpenStreetMap
presence is mapper-driven, so absence is not evidence; energy and connectivity are
over-represented because no comparable open tracker exists for ports, water or
electricity transmission.</p>
<p>The compiled payload is <a href="data/map.json">data/map.json</a>; fetch dates and
release names are in <a href="data/meta.json">data/meta.json</a>. A plain-text summary
for language models is at <a href="llms.txt">llms.txt</a>.
Country outlines: Natural Earth. Built {e(fmt_date(facts["built"]))} by
<a href="{e(AUTHOR_URL)}">{e(AUTHOR_NAME)}</a>.</p>
</article>
</noscript>
"""


def wrap_document(fragment, *, title, description, path="", host="pages", extra_head="",
                  facts=None, kind="map"):
    """Artifact fragments carry their own <meta>/<title>/<link>/<style> at the
    top and page markup after; the publishing sandbox wraps them. GitHub Pages
    serves files as-is, so wrap them here into a complete document, moving the
    stylesheet and fonts into <head> where they belong, and add what search
    engines, link previews and language-model crawlers read: description,
    canonical, Open Graph and Twitter card with the preview image, JSON-LD
    structured data, and a <noscript> summary of the page's substance."""
    frag = re.sub(r'<meta charset="utf-8">\s*', "", fragment)
    frag = re.sub(r'<meta name="viewport"[^>]*>\s*', "", frag)
    frag = re.sub(r"<title>.*?</title>\s*", "", frag, count=1, flags=re.S)
    frag = frag.replace(f'class="home" href="{SITE_URL}"', 'class="home" href="index.html"')
    frag = re.sub(r'<link rel="icon" href="data:[^"]*">',
                  '<link rel="icon" href="favicon.svg" type="image/svg+xml">\n'
                  '<link rel="icon" href="icon-192.png" type="image/png" sizes="192x192">\n'
                  '<link rel="apple-touch-icon" href="apple-touch-icon.png">', frag, count=1)
    cut = frag.index("</style>") + len("</style>")
    head_part, body_part = frag[:cut], frag[cut:]
    q = lambda x: html.escape(x, quote=True)
    t, d = q(title), q(description)
    url = q(site_url(path))
    img = q(site_url(SOCIAL_IMAGE))
    alt = q(f"{title}: Africa with every tracked power unit, AfDB project and construction "
            f"work drawn in its status colour, and the site's title.")
    jsonld = fallback = ""
    if facts is not None:
        sd = structured_data(facts, path=path, title=title, description=description, kind=kind)
        jsonld = ('<script type="application/ld+json">'
                  + json.dumps(sd, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
                  + "</script>\n")
        fallback = crawl_fallback(facts, kind=kind)
    return f"""<!doctype html>
<html lang="en" data-host="{host}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t} · {q(SITE_NAME)}</title>
<meta name="description" content="{d}">
<meta name="keywords" content="{q(", ".join(KEYWORDS))}">
<meta name="author" content="{q(AUTHOR_NAME)}">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">
<meta name="theme-color" content="#1F5F4B">
<link rel="canonical" href="{url}">
<link rel="author" href="{q(AUTHOR_URL)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{q(SITE_NAME)}">
<meta property="og:locale" content="en_GB">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:image" content="{img}">
<meta property="og:image:secure_url" content="{img}">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="{SOCIAL_W}">
<meta property="og:image:height" content="{SOCIAL_H}">
<meta property="og:image:alt" content="{alt}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{img}">
<meta name="twitter:image:alt" content="{alt}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
{head_part.strip()}
{jsonld}{extra_head}</head>
<body>
{fallback}{body_part.strip()}
</body>
</html>
"""


# ------------------------------------------------------ sitemap, llms.txt

def write_site_index(facts):
    """docs/sitemap.xml for search engines and docs/llms.txt (llmstxt.org) for
    language-model crawlers and assistants: what the site is, where the data
    is, how to read it. Both are rebuilt with the pages. robots.txt is not
    written: the site lives under a path, and a robots.txt only counts at the
    domain root, which belongs to the user site."""
    day = facts["built"]
    urls = [("", "weekly", "1.0"), ("dashboard.html", "weekly", "0.9"),
            ("llms.txt", "monthly", "0.3"),
            ("data/meta.json", "monthly", "0.2"), ("data/map.json", "monthly", "0.2")]
    urls += [("data/" + f, "monthly", "0.4") for f in LAYER_FILE.values()]
    body = "".join(
        f"  <url><loc>{html.escape(site_url(p))}</loc><lastmod>{day}</lastmod>"
        f"<changefreq>{c}</changefreq><priority>{pr}</priority></url>\n" for p, c, pr in urls)
    shutil.copy(BRAND / "favicon.svg", DOCS / "favicon.svg")
    (DOCS / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "</urlset>\n")

    src_lines = "\n".join(
        f"- [{s['name']}]({s['url']}): {s['detail']}. {facts[s['k']]:,} records, data as of "
        f"{s['fresh']}, licence {s['lic']}. GeoJSON: {site_url('data/' + LAYER_FILE[s['k']])}"
        for s in facts["sources"])
    (DOCS / "llms.txt").write_text(f"""# {SITE_NAME}

> An interactive map and dashboard of announced, approved and ongoing infrastructure in
> Africa, for investors, researchers and journalists. Compiled from five open datasets:
> {facts_sentence(facts)}. Together they describe {facts_totals(facts)}.
> Snapshot built {fmt_date(day)}; data is refreshed by hand about twice a year.

Made by {AUTHOR_NAME} ({AUTHOR_URL}). Free to use; cite the underlying sources by name.
Site: {SITE_URL}

## Pages

- [Africa Infrastructure Map]({SITE_URL}): full-screen map of the five layers with filters
  by layer, status, country and sector, a viewport summary, a "largest in view" list, detail
  cards linking to each source record, optional marker clustering and Sentinel-2 satellite
  imagery, and a Methodology tab. The view is encoded in the URL hash, so views can be shared.
- [Africa Infrastructure Monitor]({site_url('dashboard.html')}): the power, AfDB and
  OpenStreetMap layers as a page with KPIs, a country map, bar charts by country and
  sector, and a sortable table.

## Data

The compiled payload the map draws, one JSON with column-wise layers:
{site_url('data/map.json')}. Fetch dates, release names and record counts:
{site_url('data/meta.json')}. The raw layers as GeoJSON:

{src_lines}

Country outlines are Natural Earth (1:10m on the map, 1:110m on the dashboard). The
satellite layer is EOX Sentinel-2 cloudless (CC BY-NC-SA), site build only, off by default.

## How to read it

- The sources share no project identifier. They are separate layers, never summed:
  an AfDB-financed power plant can legitimately appear in several.
- Five shared statuses. Announced: GEM announced, IATI status 1, OSM proposed. Approved:
  GEM pre-construction, AfDB projects past board approval. Under construction: GEM
  construction, IATI status 2, OSM construction. Operating: GEM operating, IATI 3-4.
  Stalled: GEM cancelled/shelved/mothballed, IATI 5-6. Pipelines: GEM proposed is
  announced, construction, operating, shelved/cancelled as stalled. Submarine cables:
  TeleGeography "in service" is operating; "planned" is under construction when the
  ready-for-service year is within a year of the snapshot, otherwise announced.
- Shape is source, colour is status, size is scale: circles are power units sized by MW,
  squares are AfDB projects sized by commitment, thin lines are construction ways as
  traced, haloed lines are pipeline routes, lines ending in dots are submarine cables
  with their African landing points. Dashed lines are not yet built.
- AfDB amounts are commitments (IATI transaction type 2) converted from SDR at a fixed,
  stated rate: {SDR_NOTE}.

## Limits

- Money is AfDB only. Chinese, private, domestic-budget and other-lender finance is not
  here. Read totals as AfDB exposure, not as investment in Africa.
- About two thirds of AfDB locations are approximate (a country or region centroid).
  Exact points are used where they exist; the pages say which.
- OpenStreetMap presence is mapper-driven: absence of a road is not evidence that none is
  being built. The layer is filtered to motorway-to-secondary roads, rail and airports.
- Energy and connectivity are over-represented: no comparable open tracker exists for
  ports, water or electricity transmission. Pipeline segments without a published route
  (about a third of GEM's African segments) are not drawn.
- Somaliland and Western Sahara are drawn as Natural Earth draws them, as separate
  polygons; that is the boundary dataset's choice, not a position taken here.

## Optional

- [Global Energy Monitor, Global Integrated Power Tracker](https://globalenergymonitor.org/projects/global-integrated-power-tracker/)
- [African Development Bank on the IATI Registry](https://iatiregistry.org/publisher/afdb)
- [OpenStreetMap copyright and licence](https://www.openstreetmap.org/copyright)
- [Natural Earth](https://www.naturalearthdata.com/)
""")
