"""Every number in the app must have an explanation dot (see CLAUDE.md, decision D35).

These tests read app.py as code (no data needed, fast): a new metric or chart without an explanation, or an
explanation key that does not exist, fails the test suite."""
import ast
import re
from dataclasses import fields

import pandas as pd
import pytest

import pipeline as P

APP = (P.ROOT / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(APP)


def calls(name):
    """All calls x.<name>(...) or <name>(...) in app.py."""
    out = []
    for node in ast.walk(TREE):
        if isinstance(node, ast.Call):
            f = node.func
            if (isinstance(f, ast.Attribute) and f.attr == name) or (isinstance(f, ast.Name) and f.id == name):
                out.append(node)
    return out


def test_every_metric_has_an_explanation_dot():
    metrics = calls("metric")
    assert len(metrics) >= 20
    missing = [ast.get_source_segment(APP, m)[:60] for m in metrics if "help" not in {k.arg for k in m.keywords}]
    assert not missing, missing


def test_every_chart_has_an_explanation_dot():
    charts = calls("show_fig")
    assert len(charts) >= 24
    missing = [ast.get_source_segment(APP, c)[:60] for c in charts if "explain" not in {k.arg for k in c.keywords}]
    assert not missing, missing


def test_every_table_goes_through_the_column_help_wrapper():
    # st.dataframe may only be called inside table(); everything else must use table()
    direct = [n for n in calls("dataframe") if isinstance(n.func, ast.Attribute)]
    assert len(direct) == 1, "use table(...) instead of st.dataframe(...) so column headers get explanation dots"


def test_every_explanation_key_used_in_the_app_exists():
    used = set(re.findall(r'(?:explain=|E\(|dot\([^,]+,\s*)"([a-z0-9_]+)"', APP))  # \s*: calls may span lines
    used |= {f"status_{s}" for s in ["ok", "missing", "out_of_range", "outside_municipality"]}  # E(f"status_{...}")
    assert used, "no explanation keys found"
    assert not used - set(P.EXPLANATIONS), used - set(P.EXPLANATIONS)
    assert not set(P.EXPLANATIONS) - used, f"unused explanations: {set(P.EXPLANATIONS) - used}"


def test_explanations_are_real_sentences():
    for k, t in P.EXPLANATIONS.items():
        assert len(t) >= 40, k
    with pytest.raises(KeyError):
        P.explain("does_not_exist")


def test_answer_dot_explains_spearman_and_p_value_in_plain_words():
    # decision D39: the student's explanation of rho and p, as an easy-to-read list
    t = P.EXPLANATIONS["d_answer"]
    for must in ["compares two rankings", "−1", "+1", "ρ = −0.50", "p < 0.001", "1 time in 1,000",
                 "association", "causes"]:
        assert must in t, must
    assert t.count("\n- ") >= 8 and "\n1. " in t  # bullet points and numbered steps, not one long sentence


def test_why_municipalities_info_point_under_the_heat_map():
    # decision D40: info point under the heat-map title, with the student's explanation behind its "?"
    assert 'dot("ℹ️ **Why Municipalities Reveal a Clearer Link Between Population Density and Severity Ratio**"' in APP
    assert APP.index("#### Heat map –") < APP.index("d_why_municipalities") < APP.index('explain="d_map"')
    t = P.EXPLANATIONS["d_why_municipalities"]
    for must in ["more informative scale", "averaged away", "581 municipalities", "11 larger areas",
                 "smaller share of severe crashes"]:
        assert must in t, must
    assert t.count("\n- ") >= 4


def test_columns_of_the_pipeline_outputs_have_column_help():
    step_cols = [f.name for f in fields(P.StepReport)]
    acc = pd.DataFrame({"DT_YEAR_COLLISION": [2019], "CD_NIS": ["11001"], "CD_CLASS_ACCIDENTS": [1],
                        "POP_DENSITY": [300.0], "CD_BUILD_UP_AREA": [2], "CD_COLLISION_TYPE": ["7"],
                        "CD_LIGHT_CONDITION": [4], "CD_ROAD_TYPE": [3], "COORD_STATUS": ["ok"]})
    dens = pd.DataFrame({"YEAR": [2019], "CD_NIS": ["11001"], "POPULATION": [100], "AREA_KM2": [1.0]})
    look = pd.DataFrame({"MUNICIPALITY": ["A"], "PROVINCE": ["P"], "REGION": ["R"], "BE": "België"}, index=["11001"])
    units = pd.DataFrame({"LEVEL": ["Municipalities"], "KEY": ["11001"], "NAME": ["A"], "LAT": [51.0], "LON": [4.0]})
    agg = P.aggregate_by_level(acc, dens, look, units, "Municipalities", [2019])
    shown_agg = ["NAME", "POPULATION", "AREA_KM2", "POP_DENSITY", "ACCIDENTS", "ACCIDENTS_PER_1000_INH_YEAR", "SEVERE",
                 "DEATHS", "SEVERITY_RATIO", "LAT", "LON"]
    assert set(shown_agg) <= set(agg.columns)
    prof = P.density_class_profile(acc)
    cby = P.coordinates_by_year(acc)
    for col in step_cols + shown_agg + list(prof.columns) + list(cby.columns):
        assert col in P.COLUMN_HELP, col
    if P.OUT_COVID_MONTHLY.exists():
        mon_cols = pd.read_csv(P.OUT_COVID_MONTHLY, nrows=1, encoding="utf-8-sig").columns
        assert not [c for c in mon_cols if c not in P.COLUMN_HELP and c != "SEVERITY_RATIO"], \
            [c for c in mon_cols if c not in P.COLUMN_HELP]
