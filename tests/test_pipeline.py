"""Unit tests on the pure functions of pipeline.py, with small hand-made data (fast, no files needed)."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

import pipeline as P


# ------------------------------------------------------------------ helpers
def accidents(**cols):
    base = {"DT_YEAR_COLLISION": [2019, 2019], "DT_MONTH_COLLISION": [1, 2], "CD_NIS": ["11001", "21004"],
            "TX_RGN_COLLISION_NL": ["Vlaams Gewest", P.BRUSSELS], "TX_PROV_COLLISION_NL": ["Provincie Antwerpen", None],
            "CD_CLASS_ACCIDENTS": [1, 4]}
    base.update(cols)
    return pd.DataFrame(base)


@pytest.fixture
def two_munis():
    """Two 1 km x 1 km municipalities next to each other (Lambert 72)."""
    return gpd.GeoDataFrame({"CD_NIS": ["11001", "21004"]},
                            geometry=[box(100000, 100000, 101000, 101000), box(101000, 100000, 102000, 101000)],
                            crs=31370)


# ------------------------------------------------------------------ steps
def test_drop_french_removes_only_fr_columns():
    df = accidents(TX_X_FR=["a", "b"], TX_X_NL=["c", "d"])
    out, rep = P.step_drop_french(df)
    assert "TX_X_FR" not in out and "TX_X_NL" in out
    assert rep.rows_in == rep.rows_out == 2 and rep.rows_dropped == 0


def test_fill_province_only_brussels():
    out, rep = P.step_fill_province(accidents())
    assert out.TX_PROV_COLLISION_NL.tolist() == ["Provincie Antwerpen", P.BRUSSELS]
    assert rep.rows_changed == 1


def test_fill_province_refuses_missing_province_outside_brussels():
    df = accidents(TX_RGN_COLLISION_NL=["Vlaams Gewest", "Vlaams Gewest"])
    with pytest.raises(ValueError):
        P.step_fill_province(df)


def test_add_density_keeps_all_rows_and_matches_year():
    dens = pd.DataFrame({"YEAR": [2019, 2019, 2020], "CD_NIS": ["11001", "21004", "11001"],
                         "POPULATION": [100, 200, 999], "AREA_KM2": [1.0, 2.0, 1.0], "POP_DENSITY": [100.0, 100.0, 999.0]})
    out, rep = P.step_add_density(accidents(), dens)
    assert len(out) == 2 and rep.rows_dropped == 0
    assert out.POPULATION.tolist() == [100, 200]  # 2019 rows, not 2020


def test_check_coordinates_classifies_every_case(two_munis):
    df = pd.DataFrame({"CD_NIS": ["11001"] * 5,
                       "MS_X_COORD": [100500, np.nan, 1e16, 101500, 102500],   # inside, missing, absurd, 500 m out, 1.5 km out
                       "MS_Y_COORD": [100500, np.nan, 1e15, 100500, 100500]})
    out, rep = P.step_check_coordinates(df, two_munis, tolerance_m=1000)
    assert out.COORD_STATUS.tolist() == ["ok", "missing", "out_of_range", "ok", "outside_municipality"]
    assert rep.rows_dropped == 0 and rep.rows_changed == 3


def test_impute_coordinates_uses_own_municipality_centre(two_munis):
    df = pd.DataFrame({"CD_NIS": ["11001", "21004"], "MS_X_COORD": [100500.0, np.nan], "MS_Y_COORD": [100500.0, np.nan],
                       "COORD_STATUS": ["ok", "missing"]})
    centers = pd.DataFrame({"CD_NIS": ["11001", "21004"], "CENTER_X_L72": [100500.0, 101500.0],
                            "CENTER_Y_L72": [100500.0, 100500.0]})
    out, rep = P.step_impute_coordinates(df, centers)
    assert out.loc[1, ["MS_X_COORD", "MS_Y_COORD"]].tolist() == [101500.0, 100500.0]
    assert out.COORD_IMPUTED.tolist() == [False, True] and rep.rows_changed == 1


def test_select_georeferenced_drops_only_imputed():
    df = pd.DataFrame({"COORD_IMPUTED": [False, True, False]})
    out, rep = P.step_select_georeferenced(df)
    assert len(out) == 2 and rep.rows_dropped == 1


# ------------------------------------------------------------------ density
def test_build_density_merges_old_codes_and_uses_reference_area():
    d19 = pd.DataFrame({"CD_NIS": ["72043", "11001"], "NAME_NL": ["Pelt", "Aartselaar"], "POPULATION": [33000, 14000],
                        "AREA_KM2": [83.0, 10.0], "POP_DENSITY": [397.6, 1400.0]})
    p18 = pd.DataFrame({"CD_NIS": ["72025", "72029", "11001", "02000"], "NAME": ["Neerpelt", "Overpelt", "Aartselaar", "Vlaams Gewest"],
                        "POPULATION": [17000, 15000, 14100, 6_500_000]})
    dens = P.build_density({2019: d19}, {2018: p18}, {"72043", "11001"})
    pelt18 = dens[(dens.YEAR == 2018) & (dens.CD_NIS == "72043")].iloc[0]
    assert pelt18.POPULATION == 32000                       # Neerpelt + Overpelt
    assert pelt18.POP_DENSITY == pytest.approx(32000 / 83.0, abs=0.01)
    assert set(dens.YEAR) == {2018, 2019} and len(dens) == 4  # region row (02000) not counted


def test_build_density_fails_loudly_on_unknown_municipality():
    d19 = pd.DataFrame({"CD_NIS": ["11001"], "NAME_NL": ["Aartselaar"], "POPULATION": [1], "AREA_KM2": [1.0],
                        "POP_DENSITY": [1.0]})
    p18 = pd.DataFrame({"CD_NIS": ["99999"], "NAME": ["Nowhere"], "POPULATION": [5]})
    with pytest.raises(ValueError):
        P.build_density({2019: d19}, {2018: p18}, {"11001"})


# ------------------------------------------------------------------ analysis
def test_severity_definition():
    assert P.is_severe([1, 2, 3, 4]).tolist() == [True, True, True, False]


def test_severity_ratio_handles_zero():
    r = P.severity_ratio([1, 0], [4, 0])
    assert r[0] == 25 and np.isnan(r[1])


def test_aggregate_counts_each_accident_once_per_level():
    acc = pd.DataFrame({"DT_YEAR_COLLISION": [2019] * 4, "CD_NIS": ["11001", "11001", "21004", "21004"],
                        "CD_CLASS_ACCIDENTS": [1, 4, 3, 4]})
    dens = pd.DataFrame({"YEAR": [2019, 2019], "CD_NIS": ["11001", "21004"], "POPULATION": [100, 300],
                         "AREA_KM2": [1.0, 1.0]})
    look = pd.DataFrame({"MUNICIPALITY": ["A", "B"], "PROVINCE": ["Provincie Antwerpen", P.BRUSSELS],
                         "REGION": ["Vlaams Gewest", P.BRUSSELS], "BE": "België"}, index=["11001", "21004"])
    units = pd.DataFrame({"LEVEL": ["BE"], "KEY": ["België"], "NAME": ["België"], "LAT": [50.5], "LON": [4.4]})
    be = P.aggregate_by_level(acc, dens, look, units, "BE", [2019]).iloc[0]
    assert be.ACCIDENTS == 4 and be.SEVERE == 2 and be.SEVERITY_RATIO == 50
    assert be.POP_DENSITY == 200  # (100 + 300) / (1 + 1), not the mean of densities


def test_assign_phase_boundaries():
    ph = P.assign_phase([2019, 2020, 2020, 2020, 2021, 2021, 2022], [12, 2, 3, 5, 4, 5, 3])
    assert ph.tolist() == [P.BASELINE_PHASE, "Pre-COVID", "Lockdown 1", "Lockdown 1", "Lockdown 2", "Reopening", "Post-COVID"]


def test_road_user_group_first_rule_wins():
    d = pd.DataFrame({"CD_COLLISION_TYPE": ["7", "5", "4"], "CYCLIST": [True, True, True],
                      "CD_ROAD_USR_TYPE1": [3, 3, 3], "CD_ROAD_USR_TYPE2": [9, 8, 9]})
    assert P.road_user_group(d).tolist() == ["single vehicle / obstacle", "with a pedestrian", "cyclist involved"]


def test_mix_decomposition_without_mix_change_has_no_mix_effect():
    rows = lambda sev: pd.DataFrame({"CD_BUILD_UP_AREA": [1, 2], "CD_ROAD_TYPE": [2, 3], "CD_COLLISION_TYPE": ["4", "7"],
                                     "CYCLIST": [False, False], "SEVERE": sev})
    dec = P.mix_decomposition(rows([False, True]), rows([False, False]))
    assert dec["mix_effect_pp"] == pytest.approx(0)
    assert dec["within_effect_pp"] == pytest.approx(50)
