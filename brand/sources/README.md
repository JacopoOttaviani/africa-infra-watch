# brand/sources/

Monochrome marks of the datasets behind the map and of its publisher, shown in a grid under
**Sources and reuse → Attribution** in the Methodology. `shared.py` reads every
`*.svg` here and inlines them as the `SOURCE_LOGOS` object where a template
carries the `/*__SOURCE_LOGOS__*/{}` marker (only `map.template.html` does);
`logoTile()` in the template draws them.

Every file is the organisation's official mark with all fills set to
`currentColor` and no background, so it takes the page's ink colour in both
themes. Nothing else was redrawn.

| File | Organisation | Taken from | Rights |
|---|---|---|---|
| `global-energy-monitor.svg` | Global Energy Monitor | `globalenergymonitor.org`, site header (`GEM-DarkSVG.svg`) | © Global Energy Monitor, trademark |
| `african-development-bank.svg` | African Development Bank Group | Wikimedia Commons, `Logo_Afrikanische_Entwicklungsbank.svg` (Bank roundel only; the Fund roundel was cropped out via the viewBox) | Trademark of the AfDB; file listed as public domain on Commons |
| `iati.svg` | International Aid Transparency Initiative | `cdn.iatistandard.org`, site footer (`logo-white.svg`) | © IATI, trademark |
| `openstreetmap.svg` | OpenStreetMap | OSM wiki, `Logo_simple.svg` (the official one-colour silhouette) | CC BY-SA 2.0; OSMF trademark policy |
| `natural-earth.svg` | Natural Earth | `naturalearthdata.com`, site header (`nev_logo.png`, raster) | Public domain project |
| `eox.svg` | EOX IT Services (Sentinel-2 cloudless) | `eox.at`, site header (`EOX_Logo.svg`) | © EOX IT Services GmbH, trademark. Shown only in the site build, with the Satellite view |
| `code-for-africa.svg` | Code for Africa (publisher of this project) | Supplied by the author as a PNG with transparent background; wrapped like the Natural Earth mark | © Code for Africa, trademark |
| `telegeography.svg` | TeleGeography (Submarine Cable Map) | `submarinecablemap.com/images/telegeography-logo.svg`, the map's header wordmark; the globe's gradient fills and the white text set to `currentColor` | © TeleGeography, trademark. Data CC BY-SA 4.0 |

The Natural Earth and Code for Africa marks exist only as PNGs, so their SVGs
wrap them: the raster's alpha channel (white on transparent, base64 inside the file) is
an SVG `<mask>` over a `currentColor` rectangle. Replace them with vectors when
available.

Fetched 18 Sep 2026 (TeleGeography added the same day). The logos are used solely to credit the data sources and
imply no endorsement; if an owner objects, delete the file and the tile
disappears at the next build.
