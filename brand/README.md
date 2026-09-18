# Brand

**Chosen mark: option A** (cut-out compass rose). `shared.py` reads `favicon.svg`
and `mark.svg` from this folder and fills the `<!--__FAVICON__-->` and
`<!--__LOGO__-->` markers in both templates at build time.

Compass inside the African continent. The outline is traced from
`data/africa_basemap.json` (Natural Earth 1:110m, mainland + Madagascar) and
simplified to ~80 points; the compass is placed at the largest circle that fits
inside the mainland. All marks share a 1000x1000 viewBox. Colours come from the
map/dashboard palette (`--accent #1F5F4B`, `--ink #16211C`, `--paper #F8FAF6`,
`--accent (dark) #5FB495`).

| File | What |
|---|---|
| `option-a-cutout-rose.svg` | Solid green continent, 8-point rose cut out (one colour). `-mono` and `-inverse` variants. |
| `option-b-outline-needle.svg` | Outlined continent, bezel ring, green/grey needle. `-inverse` for dark backgrounds. |
| `option-c-solid-fineline.svg` | Solid ink continent, fine bearing ring with 24 ticks, mint needle. `-inverse` for dark backgrounds. |
| `favicon.svg` | Chosen mark (A) on a rounded green tile with a simplified rose; inlined as a data URI by both builds. |
| `mark.svg` | Chosen mark (A) in `currentColor`, inlined next to each page `<h1>`; colour follows `--accent`. |
| `favicon-check.html` | The favicon at 16 to 128 px on light and dark, for a quick legibility check. |
| `logo-options.html` | Preview sheet: light/dark, wordmark lockup, 64/32/16 px check. |

Regenerate with `python3 brand/trace.py && python3 brand/logos.py` from the project root.
