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


# Every cache below is keyed on the file's modification time ("stamp"). When pipeline.py rewrites a file while the
# app is running, the stamp changes and the file is read again - otherwise the app keeps serving the old version
# (that caused: KeyError "['dataset', 'tabs'] not in index" after the pipeline was rerun, see decision_log D30).
def stamp(*paths):
    """Modification times (ns) of the given files; 0 for a missing file."""
    return tuple(Path(x).stat().st_mtime_ns if Path(x).exists() else 0 for x in paths)


@st.cache_data(show_spinner=False)
def _csv_cached(path, file_stamp, dtype=None, parse_dates=None):
    return pd.read_csv(path, encoding="utf-8-sig", dtype=dtype, parse_dates=parse_dates)


def read_csv(path, dtype=None, parse_dates=None):
    return _csv_cached(str(path), stamp(path), dtype=dtype, parse_dates=parse_dates)


@st.cache_data(show_spinner=False)
def _text_cached(path, file_stamp):
    return Path(path).read_text(encoding="utf-8") if Path(path).exists() else None


def read_text(path):
    return _text_cached(str(path), stamp(path))


@st.cache_data(show_spinner="Loading raw accident file (first time ~1 min, then cached)...", persist="disk")
def _raw_cached(file_stamp):
    return P.load_raw_accidents()


def load_raw():
    return _raw_cached(stamp(P.RAW_ACCIDENTS))


@st.cache_data(show_spinner=False)
def _var_list_cached(file_stamp):
    v = pd.read_excel(P.VAR_LIST)
    v.columns = [str(c).strip() for c in v.columns]
    return v


def load_var_list():
    return _var_list_cached(stamp(P.VAR_LIST))


@st.cache_data(show_spinner="Loading processed accident data...")
def _processed_cached(file_stamp):
    return pd.read_parquet(P.OUT_ACCIDENTS_PARQUET)


def load_processed():
    return _processed_cached(stamp(P.OUT_ACCIDENTS_PARQUET))


def load_density():
    return read_csv(P.OUT_DENSITY, dtype={"CD_NIS": str})


def load_centers():
    return read_csv(P.OUT_CENTERS, dtype={"CD_NIS": str})


@st.cache_data(show_spinner=False)
def _lookup_cached(file_stamp):
    return P.municipality_lookup(load_centers())


def load_lookup():
    return _lookup_cached(stamp(P.OUT_CENTERS))


def load_unit_centers():
    return read_csv(P.OUT_UNIT_CENTERS, dtype={"KEY": str})


def load_outline(level):
    text = read_text(str(P.OUT_OUTLINES).format(level=level))
    return json.loads(text)


def load_steps():
    return read_csv(P.OUT_STEPS, dtype={"order": str})


def load_sample(order):
    f = P.SAMPLES / f"{order}.csv"
    return read_csv(f) if f.exists() else None


def load_coords_by_year():
    return read_csv(P.OUT_MISSING_BY_YEAR)


def load_log():
    return read_text(P.OUT_LOG) or ""


def load_markdown(path):
    return read_text(path) or f"*{Path(path).name} not found*"


def load_prompt_history():
    """Content of the student's Prompt history.txt, read live (re-read when the file changes). Never written."""
    return read_text(P.PROMPT_HISTORY)


def load_covid_monthly():
    return read_csv(P.OUT_COVID_MONTHLY, parse_dates=["DATE"])


def load_covid_phases():
    return read_csv(P.OUT_COVID_PHASES)


@st.cache_data(show_spinner=False)
def _mobility_cached(file_stamp):
    return P.load_mobility()


def load_mobility_raw():
    return _mobility_cached(stamp(*sorted(P.RAW_MOBILITY_DIR.glob("*_BE_Region_Mobility_Report.csv"))))


def load_measures_bel():
    return read_csv(P.OUT_MEASURES_BEL)


@st.cache_data(show_spinner="Preparing COVID columns...")
def _covid_accidents_cached(file_stamp):
    return P.add_covid_columns(load_processed())


def load_covid_accidents():
    return _covid_accidents_cached(stamp(P.OUT_ACCIDENTS_PARQUET))


# ------------------------------------------------------------------ tests overview (Pipeline & method tab)
TESTS_DIR = P.ROOT / "tests"


@st.cache_data(show_spinner=False)
def _list_tests_cached(file_stamp):
    import ast

    rows = []
    for f in sorted(TESTS_DIR.glob("test_*.py")):
        src = f.read_text(encoding="utf-8")
        lines = src.splitlines()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                doc = ast.get_docstring(node)
                if not doc:  # first comment line inside the test, if any
                    nxt = lines[node.body[0].lineno - 2].strip() if node.body else ""
                    doc = nxt.lstrip("# ").strip() if nxt.startswith("#") else ""
                what = doc or node.name.replace("test_", "").replace("_", " ")
                rows.append({"file": f.name, "test": node.name, "what it checks": what.splitlines()[0],
                             "line": node.lineno})
    return pd.DataFrame(rows).sort_values(["file", "line"]).drop(columns="line").reset_index(drop=True)


def list_tests():
    """Every test function in tests/ (read from the files, so always up to date)."""
    return _list_tests_cached(stamp(*sorted(TESTS_DIR.glob("test_*.py"))))


# ------------------------------------------------------------------ raw data quality
def raw_coordinate_status():
    return _raw_coordinate_status_cached(stamp(P.RAW_ACCIDENTS, P.OUT_ACCIDENTS_PARQUET))


@st.cache_data(show_spinner="Checking coordinates...")
def _raw_coordinate_status_cached(file_stamp):
    """Coordinate status of each raw row (raw and processed rows are in the same order; checked here)."""
    raw, p = load_raw(), load_processed()
    if len(raw) != len(p) or not (raw.DT_YEAR_COLLISION.values == p.DT_YEAR_COLLISION.values).all():
        raise ValueError("Raw and processed accident rows are not aligned - rerun pipeline.py")
    status = p.COORD_STATUS.copy()
    status[(status == "ok") & (p.DIST_TO_OWN_MUNTY_M > 0)] = "0-1 km outside municipality (kept)"
    return status.replace({"ok": "inside own municipality", "missing": "missing",
                           "out_of_range": "out of Belgian range",
                           "outside_municipality": "> 1 km outside municipality"})


def raw_quality():
    return _raw_quality_cached(stamp(P.RAW_ACCIDENTS, P.OUT_ACCIDENTS_PARQUET))


@st.cache_data(show_spinner="Running quality checks...")
def _raw_quality_cached(file_stamp):
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
        "(Brussels has no province)", raw.TX_PROV_COLLISION_NL.isna().sum(), "Step A3: filled with 'Brussels Hoofdstedelijk Gewest'")
    add("Missing", "MS_X_COORD / MS_Y_COORD", "Coordinates missing", raw.MS_X_COORD.isna().sum(),
        "Step A6: municipality centre; step A8: excluded from GPS map")
    oor = raw.MS_X_COORD.notna() & ~(raw.MS_X_COORD.between(*P.LAMBERT_RANGE) & raw.MS_Y_COORD.between(*P.LAMBERT_RANGE))
    add("Incorrect", "MS_X_COORD / MS_Y_COORD", "Coordinates impossible (order of 1e15-1e16, outside Belgium)",
        oor.sum(), "Step A6: municipality centre; step A8: excluded from GPS map")
    add("Incorrect", "MS_X_COORD / MS_Y_COORD", "Point lies > 1 km outside the municipality given in CD_NIS",
        (st_ == "> 1 km outside municipality").sum(), "Step A6: municipality centre; step A8: excluded from GPS map")
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
    add("Naming", "TX_COLLISON_TYPE_FR", "Typo in column name (COLLISON)", None, "Step A2: removed (FR)")
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
