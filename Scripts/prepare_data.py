"""Build the processed accident data set (Project 1.1).

Inputs  (Data/Raw Data):
  Accidents/OPENDATA_MAP_2017-2024.xlsx                       Statbel accident geolocation
  Population Density/Pop_density_en.xlsx                      Statbel density per municipality 2019-2026
  Population Density/Bevolking_per_gemeente.xlsx              Statbel population per municipality 1992-2026
  Geo/sectors_2024/.../sh_statbel_statistical_sectors_31370_20240101.geojson   Statbel sectors (Lambert 72)

Outputs:
  Data/Raw Data/Geo/municipality_centers_2024.csv             centre of each of the 581 municipalities
  Data/Raw Data/Geo/municipalities_2024.geojson               municipality polygons (WGS84), dissolved from sectors
  Data/Processed Data/population_density_2017-2024.csv        tidy density table (year x municipality)
  Data/Processed Data/accidents_processed_2017-2024.csv       processed accident data set
  Data/Processed Data/processing_log.txt                      summary of what was changed
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "Data" / "Raw Data"
OUT = ROOT / "Data" / "Processed Data"
OUT.mkdir(parents=True, exist_ok=True)

SECTORS = (RAW / "Geo" / "sectors_2024" / "sh_statbel_statistical_sectors_31370_20240101.geojson"
           / "sh_statbel_statistical_sectors_31370_20240101.geojson")

# Points further than this from their own municipality polygon are treated as abnormal.
# Small offsets (geocoding on a border road) are normal and kept.
OUTSIDE_TOLERANCE_M = 1000
# Belgian Lambert 72 extent (generous) - anything outside is not in Belgium.
X_RANGE, Y_RANGE = (0, 300_000), (0, 300_000)

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


# ---------------------------------------------------------------- geo
def build_municipalities():
    sectors = gpd.read_file(SECTORS)
    cols = ["cd_munty_refnis", "tx_munty_descr_nl", "tx_prov_descr_nl", "tx_rgn_descr_nl"]
    munis = sectors[cols + ["geometry"]].dissolve("cd_munty_refnis", aggfunc="first").reset_index()
    munis = munis.rename(columns={"cd_munty_refnis": "CD_NIS"})

    # centroid; if it falls outside the polygon (odd shapes), use a point guaranteed inside
    centre = munis.centroid
    inside = munis.geometry.contains(centre)
    centre[~inside] = munis.geometry[~inside].representative_point()
    wgs = gpd.GeoSeries(centre, crs=31370).to_crs(4326)

    centers = pd.DataFrame({
        "CD_NIS": munis.CD_NIS,
        "TX_MUNTY_NL": munis.tx_munty_descr_nl,
        "TX_PROV_NL": munis.tx_prov_descr_nl,
        "TX_RGN_NL": munis.tx_rgn_descr_nl,
        "CENTER_X_L72": centre.x.round(2),
        "CENTER_Y_L72": centre.y.round(2),
        "CENTER_LAT": wgs.y.round(6),
        "CENTER_LON": wgs.x.round(6),
        "CENTER_METHOD": np.where(inside, "centroid", "representative_point"),
        "AREA_KM2_GEO": (munis.area / 1e6).round(4),
    })
    centers.to_csv(RAW / "Geo" / "municipality_centers_2024.csv", index=False, encoding="utf-8-sig")
    munis.to_crs(4326).to_file(RAW / "Geo" / "municipalities_2024.geojson", driver="GeoJSON")
    return munis, centers


# ---------------------------------------------------------------- population density
def _read_density_sheet(year):
    d = pd.read_excel(RAW / "Population Density" / "Pop_density_en.xlsx", sheet_name=str(year),
                      skiprows=2, header=None, dtype={0: str})
    d = d.iloc[:, :6]
    d.columns = ["CD_NIS", "NAME_FR", "NAME_NL", "POPULATION", "AREA_KM2", "POP_DENSITY"]
    d["CD_NIS"] = d.CD_NIS.str.strip()
    return d[d.CD_NIS.str.fullmatch(r"\d{5}", na=False)]


def _read_population_sheet(year):
    p = pd.read_excel(RAW / "Population Density" / "Bevolking_per_gemeente.xlsx",
                      sheet_name=f"Bevolking in {year}", header=None, dtype={0: str})
    p = p.iloc[:, [0, 1, 4]]
    p.columns = ["CD_NIS", "NAME", "POPULATION"]
    p["CD_NIS"] = p.CD_NIS.str.strip()
    return p[p.CD_NIS.str.fullmatch(r"\d{5}", na=False)]


def build_density(valid_codes):
    frames = []
    # 2019-2024: Statbel's own density figures
    for y in range(2019, 2025):
        d = _read_density_sheet(y)
        d = d[d.CD_NIS.isin(valid_codes)].assign(YEAR=y, SOURCE="Pop_density_en.xlsx")
        frames.append(d[["YEAR", "CD_NIS", "NAME_NL", "POPULATION", "AREA_KM2", "POP_DENSITY", "SOURCE"]])

    # 2017-2018: population (pre-2019 codes) mapped to 2019 codes / 2019 area
    d19 = _read_density_sheet(2019).set_index("CD_NIS")
    name_to_2019 = {n: c for c, n in d19.NAME_NL.items() if c in valid_codes}
    for y in (2017, 2018):
        p = _read_population_sheet(y)
        # drop country/region/province/arrondissement totals (Brabant provinces are 20001/20002)
        p = p[(p.CD_NIS.str[-3:] != "000") & ~p.CD_NIS.isin(["20001", "20002"])]
        code = p.CD_NIS.map(MERGERS_2019)
        code = code.fillna(p.CD_NIS.where(p.CD_NIS.isin(valid_codes)))
        code = code.fillna(p.NAME.map(name_to_2019))  # Hainaut renumbering 2019 (same name, new code)
        unmapped = p[code.isna()]
        if len(unmapped):
            raise ValueError(f"{y}: unmapped municipalities {unmapped.values.tolist()}")
        pop = p.assign(CD_NIS=code).groupby("CD_NIS").POPULATION.sum()
        d = pd.DataFrame({"CD_NIS": pop.index, "POPULATION": pop.values})
        d["NAME_NL"] = d.CD_NIS.map(d19.NAME_NL)
        d["AREA_KM2"] = d.CD_NIS.map(d19.AREA_KM2)
        d["POP_DENSITY"] = d.POPULATION / d.AREA_KM2
        d = d.assign(YEAR=y, SOURCE="Bevolking_per_gemeente.xlsx / area 2019")
        frames.append(d[["YEAR", "CD_NIS", "NAME_NL", "POPULATION", "AREA_KM2", "POP_DENSITY", "SOURCE"]])

    dens = pd.concat(frames, ignore_index=True)
    dens["POPULATION"] = dens.POPULATION.astype(int)
    dens["AREA_KM2"] = dens.AREA_KM2.astype(float).round(4)
    dens["POP_DENSITY"] = dens.POP_DENSITY.astype(float).round(2)
    counts = dens.groupby("YEAR").CD_NIS.nunique()
    assert (counts == len(valid_codes)).all(), counts
    dens.sort_values(["YEAR", "CD_NIS"]).to_csv(OUT / "population_density_2017-2024.csv",
                                                index=False, encoding="utf-8-sig")
    return dens


# ---------------------------------------------------------------- accidents
def build_accidents(munis, centers, dens):
    acc = pd.read_excel(RAW / "Accidents" / "OPENDATA_MAP_2017-2024.xlsx")
    n_raw_cols = acc.shape[1]
    log = [f"Raw accidents: {len(acc):,} rows x {n_raw_cols} columns"]

    # 1. drop French columns
    fr_cols = [c for c in acc.columns if c.endswith("_FR")]
    acc = acc.drop(columns=fr_cols)
    log.append(f"Dropped {len(fr_cols)} FR columns: {', '.join(fr_cols)}")
    acc["CD_NIS"] = acc.CD_NIS.astype(str).str.zfill(5)

    # 2. Brussels has no province -> fill for the province view
    miss_prov = acc.TX_PROV_COLLISION_NL.isna()
    acc.loc[miss_prov, "TX_PROV_COLLISION_NL"] = "Brussels Hoofdstedelijk Gewest"
    log.append(f"TX_PROV_COLLISION_NL filled with 'Brussels Hoofdstedelijk Gewest': {miss_prov.sum():,} rows "
               f"(regions of those rows: {acc.loc[miss_prov, 'TX_RGN_COLLISION_NL'].unique().tolist()})")

    # 3. population density (same year, 1 January)
    d = dens[["YEAR", "CD_NIS", "POPULATION", "AREA_KM2", "POP_DENSITY"]].rename(columns={"YEAR": "DT_YEAR_COLLISION"})
    acc = acc.merge(d, on=["DT_YEAR_COLLISION", "CD_NIS"], how="left", validate="many_to_one")
    log.append(f"Added POPULATION, AREA_KM2, POP_DENSITY (inhabitants/km2); rows without match: "
               f"{acc.POP_DENSITY.isna().sum()}")

    # 4. coordinate checks
    acc["MS_X_COORD_ORIG"] = acc.MS_X_COORD
    acc["MS_Y_COORD_ORIG"] = acc.MS_Y_COORD
    x, y = acc.MS_X_COORD, acc.MS_Y_COORD
    status = pd.Series("ok", index=acc.index)
    missing = x.isna() | y.isna()
    out_bbox = ~missing & ~(x.between(*X_RANGE) & y.between(*Y_RANGE))
    status[missing] = "missing"
    status[out_bbox] = "out_of_range"

    check = ~missing & ~out_bbox
    pts = gpd.GeoSeries(gpd.points_from_xy(x[check], y[check]), index=acc.index[check], crs=31370)
    own = gpd.GeoSeries(munis.set_index("CD_NIS").geometry.reindex(acc.loc[check, "CD_NIS"]).values,
                        index=pts.index, crs=31370)
    dist = pts.distance(own)
    acc["DIST_TO_OWN_MUNTY_M"] = dist.round(1)
    status[dist[dist > OUTSIDE_TOLERANCE_M].index] = "outside_municipality"
    acc["COORD_STATUS"] = status

    fix = status != "ok"
    c = centers.set_index("CD_NIS")
    acc.loc[fix, "MS_X_COORD"] = acc.loc[fix, "CD_NIS"].map(c.CENTER_X_L72)
    acc.loc[fix, "MS_Y_COORD"] = acc.loc[fix, "CD_NIS"].map(c.CENTER_Y_L72)
    acc["COORD_IMPUTED"] = fix
    log.append("Coordinate check (Lambert 72, EPSG:31370):")
    for k, v in status.value_counts().items():
        log.append(f"   {k:22s} {v:>8,}")
    log.append(f"   -> {fix.sum():,} rows replaced by municipality centre "
               f"(abnormal = missing, outside BE range, or > {OUTSIDE_TOLERANCE_M} m outside own municipality)")
    log.append(f"   points 0-{OUTSIDE_TOLERANCE_M} m outside own municipality kept as is: "
               f"{((dist > 0) & (dist <= OUTSIDE_TOLERANCE_M)).sum():,}")

    # WGS84 for maps
    wgs = gpd.GeoSeries(gpd.points_from_xy(acc.MS_X_COORD, acc.MS_Y_COORD), crs=31370).to_crs(4326)
    acc["LAT"] = wgs.y.round(6)
    acc["LON"] = wgs.x.round(6)

    assert acc[["MS_X_COORD", "MS_Y_COORD", "TX_PROV_COLLISION_NL", "POP_DENSITY"]].notna().all().all()
    acc.to_csv(OUT / "accidents_processed_2017-2024.csv", index=False, encoding="utf-8-sig")
    log.append(f"Processed accidents: {len(acc):,} rows x {acc.shape[1]} columns")
    return acc, log


def main():
    munis, centers = build_municipalities()
    dens = build_density(set(munis.CD_NIS))
    acc, log = build_accidents(munis, centers, dens)
    head = [f"Municipalities: {len(munis)} (centre method: {centers.CENTER_METHOD.value_counts().to_dict()})",
            f"Density table: {len(dens):,} rows, years {dens.YEAR.min()}-{dens.YEAR.max()}"]
    text = "\n".join(head + log)
    (OUT / "processing_log.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
