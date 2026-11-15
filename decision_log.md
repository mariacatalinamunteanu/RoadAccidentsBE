# Decision log

Each entry: **what** was decided, **why**, the alternatives, the **impact** in numbers, and **where** it lives.
*Decided by*: **student** = answer/instruction given in a prompt; **Claude** = proposed by Claude while building,
to be confirmed by the student (marked ☐ until confirmed).

---

## Data preparation (2026-11-15)

### D01 · Work in Dutch only – drop all French columns
- **Decided by:** student (prompt: "remove all the FR columns – we will be working only based on the NL language")
- **What:** drop the 14 columns ending in `_FR`.
- **Why:** every FR column has an NL twin; keeping both doubles the width without adding information.
- **Impact:** 45 → 31 raw columns; 0 rows dropped. **Where:** `pipeline.step_drop_french` (step 2).

### D02 · Fill the empty province of Brussels
- **Decided by:** student (prompt: fill TX_PROV_COLLISION_NL with "Brussels Hoofdstedelijk Gewest", for the province view)
- **What:** empty `TX_PROV_COLLISION_NL` → "Brussels Hoofdstedelijk Gewest". The step refuses to run if an empty
  province is found outside Brussels.
- **Why:** Brussels belongs to no province; without a value, 30,022 accidents would disappear from the province view.
- **Alternative:** leave empty and drop Brussels from the province view (rejected: 10% of accidents lost).
- **Impact:** 30,022 rows changed; Brussels is the 11th unit in the province view. **Where:** step 3.

### D03 · Abnormal coordinates → centre of the municipality
- **Decided by:** student (prompt: "replace these with the geo coordinates of the centers of the municipalities")
- **What:** coordinates that are missing, outside Belgium, or > 1 km outside their municipality get the centre of the
  municipality in `CD_NIS`. Original values kept in `MS_X/Y_COORD_ORIG`; `COORD_IMPUTED` flags them.
- **Why:** the municipality of each accident is known and reliable (every NIS code has exactly one name and region),
  so the accident can still be counted. Dropping the rows would lose 12.7% of accidents and bias years 2017–2021 (15–19%).
- **Impact:** 36,628 rows replaced (35,881 missing, 2 impossible, 745 > 1 km). **Where:** steps 5–6.

### D04 · "Abnormal" = more than 1,000 m outside the own municipality ☐
- **Decided by:** Claude
- **What:** a point is abnormal only if it lies > 1,000 m outside the polygon of its `CD_NIS` municipality.
- **Why:** 4,677 points lie outside their municipality, but 3,932 of them by less than 1 km – typically accidents on a
  border road, geocoded on the other side. Those are plausible. Beyond 1 km the distance distribution has a long tail
  up to 138 km (clearly wrong).
- **Alternatives:** 0 m (would replace 4,677 plausible points), 5 km (would keep 422 doubtful points).
- **Impact:** 745 replaced, 3,932 kept. **Where:** `pipeline.OUTSIDE_TOLERANCE_M`.

### D05 · Municipality centre = polygon centroid, representative point if outside ☐
- **Decided by:** Claude
- **Why:** the centroid is the standard "centre"; for 5 oddly shaped municipalities it falls outside the municipality,
  which would put accidents in the wrong municipality on the map.
- **Alternative:** town-hall address (no open national list with coordinates found).
- **Impact:** 576 centroids, 5 representative points. **Where:** `pipeline.unit_centres`.

### D06 · Borders and centres from Statbel statistical sectors 2024 ☐
- **Decided by:** Claude
- **Why:** same source as the accident data (Statbel), Lambert 72 like the accident coordinates, and the 2024 borders
  contain exactly the 581 municipalities used in the accident data for all years.
- **Impact:** 19,795 sectors dissolved into 581 municipalities, then into 11 provinces (incl. Brussels), 3 regions, BE.

### D07 · Population density 2017–2018 derived from population / 2019 area ☐
- **Decided by:** Claude
- **What:** Statbel's density file starts in 2019. For 2017–2018, the population per municipality (old codes) is mapped
  to the 2019 codes (7 mergers hard-coded, Hainaut renumbering by name) and divided by the 2019 area.
- **Why:** the accident data uses 2019 codes for every year; areas barely change.
- **Check:** Belgian total 2017 = 11,322,088 = Statbel; 2018 vs 2019 density differs by −0.4% on average (population growth).
- **Where:** `pipeline.build_density`, `MERGERS_2019`; tested in `test_gaps.py::test_population_matches_statbel_totals`.

### D08 · Population density of the accident year (1 January), not one fixed year ☐
- **Decided by:** Claude (student asked for "each year between 2017 and 2024")
- **Why:** density changes over time (e.g. Brussels municipalities +5–10%); each accident is linked to its own year.
- **Impact:** join on `CD_NIS` + year, 0 unmatched rows. **Where:** step 4.

### D09 · Keep exact duplicates and hour = 99 ☐
- **Decided by:** Claude
- **What:** 66 identical rows and 3 rows with hour 99 are kept.
- **Why:** the data is aggregated to month + hour, so two identical rows can be two real accidents. Hour 99 rows are
  valid accidents with an unknown hour; no chart uses the hour except the COVID rush-hour share.
- **Impact:** 0.02% of rows; shown in the Raw Data Explorer.

---

## Question 1 – density vs severity (2026-11-15)

### D10 · Severe = class 1, 2, 3 and Severity Ratio definition
- **Decided by:** student (prompt)
- **What:** severe = `CD_CLASS_ACCIDENTS` 1 (deaths), 2 (fatally injured), 3 (seriously injured).
  Severity Ratio = severe / all injury accidents × 100, each accident once.
- **Where:** `pipeline.SEVERE_CLASSES`, `is_severe`, `severity_ratio`.

### D11 · Use the Severity Ratio, not accident counts, against density
- **Decided by:** student (question) + Claude (interpretation)
- **Why (denominator problem):** counts grow with residents and traffic. A ratio within accidents does not grow with
  volume. There is **no traffic-volume data**, so "risk per km" is not computed; accidents per 1,000 inhabitants is shown
  in the tables only as context.
- **Where:** stated in the app (assumption boxes) and in `CLAUDE.md`.

### D12 · Four border views, dots at the centre, colour = SR, size = density
- **Decided by:** student (4 buttons, dots at centres, gradient colours) + Claude (encoding) ☐
- **What:** colour = Severity Ratio on a blue → red scale fixed at 0–20%; size = log population density.
- **Why:** blue/red stays readable for colour-blind people (no red/green); a fixed 0–20% range keeps colours comparable
  between buttons and years (municipal outliers > 20% are shown as the darkest red).
- **Where:** `app.py` `SEV_COLORS`, `SEV_RANGE`.

### D13 · Density per unit = Σ population / Σ area ☐
- **Decided by:** Claude
- **Why:** the mean of municipal densities would give a tiny dense municipality the same weight as a large rural one.
- **Where:** `pipeline.aggregate_by_level`; tested in `test_pipeline.py::test_aggregate_counts_each_accident_once_per_level`.

### D14 · Spearman correlation + trend weighted by number of accidents ☐
- **Decided by:** Claude
- **Why:** density is very skewed (24 – 23,000 inh./km²) and the relation is not linear; Spearman uses ranks. The trend
  line is weighted by √accidents so small municipalities with noisy ratios weigh less.
- **Impact:** ρ = −0.50 across 581 municipalities, p < 0.001.

### D15 · Minimum 30 accidents per municipality in the scatter (default, adjustable) ☐
- **Decided by:** Claude
- **Why:** a municipality with 4 accidents has a ratio of 0%, 25%, 50%…; such noise hides the pattern.
- **Impact:** the slider shows how many municipalities are left out ("Rows used in this tab").

### D16 · Fixed density classes < 250 | 250–500 | 500–1,000 | 1,000–2,500 | 2,500–5,000 | > 5,000 ☐
- **Decided by:** Claude
- **Why:** rounded, easy-to-explain limits that mean the same in every year selection (quantiles would move).
- **Where:** `pipeline.DENSITY_BINS`.

### D17 · The GPS heat layer shows only accidents with their own valid coordinate (review fix)
- **Decided by:** Claude, during the review against the evaluation criteria
- **What changed:** before, the grey heat layer also drew the 36,628 accidents placed on a municipality centre (D03),
  creating false hot spots on the centres. Now it uses step 8 (`step_select_georeferenced`) and the map says how many
  accidents are not drawn.
- **Why:** "a map that hides missing coordinates is lying" (assignment, pitfall 1). The centres are fine for counting
  per municipality, not for showing *where* an accident happened.
- **Impact:** 252,904 of 289,532 accidents drawn (−12.7%; 15–19% per year before 2022, 3–6% after).
- **Later changed:** D27 adds a switch to draw the replaced accidents at their municipality centre (off by default).

---

## Question 2 – COVID (2026-11-15)

### D18 · Choose the COVID question as question 2
- **Decided by:** student (prompt: "the above question 1"), proposed by Claude out of 5 ideas.

### D19 · Phases by month ☐
- **Decided by:** Claude
- **What:** Lockdown 1 = Mar–May 2020; Summer 2020 = Jun–Oct; Lockdown 2 = Nov 2020–Apr 2021; Reopening = May 2021–
  Feb 2022; Post-COVID from Mar 2022.
- **Why:** the data has no day. Limits follow the OxCGRT stay-at-home indicator (C6M = 2 in Apr–May 2020 and Nov 2020–
  Apr 2021) and the official Belgian dates (lockdown 18/03/2020, measures lifted 07/03/2022).
- **Known weakness:** March 2020 counts fully as lockdown (only 14 of 31 days were).

### D20 · "Normal" = average of the same calendar month 2017–2019 ☐
- **Why:** removes the seasonal pattern (accidents peak in June and October); 2017–2019 is the last pre-COVID period.
- **Alternative:** 2019 only (more noise), a trend model (harder to explain).
- **Where:** `pipeline.covid_monthly`, `period_vs_baseline`; tested in `test_gaps.py::test_covid_baseline_is_three_year_average`.

### D21 · Chi-square test and mix/within decomposition ☐
- **Why:** chi-square tests whether the share of severe accidents differs from normal. The decomposition (direct
  standardisation on built-up area × road type × collision type × cyclist) separates "other accidents happened" (mix)
  from "the same accidents ended worse" (within).
- **Impact (Belgium, L1):** SR 12.3% vs 10.2%, p = 1.6e-06; mix +0.49 pp, within +1.68 pp. L2: 9.6% vs 9.7%, p = 0.85.

### D22 · Google mobility (workplaces, transit, residential) as proxy for traffic ☐
- **Why:** no open Belgian traffic counts for 2020–2022 found at monthly level; Google has no "driving" category.
- **Impact:** used for context and the scatter only, not in any ratio. Province rows dropped (step C1: 13,636 → 3,896
  rows, −9,740); only Belgium kept from OxCGRT (step C2: 202,760 → 1,096 days).

---

## Engineering (review 2026-11-15)

### D23 · One `pipeline.py` with pure step functions; app only reads its outputs
- **Decided by:** Claude, required by the assignment (step 3)
- **What changed:** `Scripts/prepare_data.py`, `Scripts/prepare_covid.py` and the logic in `App/data.py` were merged
  into `pipeline.py`; `App/app.py` → `app.py` + `app_data.py` (loaders only).
- **Check:** the new pipeline output is identical to the old one (289,532 × 41, compared cell by cell).

### D24 · Show rows in/out per step, a funnel at the top and the source of every number
- **Why:** evaluation criteria 1–2. Every step returns a `StepReport` (rows in/out/dropped/changed/why) saved in
  `pipeline_steps.csv` with a sample per step. Every metric/chart has a "Source:" caption.

### D25 · Large files not in git; app reads Parquet ☐
- **Why:** GitHub refuses files > 100 MB. The processed CSV is 109 MB; the Parquet copy is 17 MB and loads faster.
- **Not committed:** processed CSV, statistical sectors (200 MB), full municipality GeoJSON (55 MB), OxCGRT (44 MB).
  `pipeline.py` rebuilds or the files are re-downloaded (URLs in `Claude work log.txt`).
- **Open point for deploy:** the raw accident xlsx (61 MB) is committed (below the 100 MB limit).

### D26 · Row funnel at the top of the "Pipeline & method" tab, not above all tabs
- **Decided by:** student (2026-11-15: "Doesn't it make more sense to be there?")
- **What changed:** the funnel moved from above the tabs to the top of the tab "Pipeline & method", directly above
  the step expanders it summarises. The warning "only accidents with casualties" stays above all tabs.
- **Why:** the funnel describes the pipeline steps, so it belongs with them; above every tab it pushed the actual
  questions down. The casualties warning applies to every number in the app, so it stays visible everywhere
  (assignment: "name that difference explicitly on your dashboard").
- **Later changed:** D28 moved the casualties statement from above all tabs into the Assumptions of the two question tabs.

### D27 · Switch on the map: include the accidents placed at the municipality centre (off by default)
- **Decided by:** student (2026-11-15, option 3 of 3 proposed by Claude)
- **Context:** the student asked why accidents with missing GPS coordinates were "dropped", since D03 says to replace
  them with the municipality centre. They were never dropped from the data (all 289,532 rows are in every count and
  ratio); D17 only left them out of the GPS heat layer, and the funnel label "Keep accidents with own valid
  coordinates" made that look like a drop. D17 was Claude's own choice and had not been asked.
- **What changed:** tab 2 has a switch "Include accidents placed at the municipality centre (n)". Off (default) = heat
  layer from step 8, own coordinates only. On = all accidents, the replaced ones at their municipality centre (D03).
  The caption under the map and the "Rows used" table follow the switch. Step 8 is renamed "Heat layer only:
  accidents at their own GPS position" and its explanation says it removes nothing from the data.
- **Why off by default:** with the switch on, municipality centres become dark spots that come from the replacement,
  not from real accident locations (assignment pitfall: "a map that hides this is lying"). With the switch, both
  views can be shown and compared.
- **Alternatives:** keep D17 only (hides the student's instruction on the map); always draw them (false hot spots).
- **Impact:** all years: 36,628 accidents (12.7%) switched on/off. Tested in
  `test_gaps.py::test_app_runs_every_tab_and_button`.

### D28 · "Only accidents with casualties" statement moved into the Assumptions of both question tabs
- **Decided by:** student (2026-11-15)
- **What changed:** the warning under the app title was removed. Its text ("This dataset contains only accidents with
  at least one death or injury. Accidents with only material damage are not included, so the most dangerous place
  according to this data is not the same as the place with the most accidents.") is now, word for word, the first item
  of the "⚠️ Assumptions behind this tab" box in tab 2 (density vs severity) and tab 3 (COVID), followed by the note
  that the Severity Ratio is a share among injury accidents. It also appears in "Pipeline & method" → "Assumptions".
- **Why:** the statement is an assumption behind the answers to the two questions, so it belongs with the other
  assumptions of those tabs instead of above the data explorer and pipeline tabs. Replaces the last part of D26.

### D29 · Pipeline steps named after their data set and the tabs that use them
- **Decided by:** student (2026-11-15)
- **What changed:** every step report has two extra fields, `dataset` (what the step works on) and `tabs` (which app
  tabs use the result), defined once in `pipeline.STEP_CONTEXT` and saved in `pipeline_steps.csv`. In "Pipeline & method"
  each expander title reads "Step n · data set · action → used in: tabs — rows in → out", and the steps table has the
  columns "data set" and "used in tab(s)". Steps 1–8 = accident data, C1–C2 = COVID data.
- **Why:** with only the action in the title ("Check coordinates") it was not visible which data set a step changes and
  where in the app its result can be seen – needed to point out every number "from within the app" (assignment).

### D30 · App caches follow file changes (bug fix)
- **Decided by:** Claude, after the student reported the error (2026-11-15)
- **Problem:** after D29 the pipeline was rerun while the app kept running. The app still served the old
  `pipeline_steps.csv` from its cache (`st.cache_data` without arguments never expires) and crashed with
  `KeyError: "['dataset', 'tabs'] not in index"`. All 23 tests passed, because tests start with an empty cache.
- **What changed:** every loader in `app_data.py` passes the file's modification time (`stamp()`) to the cached
  function, so a rewritten file gets a new cache entry. Two tables in the Processed Data Explorer that were read with
  `pd.read_csv` directly now use the same loader. New test file `tests/test_app_cache.py` (gap 9 in TEST_GAPS.md).
- **Alternatives:** a time-to-live on the cache (still stale for minutes, re-reads unchanged files); clearing the cache
  by hand after every pipeline run (easy to forget – exactly what went wrong).
- **Side effect:** the raw xlsx is read once more (~1 min) because its cache key changed.

---

## Added during the consistency review (2026-11-15)

### D31 · Push everything to the public GitHub repo, the course PDFs included
- **Decided by:** student (2026-11-15, asked by Claude before the first push)
- **What:** `main` + all branches pushed to https://github.com/mariacatalinamunteanu/RoadAccidentsBE (public),
  including the two Syntra/RivNox demo-case PDFs.
- **Alternatives offered:** remove the PDFs from the history before the first push; make the repo private first.
- **Impact:** the PDFs are publicly visible; to remove them later, the history must be rewritten and force-pushed.

### D32 · Keep only the Belgian Google mobility files; keep the full OxCGRT file locally ☐
- **Decided by:** Claude
- **What:** from Google's worldwide zip (98 MB) only `2020/2021/2022_BE_Region_Mobility_Report.csv` were kept, the zip
  was deleted. OxCGRT (44 MB, all countries) is kept as downloaded but not committed; step C2 writes the Belgian rows
  to `covid_measures_BEL_daily.csv`, which the app reads.
- **Why:** only Belgium is analysed; raw files are kept as downloaded where their size allows, so step C2 shows what is
  filtered (202,760 → 1,096 days).

### D33 · Interface in English, data labels in Dutch ☐
- **Decided by:** Claude
- **Why:** the student's prompts and the course material are in English; the data labels stay Dutch because the French
  columns were removed (D01) and translating labels would add an unchecked step.

### D34 · Grouping steps G1, G2, P1, C3 reported in the pipeline like the other steps
- **Decided by:** Claude, during the consistency review asked by the student
- **What changed:** building the municipalities (G1: 19,795 sectors → 581), the border-view centres (G2), the density
  table (P1: → 4,648 rows) and the monthly COVID table (C3: 289,532 accidents → 384 rows) now return a step report,
  are saved in `pipeline_steps.csv` with a sample, and appear in the "Pipeline & method" tab. For these steps
  "fewer rows out" means rows were grouped, not lost (rows_dropped = 0).
- **Why:** they were run by `run_all()` and described in `Concept.txt`, but invisible in the app; every number must be
  traceable to a visible step. `test_gaps.py::test_funnel_matches_data` now checks them.
