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

from region import BMZ_LENDERS, REGION, ROOT_DOCS, region_payload  # noqa: E402

ROOT = pathlib.Path(__file__).parent
# this edition's data and pages: data/ and docs/ for Africa, data/sea/ and
# docs/se-asia/ for Southeast Asia (see region.py); the download caches stay
# under data/ whatever the edition
DATA = REGION.data_dir
DOCS = REGION.docs_dir

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
SDR_USD = 1.35
SDR_NOTE = "1 SDR = 1.35 USD (IMF, 9 Oct 2026)"
# The EU institutions publish in euros; one fixed, stated rate, like the SDR one.
EUR_USD = 1.1206
EUR_NOTE = "1 EUR = 1.1206 USD (ECB reference rate, 9 Oct 2026)"
# The ADB publishes a few non-sovereign loans in the borrower's currency (Thai
# baht, Philippine pesos). One fixed, stated rate per currency, like the SDR
# and euro ones: the ECB's reference rate against the euro on the day stated,
# crossed with its dollar rate. Any other currency is left uncounted, and the
# card says so.
LOCAL_USD = {"THB": 0.029927, "PHP": 0.015881, "IDR": 0.00005546, "MYR": 0.245009, "SGD": 0.78173,
             "VND": 0.0000380, "INR": 0.01053, "CNY": 0.149561}
LOCAL_NOTE = "ECB reference rates, 16 Oct 2026"

# Where the site lives. Canonical and social-preview URLs point here; the pages
# themselves use only relative links, so they also work at any other address.
ROOT_SITE_URL = os.environ.get("AIW_SITE_URL", "https://jacopoottaviani.com/africa-infra-watch/")
# an edition other than Africa lives in a folder of its own under the site
SITE_URL = ROOT_SITE_URL.rstrip("/") + "/" + REGION.url_slug
# Personal links carried by both pages (support button, credit line). Change here, rebuild.
COFFEE_URL = os.environ.get("AIW_COFFEE_URL", "https://ko-fi.com/jacopoottaviani")
AUTHOR_URL = os.environ.get("AIW_AUTHOR_URL", "https://www.linkedin.com/in/jacopo-ottaviani/")
WEB_URL = os.environ.get("AIW_WEB_URL", "https://jacopoottaviani.com/")
# a WhatsApp username link opens a chat without showing the phone number
WHATSAPP_URL = os.environ.get("AIW_WHATSAPP_URL", "https://wa.me/jacopoottaviani")

# What the site is called in search results, link previews and structured data:
# AfricaWatch for the Africa site (since 19 October 2026; the address keeps the
# africa-infra-watch slug); other editions keep the umbrella name.
SITE_NAME = "AfricaWatch" if REGION.key == "africa" else "InfraRadar"
# The edition's regional development bank, AfDB or ADB: short name, full name.
BANK = REGION.bank["code"]
BANK_NAME = REGION.bank["name"]
NUM_WORD = {7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
# "noindex" while an edition is built but not yet published (region.py)
ROBOTS = "noindex,nofollow" if REGION.noindex else "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1"


def an(word):
    """"an African", "a Southeast Asian", "an AfDB-financed": the article a word takes."""
    return ("an " if word[:1].lower() in "aeiou" else "a ") + word
# The name beside the logo, as a two-colour wordmark, for the headers, the
# footer and the loading box, one word: "Africa" in the accent (the mark's colour;
# .wm-r lives in LMENU_CSS), "Watch" in the surrounding ink. Other editions
# print "InfraRadar", "Radar" in the accent. Templates print it through
# __SITE_WORDMARK__.
SITE_WORDMARK = ('<span class="wm-r">Africa</span>Watch' if REGION.key == "africa"
                 else 'Infra<span class="wm-r">Radar</span>')
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
        if DOCS != ROOT_DOCS and (ROOT_DOCS / SOCIAL_IMAGE).exists():   # an edition without a card of its own
            path = ROOT_DOCS / SOCIAL_IMAGE
            return (ROOT_SITE_URL.rstrip("/") + "/" + SOCIAL_IMAGE + "?v="
                    + hashlib.sha1(path.read_bytes()).hexdigest()[:10])
        return site_url(SOCIAL_IMAGE)
    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    return site_url(SOCIAL_IMAGE) + "?v=" + digest

# The repository the site is deployed from, linked from the Methodology tab
# when set (e.g. "https://github.com/<user>/africa-infra-watch"). Optional.
REPO_URL = os.environ.get("AIW_REPO_URL", "").strip()

SOURCE_INFO = {
    "assets": {"name": "Global Energy Monitor", "lic": "CC BY 4.0",
               "url": "https://globalenergymonitor.org/projects/global-integrated-power-tracker/"},
    "finance": {"name": BANK_NAME, "lic": REGION.bank["lic"], "url": REGION.bank["registry"]},
    "finance_wb": {"name": "World Bank", "lic": "CC BY 4.0",
                   "url": "https://d-portal.iatistandard.org/ctrack.html?publisher=44000#view=main"},
    # AFD's IATI files sit on data.gouv.fr under the French Government's
    # Licence Ouverte (dataset "Données de l'aide au développement de l'AFD")
    "finance_afd": {"name": "Agence française de développement", "lic": "Licence Ouverte / Open Licence",
                    "url": "https://d-portal.iatistandard.org/ctrack.html?publisher=FR-3#view=main"},
    # BMZ's country files carry "cc-by" on the IATI Registry, no version stated
    "finance_bmz": {"name": "BMZ (German development ministry)", "lic": "CC BY (per the IATI Registry)",
                    "url": "https://d-portal.iatistandard.org/ctrack.html?publisher=DE-1#view=main"},
    "ground": {"name": "OpenStreetMap", "lic": "ODbL 1.0",
               "url": "https://www.openstreetmap.org/copyright"},
    "pipelines": {"name": "Global Energy Monitor", "lic": "CC BY 4.0",
                  "url": "https://globalenergymonitor.org/projects/global-gas-infrastructure-tracker/"},
    # TeleGeography puts its map under CC BY-SA 4.0 and keeps the data behind
    # it for subscribers: the site draws the routes and does not offer the
    # layer as a download (see fetch_sources.py)
    "cables": {"name": "TeleGeography", "lic": "© TeleGeography (map CC BY-SA 4.0)",
               "url": "https://www.submarinecablemap.com/"},
    # the project records are AidData's (ODC-By); the footprints are traced in
    # OpenStreetMap and stay under OSM's ODbL
    "china": {"name": "AidData", "lic": "ODC-By 1.0 (footprints ODbL)",
              "url": "https://www.aiddata.org/data/chinas-global-loans-and-grants-dataset-1-0"},
    # the Commission's IATI files fall under the EU's open-data decision
    # (CC BY 4.0); the EIB's are under the Bank's own terms, attribution required
    "eu": {"name": "European Union", "lic": "CC BY 4.0 (Commission), attribution (EIB)",
           "url": "https://d-portal.iatistandard.org/ctrack.html?publisher=XI-IATI-EC_INTPA#view=main"},
    # the Italian Government's portal content is CC BY 3.0 IT (governo.it, Note
    # legali); the gazetteer coordinates behind the named places are OpenStreetMap's
    "mattei": {"name": "Italian Government", "lic": "CC BY 3.0 IT (gazetteer ODbL)",
               "url": "https://www.governo.it/en/piano-mattei/progetti/"},
}
# The layers each page draws. Both pages show the same eight layers over the
# same records, and both split the finance layer between its lenders, so
# both carry the World Bank source card, and in Africa AFD's and BMZ's.
FINANCE_KEYS = (("finance", "finance_wb") + (("finance_afd",) if getattr(REGION, "afd_files", None) else ())
                + (("finance_bmz",) if getattr(REGION, "bmz_files", None) else ()))
MAP_LAYERS = tuple(k for layer in REGION.layers
                   for k in (FINANCE_KEYS if layer == "finance" else (layer,)))
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
                    "project-level record of Chinese official commitments since 2000 country by country, "
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
    ("corridors", "Africa's strategic corridors", "Railways, ports and pipelines: who pays and who builds", "corridors.json"),
]

# The menu bar names a theme by one short word; its full title is the
# tooltip, the dropdown's card and the footer's link. A theme missing here
# shows its title in the bar.
DEEP_SHORT = {"debt": "Debt", "compare": "Compare", "corridors": "Corridors"}

DEEP_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6"/><path d="m20 4-9 9"/>'
             '<path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>')
# a grid, not the three bars the map and the dashboard use for their filters drawer
MENU_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="6.5" height="6.5" rx="1"/>'
             '<rect x="13.5" y="4" width="6.5" height="6.5" rx="1"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1"/>'
             '<rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1"/></svg>')
BOOK_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/>'
             '<path d="M4 20.5V5.5M20 18v3H6.5"/><path d="M9 8h7M9 11.5h7"/></svg>')
CARET = '<svg class="lm-car" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>'
# the footer's two support buttons: the same steaming cup as every page's coffee button,
# and LinkedIn's mark (a white tile with the blue "in")
COFFEE_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><g class="steam"><path d="M8 3v2.5M11.5 2v3.5M15 3v2.5"/></g>'
               '<g class="cup"><path d="M5 9h11v6a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4z"/><path d="M16 10h1.5a2.5 2.5 0 0 1 0 5H16"/>'
               '<path d="M4 22h14"/></g></svg>')
LINKEDIN_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="1" y="1" width="22" height="22" rx="4" fill="#fff"/>'
                 '<path fill="#0A66C2" transform="translate(2.9 3.1) scale(.73)" d="M6.94 5a2 2 0 1 1-4-.002 2 2 0 0 1 4 .002zM7 '
                 '8.48H3V21h4V8.48zm6.32 0H9.34V21h3.94v-6.57c0-3.66 4.77-4 4.77 0V21H22v-7.93c0-6.17-7.06-5.94-8.72-2.91l.04-1.68z"/></svg>')

# The menu bar's and the footer's look, in one place: brand_assets() fills
# /*__LMENU_CSS__*/ in every template's stylesheet with it. It uses the
# site's tokens only, so it follows each theme.
LMENU_CSS = """
  .wm-r{color:var(--accent)}   /* the accent half of the wordmark (SITE_WORDMARK) */
  /* ---------- the menu bar (shared.site_nav) ----------
     Map, Dashboard, the theme deep dives by name, the lender profiles in a
     dropdown, Methodology, Contact me. It folds in three steps as the window narrows:
     the "Deep dives" kicker goes, then the themes and the lenders fold into
     one "Deep dives" dropdown, then everything but Methodology folds into
     "Menu". The map and the dashboard (.snav.sn-app) fold sooner: the rail takes
     409 px there, and their own controls share the top edge. */
  .snav{display:flex;align-items:center;gap:1px;height:34px;padding:0 3px;background:var(--surface);border:1px solid var(--rule);border-radius:4px;box-shadow:var(--shadow);font-family:var(--display)}
  .sn-a{display:inline-flex;align-items:center;gap:6px;height:26px;margin:0;padding:0 9px;border:0;border-radius:3px;background:none;color:var(--ink);font-family:var(--display);font-size:12px;font-weight:600;line-height:1;letter-spacing:.005em;white-space:nowrap;text-decoration:none;cursor:pointer;list-style:none;transition:background .15s,color .15s}
  .sn-a::-webkit-details-marker{display:none}
  .sn-a:hover{background:var(--surface-2)}
  .sn-a:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
  .sn-a svg{width:15px;height:15px;flex:none;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
  .sn-a[aria-current="page"],.sn-a[aria-pressed="true"],.sn-dd.cur>.sn-a,.sn-dd.cur[open]>.sn-a{background:var(--ink);color:var(--paper)}
  .sn-sep{flex:none;width:1px;height:16px;margin:0 5px;background:var(--rule)}
  .sn-k{padding:0 5px 0 3px;font-size:9.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);white-space:nowrap}
  .sn-dd{position:relative}
  .sn-dd[open]>.sn-a{background:var(--surface-2)}
  .sn-dd .lm-car{width:11px;height:11px;margin:0 -3px 0 -3px;transition:transform .15s}
  .sn-dd[open] .lm-car{transform:rotate(180deg)}
  .sn-cur{font-weight:500;opacity:.72}
  /* Contact me: the bar's one filled item, in LinkedIn's blue, with the footer button's
     shine and logo flip (lishine, liflip) */
  .sn-a.sn-contact{position:relative;margin-left:4px;overflow:hidden;isolation:isolate;background:#0A66C2;color:#fff}
  .sn-a.sn-contact::before{content:"";position:absolute;inset:0;z-index:-1;background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.5) 50%,transparent 65%);transform:translateX(-130%)}
  .sn-a.sn-contact svg{stroke:none;overflow:visible}
  .sn-a.sn-contact:hover,.sn-a.sn-contact:focus-visible{background:#0B74DB;color:#fff}
  .sn-a.sn-contact:hover::before,.sn-a.sn-contact:focus-visible::before{animation:lishine .75s ease-out forwards}
  .sn-a.sn-contact:hover svg,.sn-a.sn-contact:focus-visible svg{animation:liflip .6s cubic-bezier(.34,1.56,.64,1)}
  /* the map's coffee cup after it: the coffee button's yellow, icon only, steam always on; hover
     runs that button's wiggle and steam (cwiggle, csteam, defined in each template) */
  .sn-a.sn-coffee{margin-left:3px;padding:0 6px;background:#FFDD00;color:#1F1A00}
  .sn-a.sn-coffee svg{width:16px;height:16px;overflow:visible}
  .sn-a.sn-coffee .cup{transform-box:fill-box;transform-origin:50% 100%}
  .sn-a.sn-coffee:hover,.sn-a.sn-coffee:focus-visible{background:#FFE733;color:#1F1A00}
  .sn-a.sn-coffee:hover .cup,.sn-a.sn-coffee:focus-visible .cup{animation:cwiggle .55s ease}
  .sn-a.sn-coffee:hover .steam,.sn-a.sn-coffee:focus-visible .steam{animation:csteam 1.1s ease-in-out infinite}
  .sn-more,.sn-ico,.lm-site{display:none}
  .sn-ms{display:none;align-items:center;gap:6px}
  /* the reading pages: their header is capped at the column's 1140 px, too narrow for the
     kicker beside the coffee button, so it never shows there; then themes and lenders fold */
  .snav:not(.sn-app) .sn-k{display:none}
  @media (max-width:1100px){.snav:not(.sn-app) .sn-t{display:none}.snav:not(.sn-app) .sn-more{display:block}}
  @media (max-width:1000px){
    .snav:not(.sn-app) .sn-x,.snav:not(.sn-app) .sn-ml,.snav:not(.sn-app) .sn-meth .sn-l,.snav:not(.sn-app) .sn-contact .sn-l{display:none}
    .snav:not(.sn-app) .sn-ms{display:inline-flex}
    .snav:not(.sn-app) .sn-meth .sn-ico{display:block}
    .snav:not(.sn-app) .lm-site{display:grid}
    .snav:not(.sn-app) .sn-meth,.snav:not(.sn-app) .sn-contact{padding:0 7px}
    .snav:not(.sn-app) .sn-more.cur>.sn-a{background:none;color:var(--ink)}
    .snav:not(.sn-app) .sn-more.cur[open]>.sn-a{background:var(--surface-2)}
  }
  /* the map and the dashboard */
  @media (max-width:1533px){.snav.sn-app .sn-k{display:none}}
  @media (max-width:1453px){.snav.sn-app .sn-t{display:none}.snav.sn-app .sn-more{display:block}}
  @media (max-width:1233px){
    .snav.sn-app .sn-x,.snav.sn-app .sn-ml,.snav.sn-app .sn-meth .sn-l,.snav.sn-app .sn-contact .sn-l{display:none}
    .snav.sn-app .sn-ms{display:inline-flex}
    .snav.sn-app .sn-meth .sn-ico{display:block}
    .snav.sn-app .lm-site{display:grid}
    .snav.sn-app .sn-meth,.snav.sn-app .sn-contact{padding:0 7px}
  }

  /* the dropdown panels */
  .lm-panel{position:absolute;right:0;top:calc(100% + 8px);z-index:20;width:356px;max-height:calc(100vh - 80px);overflow:auto;background:var(--surface);border:1px solid var(--rule);border-radius:4px;box-shadow:var(--shadow-lg);padding:12px 12px 10px;text-align:left;font-family:var(--display)}
  .lm-h{margin:0 2px 4px;font-size:12px;line-height:1.45;color:var(--ink-3);max-width:none}
  .lm-h b{display:block;font-size:13px;font-weight:700;color:var(--ink)}
  .lm-tab{display:flex;align-items:center;gap:6px;margin:6px 2px 2px;font-size:11.5px;font-weight:600;color:var(--accent-ink)}
  .lm-tab svg{width:12px;height:12px;flex:none;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
  .lm-gl{display:block;margin:12px 2px 5px;font-size:9.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
  .lm-site{grid-template-columns:1fr 1fr;gap:4px;margin:0 0 10px;padding-bottom:10px;border-bottom:1px solid var(--rule-soft)}
  .lm-site .lm-item{justify-content:center;padding:7px 8px;border-color:var(--rule-soft);background:var(--surface-3)}
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
  .lm-item[aria-current="page"],.lm-site .lm-item[aria-current="page"]{background:var(--ink);border-color:var(--ink);color:var(--paper)}
  .lm-item[aria-current="page"] .lm-badge{background:transparent;border-color:color-mix(in srgb,var(--paper) 40%,transparent);color:var(--paper)}
  .lm-badge{display:inline-flex;align-items:center;justify-content:center;min-width:34px;height:18px;padding:0 4px;border:1px solid var(--rule);border-radius:2px;background:var(--surface-2);font-family:var(--mono);font-size:9.5px;font-weight:600;letter-spacing:.04em;color:var(--ink-2);flex:none}
  .lm-item>span:last-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  @media (max-width:600px){
    .lm-panel{position:fixed;left:12px;right:12px;top:56px;width:auto}
  }
  @media (prefers-reduced-motion:reduce){.sn-a,.sn-dd .lm-car{transition:none}.sn-a.sn-contact::before,.sn-a.sn-contact svg,.sn-a.sn-coffee .cup,.sn-a.sn-coffee .steam{animation:none!important}}

  /* ---------- the footer (shared.site_footer) ----------
     every page in four columns: the site, Explore, the theme deep dives, the
     lender profiles. It reflows on its own width, so the same footer sits
     under a reading page and at the foot of the map's rail. */
  .sf{container-type:inline-size}
  .sf-grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,.8fr) minmax(0,1.15fr) minmax(0,1.25fr);gap:26px 40px;font-family:var(--display);font-size:12.5px;line-height:1.45;color:var(--ink-2);text-align:left}
  .sf-home{display:inline-flex;align-items:center;gap:9px;color:var(--ink);text-decoration:none}
  .sf-home .mark{flex:none;display:block;font-size:30px;color:var(--accent)}
  .sf-home .kicker{display:block;font-size:9.5px}
  .sf-home b{display:block;margin-top:2px;font-size:14px;font-weight:800;letter-spacing:-.02em;line-height:1.15}
  .sf-home:hover b{color:var(--accent)}
  .sf-about{margin:12px 0 0;max-width:40ch}
  .sf-made{margin:10px 0 0;font-size:12px;color:var(--ink-3)}
  .sf-made .heart{color:var(--accent)}
  .sf-h{margin:3px 0 10px;font-size:9.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
  .sf-h2{margin:14px 0 8px;font-size:11px;font-weight:600;color:var(--ink-3)}
  .sf-list{display:grid;gap:7px;margin:0;padding:0;list-style:none}
  .sf-list.two{grid-template-columns:1fr 1fr;column-gap:14px}
  .sf-list small{display:block;margin-top:1px;font-size:11.5px;font-weight:400;color:var(--ink-3)}
  .sf-grid a:not(.sf-b){color:var(--ink);font-weight:600;text-decoration:none;border:0}
  .sf-grid a:not(.sf-b):hover{color:var(--accent);text-decoration:underline;text-underline-offset:2px}
  .sf-grid a[aria-current="page"]{color:var(--accent)}
  .sf-grid a[aria-current="page"]::after{content:" ·  you are here";font-weight:400;font-size:11px;color:var(--ink-3)}
  .sf-made a:not(.sf-b){color:var(--ink-2)}
  /* the two support buttons under the credit: the site's coffee button (.coffee, drawn
     and animated by each template's own stylesheet) and a LinkedIn twin that tilts the
     other way and flips its logo */
  .sf-cta{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 0}
  .sf-cta .coffee,.sf-cta .sf-li{height:36px;padding:0 14px 0 11px;gap:8px;font-size:12px}
  .sf-cta .coffee span{display:inline}
  .sf-cta svg{width:17px;height:17px}
  .sf-li{position:relative;display:inline-flex;align-items:center;border-radius:3px;background:#0A66C2;color:#fff;border:1px solid #0858A8;font-family:var(--display);font-weight:700;letter-spacing:.01em;white-space:nowrap;text-decoration:none;box-shadow:var(--shadow);overflow:hidden;isolation:isolate;transform-origin:center;transition:transform .22s cubic-bezier(.34,1.56,.64,1),box-shadow .22s,background .22s}
  .sf-li::before{content:"";position:absolute;inset:-1px;z-index:-1;background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.5) 50%,transparent 65%);transform:translateX(-130%)}
  .sf-li svg{flex:none;overflow:visible}
  .sf-li:hover,.sf-li:focus-visible{background:#0B74DB;color:#fff;transform:translateY(-2px) rotate(2deg) scale(1.05);box-shadow:0 8px 22px -8px rgba(10,102,194,.85),0 2px 4px rgba(22,33,28,.12)}
  .sf-li:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  .sf-li:hover::before,.sf-li:focus-visible::before{animation:lishine .75s ease-out forwards}
  .sf-li:hover svg,.sf-li:focus-visible svg{animation:liflip .6s cubic-bezier(.34,1.56,.64,1)}
  .sf-li:active{transform:translateY(0) scale(.98)}
  @keyframes lishine{to{transform:translateX(130%)}}
  @keyframes liflip{from{transform:perspective(80px) rotateY(0)}to{transform:perspective(80px) rotateY(360deg)}}
  @media (prefers-reduced-motion:reduce){.sf-li,.sf-li::before,.sf-li svg{animation:none!important;transition:none!important}.sf-li:hover{transform:none}}
  @container (max-width:860px){.sf-grid{grid-template-columns:1fr 1fr}.sf-brand{grid-column:1/-1}}
  @container (max-width:460px){.sf-grid{grid-template-columns:1fr;gap:22px}}
"""


def _deep_pages():
    """The published deep dives: the themes whose data is built, then the
    lender profiles, single countries apart from groups of countries. The
    menu bar and the footer both read this, so they always list the same
    pages; pages that are built but unlisted (Lobito, LAPSSET, minerals)
    stay out of both until they are added to DEEP_THEMES."""
    themes = [(slug, t, sub) for slug, t, sub, need in DEEP_THEMES if (DATA / need).exists()]
    single = sorted((d for d in DONORS if d["slug"] not in DONOR_BLOCS), key=lambda d: d["name"])
    blocs = sorted((d for d in DONORS if d["slug"] in DONOR_BLOCS), key=lambda d: d["name"])
    return themes, single, blocs


def _is_app(current):
    """True on the map and the dashboard, where a deep dive opens in a new
    tab so the reader's filters and view stay where they were."""
    return current in (None, "map", "dashboard")


NAV_SCRIPT = (
    # one dropdown open at a time; an outside click or Escape closes it; on a
    # phone the panel is pinned under the bar. A [data-method] link opens the
    # map's Methodology tab in place when the page has one (the map's rail).
    '<script>(()=>{const dd=[...document.querySelectorAll(".sn-dd")];'
    'const place=d=>{const p=d.querySelector(".lm-panel");if(!p)return;p.style.top=p.style.maxHeight="";'
    'if(innerWidth<=600){const t=Math.round(d.closest(".snav").getBoundingClientRect().bottom+8);'
    'p.style.top=t+"px";p.style.maxHeight=(innerHeight-t-12)+"px";}};'
    'dd.forEach(d=>d.addEventListener("toggle",()=>{if(d.open){dd.forEach(o=>{if(o!==d)o.open=false;});place(d);}}));'
    'document.addEventListener("click",e=>{dd.forEach(d=>{if(d.open&&!d.contains(e.target))d.open=false;});'
    'const m=e.target.closest&&e.target.closest("[data-method]"),b=document.getElementById("methodtop");'
    'if(m&&b&&b.tagName==="BUTTON"){e.preventDefault();if(document.body.dataset.tab!=="method")b.click();}});'
    'document.addEventListener("keydown",e=>{const d=dd.find(d=>d.open);'
    'if(e.key==="Escape"&&d){d.open=false;d.querySelector("summary").focus();}});'
    '})();</script>')


def site_nav(current=None):
    """The menu bar on every page: Map, Dashboard, then the deep dives (the
    themes by name, the lender profiles in a dropdown), then Methodology and
    Contact me (the author's LinkedIn), and on the map a coffee cup after
    it. As the window narrows the themes and
    lenders fold into one "Deep dives" dropdown, then everything but
    Methodology and Contact me into "Menu" (LMENU_CSS). The
    dropdowns are <details>, so they open without scripts; NAV_SCRIPT only
    keeps one open at a time and closes them on an outside click or Escape.

    `current` is the page being built: "map" or "dashboard" (the map's own
    Map and Methodology entries are buttons its script drives: #navmap and
    #methodtop), or the slug of a deep dive, which is marked aria-current
    and named on its dropdown. On the map and the dashboard every deep dive
    opens in a new tab, so the reader's filters stay where they were, and
    the panels say so; elsewhere links open in the same tab. Links are
    absolute, so they also work from an artifact; wrap_document makes them
    relative for the Pages build."""
    esc = lambda x: html.escape(x, quote=True)
    app = _is_app(current)
    themes, single, blocs = _deep_pages()
    tab = ' target="_blank" rel="noopener"' if app else ""
    tip = " (opens in a new tab)" if app else ""

    def deep(slug, title):
        cur = ' aria-current="page"' if slug == current else ""
        return f'href="{site_url(slug + "/")}"{tab}{cur} title="{esc(title + tip)}"'

    def item(d):
        return (f'<a class="lm-item" {deep(d["slug"], d["title"])}>'
                f'<span class="lm-badge">{esc(d["badge"])}</span><span>{esc(d["name"])}</span></a>')

    def here(key):
        return ' aria-current="page"' if key == current else ""

    lenders = f'<span class="lm-gl">Lenders, one by one</span><div class="lm-grid">{"".join(map(item, single))}</div>'
    if blocs:
        lenders += f'<span class="lm-gl">Groups of lending countries</span><div class="lm-grid">{"".join(map(item, blocs))}</div>'
    note = f'<p class="lm-tab">{DEEP_ICON}Each one opens in a new tab; the map keeps your filters.</p>' if app else ""
    cards = ('<span class="lm-gl">Themes</span><div class="lm-themes">' + "".join(
        f'<a class="lm-theme" {deep(slug, t)}><b>{esc(t)}</b><span>{esc(sub)}</span></a>'
        for slug, t, sub in themes) + "</div>") if themes else ""
    lender_here = next((d["name"] for d in DONORS if d["slug"] == current), "")
    theme_here = next((DEEP_SHORT.get(slug, t) for slug, t, _ in themes if slug == current), "")
    named = lambda s: f' <span class="sn-cur">· {esc(s)}</span>' if s else ""
    cur_cls = lambda on: " cur" if on else ""

    map_title = "The map: every record, filtered and zoomable"
    dash_title = "The dashboard: the same records as charts and a table"
    if current == "map":
        map_link = f'<button class="sn-a sn-x" id="navmap" type="button" aria-current="page" title="{map_title}">Map</button>'
    else:
        map_link = f'<a class="sn-a sn-x" href="{SITE_URL}" title="{map_title}">Map</a>'
    dash_link = f'<a class="sn-a sn-x" href="{site_url("dashboard.html")}"{here("dashboard")} title="{dash_title}">Dashboard</a>'
    meth_title = "Methodology: where the data comes from and how it is aligned"
    if current == "map":
        meth = (f'<button class="sn-a sn-meth" id="methodtop" type="button" aria-pressed="false" title="{meth_title}" '
                f'aria-label="Methodology"><span class="sn-ico">{BOOK_ICON}</span><span class="sn-l">Methodology</span></button>')
    else:
        meth = (f'<a class="sn-a sn-meth" href="{site_url("#t=m")}" title="{meth_title}" aria-label="Methodology">'
                f'<span class="sn-ico">{BOOK_ICON}</span><span class="sn-l">Methodology</span></a>')
    site_row = (f'<div class="lm-site"><a class="lm-item" href="{SITE_URL}"{here("map")}>Map</a>'
                f'<a class="lm-item" href="{site_url("dashboard.html")}"{here("dashboard")}>Dashboard</a></div>')

    bar = [map_link, dash_link]
    if themes or single:
        bar.append('<span class="sn-sep sn-x" aria-hidden="true"></span>')
        bar.append('<span class="sn-k sn-x sn-t" aria-hidden="true">Deep dives</span>')
        bar += [f'<a class="sn-a sn-x sn-t" {deep(slug, t)}>{esc(DEEP_SHORT.get(slug, t))}</a>' for slug, t, _ in themes]
        if single:
            bar.append(
                f'<details class="sn-dd sn-x sn-t{cur_cls(lender_here)}" name="snav">'
                f'<summary class="sn-a" title="Lender profiles: one page per lending country or group">'
                f'Lender profiles{CARET}</summary>'
                '<nav class="lm-panel" aria-label="Lender profiles"><p class="lm-h"><b>Lender profiles</b>One page per '
                f'lending country or group: what {REGION.name} owes it, what it lends and gives, and what it builds.</p>'
                f'{note}{lenders}</nav></details>')
    if themes or single:
        bar.append(
            f'<details class="sn-dd sn-more{cur_cls(lender_here or theme_here)}" name="snav">'
            f'<summary class="sn-a" title="Deep dives: reading pages on one theme or one lender, beyond the map">'
            f'<span class="sn-ms">{MENU_ICON}Menu</span><span class="sn-ml">Deep dives{named(lender_here or theme_here)}</span>'
            f'{CARET}</summary>'
            f'<nav class="lm-panel" aria-label="Site and deep dives">{site_row}'
            '<p class="lm-h"><b>Deep dives</b>Reading pages on one theme or one lender, each with its own data, '
            f'beyond what the map\'s filters show.</p>{note}{cards}{lenders if single else ""}</nav></details>')
    else:
        # an edition with no deep dives yet: the folded menu holds the site's two pages, and says so
        bar.append(
            '<details class="sn-dd sn-more" name="snav">'
            '<summary class="sn-a" title="Menu: the map and the dashboard">'
            f'<span class="sn-ms">{MENU_ICON}Menu</span><span class="sn-ml">Menu</span>{CARET}</summary>'
            f'<nav class="lm-panel" aria-label="Site">{site_row}</nav></details>')
    bar.append('<span class="sn-sep sn-x" aria-hidden="true"></span>')
    bar.append(meth)
    bar.append(f'<a class="sn-a sn-contact" href="{AUTHOR_URL}" target="_blank" rel="noopener noreferrer" '
               f'title="Contact {esc(AUTHOR_NAME)} on LinkedIn (opens in a new tab)" '
               f'aria-label="Contact me on LinkedIn (opens in a new tab)">{LINKEDIN_ICON}<span class="sn-l">Contact me</span></a>')
    if current == "map":
        # the home's support cup sits in the bar beside Contact me; the other pages keep their own coffee button
        bar.append(f'<a class="sn-a sn-coffee" href="{COFFEE_URL}" target="_blank" rel="noopener noreferrer" '
                   'title="Buy me a coffee: support this project" '
                   f'aria-label="Buy me a coffee (opens in a new tab)">{COFFEE_ICON}</a>')
    return (f'<nav class="snav{" sn-app" if app else ""}" aria-label="Site">' + "".join(bar) + "</nav>" + NAV_SCRIPT)


def site_footer(current=None):
    """The footer on every page, four columns that reflow on their own width
    (a container query), so the same markup sits under a reading page, under
    the dashboard and at the foot of the map's rail: the site and its
    author, Explore (map, dashboard, methodology), the theme deep dives and
    the lender profiles, each with a line on what it holds. It lists exactly
    the pages the menu bar lists (_deep_pages) and opens them the same way:
    in a new tab from the map and the dashboard, in place elsewhere.
    Templates own the <footer> element and anything page-specific (the
    page's data file, the build date) under this. The coffee button reuses
    the .coffee look every template already defines; the LinkedIn one is
    styled here (.sf-li)."""
    esc = lambda x: html.escape(x, quote=True)
    app = _is_app(current)
    themes, single, blocs = _deep_pages()
    tab = ' target="_blank" rel="noopener"' if app else ""
    ext = ' target="_blank" rel="noopener noreferrer"'

    def here(key):
        return ' aria-current="page"' if key == current else ""

    def li(href, label, sub="", key=None, attrs=""):
        small = f"<small>{esc(sub)}</small>" if sub else ""
        return f'<li><a href="{href}"{attrs}{here(key)}>{esc(label)}</a>{small}</li>'

    meth = ' data-method' if current == "map" else ""
    explore = (li(SITE_URL, "Map", "Every record, filtered and zoomable", "map")
               + li(site_url("dashboard.html"), "Dashboard", "The same records as charts and a table", "dashboard")
               + li(site_url("#t=m"), "Methodology", "Where the data comes from, and its limits", attrs=meth))
    cols = [
        '<div class="sf-brand">'
        f'<a class="sf-home" href="{SITE_URL}">{LOGO_MARK}<span><span class="kicker">{esc(REGION.kicker)}</span>'
        f'<b>{SITE_WORDMARK}</b></span></a>'
        f'<p class="sf-about">What is being built across {esc(REGION.name)}, and who is paying for it: power plants, '
        "lenders' projects, works on the ground, pipelines and cables from public data, with deep dives "
        'by theme and by lender.</p>'
        f'<p class="sf-made">Made with <span class="heart" aria-hidden="true">♥</span> by '
        f'<a href="{WEB_URL}"{ext}>{esc(AUTHOR_NAME)}</a>.</p>'
        f'<div class="sf-cta"><a class="coffee sf-b" href="{COFFEE_URL}"{ext} '
        'aria-label="Buy me a coffee (opens in a new tab)" title="Support this project">'
        f'{COFFEE_ICON}<span>Buy me a coffee</span></a>'
        f'<a class="sf-li sf-b" href="{AUTHOR_URL}"{ext} aria-label="{esc(AUTHOR_NAME)} on LinkedIn (opens in a new tab)" '
        f'title="Connect on LinkedIn">{LINKEDIN_ICON}<span>LinkedIn</span></a></div></div>',
        f'<nav class="sf-col" aria-label="Explore"><p class="sf-h">Explore</p><ul class="sf-list">{explore}</ul></nav>',
    ]
    if themes:
        cols.append('<nav class="sf-col" aria-label="Deep dives by theme"><p class="sf-h">Deep dives</p><ul class="sf-list">'
                    + "".join(li(site_url(slug + "/"), t, sub, slug, tab) for slug, t, sub in themes) + "</ul></nav>")
    if single:
        lend = ('<nav class="sf-col" aria-label="Lender profiles"><p class="sf-h">Lender profiles</p><ul class="sf-list two">'
                + "".join(li(site_url(d["slug"] + "/"), d["name"], key=d["slug"], attrs=tab) for d in single) + "</ul>")
        if blocs:
            lend += ('<p class="sf-h2">Groups of countries</p><ul class="sf-list two">'
                     + "".join(li(site_url(d["slug"] + "/"), d["name"], key=d["slug"], attrs=tab) for d in blocs) + "</ul>")
        cols.append(lend + "</nav>")
    return '<div class="sf"><div class="sf-grid">' + "".join(cols) + "</div></div>"


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


def china_span(meta=None):
    """AidData's commitment years and constant-dollar base year, from meta.json:
    (2000, 2023, 2023) for CLG 1.0. Every page that states them reads them here."""
    ch = ((load_meta() if meta is None else meta).get("china") or {})
    y0, y1 = (ch.get("years") or [2000, 2023])[:2]
    return y0, y1, ch.get("base_year") or 2023


def sources(meta, keys=MAP_LAYERS):
    a, f, g = meta.get("assets", {}), meta.get("finance", {}), meta.get("ground", {})
    p, c, w = meta.get("pipelines", {}), meta.get("cables", {}), meta.get("finance_wb", {})
    ch, eu, pm = meta.get("china", {}), meta.get("eu", {}), meta.get("mattei", {})
    fa, fz = meta.get("finance_afd", {}), meta.get("finance_bmz", {})
    rows = [
        {"k": "assets", **SOURCE_INFO["assets"],
         "detail": f"Global Integrated Power Tracker, release {a.get('release', 'unknown')}",
         "fresh": a.get("fresh") or fmt_date(a.get("fetched"))},
        {"k": "finance", **SOURCE_INFO["finance"],
         "detail": f"IATI 2.03 activity files, {f.get('datasets', '?')} datasets "
                   + ("(country, multinational and non-sovereign files)" if REGION.bank["publisher"] == "afdb"
                      else "(one per borrowing country, and a regional one)"),
         "fresh": f.get("fresh") or fmt_date(f.get("fetched"))},
        {"k": "finance_wb", **SOURCE_INFO["finance_wb"],
         "detail": f"IATI 2.03 activity files, {w.get('datasets', '?')} {REGION.adj} country and regional datasets",
         "fresh": w.get("fresh") or fmt_date(w.get("fetched"))},
        {"k": "finance_afd", **SOURCE_INFO["finance_afd"],
         "detail": f"IATI 2.03 activity files, {fa.get('datasets', '?')} {REGION.adj} country datasets "
                   "(the financings under each project)",
         "fresh": fa.get("fresh") or fmt_date(fa.get("fetched"))},
        {"k": "finance_bmz", **SOURCE_INFO["finance_bmz"],
         "detail": f"IATI 2.03 activity files, {fz.get('datasets', '?')} {REGION.adj} country datasets "
                   "(every project BMZ pays for, with the agency that carries it out: GIZ, KfW or another)",
         "fresh": fz.get("fresh") or fmt_date(fz.get("fetched"))},
        {"k": "ground", **SOURCE_INFO["ground"],
         "detail": "Overpass API, significant road/rail/air classes",
         "fresh": g.get("fresh") or fmt_date(g.get("fetched"))},
        {"k": "pipelines", **SOURCE_INFO["pipelines"],
         "detail": f"Global Gas and Global Oil Infrastructure Trackers, map files {p.get('release', 'unknown')}",
         "fresh": p.get("fresh") or fmt_date(p.get("fetched"))},
        {"k": "cables", **SOURCE_INFO["cables"],
         "detail": f"Submarine Cable Map, cables with {an(REGION.adj)} landing point",
         "fresh": c.get("fresh") or fmt_date(c.get("fetched"))},
        {"k": "china", **SOURCE_INFO["china"],
         "detail": f"{ch.get('release') or 'China’s Global Loans and Grants Dataset 1.0'}, "
                   f"official commitments to infrastructure {china_span(meta)[0]}–{china_span(meta)[1]}, "
                   "footprints from OpenStreetMap",
         "fresh": ch.get("fresh") or fmt_date(ch.get("fetched"))},
        {"k": "eu", **SOURCE_INFO["eu"],
         "detail": f"IATI 2.03 activity files of the European Commission ({'DG INTPA and DG NEAR' if 'ec-near' in REGION.eu_publishers else 'DG INTPA'}, "
                   f"{max((eu.get('datasets') or 1) - 1, 0)} {REGION.adj} country and regional datasets) "
                   "and the European Investment Bank's global file (IATI 2.02)",
         "fresh": eu.get("fresh") or fmt_date(eu.get("fetched"))},
        {"k": "mattei", **SOURCE_INFO["mattei"],
         "detail": "Piano Mattei per l'Africa project portal (Presidency of the Council of Ministers), "
                   "one page per project, read in its Italian and English versions",
         "fresh": pm.get("fresh") or fmt_date(pm.get("fetched"))},
    ]
    return [r for r in rows if r["k"] in keys]


def payload_meta(meta, keys=MAP_LAYERS):
    out = {"built": fmt_date(today()), "sdr_note": SDR_NOTE, "eur_note": EUR_NOTE,
            "sources": sources(meta, keys), "repo": REPO_URL or None,
            # GEM segments that exist in the tracker but carry no route, so the
            # Methodology can say how much of the layer is not drawn
            "unrouted_pipelines": (meta.get("pipelines") or {}).get("unrouted"),
            # what the AidData fetch left out, so the Methodology can say so
            "china_left_out": {k: (meta.get("china") or {}).get(k)
                               for k in ("umbrella", "pledges", "not_infrastructure", "unlocated",
                                         "acquisitions", "commodity_backed", "commodity_backed_usd")},
            # the AidData release's span and constant-dollar base year, and the
            # records new in it, which have no published location yet
            "china_meta": {k: (meta.get("china") or {}).get(k) for k in ("years", "base_year", "new_records")},
            # how the EU fetch assembled its records, so the Methodology can say so
            "eu_meta": {k: (meta.get("eu") or {}).get(k)
                        for k in ("contracts", "decisions", "decisions_folded", "eib",
                                  "named_place", "country_point", "regional", "unplaced",
                                  "envelopes_dropped", "eib_left_out", "eib_other_funder", "generated")},
            # what the IATI fetch left out of the two banks, so the Methodology can say so
            "finance_meta": {"afdb_budget_support": (meta.get("finance") or {}).get("budget_support"),
                             "wb_budget_support": (meta.get("finance_wb") or {}).get("budget_support"),
                             **({f"afd_{k}": (meta.get("finance_afd") or {}).get(k)
                                 for k in ("budget_support", "office_points", "at_office", "place_given")}
                                if "finance_afd" in keys else {}),
                             **({f"bmz_{k}": (meta.get("finance_bmz") or {}).get(k)
                                 for k in ("budget_support", "at_capital", "n_giz", "n_kfw", "n_bmz")}
                                if "finance_bmz" in keys else {})},
            "cables_meta": {k: (meta.get("cables") or {}).get(k)
                            for k in ("landing_points", "landing_sites", "length_estimated")},
            "pipes_meta": {k: (meta.get("pipelines") or {}).get(k)
                           for k in ("length_fixes", "route_drops")},
            # how the Piano Mattei fetch placed its records, so the Methodology can say so
            "mattei_meta": {k: (meta.get("mattei") or {}).get(k)
                            for k in ("stages", "named_place", "named_area", "country_point",
                                      "multi_country", "with_amount", "partner_countries")}}
    # the words, frame and lenders of this edition (DATA.region in the
    # templates); Africa's values are the templates' defaults, so its payload
    # carries none and is unchanged
    if REGION.key != "africa":
        out["region"] = region_payload()
    return out


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


def regionalize(page):
    """Fill a template's region markers. Blocks between <!--__IF:cond__--> and
    <!--__ENDIF__--> (or /*__IF:cond__*/ … /*__ENDIF__*/ inside scripts and
    styles) stay when `cond` holds and go otherwise; `cond` is a region key
    ("africa", "sea"), a layer the region has ("mattei"), "debt" for the
    dashboard's debt box, or any of these negated with "!". Then the word
    markers: __REGION__ (Africa), __REGION_ADJ__ (African), __KICKER__,
    __BANK__ (AfDB), __BANK_NAME__, __REGIONAL__ ("Africa, regional"),
    __LANDINGS__ ("African landings"), __WIDE__ ("Africa-wide") and
    __EU_WHERE__ ("in Chad"). Blocks are not nested."""
    def holds(cond):
        neg = cond.startswith("!")
        c = cond.lstrip("!")
        ok = c == REGION.key or c in REGION.layers or (c == "debt" and REGION.debt)
        return ok != neg

    def block(m):
        return m.group(2) if holds(m.group(1)) else ""
    page = re.sub(r"<!--__IF:([!\w]+)__-->(.*?)<!--__ENDIF__-->", block, page, flags=re.S)
    page = re.sub(r"/\*__IF:([!\w]+)__\*/(.*?)/\*__ENDIF__\*/", block, page, flags=re.S)
    for marker, word in (("__REGION_ADJ__", REGION.adj), ("__REGIONAL__", REGION.regional_label),
                         ("__REGION__", REGION.name), ("__KICKER__", REGION.kicker),
                         ("__BANK_NAME__", BANK_NAME), ("__BANK__", BANK),
                         ("__LANDINGS__", REGION.landings_label), ("__WIDE__", REGION.wide),
                         ("__EU_WHERE__", REGION.eu_point_where), ("__LAND__", REGION.land), ("__WHOLE__", REGION.whole),
                         ("__N_LAYERS__", NUM_WORD.get(len(REGION.layers), str(len(REGION.layers)))),
                         ("__N_DATASETS__", NUM_WORD.get(len(MAP_LAYERS) + 1, str(len(MAP_LAYERS) + 1)))):
        page = page.replace(marker, word)
    return page


def brand_assets(page, donor=None, here=None):
    """Fill the brand markers a template carries: the inline favicon link in
    its head, the header mark next to each <h1>, the mark's home link, the
    menu bar (<!--__NAV__-->), the footer (<!--__FOOTER__-->) and, where the
    template asks for them, the data-source logos.
    The home link is the absolute site URL so it also works from an artifact;
    wrap_document makes it relative for the Pages build. `donor` is the slug
    of the deep dive being built and `here` is "map" or "dashboard", so the
    menu bar and the footer mark the current page."""
    for marker in ("<!--__FAVICON__-->", "<!--__LOGO__-->", "__HOME_URL__", "<!--__NAV__-->", "<!--__FOOTER__-->"):
        if marker not in page:
            raise SystemExit(f"template missing the {marker} marker")
    current = donor or here
    return regionalize(page.replace("<!--__FAVICON__-->", f'<link rel="icon" href="{FAVICON}">')
                .replace("<!--__LOGO__-->", LOGO_MARK)
                .replace("<!--__NAV__-->", site_nav(current))
                .replace("<!--__FOOTER__-->", site_footer(current))
                .replace("/*__LMENU_CSS__*/", LMENU_CSS)
                .replace("/*__SOURCE_LOGOS__*/{}", json.dumps(SOURCE_LOGOS, ensure_ascii=False))
                .replace("__HOME_URL__", SITE_URL)
                .replace("__COFFEE_URL__", COFFEE_URL)
                .replace("__WHATSAPP_URL__", WHATSAPP_URL)
                .replace("__AUTHOR_URL__", AUTHOR_URL)
                .replace("__WEB_URL__", WEB_URL)
                .replace("__SITE_WORDMARK__", SITE_WORDMARK)
                .replace("__SITE_NAME__", SITE_NAME))


def site_url(path=""):
    return SITE_URL.rstrip("/") + "/" + path.lstrip("/")


# ------------------------------------------------------- what the site says

# The same facts feed the <meta description>, the JSON-LD, the <noscript>
# fallback, llms.txt and the sitemap, so search engines, link previews and
# language-model crawlers all read one story, with this snapshot's figures.

AFRICA_KEYWORDS = ["Africa infrastructure", "infrastructure projects Africa", "Africa power plants map",
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
SEA_KEYWORDS = ["Southeast Asia infrastructure", "infrastructure projects Southeast Asia", "ASEAN infrastructure map",
                "Southeast Asia power plants map", "Asian Development Bank projects", "ADB finance",
                "World Bank projects Southeast Asia", "construction Southeast Asia map",
                "energy Southeast Asia", "Global Energy Monitor", "OpenStreetMap construction",
                "oil and gas pipelines Southeast Asia", "submarine cables Southeast Asia", "TeleGeography",
                "Chinese investment Southeast Asia", "China ASEAN infrastructure", "AidData",
                "Chinese loans Southeast Asia", "Belt and Road Southeast Asia",
                "EU investment Southeast Asia", "Global Gateway Asia", "European Investment Bank Asia",
                "European Commission Southeast Asia infrastructure",
                "Indonesia infrastructure", "Vietnam infrastructure", "Philippines infrastructure",
                "open data Southeast Asia", "infrastructure investment Southeast Asia", "interactive map"]
KEYWORDS = {"africa": AFRICA_KEYWORDS, "sea": SEA_KEYWORDS}[REGION.key]

LICENSE_URL = {"CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
               "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
               "© TeleGeography (map CC BY-SA 4.0)": "https://www2.telegeography.com/cite-telegeography-map",
               "ODbL 1.0": "https://opendatacommons.org/licenses/odbl/1-0/",
               "ODC-By 1.0 (footprints ODbL)": "https://opendatacommons.org/licenses/by/1-0/",
               "CC BY 3.0 IT (gazetteer ODbL)": "https://creativecommons.org/licenses/by/3.0/it/",
               "Licence Ouverte / Open Licence": "https://www.etalab.gouv.fr/wp-content/uploads/2014/05/Licence_Ouverte.pdf"}

# layers drawn but not offered as a download (build_map.NOT_REDISTRIBUTED)
NO_DOWNLOAD = {"cables"}

LAYER_FILE = {"assets": "gem_power_assets.geojson", "finance": f"iati_{REGION.bank['publisher']}_finance.geojson",
              "finance_wb": "iati_worldbank_finance.geojson", "finance_afd": "iati_afd_finance.geojson",
              "finance_bmz": "iati_bmz_finance.geojson",
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
        n_afdb = sum(1 for r in f if r[fc.index("ln")] == BANK)
        n_wb = sum(1 for r in f if r[fc.index("ln")] == "WB")
        usd_wb = sum((r[fc.index("usd_m")] or 0) for r in f if r[fc.index("ln")] == "WB")
        n_afd = sum(1 for r in f if r[fc.index("ln")] == "AFD")
        usd_afd = sum((r[fc.index("usd_m")] or 0) for r in f if r[fc.index("ln")] == "AFD")
        n_bmz = sum(1 for r in f if r[fc.index("ln")] in BMZ_LENDERS)
        usd_bmz = sum((r[fc.index("usd_m")] or 0) for r in f if r[fc.index("ln")] in BMZ_LENDERS)
    else:
        n_afdb, n_wb, usd_wb = len(f), (meta.get("finance_wb") or {}).get("activities") or 0, 0
        n_afd, usd_afd = (meta.get("finance_afd") or {}).get("activities") or 0, 0
        n_bmz, usd_bmz = (meta.get("finance_bmz") or {}).get("activities") or 0, 0

    def count(layer, key):
        if layer is None:
            return (meta.get(key) or {}).get("records") or 0
        return len(_rows(layer)[0])

    # shares the crawler text states, computed rather than typed
    afdb = [r for r in f if "ln" in fc and r[fc.index("ln")] == BANK]
    afdb_approx = (100 * sum(1 for r in afdb if (r[fc.index("prec")] or 0) > 0) / len(afdb)) if afdb and "prec" in fc else None
    mrows, mcols = _rows(mattei) if mattei is not None else ([], [])
    m_edu = sum(1 for r in mrows if "Education" in (r[mcols.index("dirs")] or "")) if "dirs" in mcols else None
    crows, ccols = _rows(china) if china is not None else ([], [])
    china_country = (100 * sum(1 for r in crows if r[ccols.index("prec")] == 3) / len(crows)) if crows and "prec" in ccols else None

    def total(layer, col):
        if layer is None:
            return 0
        rows, cols = _rows(layer)
        return sum((r[cols.index(col)] or 0) for r in rows) if col in cols else 0

    return {"assets": len(a), "finance": n_afdb, "finance_wb": n_wb, "finance_afd": n_afd,
            "usd_bn_afd": usd_afd / 1000, "finance_bmz": n_bmz, "usd_bn_bmz": usd_bmz / 1000,
            "finance_total": len(f),
            "ground": len(g),
            "pipelines": count(pipelines, "pipelines"), "cables": count(cables, "cables"),
            "pipe_km": total(pipelines, "km"),
            "china": count(china, "china"), "china_usd_bn": total(china, "usd_m") / 1000,
            "eu": count(eu, "eu"), "eu_usd_bn": total(eu, "usd_m") / 1000,
            "mattei": count(mattei, "mattei"), "mattei_eur_bn": total(mattei, "eur_m") / 1000,
            "gw": mw / 1000, "usd_bn": usd / 1000, "usd_bn_wb": usd_wb / 1000,
            "afdb_approx_pct": afdb_approx, "mattei_edu": m_edu, "china_country_pct": china_country,
            "sources": sources(meta), "built": today(), "meta": meta}


def n_datasets(facts):
    """How many public datasets the edition draws on, as a word: one per
    source card, and the EU card is two (the Commission and the EIB)."""
    keys = {s["k"] for s in facts["sources"]}
    n = len(keys) + (1 if "eu" in keys else 0)
    return NUM_WORD.get(n, str(n))


def _pct(x):
    """A computed share as the crawler text states it: "42%", or "some" when unknown."""
    return f"{x:.0f}%" if isinstance(x, (int, float)) else "some"


def facts_sentence(facts):
    s = (f"{facts['assets']:,} power units tracked by Global Energy Monitor, "
         f"{facts['finance']:,} projects financed by the {BANK_NAME}")
    if facts.get("finance_wb"):
        s += (f", {facts['finance_wb']:,} by the World Bank" if facts.get("finance_afd")
              else f" and {facts['finance_wb']:,} by the World Bank")
    if facts.get("finance_afd"):
        s += (f", {facts['finance_afd']:,} financings by the Agence française de développement (AFD)"
              if facts.get("finance_bmz") else
              f" and {facts['finance_afd']:,} financings by the Agence française de développement (AFD)")
    if facts.get("finance_bmz"):
        s += (f" and {facts['finance_bmz']:,} projects paid for by Germany's development ministry (BMZ) "
              "and carried out by GIZ, KfW and others")
    s += f", {facts['ground']:,} construction works traced in OpenStreetMap"
    if facts.get("pipelines"):
        s += f", {facts['pipelines']:,} oil and gas pipeline segments from Global Energy Monitor"
    if facts.get("cables"):
        s += f" and {facts['cables']:,} submarine cables landing in {REGION.name} from TeleGeography"
    if facts.get("china"):
        s += (f", plus {facts['china']:,} infrastructure projects financed by Chinese official "
              f"lenders and agencies between {china_span(facts['meta'])[0]} and {china_span(facts['meta'])[1]}, from AidData")
    if facts.get("eu"):
        s += (f", and {facts['eu']:,} infrastructure projects financed by the European Union's "
              f"institutions, the European Commission and the European Investment Bank, via IATI")
    if facts.get("mattei"):
        s += (f", and the {facts['mattei']:,} projects of Italy's Piano Mattei per l'Africa as the "
              f"Italian Government's portal lists them")
    return s


def facts_totals(facts):
    parts = []
    # the regional bank's currency: the AfDB publishes in SDR, the ADB in dollars
    bank_rate = f"converted at {SDR_NOTE}" if REGION.bank["currency"] == "XDR" else "in US dollars as published"
    if facts["gw"]:
        parts.append(f"about {facts['gw']:,.0f} GW of generating capacity across all statuses")
    if facts["usd_bn"]:
        afd = facts.get("usd_bn_afd") or 0
        bmz = facts.get("usd_bn_bmz") or 0
        if facts.get("usd_bn_wb"):
            parts.append(f"USD {facts['usd_bn'] - facts['usd_bn_wb'] - afd - bmz:,.1f} billion of {BANK} commitments, "
                         f"{bank_rate}, " + ("" if afd else "and ")
                         + f"USD {facts['usd_bn_wb']:,.1f} billion of World Bank commitments"
                         + ((f", USD {afd:,.1f} billion of AFD commitments and USD {bmz:,.1f} billion of BMZ "
                             f"commitments, both converted at {EUR_NOTE}") if afd and bmz else
                            f" and USD {afd:,.1f} billion of AFD commitments, converted at {EUR_NOTE}" if afd else "")
                         + ", each the infrastructure share of the lender's own commitment, "
                         "budget support and cancelled projects left out")
        else:
            parts.append(f"USD {facts['usd_bn']:,.1f} billion of {BANK} commitments, {bank_rate}")
    if facts.get("china_usd_bn"):
        parts.append(f"USD {facts['china_usd_bn']:,.1f} billion of Chinese official commitments to "
                     f"infrastructure over {china_span(facts['meta'])[0]}–{china_span(facts['meta'])[1]}, "
                     f"in constant {china_span(facts['meta'])[2]} dollars as AidData publishes them")
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
                              f"ongoing infrastructure in {REGION.name}, compiled from open data.",
               "author": {"@id": person["@id"]}, "publisher": {"@id": person["@id"]}}
    place = {"@type": "Place", "name": REGION.name,
             "geo": {"@type": "GeoShape", "box": REGION.geo_box}}
    parts = []
    for src in facts["sources"]:
        k = src["k"]
        n = facts.get(k) or 0
        what = {"assets": f"Power generation units in {REGION.name} (announced, pre-construction, "
                          "under construction, operating, cancelled or shelved) with technology, "
                          "capacity in MW, owner and coordinates.",
                "finance": f"{BANK_NAME} projects from its IATI 2.03 activity files: "
                           "title, recipient country, status, DAC sector, commitment and "
                           "disbursement, and geocoded locations where published.",
                "finance_wb": f"World Bank infrastructure projects in {REGION.name} from its IATI 2.03 "
                              "activity files: title, recipient country or region, status, DAC "
                              "sector, commitment and disbursement in USD, and the Bank's geocoded "
                              "project locations with their location class.",
                "finance_afd": f"Infrastructure financings of the Agence française de développement in {REGION.name} "
                               "from its IATI 2.03 activity files: title, recipient country, status, DAC "
                               "sector, commitment and disbursement in EUR, and AFD's point where it is not "
                               "the agency's office (otherwise the country's centre).",
                "finance_bmz": f"Infrastructure projects in {REGION.name} paid for by Germany's Federal Ministry for "
                               "Economic Cooperation and Development (BMZ), from its IATI 2.03 activity files: "
                               "title, recipient country, the agency that carries the project out (GIZ, KfW or "
                               "another), status, DAC sector, commitment and disbursement in EUR, placed at the "
                               "country's centre (BMZ gives only the capital).",
                "ground": "Roads (motorway to secondary), railways and airports under "
                          f"construction or proposed in {REGION.name}, traced by OpenStreetMap mappers, "
                          "as line geometries with status, operator and opening date.",
                "pipelines": f"Oil, NGL and gas transmission pipelines with {an(REGION.adj)} country on "
                             "their route (proposed, under construction, operating, shelved or "
                             "cancelled), as route geometries with fuel, capacity, length, owner "
                             "and start year, from Global Energy Monitor's Global Gas and Global "
                             "Oil Infrastructure Trackers.",
                "cables": "Submarine telecommunications cables with at least one landing point "
                          f"in {REGION.name}, planned or in service, as route geometries with owners, "
                          f"suppliers, ready-for-service year, length and {REGION.adj} landing points, "
                          "from TeleGeography's Submarine Cable Map.",
                "china": f"Infrastructure projects in {REGION.name} supported by official financial "
                         f"commitments from China between {china_span(facts['meta'])[0]} and "
                         f"{china_span(facts['meta'])[1]} (loans and grants from "
                         "China Eximbank, China Development Bank, the Ministry of Commerce and "
                         "other official lenders), with status, sector, funder, implementer, "
                         f"commitment in constant {china_span(facts['meta'])[2]} USD, loan terms where known, and the "
                         "project's footprint traced in OpenStreetMap where AidData geocoded it, "
                         "from AidData's China's Global Loans and Grants Dataset 1.0, located with "
                         "its Global Chinese Development Finance Dataset 3.0 and that release's "
                         "Geospatial companion.",
                "eu": f"Infrastructure projects in {REGION.name} financed by the European Union's "
                      "institutions: the European Commission's contracts and financing decisions "
                      "(DG International Partnerships and DG Neighbourhood and Enlargement) and the "
                      "European Investment Bank's own loans and direct equity, from their IATI activity "
                      "files, with status, DAC or EIB sector, implementer, instrument, commitment "
                      "and disbursement in euros, and the location the publisher gives: a named "
                      f"place, the country's point or the Commission's {REGION.wide} point.",
                "mattei": "The projects of Italy's Piano Mattei per l'Africa (Mattei Plan) as the "
                          "Italian Government's project portal lists them: title, the plan's "
                          "pillar (energy, water, agriculture, health, education, infrastructure), "
                          "objective, countries, implementing body, partners, funding source, the "
                          "stated amount in euros and the portal's progress stage (identified, "
                          "formulated, approved, ongoing, completed), placed on the site the "
                          "description names, the country's point or, for a programme across "
                          "several countries, one Africa-wide point for the layer."}[k]
        d = {"@type": "Dataset", "@id": site_url(f"#dataset-{k}"),
             "name": f"{SITE_NAME}: {src['name']} layer",
             "description": f"{what} {n:,} records in this snapshot. {src['detail']}.",
             "url": SITE_URL, "isBasedOn": src["url"],
             "creator": {"@type": "Organization", "name": src["name"], "url": src["url"]},
             "spatialCoverage": place, "isAccessibleForFree": True,
             "dateModified": facts["meta"].get(k, {}).get("fetched") or facts["built"],
             "distribution": [] if k in NO_DOWNLOAD else
                             [{"@type": "DataDownload", "encodingFormat": "application/geo+json",
                               "contentUrl": site_url("data/" + LAYER_FILE[k])}]}
        if not d["distribution"]:
            del d["distribution"]
        if src["lic"] in LICENSE_URL:
            d["license"] = LICENSE_URL[src["lic"]]
        parts.append(d)
    dataset = {"@type": "Dataset", "@id": site_url("#dataset"),
               "name": f"{SITE_NAME}: infrastructure projects across {REGION.name}",
               "description": f"{n_datasets(facts).capitalize()} public datasets on infrastructure in {REGION.name}, kept as separate "
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
            {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": SITE_URL},
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
        + (f"<td><a href=\"{e(s['url'])}\">at the source</a></td></tr>" if s["k"] in NO_DOWNLOAD
           else f"<td><a href=\"data/{LAYER_FILE[s['k']]}\">GeoJSON</a></td></tr>")
        for s in facts["sources"])
    lede = ("This page is an interactive map" if kind == "map" else "This page is a dashboard, with charts and a table,")
    # the pieces that depend on the edition: its plan layer, its bank's conventions
    mattei_amounts = (", and the amounts Italy's\nPiano Mattei portal states for its projects, which may be a "
                      "whole project's value rather than\nItaly's share") if facts.get("mattei") else ""
    if BANK == "AfDB":
        bank_loc = (f"about {e(_pct(facts.get('afdb_approx_pct')))}\nof AfDB locations are approximate, a named town "
                    "or a country or region centroid, the World Bank marks every location approximate")
    else:
        bank_loc = (f"{BANK} marks every location approximate and names it, a province, a town or the country "
                    "itself, and the World Bank marks every location approximate too")
    no_loc = "the EIB and the\nPiano Mattei portal publish" if facts.get("mattei") else "the EIB publishes"
    return f"""<noscript>
<article style="max-width:72ch;margin:0 auto;padding:24px 16px;font:16px/1.5 Georgia,serif">
<h2>{e(SITE_NAME)}: announced, approved and ongoing infrastructure in {e(REGION.name)}</h2>
<p>{lede} of infrastructure projects across {e(REGION.name)}, built from {n_datasets(facts)} public datasets:
{e(facts_sentence(facts))}. Together they describe {e(facts_totals(facts))}.
The page needs JavaScript to draw; without it, this summary, the data files below
and {other} are what is here.</p>
<p>The sources share no project identifier, so they are kept as separate layers
and never added into one project cost: {an(BANK)}-financed power plant can legitimately appear in several.
Each source's own lifecycle is mapped onto five shared statuses: announced, approved,
under construction, operating and stalled.</p>
<table>
<caption>The layers in this snapshot</caption>
<thead><tr><th>Source</th><th>Dataset</th><th>Records</th><th>Licence</th><th>Data as of</th><th>Download</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p>Limits: money is two multilateral lenders, {BANK} and the World Bank, the European Union's
institutions (the Commission's contracts and the EIB's loans, as each publishes them to IATI),
Chinese official finance as AidData reconstructs it from public sources{mattei_amounts}; the Chinese layer ends with commitments made in {china_span(facts['meta'])[1]}, so totals are each lender's
exposure, kept on lines of their own, and not investment in {e(REGION.name)}; {bank_loc}, {no_loc} no locations at all, so their records sit on a place the record names
or at their country's point, and about {e(_pct(facts.get('china_country_pct')))} of the Chinese-financed
projects have no published location and sit at their country's centre; OpenStreetMap presence is mapper-driven,
so absence is not evidence; energy and connectivity are over-represented because no comparable
open project tracker exists for ports, water or electricity transmission.</p>
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
    alt = q(f"{title}: {REGION.name} with the atlas's records, power units, lenders' projects and "
            f"construction works, drawn in their status colours, and the site's title.")
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
<title>{q(SITE_NAME)}{": " + q(REGION.kicker) if title == SITE_NAME else " · " + t}</title>
<meta name="description" content="{d}">
<meta name="keywords" content="{q(", ".join(KEYWORDS))}">
<meta name="author" content="{q(AUTHOR_NAME)}">
<meta name="robots" content="{ROBOTS}">
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
            *([("corridors/", "monthly", "0.8"), ("data/corridors.json", "monthly", "0.3")] if (DOCS / "corridors" / "index.html").exists() else []),
            *[("data/donors/" + d["slug"] + ".json", "monthly", "0.3") for d in DONORS],
            ("llms.txt", "monthly", "0.3"),
            ("data/meta.json", "monthly", "0.2"), ("data/map.json", "monthly", "0.2")]
    urls += [("data/" + f, "monthly", "0.4") for k, f in LAYER_FILE.items() if k not in NO_DOWNLOAD]
    body = "".join(
        f"  <url><loc>{html.escape(site_url(p))}</loc><lastmod>{day}</lastmod>"
        f"<changefreq>{c}</changefreq><priority>{pr}</priority></url>\n" for p, c, pr in urls)
    shutil.copy(BRAND / "favicon.svg", DOCS / "favicon.svg")
    if DOCS != ROOT_DOCS:          # an edition in a folder of its own: the icons its pages link relatively
        for icon in ("icon-192.png", "apple-touch-icon.png"):
            if (ROOT_DOCS / icon).exists():
                shutil.copy(ROOT_DOCS / icon, DOCS / icon)
    (DOCS / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "</urlset>\n")

    donor_pages = "".join(
        f"- [{d['title']}]({site_url(d['slug'] + '/')}): {d['description']} "
        f"Data: {site_url('data/donors/' + d['slug'] + '.json')}\n" for d in DONORS)
    src_lines = "\n".join(
        f"- [{s['name']}]({s['url']}): {s['detail']}. {facts[s['k']]:,} records, data as of "
        f"{s['fresh']}, licence {s['lic']}. "
        + (f"Not offered as a download (the publisher's terms): see {s['url']}" if s["k"] in NO_DOWNLOAD
           else f"GeoJSON: {site_url('data/' + LAYER_FILE[s['k']])}")
        for s in facts["sources"])
    # the pieces of the text that depend on the edition: its plan layer, its
    # bank's conventions, the shapes of its basemap
    mattei = bool(facts.get("mattei"))
    mattei_plan = ", Piano Mattei Italy's plan" if mattei else ""
    mattei_approved = ', the Piano Mattei portal\'s "approved"' if mattei else ""
    mattei_status = ((" Piano Mattei: the portal's progress\n  stage, \"identified\" and \"formulated\" are announced, "
                      "\"approved\" is approved, \"ongoing\" is\n  under construction, \"completed\" is operating; "
                      "the portal has no cancelled stage.") if mattei else "")
    mattei_glyph = (", hexagons are Piano Mattei\n  projects sized by the amount the Italian Government's portal states"
                    if mattei else "")
    mattei_amounts = (("\n  Piano Mattei amounts are the figure the portal prints for each project, in euros as\n"
                       "  stated, converted at the same rate; the portal does not say whether a figure is Italy's\n"
                       "  share or the whole project's value, so they are shown on their own and never added to\n"
                       "  the lenders' commitments.") if mattei else "")
    mattei_not_added = ", and the Piano Mattei\n  figures are not added to any of them" if mattei else ""
    # AFD, France's development agency, the finance layer's third lender (Africa only)
    afd = bool(facts.get("finance_afd"))
    bmz = bool(facts.get("finance_bmz"))
    afd_glyph = (", crosses AFD financings" if afd else "") + (", inverted triangles BMZ projects" if bmz else "")
    afd_money = (" AFD, France's development agency, publishes in euros too, converted at the same\n"
                 "  rate; one AFD record is one financing (a loan or a grant) under a project, and its\n"
                 "  policy loans, which it files as project aid, are left out as budget support by their\n"
                 "  own words (\"financement budgétaire\", \"prêt de politique publique\").") if afd else ""
    afd_money += ("\n  Germany's development ministry BMZ publishes in euros too, converted at the same rate;\n"
                  "  one BMZ record is one project it pays for, under the agency that carries it out (GIZ,\n"
                  "  KfW, or an NGO, church or UN agency), and every one is placed at its country's centre,\n"
                  "  since BMZ gives only the capital, where the agreement is made.") if bmz else ""
    afd_limit = (", France's development agency AFD" if afd else "") + (", Germany's development ministry BMZ" if bmz else "")
    mattei_bullet = ((f"- The Piano Mattei layer is the Italian Government's own list of the plan's projects, all of\n"
                      f"  them, not an infrastructure subset: {facts.get('mattei_edu') or 'many'} of the {facts['mattei']:,} carry the\n"
                      "  education, training and culture pillar. Narrow by sector to keep the ones that build\n"
                      "  something. The portal publishes no coordinates: a record sits on the place its\n"
                      "  description names (coordinates from OpenStreetMap), on the country's point, or, for a\n"
                      "  programme across several countries, at one Africa-wide point for the whole layer (the\n"
                      "  mean of the plan's partner countries' points, in the Central African Republic), which is\n"
                      "  not a site.\n") if mattei else "")
    mattei_link = ("- [Piano Mattei per l'Africa, project portal of the Italian Government](https://www.governo.it/en/piano-mattei/progetti/)\n"
                   if mattei else "")
    if BANK == "AfDB":
        counterpart = "the\n  borrowing government's counterpart funds that the AfDB files beside its own, "
        bank_currency = (f"AfDB publishes in SDR, converted at a\n  fixed, stated rate: {SDR_NOTE}. "
                         "The World Bank publishes in USD, taken as is.")
        bank_loc = (f"- About {_pct(facts.get('afdb_approx_pct'))} of AfDB locations are approximate (a named town or a country or\n"
                    "  region centroid). The\n"
                    "  World Bank marks every location approximate and states its class: site, populated place\n"
                    "  or administrative region. The pages say which for each record.")
        unrouted = "about a third of GEM's African segments"
        borders = ("- Somaliland and Western Sahara are drawn as Natural Earth draws them, as separate\n"
                   "  polygons; that is the boundary dataset's choice, not a position taken here. Natural Earth\n"
                   "  follows the line of control: the part of Western Sahara that Morocco administers lies\n"
                   "  inside Morocco's shape, so works placed by their coordinates there count as Morocco, while\n"
                   "  power units follow Global Energy Monitor's own country field.\n")
    else:
        counterpart = ""
        bank_currency = f"{BANK} and the World Bank publish in USD, taken as is."
        bank_loc = (f"- {BANK} marks every location approximate (IATI exactness 2) and names it: a province, a town, or\n"
                    "  the country itself. A named one is drawn as a named place, the rest at the country's point. The\n"
                    "  World Bank marks every location approximate and states its class: site, populated place\n"
                    "  or administrative region. The pages say which for each record.")
        unrouted = f"the segments GEM lists for {REGION.name} without a route"
        borders = ""
    near = (", [DG Neighbourhood and Enlargement](https://d-portal.iatistandard.org/ctrack.html?publisher=XI-IATI-EC_NEAR#view=main)"
            if "ec-near" in REGION.eu_publishers else "")
    (DOCS / "llms.txt").write_text(f"""# {SITE_NAME}

> An interactive map and dashboard of announced, approved and ongoing infrastructure in
> {REGION.name}, for investors, researchers and journalists. Compiled from {n_datasets(facts)} public datasets:
> {facts_sentence(facts)}. Together they describe {facts_totals(facts)}.
> Snapshot built {fmt_date(day)}; data is refreshed by hand about twice a year.

Made by {AUTHOR_NAME} ({AUTHOR_URL}). Free to use; cite the underlying sources by name.
Site: {SITE_URL}

## Pages

- [{SITE_NAME}, map]({SITE_URL}): full-screen map of the {NUM_WORD[len(REGION.layers)]} layers (finance holds {'four' if bmz else 'three' if afd else 'two'} lenders, EU finance the Commission and the EIB{mattei_plan}) with filters
  by layer, status, country and sector, a viewport summary, a "largest in view" list, detail
  cards linking to each source record, optional marker clustering and Sentinel-2 satellite
  imagery, and a Methodology tab. The view is encoded in the URL hash, so views can be shared.
- [{SITE_NAME}, dashboard view]({site_url('dashboard.html')}): the same records as a page
  with KPIs, a country map, bar charts by country and sector, and a sortable table.
{donor_pages}{"- [Debt: who African governments owe, creditor by creditor](" + site_url("debt/") + "): World Bank International Debt Statistics by creditor, with a card on the dashboard. Data: " + site_url("data/debt.json") + chr(10) if (DOCS / "debt" / "index.html").exists() else ""}{"- [Compare the lenders](" + site_url("compare/") + "): the seven lender profiles side by side, with filters by lender, region or country, year and measure: where each one's money goes (small-multiple maps and a who-leads-where map), what it funds (sector mix), how it is lent (grants, loans, delivery channels, concentration) and how its exposure moved since 2000. Data: " + site_url("data/compare.json") + chr(10) if (DOCS / "compare" / "index.html").exists() else ""}{"- [Africa's strategic corridors](" + site_url("corridors/") + "): a hand-kept register of Africa's main cross-border transport and energy corridors (LAPSSET, Lobito, TAZARA, the standard gauge railways, EACOP, the Saharan and Atlantic gas pipelines and others), on one map, piece by piece, with each piece's stage and who lends for, owns and builds it, every line sourced. Data: " + site_url("data/corridors.json") + chr(10) if (DOCS / "corridors" / "index.html").exists() else ""}
## Data

The compiled payload the map draws, one JSON with column-wise layers:
{site_url('data/map.json')}. Fetch dates, release names and record counts:
{site_url('data/meta.json')}. The raw layers as GeoJSON:

{src_lines}

Country outlines are Natural Earth (1:10m on the map, 1:110m on the dashboard). The
satellite layer is EOX Sentinel-2 cloudless (CC BY-NC-SA), site build only, off by default.

## How to read it

- The sources share no project identifier. They are separate layers, never added into one
  project cost: {an(BANK)}-financed power plant can legitimately appear in several.
- Two maps, each with its own filters: Built, for the works, and Financed, for the lenders'
  records of their loans and grants.
- Two sets of words for the same five steps: a status for the works (announced, approved,
  under construction, operating, stalled) and a stage for a lender's record (pipeline,
  committed, disbursing, closed, cancelled). Closed means the money was spent, not that
  the works run.
- Five shared statuses. Announced: GEM announced, IATI status 1, OSM proposed. Approved:
  GEM pre-construction (permits, land or finance still being sought), {an(BANK)} activity still
  at IATI status 1 whose commitment is on record (past board approval), AidData
  "Pipeline: Commitment"{mattei_approved}. Under construction: GEM
  construction, IATI status 2, OSM construction. Operating: GEM operating, IATI 3-4.
  Stalled: GEM cancelled/shelved/mothballed, IATI 5-6. Pipelines: GEM proposed is
  announced, construction, operating, shelved/cancelled as stalled. Submarine cables:
  TeleGeography "in service" is operating; "planned" is under construction when the
  ready-for-service year is no later than the year after the snapshot, otherwise announced. Chinese
  finance (AidData): "Pipeline: Commitment" is approved, "Implementation" is under
  construction, "Completion" is operating, "Suspended" and "Cancelled" are stalled; pledges
  (MoUs, letters of intent), umbrella agreements and loans that buy a stake are left out,
  so the layer has no announced records and no double-counted money. EU finance: IATI statuses as for {BANK}
  (1 announced, 2 under construction, 3-4 operating, 5-6 stalled); a Commission financing
  decision still in the pipeline is an announced record.{mattei_status}
- Shape is source, colour is status, size is scale: circles are power units sized by MW,
  squares are {BANK} projects and diamonds World Bank projects{afd_glyph}, {'all' if afd else 'both'} sized by commitment, thin lines are construction ways as
  traced, haloed lines are pipeline routes, lines ending in dots are submarine cables
  with their {REGION.adj} landing points, triangles are Chinese-financed projects sized by
  commitment, with the project's OpenStreetMap footprint drawn as a thin outline where
  AidData geocoded it precisely, stars are EU-financed records (European Commission
  contracts and decisions, EIB operations) sized by commitment{mattei_glyph}. Dashed lines are not yet built.
- Amounts are commitments (IATI transaction type 2), counted as the infrastructure share of
  the lender's own commitment by its own sector percentages (and, for the EIB, the {REGION.adj}
  share by its recipient percentages). Left out: budget support (IATI aid-type A01/A02), {counterpart}EIB fund
  investments and credit lines, EIB operations funded by the Commission or a member state,
  and the money of cancelled or suspended records, which stay on the map. Cards show the
  lender's own figure beside the counted one. {bank_currency} AidData's
  Chinese commitments are in constant {china_span(facts['meta'])[2]} US dollars, as published, and are never added to
  the IATI figures. The EU institutions publish in euros, converted at a fixed, stated rate:
  {EUR_NOTE}; a Commission contract carries the contracted amount, a financing decision with
  no contract yet its whole envelope, once however many country copies repeat it, an EIB
  operation the signed amount (the Bank's file repeats each commitment transaction per
  tranche record; the distinct ones are summed).{afd_money}{mattei_amounts}

## Limits

- Money is two multilateral lenders, {BANK} and the World Bank{afd_limit}, the European Union's
  institutions (the Commission and the EIB, each publishing its own share to IATI), plus
  Chinese official finance as AidData reconstructs it from public sources. Private,
  domestic-budget, {'other ' if afd else ''}EU member states' bilateral and other-lender finance is not here. Read
  totals as each lender's exposure, not as investment in {REGION.name}. Each lender's total is
  shown on its own line and never added into one project cost{mattei_not_added}.
{mattei_bullet}- The EU layer is the Commission's contracts (one record per grant, delegation agreement or
  works contract under a financing decision; a decision is a record only when none of its
  contracts is published yet) and the EIB's operations. The Commission's points are either
  a named place or the country's default point; the EIB publishes no locations, so its
  records sit at the country's point; {REGION.wide} programmes sit at the Commission's
  regional point, {REGION.eu_point_where}.
- The Chinese layer is AidData's China's Global Loans and Grants Dataset 1.0 (November 2025):
  commitments made {china_span(facts['meta'])[0]}-{china_span(facts['meta'])[1]} and their implementation to 2025. CLG 1.0 publishes no
  locations; records it carries over from AidData's GCDF 3.0 keep that release's location and
  footprint, and the {(facts['meta'].get('china') or {}).get('new_records') or 0:,} records new in CLG 1.0 sit at their country's centre. It says
  where Chinese money went, not what China is financing now. Only projects AidData flags as
  physical infrastructure are kept, which includes infrastructure loans secured on oil or
  mineral exports; about {_pct(facts.get('china_country_pct'))} have no published location and sit at their country's centre.
{bank_loc}
- OpenStreetMap presence is mapper-driven: absence of a road is not evidence that none is
  being built. The layer is filtered to motorway-to-secondary roads, rail and airports.
- Energy and connectivity are over-represented: no comparable open project tracker exists for
  ports, water or electricity transmission. Pipeline segments without a usable route
  ({unrouted}) are not drawn.
{borders}
## Optional

- [Global Energy Monitor, Global Integrated Power Tracker](https://globalenergymonitor.org/projects/global-integrated-power-tracker/)
- [{BANK_NAME} on d-portal, IATI's data explorer]({REGION.bank['registry']})
- [European Commission, DG International Partnerships](https://d-portal.iatistandard.org/ctrack.html?publisher=XI-IATI-EC_INTPA#view=main){near} and the [European Investment Bank](https://d-portal.iatistandard.org/ctrack.html?publisher=XM-DAC-918-3#view=main) on d-portal
{mattei_link}- [AidData, Global Chinese Development Finance Dataset 3.0](https://www.aiddata.org/data/aiddatas-global-chinese-development-finance-dataset-version-3-0) and its [geospatial companion on GitHub](https://github.com/aiddata/gcdf-geospatial-data)
- [OpenStreetMap copyright and licence](https://www.openstreetmap.org/copyright)
- [Natural Earth](https://www.naturalearthdata.com/)
""")
