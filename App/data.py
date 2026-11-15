"""Data loading, quality checks and aggregations for the road-safety app."""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "Data" / "Raw Data"
PROC = ROOT / "Data" / "Processed Data"

RAW_ACC = RAW / "Accidents" / "OPENDATA_MAP_2017-2024.xlsx"
VAR_LIST = RAW / "Accidents" / "VAR_LIST_ACC_OPENDATA_MAP.xlsx"
PROC_ACC = PROC / "accidents_processed_2017-2024.csv"
PROC_DENS = PROC / "population_density_2017-2024.csv"
PROC_LOG = PROC / "processing_log.txt"
CENTERS = RAW / "Geo" / "municipality_centers_2024.csv"
MUNI_GEO = RAW / "Geo" / "municipalities_2024.geojson"

BRU = "Brussels Hoofdstedelijk Gewest"
SEVERE_CLASSES = [1, 2, 3]
STR_CODES = {"CD_WEATHER": str, "CD_ROAD_CONDITION": str, "CD_COLLISION_TYPE": str}

# code values that mean "unknown / not specified"
UNKNOWN_CODES = {
    "DT_TIME": [99],
    "CD_CROSSWAY": [9],
    "CD_WEATHER": ["9"],
    "CD_ROAD_CONDITION": ["9"],
    "CD_BUILD_UP_AREA": [9],
    "CD_LIGHT_CONDITION": [9],
    "CD_ROAD_TYPE": [9],
    "CD_ROAD_USR_TYPE1": [99],
    "CD_ROAD_USR_TYPE2": [99],
    "CD_COLLISION_TYPE": ["0", "9"],
    "CD_OBSTACLES": [-1, -3],
}

# code column -> NL label column
CODE_LABEL = {
    "CD_CROSSWAY": "TX_CROSSWAY_NL",
    "CD_WEATHER": "TX_WEATHER_NL",
    "CD_ROAD_CONDITION": "TX_ROAD_CONDITION_NL",
    "CD_BUILD_UP_AREA": "TX_BUILD_UP_AREA_NL",
    "CD_LIGHT_CONDITION": "TX_LIGHT_CONDITION_NL",
    "CD_ROAD_TYPE": "CD_ROAD_TYPE_NL",
    "CD_CLASS_ACCIDENTS": "TX_CLASS_ACCIDENTS_NL",
    "CD_ROAD_USR_TYPE1": "TX_ROAD_USR_TYPE1_NL",
    "CD_ROAD_USR_TYPE2": "TX_ROAD_USR_TYPE2_NL",
    "CD_COLLISION_TYPE": "TX_COLLISION_TYPE_NL",
    "CD_OBSTACLES": "TX_OBSTACLES_NL",
    "CD_NIS": "TX_MUNTY_COLLISION_NL",
}

COVID_MONTHLY = PROC / "covid_monthly_2017-2024.csv"
COVID_PHASES = PROC / "covid_phases.csv"
COVID_LOG = PROC / "covid_processing_log.txt"
MOBILITY_DIR = RAW / "COVID Mobility"
MEASURES_FILE = RAW / "COVID Measures" / "OxCGRT_compact_national_v1.csv"

LEVEL_COL = {"Regions": "REGION", "Provinces": "PROVINCE", "Municipalities": "CD_NIS", "BE": "BE"}


# ------------------------------------------------------------------ loaders
@st.cache_data(show_spinner="Loading raw accident file (first time ~1 min, then cached)...", persist="disk")
def load_raw():
    df = pd.read_excel(RAW_ACC, dtype=STR_CODES)
    df["CD_NIS"] = df.CD_NIS.astype(str).str.zfill(5)
    return df


@st.cache_data(show_spinner=False)
def load_var_list():
    v = pd.read_excel(VAR_LIST)
    v.columns = [str(c).strip() for c in v.columns]
    return v


@st.cache_data(show_spinner="Loading processed accident data...")
def load_processed():
    df = pd.read_csv(PROC_ACC, dtype={"CD_NIS": str, **STR_CODES}, encoding="utf-8-sig")
    df["SEVERE"] = df.CD_CLASS_ACCIDENTS.isin(SEVERE_CLASSES)
    return df


@st.cache_data(show_spinner=False)
def load_density():
    return pd.read_csv(PROC_DENS, dtype={"CD_NIS": str}, encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def load_centers():
    return pd.read_csv(CENTERS, dtype={"CD_NIS": str}, encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def load_log():
    return PROC_LOG.read_text(encoding="utf-8") if PROC_LOG.exists() else ""


@st.cache_data(show_spinner=False)
def muni_lookup():
    """CD_NIS -> municipality / province / region names (NL)."""
    c = load_centers()
    prov = c.TX_PROV_NL.replace("", np.nan).fillna(BRU)
    return pd.DataFrame({"CD_NIS": c.CD_NIS, "MUNICIPALITY": c.TX_MUNTY_NL, "PROVINCE": prov,
                         "REGION": c.TX_RGN_NL, "BE": "België"}).set_index("CD_NIS")


@st.cache_resource(show_spinner="Building borders and centres...")
def load_units():
    """Per level: table KEY/NAME/LAT/LON (centre) and a simplified outline GeoJSON."""
    m = gpd.read_file(MUNI_GEO).to_crs(31370)
    m["CD_NIS"] = m.CD_NIS.astype(str).str.zfill(5)
    look = muni_lookup()
    m = m.join(look, on="CD_NIS")
    out = {}
    for level, col in LEVEL_COL.items():
        if level == "Municipalities":
            g = m[["CD_NIS", "MUNICIPALITY", "geometry"]].rename(columns={"CD_NIS": "KEY", "MUNICIPALITY": "NAME"})
        else:
            g = m[[col, "geometry"]].dissolve(col).reset_index().rename(columns={col: "KEY"})
            g["NAME"] = g.KEY
        centre = g.centroid
        inside = g.contains(centre)
        centre[~inside] = g.geometry[~inside].representative_point()
        cw = gpd.GeoSeries(centre, crs=31370).to_crs(4326)
        g["LAT"], g["LON"] = cw.y.values, cw.x.values
        outline = g[["KEY", "geometry"]].copy()
        outline["geometry"] = outline.simplify(120 if level == "Municipalities" else 250)
        geojson = json.loads(outline.to_crs(4326).to_json())
        out[level] = (pd.DataFrame(g.drop(columns="geometry")), geojson)
    return out


# ------------------------------------------------------------------ raw quality
@st.cache_data(show_spinner="Checking coordinates...")
def raw_coordinate_status():
    """Coordinate status of each raw row (rows are in the same order in raw and processed files)."""
    raw = load_raw()
    p = load_processed()
    assert len(raw) == len(p) and (raw.DT_YEAR_COLLISION.values == p.DT_YEAR_COLLISION.values).all()
    status = p.COORD_STATUS.copy()
    near = (status == "ok") & (p.DIST_TO_OWN_MUNTY_M > 0)
    status[near] = "0-1 km outside municipality (kept)"
    status = status.replace({"ok": "inside own municipality", "missing": "missing",
                             "out_of_range": "out of Belgian range",
                             "outside_municipality": "> 1 km outside municipality"})
    return status


@st.cache_data(show_spinner="Running quality checks...")
def raw_quality():
    raw = load_raw()
    n = len(raw)
    res = {}

    miss = raw.isna().sum()
    res["missing"] = (pd.DataFrame({"column": miss.index, "missing": miss.values,
                                    "missing %": (miss.values / n * 100).round(2)})
                      .query("missing > 0").sort_values("missing", ascending=False))

    rows = []
    for col, codes in UNKNOWN_CODES.items():
        cnt = int(raw[col].isin(codes).sum())
        rows.append({"column": col, "codes meaning unknown": ", ".join(map(str, codes)),
                     "rows": cnt, "% of rows": round(cnt / n * 100, 2)})
    res["unknown"] = pd.DataFrame(rows).sort_values("rows", ascending=False)

    # code <-> label consistency
    pairs = []
    for c, t in CODE_LABEL.items():
        per_code = raw.groupby(c)[t].nunique()
        per_label = raw.groupby(t)[c].nunique()
        pairs.append({"code column": c, "label column": t,
                      "codes with >1 label": int((per_code > 1).sum()),
                      "labels with >1 code": int((per_label > 1).sum())})
    res["code_label"] = pd.DataFrame(pairs)

    issues = []

    def add(category, column, issue, count, action):
        issues.append({"category": category, "column": column, "issue": issue,
                       "rows": int(count) if count is not None else None, "handling": action})

    add("Missing", "TX_PROV_COLLISION_NL / _FR", "Province empty: all rows are in the Brussels Capital Region "
        "(Brussels has no province)", raw.TX_PROV_COLLISION_NL.isna().sum(),
        "Filled with 'Brussels Hoofdstedelijk Gewest'")
    add("Missing", "MS_X_COORD / MS_Y_COORD", "Coordinates missing", raw.MS_X_COORD.isna().sum(),
        "Replaced by municipality centre")
    oor = raw.MS_X_COORD.notna() & ~(raw.MS_X_COORD.between(0, 300000) & raw.MS_Y_COORD.between(0, 300000))
    add("Incorrect", "MS_X_COORD / MS_Y_COORD", "Coordinates impossible (order of 1e15-1e16, outside Belgium)",
        oor.sum(), "Replaced by municipality centre")
    st_ = raw_coordinate_status()
    add("Incorrect", "MS_X_COORD / MS_Y_COORD", "Point lies > 1 km outside the municipality given in CD_NIS",
        (st_ == "> 1 km outside municipality").sum(), "Replaced by municipality centre")
    add("Inconsistent (minor)", "MS_X_COORD / MS_Y_COORD", "Point lies 0-1 km outside its municipality "
        "(typically border roads)", (st_ == "0-1 km outside municipality (kept)").sum(), "Kept")
    add("Incorrect", "DT_TIME", "Hour = 99 (not a valid hour 0-23)", (~raw.DT_TIME.between(0, 23)).sum(),
        "Kept; treat as unknown hour")
    add("Duplicates", "all columns", "Rows identical in all 45 columns (may be genuine separate accidents "
        "since the data is aggregated to hour level)", raw.duplicated().sum(), "Kept")
    add("Inconsistent", "TX_ROAD_CONDITION_NL", "Label typo 'Ijzel, sneeuw+ roper' (should be '+Proper')",
        raw.TX_ROAD_CONDITION_NL.str.contains(r"\+ roper", na=False).sum(), "Kept (label only)")
    add("Inconsistent", "CD_OBSTACLES", "Code -1 has label 'Geen vermelding van de type aanrijding' "
        "(a collision-type label, not an obstacle)", (raw.CD_OBSTACLES == -1).sum(), "Treated as unknown")
    add("Inconsistent", "CD_ROAD_USR_TYPE2", "Codes 10/11 are not road-user types but crash situations "
        "('één bestuurder, geen hindernis' / 'tegen een hindernis')",
        raw.CD_ROAD_USR_TYPE2.isin([10, 11]).sum(), "Kept")
    multi = raw.CD_WEATHER.str.contains("/", na=False) | raw.CD_ROAD_CONDITION.str.contains("/", na=False)
    add("Inconsistent", "CD_WEATHER / CD_ROAD_CONDITION", "Combined codes such as '2/4' (multiple values "
        "in one field, so the column is text, not numeric)", multi.sum(), "Kept")
    add("Inconsistent", "CD_COLLISION_TYPE", "Mixed numeric and letter codes (code 'A')",
        (raw.CD_COLLISION_TYPE == "A").sum(), "Read as text")
    lower = [c for c in raw.columns if c.endswith("_NL") and (raw[c] == "onbekend").any()]
    upper = [c for c in raw.columns if c.endswith("_NL") and (raw[c] == "Onbekend").any()]
    add("Inconsistent", ", ".join(lower + upper), "'unknown' spelled as 'onbekend' in some columns and "
        "'Onbekend' in others; label capitalisation varies (e.g. 'personenauto' vs 'Fiets')", None, "Kept")
    add("Naming", "CD_ROAD_TYPE_FR / CD_ROAD_TYPE_NL", "Prefix CD_ (code) but the columns hold text labels",
        None, "Kept")
    add("Naming", "TX_COLLISON_TYPE_FR", "Typo in column name (COLLISON)", None, "Column removed (FR)")
    add("Metadata", "VAR_LIST", "Variable list declares all codes as 'Char'; the file stores most of them as "
        "numbers. Header 'Lenght' is misspelt", None, "-")
    res["issues"] = pd.DataFrame(issues)

    checks = [
        ("Every CD_NIS has exactly one municipality name",
         int((raw.groupby("CD_NIS").TX_MUNTY_COLLISION_NL.nunique() > 1).sum()) == 0),
        ("Every CD_NIS belongs to exactly one region",
         int((raw.groupby("CD_NIS").TX_RGN_COLLISION_NL.nunique() > 1).sum()) == 0),
        ("Months are 1-12", bool(raw.DT_MONTH_COLLISION.between(1, 12).all())),
        ("Years are 2017-2024", bool(raw.DT_YEAR_COLLISION.between(2017, 2024).all())),
        ("No empty strings / leading or trailing spaces in text columns",
         all(((s := raw[c].dropna().astype(str)) == s.str.strip()).all() and (s != "").all()
             for c in raw.columns if raw[c].dtype == object or str(raw[c].dtype).startswith("str"))),
        ("Accident class has only codes 1-4", bool(raw.CD_CLASS_ACCIDENTS.isin([1, 2, 3, 4]).all())),
    ]
    res["checks"] = pd.DataFrame(checks, columns=["check", "passed"])

    res["coord_by_year"] = (pd.crosstab(raw.DT_YEAR_COLLISION, st_).reset_index()
                            .melt(id_vars="DT_YEAR_COLLISION", var_name="status", value_name="rows"))
    return res


# ------------------------------------------------------------------ analysis
def severity_ratio(severe, total):
    return np.where(total > 0, severe / np.maximum(total, 1) * 100, np.nan)


def aggregate(acc, dens, level, years):
    """Accidents, severe accidents, Severity Ratio and population density per unit of `level`."""
    look = muni_lookup()
    col = LEVEL_COL[level]
    a = acc[acc.DT_YEAR_COLLISION.isin(years)]
    key = a.CD_NIS.map(look[col]) if col != "CD_NIS" else a.CD_NIS
    g = a.groupby(key).agg(ACCIDENTS=("SEVERE", "size"), SEVERE=("SEVERE", "sum"),
                           DEATHS=("CD_CLASS_ACCIDENTS", lambda s: s.isin([1, 2]).sum()))
    g.index.name = "KEY"

    d = dens[dens.YEAR.isin(years)].copy()
    d["KEY"] = d.CD_NIS.map(look[col]) if col != "CD_NIS" else d.CD_NIS
    per_year = d.groupby(["KEY", "YEAR"]).agg(POPULATION=("POPULATION", "sum"), AREA_KM2=("AREA_KM2", "sum"))
    pd_ = per_year.groupby("KEY").mean()
    pd_["POP_DENSITY"] = pd_.POPULATION / pd_.AREA_KM2

    out = pd_.join(g, how="left").fillna({"ACCIDENTS": 0, "SEVERE": 0, "DEATHS": 0})
    out["SEVERITY_RATIO"] = severity_ratio(out.SEVERE, out.ACCIDENTS)
    units, _ = load_units()[level]
    out = out.reset_index().merge(units[["KEY", "NAME", "LAT", "LON"]], on="KEY", how="left")
    if level == "Municipalities":
        out = out.merge(look[["PROVINCE", "REGION"]], left_on="KEY", right_index=True, how="left")
    return out


DENSITY_BINS = [0, 250, 500, 1000, 2500, 5000, np.inf]
DENSITY_LABELS = ["< 250", "250-500", "500-1,000", "1,000-2,500", "2,500-5,000", "> 5,000"]


def add_density_class(acc):
    acc = acc.copy()
    acc["DENSITY_CLASS"] = pd.cut(acc.POP_DENSITY, DENSITY_BINS, labels=DENSITY_LABELS, right=False)
    return acc


# ------------------------------------------------------------------ COVID (question 3)
@st.cache_data(show_spinner=False)
def load_covid_monthly():
    m = pd.read_csv(COVID_MONTHLY, encoding="utf-8-sig", parse_dates=["DATE"])
    return m


@st.cache_data(show_spinner=False)
def load_covid_phases():
    return pd.read_csv(COVID_PHASES, encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def load_covid_log():
    return COVID_LOG.read_text(encoding="utf-8") if COVID_LOG.exists() else ""


@st.cache_data(show_spinner=False)
def load_mobility_raw():
    files = sorted(MOBILITY_DIR.glob("*_BE_Region_Mobility_Report.csv"))
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


@st.cache_data(show_spinner="Reading OxCGRT (Belgium only)...")
def load_measures_raw():
    o = pd.read_csv(MEASURES_FILE, low_memory=False)
    return o[o.CountryCode == "BEL"].reset_index(drop=True)


def covid_phase(acc):
    """Phase label for each accident row (same definition as Scripts/prepare_covid.py)."""
    ph = load_covid_phases()
    ym = acc.DT_YEAR_COLLISION * 100 + acc.DT_MONTH_COLLISION
    out = pd.Series("Baseline 2017-2019", index=acc.index)
    for _, r in ph.iterrows():
        s, e = int(r.FIRST_MONTH.replace("-", "")), int(r.LAST_MONTH.replace("-", ""))
        out[(ym >= s) & (ym <= e)] = r.PHASE
    return out
