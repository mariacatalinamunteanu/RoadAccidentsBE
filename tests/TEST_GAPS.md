# What do the AI-written tests NOT test – and what we did about it

`tests/test_pipeline.py` contains the unit tests written with the AI: 15 tests, each function of `pipeline.py` on a
few hand-made rows. They all pass in under a second. Then we asked: **what does this not test?**

| # | Gap in the unit tests | Why it matters | Test added (`tests/test_gaps.py`) | Result |
|---|---|---|---|---|
| 1 | They never look at the **real output file**. A step can work on 2 toy rows and still lose, reorder or change rows on 289,532 real ones. | The whole app relies on processed rows = raw rows. | `test_processed_keeps_every_raw_accident_unchanged`: same number and order of rows, key columns identical to the raw file, no FR columns, no empty key cells. | ✅ |
| 2 | Tests that call pipeline code to check pipeline code are **circular**: a wrong definition gives a wrong expected value. | The Severity Ratio is the core number of the app. | `test_severity_ratio_per_province_matches_independent_calculation`: SR per province recomputed in plain pandas from the **raw xlsx**, compared with `aggregate_by_level`. | ✅ |
| 3 | "Coordinate replaced" ≠ "coordinate correct". The unit test only checks that a value was written. | A wrong centre would put accidents in the wrong municipality on the map. | `test_replaced_coordinates_lie_inside_their_own_municipality`: all 36,628 replaced points lie **inside** their own municipality polygon; all points inside Belgium. | ✅ |
| 4 | Each border view is tested alone, never **against each other**. | Regions, provinces, municipalities and BE must count the same accidents and people, otherwise the views contradict each other. | `test_all_border_views_count_the_same_accidents_and_population` + every dot has a centre. | ✅ |
| 5 | No test against an **external truth**. | Our 2017–2018 density is derived (code mapping); an error would not show in a unit test. | `test_population_matches_statbel_totals`: Belgian population 2017 = 11,322,088 (Statbel) and 2019–2024 = Statbel's Belgium row. | ✅ |
| 6 | Nothing checks that what the **app tells** about the data is true. | The funnel and step expanders are read from `pipeline_steps.csv`; if that file is stale, the app lies. | `test_funnel_matches_data`: funnel numbers = counts in the processed data. | ✅ |
| 7 | The COVID "normal" was only tested with a toy phase. | All COVID conclusions compare to "normal". | `test_covid_baseline_is_three_year_average`: April 2020's normal = (April 2017+2018+2019) / 3. | ✅ |
| 9 | Every test starts with an **empty cache**, so none can see that a **running** app keeps serving an old file after `pipeline.py` rewrote it. Found the hard way: after a pipeline rerun the app crashed with `KeyError: "['dataset', 'tabs'] not in index"` while all 23 tests passed. | The app is kept running during a demo while the data is rebuilt. | `tests/test_app_cache.py`: a file is rewritten between two reads in the same process → the new columns must appear; an unchanged file must come from the cache. Fix: every cache in `app_data.py` is keyed on the file's modification time. | ✅ |
| 10 | Nothing checks that **every number is explained**. A new metric or chart without an explanation dot, or a dot pointing to a missing text, would go unnoticed. | Assignment: you must explain every number from within the app. | `tests/test_explanations.py` reads `app.py` as code: every `metric` has `help`, every chart has `explain`, every table goes through `table()` (column dots), every key exists in `pipeline.EXPLANATIONS` and none is unused, columns of the pipeline outputs have `COLUMN_HELP`. The app test checks that every metric on screen has a non-empty help text. | ✅ |
| 11 | Every test starts a **new Python process**, so none can see that a running server keeps an **old `pipeline.py`** in memory after the code changed. Found for real: `AttributeError: module 'pipeline' has no attribute 'explain'` after a refresh, while all 31 tests passed. | Code changes are made while the app runs (also on Streamlit Cloud after every push). | `tests/test_module_reload.py`: a module file is changed inside one process → `module_reload.fresh()` must reload it; an unchanged module must not be reloaded. Fix: `app.py` calls `fresh()` on `pipeline` and `app_data` at every run. | ✅ |
| 8 | Unit tests never **start the app**. | A renamed column or file breaks the dashboard without any failing unit test. | `test_app_runs_every_tab_and_button`: runs the app headlessly and clicks every border view, area and radio button. | ✅ |

Run: `python -m pytest` (all, 33 tests) · `python -m pytest -m "not data"` (fast unit tests only) · `python -m pytest -m data`.

## Still not tested automatically (checked by hand)
- **Whether the charts are readable and correct to the eye**: colours, dot sizes, map position. AppTest only checks
  that no error occurs, not what is drawn. → Checked manually in the browser before every presentation.
- **Whether the explanations ("Why") are true**: e.g. "higher speeds in Lockdown 1" cannot be tested with this data
  (no speed column). → Stated as a hypothesis in the app.
- **Statistical robustness**: e.g. the result with another tolerance than 1 km or another baseline. → Possible
  follow-up: a sensitivity test that reruns the analysis with 500 m / 5 km.
- **Deploy environment** (Streamlit Community Cloud, package versions). → To check after the first deploy.
