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
Earth 1:10m basemap (coastlines, borders, provinces, rivers, lakes, cities), with
the three data layers drawn as circles (power units, sized by MW), squares
(AfDB projects, sized by commitment) and lines (construction ways traced in
OpenStreetMap). Filters, a viewport summary, a "largest in view" list, per-record
detail cards linking back to the source record, and a shareable URL hash. A
**Methodology** tab (also reachable with `t=m` in the hash) documents each
source's origin, access route, unit of observation, filters, status mapping,
what it can and cannot answer, the drawing rules and the counting rules; its
figures are computed from the same payload the map draws, so they cannot drift.
The dashboard is the page-first view of the same data, with charts and a table.

## Sources

Three open datasets, deliberately kept as separate layers because they share no
project identifier. Summing across them double-counts.

| Layer | Source | Records | Answers |
|---|---|---|---|
| Assets | Global Energy Monitor, Global Integrated Power Tracker | 4,274 power units | what asset is being built |
| Finance | African Development Bank, IATI 2.03 activity files | 1,401 projects | who is paying, and how much |
| Ground truth | OpenStreetMap via Overpass | 3,586 works | what has physically broken ground |

## Rebuild

```bash
python3 refresh.py                # fetch → gate → build, in one go (see "Updating" below)
```

or step by step:

```bash
python3 fetch_sources.py          # all three layers -> data/*.geojson + data/meta.json
python3 fetch_basemap.py          # Natural Earth 1:10m -> data/africa_basemap_10m.json
python3 check_data.py             # refuse a snapshot that shrank or moved
python3 build_dashboard.py        # -> dashboard.html  and  docs/dashboard.html
python3 build_map.py              # -> map.html  and  docs/index.html + docs/data/
```

Both builds inline the favicon and header mark from `brand/` (option A of the
logo sheet: the continent traced from the basemap with a compass rose cut out).
`python3 brand/trace.py && python3 brand/logos.py` regenerates them; see
`brand/README.md`.

`fetch_sources.py gem` / `iati` / `osm` runs a single layer. The OSM pass takes
~10 minutes: it walks latitude bands and sleeps between them to stay inside
Overpass's slot budget. Each run records the fetch date, release and record
count in `data/meta.json`; the pages read their "data as of" dates from there.

`fetch_basemap.py` downloads the Natural Earth GeoJSON mirrors from
`nvkelso/natural-earth-vector` (~70 MB, cached in `data/.ne_cache/`, or pass a
cache directory as the first argument), clips them to an Africa window and
Douglas-Peucker simplifies them into a 2.3 MB file.

`data/africa_basemap.json` (Natural Earth 1:110m, Africa only, 32 KB) is
committed rather than fetched — it draws the dashboard and clips the OSM results.

Two outputs from one template, because they run in different places:

- `map.html` / `dashboard.html` — **artifact builds**, payload inlined. The
  Claude publishing sandbox blocks runtime requests to any host, so there is no
  tile server and no `fetch()`; everything ships inside the page (4.3 MB and
  1.5 MB; the ceiling is 16 MB).
- `docs/` — the **site build** for GitHub Pages. `index.html` is a complete
  HTML document (doctype, head, favicon, social tags) that loads
  `data/map.json` at runtime via a module script with a loading state, so the
  page and the data cache separately. `docs/data/` also carries the raw
  GeoJSON layers and `meta.json`, linked from the Methodology tab, so the site
  publishes its data. The site build alone shows a light/dark toggle and links
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
runtime), `dashboard.html`, `data/` (the compiled payload, the three raw
GeoJSON layers, the basemap and `meta.json` — the site publishes its data,
linked from the Methodology tab), and `.nojekyll` so Pages serves the folder
as-is. About 17 MB per snapshot.

## Updating, twice a year

```bash
python3 refresh.py
```

This fetches the three sources (about 15 minutes, most of it the
OpenStreetMap pass), records the dates in `data/meta.json`, runs
`check_data.py`, and rebuilds `docs/` and the artifact files. Then look at it:

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
sets the natural cadence. AfDB's IATI files and OpenStreetMap change
continuously, so whatever a run picks up is the snapshot. `refresh.py --build`
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
  passing. Stalled is hollow so it never competes with live colour.
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
- **The IATI Datastore needs a subscription key** (401 without). Use the CKAN
  registry at `iatiregistry.org/api/3` or `d-portal.org/q.json`.
- **GEM's own map config points at a deleted file.** Resolve releases from the
  listable bucket under `Current_maps/`, never from their front-end source.

## Not used, and why

- **PIDA / VPIC** — Africa's own continental pipeline, and conceptually ideal,
  but `au-pida.org` is a stock WordPress install with no project post type and
  no CSV or GeoJSON. Project data reaches the public only as PDF reports.
- **AidData Chinese development finance 3.0** — excellent geocoding, but
  coverage ends 2021, so it cannot answer "ongoing". Good historical baseline.
- **AfDB Open Data Platform** — country indicator series, not project records.
- **Raster tiles of any kind** — blocked by the artifact sandbox's content
  security policy, which is why the basemap is vector and inline. The site
  build keeps the same basemap so both outputs look identical.
