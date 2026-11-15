"""Cached loaders for the Streamlit app. All logic lives in pipeline.py; this file only reads files and caches."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

import pipeline as P

DECISION_LOG = P.ROOT / "decision_log.md"
TEST_GAPS = P.ROOT / "tests" / "TEST_GAPS.md"

CODE_LABEL = {
    "CD_CROSSWAY": "TX_CROSSWAY_NL", "CD_WEATHER": "TX_WEATHER_NL", "CD_ROAD_CONDITION": "TX_ROAD_CONDITION_NL",
    "CD_BUILD_UP_AREA": "TX_BUILD_UP_AREA_NL", "CD_LIGHT_CONDITION": "TX_LIGHT_CONDITION_NL",
    "CD_ROAD_TYPE": "CD_ROAD_TYPE_NL", "CD_CLASS_ACCIDENTS": "TX_CLASS_ACCIDENTS_NL",
    "CD_ROAD_USR_TYPE1": "TX_ROAD_USR_TYPE1_NL", "CD_ROAD_USR_TYPE2": "TX_ROAD_USR_TYPE2_NL",
    "CD_COLLISION_TYPE": "TX_COLLISION_TYPE_NL", "CD_OBSTACLES": "TX_OBSTACLES_NL", "CD_NIS": "TX_MUNTY_COLLISION_NL",
}


def _csv(path, **kw):
    return pd.read_csv(path, encoding="utf-8-sig", **kw)


@st.cache_data(show_spinner="Loading raw accident file (first time ~1 min, then cached)...", persist="disk")
def load_raw():
    return P.load_raw_accidents()


@st.cache_data(show_spinner=False)
def load_var_list():
    v = pd.read_excel(P.VAR_LIST)
    v.columns = [str(c).strip() for c in v.columns]
    return v


@st.cache_data(show_spinner="Loading processed accident data...")
def load_processed():
    return pd.read_parquet(P.OUT_ACCIDENTS_PARQUET)


@st.cache_data(show_spinner=False)
def load_density():
    return _csv(P.OUT_DENSITY, dtype={"CD_NIS": str})


@st.cache_data(show_spinner=False)
def load_centers():
    return _csv(P.OUT_CENTERS, dtype={"CD_NIS": str})


@st.cache_data(show_spinner=False)
def load_lookup():
    return P.municipality_lookup(load_centers())


@st.cache_data(show_spinner=False)
def load_unit_centers():
    return _csv(P.OUT_UNIT_CENTERS, dtype={"KEY": str})


@st.cache_data(show_spinner=False)
def load_outline(level):
    return json.loads(Path(str(P.OUT_OUTLINES).format(level=level)).read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_steps():
    return _csv(P.OUT_STEPS, dtype={"order": str})


@st.cache_data(show_spinner=False)
def load_sample(order):
    f = P.SAMPLES / f"{order}.csv"
    return _csv(f) if f.exists() else None


@st.cache_data(show_spinner=False)
def load_coords_by_year():
    return _csv(P.OUT_MISSING_BY_YEAR)


@st.cache_data(show_spinner=False)
def load_log():
    return P.OUT_LOG.read_text(encoding="utf-8") if P.OUT_LOG.exists() else ""


@st.cache_data(show_spinner=False)
def load_markdown(path):
    return Path(path).read_text(encoding="utf-8") if Path(path).exists() else f"*{Path(path).name} not found*"


@st.cache_data(show_spinner=False)
def load_covid_monthly():
    return _csv(P.OUT_COVID_MONTHLY, parse_dates=["DATE"])


@st.cache_data(show_spinner=False)
def load_covid_phases():
    return _csv(P.OUT_COVID_PHASES)


@st.cache_data(show_spinner=False)
def load_mobility_raw():
    return P.load_mobility()


@st.cache_data(show_spinner=False)
def load_measures_bel():
    return _csv(P.OUT_MEASURES_BEL)


@st.cache_data(show_spinner="Preparing COVID columns...")
def load_covid_accidents():
    return P.add_covid_columns(load_processed())


# ------------------------------------------------------------------ raw data quality
@st.cache_data(show_spinner="Checking coordinates...")
def raw_coordinate_status():
    """Coordinate status of each raw row (raw and processed rows are in the same order; checked here)."""
    raw, p = load_raw(), load_processed()
    if len(raw) != len(p) or not (raw.DT_YEAR_COLLISION.values == p.DT_YEAR_COLLISION.values).all():
        raise ValueError("Raw and processed accident rows are not aligned - rerun pipeline.py")
    status = p.COORD_STATUS.copy()
    status[(status == "ok") & (p.DIST_TO_OWN_MUNTY_M > 0)] = "0-1 km outside municipality (kept)"
    return status.replace({"ok": "inside own municipality", "missing": "missing",
                           "out_of_range": "out of Belgian range",
                           "outside_municipality": "> 1 km outside municipality"})


@st.cache_data(show_spinner="Running quality checks...")
def raw_quality():
    raw = load_raw()
    n = len(raw)
    res = {}
    miss = raw.isna().sum()
    res["missing"] = (pd.DataFrame({"column": miss.index, "missing": miss.values,
                                    "missing %": (miss.values / n * 100).round(2)})
                      .query("missing > 0").sort_values("missing", ascending=False))
    res["unknown"] = pd.DataFrame([
        {"column": c, "codes meaning unknown": ", ".join(map(str, codes)), "rows": int(raw[c].isin(codes).sum()),
         "% of rows": round(raw[c].isin(codes).mean() * 100, 2)} for c, codes in P.UNKNOWN_CODES.items()
    ]).sort_values("rows", ascending=False)
    res["code_label"] = pd.DataFrame([
        {"code column": c, "label column": t, "codes with >1 label": int((raw.groupby(c)[t].nunique() > 1).sum()),
         "labels with >1 code": int((raw.groupby(t)[c].nunique() > 1).sum())} for c, t in CODE_LABEL.items()])

    st_ = raw_coordinate_status()
    issues = []

    def add(category, column, issue, count, action):
        issues.append({"category": category, "column": column, "issue": issue,
                       "rows": int(count) if count is not None else None, "handling": action})

    add("Missing", "TX_PROV_COLLISION_NL / _FR", "Province empty: all rows are in the Brussels Capital Region "
        "(Brussels has no province)", raw.TX_PROV_COLLISION_NL.isna().sum(), "Step 3: filled with 'Brussels Hoofdstedelijk Gewest'")
    add("Missing", "MS_X_COORD / MS_Y_COORD", "Coordinates missing", raw.MS_X_COORD.isna().sum(),
        "Step 6: municipality centre; step 8: excluded from GPS map")
    oor = raw.MS_X_COORD.notna() & ~(raw.MS_X_COORD.between(*P.LAMBERT_RANGE) & raw.MS_Y_COORD.between(*P.LAMBERT_RANGE))
    add("Incorrect", "MS_X_COORD / MS_Y_COORD", "Coordinates impossible (order of 1e15-1e16, outside Belgium)",
        oor.sum(), "Step 6: municipality centre; step 8: excluded from GPS map")
    add("Incorrect", "MS_X_COORD / MS_Y_COORD", "Point lies > 1 km outside the municipality given in CD_NIS",
        (st_ == "> 1 km outside municipality").sum(), "Step 6: municipality centre; step 8: excluded from GPS map")
    add("Inconsistent (minor)", "MS_X_COORD / MS_Y_COORD", "Point lies 0-1 km outside its municipality "
        "(typically border roads)", (st_ == "0-1 km outside municipality (kept)").sum(), "Kept")
    add("Incorrect", "DT_TIME", "Hour = 99 (not a valid hour 0-23)", (~raw.DT_TIME.between(0, 23)).sum(),
        "Kept; treated as unknown hour")
    add("Duplicates", "all columns", "Rows identical in all 45 columns (may be genuine separate accidents: "
        "the data is aggregated to hour level)", raw.duplicated().sum(), "Kept")
    add("Inconsistent", "TX_ROAD_CONDITION_NL", "Label typo 'Ijzel, sneeuw+ roper' (should be '+Proper')",
        raw.TX_ROAD_CONDITION_NL.str.contains(r"\+ roper", na=False).sum(), "Kept (label only)")
    add("Inconsistent", "CD_OBSTACLES", "Code -1 has label 'Geen vermelding van de type aanrijding' "
        "(a collision-type label, not an obstacle)", (raw.CD_OBSTACLES == -1).sum(), "Treated as unknown")
    add("Inconsistent", "CD_ROAD_USR_TYPE2", "Codes 10/11 are not road-user types but crash situations",
        raw.CD_ROAD_USR_TYPE2.isin([10, 11]).sum(), "Kept")
    multi = raw.CD_WEATHER.str.contains("/", na=False) | raw.CD_ROAD_CONDITION.str.contains("/", na=False)
    add("Inconsistent", "CD_WEATHER / CD_ROAD_CONDITION", "Combined codes such as '2/4' (several values in one field)",
        multi.sum(), "Kept; read as text")
    add("Inconsistent", "CD_COLLISION_TYPE", "Mixed numeric and letter codes (code 'A')",
        (raw.CD_COLLISION_TYPE == "A").sum(), "Read as text")
    lower = [c for c in raw.columns if c.endswith("_NL") and (raw[c] == "onbekend").any()]
    upper = [c for c in raw.columns if c.endswith("_NL") and (raw[c] == "Onbekend").any()]
    add("Inconsistent", ", ".join(lower + upper), "'unknown' spelled 'onbekend' in some columns and 'Onbekend' in "
        "others; label capitalisation varies", None, "Kept")
    add("Naming", "CD_ROAD_TYPE_FR / CD_ROAD_TYPE_NL", "Prefix CD_ (code) but the columns hold text labels", None, "Kept")
    add("Naming", "TX_COLLISON_TYPE_FR", "Typo in column name (COLLISON)", None, "Step 2: removed (FR)")
    add("Metadata", "VAR_LIST", "Declares all codes as 'Char'; the file stores most as numbers. Header 'Lenght' "
        "is misspelt", None, "-")
    res["issues"] = pd.DataFrame(issues)

    text_cols = [c for c in raw.columns if raw[c].dtype == object or str(raw[c].dtype).startswith("str")]
    res["checks"] = pd.DataFrame([
        ("Every CD_NIS has exactly one municipality name", int((raw.groupby("CD_NIS").TX_MUNTY_COLLISION_NL.nunique() > 1).sum()) == 0),
        ("Every CD_NIS belongs to exactly one region", int((raw.groupby("CD_NIS").TX_RGN_COLLISION_NL.nunique() > 1).sum()) == 0),
        ("Months are 1-12", bool(raw.DT_MONTH_COLLISION.between(1, 12).all())),
        ("Years are 2017-2024", bool(raw.DT_YEAR_COLLISION.between(2017, 2024).all())),
        ("No empty strings / leading or trailing spaces in text columns",
         all(((s := raw[c].dropna().astype(str)) == s.str.strip()).all() and (s != "").all() for c in text_cols)),
        ("Accident class has only codes 1-4", bool(raw.CD_CLASS_ACCIDENTS.isin([1, 2, 3, 4]).all())),
    ], columns=["check", "passed"])
    return res
