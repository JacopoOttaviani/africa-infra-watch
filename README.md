# africa-infra-watch

An interactive map and dashboard of announced, approved and ongoing infrastructure
in Africa, for investors, researchers and journalists.

**Interactive map:** https://claude.ai/code/artifact/ba74ed91-3123-4fe5-9f01-43708f368104
**Dashboard:** https://claude.ai/code/artifact/e4229926-b67c-4c7b-ac4a-5b21b03b83fa
**Dataset evaluation:** https://claude.ai/code/artifact/db7c4c37-e62c-4b0f-89e3-ccaa35eb184c

**Live site:** https://jacopoottaviani.com/africa-infra-watch/ (map) and
[…/dashboard.html](https://jacopoottaviani.com/africa-infra-watch/dashboard.html) —
the same two pages, served by GitHub Pages from `docs/`. Data is refreshed by
hand about twice a year; the header of each page says when.

The map is the map-first view: a full-screen Web Mercator canvas over a Natural
Earth 1:10m basemap (the whole world's coastlines and borders, with provinces,
rivers, lakes and cities around Africa), with
the six data layers drawn as circles (power units, sized by MW), squares and
diamonds (AfDB and World Bank projects, sized by commitment), triangles
(Chinese-financed projects from AidData, 2000–2021, sized by commitment, with
the works' OpenStreetMap footprint outlined from country zoom in), thin lines
(construction ways traced in OpenStreetMap), haloed lines (oil and gas pipeline
routes) and lines ending in dots (submarine cables, dots at their African
landing points). Filters, a viewport summary, a "largest in view" list, per-record
detail cards linking back to the source record, and a shareable URL hash. A
**Cluster markers** toggle (on by default; `cl=0` in the hash turns it off) regroups the records that pass
the filters into donuts, sized by count and sliced by status (pipelines and
submarine cables stay drawn as lines), using
Leaflet.markercluster over the same projection (libraries in `vendor/`, inlined
at build time). A **Satellite** toggle (`sat=1`), site build only, draws EOX's
Sentinel-2 cloudless 2025 mosaic (10 m, CC BY-NC-SA) under the borders, labels
and records; off by default. The provider is one config block in the template
(`SAT_SRC`). A
**Methodology** tab (also reachable with `t=m` in the hash) documents each
source's origin, access route, unit of observation, filters, status mapping,
what it can and cannot answer, the drawing rules and the counting rules; its
figures are computed from the same payload the map draws, so they cannot drift.
The dashboard is the page-first view of the same data, in the same frame: the
map's left rail (brand, lede, data-as-of line, view tabs, search, Layers, Status,
Narrow, and a Selection panel in place of the map's lists) beside a scrolling
column of KPIs, a smaller equirectangular map of all six layers over Natural
Earth 1:110m, charts by country and sector, and a sortable table. The rail
becomes a drawer below 880 px on both pages. Pipeline and cable routes are
thinned harder for the dashboard and clipped to a window around its frame at
build time (`LINE_WINDOW` in `build_dashboard.py`), so a cable to India is drawn
only where it runs around the continent; the record builders themselves are
shared with the map. Both pages use one status palette.

## Sources

Seven open datasets in six layers, deliberately kept apart because they share no
project identifier. Summing across them double-counts. Both pages show the same
six layers over the same records; the finance layer holds both lenders on each,
drawn as squares (AfDB) and diamonds (World Bank).

| Layer | Source | Records | Answers |
|---|---|---|---|
| Assets | Global Energy Monitor, Global Integrated Power Tracker | 4,274 power units | what asset is being built |
| Finance | African Development Bank, IATI 2.03 activity files | 1,767 projects | who is paying, and how much |
| Finance | World Bank, IATI 2.03 activity files (50 African country files + 2 regional) | 1,123 projects | the same, for the other big multilateral lender |
| Ground truth | OpenStreetMap via Overpass | 3,586 works | what has physically broken ground |
| Pipelines | Global Energy Monitor, Global Gas + Global Oil Infrastructure Trackers | 324 routed segments | where oil, NGL and gas move, or are meant to |
| Cables | TeleGeography, Submarine Cable Map | 81 cables | where the continent's bandwidth comes ashore, owned by whom, due when |
| Chinese finance | AidData, Global Chinese Development Finance Dataset 3.0 + Geospatial GCDF 3.0 | 2,324 projects | what Chinese official lenders committed to infrastructure 2000–2021, where, on what terms, what got built |

The two line layers and the World Bank lender were added in September 2026
(`fetch_sources.py pipes cables wb`), the Chinese finance layer on
2026-09-19 (`fetch_sources.py china`). The finance layer carries a `ln` column
(`AfDB` / `WB`) and a lender filter (`ln=` in the hash); World Bank markers are
diamonds, AfDB squares, and the two are never summed.
Status vocabulary for them: GEM `proposed` is *announced*, `construction`, `operating`
and `shelved`/`cancelled`/`idle` as *stalled*; TeleGeography's *in service* is
*operating*, and a *planned* cable is *under construction* when its ready-for-service
year is within a year of the snapshot, *announced* otherwise. The Methodology tab
states the inference.

**The Chinese finance layer** is AidData's GCDF 3.0 workbook (26 MB Excel,
ODC-By) joined with the per-project footprints of its Geospatial companion
(GeoGCDF v3.0.1 on GitHub, one GeoJSON per project, ODbL because the geometry
is OpenStreetMap's). Kept: every non-umbrella commitment to an African recipient
that AidData flags as `Infrastructure` (building, extending or maintaining a
physical structure: power plants and highways, but also hospitals, stadiums and
ministry buildings). Left out: 835 umbrella agreements (their money reappears in
the projects under them), 489 pledges (MoUs and letters of intent, which AidData
excludes from its own aggregates and never geocodes, so the layer has no
*announced* records) and 5,674 records that are not physical infrastructure
(cash, equipment and vehicle donations, scholarships, medical teams, oil-backed
corporate loans). Status: *Pipeline: Commitment* is **approved**,
*Implementation* **under construction**, *Completion* **operating**,
*Suspended*/*Cancelled* **stalled**. Amounts are AidData's constant 2021 USD and
are never added to the IATI figures; the map's lender filter offers "Chinese
official lenders" beside AfDB and the World Bank. Location comes in four tiers,
stated on every card: precise (on the OSM feature; 894 of these carry a footprint
that both pages outline), within 5 km, administrative area (the centre of the
district or province AidData names), and country only (the country's interior
point, computed from the 1:110m basemap). It is a **2000–2021 baseline**, which
is why it was first evaluated and left out; the pages say so wherever the layer
is described. The layer's GeoJSON carries the simplified footprints as
`MultiLineString` rings (a buffered road is a 2 m sliver, so rings are stroked,
never filled) and every other record as a `Point`.

## Rebuild

```bash
python3 refresh.py                # fetch → gate → build, in one go (see "Updating" below)
```

or step by step:

```bash
python3 fetch_sources.py          # all seven sources -> data/*.geojson + data/meta.json
python3 fetch_basemap.py          # Natural Earth 1:10m -> data/africa_basemap_10m.json
python3 check_data.py             # refuse a snapshot that shrank or moved
python3 build_social.py           # -> docs/social.png (link preview) + docs/icon-192.png, apple-touch-icon.png
python3 build_dashboard.py        # -> dashboard.html  and  docs/dashboard.html
python3 build_map.py              # -> map.html  and  docs/index.html + docs/data/ + sitemap.xml + llms.txt
```

Both builds inline the favicon and header mark from `brand/` (option A of the
logo sheet: the continent traced from the basemap with a compass rose cut out).
`python3 brand/trace.py && python3 brand/logos.py` regenerates them; see
`brand/README.md`.

`fetch_sources.py gem` / `iati` / `wb` / `osm` / `pipes` / `cables` / `china` runs a single source.
The OSM pass takes ~10 minutes: it walks latitude bands and sleeps between them
to stay inside Overpass's slot budget. The cables pass reads one small JSON per
cable system in the world (~700, a few minutes); the pipelines pass downloads two
GeoJSON files of ~70 MB each from GEM's bucket. The china pass downloads
AidData's 28 MB zip, reads the Excel workbook with the standard library (zip +
XML, about three seconds), then fetches ~1,900 per-project GeoJSONs from GitHub
eight at a time (two minutes; cached under `data/.aiddata_cache/` by GeoGCDF
version, so a rerun is seconds). Each run records the fetch date, release and record
count in `data/meta.json`; the pages read their "data as of" dates from there.

`fetch_basemap.py` downloads the Natural Earth GeoJSON mirrors from
`nvkelso/natural-earth-vector` (~70 MB, cached in `data/.ne_cache/`, or pass a
cache directory as the first argument) and Douglas-Peucker simplifies them into
a 3.4 MB file: the whole world's land, Africa at full detail and the rest coarser
as grey context; provinces and cities for Africa only; lakes and rivers in full
around the continent and only the largest elsewhere.

`data/africa_basemap.json` (Natural Earth 1:110m, Africa only, 32 KB) is
committed rather than fetched — it draws the dashboard's Africa and clips the
OSM results. The dashboard takes the rest of the world from the 1:10m file,
simplified much harder (about 250 KB), as grey context around the continent.

Two outputs from one template, because they run in different places:

- `map.html` / `dashboard.html` — **artifact builds**, payload inlined. The
  Claude publishing sandbox blocks runtime requests to any host, so there is no
  tile server and no `fetch()`; everything ships inside the page (6.4 MB and
  1.8 MB; the ceiling is 16 MB).
- `docs/` — the **site build** for GitHub Pages. `index.html` is a complete
  HTML document (doctype, head, favicon, social tags) that loads
  `data/map.json` at runtime via a module script with a loading state, so the
  page and the data cache separately. `docs/data/` also carries the raw
  GeoJSON layers (the AidData one with simplified footprints) and `meta.json`,
  linked from the Methodology tab, so the site publishes its data. The site build alone shows a light/dark toggle and links
  between the map and the dashboard.

## Deploying to jacopoottaviani.com/africa-infra-watch

The site is a plain folder, `docs/`, committed to the repository and served by
GitHub Pages straight from the `main` branch. Nothing runs on GitHub's side:
you build locally, look at the result, commit, push.

First time only:

```bash
git init -b main && git add . && git commit -m "africa-infra-watch: map, dashboard, pipeline"
```

```bash
gh repo create africa-infra-watch --public --source . --push
```

Then, in the new repository, **Settings → Pages → Build and deployment →
Source: Deploy from a branch → `main`, folder `/docs`**, and save.

`jacopoottaviani.com` is already the custom domain of your GitHub Pages user
site, so a project repository named `africa-infra-watch` is served at
`https://jacopoottaviani.com/africa-infra-watch/` automatically, no extra DNS.
Two things follow from that:

- **Do not add a `CNAME` file to `docs/`.** A CNAME in a project repository
  tries to claim the whole domain for that project and breaks the user site.
- Everything in the pages is a relative URL (`data/map.json`,
  `dashboard.html`), so the subpath is fine. The canonical and social-preview
  tags point at the address above; if the site ever moves, change `SITE_URL`
  in `shared.py` (or set `AIW_SITE_URL` when building) and rebuild.

What `docs/` holds: `index.html` (the map, which loads `data/map.json` at
runtime), `dashboard.html`, `data/` (the compiled payload, the seven raw
GeoJSON layers, the basemap and `meta.json` — the site publishes its data,
linked from the Methodology tab), `social.png`, `favicon.svg` and the two PNG
icons, `sitemap.xml`, `llms.txt`, and `.nojekyll` so Pages serves the folder
as-is. About 40 MB per snapshot.

## Search engines, link previews and AI crawlers

Everything a crawler reads is generated by `shared.py` at build time from the
same facts the pages draw, so the counts in the description, the structured
data and `llms.txt` cannot drift from the map:

- **`<head>`** of both pages: title suffixed with the site name (`SITE_NAME`
  in `shared.py`), description, keywords, author, canonical, `robots` with
  `max-image-preview:large`, Open Graph (`og:site_name`, `og:image` with
  width, height, type and alt) and a `summary_large_image` Twitter card.
  Favicons are files (`favicon.svg`, `icon-192.png`, `apple-touch-icon.png`),
  not data URIs, because Google only shows a result favicon it can fetch.
- **`docs/social.png`** (1200 × 630) is the picture Slack, WhatsApp, LinkedIn,
  iMessage and X show next to the link: the map itself, every record in its
  status colour over the Natural Earth coastlines, with the title and the
  three counts. `build_social.py` draws it as SVG and rasterises it with a
  headless Chrome (any `/Applications/*Chrome*` or `AIW_CHROME`); without one
  it keeps the committed PNG. It is palette-quantised if it exceeds ~290 KB,
  because WhatsApp ignores preview images above about 300 KB. Chat apps
  cache previews per URL, so after a redesign share the link with `?v=2`
  once, or paste it into a debugger
  ([opengraph.xyz](https://www.opengraph.xyz/), LinkedIn Post Inspector) to
  refresh it.
- **JSON-LD** (schema.org) in each page: `WebSite`, `Person` (author),
  `WebPage`/`WebApplication`, and a `Dataset` with one part per source, each
  with its licence, GeoJSON download, fetch date and the source organisation
  as creator. This is what Google Dataset Search and the AI crawlers parse.
- **`<noscript>`** block at the top of each body: the page's substance as
  plain HTML (what it shows, the three layers with counts, licences and
  download links, the limits), for crawlers that do not run JavaScript.
  Browsers with scripts skip it entirely.
- **`docs/llms.txt`** ([llmstxt.org](https://llmstxt.org/)): the site, the
  pages, the data files, the status vocabulary and the limits, in Markdown,
  for language-model assistants that look for it.
- **`docs/sitemap.xml`**: both pages, `llms.txt` and the data files. Submit
  `https://jacopoottaviani.com/africa-infra-watch/sitemap.xml` once in Google
  Search Console (property: the `jacopoottaviani.com` domain or the URL
  prefix), and again after a data refresh to speed up re-crawling.

There is no `robots.txt`: it only counts at the domain root, which belongs
to the user site (`jacopoottaviani.github.io`), and that root currently has
none, so nothing is blocked. If one is ever added there, include
`Sitemap: https://jacopoottaviani.com/africa-infra-watch/sitemap.xml`.

## Updating, twice a year

```bash
python3 refresh.py
```

This fetches the seven sources (about 20 minutes, most of it the
OpenStreetMap pass), records the dates in `data/meta.json`, runs
`check_data.py`, and rebuilds `docs/` and the artifact files, including the
link-preview image and `llms.txt` with the new counts. Then look at it:

```bash
python3 -m http.server 8791 --directory docs
```

and publish:

```bash
git add -A && git commit -m "data refresh $(date +%Y-%m)" && git push
```

Pages redeploys within a minute or two. The map's header shows the new "data
as of" dates, and the Methodology tab's figures update from the payload.

`check_data.py` is the gate: if a layer lost more than a fifth of its records
against the last committed snapshot, fell below an absolute floor, or has
geometry outside Africa, the build stops and nothing is written. That is
deliberate — the fetcher tolerates a refused Overpass band by design, and a
half-empty layer must never be published as "current". Rerun the failing
layer alone (`python3 fetch_sources.py osm`), then `python3 refresh.py --build`
to rebuild from whatever is in `data/`; `--force` overrides the gate if you
have looked and the drop is real.

When to run it: Global Energy Monitor releases the Integrated Power Tracker
roughly every six months (the fetch prints the release name it found), which
sets the natural cadence; its pipeline trackers refresh on their own schedule
(gas pipelines about yearly, oil pipelines twice a year; the fetch prints the
release folder it found). AfDB's IATI files, OpenStreetMap and TeleGeography's
map change continuously, so whatever a run picks up is the snapshot. `refresh.py --build`
alone rebuilds the pages after a template change without touching the data;
`--basemap` also regenerates the Natural Earth basemap, which rarely needs it.

## Why the pages do not call the source APIs themselves

They could not, and should not:

- **Global Energy Monitor** has no per-record API. The tracker is a bulk
  global CSV released about twice a year, in a storage bucket not set up for
  cross-origin browser requests. Twice a year by hand matches the source.
- **African Development Bank / IATI.** The IATI Datastore API needs a
  subscription key, and a static page cannot hold a secret. The public route
  the fetcher uses — the IATI Registry catalogue plus 57 XML files — is tens
  of megabytes that no browser should parse on load.
- **OpenStreetMap / Overpass** does answer browser requests, but a continental
  query takes about ten minutes with mirror rotation and gets rate-limited.
  A "check OpenStreetMap live for this view" button for a single zoomed-in
  viewport would be feasible and is the one live connection worth adding.

So the pages are fully static and self-describing: the sources, their
licences and the fetch dates are in the Methodology tab and in
`docs/data/meta.json`, and every detail card links back to the source record.

## Things that will bite you

These each cost real time to find. They are not in any of the upstream docs.

- **OSM raw tag counts are not project counts.** 15,291 of 21,470 African
  `highway=construction` ways are `construction=residential` — street stubs in
  housing estates. Filter to motorway/trunk/primary/secondary + rail or your
  headline number is 6× too high.
- **AfDB `<budget>` elements repeat the same value every quarter.** Taking the
  first understates; summing them is only accidentally right. Commitments live
  in `<transaction>` with `transaction-type` code 2. Values carry no currency
  attribute — they inherit the activity's `default-currency`, which is XDR
  (IMF SDR), converted here at a rate stated on the page.
- **AfDB multinational activities have no country.** Their IATI identifiers
  carry the `Z1` region code and an empty recipient country; 342 activities.
  They are labelled "Multinational" on the map and excluded from the country
  filter rather than dropped.
- **`overpass-api.de` will block you** after a few dozen queries (429, then
  refused connections). `maps.mail.ru/osm/tools/overpass` is a working global
  mirror. `overpass.osm.ch` answers but holds only Switzerland — an empty
  result for Africa, which is worse than an error.
- **Overpass `area[...]` lookups time out** on the mirrors at continental
  scale. Bounding boxes are cheap; clip to Africa locally instead.
- **An Africa bounding box is not Africa.** `(-35,-18,38,52)` pulls in Turkey,
  Spain and the Gulf — 13,454 of 18,565 raw ways in one run.
- **Natural Earth's `CONTINENT` field is not "Africa" for Mauritius and
  Seychelles** — they are "Seven seas (open ocean)". Filter by continent alone
  and both island states vanish along with their projects. Bir Tawil, the
  unclaimed strip between Egypt and Sudan, is its own polygon with ISO code
  `-99`, the same placeholder Natural Earth uses for Somaliland.
- **Natural Earth's `MIN_ZOOM` / `MIN_LABEL` fields are worth keeping.** They
  are calibrated web-map zoom levels; using them directly for label and river
  thresholds saves inventing a scheme.
- **A red/green or amber/orange status palette fails colour-vision checks.**
  The dashboard's original amber (announced) and orange (under construction)
  sat at ΔE 3 under deutan simulation — indistinguishable to about 5% of
  readers. The map's palette (ochre, indigo, magenta, green, hollow grey) was
  found by searching OKLCH space against the `dataviz` validator with the hue
  families constrained; magenta for "under construction" is the price of
  passing. Stalled is hollow so it never competes with live colour. The
  dashboard adopted the map's palette and hollow-stalled convention in
  September 2026, when it gained the map's rail and the two line layers.
- **CSS token names must match the status vocabulary exactly.** Both templates
  originally looked up `--st-under_construction` while the token was
  `--st-construction`; canvas silently ignores an empty `fillStyle`, so
  under-construction marks took whatever colour was set before them. Fixed in
  both templates; the published dashboard artifact predates the fix until
  republished.
- **A file with no `<meta name="viewport">` renders at 980 px on phones.** The
  artifact wrapper adds one; a standalone file must carry its own, or the
  mobile layout never triggers. Both templates now declare it.
- **`site` is a Python standard-library module.** A helper called `site.py`
  shadows it and breaks the interpreter's start-up; hence `shared.py`.
- **The World Bank's `Africa` region no longer exists.** It split into
  "Eastern and Southern Africa" and "Western and Central Africa";
  `regionname_exact=Africa` returns 245 rows and MENA returns 0. Filter by
  country. (The WB Projects API also has no coordinates at all — its geodata
  is only in its IATI files.)
- **DAC energy codes are the whole 23x block.** The infrastructure filter once
  matched the prefix `230`, which is only the legacy code 23010; every 5-digit
  energy code (23110 policy, 23210 solar, 23630 distribution…) fell through
  and the World Bank's energy portfolio went missing. Match `23`.
- **The IATI Datastore needs a subscription key** (401 without). Use the CKAN
  registry at `iatiregistry.org/api/3` or `d-portal.org/q.json`.
- **The World Bank marks every IATI location `exactness=2`** (approximate), even
  a named substation. The precision is in `location-class`: 4 site, 2 populated
  place, 1 administrative region. Rank on that, not on exactness, or every
  World Bank marker reads as a centroid. Its sector elements mix DAC codes
  (vocabulary 1) with the Bank's own theme and sector codes (98, 99: `000071`,
  `BC`); filter on vocabulary 1 only. Amounts are USD, not SDR. Its
  `activity-status` never says 1 (pipeline), so it has no "announced" records.
  No files exist for Algeria, Equatorial Guinea, Eritrea or Libya; regional
  programmes live in the `289` (South of Sahara) and `298` (Africa) files with
  no recipient country. The registry lists 148 files worldwide, so filter by the
  ISO suffix of the dataset name.
- **GEM's own map config points at a deleted file.** Resolve releases from the
  listable bucket under `Current_maps/`, never from their front-end source.
- **GEM's pipeline routes are not under `Current_maps/`.** The gas and oil
  trackers' GeoJSON lives under `Input_geojson_files/ggit/<release>/` and
  `Input_geojson_files/goit/<release>/` in the same public bucket (the official
  download is a form). `ggit/` and `goit/` under `Current_maps/` are empty
  folder markers. Sort by the release folder, not the file name: `2026-06.1`
  and `2026-06` sit beside `2026-07`.
- **712 GGIT features are an empty `GeometryCollection`.** Segments GEM knows
  about but has not routed; 176 of the 500 African segments. They are dropped
  from the layer and counted in `meta.json` as `unrouted`, not placed at a
  centroid.
- **A pipeline's country list is a comma-separated string** (`CountriesOrAreas`:
  "Nigeria, Benin, …, Spain") with GEM's own spellings: "The Gambia",
  "Republic of the Congo". Keep a segment if *any* country is African, so the
  Mediterranean crossings stay.
- **TeleGeography's API is undocumented.** `api/v3/cable/cable-geo.json`,
  `landing-point/landing-point-geo.json`, `cable/all.json`, `cable/<id>.json`
  and `landing-point/<id>.json` worked on 2026-09-18. A landing point marked
  "to be determined" has no detail record and answers with the HTML shell,
  so go cable by cable, never landing point by landing point, or you lose
  cables like Umoja whose only African landing is TBD.
- **TeleGeography has two statuses, planned and in service.** The
  under-construction reading here is inferred from the ready-for-service year
  (due within a year of the snapshot). Landing-point names read
  "City, Country" and the country can hold a comma ("Muanda, Congo, Dem. Rep."):
  use the `country` field of the cable detail, or match by suffix.
- **A cable's route is its whole route.** 2Africa runs from Europe to India.
  `check_data.py` tests that a line *touches* the Africa window rather than
  that it starts in it, and the map's "zoom to" fits the part of the route
  inside that window, not the whole thing.
- **Every GeoGCDF footprint is a MultiPolygon**, even a road or a single
  node: AidData buffers points and lines by about a metre and dissolves them.
  A railway arrives as a two-metre-wide sliver whose ring runs up one side and
  back the other. Stroke the exterior ring, never fill it, and drop rings
  narrower than ~20 m (a buffered node is a 65-vertex circle). The whole TAZARA
  railway (1,882 vertices after simplification) comes with five records, so cap
  the vertices a single record may carry in the payload.
- **Only AidData's "Recommended For Aggregates" records have a precision or a
  footprint**; pledges and umbrella agreements carry `NA`. Umbrella agreements
  (master facilities, ECTA framework deals) must go, or their money is counted
  twice. AidData's `Infrastructure` flag is the right filter, not the sector:
  a vehicle donation sits in transport and an oil-backed corporate loan in
  industry, and neither builds anything.
- **The per-project GeoJSON carries only a dozen fields.** Funder, contractor,
  flow class, terms and the precision tier live in the 128-column workbook,
  which the pipeline reads without openpyxl: an `.xlsx` is a zip of XML, and a
  70-line `iterparse` reader matches openpyxl cell for cell in a third of the
  time. Dates come out as Excel serials, which is fine because only years are
  used.
- **One GeoGCDF footprint is in Colombia** (record 34840, a buyer's credit in
  Africa whose OSM link points at the wrong feature). The fetcher tests every
  footprint's interior point against the Africa window and falls back to the
  country's centre, ignoring the ADM rows derived from the same bad link.
- **AidData records the recipient as ISO-3**, and "Africa, regional" has no
  code at all. Regional projects with a footprint are attributed by
  point-in-polygon; the 26 without one are dropped and counted in `meta.json`.
- **GitHub's raw host serves 1,900 small files in about two minutes** at eight
  concurrent requests with no throttling, so the 496 MB GeoPackage release is
  never needed. A 404 is a project without a feature; cache it as an empty file.

## Not used, and why

- **PIDA / VPIC** — Africa's own continental pipeline, and conceptually ideal,
  but `au-pida.org` is a stock WordPress install with no project post type and
  no CSV or GeoJSON. Project data reaches the public only as PDF reports.
- **AidData Chinese development finance 3.0** was left out at first because its
  coverage ends with 2021 commitments, so it cannot answer "ongoing". It was
  added on 2026-09-19 as the Chinese finance layer, explicitly as a historical
  baseline (see Sources): for a map of who pays for African infrastructure, two
  decades of Chinese official lending were too large a gap.
- **Boston University's Chinese Loans to Africa database** — updated through
  2024 and loan-level, but no coordinates; country-level only.
- **Microsoft's Global Renewables Watch** — quarterly satellite detections of
  solar and wind, MIT licence, but coverage stops in mid-2024 and it shows
  only what already exists, so it cannot answer "announced" or "ongoing".
- **World Bank IATI files** were evaluated on 2026-09-18 and added the same
  day as the second lender in the finance layer (see above).
- **AfDB Open Data Platform** — country indicator series, not project records.
- **Raster tiles of any kind** — blocked by the artifact sandbox's content
  security policy, which is why the basemap is vector and inline. The site
  build keeps the same basemap so both outputs look identical.
