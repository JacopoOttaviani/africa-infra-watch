# Fact-check: homepage and dashboard, 14 Oct 2026

Eight agents checked every number on the map page (`docs/index.html`, rail and
Methodology tab) and its Dashboard view (`docs/dashboard.html`, KPI tiles, charts,
records table, "Who Africa owes" box), plus `docs/llms.txt`, against the
publishers' own sources: the raw GEM releases, IATI XML, the AidData workbook,
TeleGeography's API, Overpass, the Piano Mattei portal, the World Bank IDS API,
the ECB and IMF, and the institutions' project pages. Deep dives (/debt/, lender
profiles, corridors, Lobito, LAPSSET, minerals) were not checked.

`check_numbers.py` already shows the pages agree with `data/` (306 of 306), so
these checks go one step upstream: does `data/` agree with the source, and does
the prose agree with the facts?

**Upshot.** Nothing has drifted. Re-downloading every source on 14 Oct
reproduces the site's counts and sums. The errors come from *rules*: what the
fetchers add up, what the filters let through, and what the prose says the
filters do. Four of them move a homepage headline. The ones marked ✔ were also
re-checked by hand against the raw files.

**Status (same day): fixed.** Where data and methodology disagreed, the data
was changed to follow the stated rules (the user's choice), every layer was
re-fetched, and the pages rebuilt. What was done for each finding is in
"0. What changed" below; the findings themselves are kept as they were found.

Each slice has its full table (claim, page value, verified value, source URL or
command, verdict, file:line) in `detail/`. The scripts are in `scripts/`. Their
raw downloads (about 1.4 GB) were left in the session's scratchpad and will not
survive it; the commands in each table re-fetch them.

---

## 0. What changed

**Rules, in the fetchers** (`fetch_sources.py`; the README's "Counting rules
for money" states them):

- **AfDB**: the government's counterpart commitments (`XX-COA-GOV` providers)
  are skipped. An AfDB activity still at status 1 but with a commitment on
  record is now *approved*, not *announced*; that makes the dashboard's "AfDB
  projects past board approval" true.
- **AfDB and World Bank**: budget support (aid-type A01/A02) is left out. Only
  the infrastructure share of each activity is counted, by its own sector
  percentages, and the sector label follows the largest share.
- **Every lender**: cancelled and suspended records are drawn but not counted.
  The data now carries `commitment` (counted), `commitment_published` and
  `counted_note`, and the cards show both figures.
- **EU**:
  - Commission envelopes repeated across country copies count once, or not at
    all when any copy has contracts.
  - The four sub-regional INTPA files (1027–1030) are read.
  - EIB fund investments and credit lines are left out by project number
    (`EIB_NOT_INFRA`), and so are EIB operations funded by the Commission or
    AECID.
  - EIB sector and recipient percentages give the infrastructure share and the
    African share.
  - The EIB's implementer is named from its IATI ref, and "data as of" is now
    the oldest file's own date.
- **GEM power**:
  - "The Gambia" is in the country list.
  - The release lookup follows continuation tokens and sorts versions, so it
    now reads the September 2026 release. `GEM_RELEASE` pins one.
- **GEM pipelines**:
  - `PIPE_LENGTH_FIX` corrects Wafa–Mellitah, AKK, Egbin and Medgaz onshore.
  - `PIPE_ROUTE_DROP` leaves Medgaz's bogus offshore route undrawn.
  - The fetch warns on any other length mismatch.
  - "Data as of" is now the newest record update.
- **Cables**: the length estimate is computed once, in the fetcher, and
  labelled as such. Distinct landing sites are counted.
- **OSM**: the airport query also catches `construction=aerodrome`,
  `construction:aeroway` and `proposed:aeroway`.
- **AidData**:
  - The M&A acquisition loans are left out.
  - Island-state records fall back to their island's point instead of being
    dropped.
  - Commodity-collateralised loans are counted in `meta.json` and stated.
- **Piano Mattei**:
  - TANIT's two amounts are added.
  - Wrapped implementer names are joined.
  - The funder tally splits only where " and " starts a second body. The
    implementer tally is dropped, because no separator in the portal's text is
    reliable.

**Builders and pages**:

- Owner, funder and implementer lists are no longer cut short, so their tallies
  are right.
- Co-financed is counted by AidData's own flag.
- Map and dashboard take the same representative point for a work, so their
  country counts agree.
- TeleGeography's GeoJSON is no longer published (`NOT_REDISTRIBUTED`,
  `NO_DOWNLOAD`), and the licence line says what TeleGeography's terms say.
- "Show more" hides when hidden. "In view" counts every country a record
  lists.
- The two banks and the two EU institutions are shown side by side, never as
  one total.
- Prose fixed throughout, as listed in sections 2–6: AU 55, the
  approximate-location share computed, ports and water, Western Sahara, the
  lede, "ten public datasets" listed, the approved stage, the counting rule,
  pillars, and the debt box's "Europe".
- The checker's location-share checks now compare computed percentages.

**Left as is**:

- **AidData's successor dataset** is not migrated. The site says it exists and
  that a card's link may show a revised record.
- **Upstream data errors**, which are GEM's or AidData's own:
  - ACWA's 10 GW "under construction" in Egypt.
  - Medusa "in service".
  - The Ethiopia–Djibouti pipeline "under construction".
  - NEDA's two amounts on the Mattei portal.
  These are worth reporting to the publishers.
- **TeleGeography's terms** are worth confirming with TeleGeography.
- **OSM details**:
  - A named work takes its first segment's status.
  - Islands outside the query box are disclosed, not fetched.

## 1. Headline figures that are wrong

| # | Figure on the page | Says | Should say | Cause | Where |
|---|---|---|---|---|---|
| 1 ✔ | AfDB committed | $100.3bn | **$80.0bn** | `fetch_iati` adds every commitment transaction, including the borrowing **government's own counterpart funds** (provider-org `*-COA-GOV`). It hits 698 of 1,710 AfDB activities and adds $20.3bn. Medupi shows **$9,055.4m against a real $1,711.4m**: UA 5.44bn of it is South Africa's own money. Skipping `-COA-GOV` providers matches MapAfrica's `total_commitments_nongov` exactly for Medupi and within 1% for the 40 largest activities. | fetch_sources.py:321-325 |
| 1a | Bank commitment tile | $283.8bn | **$263.6bn** | same | dashboard KPI, methodology |
| 1b | AfDB disbursed | 44% of commitments | **56%** | same (no disbursement comes from a government) | methodology |
| 1c | AfDB top records | Ain Sokhna 1,475.2 · Abu Qir 812.4 · Tunisia roads 649.3 · Namibia transport 615.8 · El Kureimat 596.3 | 380.5 · 267.4 · 218.5 · 224.1 · 164.8 | same | cards, table |
| 2 ✔ | Pipeline route | 115,012 km | **≈109,200 km** | GEM's own file has typos that we pass through. Wafa–Mellitah Pipeline 1 is **5,246 km against 524.6** (a dropped decimal; its twin and GEM's estimate field both say about 525). AKK is 1,300 km against 614, and its other 686 km is *also* a separate record. Egbin–Alagbado is 447 km against 40. | GEM GGIT 2025-11; fetch_sources.py:643 |
| 2a | Pipeline under construction | 5,822 km | **≈5,136 km** | AKK, as above | methodology |
| 3 | World Bank committed | $183.6bn | **$183.6bn stands**: it is what the stated rule ("any infrastructure DAC code") produces. What's false is the Methodology's claim that budget support is left out (see section 2). | **$46.2bn of it is sector budget support** (aid-type A02; 6 of the Bank's 10 largest "infrastructure" records are development-policy loans). Any one infrastructure DAC code lets a multi-sector project in at 100%. Weighting by the Bank's own sector percentages would give $114.8bn; that is an alternative rule, not a correction. | fetch_sources.py:291-295 |
| 4 | EU committed | €33.7bn (Commission €15.3bn) | Commission **≈€14.7bn**, with several overstatements on the EIB side | (a ✔) Each country copy of a multi-country decision repeats the whole envelope, and copies with no contract survive the fold: **"Infrastructure: African Investment Platform" €128.4m ×3** (MW, MZ, UG) and **Muzizi hydro €174.8m** (envelope already spent by sibling contracts). That is about €0.6bn counted twice. (b) The EIB's 35 "grants" are Commission blending money, also published as Commission contracts: about €0.55bn on both sides. (c) About 37 of the 47 EIB equity records are **fund investments** (≈€1.09bn), which the methodology says are left out. (d) Credit lines to banks (Afreximbank €200m, of which ≤€75m is energy). (e) Non-African shares of 16 multi-region operations (≈€0.5bn too much). (f) €1.08bn in 17 EIB operations the Bank marks cancelled. These overlap; don't add them up. | fetch_sources.py:1372-1376, 1508-1511 |
| 5 ✔ | Power units | 4,274 units · 54 countries | **4,285 · 55** (1,091.1 GW) | **The Gambia is missing**: GEM writes "The Gambia" and `AFRICA_NAMES` has only "Gambia". The pipeline fetcher patches this (line 613); `fetch_gem` doesn't. 11 units and 894 MW are lost, including the 350 MW NEK offshore wind farm. | fetch_sources.py:53-65, 145 |

## 2. Prose that says the opposite of what the data does

- **✔ "54 member states of the African Union"** (Methodology, Basemap). The AU has **55**; 54 is Africa's UN members. The 59 on the map is 54 + Somaliland + Western Sahara + Mayotte, Réunion and Saint Helena. Bir Tawil adds nothing. A proposed sentence is in `detail/prose.md` row 1. `map.template.html:2819-2821`
- **"Never summed / never added"** against summed tiles: $283.8bn = AfDB + WB and €33.7bn = Commission + EIB. Each AfDB/WB record is one lender's share, so there's no double count, but the wording is a blanket "never". In the EU case there *is* double counting (4b). Suggested: "never added into one project's cost", or show the two lenders side by side.
- **✔ "About two thirds of AfDB points are approximate"**: the dashboard, `llms.txt` and the no-JavaScript text say this; the Methodology says 42%, which is right. `dashboard.template.html:711`, `shared.py:742, 970`
- **✔ "Approved: … AfDB projects past board approval"**: AfDB has **0** approved records. `dashboard.template.html:663`, `shared.py:912`
- **"Health, education, agriculture and budget support are left out"** (finance layer): false for the World Bank (#3), and the agro-industries, SME and trade-policy codes counted as Industry/Trade aren't infrastructure in the DAC's own scheme.
- **"Only each bank's own share … national budgets are not counted"**: false for AfDB until #1 is fixed.
- **"Oil-backed credit lines … commodity-backed corporate loans … left out"** (Chinese finance): the only test is AidData's infrastructure flag. Kept: 242 commodity-collateralised records ($46.2bn, 19%), e.g. CDB's $2bn oil-backed loan to Sonangol (2,214.2). Three acquisition loans ($2.6bn) are in too.
- **"Approved exists only for power and for Chinese finance"**: the Piano Mattei layer has 17 approved records. `map.template.html:2756`
- **GEM "Approved"** = GEM's *pre-construction*, which means still seeking permits, land or finance; "a signed commitment" overstates it (601 units, 267.5 GW, including AMAN, paused in 2025). The ACWA wind farm in Egypt, 10 GW "under construction", has only an MoU and a land allocation behind it: 13% of all under-construction GW.
- **Medgaz "drawn along its whole route"**: GEM's "offshore" geometry runs overland across Algeria and never reaches Spain. The Nigeria–Morocco line is drawn from Ghana, not Nigeria.
- **Dashboard: ports, water and transmission "appear only where AfDB finances them or OSM mappers trace them"**: water comes from five lenders, and OSM has no water or port records. `dashboard.template.html:735-737`
- **Western Sahara as "a separate shape"**: in Natural Earth, Morocco's polygon includes the part Morocco administers. 12 OSM works there count as Morocco, while GEM's 20 units count as Western Sahara.
- **The lede's "power plants planned or under construction"**: the layer is every status (only 34% is pipeline).

## 3. Licence: needs a decision, not a number

**TeleGeography "CC BY-SA 4.0"** (two agents raised this independently). The
code cites "TeleGeography's FAQ" for the licence (`fetch_sources.py:668-672`).
Today that FAQ and TeleGeography's citation page say CC BY-SA 4.0 covers its
*maps, URLs and screenshots*, that "access to the underlying databases remains
restricted to paying subscribers", and that the raw map data, delivered as the
JSON API, is sold under an annual licence. TeleGeography's GitHub repo, which
used to carry the cable data under CC BY-SA, now returns 404. The site reads
that JSON and republishes it as `docs/data/telegeography_cables.geojson`, with
owners, suppliers, RFS dates and landings. Either the terms have changed since
the layer was added, or they never covered the data. Worth asking
TeleGeography, or dropping the download and keeping the drawn map.
`shared.py:107`

## 4. Wrong tallies (bugs, medium/low)

- **✔ Cable owners**: the build cuts owner lists at 200 characters, so ten consortium cables lose owners. It's Telecom Egypt 15 · Orange 14 · center3 8 · Sparkle 8 · Tata 8 · Djibouti Telecom 7 · Mauritius Telecom 7, not "Orange 12 · Telecom Egypt 11 …". `build_dashboard.py:470` (notes cut at :474 too)
- **Chinese implementers and funders**: cut at 110 characters. SinoHydro 105 (site 100), Huawei 95 (88), CRBC 78, CMEC 66, ICBC 88. Co-financed is 169, not 156. `build_dashboard.py:542, 546`
- **Piano Mattei funders**: "Ministry of Foreign Affairs 20 · International Cooperation (MAECI) 17" is one ministry split at " and ". **Implementers**: "UNDP 2 · (UNDP) 2 · …" comes from splitting on a line break. Correct: UNDP 5 · ITS Academies 4 · MASE 4. `map.template.html:2371-2372`
- **Piano Mattei amounts**: TANIT's second figure (€36.5m) is dropped, because the parser keeps the first match. The shared €5m education envelope is counted zero times, not once. Total €4.39bn / $4.92bn, not €4.35bn / $4.88bn; the dashboard's rounded €4.4bn stands. "50 in one country" is 48 (+2 with no country).
- **EU implementers**: "European Investment Bank 19" counts names only. By organisation ref the EIB implements 61 Commission records, second after GIZ.
- **Chinese finance**: 26 records ($0.54bn, mostly island states) are dropped silently because the basemap has no polygon for them.
- **Map ↔ dashboard country counts** (Egypt 1,191/1,192, Libya 472/474, Morocco 578/576, W. Sahara 25/27): the two builds take different midpoints for 5 OSM works. The "a route counts in each country" caption explains none of it.
- **"Show more ↓ (-2)"** under "Largest in view 8 of 8": `.showmore{display:inline-flex}` overrides `[hidden]`. Fix: `.showmore[hidden]{display:none}`. `map.template.html:170`
- **"In view … 6 countries"** counts only each record's first country.

## 5. Freshness and sources moving on

- **✔ AidData has superseded GCDF 3.0**: *China's Global Loans and Grants Dataset 1.0* (18 Nov 2025, commitments to 2023, constant 2023 USD). The card links now land on the new records, which can disagree. Egypt CBD shows $2,921m on the site against ICBC's $610m share now; the Ethiopia–Djibouti gas pipeline is now "[Cancelled]". The pinned zip URL can't pick it up.
- **GEM power is a release behind**: September 2026 was out before the 12 Oct fetch (4,284 units, 1,093.1 GW). `gem_latest_csv()` reads only the first 1,000 bucket keys (all 2026-08-v2 tiles), so it can never see a newer release; `sorted()[-1]` would also rank `2026-08` above `2026-08-v3`.
- **"Data as of" shows download dates, not data dates**, for GEM O&G (data to Mar 2026; "GOIT 2026-07" is a bucket folder, and GEM's public release is March 2025) and the EU (EIB file generated May 2025 in IATI 2.02, not 2.03; DG NEAR Jan 2025). As a result ONCF shows €200m against €265m signed, and Morocco post-earthquake €500m against €1bn.
- Cables: IEX and Daraja have slipped to RFS 2027. Medusa is "operating" per TeleGeography, but only Marseille–Bizerte is lit.

## 6. Smaller claims

- OSM "without that filter … about six times higher": today it's **9×** by segments and **12×** by works. The 6× probably came from an old code comment (21,470 / 3,680).
- OSM "Airport 4": the query takes only `aeroway=construction` outlines and misses 18 named new airports (Bugesera, Bishoftu, New Khartoum, Hoima…).
- Cables "282 African landing points" is cable-landing pairs; there are 127 distinct points. 24,520 of the 510,029 km are our own route estimates, not "as published" (Umoja shows 5,599 km on the dashboard and 8,137 km on the map).
- AfDB "58% on an exact site": 508 of those 991 are coded *administrative region*, and 517 sit on capital-city points shared by five or more activities.
- AfDB "Announced 130": all carry approved commitments and 83 are signed.
- Chinese finance: "a syndicated loan is one record" is not true for at least 12 syndicates, which are split per lender. The $242.7bn includes $8.56bn in cancelled or suspended records, which AidData's own Recommended-for-Aggregates field excludes.
- "Ten open datasets" is never listed, and the Methodology's §02 says "eight sources".
- "15,582 records across 59 countries": the dashboard should say "countries and territories".
- Social card "4,823 AfDB, World Bank and EU projects" adds two layers.
- Debt box: "Europe 71.9" excludes EU institutions (EIB, EU: $14.1bn), which the IDS files under multilateral. Counting them makes Europe $86.1bn, **above China's $82.2bn**. Worth one clause.
- Piano Mattei: "Lobito corridor" among the flagship *works* is a €600k technical-assistance grant; `llms.txt` says multi-country programmes sit "between their countries" (they all sit at one point in CAR).

## 7. What held up

- **Debt box**: every figure matches the World Bank IDS (release 3 Dec 2025) to the printed decimal, including the 50 governments, the shares and the IMF line.
- **Exchange rates**: ECB 1.1206 on 9 Oct 2026 ✓; IMF SDR 1.35326 (the rounded 1.35 understates AfDB by 0.24%).
- **Counts**: every headline count reproduces from upstream (GEM, AidData, IATI, TeleGeography, portal); OSM drifted by under 1%.
- **Outliers that look odd but are right**: Megaton Moon 2 × 29.4 GW, Topeka 25 GW, Eskom $3,159.6m (net of cancellations), ZTE Ethiopia $2,698.9m (2007 deflator), the repeated Renergy, Adani and Globeleq rows (distinct GEM units), the Angola master facilities (net drawn-down amounts, no double count).
- ELMED "mostly European and Tunisian money", the €5.5bn Mattei envelope, the 18 partner countries, every licence except TeleGeography's, and Natural Earth's shapes.
