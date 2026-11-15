"""Tests that fill the gaps of test_pipeline.py (see tests/TEST_GAPS.md).

test_pipeline.py only checks the functions on tiny hand-made data. It does NOT check that the real output files are
right, that the numbers agree with an independent calculation or with Statbel, or that the app runs. These tests do,
on the real data. They are slower (the raw xlsx takes ~1 min to read) and are skipped when the data files are absent.
Run only these:  pytest -m data
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

import pipeline as P

pytestmark = pytest.mark.data
needs = [P.RAW_ACCIDENTS, P.OUT_ACCIDENTS_PARQUET, P.OUT_DENSITY, P.OUT_CENTERS, P.OUT_UNIT_CENTERS, P.OUT_STEPS]
if not all(p.exists() for p in needs):
    pytest.skip("data files missing - run `python pipeline.py` first", allow_module_level=True)


@pytest.fixture(scope="session")
def raw():
    return P.load_raw_accidents()


@pytest.fixture(scope="session")
def proc():
    return pd.read_parquet(P.OUT_ACCIDENTS_PARQUET)


@pytest.fixture(scope="session")
def dens():
    return pd.read_csv(P.OUT_DENSITY, dtype={"CD_NIS": str}, encoding="utf-8-sig")


@pytest.fixture(scope="session")
def centers():
    return pd.read_csv(P.OUT_CENTERS, dtype={"CD_NIS": str}, encoding="utf-8-sig")


# GAP 1 - unit tests never look at the real output: no accident lost, changed or reordered
def test_processed_keeps_every_raw_accident_unchanged(raw, proc):
    assert len(proc) == len(raw)
    for col in ["DT_YEAR_COLLISION", "DT_MONTH_COLLISION", "DT_TIME", "CD_NIS", "CD_CLASS_ACCIDENTS",
                "TX_MUNTY_COLLISION_NL", "CD_COLLISION_TYPE"]:
        assert (proc[col].astype(str).values == raw[col].astype(str).values).all(), col
    assert not [c for c in proc.columns if c.endswith("_FR")]
    assert proc[["MS_X_COORD", "MS_Y_COORD", "LAT", "LON", "TX_PROV_COLLISION_NL", "POP_DENSITY"]].notna().all().all()


# GAP 2 - tests that reuse pipeline code to check pipeline code prove nothing: recompute independently from raw
def test_severity_ratio_per_province_matches_independent_calculation(raw, proc, dens, centers):
    r = raw.assign(prov=raw.TX_PROV_COLLISION_NL.fillna("Brussels Hoofdstedelijk Gewest"))
    expected = (r.CD_CLASS_ACCIDENTS <= 3).groupby(r.prov).mean() * 100  # plain pandas, no pipeline function
    units = pd.read_csv(P.OUT_UNIT_CENTERS, dtype={"KEY": str}, encoding="utf-8-sig")
    got = P.aggregate_by_level(proc, dens, P.municipality_lookup(centers), units, "Provinces", range(2017, 2025))
    got = got.set_index("KEY").SEVERITY_RATIO
    assert set(got.index) == set(expected.index)
    assert np.allclose(got.sort_index(), expected.sort_index())


# GAP 3 - "imputed" is not the same as "correct": every final coordinate must lie in its own municipality
def test_replaced_coordinates_lie_inside_their_own_municipality(proc):
    if not P.OUT_MUNI_GEOJSON.exists():
        pytest.skip("municipalities_2024.geojson missing")
    munis = gpd.read_file(P.OUT_MUNI_GEOJSON).to_crs(31370).set_index("CD_NIS")
    imp = proc[proc.COORD_IMPUTED]
    pts = gpd.GeoSeries(gpd.points_from_xy(imp.MS_X_COORD, imp.MS_Y_COORD), crs=31370, index=imp.index)
    own = gpd.GeoSeries(munis.geometry.reindex(imp.CD_NIS).values, crs=31370, index=imp.index)
    assert pts.within(own).all()
    assert proc.LAT.between(49.4, 51.6).all() and proc.LON.between(2.5, 6.5).all()


# GAP 4 - consistency between border views: every view must count the same accidents and people
def test_all_border_views_count_the_same_accidents_and_population(proc, dens, centers):
    units = pd.read_csv(P.OUT_UNIT_CENTERS, dtype={"KEY": str}, encoding="utf-8-sig")
    look = P.municipality_lookup(centers)
    totals = {lvl: P.aggregate_by_level(proc, dens, look, units, lvl, [2023])[["ACCIDENTS", "POPULATION"]].sum()
              for lvl in P.LEVELS}
    assert len({int(t.ACCIDENTS) for t in totals.values()}) == 1
    assert len({int(t.POPULATION) for t in totals.values()}) == 1
    for lvl in P.LEVELS:  # every dot has a centre
        assert P.aggregate_by_level(proc, dens, look, units, lvl, [2023])[["LAT", "LON"]].notna().all().all()


# GAP 5 - external truth: our derived population must equal Statbel's published Belgian totals
def test_population_matches_statbel_totals(dens):
    assert dens[dens.YEAR == 2017].POPULATION.sum() == 11_322_088   # Statbel, 1 January 2017
    for y in range(2019, 2025):
        be = P.load_density_sheet(y)
        assert dens[dens.YEAR == y].POPULATION.sum() == be[be.CD_NIS == "01000"].POPULATION.iloc[0]


# GAP 6 - the funnel shown in the app must agree with the data it describes
def test_funnel_matches_data(proc):
    steps = pd.read_csv(P.OUT_STEPS, dtype={"order": str}, encoding="utf-8-sig").set_index("order")
    assert steps.loc["1", "rows_in"] == len(proc)
    assert steps.loc["8", "rows_out"] == int((~proc.COORD_IMPUTED).sum())
    assert (steps.loc[[str(i) for i in range(1, 8)], "rows_dropped"] == 0).all()
    assert steps.loc["6", "rows_changed"] == int(proc.COORD_IMPUTED.sum())
    # the grouping steps are reported too, with the numbers the app relies on
    assert steps.loc["G1", "rows_out"] == proc.CD_NIS.nunique() == 581
    assert steps.loc["P1", "rows_out"] == 581 * 8
    assert steps.loc["C3", "rows_in"] == len(proc) and steps.loc["C3", "rows_out"] == 4 * 96


# GAP 7 - the COVID baseline: 'normal' must be the plain 2017-2019 average of that month
def test_covid_baseline_is_three_year_average(proc):
    mon = pd.read_csv(P.OUT_COVID_MONTHLY, encoding="utf-8-sig")
    april = proc[(proc.DT_MONTH_COLLISION == 4) & proc.DT_YEAR_COLLISION.isin([2017, 2018, 2019])]
    row = mon[(mon.AREA == "België") & (mon.YEAR == 2020) & (mon.MONTH == 4)].iloc[0]
    assert row.BASE_ACCIDENTS == pytest.approx(len(april) / 3, abs=0.05)


# GAP 8 - unit tests never start the app: every tab and button must run without an exception
@pytest.mark.slow
def test_app_runs_every_tab_and_button():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(P.ROOT / "app.py"), default_timeout=600).run()
    assert not at.exception, [e.value for e in at.exception]
    # every metric on screen carries an explanation dot (decision D35)
    assert len(at.metric) >= 20 and all(m.help for m in at.metric), [m.label for m in at.metric if not m.help]
    assert at.radio(key="heat_mode").value == "Severe accidents"  # default heat layer (decision D44)
    assert at.segmented_control(key="level").value == "Municipalities"  # default border view (decision D45)
    at.toggle(key="heat_imputed").set_value(True).run()
    assert not at.exception, [e.value for e in at.exception]
    for mode in ["All accidents", "Off", "Severe accidents"]:
        at.radio(key="heat_mode").set_value(mode).run()
        assert not at.exception, (mode, [e.value for e in at.exception])
    at.toggle(key="heat_imputed").set_value(False).run()
    assert not at.exception, [e.value for e in at.exception]
    for lvl in ["Regions", "Municipalities", "BE", "Provinces"]:
        at.segmented_control(key="level").set_value(lvl).run()
        assert not at.exception, (lvl, [e.value for e in at.exception])
    for area in ["Flanders", "Wallonia", "Brussels"]:
        at.segmented_control(key="covid_area").set_value(area).run()
        assert not at.exception, (area, [e.value for e in at.exception])
    at.radio(key="cv_phase").set_value("Lockdown 2").run()
    at.radio(key="cv_y").set_value("Severity Ratio vs normal (pp)").run()
    assert not at.exception
