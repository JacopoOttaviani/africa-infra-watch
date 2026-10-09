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
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"

# Leaflet + Leaflet.markercluster power the "Cluster markers" view on both
# pages. They are inlined like the payload: the artifact sandbox blocks runtime
# requests, and the site build should not depend on a CDN either.
VENDOR = ROOT / "vendor"
VENDOR_JS = ["leaflet-1.9.4.min.js", "leaflet.markercluster-1.5.3.min.js"]
VENDOR_MARKER = "/*__VENDOR__*/"


def vendor_js():
    parts = []
    for name in VENDOR_JS:
        path = VENDOR / name
        if not path.exists():
            sys.exit(f"missing {path} — see vendor/README.md")
        parts.append(path.read_text())
    return "\n".join(parts)


def inline_vendor(page):
    """Replace the template's vendor marker with the bundled libraries."""
    if VENDOR_MARKER not in page:
        sys.exit("template missing the vendor marker")
    return page.replace(VENDOR_MARKER, vendor_js(), 1)

# AfDB publishes in SDR. One place, stated on both pages, so the figure is
# auditable rather than an invented conversion.
SDR_USD = 1.37
SDR_NOTE = "1 SDR = 1.37 USD (IMF, Sep 2026)"
# The EU institutions publish in euros; one fixed, stated rate, like the SDR one.
EUR_USD = 1.1225
EUR_NOTE = "1 EUR = 1.1225 USD (ECB reference rate, 2 Oct 2026)"

# Where the site lives. Canonical and social-preview URLs point here; the pages
# themselves use only relative links, so they also work at any other address.
SITE_URL = os.environ.get("AIW_SITE_URL", "https://jacopoottaviani.com/africa-infra-watch/")
# Personal links carried by both pages (support button, credit line). Change here, rebuild.
COFFEE_URL = os.environ.get("AIW_COFFEE_URL", "https://ko-fi.com/jacopoottaviani")
AUTHOR_URL = os.environ.get("AIW_AUTHOR_URL", "https://www.linkedin.com/in/jacopo-ottaviani/")
WEB_URL = os.environ.get("AIW_WEB_URL", "https://jacopoottaviani.com/")

# What the site is called in search results, link previews and structured data.
SITE_NAME = "Africa Infra Watch"
AUTHOR_NAME = "Jacopo Ottaviani"
# The link-preview image, docs/social.png, drawn by build_social.py.
SOCIAL_IMAGE = "social.png"
SOCIAL_W, SOCIAL_H = 1200, 630


def social_image_url():
    """The preview image's absolute URL, versioned with a digest of the file.

    WhatsApp, Facebook, LinkedIn and Slack cache an og:image by its URL, some
    for weeks, so a redrawn social.png at the same address keeps showing the
    old card. A content digest in the query string gives every new drawing a
    new address; the file itself stays docs/social.png.
    """
    import hashlib
    path = DOCS / SOCIAL_IMAGE
    if not path.exists():
        return site_url(SOCIAL_IMAGE)
    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    return site_url(SOCIAL_IMAGE) + "?v=" + digest

# The repository the site is deployed from, linked from the Methodology tab
# when set (e.g. "https://github.com/<user>/africa-infra-watch"). Optional.
REPO_URL = os.environ.get("AIW_REPO_URL", "").strip()

SOURCE_INFO = {
    "assets": {"name": "Global Energy Monitor", "lic": "CC BY 4.0",
               "url": "https://globalenergymonitor.org/projects/global-integrated-power-tracker/"},
    "finance": {"name": "African Development Bank", "lic": "Open, per publisher",
                "url": "https://iatiregistry.org/publisher/afdb"},
    "finance_wb": {"name": "World Bank", "lic": "CC BY 4.0",
                   "url": "https://iatiregistry.org/publisher/worldbank"},
    "ground": {"name": "OpenStreetMap", "lic": "ODbL 1.0",
               "url": "https://www.openstreetmap.org/copyright"},
    "pipelines": {"name": "Global Energy Monitor", "lic": "CC BY 4.0",
                  "url": "https://globalenergymonitor.org/projects/global-gas-infrastructure-tracker/"},
    "cables": {"name": "TeleGeography", "lic": "CC BY-SA 4.0",
               "url": "https://www.submarinecablemap.com/"},
    # the project records are AidData's (ODC-By); the footprints are traced in
    # OpenStreetMap and stay under OSM's ODbL
    "china": {"name": "AidData", "lic": "ODC-By 1.0 (footprints ODbL)",
              "url": "https://www.aiddata.org/data/aiddatas-global-chinese-development-finance-dataset-version-3-0"},
    # the Commission's IATI files fall under the EU's open-data decision
    # (CC BY 4.0); the EIB's are under the Bank's own terms, attribution required
    "eu": {"name": "European Union", "lic": "CC BY 4.0 (Commission), attribution (EIB)",
           "url": "https://iatiregistry.org/publisher/ec-intpa"},
    # the Italian Government's portal content is CC BY 3.0 IT (governo.it, Note
    # legali); the gazetteer coordinates behind the named places are OpenStreetMap's
    "mattei": {"name": "Italian Government", "lic": "CC BY 3.0 IT (gazetteer ODbL)",
               "url": "https://www.governo.it/en/piano-mattei/progetti/"},
}
# The layers each page draws. Both pages show the same eight layers over the
# same records, and both split the finance layer between its two lenders, so
# both carry the World Bank source card.
MAP_LAYERS = ("assets", "finance", "finance_wb", "ground", "pipelines", "cables", "china", "eu", "mattei")
DASHBOARD_LAYERS = MAP_LAYERS

# Lender profiles: one page per lending country or bloc, served at
# docs/<slug>/ and built by build_donors.py from donor.template.html (the
# frame every profile shares), donors/<slug>.html (that profile's prose) and
# data/donors/<slug>.json (its data pack, from fetch_donors.py). Every page
# links them from the row of buttons above the Methodology button. Adding a
# profile is one entry here, one fetch function, one fragment.
DONORS = [
    {"slug": "russia", "name": "Russia", "badge": "RU",
     "title": "Russia in Africa's infrastructure",
     "description": "What the open data holds on Russian money in African infrastructure: "
                    "sovereign debt owed to the Russian Federation by every African government "
                    "(World Bank International Debt Statistics), the energy assets with a Russian "
                    "vendor or shareholder (Global Energy Monitor), Rosatom's nuclear agreements "
                    "and the Bank of Russia's investment stocks, country by country."},
    {"slug": "turkey", "name": "Turkey", "badge": "TR",
     "title": "Turkey in Africa's infrastructure",
     "description": "What the open data holds on Turkish money in Africa: Turkey's aid activities "
                    "country by country from the OECD's Creditor Reporting System, net ODA by recipient, "
                    "Turkish direct-investment stock by African country, sovereign debt owed to Turkey "
                    "(World Bank International Debt Statistics), the power units with a Turkish owner in "
                    "Global Energy Monitor's tracker, and the works that Türk Eximbank, Summa, Yapı Merkezi "
                    "and Karpowership place on the map themselves."},
    {"slug": "italy", "name": "Italy", "badge": "IT",
     "title": "Italy in Africa's infrastructure",
     "description": "What the open data holds on Italian money in Africa: the Italian Government's "
                    "Piano Mattei project list, Italy's aid activities country by country from the "
                    "OECD's Creditor Reporting System, net ODA by recipient, Italian direct-investment "
                    "stock by African country, sovereign debt owed to Italy (World Bank International "
                    "Debt Statistics), and the power plants, pipelines and submarine cables with Eni, "
                    "Enel, Snam or Sparkle among their owners in the map's own layers."},
    {"slug": "china", "name": "China", "badge": "CN",
     "title": "China in Africa's infrastructure",
     "description": "What the open data holds on Chinese money in African infrastructure: AidData's "
                    "project-level record of Chinese official commitments 2000–2021 country by country, "
                    "lender by lender and sector by sector, what each African government owes Chinese "
                    "creditors (World Bank International Debt Statistics), and the power plants, pipelines "
                    "and submarine cables with a Chinese owner in the map's own layers."},
    {"slug": "eu", "name": "European Union", "badge": "EU",
     "title": "The European Union in Africa's infrastructure",
     "description": "What the open data holds on EU money in African infrastructure: the European "
                    "Commission's and the European Investment Bank's own records from IATI as the map draws "
                    "them, the EU institutions' aid activities country by country from the OECD's Creditor "
                    "Reporting System, net ODA by recipient, and what each African government owes the EIB "
                    "and the EU budget (World Bank International Debt Statistics)."},
    {"slug": "usa", "name": "United States", "badge": "US",
     "title": "The United States in Africa's infrastructure",
     "description": "What the open data holds on US money in Africa: the United States' aid activities "
                    "country by country from the OECD's Creditor Reporting System, net ODA by recipient, US "
                    "direct-investment stock by African country, sovereign debt owed to the United States "
                    "(World Bank International Debt Statistics), and the pipelines, power units and cables "
                    "with a US owner in the map's own layers."},
    {"slug": "germany", "name": "Germany", "badge": "DE",
     "title": "Germany in Africa's infrastructure",
     "description": "What the open data holds on German money in Africa: Germany's aid activities country by "
                    "country from the OECD's Creditor Reporting System, net ODA by recipient, German "
                    "direct-investment stock by African country, sovereign debt owed to Germany (World Bank "
                    "International Debt Statistics), and the power units with a German owner in the map's own layers."},
    {"slug": "france", "name": "France", "badge": "FR",
     "title": "France in Africa's infrastructure",
     "description": "What the open data holds on French money in Africa: France's aid activities country by country "
                    "from the OECD's Creditor Reporting System, net ODA by recipient, French direct-investment stock by "
                    "African country, sovereign debt owed to France (World Bank International Debt Statistics), and the "
                    "power plants, pipelines and cables with TotalEnergies, EDF, Engie or Orange among their owners."},
    {"slug": "spain", "name": "Spain", "badge": "ES",
     "title": "Spain in Africa's infrastructure",
     "description": "What the open data holds on Spanish money in Africa: Spain's aid activities country by country "
                    "from the OECD's Creditor Reporting System, net ODA by recipient, Spanish direct-investment stock by "
                    "African country, sovereign debt owed to Spain (World Bank International Debt Statistics), and the "
                    "power plants and pipelines with Acciona, Naturgy or Repsol among their owners."},
    {"slug": "japan", "name": "Japan", "badge": "JP",
     "title": "Japan in Africa's infrastructure",
     "description": "What the open data holds on Japanese money in Africa: Japan's aid activities country by country "
                    "from the OECD's Creditor Reporting System, JICA's loans among them, net ODA by recipient, Japanese "
                    "direct-investment stock, sovereign debt owed to Japan (World Bank International Debt Statistics), and "
                    "the power plants with a Japanese owner in the map's own layers."},
    {"slug": "nordics", "name": "Nordic countries", "badge": "NORD",
     "title": "The Nordic countries in Africa's infrastructure",
     "description": "What the open data holds on Nordic money in Africa, Denmark, Finland, Iceland, Norway and Sweden "
                    "together: their aid activities country by country from the OECD's Creditor Reporting System, net ODA "
                    "by recipient, direct-investment stock, sovereign debt owed to the five (World Bank International Debt "
                    "Statistics), and the power plants with Scatec, Norfund or Equinor among their owners."},
    {"slug": "gulf", "name": "Gulf states", "badge": "GCC",
     "title": "The Gulf states in Africa's infrastructure",
     "description": "What the open data holds on Gulf money in Africa, the United Arab Emirates, Saudi Arabia, Kuwait and "
                    "Qatar together: their aid activities country by country from the OECD's Creditor Reporting System, net "
                    "ODA by recipient, sovereign debt owed to the four states and to the Gulf-based development funds (World "
                    "Bank International Debt Statistics), and the power plants, pipelines and cables with ACWA Power, AMEA "
                    "Power, Masdar, TAQA or the Gulf carriers among their owners."},
]

# A profile appears on the site once its data pack has been fetched; a listed
# lender whose fetch has not run yet (or failed) gets no button and no page.
DONORS = [d for d in DONORS if (DATA / "donors" / (d["slug"] + ".json")).exists()]


# Lender profiles that are groups of countries rather than one state; the
# menu lists them apart from the single countries.
DONOR_BLOCS = ("eu", "gulf", "nordics")

# The deep dives that are about a theme rather than one lender, listed first
# in the menu: slug, title, one line on what it holds, and the file whose
# existence means the page is built.
DEEP_THEMES = [
    ("debt", "Who Africa owes", "Debt by creditor, 2000–2024, from the World Bank", "debt.json"),
    ("compare", "Seven lenders side by side", "Debt, aid and what each one builds, compared", "donors"),
]

DEEP_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6"/><path d="m20 4-9 9"/>'
             '<path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>')

# The menu's look, in one place: brand_assets() fills /*__LMENU_CSS__*/ in
# every template's stylesheet with it. It reuses the .methodbtn look for the
# button and the site's tokens for the panel, so it follows each theme.
LMENU_CSS = """
  /* the Deep dives menu (shared.donor_nav): one button in the top bar, the
     reading pages in a panel under it */
  .lmenu{position:relative}
  .lmenu>summary{list-style:none;cursor:pointer}
  .lmenu>summary::-webkit-details-marker{display:none}
  .lmenu>summary .lm-cur{font-weight:500;color:var(--ink-3)}
  .lmenu>summary .lm-car{width:11px;height:11px;margin-left:1px;transition:transform .15s}
  .lmenu[open]>summary{background:var(--surface-2)}
  .lmenu[open]>summary .lm-car{transform:rotate(180deg)}
  .lm-panel{position:absolute;right:0;top:calc(100% + 6px);z-index:20;width:356px;max-height:calc(100vh - 80px);overflow:auto;background:var(--surface);border:1px solid var(--rule);border-radius:4px;box-shadow:var(--shadow-lg);padding:12px 12px 10px;text-align:left}
  .lm-h{margin:0 2px 4px;font-size:12px;line-height:1.45;color:var(--ink-3);max-width:none}
  .lm-h b{display:block;font-size:13px;font-weight:700;color:var(--ink)}
  .lm-tab{display:flex;align-items:center;gap:6px;margin:6px 2px 2px;font-size:11.5px;font-weight:600;color:var(--accent-ink)}
  .lm-tab svg{width:12px;height:12px;flex:none;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
  .lm-gl{display:block;margin:12px 2px 5px;font-size:9.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
  .lm-themes{display:grid;gap:4px}
  .lm-theme{display:block;padding:7px 9px;border-radius:3px;border:1px solid var(--rule-soft);background:var(--surface-3);color:var(--ink);text-decoration:none;font-family:var(--display);line-height:1.3}
  .lm-theme b{display:block;font-size:12.5px;font-weight:700}
  .lm-theme span{display:block;font-size:11.5px;color:var(--ink-3)}
  .lm-theme:hover{background:var(--surface-2)}
  .lm-theme[aria-current="page"]{background:var(--ink);border-color:var(--ink);color:var(--paper)}
  .lm-theme[aria-current="page"] span{color:color-mix(in srgb,var(--paper) 70%,transparent)}
  .lm-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px}
  .lm-item{display:flex;align-items:center;gap:8px;min-width:0;padding:6px 8px 6px 6px;border-radius:3px;border:1px solid transparent;color:var(--ink);text-decoration:none;font-family:var(--display);font-size:12.5px;font-weight:600;line-height:1.2}
  .lm-item:hover{background:var(--surface-2)}
  .lm-item[aria-current="page"]{background:var(--ink);color:var(--paper)}
  .lm-item[aria-current="page"] .lm-badge{background:transparent;border-color:color-mix(in srgb,var(--paper) 40%,transparent);color:var(--paper)}
  .lm-badge{display:inline-flex;align-items:center;justify-content:center;min-width:34px;height:18px;padding:0 4px;border:1px solid var(--rule);border-radius:2px;background:var(--surface-2);font-family:var(--mono);font-size:9.5px;font-weight:600;letter-spacing:.04em;color:var(--ink-2);flex:none}
  .lm-item>span:last-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  @media (max-width:600px){
    .lmenu>summary .lm-cur{display:none}
    .lm-panel{position:fixed;left:12px;right:12px;top:56px;width:auto}
  }
"""


def donor_nav(current=None):
    """The Deep dives menu, the first button of the top bar on every page: a
    <details> whose panel lists the reading pages beyond the map, the themes
    (debt, the comparison) first, then the lender profiles, single countries
    apart from groups of countries. It opens without scripts; the small
    script only closes it on an outside click or Escape.

    `current` is the page being built: None on the map and the dashboard,
    where every entry opens in a new tab (so the reader's filters and view
    stay where they were, and the panel says so), or the slug of a deep dive
    ("debt", "compare", a lender), whose entry is marked aria-current and
    named on the button, and where entries open in the same tab. Links are
    absolute, so they also work from an artifact; wrap_document makes them
    relative for the Pages build."""
    if not DONORS:
        return ""
    esc = lambda x: html.escape(x, quote=True)
    new_tab = current is None
    tab = ' target="_blank" rel="noopener"' if new_tab else ""
    tip = " (opens in a new tab)" if new_tab else ""

    def link_attrs(slug, title):
        cur = ' aria-current="page"' if slug == current else ""
        return f'href="{site_url(slug + "/")}"{tab}{cur} title="{esc(title + tip)}"'

    def item(d):
        return (f'<a class="lm-item" {link_attrs(d["slug"], d["title"])}>'
                f'<span class="lm-badge">{esc(d["badge"])}</span><span>{esc(d["name"])}</span></a>')
    themes = [(slug, t, sub) for slug, t, sub, need in DEEP_THEMES if (DATA / need).exists()]
    single = sorted((d for d in DONORS if d["slug"] not in DONOR_BLOCS), key=lambda d: d["name"])
    blocs = sorted((d for d in DONORS if d["slug"] in DONOR_BLOCS), key=lambda d: d["name"])
    here = next((d["name"] for d in DONORS if d["slug"] == current), None) or \
        next((t for slug, t, _, _ in DEEP_THEMES if slug == current), "")
    short = {"debt": "Debt", "compare": "Compare"}.get(current, here)
    body = ""
    if themes:
        body += ('<span class="lm-gl">Themes</span><div class="lm-themes">' + "".join(
            f'<a class="lm-theme" {link_attrs(slug, t)}><b>{esc(t)}</b><span>{esc(sub)}</span></a>'
            for slug, t, sub in themes) + "</div>")
    body += f'<span class="lm-gl">Lenders, one by one</span><div class="lm-grid">{"".join(map(item, single))}</div>'
    if blocs:
        body += f'<span class="lm-gl">Groups of lending countries</span><div class="lm-grid">{"".join(map(item, blocs))}</div>'
    note = (f'<p class="lm-tab">{DEEP_ICON}Each one opens in a new tab; the map keeps your filters.</p>'
            if new_tab else "")
    cur_html = f' <span class="lm-cur">· {esc(short)}</span>' if short else ""
    return (
        '<details class="lmenu" id="lmenu">'
        '<summary class="methodbtn" aria-label="Deep dives" title="Deep dives: reading pages on one theme or one lender, '
        'beyond the map">'
        f'{DEEP_ICON}<span>Deep dives{cur_html}</span>'
        '<svg class="lm-car" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary>'
        '<nav class="lm-panel" aria-label="Deep dives">'
        '<p class="lm-h"><b>Deep dives</b>Reading pages on one theme or one lender, each with its own data, '
        f'beyond what the map\'s filters show.</p>{note}{body}'
        '</nav></details>'
        '<script>(()=>{const d=document.getElementById("lmenu");if(!d)return;'
        'document.addEventListener("click",e=>{if(d.open&&!d.contains(e.target))d.open=false;});'
        'document.addEventListener("keydown",e=>{if(e.key==="Escape"&&d.open){d.open=false;d.querySelector("summary").focus();}});'
        '})();</script>')


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
    p, c, w = meta.get("pipelines", {}), meta.get("cables", {}), meta.get("finance_wb", {})
    ch, eu, pm = meta.get("china", {}), meta.get("eu", {}), meta.get("mattei", {})
    rows = [
        {"k": "assets", **SOURCE_INFO["assets"],
         "detail": f"Global Integrated Power Tracker, release {a.get('release', 'unknown')}",
         "fresh": a.get("fresh") or fmt_date(a.get("fetched"))},
        {"k": "finance", **SOURCE_INFO["finance"],
         "detail": f"IATI 2.03 activity files, {f.get('datasets', '?')} country datasets",
         "fresh": f.get("fresh") or fmt_date(f.get("fetched"))},
        {"k": "finance_wb", **SOURCE_INFO["finance_wb"],
         "detail": f"IATI 2.03 activity files, {w.get('datasets', '?')} African country and regional datasets",
         "fresh": w.get("fresh") or fmt_date(w.get("fetched"))},
        {"k": "ground", **SOURCE_INFO["ground"],
         "detail": "Overpass API, significant road/rail/air classes",
         "fresh": g.get("fresh") or fmt_date(g.get("fetched"))},
        {"k": "pipelines", **SOURCE_INFO["pipelines"],
         "detail": f"Global Gas and Global Oil Infrastructure Trackers, releases {p.get('release', 'unknown')}",
         "fresh": p.get("fresh") or fmt_date(p.get("fetched"))},
        {"k": "cables", **SOURCE_INFO["cables"],
         "detail": "Submarine Cable Map, cables with an African landing point",
         "fresh": c.get("fresh") or fmt_date(c.get("fetched"))},
        {"k": "china", **SOURCE_INFO["china"],
         "detail": f"{ch.get('release') or 'Global Chinese Development Finance Dataset 3.0'}, "
                   "official commitments to infrastructure 2000–2021, footprints from OpenStreetMap",
         "fresh": ch.get("fresh") or fmt_date(ch.get("fetched"))},
        {"k": "eu", **SOURCE_INFO["eu"],
         "detail": f"IATI 2.03 activity files of the European Commission (DG INTPA and DG NEAR, "
                   f"{max((eu.get('datasets') or 1) - 1, 0)} African country and regional datasets) "
                   "and the European Investment Bank's global file",
         "fresh": eu.get("fresh") or fmt_date(eu.get("fetched"))},
        {"k": "mattei", **SOURCE_INFO["mattei"],
         "detail": "Piano Mattei per l'Africa project portal (Presidency of the Council of Ministers), "
                   "one page per project, read in its Italian and English versions",
         "fresh": pm.get("fresh") or fmt_date(pm.get("fetched"))},
    ]
    return [r for r in rows if r["k"] in keys]


def payload_meta(meta, keys=MAP_LAYERS):
    return {"built": fmt_date(today()), "sdr_note": SDR_NOTE, "eur_note": EUR_NOTE,
            "sources": sources(meta, keys), "repo": REPO_URL or None,
            # GEM segments that exist in the tracker but carry no route, so the
            # Methodology can say how much of the layer is not drawn
            "unrouted_pipelines": (meta.get("pipelines") or {}).get("unrouted"),
            # what the AidData fetch left out, so the Methodology can say so
            "china_left_out": {k: (meta.get("china") or {}).get(k)
                               for k in ("umbrella", "pledges", "not_infrastructure", "unlocated")},
            # how the EU fetch assembled its records, so the Methodology can say so
            "eu_meta": {k: (meta.get("eu") or {}).get(k)
                        for k in ("contracts", "decisions", "decisions_folded", "eib",
                                  "named_place", "country_point", "regional", "unplaced")},
            # how the Piano Mattei fetch placed its records, so the Methodology can say so
            "mattei_meta": {k: (meta.get("mattei") or {}).get(k)
                            for k in ("stages", "named_place", "named_area", "country_point",
                                      "multi_country", "with_amount", "partner_countries")}}


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


def brand_assets(page, donor=None):
    """Fill the brand markers a template carries: the inline favicon link in
    its head, the header mark next to each <h1>, the mark's home link, the
    row of lender-profile buttons and, where the template asks for them, the
    data-source logos.
    The home link is the absolute site URL so it also works from an artifact;
    wrap_document makes it relative for the Pages build. `donor` is the slug
    of the profile being built, so its own button reads as the current page."""
    for marker in ("<!--__FAVICON__-->", "<!--__LOGO__-->", "__HOME_URL__"):
        if marker not in page:
            raise SystemExit(f"template missing the {marker} marker")
    return (page.replace("<!--__FAVICON__-->", f'<link rel="icon" href="{FAVICON}">')
                .replace("<!--__LOGO__-->", LOGO_MARK)
                .replace("<!--__DONORS__-->", donor_nav(donor))
                .replace("/*__LMENU_CSS__*/", LMENU_CSS)
                .replace("/*__SOURCE_LOGOS__*/{}", json.dumps(SOURCE_LOGOS, ensure_ascii=False))
                .replace("__HOME_URL__", SITE_URL)
                .replace("__COFFEE_URL__", COFFEE_URL)
                .replace("__AUTHOR_URL__", AUTHOR_URL)
                .replace("__WEB_URL__", WEB_URL))


def site_url(path=""):
    return SITE_URL.rstrip("/") + "/" + path.lstrip("/")


# ------------------------------------------------------- what the site says

# The same facts feed the <meta description>, the JSON-LD, the <noscript>
# fallback, llms.txt and the sitemap, so search engines, link previews and
# language-model crawlers all read one story, with this snapshot's figures.

KEYWORDS = ["Africa infrastructure", "infrastructure projects Africa", "Africa power plants map",
            "African Development Bank projects", "AfDB finance", "World Bank projects Africa",
            "construction Africa map",
            "energy Africa", "Global Energy Monitor", "OpenStreetMap construction",
            "oil and gas pipelines Africa", "submarine cables Africa", "TeleGeography",
            "Chinese investment Africa", "China Africa infrastructure", "AidData",
            "Chinese loans Africa", "Belt and Road Africa",
            "EU investment Africa", "Global Gateway Africa", "European Investment Bank Africa",
            "European Commission Africa infrastructure",
            "Piano Mattei", "Mattei Plan Africa", "Italy Africa investment", "Italian cooperation Africa",
            "open data Africa", "infrastructure investment Africa", "interactive map"]

LICENSE_URL = {"CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
               "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
               "ODbL 1.0": "https://opendatacommons.org/licenses/odbl/1-0/",
               "ODC-By 1.0 (footprints ODbL)": "https://opendatacommons.org/licenses/by/1-0/",
               "CC BY 3.0 IT (gazetteer ODbL)": "https://creativecommons.org/licenses/by/3.0/it/"}

LAYER_FILE = {"assets": "gem_power_assets.geojson", "finance": "iati_afdb_finance.geojson",
              "finance_wb": "iati_worldbank_finance.geojson",
              "ground": "osm_construction.geojson", "pipelines": "gem_oil_gas_pipelines.geojson",
              "cables": "telegeography_cables.geojson", "china": "aiddata_china_finance.geojson",
              "eu": "iati_eu_finance.geojson", "mattei": "piano_mattei.geojson"}


def _rows(layer):
    """A layer is either {"cols": [...], "rows": [[...]]} (map payload) or a
    list of dicts (dashboard ground layer). Return (rows, cols)."""
    if isinstance(layer, dict) and "rows" in layer:
        return layer["rows"], layer.get("cols", [])
    return list(layer), []


def site_facts(assets, finance, ground, pipelines=None, cables=None, china=None, eu=None, mattei=None, meta=None):
    """Counts and totals of the snapshot being built, for the crawlable text.
    A page that does not draw a layer passes None for it and the count comes
    from meta.json, so the JSON-LD still describes every file the site
    publishes."""
    meta = load_meta() if meta is None else meta
    a, ac = _rows(assets)
    f, fc = _rows(finance)
    g, _ = _rows(ground)
    mw = sum((r[ac.index("mw")] or 0) for r in a) if "mw" in ac else 0
    usd = sum((r[fc.index("usd_m")] or 0) for r in f) if "usd_m" in fc else 0
    # both pages' finance rows carry a lender column; the fallback covers a
    # caller that passes a lenderless layer
    if "ln" in fc:
        n_afdb = sum(1 for r in f if r[fc.index("ln")] == "AfDB")
        n_wb = sum(1 for r in f if r[fc.index("ln")] == "WB")
        usd_wb = sum((r[fc.index("usd_m")] or 0) for r in f if r[fc.index("ln")] == "WB")
    else:
        n_afdb, n_wb, usd_wb = len(f), (meta.get("finance_wb") or {}).get("activities") or 0, 0

    def count(layer, key):
        if layer is None:
            return (meta.get(key) or {}).get("records") or 0
        return len(_rows(layer)[0])

    def total(layer, col):
        if layer is None:
            return 0
        rows, cols = _rows(layer)
        return sum((r[cols.index(col)] or 0) for r in rows) if col in cols else 0

    return {"assets": len(a), "finance": n_afdb, "finance_wb": n_wb, "finance_total": len(f),
            "ground": len(g),
            "pipelines": count(pipelines, "pipelines"), "cables": count(cables, "cables"),
            "pipe_km": total(pipelines, "km"),
            "china": count(china, "china"), "china_usd_bn": total(china, "usd_m") / 1000,
            "eu": count(eu, "eu"), "eu_usd_bn": total(eu, "usd_m") / 1000,
            "mattei": count(mattei, "mattei"), "mattei_eur_bn": total(mattei, "eur_m") / 1000,
            "gw": mw / 1000, "usd_bn": usd / 1000, "usd_bn_wb": usd_wb / 1000,
            "sources": sources(meta), "built": today(), "meta": meta}


def facts_sentence(facts):
    s = (f"{facts['assets']:,} power units tracked by Global Energy Monitor, "
         f"{facts['finance']:,} projects financed by the African Development Bank")
    if facts.get("finance_wb"):
        s += f" and {facts['finance_wb']:,} by the World Bank"
    s += f", {facts['ground']:,} construction works traced in OpenStreetMap"
    if facts.get("pipelines"):
        s += f", {facts['pipelines']:,} oil and gas pipeline segments from Global Energy Monitor"
    if facts.get("cables"):
        s += f" and {facts['cables']:,} submarine cables landing in Africa from TeleGeography"
    if facts.get("china"):
        s += (f", plus {facts['china']:,} infrastructure projects financed by Chinese official "
              f"lenders and agencies between 2000 and 2021, from AidData")
    if facts.get("eu"):
        s += (f", and {facts['eu']:,} infrastructure projects financed by the European Union's "
              f"institutions, the European Commission and the European Investment Bank, via IATI")
    if facts.get("mattei"):
        s += (f", and the {facts['mattei']:,} projects of Italy's Piano Mattei per l'Africa as the "
              f"Italian Government's portal lists them")
    return s


def facts_totals(facts):
    parts = []
    if facts["gw"]:
        parts.append(f"about {facts['gw']:,.0f} GW of generating capacity across all statuses")
    if facts["usd_bn"]:
        if facts.get("usd_bn_wb"):
            parts.append(f"USD {facts['usd_bn'] - facts['usd_bn_wb']:,.1f} billion of AfDB commitments, "
                         f"converted at {SDR_NOTE}, and USD {facts['usd_bn_wb']:,.1f} billion of World Bank "
                         f"commitments as published")
        else:
            parts.append(f"USD {facts['usd_bn']:,.1f} billion of AfDB commitments, converted at {SDR_NOTE}")
    if facts.get("china_usd_bn"):
        parts.append(f"USD {facts['china_usd_bn']:,.1f} billion of Chinese official commitments to "
                     f"infrastructure over 2000–2021, in constant 2021 dollars as AidData publishes them")
    if facts.get("eu_usd_bn"):
        parts.append(f"USD {facts['eu_usd_bn']:,.1f} billion of European Union commitments, Commission "
                     f"contracts and EIB loans, converted at {EUR_NOTE}")
    if facts.get("mattei_eur_bn"):
        parts.append(f"EUR {facts['mattei_eur_bn']:,.2f} billion of stated Piano Mattei project amounts, "
                     f"the figures the Italian Government's portal prints, which may include other funders' shares")
    return "; ".join(parts)


def structured_data(facts, *, path, title, description, kind):
    """schema.org JSON-LD: the site, this page, the author and the data as a
    Dataset with one part per source, each with its licence and GeoJSON
    download. Google Dataset Search and the AI crawlers both read this."""
    person = {"@type": "Person", "@id": site_url("#author"), "name": AUTHOR_NAME,
              "url": WEB_URL, "sameAs": [WEB_URL, AUTHOR_URL, COFFEE_URL]}
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
                "finance_wb": "World Bank infrastructure projects in Africa from its IATI 2.03 "
                              "activity files: title, recipient country or region, status, DAC "
                              "sector, commitment and disbursement in USD, and the Bank's geocoded "
                              "project locations with their location class.",
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
                          "from TeleGeography's Submarine Cable Map.",
                "china": "Infrastructure projects in Africa supported by official financial "
                         "commitments from China between 2000 and 2021 (loans and grants from "
                         "China Eximbank, China Development Bank, the Ministry of Commerce and "
                         "other official lenders), with status, sector, funder, implementer, "
                         "commitment in constant 2021 USD, loan terms where known, and the "
                         "project's footprint traced in OpenStreetMap where AidData geocoded it, "
                         "from AidData's Global Chinese Development Finance Dataset 3.0 and its "
                         "Geospatial companion.",
                "eu": "Infrastructure projects in Africa financed by the European Union's "
                      "institutions: the European Commission's contracts and financing decisions "
                      "(DG International Partnerships and DG Neighbourhood and Enlargement) and the "
                      "European Investment Bank's loans, equity and grants, from their IATI activity "
                      "files, with status, DAC or EIB sector, implementer, instrument, commitment "
                      "and disbursement in euros, and the location the publisher gives: a named "
                      "place, the country's point or the Commission's Africa-wide point.",
                "mattei": "The projects of Italy's Piano Mattei per l'Africa (Mattei Plan) as the "
                          "Italian Government's project portal lists them: title, the plan's "
                          "directive (energy, water, agriculture, health, education, infrastructure), "
                          "objective, countries, implementing body, partners, funding source, the "
                          "stated amount in euros and the portal's progress stage (identified, "
                          "formulated, approved, ongoing, completed), placed on the site the "
                          "description names, the country's point or between the countries listed."}[k]
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
               "description": f"Ten open datasets on infrastructure in Africa, kept as separate "
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
            "primaryImageOfPage": {"@type": "ImageObject", "url": social_image_url(),
                                   "width": SOCIAL_W, "height": SOCIAL_H}}
    if kind == "map":
        page["applicationCategory"] = "Map"
        page["operatingSystem"] = "Any (web browser)"
        page["offers"] = {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
    graph = [website, person, page, dataset, *parts]
    if path:
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Africa Infrastructure Map", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": "Dashboard" if kind == "dashboard" else title, "item": site_url(path)}]})
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
<p>{lede} of infrastructure projects across Africa, built from ten open datasets:
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
<p>Limits: money is two multilateral lenders, AfDB and the World Bank, the European Union's
institutions (the Commission's contracts and the EIB's loans, as each publishes them to IATI),
Chinese official finance as AidData reconstructs it from public sources, and the amounts Italy's
Piano Mattei portal states for its projects, which may be a whole project's value rather than
Italy's share; the Chinese layer ends with commitments made in 2021, so totals are those lenders'
exposure, never summed and not investment in Africa; about two thirds of AfDB locations sit on a
country or region centroid, the World Bank marks every location approximate, the EIB and the
Piano Mattei portal publish no locations at all, so their records sit on a place the record names
or at their country's point, and about a quarter of the Chinese-financed
projects have no published location and sit at their country's centre; OpenStreetMap presence is mapper-driven,
so absence is not evidence; energy and connectivity are over-represented because no comparable
open tracker exists for ports, water or electricity transmission.</p>
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
    # Every link into the site (the home link, the Methodology link, the
    # lender-profile buttons) is absolute in the templates; here it becomes
    # relative to this page's folder, so the pages also work at any other
    # address. A profile lives one folder down (russia/index.html).
    up = "../" * path.count("/")

    def relative(m):
        rest = m.group(1)
        if not rest or rest.startswith("#"):
            rest = "index.html" + rest
        return f'href="{up}{rest}"'
    frag = re.sub(r'href="' + re.escape(SITE_URL) + r'([^"]*)"', relative, frag)
    frag = re.sub(r'<link rel="icon" href="data:[^"]*">',
                  f'<link rel="icon" href="{up}favicon.svg" type="image/svg+xml">\n'
                  f'<link rel="icon" href="{up}icon-192.png" type="image/png" sizes="192x192">\n'
                  f'<link rel="apple-touch-icon" href="{up}apple-touch-icon.png">', frag, count=1)
    cut = frag.index("</style>") + len("</style>")
    head_part, body_part = frag[:cut], frag[cut:]
    q = lambda x: html.escape(x, quote=True)
    t, d = q(title), q(description)
    url = q(site_url(path))
    img = q(social_image_url())
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
<title>Geopolitics of Africa: {t} · {q(SITE_NAME)}</title>
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
{jsonld}{extra_head}<script data-goatcounter="https://jacopo.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
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
            *[(d["slug"] + "/", "monthly", "0.8") for d in DONORS],
            *([("debt/", "monthly", "0.8"), ("data/debt.json", "monthly", "0.3")] if (DOCS / "debt" / "index.html").exists() else []),
            *([("compare/", "monthly", "0.8"), ("data/compare.json", "monthly", "0.3")] if (DOCS / "compare" / "index.html").exists() else []),
            *[("data/donors/" + d["slug"] + ".json", "monthly", "0.3") for d in DONORS],
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

    donor_pages = "".join(
        f"- [{d['title']}]({site_url(d['slug'] + '/')}): {d['description']} "
        f"Data: {site_url('data/donors/' + d['slug'] + '.json')}\n" for d in DONORS)
    src_lines = "\n".join(
        f"- [{s['name']}]({s['url']}): {s['detail']}. {facts[s['k']]:,} records, data as of "
        f"{s['fresh']}, licence {s['lic']}. GeoJSON: {site_url('data/' + LAYER_FILE[s['k']])}"
        for s in facts["sources"])
    (DOCS / "llms.txt").write_text(f"""# {SITE_NAME}

> An interactive map and dashboard of announced, approved and ongoing infrastructure in
> Africa, for investors, researchers and journalists. Compiled from ten open datasets:
> {facts_sentence(facts)}. Together they describe {facts_totals(facts)}.
> Snapshot built {fmt_date(day)}; data is refreshed by hand about twice a year.

Made by {AUTHOR_NAME} ({AUTHOR_URL}). Free to use; cite the underlying sources by name.
Site: {SITE_URL}

## Pages

- [Africa Infrastructure Map]({SITE_URL}): full-screen map of the eight layers (finance holds two lenders, EU finance the Commission and the EIB, Piano Mattei Italy's plan) with filters
  by layer, status, country and sector, a viewport summary, a "largest in view" list, detail
  cards linking to each source record, optional marker clustering and Sentinel-2 satellite
  imagery, and a Methodology tab. The view is encoded in the URL hash, so views can be shared.
- [Africa Infrastructure Map, dashboard view]({site_url('dashboard.html')}): the same records as a page
  with KPIs, a country map, bar charts by country and sector, and a sortable table.
{donor_pages}{"- [Debt: who African governments owe, creditor by creditor](" + site_url("debt/") + "): World Bank International Debt Statistics by creditor, with a card on the dashboard. Data: " + site_url("data/debt.json") + chr(10) if (DOCS / "debt" / "index.html").exists() else ""}{"- [Compare the lenders](" + site_url("compare/") + "): the seven lender profiles side by side, with filters by lender, region or country, year and measure: where each one's money goes (small-multiple maps and a who-leads-where map), what it funds (sector mix), how it is lent (grants, loans, delivery channels, concentration) and how its exposure moved since 2000. Data: " + site_url("data/compare.json") + chr(10) if (DOCS / "compare" / "index.html").exists() else ""}
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
  ready-for-service year is within a year of the snapshot, otherwise announced. Chinese
  finance (AidData): "Pipeline: Commitment" is approved, "Implementation" is under
  construction, "Completion" is operating, "Suspended" and "Cancelled" are stalled; pledges
  (MoUs, letters of intent) and umbrella agreements are left out, so the layer has no
  announced records and no double-counted money. EU finance: IATI statuses as for AfDB
  (1 announced, 2 under construction, 3-4 operating, 5-6 stalled); a Commission financing
  decision still in the pipeline is an announced record. Piano Mattei: the portal's progress
  stage, "identified" and "formulated" are announced, "approved" is approved, "ongoing" is
  under construction, "completed" is operating; the portal has no cancelled stage.
- Shape is source, colour is status, size is scale: circles are power units sized by MW,
  squares are AfDB projects and diamonds World Bank projects, both sized by commitment, thin lines are construction ways as
  traced, haloed lines are pipeline routes, lines ending in dots are submarine cables
  with their African landing points, triangles are Chinese-financed projects sized by
  commitment, with the project's OpenStreetMap footprint drawn as a thin outline where
  AidData geocoded it precisely, stars are EU-financed records (European Commission
  contracts and decisions, EIB operations) sized by commitment, hexagons are Piano Mattei
  projects sized by the amount the Italian Government's portal states. Dashed lines are not yet built.
- Amounts are commitments (IATI transaction type 2). AfDB publishes in SDR, converted at a
  fixed, stated rate: {SDR_NOTE}. The World Bank publishes in USD, taken as is. AidData's
  Chinese commitments are in constant 2021 US dollars, as published, and are never added to
  the IATI figures. The EU institutions publish in euros, converted at a fixed, stated rate:
  {EUR_NOTE}; a Commission contract carries the contracted amount, a financing decision with
  no contract yet its whole envelope, an EIB operation the signed amount (the Bank's file
  repeats each commitment transaction per tranche record; the distinct ones are summed).
  Piano Mattei amounts are the figure the portal prints for each project, in euros as
  stated, converted at the same rate; the portal does not say whether a figure is Italy's
  share or the whole project's value, so they are shown on their own and never added to
  the lenders' commitments.

## Limits

- Money is two multilateral lenders, AfDB and the World Bank, the European Union's
  institutions (the Commission and the EIB, each publishing its own share to IATI), plus
  Chinese official finance as AidData reconstructs it from public sources. Private,
  domestic-budget, EU member states' bilateral and other-lender finance is not here. Read
  totals as each lender's exposure, not as investment in Africa. The four are never summed
  into one project cost, and the Piano Mattei figures are not added to any of them.
- The Piano Mattei layer is the Italian Government's own list of the plan's projects, all of
  them, not an infrastructure subset: 40 of the 76 are education, training or culture.
  Narrow by sector to keep the ones that build something. The portal publishes no
  coordinates: a record sits on the place its description names (coordinates from
  OpenStreetMap), on the country's point, or, for a multi-country programme, between its
  countries, which is not a site.
- The EU layer is the Commission's contracts (one record per grant, delegation agreement or
  works contract under a financing decision; a decision is a record only when none of its
  contracts is published yet) and the EIB's operations. The Commission's points are either
  a named place or the country's default point; the EIB publishes no locations, so its
  records sit at the country's point; Africa-wide programmes sit at the Commission's
  regional point, in Chad.
- The Chinese layer is a historical baseline: AidData's 3.0 release covers commitments
  made 2000-2021 and their implementation to 2023. It says where Chinese money went, not
  what China is financing now. Only projects AidData flags as physical infrastructure are
  kept; about a quarter have no published location and sit at their country's centre.
- About two thirds of AfDB locations are approximate (a country or region centroid). The
  World Bank marks every location approximate and states its class: site, populated place
  or administrative region. The pages say which for each record.
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
- [European Commission, DG International Partnerships](https://iatiregistry.org/publisher/ec-intpa), [DG Neighbourhood and Enlargement](https://iatiregistry.org/publisher/ec-near) and the [European Investment Bank](https://iatiregistry.org/publisher/eib) on the IATI Registry
- [Piano Mattei per l'Africa, project portal of the Italian Government](https://www.governo.it/en/piano-mattei/progetti/)
- [AidData, Global Chinese Development Finance Dataset 3.0](https://www.aiddata.org/data/aiddatas-global-chinese-development-finance-dataset-version-3-0) and its [geospatial companion on GitHub](https://github.com/aiddata/gcdf-geospatial-data)
- [OpenStreetMap copyright and licence](https://www.openstreetmap.org/copyright)
- [Natural Earth](https://www.naturalearthdata.com/)
""")
