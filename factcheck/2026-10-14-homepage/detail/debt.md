I could not write `FC/findings_debt.md`: the harness blocks subagents from writing report files. The full table and notes are below so you can save them.

**Result: no WRONG and no DRIFTED values.** Every figure in the box comes out the same from the live World Bank debt statistics API, to the printed decimal. The data still carries the 3 Dec 2025 release date.
- **MISLEADING (med), row 1, "Europe 71.9 bn (10%)":** "Europe" means European countries only. The EU's own lenders (EIB 11.58, EU 2.18, European Social Fund 0.31, EDF 0.06, EEC 0.01, together 14.14 bn) are counted under "Multilateral lenders", which is also how the World Bank classes them. The box never says so. Counting them gives Europe **86.1 bn (12.2%), above China's 82.2 bn (11.6%)**, so the China-versus-Europe ranking a reader sees depends on an unstated choice. Fix: one clause in the footnote or a tooltip on the Europe key.
- **No other MISLEADING rows.** Low-severity notes:
  - "United Kingdom 14.8" is 85% commercial banks.
  - "Multiple lenders 24.4" is a World Bank bucket for several lenders together, not a named lender.
  - Of the 96.2 bn IMF line, 43.9 is SDR allocations and 52.3 is IMF credit.
  - The site's multilateral total is 265.56 against the World Bank's own 264.51. The gap is the Africa Finance Corporation (1.22 bn), which the World Bank classes as a private lender.
  - The printed percentages add to 100% plus "<1%" because of rounding.
- **UNVERIFIABLE (low):** how much the 4 missing debtors (Libya, Namibia, Seychelles, South Sudan) would add. None of them reports its debts to the World Bank.
- **Calling it "Africa" is fair.** Egypt (106.9 bn), Morocco, Tunisia and Algeria are all included; only Libya is missing from the north. The total breaks down exactly as the World Bank's own Sub-Saharan Africa figure (530.8) plus Djibouti (2.8, which the Bank counts in the Middle East) plus North Africa (174.3).

## Findings table (findings_debt.md content)

Data URL patterns used in the table:
- **[A]** `https://api.worldbank.org/v2/sources/6/country/{ISO3}/series/DT.DOD.DPPG.CD/counterpart-area/all/time/all?format=json&per_page=30000`, saved in `FC/raw_debt/by_debtor/`
- **[B]** `python3 -I FC/scripts_debt/analyse.py FC/raw_debt/by_debtor FC/raw_debt/counterpart_list.json 2024`
- **[C]** `.../country/{50}/series/DT.DOD.DPPG.CD;DT.DOD.BLAT.CD;DT.DOD.PCBK.CD;DT.DOD.PROP.CD;DT.DOD.PBND.CD;DT.DOD.MLAT.CD;DT.DOD.OFFT.CD;DT.DOD.PRVT.CD/counterpart-area/730;012;004;994;302;BND;WLD/time/YR2024`, then `scripts_debt/split.py`
- **[D]** `.../series/DT.DOD.MLAT.CD;DT.DOD.BLAT.CD;DT.DOD.PRVT.CD/counterpart-area/all/time/YR2024` (3 pages), then `scripts_debt/mlat.py`
- **[E]** `.../series/DT.DOD.DIMF.CD;DT.DOD.DIMF.US.CD;DT.DOD.DSDR.CD/counterpart-area/WLD/time/YR2024`
- **[F]** `.../country/SSA;MNA;LMY/series/DT.DOD.DPPG.CD;DT.DOD.DECT.CD;DT.DOD.DIMF.CD/counterpart-area/WLD/time/YR2024`
- **[G]** International Debt Report 2025 PDF: https://documents1.worldbank.org/curated/en/099122225162037208/pdf/P165236-a536f876-71a7-4abb-b204-80ef88d247a1.pdf (Table 1.8 and the Sub-Saharan Africa snapshot)
- **[H]** https://www.worldbank.org/en/news/press-release/2025/12/03/developing-countries-debt-outflows-hit-50-year-high-during-2022-2024
- **[I]** https://api.worldbank.org/v2/sources?format=json (source 6 lastupdated 2025-12-03) and `https://api.worldbank.org/v2/sources/6/country?format=json&per_page=1000`

| # | claim | where | site | verified | source | verdict | sev | repo |
|---|---|---|---|---|---|---|---|---|
| 1 | Europe vs China grouping | key | Europe 71.9 (10%) < China 82.2 (12%) | European states only; EU institutions (14.14 bn) sit in multilateral. With them Europe = 86.1 (12.2%) > China 82.2 (11.6%). The World Bank also classes the EIB as multilateral; the box does not say so. | [B],[D] | MISLEADING | med | fetch_debt.py:56-59, :113; build_debt.py:45-46; dashboard.template.html:1873 |
| 2 | Total | head | 707.9 | 707.933 (sum of WLD rows = sum of counterparts) | [A],[B] | OK | – | data/debt.json:1; docs/dashboard.html:914; dashboard.template.html:1868 |
| 3 | End of 2024 is the latest year | head | 2024 | Max year with data is 2024 for all 50 | [B] | OK | – | fetch_debt.py:224 |
| 4 | 50 governments | head | 50 | 54 queried; LBY/NAM/SYC/SSD return API error 160 and are absent from the source 6 debtor list | [A],[I] | OK | – | fetch_donors.py:37-46; fetch_debt.py:205-207; build_debt.py:421 |
| 5 | Fair to call it "Africa" | title | 50/54 | EGY 106.93, MAR 45.73, TUN 20.82, DZA 0.85 included (North Africa 174.3 = 24.6%). The 46 sub-Saharan debtors excluding Djibouti = 530.82, exactly the API SSA PPG aggregate (530.816). | [B],[F] | OK | low | fetch_donors.py:37-46 |
| 6 | Size of the gap left by the 4 missing debtors | implicit | – | Not reported to the World Bank, so it cannot be sized from this data | [I] | UNVERIFIABLE | low | data/debt.json:1 (missing) |
| 7 | Multilateral lenders | key | 265.6 (38%) | 265.558 (37.51%). World Bank's own multilateral class is 264.51; the 1.05 gap = AFC 1.223 (private in the World Bank data) − 0.172 multilateral inside "Multiple lenders" | [B],[D] | OK | low | fetch_debt.py:53-54, :113 |
| 8 | IMF not in the total | IMF line | – | Code 907 has no PPG value in 2024; IMF credit is the separate series DT.DOD.DIMF.CD | [B] | OK | – | fetch_debt.py:18-20 |
| 9 | Bondholders | key | 192.8 (27%) | 192.800 (27.23%) = DT.DOD.PBND.CD | [B],[C] | OK | – | data/debt.json:1 |
| 10 | China | key | 82.2 (12%) | 82.218 (11.61%) | [B] | OK | – | " |
| 11 | Europe (number) | key | 71.9 (10%) | 71.945 (10.16%) | [B] | OK | – | fetch_debt.py:56-59 |
| 12 | Gulf states | key | 28.5 (4%) | 28.460 (4.02%): Saudi Arabia 12.05, Kuwait 9.81, UAE 5.90, Bahrain 0.51, Qatar 0.09, Oman 0.09. Gulf-funded multilaterals (≈24 bn) are counted in multilateral. | [B] | OK | low | fetch_debt.py:60 |
| 13 | United States | key | 6.8 (<1%) | 6.764 (0.96%); 5.22 of it commercial banks | [B],[C] | OK | – | fetch_debt.py:119 |
| 14 | Other lenders | key | 60.2 (9%) | 60.187 (8.50%) | [B] | OK | – | build_debt.py:49-50 |
| 15 | Shares sum to 100% | key | 100% + "<1%" | Unrounded shares sum to 100.00%; the printed excess comes from 8.50% rounding up | [B] | OK | low | dashboard.template.html:1839 |
| 16 | IMF credit and SDR allocations | IMF line | 96.2 | 96.164 = DT.DOD.DIMF.CD over the same 50 (IMF credit 52.31 + SDR allocations 43.86) | [E] | OK | – | fetch_debt.py:179-194; build_debt.py:419-420 |
| 17-24 | Largest creditors | top list | 192.8 / 110.0 / 82.2 / 47.1 / 40.8 / 25.4 / 24.4 / 14.8 | BND 192.800, IDA 110.045, China 82.218, AfDB 47.102, IBRD 40.829, France 25.356, Multiple lenders 24.380 (mostly commercial banks: 17.56), UK 14.752 (12.61 commercial banks) | [B],[C] | OK | low (994, 012 notes) | build_debt.py:411, :419; docs/dashboard.html:914 |
| 25 | Order of the top 8 | top list | as listed | Same order upstream; next are Germany 13.60 and Saudi Arabia 12.05 | [B] | OK | – | build_debt.py:419 |
| 26 | "A lending country counts all its lenders, public and private" | footnote | – | China 82.22 = bilateral 62.15 + commercial banks 17.38 + other private 2.69 | [C] | OK | – | dashboard.template.html:1873 |
| 27 | "bondholders are not named" | footnote | – | BND is a single counterpart | [C] | OK | – | " |
| 28 | PPG, current USD | footnote | – | Series name confirmed; long-term PPG only (SSA total external debt is 900.8 vs SSA PPG 530.8) | [F],[G] | OK | – | fetch_debt.py:39-40 |
| 29 | "by 50 governments" | head | – | PPG also covers public corporations and state-guaranteed debt; slight simplification | [F] | OK | low | dashboard.template.html:1868 |
| 30 | Release of 3 Dec 2025 | footnote | 3 Dec 2025 | Source 6 lastupdated 2025-12-03; press release dated 2025/12/03, covering end-2024 data | [I],[H] | OK | – | fetch_debt.py:176, :228 |
| 31 | Chart of the stock since 2000 | chart | 237.5 / 203.6 / 414.2 / 707.9 | Upstream 237.6 / 203.6 / 414.2 / 707.9; 2024 is the peak (fits the 750 axis) | `scripts_debt/years.py` vs `scripts_debt/chart.py docs/dashboard.html` | OK | – | docs/dashboard.html:914; build_debt.py:410 |
| 32 | Against the World Bank's own Sub-Saharan Africa figures | context | – | International Debt Report 2025: SSA PPG 302 + 229 = 531 (API 530.8), bonds 149 (149.4), IMF 72 (71.6), total external debt 900.8 | [G],[F] | OK | – | – |
| 33 | China ~12% sanity check | key | 12% | 11.6% (peak 15.4% in 2016). Sub-Saharan Africa only: 74.5/530.8 = 14.0%; North Africa dilutes it (China 6.29 of 174.3). Chatham House's 12% is total public and private external debt in 2020, a different base. | [B],[F]; https://www.chathamhouse.org/sites/default/files/2022-12/2022-12-15-africa-china-debt-distress-vines-et-al.pdf (seen via search snippet; the page returned 403) | OK | – | – |

**Notes:**
- The group totals were rebuilt from freshly downloaded data, not from debt.json. To do that, the group definitions were re-typed from fetch_debt.py:53-61 and :108-133. The definitions were then judged separately against the World Bank's own lender classes (multilateral, bilateral, private; [D]).
- Two odd rows come from the World Bank data itself, not the site: Tunisia owes 0.31 bn to the "European Social Fund", and Israel holds 4.21 bn of claims, 2.73 bn of them on Angola.
- Nothing in the repo was modified or run. The downloads are in `FC/raw_debt/` and the scripts in `FC/scripts_debt/`, where FC is `/private/tmp/claude-501/-Users-jacopo-Documents-Claude-Projects-africa-infra-watch/1c32fbf0-4aa0-4fb1-9410-2458a10f75b6/scratchpad/factcheck`.