# Decision log

Each entry: **what** was decided, **why**, the alternatives, the **impact** in numbers, and **where** it lives.
*Decided by*: **student** = answer/instruction given in a prompt; **Claude** = proposed by Claude while building,
to be confirmed by the student (marked ☐ until confirmed).

> **Step names:** since D46 the accident steps are called **A1–A8** (before: steps 1–8). Entries D01–D45 use the
> old numbers: step *n* = A*n*.

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
- **Later changed:** D43 sets the default to 1 (all municipalities shown); 30 can still be chosen with the slider.

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

### D35 · Explanation dots (?) on every number, chart and table column
- **Decided by:** student (2026-11-15: "add explanation dots, such as in https://yunleebe.streamlit.app/, for each
  number presented"). Claude could not open the example (it redirects to a Streamlit login and needs JavaScript) and
  used Streamlit's built-in help icon (a small "?" that shows the text on hover) – to adapt if the example differs.
- **What:** 23 metrics get `help=`; the 24 charts get their title as a heading with a dot (`show_fig(..., explain=)`);
  every table shows a dot on each column header (`table()` wrapper with `COLUMN_HELP`); the two answer boxes get
  "ⓘ How is this answer computed?". One line under the app title explains how to use the dots.
- **Where the texts live:** `pipeline.EXPLANATIONS` (50 texts) and `pipeline.COLUMN_HELP` (108 columns), next to
  the steps they describe, so app and tests use the same text. Each text says what the number is, how it is
  calculated and which step creates it.
- **Why:** assignment criterion 1 ("for every number, in which step was it created?") and the no-AI conversation:
  the explanation must be visible in the app itself, not only in the log.
- **Tests:** `tests/test_explanations.py` (6 tests) + metric check in the app test (TEST_GAPS gap 10).

### D36 · Standing rule: update pipeline.py, app.py, tests, CLAUDE.md and decision_log.md after every prompt
- **Decided by:** student (2026-11-15)
- **What:** after each prompt, every one of the five files that the task affects is updated, the others are checked,
  and the answer says which needed no change. Recorded in `CLAUDE.md` (working agreements) so every session follows it.
- **Why:** these five files are the deliverables of the assignment; they must always describe the project as it is.

### D37 · Reload changed project modules in the running app (bug fix)
- **Decided by:** Claude, after the student reported the error (2026-11-15)
- **Problem:** after D35, refreshing the running app gave `AttributeError: module 'pipeline' has no attribute
  'explain'`. Streamlit reran the new `app.py` but kept the old `pipeline.py` (without `explain`) in memory. All 31
  tests passed, because each test run starts a new Python process. Same family of problem as D30 (stale cache).
- **What changed:** new `module_reload.py` with `fresh(module)`: reloads a module when its file's modification time
  changed. `app.py` calls it on `pipeline` and `app_data` at the start of every run. New
  `tests/test_module_reload.py` (gap 11 in TEST_GAPS.md).
- **Alternatives:** restart the server after every change (easy to forget, and not possible for a viewer of the
  deployed app); Streamlit's file watcher (did not reload `pipeline.py` here).
- **pipeline.py:** no change needed.

### D38 · Deployed on Streamlit Community Cloud
- **Decided by:** student (2026-11-15, assignment step 7)
- **What:** https://road-accidents-be.streamlit.app/ – deployed by the student from GitHub, branch `main`, file `app.py`,
  packages from `requirements.txt`. It redeploys after every push to `main`.
- **First problem:** "Oh no. Error running app" right after deploying; solved by the student with **Reboot app**
  (no code change). Kept as the first thing to try in `CLAUDE.md`.
- **Open risk:** the free cloud has limited memory and the Raw Data Explorer reads the 58 MB raw xlsx (D25). If the
  app runs out of memory: let the pipeline write the raw data as Parquet for the app.

### D39 · Plain-language explanation of Spearman ρ and the p-value in the answer dot (tab ❓ Density vs severity)
- **Decided by:** student (2026-11-15), text written by the student
- **What changed:** the dot after "ⓘ How is this answer computed?" (`pipeline.EXPLANATIONS["d_answer"]`) now explains,
  in short sections with bullet points and numbered steps: what the two percentages are, when the answer is "Yes",
  what Spearman ρ means (two rankings, −1 / 0 / +1, ρ = −0.50), what the p-value means (p < 0.001 = less than 1 time
  in 1,000 if there were no association) and that association is not causation.
- **Why:** the earlier text named ρ and p without explaining them; the audience of the presentation and the no-AI
  conversation need the meaning, not only the name.
- **Note:** ρ = −0.50 is the value for all years 2017–2024; with another year selection the metric above shows the
  current value. Tooltips support Markdown (headings, lists) but no real tab stops, so lists replace tabs.
- **Test:** `test_explanations.py::test_answer_dot_explains_spearman_and_p_value_in_plain_words`.

### D40 · Info point "Why Municipalities Reveal a Clearer Link …" under the heat-map title
- **Decided by:** student (2026-11-15), text written by the student
- **What changed:** directly under "Heat map – …" in tab ❓ Density vs severity: an ℹ️ line "Why Municipalities Reveal a
  Clearer Link Between Population Density and Severity Ratio" with a "?" dot. Behind the dot
  (`pipeline.EXPLANATIONS["d_why_municipalities"]`), in short sections with bullet points: municipalities keep local
  differences that are averaged away in larger areas; 581 municipalities give more observations than 11 larger areas;
  at municipal level the evidence is clearer that denser places have a smaller severe share.
- **Why:** explains to the viewer why the municipality view is the most informative of the four border views.
- **Note:** "11 larger areas" = the province view (10 provinces + Brussels); the region view has 3 units.
- **Test:** `test_explanations.py::test_why_municipalities_info_point_under_the_heat_map`. The key-check regex in
  `test_every_explanation_key_used_in_the_app_exists` now also finds `dot(...)` calls spread over two lines.

### D41 · File rules: Presentation.txt stays deleted; Prompt history.txt only pushed on request; commit only own files
- **Decided by:** student (2026-11-15)
- **What:**
  - `Presentation.txt` was deleted on purpose by the student; it is not restored or recreated (the deletion was
    committed in f25cd17).
  - `Prompt history.txt` is the student's file: Claude never changes its content and commits/pushes it only when the
    student asks. (Its latest edit was already pushed with D40, before this rule – left as it is.)
  - Claude stages only the files it changed itself (`git add <files>`), never `git add -A`, and reports other changes.
- **Why:** twice a change made by the student was committed without being asked (deletion of `Presentation.txt`,
  edit of `Prompt history.txt`). Staging named files makes that impossible.
- **Five-file check for this prompt:** `CLAUDE.md` and `decision_log.md` updated; `pipeline.py`, `app.py`, tests: no
  change needed (rules about files, no code or data change).

### D42 · One style for all info points (ℹ️ + bold title + ?)
- **Decided by:** student (2026-11-15: "Keep the formatting of the 'I' point consistent in the tab")
- **Problem:** in tab ❓ Density vs severity, "ⓘ How is this answer computed?" (small ⓘ, plain text) and
  "ℹ️ **Why Municipalities …**" (coloured ℹ️, bold) looked different, because each title carried its own icon/format.
- **What changed:** `dot()` in `app.py` now adds the icon (`INFO_ICON = "ℹ️"`) and the bold itself; call sites pass the
  plain title. All three info points (density answer, "Why Municipalities …", COVID answer) look the same.
- **Test:** `test_explanations.py::test_all_info_points_have_the_same_style` fails if a title brings its own icon or **.
- **Five-file check:** app.py, tests, CLAUDE.md (dot rule), decision_log.md updated; pipeline.py: no change needed.

### D43 · Scatter starts with all municipalities: minimum-accidents slider default 1 (was 30)
- **Decided by:** student (2026-11-15)
- **What changed:** the slider "Only municipalities with at least N accidents (small numbers = noisy ratios)" in the
  municipality view of tab ❓ Density vs severity now starts at **1**, so all 581 municipalities are in the scatter,
  its Spearman ρ and the trend line. Range stays 1–500. Replaces the default of D15 (30).
- **Effect:** at N = 1 the scatter ρ is computed over all 581 municipalities, the same set as the headline metric
  "Spearman ρ density ↔ SR (581 municipalities)"; the small, noisy municipalities are now visible by default
  (their ratios jump between 0%, 25%, 50% …) – raise N to hide them.
- **Five-file check:** app.py, tests, decision_log.md updated (+ Concept.txt); pipeline.py and CLAUDE.md: no change
  needed (no explanation text or rule mentions the default).

### D44 · Heat layer shows severe accidents by default
- **Decided by:** student (2026-11-15)
- **What changed:** the radio "Accident heat layer (GPS positions)" in tab ❓ Density vs severity starts at
  **Severe accidents** (was "All accidents"); "All accidents" and "Off" can still be chosen.
- **Made consistent with it (Claude):** the counts about the heat layer now follow the selected layer – the switch label
  ("Include severe accidents placed at the municipality centre (n)"), the caption under the map and the "Rows used"
  table count severe accidents when the severe layer is shown (before, they always counted all accidents, which would
  not match what is drawn). With "Off" the switch is disabled and the caption says the layer is off.
  `pipeline.EXPLANATIONS["d_map"]` mentions the new default.
- **Tests:** the app test checks the default and runs all three choices with the switch on and off.
- **Five-file check:** app.py, pipeline.py (text), tests, CLAUDE.md, decision_log.md updated (+ Concept.txt).

### D45 · Border view starts at Municipalities; "Why Municipalities …" info point under the border-view buttons
- **Decided by:** student (2026-11-15)
- **What changed:** in tab ❓ Density vs severity the border view starts at **Municipalities** (was Provinces), and the
  ℹ️ "Why Municipalities Reveal a Clearer Link Between Population Density and Severity Ratio" point (D40) moved from
  under the "Heat map – …" title to directly under the four border-view buttons, where the choice is made.
- **Effect:** the tab opens with 581 municipality dots, the municipality scatter (all municipalities, D43) and the
  minimum-accidents slider; the info point explains this default right next to it.
- **Tests:** the app test checks the default; `test_why_municipalities_info_point_under_the_border_view_buttons`
  checks the place (once, between the buttons and the heat-map title).
- **Five-file check:** app.py, tests, CLAUDE.md, decision_log.md updated (+ Concept.txt); pipeline.py: no change
  needed (the explanation texts did not change).

### D46 · Conclusions under every chart · own source for chart 4 · steps A1–A8 in order A, P, G, C · Pipeline tab audit
- **Decided by:** student (2026-11-15)
- **Conclusions:** every chart (24) shows "📌 Conclusion:" under its title – 1–2 sentences computed in `app.py` from the
  data of that chart, so they follow the filters (years, area, lockdown, border view). Claude rendered all 24 and read
  them against the numbers; 2 were corrected (tie MS_X/MS_Y_COORD; an unverified "until 2022" replaced by the
  measured value). Test: `test_every_chart_has_a_conclusion` (presence only – TEST_GAPS gap 12).
- **Chart 4 (tab ❓, Severity Ratio by type of collision):** has its own source line (selected years, all of Belgium,
  `pipeline.collision_group`, SR per group); chart 3 got its own line too (they shared one before).
- **Step names and order:** steps 1–8 → **A1–A8** (code, texts, samples `pipeline_samples/A1.csv`…, tests, docs).
  Shown in the order A1–A8, P1, G1, G2, C1–C3 (`pipeline.STEP_DISPLAY_ORDER`). They still RUN G1, G2, P1 first
  (A4 needs P1, A5/A6 need G1); the new column `run_order` shows that, explained under the steps table.
  Old entries of this log keep the old numbers (note at the top).
- **Pipeline & method tab checked against D01–D45 and the tests:**
  - *Where does each number come from?*: 5 rows added (conclusions, explanation dots D35, info points D39/D40/D45,
    tab defaults D43–D45, test list); step names updated.
  - *Assumptions*: step names updated; content still matches D17, D27, D28, D44.
  - *Category rules*: added heat-layer default (D44), minimum accidents (D43), border-view default (D45).
  - *Decision log & tests*: TEST_GAPS said 33 tests (now 39) → corrected; new sub-tab **All tests** reads `tests/`
    itself (`app_data.list_tests`), so it cannot fall behind (`test_pipeline_tab_lists_every_test`).
- **Five-file check:** pipeline.py, app.py (+ app_data.py), tests, CLAUDE.md, decision_log.md all updated
  (+ Concept.txt, TEST_GAPS.md).

### D47 · New main tab "📝 Prompt history" showing Prompt history.txt
- **Decided by:** student (2026-11-15)
- **What:** a fifth main tab shows the content of `Prompt history.txt`. It is **read live** from the file
  (`app_data.load_prompt_history`, path `pipeline.PROMPT_HISTORY`), not copied into the code, so the tab always shows
  the current file; it is re-read when the file changes. Shown with `st.code` (keeps line breaks and indentation,
  wraps long lines) plus the date the file last changed.
- **Never changes the file:** `tests/test_prompt_history_tab.py` checks that no code writes it; the app test checks
  that the tab shows exactly the file content (Streamlit drops only the final line break).
- **Deployed app:** shows the version of the file that is on GitHub, i.e. as of the last push.

### D48 · Prompt history.txt is included in every commit
- **Decided by:** student (2026-11-15: "Always include the prompt history.txt in the commit")
- **What:** replaces the rule of D41 that `Prompt history.txt` is pushed only on request. Claude still never changes
  its content, and still commits other files only when it changed them itself (explicit `git add`, never `git add -A`).
- **Why:** with D47 the app shows the file; committing it every time keeps the deployed tab up to date.
- **Five-file check (D47 + D48):** app.py (+ app_data.py), pipeline.py (path), tests (new file + app test),
  CLAUDE.md, decision_log.md updated (+ Concept.txt).
