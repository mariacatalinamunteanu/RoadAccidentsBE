"""Build the processed COVID data set (Project 1.1, question 3).

Question: Did the COVID-19 lockdowns make road accidents fewer but more severe? Why?

Inputs:
  Data/Processed Data/accidents_processed_2017-2024.csv                (from prepare_data.py)
  Data/Raw Data/COVID Mobility/20xx_BE_Region_Mobility_Report.csv       Google COVID-19 Community Mobility Reports
  Data/Raw Data/COVID Measures/OxCGRT_compact_national_v1.csv           Oxford COVID-19 Government Response Tracker

Outputs (Data/Processed Data):
  covid_phases.csv                  definition of the COVID phases (by month)
  covid_monthly_2017-2024.csv       per month x area (BE + 3 regions): accidents, severe, Severity Ratio,
                                    2017-2019 baseline for the same calendar month, mobility, stringency
  covid_processing_log.txt          summary
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "Data" / "Raw Data"
OUT = ROOT / "Data" / "Processed Data"

SEVERE_CLASSES = [1, 2, 3]
BASELINE_YEARS = (2017, 2018, 2019)
REGION_GOOGLE = {"Brussels": "Brussels Hoofdstedelijk Gewest", "Flanders": "Vlaams Gewest",
                 "Wallonia": "Waals Gewest"}

# Phases by month. Based on the Belgian measures (stay-at-home requirement in OxCGRT, C6M):
#   1st lockdown from 18 March 2020, easing from 4 May; 2nd lockdown from 2 November 2020,
#   stay-at-home advice until spring 2021; almost all measures lifted on 7 March 2022.
PHASES = [
    # code, name, first month, last month, description
    ("P0", "Pre-COVID", "2020-01", "2020-02", "Before the measures"),
    ("L1", "Lockdown 1", "2020-03", "2020-05", "1st lockdown: stay at home, non-essential shops closed (from 18/03/2020)"),
    ("R1", "Summer 2020", "2020-06", "2020-10", "Measures relaxed"),
    ("L2", "Lockdown 2", "2020-11", "2021-04", "2nd lockdown: curfew, telework mandatory, contact restrictions"),
    ("R2", "Reopening", "2021-05", "2022-02", "Gradual reopening, Covid Safe Ticket"),
    ("POST", "Post-COVID", "2022-03", "2024-12", "Measures lifted (07/03/2022)"),
]


def phase_of(year, month):
    ym = pd.Series(year).astype(int) * 100 + pd.Series(month).astype(int)
    out = pd.Series("Baseline 2017-2019", index=ym.index)
    for code, name, start, end, _ in PHASES:
        s, e = int(start.replace("-", "")), int(end.replace("-", ""))
        out[(ym >= s) & (ym <= e)] = name
    return out.values


def load_mobility():
    files = sorted((RAW / "COVID Mobility").glob("*_BE_Region_Mobility_Report.csv"))
    g = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    g = g[g.sub_region_2.isna()]  # country + regions (provinces dropped)
    g["AREA"] = g.sub_region_1.map(REGION_GOOGLE).fillna("België")
    g["date"] = pd.to_datetime(g.date)
    cols = {c: "MOB_" + c.replace("_percent_change_from_baseline", "").upper()
            for c in g.columns if c.endswith("_percent_change_from_baseline")}
    g = g.rename(columns=cols)
    m = (g.groupby(["AREA", g.date.dt.year.rename("YEAR"), g.date.dt.month.rename("MONTH")])[list(cols.values())]
         .mean().round(1).reset_index())
    return m, files


def load_measures():
    f = RAW / "COVID Measures" / "OxCGRT_compact_national_v1.csv"
    use = ["CountryCode", "Jurisdiction", "Date", "StringencyIndex_Average",
           "C6M_Stay at home requirements", "C2M_Workplace closing", "C7M_Restrictions on internal movement"]
    o = pd.read_csv(f, usecols=use)
    o = o[(o.CountryCode == "BEL") & (o.Jurisdiction == "NAT_TOTAL")].copy()
    o["date"] = pd.to_datetime(o.Date.astype(str), format="%Y%m%d")
    o = o.rename(columns={"StringencyIndex_Average": "STRINGENCY", "C6M_Stay at home requirements": "STAY_HOME",
                          "C2M_Workplace closing": "WORKPLACE_CLOSING",
                          "C7M_Restrictions on internal movement": "MOVEMENT_RESTRICTION"})
    m = (o.groupby([o.date.dt.year.rename("YEAR"), o.date.dt.month.rename("MONTH")])
         [["STRINGENCY", "STAY_HOME", "WORKPLACE_CLOSING", "MOVEMENT_RESTRICTION"]].mean().round(2).reset_index())
    return m, f


def main():
    acc = pd.read_csv(OUT / "accidents_processed_2017-2024.csv", encoding="utf-8-sig",
                      usecols=["DT_YEAR_COLLISION", "DT_MONTH_COLLISION", "TX_RGN_COLLISION_NL", "CD_CLASS_ACCIDENTS"])
    acc["SEVERE"] = acc.CD_CLASS_ACCIDENTS.isin(SEVERE_CLASSES)
    acc = acc.rename(columns={"DT_YEAR_COLLISION": "YEAR", "DT_MONTH_COLLISION": "MONTH"})

    frames = []
    for area, d in [("België", acc)] + [(r, acc[acc.TX_RGN_COLLISION_NL == r]) for r in REGION_GOOGLE.values()]:
        m = d.groupby(["YEAR", "MONTH"]).agg(ACCIDENTS=("SEVERE", "size"), SEVERE=("SEVERE", "sum")).reset_index()
        frames.append(m.assign(AREA=area))
    mon = pd.concat(frames, ignore_index=True)
    mon["SEVERITY_RATIO"] = (mon.SEVERE / mon.ACCIDENTS * 100).round(2)

    base = (mon[mon.YEAR.isin(BASELINE_YEARS)].groupby(["AREA", "MONTH"])
            .agg(BASE_ACCIDENTS=("ACCIDENTS", "mean"), BASE_SEVERE=("SEVERE", "mean"),
                 BASE_ACC_MIN=("ACCIDENTS", "min"), BASE_ACC_MAX=("ACCIDENTS", "max")).reset_index())
    base["BASE_SEVERITY_RATIO"] = (base.BASE_SEVERE / base.BASE_ACCIDENTS * 100).round(2)
    base[["BASE_ACCIDENTS", "BASE_SEVERE"]] = base[["BASE_ACCIDENTS", "BASE_SEVERE"]].round(1)
    mon = mon.merge(base, on=["AREA", "MONTH"], how="left")
    mon["ACCIDENTS_CHANGE_PCT"] = ((mon.ACCIDENTS / mon.BASE_ACCIDENTS - 1) * 100).round(1)
    mon["SEVERE_CHANGE_PCT"] = ((mon.SEVERE / mon.BASE_SEVERE - 1) * 100).round(1)
    mon["SR_DIFF_PP"] = (mon.SEVERITY_RATIO - mon.BASE_SEVERITY_RATIO).round(2)
    mon["PHASE"] = phase_of(mon.YEAR, mon.MONTH)
    mon["DATE"] = pd.to_datetime(dict(year=mon.YEAR, month=mon.MONTH, day=1))

    mob, mob_files = load_mobility()
    mea, mea_file = load_measures()
    mon = mon.merge(mob.rename(columns={"AREA": "AREA"}), on=["AREA", "YEAR", "MONTH"], how="left")
    mon = mon.merge(mea, on=["YEAR", "MONTH"], how="left")  # national measures, same for every area
    mon = mon.sort_values(["AREA", "YEAR", "MONTH"])
    mon.to_csv(OUT / "covid_monthly_2017-2024.csv", index=False, encoding="utf-8-sig")

    ph = pd.DataFrame(PHASES, columns=["CODE", "PHASE", "FIRST_MONTH", "LAST_MONTH", "DESCRIPTION"])
    ph.to_csv(OUT / "covid_phases.csv", index=False, encoding="utf-8-sig")

    be = mon[mon.AREA == "België"]
    log = [
        "COVID processing",
        f"Accidents: {len(acc):,} rows from accidents_processed_2017-2024.csv",
        f"Mobility (Google): {', '.join(f.name for f in mob_files)} -> monthly mean per region, "
        f"{mob.YEAR.min()}-{mob.YEAR.max()}",
        f"Measures (OxCGRT): {mea_file.name} -> Belgium national, monthly mean, {mea.YEAR.min()}-{mea.YEAR.max()}",
        f"Baseline = mean of the same calendar month in {BASELINE_YEARS[0]}-{BASELINE_YEARS[-1]}",
        f"covid_monthly_2017-2024.csv: {len(mon):,} rows (4 areas x 96 months), {mon.shape[1]} columns",
        "Phases: " + "; ".join(f"{p[1]} {p[2]}..{p[3]}" for p in PHASES),
        "Belgium per phase (accidents, Severity Ratio %):",
    ]
    for p, d in be.groupby("PHASE", sort=False):
        log.append(f"   {p:20s} {d.ACCIDENTS.sum():>8,}  {d.SEVERE.sum() / d.ACCIDENTS.sum() * 100:5.2f}")
    (OUT / "covid_processing_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
