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
}


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


def sources(meta):
    a, f, g = meta.get("assets", {}), meta.get("finance", {}), meta.get("ground", {})
    return [
        {"k": "assets", **SOURCE_INFO["assets"],
         "detail": f"Global Integrated Power Tracker, release {a.get('release', 'unknown')}",
         "fresh": a.get("fresh") or fmt_date(a.get("fetched"))},
        {"k": "finance", **SOURCE_INFO["finance"],
         "detail": f"IATI 2.03 activity files, {f.get('datasets', '?')} country datasets",
         "fresh": f.get("fresh") or fmt_date(f.get("fetched"))},
        {"k": "ground", **SOURCE_INFO["ground"],
         "detail": "Overpass API, significant road/rail/air classes",
         "fresh": g.get("fresh") or fmt_date(g.get("fetched"))},
    ]


def payload_meta(meta):
    return {"built": fmt_date(today()), "sdr_note": SDR_NOTE,
            "sources": sources(meta), "repo": REPO_URL or None}


# ------------------------------------------------------------ HTML document

BRAND = ROOT / "brand"

# The mark (brand/option-a-cutout-rose.svg, "option A"): the continent traced from
# data/africa_basemap.json with a compass rose cut out. brand/logos.py generates
# the two derived files used here; edit there, not in the templates.
FAVICON = "data:image/svg+xml," + urllib.parse.quote((BRAND / "favicon.svg").read_text().strip())
LOGO_MARK = re.sub(r"<svg ", '<svg class="mark" aria-hidden="true" focusable="false" ',
                   (BRAND / "mark.svg").read_text().strip(), count=1)


def brand_assets(page):
    """Fill the two brand markers a template carries: the inline favicon link
    in its head and the header mark next to each <h1>."""
    for marker in ("<!--__FAVICON__-->", "<!--__LOGO__-->"):
        if marker not in page:
            raise SystemExit(f"template missing the {marker} marker")
    return (page.replace("<!--__FAVICON__-->", f'<link rel="icon" href="{FAVICON}">')
                .replace("<!--__LOGO__-->", LOGO_MARK))


def wrap_document(fragment, *, title, description, path="", host="pages", extra_head=""):
    """Artifact fragments carry their own <meta>/<title>/<link>/<style> at the
    top and page markup after; the publishing sandbox wraps them. GitHub Pages
    serves files as-is, so wrap them here into a complete document, moving the
    stylesheet and fonts into <head> where they belong."""
    frag = re.sub(r'<meta charset="utf-8">\s*', "", fragment)
    frag = re.sub(r'<meta name="viewport"[^>]*>\s*', "", frag)
    frag = re.sub(r"<title>.*?</title>\s*", "", frag, count=1, flags=re.S)
    cut = frag.index("</style>") + len("</style>")
    head_part, body_part = frag[:cut], frag[cut:]
    t, d = html.escape(title, quote=True), html.escape(description, quote=True)
    url = html.escape(SITE_URL.rstrip("/") + "/" + path.lstrip("/"), quote=True)
    return f"""<!doctype html>
<html lang="en" data-host="{host}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t}</title>
<meta name="description" content="{d}">
<meta name="theme-color" content="#1F5F4B">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
{head_part.strip()}
{extra_head}</head>
<body>
{body_part.strip()}
</body>
</html>
"""
