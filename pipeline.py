"""pipeline.py - every data step of the project as a pure function (no Streamlit).

Each processing step takes a DataFrame and returns (DataFrame, StepReport). The report records how many rows
went in, how many came out, how many were dropped or changed, and why. `run_all()` reads the raw files, runs the
steps in order and writes the processed files, the step reports and a sample of the data after every step to
Data/Processed Data. The app (app.py) only reads those outputs and calls the analysis functions below.

    python pipeline.py            # rebuild everything (about 3 minutes)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# ====================================================================================== paths
ROOT = Path(__file__).resolve().parent
RAW = ROOT / "Data" / "Raw Data"
PROC = ROOT / "Data" / "Processed Data"
SAMPLES = PROC / "pipeline_samples"

RAW_ACCIDENTS = RAW / "Accidents" / "OPENDATA_MAP_2017-2024.xlsx"
VAR_LIST = RAW / "Accidents" / "VAR_LIST_ACC_OPENDATA_MAP.xlsx"
RAW_DENSITY = RAW / "Population Density" / "Pop_density_en.xlsx"
RAW_POPULATION = RAW / "Population Density" / "Bevolking_per_gemeente.xlsx"
RAW_SECTORS = (RAW / "Geo" / "sectors_2024" / "sh_statbel_statistical_sectors_31370_20240101.geojson"
               / "sh_statbel_statistical_sectors_31370_20240101.geojson")
RAW_MOBILITY_DIR = RAW / "COVID Mobility"
RAW_MEASURES = RAW / "COVID Measures" / "OxCGRT_compact_national_v1.csv"

OUT_ACCIDENTS_CSV = PROC / "accidents_processed_2017-2024.csv"
OUT_ACCIDENTS_PARQUET = PROC / "accidents_processed_2017-2024.parquet"
OUT_DENSITY = PROC / "population_density_2017-2024.csv"
OUT_CENTERS = RAW / "Geo" / "municipality_centers_2024.csv"
OUT_MUNI_GEOJSON = RAW / "Geo" / "municipalities_2024.geojson"
OUT_UNIT_CENTERS = PROC / "unit_centers.csv"
OUT_OUTLINES = PROC / "outlines_{level}.geojson"
OUT_STEPS = PROC / "pipeline_steps.csv"
OUT_MISSING_BY_YEAR = PROC / "coordinates_by_year.csv"
OUT_COVID_MONTHLY = PROC / "covid_monthly_2017-2024.csv"
OUT_COVID_PHASES = PROC / "covid_phases.csv"
OUT_MEASURES_BEL = PROC / "covid_measures_BEL_daily.csv"
OUT_LOG = PROC / "processing_log.txt"

# ====================================================================================== agreements
# (also written down in CLAUDE.md and decision_log.md - change them there too)
SEVERE_CLASSES = [1, 2, 3]  # 1 = met doden, 2 = dodelijk gewonden, 3 = zwaargewonden; 4 = lichtgewonden
OUTSIDE_TOLERANCE_M = 1000  # a point further than this outside its own municipality is "abnormal"
LAMBERT_RANGE = (0, 300_000)  # generous Lambert 72 extent of Belgium (x and y)
BRUSSELS = "Brussels Hoofdstedelijk Gewest"
BASELINE_YEARS = (2017, 2018, 2019)

UNKNOWN_CODES = {
    "DT_TIME": [99], "CD_CROSSWAY": [9], "CD_WEATHER": ["9"], "CD_ROAD_CONDITION": ["9"],
    "CD_BUILD_UP_AREA": [9], "CD_LIGHT_CONDITION": [9], "CD_ROAD_TYPE": [9], "CD_ROAD_USR_TYPE1": [99],
    "CD_ROAD_USR_TYPE2": [99], "CD_COLLISION_TYPE": ["0", "9"], "CD_OBSTACLES": [-1, -3],
}
STR_CODES = {"CD_WEATHER": str, "CD_ROAD_CONDITION": str, "CD_COLLISION_TYPE": str}

# 2019 municipal mergers: pre-2019 NIS code -> post-2019 NIS code
MERGERS_2019 = {
    "12030": "12041", "12034": "12041",                    # Puurs + Sint-Amands -> Puurs-Sint-Amands
    "44001": "44084", "44029": "44084",                    # Aalter + Knesselare -> Aalter
    "44011": "44083", "44049": "44083",                    # Deinze + Nevele -> Deinze
    "44036": "44085", "44072": "44085", "44080": "44085",  # Lovendegem + Waarschoot + Zomergem -> Lievegem
    "45017": "45068", "45057": "45068",                    # Kruishoutem + Zingem -> Kruisem
    "72040": "72042", "71047": "72042",                    # Meeuwen-Gruitrode + Opglabbeek -> Oudsbergen
    "72025": "72043", "72029": "72043",                    # Neerpelt + Overpelt -> Pelt
}

DENSITY_BINS = [0, 250, 500, 1000, 2500, 5000, np.inf]
DENSITY_LABELS = ["< 250", "250-500", "500-1,000", "1,000-2,500", "2,500-5,000", "> 5,000"]

LEVELS = {"Regions": "REGION", "Provinces": "PROVINCE", "Municipalities": "CD_NIS", "BE": "BE"}

COVID_PHASES = [
    # code, name, first month, last month, description
    ("P0", "Pre-COVID", "2020-01", "2020-02", "Before the measures"),
    ("L1", "Lockdown 1", "2020-03", "2020-05", "1st lockdown: stay at home, non-essential shops closed (from 18/03/2020)"),
    ("R1", "Summer 2020", "2020-06", "2020-10", "Measures relaxed"),
    ("L2", "Lockdown 2", "2020-11", "2021-04", "2nd lockdown: curfew, telework mandatory, contact restrictions"),
    ("R2", "Reopening", "2021-05", "2022-02", "Gradual reopening, Covid Safe Ticket"),
    ("POST", "Post-COVID", "2022-03", "2024-12", "Measures lifted (07/03/2022)"),
]
BASELINE_PHASE = "Baseline 2017-2019"
REGION_GOOGLE = {"Brussels": BRUSSELS, "Flanders": "Vlaams Gewest", "Wallonia": "Waals Gewest"}
MIX_CELLS = ["CD_BUILD_UP_AREA", "CD_ROAD_TYPE", "CD_COLLISION_TYPE", "CYCLIST"]

# Category rules per chart: which categories, and which classification rule (shown in the app).
CATEGORY_RULES = [
    ("Severe accident (all tabs)", "CD_CLASS_ACCIDENTS in {1, 2, 3}",
     "1 = with deaths, 2 = fatally injured, 3 = seriously injured. Class 4 (light injuries only) = not severe."),
    ("Severity Ratio (all tabs)", "severe accidents / all injury accidents x 100",
     "Each accident counts once, whatever the number of victims."),
    ("Population density", "population on 1 January / area (km2) of the municipality, same year as the accident",
     "Higher levels (province, region, BE): sum of population / sum of area, averaged over the selected years."),
    ("Density class (tab 2, 'Why' charts)", "< 250 | 250-500 | 500-1,000 | 1,000-2,500 | 2,500-5,000 | > 5,000 inh./km2",
     "Fixed, rounded class limits (not quantiles), so the classes mean the same in every year selection."),
    ("Outside built-up area (tab 2 chart 2-3, tab 3)", "CD_BUILD_UP_AREA = 2",
     "Code 9 (unknown) is left out of chart 3 (inside vs outside) and counts as 'not outside' in shares."),
    ("Single vehicle / obstacle", "CD_COLLISION_TYPE in {6, 7, 8}",
     "6 = obstacle on the road, 7 = obstacle off the road, 8 = one driver, no obstacle (incl. fall)."),
    ("Collision type groups (tab 2 chart 4)", "6/7/8 single vehicle | 5 with pedestrian | 2 frontal | 1/3/4/A rear-side-chain | 0/9 other",
     "0 and 9 (not stated / unknown) are grouped as 'other / unknown'."),
    ("Night without street lighting (tab 2 chart 2)", "CD_LIGHT_CONDITION = 4", ""),
    ("In the dark (tab 3)", "CD_LIGHT_CONDITION in {3, 4, 5}", "Night with, without or with switched-off street lighting."),
    ("Cyclist involved (tab 3)", "CD_ROAD_USR_TYPE1 = 3 or CD_ROAD_USR_TYPE2 = 3", ""),
    ("Motorcyclist involved (tab 3)", "CD_ROAD_USR_TYPE1 = 7 or CD_ROAD_USR_TYPE2 = 7", ""),
    ("Road-user group (tab 3 chart 2)", "first match of: single vehicle | pedestrian | cyclist | motorcyclist | other",
     "An accident belongs to exactly one group; the order of the rules decides."),
    ("Rush hour (tab 3)", "DT_TIME in {7, 8, 16, 17, 18}", "07:00-08:59 and 16:00-18:59."),
    ("COVID phase (tab 3)", "by month, see covid_phases.csv",
     "Data has no day, so March 2020 counts fully as Lockdown 1 (lockdown started on 18/03)."),
    ("'Normal' (tab 3)", "average of the same calendar month in 2017-2019", ""),
]


# ====================================================================================== step reports
# Per step: the data set it works on, and the app tabs that use its result (shown in the tab "Pipeline & method").
TAB_RAW, TAB_PROC = "1.1 Raw Data Explorer", "1.2 Processed Data Explorer"
TAB_DENS, TAB_COVID = "❓ Density vs severity", "🦠 COVID lockdowns"
STEP_CONTEXT = {
    "1": ("Accidents – raw (OPENDATA_MAP_2017-2024.xlsx)", f"{TAB_RAW}; input of all other tabs"),
    "2": ("Accidents – processing", f"{TAB_PROC}, {TAB_DENS}, {TAB_COVID}"),
    "3": ("Accidents – processing", f"{TAB_PROC}, {TAB_DENS} (province view)"),
    "4": ("Accidents + population density (population_density_2017-2024.csv)", f"{TAB_PROC}, {TAB_DENS}"),
    "5": ("Accidents + municipality borders (Statbel statistical sectors 2024)", f"{TAB_RAW} (coordinates), {TAB_PROC}, {TAB_DENS}"),
    "6": ("Accidents + municipality centres (municipality_centers_2024.csv)", f"{TAB_PROC}, {TAB_DENS} (heat-layer switch)"),
    "7": ("Accidents – processed (accidents_processed_2017-2024.csv / .parquet)", f"{TAB_PROC}, {TAB_DENS} (maps)"),
    "8": ("Accidents – processed, view for the map (not saved)", f"{TAB_DENS} (grey heat layer)"),
    "C1": ("Google COVID-19 mobility reports BE 2020-2022", f"{TAB_COVID} (via covid_monthly_2017-2024.csv)"),
    "C2": ("OxCGRT government measures (OxCGRT_compact_national_v1.csv)", f"{TAB_COVID} (via covid_measures_BEL_daily.csv, covid_monthly_2017-2024.csv)"),
}


@dataclass
class StepReport:
    order: str
    step: str
    function: str
    rows_in: int
    rows_out: int
    rows_dropped: int
    rows_changed: int
    why: str
    dataset: str = ""
    tabs: str = ""

    def __post_init__(self):
        ds, tabs = STEP_CONTEXT.get(self.order, ("", ""))
        self.dataset, self.tabs = self.dataset or ds, self.tabs or tabs


def _report(order, step, function, df_in, df_out, changed=0, why=""):
    return StepReport(order, step, function, len(df_in), len(df_out), len(df_in) - len(df_out), int(changed), why)


# ====================================================================================== loaders (I/O only)
def load_raw_accidents(path=RAW_ACCIDENTS) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=STR_CODES)
    df["CD_NIS"] = df.CD_NIS.astype(str).str.zfill(5)
    return df


def load_density_sheet(year, path=RAW_DENSITY) -> pd.DataFrame:
    d = pd.read_excel(path, sheet_name=str(year), skiprows=2, header=None, dtype={0: str}).iloc[:, :6]
    d.columns = ["CD_NIS", "NAME_FR", "NAME_NL", "POPULATION", "AREA_KM2", "POP_DENSITY"]
    d["CD_NIS"] = d.CD_NIS.str.strip()
    return d[d.CD_NIS.str.fullmatch(r"\d{5}", na=False)].reset_index(drop=True)


def load_population_sheet(year, path=RAW_POPULATION) -> pd.DataFrame:
    p = pd.read_excel(path, sheet_name=f"Bevolking in {year}", header=None, dtype={0: str}).iloc[:, [0, 1, 4]]
    p.columns = ["CD_NIS", "NAME", "POPULATION"]
    p["CD_NIS"] = p.CD_NIS.str.strip()
    return p[p.CD_NIS.str.fullmatch(r"\d{5}", na=False)].reset_index(drop=True)


def load_mobility(folder=RAW_MOBILITY_DIR) -> pd.DataFrame:
    return pd.concat([pd.read_csv(f) for f in sorted(folder.glob("*_BE_Region_Mobility_Report.csv"))],
                     ignore_index=True)


def load_measures(path=RAW_MEASURES) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


# ====================================================================================== geography
def build_municipalities(sectors):
    """Dissolve statistical sectors (GeoDataFrame, EPSG:31370) into municipalities and compute their centres."""
    import geopandas as gpd

    cols = ["cd_munty_refnis", "tx_munty_descr_nl", "tx_prov_descr_nl", "tx_rgn_descr_nl"]
    munis = sectors[cols + ["geometry"]].dissolve("cd_munty_refnis", aggfunc="first").reset_index()
    munis = munis.rename(columns={"cd_munty_refnis": "CD_NIS"})
    centers = unit_centres(munis.geometry)
    wgs = gpd.GeoSeries(gpd.points_from_xy(centers.X, centers.Y), crs=31370).to_crs(4326)
    table = pd.DataFrame({
        "CD_NIS": munis.CD_NIS, "TX_MUNTY_NL": munis.tx_munty_descr_nl,
        "TX_PROV_NL": munis.tx_prov_descr_nl.fillna(BRUSSELS).replace("", BRUSSELS),
        "TX_RGN_NL": munis.tx_rgn_descr_nl,
        "CENTER_X_L72": centers.X.round(2).values, "CENTER_Y_L72": centers.Y.round(2).values,
        "CENTER_LAT": wgs.y.round(6).values, "CENTER_LON": wgs.x.round(6).values,
        "CENTER_METHOD": centers.METHOD.values, "AREA_KM2_GEO": (munis.area / 1e6).round(4).values,
    })
    return munis, table


def unit_centres(geoms) -> pd.DataFrame:
    """Centroid of each polygon; if the centroid falls outside (odd shapes) a point guaranteed inside."""
    c = geoms.centroid
    inside = geoms.contains(c)
    c[~inside] = geoms[~inside].representative_point()
    return pd.DataFrame({"X": c.x.values, "Y": c.y.values,
                         "METHOD": np.where(inside, "centroid", "representative_point")})


def build_units(munis, centers_table):
    """Centres (WGS84) and simplified outlines (GeoJSON dict) for every border view."""
    import geopandas as gpd

    m = munis.merge(centers_table[["CD_NIS", "TX_PROV_NL"]], on="CD_NIS")
    m["REGION"], m["PROVINCE"], m["BE"] = m.tx_rgn_descr_nl, m.TX_PROV_NL, "België"
    rows, outlines = [], {}
    for level, col in LEVELS.items():
        if level == "Municipalities":
            g = m[["CD_NIS", "tx_munty_descr_nl", "geometry"]].rename(columns={"CD_NIS": "KEY", "tx_munty_descr_nl": "NAME"})
        else:
            g = m[[col, "geometry"]].dissolve(col).reset_index().rename(columns={col: "KEY"})
            g["NAME"] = g.KEY
        c = unit_centres(g.geometry)
        w = gpd.GeoSeries(gpd.points_from_xy(c.X, c.Y), crs=31370).to_crs(4326)
        rows.append(pd.DataFrame({"LEVEL": level, "KEY": g.KEY.values, "NAME": g.NAME.values,
                                  "LAT": w.y.round(6).values, "LON": w.x.round(6).values, "METHOD": c.METHOD.values}))
        o = g[["KEY", "geometry"]].copy()
        o["geometry"] = o.simplify(120 if level == "Municipalities" else 250)
        outlines[level] = json.loads(o.to_crs(4326).to_json())
    return pd.concat(rows, ignore_index=True), outlines


# ====================================================================================== population density
def build_density(density_by_year: dict, population_by_year: dict, valid_codes) -> pd.DataFrame:
    """Tidy table YEAR x CD_NIS with POPULATION, AREA_KM2, POP_DENSITY.

    density_by_year: {year: density sheet} for 2019+ (Statbel density, taken as is)
    population_by_year: {year: population sheet} for years without density sheet (old codes -> 2019 codes,
                        divided by the 2019 area)
    """
    valid_codes = set(valid_codes)
    frames = []
    for y, d in sorted(density_by_year.items()):
        d = d[d.CD_NIS.isin(valid_codes)].assign(YEAR=y, SOURCE="Pop_density_en.xlsx")
        frames.append(d[["YEAR", "CD_NIS", "NAME_NL", "POPULATION", "AREA_KM2", "POP_DENSITY", "SOURCE"]])

    ref = density_by_year[min(density_by_year)].set_index("CD_NIS")
    name_to_code = {n: c for c, n in ref.NAME_NL.items() if c in valid_codes}
    for y, p in sorted(population_by_year.items()):
        p = p[(p.CD_NIS.str[-3:] != "000") & ~p.CD_NIS.isin(["20001", "20002"])]  # drop country/region/prov./arr.
        code = p.CD_NIS.map(MERGERS_2019)
        code = code.fillna(p.CD_NIS.where(p.CD_NIS.isin(valid_codes)))
        code = code.fillna(p.NAME.map(name_to_code))  # 2019 Hainaut renumbering: same name, new code
        if code.isna().any():
            raise ValueError(f"{y}: unmapped municipalities {p[code.isna()].values.tolist()}")
        pop = p.assign(CD_NIS=code).groupby("CD_NIS").POPULATION.sum()
        d = pd.DataFrame({"CD_NIS": pop.index, "POPULATION": pop.values})
        d["NAME_NL"] = d.CD_NIS.map(ref.NAME_NL)
        d["AREA_KM2"] = d.CD_NIS.map(ref.AREA_KM2)
        d["POP_DENSITY"] = d.POPULATION / d.AREA_KM2
        d = d.assign(YEAR=y, SOURCE=f"Bevolking_per_gemeente.xlsx / area {min(density_by_year)}")
        frames.append(d[["YEAR", "CD_NIS", "NAME_NL", "POPULATION", "AREA_KM2", "POP_DENSITY", "SOURCE"]])

    dens = pd.concat(frames, ignore_index=True)
    dens["POPULATION"] = dens.POPULATION.astype(int)
    dens["AREA_KM2"] = dens.AREA_KM2.astype(float).round(4)
    dens["POP_DENSITY"] = dens.POP_DENSITY.astype(float).round(2)
    return dens.sort_values(["YEAR", "CD_NIS"]).reset_index(drop=True)


# ====================================================================================== accident steps
def step_load(raw: pd.DataFrame):
    return raw.copy(), _report("1", "Load raw accidents", "load_raw_accidents", raw, raw,
                               why="All rows of OPENDATA_MAP_2017-2024.xlsx; nothing dropped.")


def step_drop_french(df):
    fr = [c for c in df.columns if c.endswith("_FR")]
    out = df.drop(columns=fr)
    return out, _report("2", "Drop French columns", "step_drop_french", df, out,
                        why=f"{len(fr)} columns removed ({', '.join(fr)}); we work in Dutch only. No rows dropped.")


def step_fill_province(df):
    out = df.copy()
    miss = out.TX_PROV_COLLISION_NL.isna()
    not_bru = miss & (out.TX_RGN_COLLISION_NL != BRUSSELS)
    if not_bru.any():
        raise ValueError(f"{not_bru.sum()} rows without province outside Brussels")
    out.loc[miss, "TX_PROV_COLLISION_NL"] = BRUSSELS
    return out, _report("3", "Fill province for Brussels", "step_fill_province", df, out, changed=miss.sum(),
                        why="Brussels belongs to no province. Empty province -> 'Brussels Hoofdstedelijk Gewest' "
                            "so Brussels is its own unit in the province view.")


def step_add_density(df, density):
    d = density[["YEAR", "CD_NIS", "POPULATION", "AREA_KM2", "POP_DENSITY"]].rename(columns={"YEAR": "DT_YEAR_COLLISION"})
    out = df.merge(d, on=["DT_YEAR_COLLISION", "CD_NIS"], how="left", validate="many_to_one")
    unmatched = int(out.POP_DENSITY.isna().sum())
    return out, _report("4", "Add population density", "step_add_density", df, out, changed=len(out) - unmatched,
                        why=f"Joined on CD_NIS + year (population on 1 January). Rows without a match: {unmatched}. "
                            "No rows dropped (left join, one density row per municipality-year).")


def step_check_coordinates(df, munis, tolerance_m=OUTSIDE_TOLERANCE_M):
    """Classify every coordinate: ok / missing / out_of_range / outside_municipality (> tolerance)."""
    import geopandas as gpd

    out = df.copy()
    out["MS_X_COORD_ORIG"], out["MS_Y_COORD_ORIG"] = out.MS_X_COORD, out.MS_Y_COORD
    x, y = out.MS_X_COORD, out.MS_Y_COORD
    status = pd.Series("ok", index=out.index)
    missing = x.isna() | y.isna()
    out_range = ~missing & ~(x.between(*LAMBERT_RANGE) & y.between(*LAMBERT_RANGE))
    status[missing], status[out_range] = "missing", "out_of_range"
    chk = ~missing & ~out_range
    pts = gpd.GeoSeries(gpd.points_from_xy(x[chk], y[chk]), index=out.index[chk], crs=31370)
    own = gpd.GeoSeries(munis.set_index("CD_NIS").geometry.reindex(out.loc[chk, "CD_NIS"]).values,
                        index=pts.index, crs=31370)
    dist = pts.distance(own)
    out["DIST_TO_OWN_MUNTY_M"] = dist.round(1)
    status[dist[dist > tolerance_m].index] = "outside_municipality"
    out["COORD_STATUS"] = status
    n = status.value_counts()
    return out, _report("5", "Check coordinates", "step_check_coordinates", df, out, changed=int((status != "ok").sum()),
                        why=f"Flagged, not dropped: missing {n.get('missing', 0):,}, out of Belgian range "
                            f"{n.get('out_of_range', 0):,}, > {tolerance_m} m outside own municipality "
                            f"{n.get('outside_municipality', 0):,}.")


def step_impute_coordinates(df, centers_table):
    out = df.copy()
    fix = out.COORD_STATUS != "ok"
    c = centers_table.set_index("CD_NIS")
    out.loc[fix, "MS_X_COORD"] = out.loc[fix, "CD_NIS"].map(c.CENTER_X_L72)
    out.loc[fix, "MS_Y_COORD"] = out.loc[fix, "CD_NIS"].map(c.CENTER_Y_L72)
    out["COORD_IMPUTED"] = fix
    return out, _report("6", "Replace abnormal coordinates", "step_impute_coordinates", df, out, changed=fix.sum(),
                        why="Abnormal coordinates -> centre of the municipality in CD_NIS. Rows are kept because "
                            "the municipality is known; COORD_IMPUTED marks them.")


def step_add_wgs84(df):
    import geopandas as gpd

    out = df.copy()
    w = gpd.GeoSeries(gpd.points_from_xy(out.MS_X_COORD, out.MS_Y_COORD), crs=31370).to_crs(4326)
    out["LAT"], out["LON"] = w.y.round(6).values, w.x.round(6).values
    return out, _report("7", "Add latitude / longitude", "step_add_wgs84", df, out, changed=len(out),
                        why="Lambert 72 (EPSG:31370) -> WGS84 for the maps. No rows dropped.")


def step_select_georeferenced(df):
    """Rows whose OWN coordinates are valid - used for everything plotted at GPS position (heat layer)."""
    out = df[~df.COORD_IMPUTED]
    return out, _report("8", "Heat layer only: accidents at their own GPS position",
                        "step_select_georeferenced", df, out,
                        why="NOT removed from the data. Accidents with a replaced coordinate sit on the municipality "
                            "centre, not where they happened, so by default the GPS heat layer leaves them out (a switch "
                            "on the map can include them). They stay in all counts, ratios and dots, which are grouped "
                            "by municipality code.")


def coordinates_by_year(df) -> pd.DataFrame:
    t = pd.crosstab(df.DT_YEAR_COLLISION, df.COORD_STATUS)
    t["total"] = t.sum(axis=1)
    t["excluded_from_gps_map"] = t.total - t.get("ok", 0)
    t["excluded_pct"] = (t.excluded_from_gps_map / t.total * 100).round(2)
    t["missing_pct"] = (t.get("missing", 0) / t.total * 100).round(2)
    return t.reset_index().rename(columns={"DT_YEAR_COLLISION": "YEAR"})


# ====================================================================================== analysis functions
def is_severe(cls) -> pd.Series:
    return pd.Series(cls).isin(SEVERE_CLASSES)


def severity_ratio(severe, total):
    severe, total = np.asarray(severe, dtype=float), np.asarray(total, dtype=float)
    return np.where(total > 0, severe / np.where(total > 0, total, 1) * 100, np.nan)


def filter_years(df, years):
    out = df[df.DT_YEAR_COLLISION.isin(list(years))]
    return out, StepReport("A", "Filter selected years", "filter_years", len(df), len(out), len(df) - len(out), 0,
                           f"Years {min(years)}-{max(years)} selected.")


def municipality_lookup(centers_table) -> pd.DataFrame:
    c = centers_table
    return pd.DataFrame({"MUNICIPALITY": c.TX_MUNTY_NL.values,
                         "PROVINCE": c.TX_PROV_NL.fillna(BRUSSELS).replace("", BRUSSELS).values,
                         "REGION": c.TX_RGN_NL.values, "BE": "België"}, index=c.CD_NIS.values)


def aggregate_by_level(acc, density, lookup, unit_centers, level, years) -> pd.DataFrame:
    """Per unit of `level`: accidents, severe, deaths, Severity Ratio, population, area, density, centre."""
    col = LEVELS[level]
    a = acc[acc.DT_YEAR_COLLISION.isin(years)]
    key = a.CD_NIS if col == "CD_NIS" else a.CD_NIS.map(lookup[col])
    sev = a.CD_CLASS_ACCIDENTS.isin(SEVERE_CLASSES)
    g = pd.DataFrame({"KEY": key, "SEV": sev, "DEATH": a.CD_CLASS_ACCIDENTS.isin([1, 2])}).groupby("KEY").agg(
        ACCIDENTS=("SEV", "size"), SEVERE=("SEV", "sum"), DEATHS=("DEATH", "sum"))

    d = density[density.YEAR.isin(years)].copy()
    d["KEY"] = d.CD_NIS if col == "CD_NIS" else d.CD_NIS.map(lookup[col])
    pop = d.groupby(["KEY", "YEAR"]).agg(POPULATION=("POPULATION", "sum"), AREA_KM2=("AREA_KM2", "sum")).groupby("KEY").mean()
    pop["POP_DENSITY"] = pop.POPULATION / pop.AREA_KM2

    out = pop.join(g, how="left").fillna({"ACCIDENTS": 0, "SEVERE": 0, "DEATHS": 0})
    out[["ACCIDENTS", "SEVERE", "DEATHS"]] = out[["ACCIDENTS", "SEVERE", "DEATHS"]].astype(int)
    out["SEVERITY_RATIO"] = severity_ratio(out.SEVERE, out.ACCIDENTS)
    out["ACCIDENTS_PER_1000_INH_YEAR"] = out.ACCIDENTS / len(years) / out.POPULATION * 1000
    u = unit_centers[unit_centers.LEVEL == level][["KEY", "NAME", "LAT", "LON"]]
    return out.reset_index().merge(u, on="KEY", how="left")


def add_density_class(df) -> pd.DataFrame:
    out = df.copy()
    out["DENSITY_CLASS"] = pd.cut(out.POP_DENSITY, DENSITY_BINS, labels=DENSITY_LABELS, right=False)
    return out


def collision_group(df) -> np.ndarray:
    ct = df.CD_COLLISION_TYPE
    return np.select([ct.isin(["6", "7", "8"]), ct == "5", ct == "2", ct.isin(["1", "3", "4", "A"])],
                     ["single vehicle / obstacle", "with pedestrian", "frontal", "rear / side / chain"],
                     "other / unknown")


def density_class_profile(acc) -> pd.DataFrame:
    a = add_density_class(acc)
    g = a.groupby("DENSITY_CLASS", observed=True)
    return pd.DataFrame({
        "Severity Ratio (%)": g.CD_CLASS_ACCIDENTS.apply(lambda s: s.isin(SEVERE_CLASSES).mean() * 100),
        "accidents": g.size(),
        "outside built-up area (%)": g.CD_BUILD_UP_AREA.apply(lambda s: (s == 2).mean() * 100),
        "single vehicle / obstacle (%)": g.CD_COLLISION_TYPE.apply(lambda s: s.isin(["6", "7", "8"]).mean() * 100),
        "night, no street lighting (%)": g.CD_LIGHT_CONDITION.apply(lambda s: (s == 4).mean() * 100),
        "motorway (%)": g.CD_ROAD_TYPE.apply(lambda s: (s == 1).mean() * 100),
    }).reset_index()


# ====================================================================================== COVID
def assign_phase(year, month, phases=COVID_PHASES) -> np.ndarray:
    ym = np.asarray(year, dtype=int) * 100 + np.asarray(month, dtype=int)
    out = np.full(ym.shape, BASELINE_PHASE, dtype=object)
    for _, name, start, end, _ in phases:
        out[(ym >= int(start.replace("-", ""))) & (ym <= int(end.replace("-", "")))] = name
    return out


def mobility_monthly(raw_mobility):
    """Google mobility: keep country + regions (drop provinces), monthly mean per area."""
    g = raw_mobility[raw_mobility.sub_region_2.isna()].copy()
    rep = StepReport("C1", "Mobility: country + regions only", "mobility_monthly", len(raw_mobility), len(g),
                     len(raw_mobility) - len(g), 0, "Province rows dropped: accidents are compared per region.")
    g["AREA"] = g.sub_region_1.map(REGION_GOOGLE).fillna("België")
    g["date"] = pd.to_datetime(g.date)
    cols = {c: "MOB_" + c.replace("_percent_change_from_baseline", "").upper()
            for c in g.columns if c.endswith("_percent_change_from_baseline")}
    g = g.rename(columns=cols)
    m = (g.groupby(["AREA", g.date.dt.year.rename("YEAR"), g.date.dt.month.rename("MONTH")])[list(cols.values())]
         .mean().round(1).reset_index())
    return m, rep


def measures_belgium(raw_measures):
    o = raw_measures[(raw_measures.CountryCode == "BEL") & (raw_measures.Jurisdiction == "NAT_TOTAL")].copy()
    rep = StepReport("C2", "Measures: Belgium only", "measures_belgium", len(raw_measures), len(o),
                     len(raw_measures) - len(o), 0, "OxCGRT covers every country; only Belgium (national) is used.")
    return o.reset_index(drop=True), rep


def measures_monthly(measures_bel):
    o = measures_bel.copy()
    o["date"] = pd.to_datetime(o.Date.astype(str), format="%Y%m%d")
    o = o.rename(columns={"StringencyIndex_Average": "STRINGENCY", "C6M_Stay at home requirements": "STAY_HOME",
                          "C2M_Workplace closing": "WORKPLACE_CLOSING",
                          "C7M_Restrictions on internal movement": "MOVEMENT_RESTRICTION"})
    return (o.groupby([o.date.dt.year.rename("YEAR"), o.date.dt.month.rename("MONTH")])
            [["STRINGENCY", "STAY_HOME", "WORKPLACE_CLOSING", "MOVEMENT_RESTRICTION"]].mean().round(2).reset_index())


def covid_monthly(acc, mobility_m, measures_m):
    """Per month x area (BE + 3 regions): accidents, severe, SR, 2017-2019 baseline of the same month."""
    a = pd.DataFrame({"YEAR": acc.DT_YEAR_COLLISION, "MONTH": acc.DT_MONTH_COLLISION,
                      "REGION": acc.TX_RGN_COLLISION_NL, "SEVERE": acc.CD_CLASS_ACCIDENTS.isin(SEVERE_CLASSES)})
    frames = []
    for area, d in [("België", a)] + [(r, a[a.REGION == r]) for r in REGION_GOOGLE.values()]:
        m = d.groupby(["YEAR", "MONTH"]).agg(ACCIDENTS=("SEVERE", "size"), SEVERE=("SEVERE", "sum")).reset_index()
        frames.append(m.assign(AREA=area))
    mon = pd.concat(frames, ignore_index=True)
    mon["SEVERITY_RATIO"] = severity_ratio(mon.SEVERE, mon.ACCIDENTS).round(2)
    base = (mon[mon.YEAR.isin(BASELINE_YEARS)].groupby(["AREA", "MONTH"])
            .agg(BASE_ACCIDENTS=("ACCIDENTS", "mean"), BASE_SEVERE=("SEVERE", "mean")).reset_index())
    base["BASE_SEVERITY_RATIO"] = severity_ratio(base.BASE_SEVERE, base.BASE_ACCIDENTS).round(2)
    base[["BASE_ACCIDENTS", "BASE_SEVERE"]] = base[["BASE_ACCIDENTS", "BASE_SEVERE"]].round(1)
    mon = mon.merge(base, on=["AREA", "MONTH"], how="left")
    mon["ACCIDENTS_CHANGE_PCT"] = ((mon.ACCIDENTS / mon.BASE_ACCIDENTS - 1) * 100).round(1)
    mon["SEVERE_CHANGE_PCT"] = ((mon.SEVERE / mon.BASE_SEVERE - 1) * 100).round(1)
    mon["SR_DIFF_PP"] = (mon.SEVERITY_RATIO - mon.BASE_SEVERITY_RATIO).round(2)
    mon["PHASE"] = assign_phase(mon.YEAR, mon.MONTH)
    mon["DATE"] = pd.to_datetime(dict(year=mon.YEAR, month=mon.MONTH, day=1))
    mon = mon.merge(mobility_m, on=["AREA", "YEAR", "MONTH"], how="left").merge(measures_m, on=["YEAR", "MONTH"], how="left")
    return mon.sort_values(["AREA", "YEAR", "MONTH"]).reset_index(drop=True)


def add_covid_columns(acc) -> pd.DataFrame:
    out = acc.copy()
    out["PHASE"] = assign_phase(out.DT_YEAR_COLLISION, out.DT_MONTH_COLLISION)
    out["SEVERE"] = out.CD_CLASS_ACCIDENTS.isin(SEVERE_CLASSES)
    out["CYCLIST"] = (out.CD_ROAD_USR_TYPE1 == 3) | (out.CD_ROAD_USR_TYPE2 == 3)
    return out


def period_vs_baseline(acc, phase):
    """Accidents of `phase`, the 2017-2019 accidents of the same calendar months, and the expected
    ('normal') number of accidents and severe accidents for that phase."""
    cur = acc[acc.PHASE == phase]
    base = acc[(acc.PHASE == BASELINE_PHASE) & acc.DT_MONTH_COLLISION.isin(cur.DT_MONTH_COLLISION.unique())]
    occ = cur.groupby("DT_MONTH_COLLISION").DT_YEAR_COLLISION.nunique()  # how often each month occurs in the phase
    n_years = len(BASELINE_YEARS)
    bm = base.groupby("DT_MONTH_COLLISION").agg(n=("SEVERE", "size"), s=("SEVERE", "sum"))
    base_n = float((bm.n.reindex(occ.index).fillna(0) / n_years * occ).sum())
    base_sev = float((bm.s.reindex(occ.index).fillna(0) / n_years * occ).sum())
    return cur, base, base_n, base_sev


def mix_profile(d) -> pd.Series:
    return pd.Series({
        "outside built-up area": (d.CD_BUILD_UP_AREA == 2).mean() * 100,
        "on a motorway": (d.CD_ROAD_TYPE == 1).mean() * 100,
        "single vehicle / obstacle": d.CD_COLLISION_TYPE.isin(["6", "7", "8"]).mean() * 100,
        "cyclist involved": d.CYCLIST.mean() * 100,
        "motorcyclist involved": ((d.CD_ROAD_USR_TYPE1 == 7) | (d.CD_ROAD_USR_TYPE2 == 7)).mean() * 100,
        "with a pedestrian": (d.CD_COLLISION_TYPE == "5").mean() * 100,
        "in the dark": d.CD_LIGHT_CONDITION.isin([3, 4, 5]).mean() * 100,
        "rush hour (7-9h, 16-19h)": d.DT_TIME.isin([7, 8, 16, 17, 18]).mean() * 100,
    })


def road_user_group(d) -> np.ndarray:
    return np.select(
        [d.CD_COLLISION_TYPE.isin(["6", "7", "8"]), d.CD_COLLISION_TYPE == "5", d.CYCLIST,
         (d.CD_ROAD_USR_TYPE1 == 7) | (d.CD_ROAD_USR_TYPE2 == 7)],
        ["single vehicle / obstacle", "with a pedestrian", "cyclist involved", "motorcyclist involved"],
        "other (mostly car-car)")


def mix_decomposition(cur, base, cells=MIX_CELLS) -> dict:
    """Direct standardisation: SR the period would have had with normal severity per cell (= only the mix changed)."""
    rates = base.groupby(cells).SEVERE.mean().rename("rate")
    c = cur.join(rates, on=cells)
    expected = c.rate.fillna(base.SEVERE.mean()).mean() * 100
    base_sr, obs_sr = base.SEVERE.mean() * 100, cur.SEVERE.mean() * 100
    return {"base_sr": base_sr, "expected_sr": expected, "observed_sr": obs_sr,
            "mix_effect_pp": expected - base_sr, "within_effect_pp": obs_sr - expected,
            "cells_without_baseline": int(c.rate.isna().sum())}


# ====================================================================================== run everything
def run_all(verbose=True):
    import geopandas as gpd

    PROC.mkdir(parents=True, exist_ok=True)
    SAMPLES.mkdir(parents=True, exist_ok=True)
    reports, log = [], []

    def keep(df, rep, focus=None):
        """Store the report and a sample after the step (rows the step changed, if any)."""
        reports.append(rep)
        sample = df[focus(df)].head(5) if focus is not None else df.head(5)
        sample.to_csv(SAMPLES / f"{rep.order}.csv", index=False, encoding="utf-8-sig")
        if verbose:
            print(f"[{rep.order}] {rep.step}: {rep.rows_in:,} -> {rep.rows_out:,} (dropped {rep.rows_dropped:,}, "
                  f"changed {rep.rows_changed:,})")
        return df

    # geography
    sectors = gpd.read_file(RAW_SECTORS)
    munis, centers = build_municipalities(sectors)
    centers.to_csv(OUT_CENTERS, index=False, encoding="utf-8-sig")
    munis.to_crs(4326).to_file(OUT_MUNI_GEOJSON, driver="GeoJSON")
    units, outlines = build_units(munis, centers)
    units.to_csv(OUT_UNIT_CENTERS, index=False, encoding="utf-8-sig")
    for level, gj in outlines.items():
        Path(str(OUT_OUTLINES).format(level=level)).write_text(json.dumps(gj), encoding="utf-8")
    log.append(f"Municipalities: {len(munis)} (centre method: {centers.CENTER_METHOD.value_counts().to_dict()})")

    # population density
    dens = build_density({y: load_density_sheet(y) for y in range(2019, 2025)},
                         {y: load_population_sheet(y) for y in (2017, 2018)}, set(munis.CD_NIS))
    dens.to_csv(OUT_DENSITY, index=False, encoding="utf-8-sig")
    log.append(f"Density table: {len(dens):,} rows, {dens.YEAR.min()}-{dens.YEAR.max()}")

    # accidents
    acc = keep(*step_load(load_raw_accidents()))
    acc = keep(*step_drop_french(acc))
    acc = keep(*step_fill_province(acc), focus=lambda d: d.TX_RGN_COLLISION_NL == BRUSSELS)
    acc = keep(*step_add_density(acc, dens))
    acc = keep(*step_check_coordinates(acc, munis), focus=lambda d: d.COORD_STATUS != "ok")
    acc = keep(*step_impute_coordinates(acc, centers), focus=lambda d: d.COORD_IMPUTED)
    acc = keep(*step_add_wgs84(acc))
    keep(*step_select_georeferenced(acc))
    acc.to_csv(OUT_ACCIDENTS_CSV, index=False, encoding="utf-8-sig")
    acc.to_parquet(OUT_ACCIDENTS_PARQUET, index=False)
    coordinates_by_year(acc).to_csv(OUT_MISSING_BY_YEAR, index=False, encoding="utf-8-sig")

    # COVID
    mob_m, rep = mobility_monthly(load_mobility())
    reports.append(rep)
    mea_bel, rep = measures_belgium(load_measures())
    reports.append(rep)
    mea_bel.to_csv(OUT_MEASURES_BEL, index=False, encoding="utf-8-sig")
    mon = covid_monthly(acc, mob_m, measures_monthly(mea_bel))
    mon.to_csv(OUT_COVID_MONTHLY, index=False, encoding="utf-8-sig")
    pd.DataFrame(COVID_PHASES, columns=["CODE", "PHASE", "FIRST_MONTH", "LAST_MONTH", "DESCRIPTION"]).to_csv(
        OUT_COVID_PHASES, index=False, encoding="utf-8-sig")

    steps = pd.DataFrame([asdict(r) for r in reports])
    steps.to_csv(OUT_STEPS, index=False, encoding="utf-8-sig")
    log += [f"[{r.order}] {r.step}: {r.rows_in:,} -> {r.rows_out:,} | dropped {r.rows_dropped:,} | "
            f"changed {r.rows_changed:,} | {r.why}" for r in reports]
    OUT_LOG.write_text("\n".join(log), encoding="utf-8")
    if verbose:
        print("\n".join(log[:2]))
    return steps


if __name__ == "__main__":
    run_all()
