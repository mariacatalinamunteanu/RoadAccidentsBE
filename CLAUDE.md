# CLAUDE.md – Project 1.1 · Road accidents in Belgium 2017–2024

Project agreements. Every session (human or AI) follows these. If an agreement changes, change it here,
in `pipeline.py` (constants at the top) and add an entry to `decision_log.md`.

## Questions answered
1. *Is it true that as the density of the population increases, the severity of the accidents decreases? Why?* (tab 2)
2. *Did the COVID-19 lockdowns make road accidents fewer but more severe? Why?* (tab 3)

## Structure
| File | Role |
|---|---|
| `pipeline.py` | **All** data logic: one pure function per step, no Streamlit. `python pipeline.py` rebuilds every processed file. |
| `app.py` | Streamlit app (`streamlit run app.py`). Shows data, never computes new data rules itself. |
| `app_data.py` | Cached file loaders for the app only. |
| `module_reload.py` | `fresh()`: reloads `pipeline.py` / `app_data.py` in a running app when the file changed. |
| `tests/` | `test_pipeline.py` (15 unit tests, fast) · `test_gaps.py` (8 tests on real data, `-m data`) · `test_app_cache.py` (2, app cache) · `test_explanations.py` (6, explanation dots) · `test_module_reload.py` (2, reload of changed modules) · `TEST_GAPS.md` (what the tests miss) |
| `pytest.ini`, `requirements.txt` | Test settings; packages for Streamlit Community Cloud. |
| `decision_log.md` | What was decided, why, alternatives, impact. |
| `Concept.txt` | Design: four pillars, sub-questions, categories, columns, filters, steps, drawing of every tab. |
| `Data/Raw Data/` | Downloaded files, **never edited** (by hand or code). Exception: `Geo/municipality_centers_2024.csv` and `Geo/municipalities_2024.geojson` are written by `pipeline.py` (step G1), because the student asked for the centres in that folder. |
| `Data/Processed Data/` | Everything else written by `pipeline.py`. Safe to delete and rebuild. |
| `Claude work log.txt` | Chronological history of every task. |
| `Mission statement.txt`, `Progress.txt`, `Prompt history.txt`, `Project 1 - demo-case *.pdf` | The student's own notes and the course assignment (not edited by Claude; `Prompt history.txt` is committed only on request). |

## Pipeline steps (pipeline_steps.csv, shown in the app)
G1 municipalities + centres · G2 regions/provinces/BE centres + borders · P1 population density ·
1 load accidents · 2 drop FR · 3 Brussels province · 4 add density · 5 check coordinates · 6 replace by centre ·
7 lat/lon · 8 heat-layer view (not saved) · C1 mobility · C2 measures · C3 monthly COVID table.
G1, G2, P1 and C3 group rows (nothing lost); only C1 and C2 really drop rows (other provinces / countries).

## Data agreements
- **Language:** Dutch only. All `_FR` columns are dropped (step 2).
- **Severe accident:** `CD_CLASS_ACCIDENTS` in {1, 2, 3} (deaths, fatally injured, seriously injured). Class 4 = not severe.
- **Severity Ratio** = severe accidents / all injury accidents × 100. Each accident counts once.
- **Only injury accidents** are in the data. Never call a place "the most dangerous" based on counts; say "injury accidents".
- **Denominator:** we do not rank places by accident counts. Population per municipality (Statbel) is used for density
  and accidents per 1,000 inhabitants. There is no traffic-volume data: never claim "risk per km driven".
- **Brussels province:** empty `TX_PROV_COLLISION_NL` → `"Brussels Hoofdstedelijk Gewest"` (step 3). Must only happen in Brussels.
- **Missing / abnormal coordinates:** missing, outside the Belgian Lambert range, or more than **1,000 m** outside the
  municipality in `CD_NIS` → replaced by the **municipality centre** (step 6) and flagged `COORD_IMPUTED = True`.
  - They **stay in all counts and ratios** (grouped by municipality code).
  - In the GPS heat layer they are **left out by default** (step 8); a switch on the map ("Include accidents placed at
    the municipality centre") draws them at the centre. The app always says how many are left out or placed on centres.
  - Step 8 never removes rows from the data set.
  - 0–1,000 m outside the municipality = kept (border roads).
- **Municipality centre:** centroid of the polygon; representative point if the centroid falls outside (5 cases).
- **Municipalities:** the 581 post-2019 municipalities (NIS codes as in the accident data). 2017–2018 population is
  mapped to these codes (`MERGERS_2019` + renaming by name).
- **Population density** = population on 1 January / area, same year as the accident. For province/region/BE:
  Σ population / Σ area (never the mean of municipal densities).
- **Unknown codes** (9, 99, 0, -1, -3 – see `UNKNOWN_CODES`) are kept as their own category, never silently dropped.
  If a chart leaves them out, the chart says how many.
- **Duplicates** (66 identical rows) are kept: the data is at hour level, so they can be different accidents.
- **COVID:** phases by month (`COVID_PHASES`); "normal" = average of the same calendar month 2017–2019.
- **Category rules per chart** live in `pipeline.CATEGORY_RULES` and are shown in the app. Add a rule there for
  every new chart category.

## Working agreements
- **Every number in the app shows its source** (`src(...)` caption: pipeline step / function).
- **Every number has an explanation dot (?)**: `help=E("key")` on every `metric`, `explain="key"` on every
  `show_fig`, `table(...)` instead of `st.dataframe` (dots on column headers), `dot("Plain title", "key")` for info points
  (one style everywhere: ℹ️ + bold title + ?, added by `dot()` – never put an icon or ** in the title).
  The texts live in `pipeline.EXPLANATIONS` and `pipeline.COLUMN_HELP` (what it is, how it is calculated, which
  step). A new number without a text fails `tests/test_explanations.py`.
- **Rows that drop out are shown** (row funnel at the top of the tab "Pipeline & method", step expanders,
  "Rows used in this tab"). The "only injury accidents" statement is the first item of the Assumptions box in
  both question tabs (tab 2 and tab 3).
- New logic goes in `pipeline.py` as a pure function, with a test in `tests/`.
- Every cached loader in `app_data.py` is keyed on the file's modification time (`stamp()`), so a running app
  picks up files rewritten by `pipeline.py`. Never add `@st.cache_data` on a loader without a file stamp argument.
- `app.py` passes every project module it imports through `module_reload.fresh()`, so a running server never mixes a
  new `app.py` with an old `pipeline.py`. A new project module must be added there too.
- Run `python -m pytest` (fast) and `python -m pytest -m data` (real data) before merging into `main`.
- Work on a branch, merge into `main` with `--no-ff`. Commit messages say what and why.
- **Commit only the files Claude changed**: `git add <file> ...` with explicit names, never `git add -A`. First run
  `git status` and report any other changed or deleted file instead of committing it (lessons: the deletion of
  `Presentation.txt` was committed unnoticed in f25cd17; an edit of `Prompt history.txt` was pushed with D40).
- **`Prompt history.txt`**: the student's file. Claude never changes its content, and commits/pushes it **only when
  the student asks**. Otherwise it is treated like every other project file (read it when useful).
- **`Presentation.txt`** was deleted by the student on purpose (2026-11-15): do not restore or recreate it.
- Large files (> 40 MB) are not committed (see `.gitignore`); they are downloaded or rebuilt by `pipeline.py`.
- **After every prompt** (student's standing instruction, 2026-11-15): update `pipeline.py`, `app.py`, `tests/`,
  `CLAUDE.md` and `decision_log.md` so they reflect what was done – change each file the task affects, check the
  others, and say in the answer which of the five needed no change. Also append an entry to `Claude work log.txt`.
- Before building something new: ask a question wherever an assumption would otherwise be made, and record the answer
  in `decision_log.md`.
- UI language: English; data labels stay Dutch.

## Repository and deploy
- Public app (Streamlit Community Cloud, branch `main`, file `app.py`): https://road-accidents-be.streamlit.app/
  It redeploys by itself after every push to `main`. If it shows "Oh no. Error running app": Manage app → ⋮ →
  **Reboot app** first; if that does not help, read the log (Manage app) before changing code.
- GitHub: https://github.com/mariacatalinamunteanu/RoadAccidentsBE (public). `main` is the deployed branch;
  push feature branches too, so the branch history stays visible.

## How to run
```
python pipeline.py          # rebuild processed data (~3 min)
python -m pytest            # unit tests + data tests (data tests need the files; ~3 min)
streamlit run app.py        # app on http://localhost:8501
```
