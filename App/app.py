"""Road accidents Belgium 2017-2024 - data explorer and density vs severity analysis.

Run from the project folder:   streamlit run App/app.py
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pyproj import Transformer
from scipy import stats

import data as D

st.set_page_config(page_title="Road accidents BE 2017-2024", page_icon="🚦", layout="wide")

# blue (low) -> red (high): readable on a light map and colour-blind safe (blue/orange contrast)
SEV_COLORS = ["#313695", "#4575b4", "#74add1", "#fdae61", "#f46d43", "#d73027", "#a50026"]
SEV_SCALE = [[i / (len(SEV_COLORS) - 1), c] for i, c in enumerate(SEV_COLORS)]
SEV_RANGE = (0, 20)
GREY = "#6b7280"
BE_CENTER = {"lat": 50.52, "lon": 4.47}
QUESTION = "Is it true that as the density of the population increases, the severity of the accidents decreases? Why?"


def fmt(n):
    return f"{n:,.0f}".replace(",", " ")


def show_fig(fig, key=None):
    st.plotly_chart(fig, width="stretch", key=key)


# =================================================================== DATA EXPLORER
def raw_explorer():
    st.subheader("Raw data – Accidents")
    st.caption(f"Source: Statbel, *Geolocatie van de verkeersongevallen 2017–2024* · `{D.RAW_ACC.name}` "
               f"and `{D.VAR_LIST.name}`")

    st.markdown("#### Variable list (`VAR_LIST_ACC_OPENDATA_MAP.xlsx`)")
    st.dataframe(D.load_var_list(), width="stretch", hide_index=True, height=420)

    raw = D.load_raw()
    q = D.raw_quality()

    st.markdown("#### Accident data (`OPENDATA_MAP_2017-2024.xlsx`)")
    c = st.columns(5)
    c[0].metric("Rows (accidents)", fmt(len(raw)))
    c[1].metric("Columns", raw.shape[1])
    c[2].metric("Municipalities (CD_NIS)", raw.CD_NIS.nunique())
    c[3].metric("Rows with ≥1 missing value", fmt(raw.isna().any(axis=1).sum()))
    c[4].metric("Exact duplicate rows", fmt(raw.duplicated().sum()))
    with st.expander("Browse the raw data", expanded=False):
        n = st.slider("Rows to show", 100, 5000, 500, step=100, key="raw_rows")
        yr = st.multiselect("Year", sorted(raw.DT_YEAR_COLLISION.unique()), key="raw_year")
        view = raw[raw.DT_YEAR_COLLISION.isin(yr)] if yr else raw
        st.dataframe(view.head(n), width="stretch", height=400)

    st.markdown("### Data quality")
    t1, t2, t3, t4 = st.tabs(["Missing values", "Unknown / unspecified", "Inconsistent & incorrect",
                              "Coordinates"])

    with t1:
        m = q["missing"]
        st.markdown(f"**{len(m)} of {raw.shape[1]} columns** have empty cells. Everything else is complete.")
        fig = px.bar(m, x="missing", y="column", orientation="h", text="missing %",
                     labels={"missing": "Empty cells", "column": ""})
        fig.update_traces(marker_color="#d73027", texttemplate="%{text:.1f}%")
        fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0))
        show_fig(fig)
        st.dataframe(m, hide_index=True, width="stretch")
        miss_rgn = raw[raw.TX_PROV_COLLISION_NL.isna()].TX_RGN_COLLISION_NL.value_counts()
        st.info(f"Province is empty only for **{', '.join(miss_rgn.index)}** ({fmt(miss_rgn.sum())} rows): "
                "the Brussels Capital Region does not belong to a province, so this is structural, not an error.")

    with t2:
        st.markdown("Cells that are filled in but mean *unknown / not specified*. They are not empty, so "
                    "they do not show up as missing values.")
        u = q["unknown"]
        fig = px.bar(u, x="% of rows", y="column", orientation="h", text="rows")
        fig.update_traces(marker_color="#fdae61", texttemplate="%{text:,}")
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"))
        show_fig(fig)
        st.dataframe(u, hide_index=True, width="stretch")
        st.markdown("**Distribution of a coded column**")
        col = st.selectbox("Column", list(D.CODE_LABEL)[:-1], index=6, key="dist_col")
        lab = D.CODE_LABEL[col]
        dist = raw.groupby([col, lab], dropna=False).size().reset_index(name="rows")
        dist["unknown"] = dist[col].isin(D.UNKNOWN_CODES.get(col, []))
        dist["label"] = dist[col].astype(str) + " – " + dist[lab].astype(str)
        fig = px.bar(dist.sort_values("rows"), x="rows", y="label", color="unknown", orientation="h",
                     color_discrete_map={True: "#fdae61", False: "#4575b4"}, labels={"label": ""})
        fig.update_layout(height=max(250, 28 * len(dist)), margin=dict(l=0, r=0, t=10, b=0))
        show_fig(fig)

    with t3:
        st.markdown("**Issues found**")
        st.dataframe(q["issues"], hide_index=True, width="stretch",
                     column_config={"rows": st.column_config.NumberColumn(format="%d"),
                                    "issue": st.column_config.TextColumn(width="large")})
        a, b = st.columns(2)
        with a:
            st.markdown("**Code ↔ label consistency** (each code should have exactly one label)")
            st.dataframe(q["code_label"], hide_index=True, width="stretch")
        with b:
            st.markdown("**Checks passed / failed**")
            st.dataframe(q["checks"].assign(passed=q["checks"].passed.map({True: "✅", False: "❌"})),
                         hide_index=True, width="stretch")
        dups = raw[raw.duplicated(keep=False)].sort_values(list(raw.columns[:4]))
        with st.expander(f"Show the {fmt(len(dups))} rows involved in exact duplicates"):
            st.dataframe(dups, width="stretch", height=300)

    with t4:
        status = D.raw_coordinate_status()
        counts = status.value_counts().rename_axis("status").reset_index(name="rows")
        counts["%"] = (counts.rows / len(status) * 100).round(2)
        a, b = st.columns([1, 2])
        with a:
            st.markdown("Each point (Lambert 72) is checked against the border of the municipality in "
                        "`CD_NIS`. The borders come from Statbel's 2024 statistical sectors.")
            st.dataframe(counts, hide_index=True, width="stretch")
        with b:
            cy = q["coord_by_year"]
            cy = cy[cy.status != "inside own municipality"]
            fig = px.bar(cy, x="DT_YEAR_COLLISION", y="rows", color="status", barmode="stack",
                         labels={"DT_YEAR_COLLISION": "Year", "rows": "Rows with a problem"},
                         color_discrete_sequence=["#d73027", "#fdae61", "#4575b4", "#a50026"])
            fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), legend_title="")
            show_fig(fig)
        p = D.load_processed()
        bad = p[p.COORD_STATUS == "outside_municipality"]
        tr = Transformer.from_crs(31370, 4326, always_xy=True)
        lon, lat = tr.transform(bad.MS_X_COORD_ORIG.values, bad.MS_Y_COORD_ORIG.values)
        fig = go.Figure(go.Scattermap(
            lat=lat, lon=lon, mode="markers",
            marker=dict(size=7, color=np.minimum(bad.DIST_TO_OWN_MUNTY_M / 1000, 50), colorscale="OrRd",
                        cmin=0, cmax=50, colorbar=dict(title="km outside")),
            text=bad.TX_MUNTY_COLLISION_NL,
            hovertemplate="Recorded municipality: %{text}<br>%{marker.color:.1f} km outside<extra></extra>"))
        fig.update_layout(map=dict(style="carto-positron", center=BE_CENTER, zoom=6.4), height=480,
                          margin=dict(l=0, r=0, t=30, b=0),
                          title=f"Where the {fmt(len(bad))} points lying > 1 km outside their municipality were recorded")
        show_fig(fig)


def processed_explorer():
    st.subheader("Processed data")
    st.caption("Built by `Scripts/prepare_data.py` from the raw accident data, Statbel population figures and "
               "Statbel municipality borders.")
    p = D.load_processed()
    dens = D.load_density()
    cent = D.load_centers()
    raw_cols = list(D.load_raw().columns)

    t1, t2, t3, t4 = st.tabs(["Tables", "What changed", "Coordinates fixed", "Population density"])

    with t1:
        which = st.radio("Data set", ["accidents_processed_2017-2024.csv", "population_density_2017-2024.csv",
                                      "municipality_centers_2024.csv (Raw Data/Geo)", "covid_monthly_2017-2024.csv",
                                      "covid_phases.csv"], horizontal=True)
        if which.startswith("accidents"):
            c = st.columns(3)
            c[0].metric("Rows", fmt(len(p)))
            c[1].metric("Columns", p.shape[1] - 1)
            c[2].metric("Empty cells in key columns", int(p[["MS_X_COORD", "MS_Y_COORD", "TX_PROV_COLLISION_NL",
                                                              "POP_DENSITY"]].isna().sum().sum()))
            f1, f2, f3 = st.columns(3)
            yr = f1.multiselect("Year", sorted(p.DT_YEAR_COLLISION.unique()))
            rg = f2.multiselect("Region", sorted(p.TX_RGN_COLLISION_NL.unique()))
            only = f3.selectbox("Rows", ["All", "Only rows with replaced coordinates"])
            v = p.drop(columns="SEVERE")
            if yr:
                v = v[v.DT_YEAR_COLLISION.isin(yr)]
            if rg:
                v = v[v.TX_RGN_COLLISION_NL.isin(rg)]
            if only != "All":
                v = v[v.COORD_IMPUTED]
            st.caption(f"{fmt(len(v))} matching rows. The first 2,000 are shown.")
            st.dataframe(v.head(2000), width="stretch", height=450)
        elif which.startswith("covid_monthly"):
            st.dataframe(D.load_covid_monthly(), width="stretch", height=450, hide_index=True)
        elif which.startswith("covid_phases"):
            st.dataframe(D.load_covid_phases(), width="stretch", hide_index=True)
        elif which.startswith("population"):
            st.dataframe(dens, width="stretch", height=450, hide_index=True)
        else:
            st.dataframe(cent, width="stretch", height=450, hide_index=True)
        with st.expander("Processing log"):
            st.code(D.load_log(), language=None)

    with t2:
        removed = [c for c in raw_cols if c not in p.columns]
        added = [c for c in p.columns if c not in raw_cols and c != "SEVERE"]
        desc = {
            "POPULATION": "Population of the municipality on 1 January of the accident year (Statbel)",
            "AREA_KM2": "Area of the municipality in km² (Statbel)",
            "POP_DENSITY": "Inhabitants per km² for that municipality and year",
            "MS_X_COORD_ORIG": "Original X coordinate (before correction)",
            "MS_Y_COORD_ORIG": "Original Y coordinate (before correction)",
            "DIST_TO_OWN_MUNTY_M": "Distance (m) from the original point to its municipality border; 0 = inside",
            "COORD_STATUS": "ok / missing / out_of_range / outside_municipality",
            "COORD_IMPUTED": "True if MS_X/Y_COORD were replaced by the municipality centre",
            "LAT": "Latitude (WGS84) of the final coordinates",
            "LON": "Longitude (WGS84) of the final coordinates",
        }
        a, b = st.columns(2)
        with a:
            st.markdown(f"**➖ Removed: {len(removed)} French columns**")
            st.dataframe(pd.DataFrame({"column": removed}), hide_index=True, width="stretch", height=300)
        with b:
            st.markdown(f"**➕ Added: {len(added)} columns**")
            st.dataframe(pd.DataFrame({"column": added, "meaning": [desc.get(c, "") for c in added]}),
                         hide_index=True, width="stretch", height=300)

        st.markdown("**🔧 Values fixed / filled**")
        raw = D.load_raw()
        before = raw[["TX_PROV_COLLISION_NL", "MS_X_COORD", "MS_Y_COORD"]].isna().sum()
        after = p[["TX_PROV_COLLISION_NL", "MS_X_COORD", "MS_Y_COORD", "POP_DENSITY"]].isna().sum()
        comp = pd.DataFrame({
            "column": ["TX_PROV_COLLISION_NL", "MS_X_COORD / MS_Y_COORD", "POP_DENSITY"],
            "empty before": [before.TX_PROV_COLLISION_NL, before.MS_X_COORD, len(p)],
            "values changed": [before.TX_PROV_COLLISION_NL, int(p.COORD_IMPUTED.sum()), len(p)],
            "empty after": [after.TX_PROV_COLLISION_NL, after.MS_X_COORD, after.POP_DENSITY],
            "how": ["Filled with 'Brussels Hoofdstedelijk Gewest' (province view)",
                    "Missing, impossible or > 1 km outside municipality → centre of the municipality",
                    "New column: joined from Statbel on CD_NIS + year"],
        })
        st.dataframe(comp, hide_index=True, width="stretch")
        prov = p.TX_PROV_COLLISION_NL.value_counts().rename_axis("province").reset_index(name="accidents")
        fig = px.bar(prov, x="accidents", y="province", orientation="h",
                     color=prov.province.eq(D.BRU).map({True: "filled", False: "original"}),
                     color_discrete_map={"filled": "#f46d43", "original": "#4575b4"},
                     labels={"color": "", "province": ""}, title="Accidents per province after filling Brussels")
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0), yaxis=dict(autorange="reversed"))
        show_fig(fig)

    with t3:
        s = p.COORD_STATUS.value_counts().rename_axis("status").reset_index(name="rows")
        c = st.columns(len(s) + 1)
        c[0].metric("Coordinates replaced", fmt(p.COORD_IMPUTED.sum()), f"{p.COORD_IMPUTED.mean() * 100:.1f}% of rows",
                    delta_color="off")
        for i, r in s.iterrows():
            c[i + 1].metric(r.status, fmt(r.rows))
        by = p[p.COORD_IMPUTED].groupby(["DT_YEAR_COLLISION", "COORD_STATUS"]).size().reset_index(name="rows")
        fig = px.bar(by, x="DT_YEAR_COLLISION", y="rows", color="COORD_STATUS",
                     labels={"DT_YEAR_COLLISION": "Year", "rows": "Rows replaced", "COORD_STATUS": ""},
                     color_discrete_sequence=["#d73027", "#fdae61", "#a50026"], title="Replaced coordinates per year")
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0))
        show_fig(fig)

        st.markdown("**Points > 1 km outside their municipality: original position → municipality centre**")
        bad = p[p.COORD_STATUS == "outside_municipality"]
        tr = Transformer.from_crs(31370, 4326, always_xy=True)
        olon, olat = tr.transform(bad.MS_X_COORD_ORIG.values, bad.MS_Y_COORD_ORIG.values)
        lines_lat = np.column_stack([olat, bad.LAT.values, np.full(len(bad), np.nan)]).ravel()
        lines_lon = np.column_stack([olon, bad.LON.values, np.full(len(bad), np.nan)]).ravel()
        fig = go.Figure()
        fig.add_trace(go.Scattermap(lat=lines_lat, lon=lines_lon, mode="lines", line=dict(width=1, color=GREY),
                                    name="moved", hoverinfo="skip"))
        fig.add_trace(go.Scattermap(lat=olat, lon=olon, mode="markers", marker=dict(size=6, color="#d73027"),
                                    name="original (wrong) position", text=bad.TX_MUNTY_COLLISION_NL,
                                    hovertemplate="%{text}<extra>original</extra>"))
        fig.add_trace(go.Scattermap(lat=bad.LAT, lon=bad.LON, mode="markers", marker=dict(size=8, color="#1a9850"),
                                    name="municipality centre (new)", text=bad.TX_MUNTY_COLLISION_NL,
                                    hovertemplate="%{text}<extra>new</extra>"))
        fig.update_layout(map=dict(style="carto-positron", center=BE_CENTER, zoom=6.4), height=520,
                          margin=dict(l=0, r=0, t=0, b=0), legend=dict(x=0, y=1, bgcolor="rgba(255,255,255,.8)"))
        show_fig(fig)
        st.caption(f"{fmt(((p.DIST_TO_OWN_MUNTY_M > 0) & (p.DIST_TO_OWN_MUNTY_M <= 1000)).sum())} points that "
                   "lie less than 1 km outside their municipality, mostly on border roads, were kept as they are.")

    with t4:
        st.markdown("Population density = population on 1 January / area. **2019–2024** come straight from "
                    "Statbel (`Pop_density_en.xlsx`). For **2017–2018** the population (`Bevolking_per_gemeente.xlsx`) "
                    "was converted to the 2019 municipalities (7 mergers + Hainaut renumbering) and divided by the "
                    "2019 area.")
        tot = dens.groupby(["YEAR", "SOURCE"]).agg(municipalities=("CD_NIS", "nunique"),
                                                   population=("POPULATION", "sum")).reset_index()
        st.dataframe(tot, hide_index=True, width="stretch")
        fig = px.box(dens, x="YEAR", y="POP_DENSITY", log_y=True, points=False,
                     labels={"POP_DENSITY": "Inhabitants / km² (log)", "YEAR": "Year"},
                     title="Distribution of municipal population density per year")
        fig.update_traces(marker_color="#4575b4")
        fig.update_layout(height=360, margin=dict(l=0, r=0, t=40, b=0))
        show_fig(fig)


# =================================================================== ANALYSIS
def heat_map(agg, level, acc, heat_mode, units_geojson):
    fig = go.Figure()
    if heat_mode != "Off":
        a = acc[acc.SEVERE] if heat_mode == "Severe accidents" else acc
        grid = (a.assign(lat=(a.LAT / 0.02).round() * 0.02, lon=(a.LON / 0.03).round() * 0.03)
                .groupby(["lat", "lon"]).size().reset_index(name="n"))
        fig.add_trace(go.Densitymap(
            lat=grid.lat, lon=grid.lon, z=np.log1p(grid.n), radius=14, hoverinfo="skip", showscale=False,
            colorscale=[[0, "rgba(90,90,90,0)"], [0.3, "rgba(90,90,90,0.25)"], [1, "rgba(40,40,40,0.75)"]],
            name="accident concentration"))
    d = np.log10(agg.POP_DENSITY)
    if len(agg) > 1:
        size = 10 + 26 * (d - d.min()) / max(d.max() - d.min(), 1e-9)
    else:
        size = pd.Series([40])
    if level == "Municipalities":
        size = size * 0.55
    fig.add_trace(go.Scattermap(
        lat=agg.LAT, lon=agg.LON, mode="markers",
        marker=dict(size=size, color=agg.SEVERITY_RATIO, colorscale=SEV_SCALE, cmin=SEV_RANGE[0],
                    cmax=SEV_RANGE[1], opacity=0.92,
                    colorbar=dict(title=dict(text="Severity<br>Ratio (%)"), thickness=14, len=0.75)),
        customdata=np.column_stack([agg.NAME, agg.POP_DENSITY, agg.ACCIDENTS, agg.SEVERE, agg.SEVERITY_RATIO]),
        hovertemplate=("<b>%{customdata[0]}</b><br>Population density: %{customdata[1]:,.0f} inh./km²"
                       "<br>Injury accidents: %{customdata[2]:,}<br>Severe (class 1-3): %{customdata[3]:,}"
                       "<br><b>Severity Ratio: %{customdata[4]:.1f}%</b><extra></extra>"),
        name=level))
    fig.update_layout(
        map=dict(style="carto-positron", center=BE_CENTER, zoom=6.55,
                 layers=[dict(source=units_geojson, type="line", color="#374151",
                              line=dict(width=0.5 if level == "Municipalities" else 1.3))]),
        height=640, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
    return fig


def relation_scatter(agg, level, min_n):
    a = agg[agg.ACCIDENTS >= min_n]
    fig = px.scatter(a, x="POP_DENSITY", y="SEVERITY_RATIO", size="ACCIDENTS", color="SEVERITY_RATIO",
                     color_continuous_scale=SEV_COLORS, range_color=SEV_RANGE, log_x=True, hover_name="NAME",
                     size_max=40 if level != "Municipalities" else 22,
                     labels={"POP_DENSITY": "Population density (inhabitants / km², log scale)",
                             "SEVERITY_RATIO": "Severity Ratio (%)", "ACCIDENTS": "Injury accidents"})
    res = None
    if len(a) >= 4:
        x = np.log10(a.POP_DENSITY)
        slope, icpt = np.polyfit(x, a.SEVERITY_RATIO, 1, w=np.sqrt(a.ACCIDENTS))
        xs = np.linspace(x.min(), x.max(), 50)
        fig.add_trace(go.Scatter(x=10 ** xs, y=icpt + slope * xs, mode="lines", line=dict(color="#111827", dash="dash"),
                                 name="weighted trend", hoverinfo="skip"))
        rho, pval = stats.spearmanr(a.POP_DENSITY, a.SEVERITY_RATIO)
        res = dict(rho=rho, p=pval, slope=slope, n=len(a))
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0), coloraxis_showscale=False, showlegend=False)
    return fig, res


def answer_tab():
    st.subheader(QUESTION)
    acc = D.add_density_class(D.load_processed())
    dens = D.load_density()
    units = D.load_units()

    c1, c2, c3 = st.columns([2, 1.3, 1.3])
    level = c1.segmented_control("Border view", ["Regions", "Provinces", "Municipalities", "BE"],
                                 default="Provinces", key="level") or "Provinces"
    years = c2.select_slider("Years", options=list(range(2017, 2025)), value=(2017, 2024))
    heat_mode = c3.radio("Accident heat layer (GPS positions)", ["All accidents", "Severe accidents", "Off"],
                         horizontal=True)
    yrs = list(range(years[0], years[1] + 1))
    a = acc[acc.DT_YEAR_COLLISION.isin(yrs)]
    agg = D.aggregate(acc, dens, level, yrs)

    # ---------- headline
    by_cls = a.groupby("DENSITY_CLASS", observed=True).agg(n=("SEVERE", "size"), sev=("SEVERE", "sum"))
    by_cls["SR"] = by_cls.sev / by_cls.n * 100
    mun = D.aggregate(acc, dens, "Municipalities", yrs)
    rho, pval = stats.spearmanr(mun.POP_DENSITY, mun.SEVERITY_RATIO)
    be_sr = a.SEVERE.mean() * 100
    k = st.columns(4)
    k[0].metric("Injury accidents", fmt(len(a)))
    k[1].metric("Severe (class 1–3)", fmt(a.SEVERE.sum()))
    k[2].metric("Severity Ratio Belgium", f"{be_sr:.1f}%")
    k[3].metric("Spearman ρ density ↔ SR (581 municipalities)", f"{rho:.2f}", "p < 0.001" if pval < 0.001 else f"p = {pval:.3f}",
                delta_color="off")
    verdict = "Yes" if rho < 0 and pval < 0.05 else "No clear evidence"
    st.success(f"**{verdict}.** The Severity Ratio is **{by_cls.SR.iloc[0]:.1f}%** in municipalities with "
               f"fewer than 250 inhabitants/km² and **{by_cls.SR.iloc[-1]:.1f}%** in municipalities with more than "
               f"5,000 inhabitants/km². Denser areas have more injury accidents, but a smaller share of them are "
               f"severe. The *why* is explained below the map.")
    st.caption("Severity Ratio = accidents of class 1 (deaths), 2 (fatally injured) and 3 (seriously injured) ÷ all "
               "recorded injury accidents × 100. Each accident counts once.")

    # ---------- map + scatter
    st.markdown(f"#### Heat map – {level.lower() if level != 'BE' else 'Belgium'}")
    st.caption("Each **dot** sits at the centre of a unit. **Colour** = Severity Ratio (blue = low, red = high). "
               "**Size** = population density (bigger = denser). The grey **heat layer** shows where accidents "
               "happened, using their GPS coordinates.")
    m1, m2 = st.columns([3, 2])
    with m1:
        show_fig(heat_map(agg, level, a, heat_mode, units[level][1]), key="map")
    with m2:
        min_n = 1
        if level == "Municipalities":
            min_n = st.slider("Only municipalities with at least N accidents (small numbers = noisy ratios)",
                              1, 500, 30, key="min_n")
        if level == "BE":
            r = agg.iloc[0]
            st.markdown(f"**Belgium** · density **{r.POP_DENSITY:,.0f} inh./km²** · "
                        f"**{fmt(r.ACCIDENTS)}** injury accidents · Severity Ratio **{r.SEVERITY_RATIO:.1f}%**")
            st.info("At BE level there is only one dot, so no relationship can be seen. Use regions, provinces or "
                    "municipalities, or the density classes below.")
        else:
            fig, res = relation_scatter(agg, level, min_n)
            show_fig(fig, key="scatter")
            if res:
                st.caption(f"{res['n']} units · Spearman ρ = **{res['rho']:.2f}** (p = {res['p']:.2g}) · trend: "
                           f"**{res['slope']:+.1f} percentage points** of Severity Ratio for every 10× increase in density.")
    with st.expander(f"Table – {level}"):
        cols = ["NAME", "POPULATION", "AREA_KM2", "POP_DENSITY", "ACCIDENTS", "SEVERE", "DEATHS", "SEVERITY_RATIO", "LAT", "LON"]
        st.dataframe(agg[cols].sort_values("POP_DENSITY", ascending=False).round(2), hide_index=True,
                     width="stretch")

    # ---------- why
    st.markdown("---")
    st.markdown("### Why? What changes as density increases")
    cls = a.groupby("DENSITY_CLASS", observed=True)
    prof = pd.DataFrame({
        "Severity Ratio (%)": cls.SEVERE.mean() * 100,
        "accidents": cls.size(),
        "outside built-up area (%)": cls.CD_BUILD_UP_AREA.apply(lambda s: (s == 2).mean() * 100),
        "single vehicle / obstacle (%)": cls.CD_COLLISION_TYPE.apply(lambda s: s.isin(["6", "7", "8"]).mean() * 100),
        "night, no street lighting (%)": cls.CD_LIGHT_CONDITION.apply(lambda s: (s == 4).mean() * 100),
        "motorway (%)": cls.CD_ROAD_TYPE.apply(lambda s: (s == 1).mean() * 100),
    }).reset_index()

    w1, w2 = st.columns(2)
    with w1:
        fig = px.bar(prof, x="DENSITY_CLASS", y="Severity Ratio (%)", text="Severity Ratio (%)",
                     color="Severity Ratio (%)", color_continuous_scale=SEV_COLORS, range_color=SEV_RANGE,
                     labels={"DENSITY_CLASS": "Population density of the municipality (inh./km²)"},
                     title="1 · Severity Ratio by density class", hover_data={"accidents": ":,"})
        fig.update_traces(texttemplate="%{text:.1f}%")
        fig.update_layout(height=380, coloraxis_showscale=False, margin=dict(l=0, r=0, t=40, b=0))
        show_fig(fig)
    with w2:
        long = prof.melt(id_vars="DENSITY_CLASS", value_vars=["outside built-up area (%)",
                         "single vehicle / obstacle (%)", "night, no street lighting (%)"],
                         var_name="factor", value_name="% of accidents")
        fig = px.line(long, x="DENSITY_CLASS", y="% of accidents", color="factor", markers=True,
                      labels={"DENSITY_CLASS": "Population density (inh./km²)", "factor": ""},
                      title="2 · Where and how accidents happen, by density class",
                      color_discrete_sequence=["#d73027", "#f46d43", "#313695"])
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0), legend=dict(orientation="h", y=-0.25))
        show_fig(fig)

    w3, w4 = st.columns(2)
    with w3:
        bu = (a[a.CD_BUILD_UP_AREA.isin([1, 2])]
              .groupby(["DENSITY_CLASS", "TX_BUILD_UP_AREA_NL"], observed=True).SEVERE.mean().mul(100)
              .reset_index(name="Severity Ratio (%)"))
        fig = px.bar(bu, x="DENSITY_CLASS", y="Severity Ratio (%)", color="TX_BUILD_UP_AREA_NL", barmode="group",
                     labels={"DENSITY_CLASS": "Population density (inh./km²)", "TX_BUILD_UP_AREA_NL": ""},
                     color_discrete_map={"binnen bebouwde kom": "#4575b4", "buiten bebouwde kom": "#d73027"},
                     title="3 · Severity Ratio inside vs outside built-up areas")
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0), legend=dict(orientation="h", y=-0.25))
        show_fig(fig)
    with w4:
        ct = a.copy()
        ct["situation"] = np.select(
            [ct.CD_COLLISION_TYPE.isin(["6", "7", "8"]), ct.CD_COLLISION_TYPE == "5", ct.CD_COLLISION_TYPE == "2",
             ct.CD_COLLISION_TYPE.isin(["1", "3", "4", "A"])],
            ["single vehicle / obstacle", "with pedestrian", "frontal", "rear / side / chain"], "other / unknown")
        sit = ct.groupby("situation").agg(n=("SEVERE", "size"), SR=("SEVERE", "mean")).reset_index()
        sit["SR"] *= 100
        fig = px.bar(sit.sort_values("SR"), x="SR", y="situation", orientation="h", text="SR", color="SR",
                     color_continuous_scale=SEV_COLORS, range_color=SEV_RANGE, hover_data={"n": ":,"},
                     labels={"SR": "Severity Ratio (%)", "situation": ""},
                     title="4 · Severity Ratio by type of collision (all of Belgium)")
        fig.update_traces(texttemplate="%{text:.1f}%")
        fig.update_layout(height=380, coloraxis_showscale=False, margin=dict(l=0, r=0, t=40, b=0))
        show_fig(fig)

    out_lo, out_hi = prof["outside built-up area (%)"].iloc[[0, -1]]
    sv_lo, sv_hi = prof["single vehicle / obstacle (%)"].iloc[[0, -1]]
    bu_p = bu.pivot(index="DENSITY_CLASS", columns="TX_BUILD_UP_AREA_NL", values="Severity Ratio (%)")
    st.markdown(f"""
**Explanation**

1. **Speed (the main reason).** In the least dense municipalities, **{out_lo:.0f}%** of injury accidents happen
   *outside* built-up areas, on 70–90 km/h roads. In the densest municipalities this is only **{out_hi:.0f}%** (chart 2).
   Crash energy rises with the square of speed, so an accident outside a built-up area is far more often serious
   or fatal (chart 3, red bars).
2. **Type of crash.** Low-density areas have more single-vehicle crashes and crashes into trees, posts or ditches
   (**{sv_lo:.0f}%** vs **{sv_hi:.0f}%**). These are among the most severe types (chart 4). In cities, most crashes are
   low-speed rear-end, side and flank collisions, which mostly cause light injuries.
3. **Even inside built-up areas, density helps.** Inside built-up areas the ratio still drops from
   **{bu_p.iloc[0].get('binnen bebouwde kom', np.nan):.1f}%** to **{bu_p.iloc[-1].get('binnen bebouwde kom', np.nan):.1f}%** (chart 3, blue bars).
   Cities have congestion, 30 km/h zones, more traffic lights and roundabouts, and better street lighting
   (fewer accidents in the dark without lighting: chart 2). Ambulances and trauma centres are also closer,
   so a serious injury is less likely to become fatal.
4. **More minor accidents are recorded.** Cities have many more small injury accidents (the denominator), and
   police are close by to record them. This lowers the *ratio* even though the absolute number of severe
   accidents in cities is high.

**Caveats:** this is a correlation between areas, not proof about individual drivers. Brussels drives the
top density class. The ratios of municipalities with few accidents are noisy, so use the minimum-accidents
filter. {a.COORD_IMPUTED.mean() * 100:.1f}% of coordinates were replaced by municipality centres; this does not affect the ratios, because
they are grouped by municipality code, not by GPS position.
""")
    with st.expander("Data behind the charts (by density class)"):
        st.dataframe(prof.round(2), hide_index=True, width="stretch")


# =================================================================== COVID (question 3)
COVID_Q = "Did the COVID-19 lockdowns make road accidents fewer but more severe? Why?"
AREAS = {"Belgium": "België", "Flanders": "Vlaams Gewest", "Wallonia": "Waals Gewest",
         "Brussels": "Brussels Hoofdstedelijk Gewest"}
PHASE_FILL = {"L1": "rgba(215,48,39,0.16)", "L2": "rgba(215,48,39,0.16)",
              "R1": "rgba(253,174,97,0.14)", "R2": "rgba(253,174,97,0.14)"}
CELLS = ["CD_BUILD_UP_AREA", "CD_ROAD_TYPE", "CD_COLLISION_TYPE", "CYCLIST"]


def add_phase_shading(fig, phases):
    for _, r in phases.iterrows():
        if r.CODE in PHASE_FILL:
            x0 = pd.Timestamp(r.FIRST_MONTH + "-01") - pd.Timedelta(days=15)
            x1 = pd.Timestamp(r.LAST_MONTH + "-01") + pd.Timedelta(days=15)
            fig.add_vrect(x0=x0, x1=x1, fillcolor=PHASE_FILL[r.CODE], line_width=0, layer="below",
                          annotation_text=r.PHASE, annotation_position="top left", annotation_font_size=10)


def period_vs_baseline(acc, phase):
    """Accidents of `phase` and the 2017-2019 accidents of the same calendar months."""
    cur = acc[acc.PHASE == phase]
    months = cur.DT_MONTH_COLLISION.unique()
    base = acc[(acc.PHASE == "Baseline 2017-2019") & acc.DT_MONTH_COLLISION.isin(months)]
    # baseline per calendar month = average year; weight months by how often they occur in the phase
    w = cur.groupby("DT_MONTH_COLLISION").DT_YEAR_COLLISION.nunique()
    base_n = sum(base[base.DT_MONTH_COLLISION == mth].shape[0] / 3 * k for mth, k in w.items())
    base_sev = sum(base[base.DT_MONTH_COLLISION == mth].SEVERE.sum() / 3 * k for mth, k in w.items())
    return cur, base, base_n, base_sev


def mix_profile(d):
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


def road_user_group(d):
    return np.select(
        [d.CD_COLLISION_TYPE.isin(["6", "7", "8"]), d.CD_COLLISION_TYPE == "5", d.CYCLIST,
         (d.CD_ROAD_USR_TYPE1 == 7) | (d.CD_ROAD_USR_TYPE2 == 7)],
        ["single vehicle / obstacle", "with a pedestrian", "cyclist involved", "motorcyclist involved"],
        "other (mostly car-car)")


def covid_tab():
    st.subheader(COVID_Q)
    st.caption("Sources: processed accident data (Statbel) · Google COVID-19 Community Mobility Reports "
               "(Belgium, 2020–2022) · Oxford COVID-19 Government Response Tracker (OxCGRT). "
               "**Normal** = average of the same calendar month in 2017–2019.")
    mon = D.load_covid_monthly()
    phases = D.load_covid_phases()
    acc = D.load_processed().copy()
    acc["PHASE"] = D.covid_phase(acc)
    acc["CYCLIST"] = (acc.CD_ROAD_USR_TYPE1 == 3) | (acc.CD_ROAD_USR_TYPE2 == 3)

    area_label = st.segmented_control("Area", list(AREAS), default="Belgium", key="covid_area") or "Belgium"
    area = AREAS[area_label]
    a = acc if area == "België" else acc[acc.TX_RGN_COLLISION_NL == area]
    m = mon[mon.AREA == area].sort_values("DATE")

    # ---------- headline per lockdown
    res = {}
    for ph in ["Lockdown 1", "Lockdown 2"]:
        cur, base, bn, bs = period_vs_baseline(a, ph)
        p = stats.chi2_contingency(pd.crosstab(pd.concat([cur, base]).PHASE, pd.concat([cur, base]).SEVERE))[1]
        res[ph] = dict(n=len(cur), sev=int(cur.SEVERE.sum()), bn=bn, bs=bs, sr=cur.SEVERE.mean() * 100,
                       bsr=bs / bn * 100, p=p)
    cols = st.columns(2)
    for col, ph in zip(cols, res):
        r = res[ph]
        row = phases.set_index("PHASE").loc[ph]
        with col:
            st.markdown(f"**{ph}** ({row.FIRST_MONTH} → {row.LAST_MONTH})")
            k = st.columns(3)
            k[0].metric("Injury accidents vs normal", fmt(r["n"]), f"{(r['n'] / r['bn'] - 1) * 100:+.0f}%",
                        delta_color="inverse")
            k[1].metric("Severe accidents vs normal", fmt(r["sev"]), f"{(r['sev'] / r['bs'] - 1) * 100:+.0f}%",
                        delta_color="inverse")
            k[2].metric("Severity Ratio", f"{r['sr']:.1f}%", f"{r['sr'] - r['bsr']:+.1f} pp vs {r['bsr']:.1f}%",
                        delta_color="inverse")
            st.caption(f"Chi-square test, Severity Ratio vs normal: p = {r['p']:.2g} "
                       f"({'significant' if r['p'] < 0.05 else 'not significant'} at 5%)")
    l1, l2 = res["Lockdown 1"], res["Lockdown 2"]
    l1_yes = l1["sr"] > l1["bsr"] and l1["p"] < 0.05
    l2_yes = l2["sr"] > l2["bsr"] and l2["p"] < 0.05
    def fewer(r):
        ch = (r["n"] / r["bn"] - 1) * 100
        return f"{abs(ch):.0f}% {'fewer' if ch < 0 else 'more'}"
    msg = (f"**{'Yes' if l1_yes else 'No'} for the first lockdown, {'yes' if l2_yes else 'no'} for the second.** "
           f"In {area_label}, Lockdown 1 had {fewer(l1)} injury accidents than normal, and a Severity Ratio of "
           f"**{l1['sr']:.1f}%** (normal {l1['bsr']:.1f}%, p = {l1['p']:.2g}). Lockdown 2 had {fewer(l2)} accidents "
           f"and a ratio of **{l2['sr']:.1f}%** (normal {l2['bsr']:.1f}%, p = {l2['p']:.2g}).")
    (st.success if l1_yes else st.info)(msg)

    # ---------- time series
    st.markdown("#### Accidents and severity month by month (2017–2024)")
    t1, t2 = st.columns(2)
    with t1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=m.DATE, y=m.BASE_ACCIDENTS.where(m.YEAR >= 2020), name="normal (2017–2019 average)",
                                 line=dict(color=GREY, dash="dot")))
        fig.add_trace(go.Scatter(x=m.DATE, y=m.ACCIDENTS, name="injury accidents", line=dict(color="#313695")))
        fig.add_trace(go.Bar(x=m.DATE, y=m.SEVERE, name="severe (class 1–3)", marker_color="#d73027", opacity=0.8))
        add_phase_shading(fig, phases)
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=30, b=0), title="Number of accidents",
                          legend=dict(orientation="h", y=-0.15))
        show_fig(fig, key="cv_n")
    with t2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=m.DATE, y=m.BASE_SEVERITY_RATIO.where(m.YEAR >= 2020), name="normal",
                                 line=dict(color=GREY, dash="dot")))
        fig.add_trace(go.Scatter(x=m.DATE, y=m.SEVERITY_RATIO, name="Severity Ratio", mode="lines+markers",
                                 marker=dict(size=5, color=m.SEVERITY_RATIO, colorscale=SEV_SCALE, cmin=5, cmax=15),
                                 line=dict(color="#9ca3af")))
        add_phase_shading(fig, phases)
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=30, b=0), title="Severity Ratio (%)",
                          legend=dict(orientation="h", y=-0.15))
        show_fig(fig, key="cv_sr")

    # ---------- measures & mobility
    st.markdown("#### Measures and mobility")
    mm = m[(m.DATE >= "2020-02-01") & (m.DATE <= "2022-10-01")]
    t3, t4 = st.columns(2)
    with t3:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=mm.DATE, y=mm.STRINGENCY, name="Stringency index (0–100)", marker_color="#fdae61",
                             opacity=0.6), secondary_y=False)
        for c, lab, colr in [("MOB_WORKPLACES", "workplaces", "#313695"), ("MOB_TRANSIT_STATIONS", "transit", "#74add1"),
                             ("MOB_RESIDENTIAL", "residential", "#a50026")]:
            fig.add_trace(go.Scatter(x=mm.DATE, y=mm[c], name=f"mobility: {lab}", line=dict(color=colr)),
                          secondary_y=True)
        fig.update_yaxes(title_text="Stringency", secondary_y=False, range=[0, 100])
        fig.update_yaxes(title_text="% change vs pre-COVID", secondary_y=True)
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=-0.15),
                          title="Strictness of measures (OxCGRT) and mobility (Google)")
        show_fig(fig, key="cv_mob")
    with t4:
        sc = mon[(mon.AREA != "België") & mon.MOB_WORKPLACES.notna() & (mon.DATE >= "2020-03-01")].copy()
        sc["region"] = sc.AREA.map({v: k for k, v in AREAS.items()})
        y_sel = st.radio("Y axis", ["Accidents vs normal (%)", "Severity Ratio vs normal (pp)"], horizontal=True,
                         key="cv_y")
        ycol = "ACCIDENTS_CHANGE_PCT" if y_sel.startswith("Accidents") else "SR_DIFF_PP"
        fig = px.scatter(sc, x="MOB_WORKPLACES", y=ycol, color="region", hover_data=["YEAR", "MONTH", "PHASE"],
                         color_discrete_map={"Flanders": "#4575b4", "Wallonia": "#f46d43", "Brussels": "#a50026"},
                         labels={"MOB_WORKPLACES": "Workplace mobility vs pre-COVID (%)", ycol: y_sel})
        rho, p = stats.spearmanr(sc.MOB_WORKPLACES, sc[ycol])
        fig.add_hline(y=0, line_color=GREY, line_dash="dot")
        fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=-0.2))
        show_fig(fig, key="cv_sc")
        st.caption(f"Each dot = one region in one month (Mar 2020 – Oct 2022). Spearman ρ = **{rho:.2f}** "
                   f"(p = {p:.2g}).")

    # ---------- why
    st.markdown("---")
    st.markdown("### Why? What was different about lockdown accidents")
    ph = st.radio("Compare with normal (same months 2017–2019)", ["Lockdown 1", "Lockdown 2"], horizontal=True,
                  key="cv_phase")
    cur, base, _, _ = period_vs_baseline(a, ph)
    w1, w2 = st.columns(2)
    with w1:
        prof = pd.DataFrame({"normal": mix_profile(base), ph: mix_profile(cur)}).reset_index(names="share of accidents")
        long = prof.melt(id_vars="share of accidents", var_name="period", value_name="%")
        fig = px.bar(long, y="share of accidents", x="%", color="period", barmode="group", orientation="h",
                     color_discrete_map={"normal": "#9ca3af", ph: "#d73027"}, text="%",
                     title="1 · Which accidents happened (% of all injury accidents)")
        fig.update_traces(texttemplate="%{text:.0f}%")
        fig.update_layout(height=430, margin=dict(l=0, r=0, t=40, b=0), yaxis=dict(autorange="reversed", title=""),
                          legend=dict(orientation="h", y=-0.12))
        show_fig(fig, key="cv_mix")
    with w2:
        g = pd.concat([base.assign(period="normal"), cur.assign(period=ph)])
        g["group"] = road_user_group(g)
        s = g.groupby(["group", "period"]).agg(n=("SEVERE", "size"), SR=("SEVERE", "mean")).reset_index()
        s["SR"] *= 100
        fig = px.bar(s, y="group", x="SR", color="period", barmode="group", orientation="h", text="SR",
                     hover_data={"n": ":,"}, color_discrete_map={"normal": "#9ca3af", ph: "#d73027"},
                     labels={"SR": "Severity Ratio (%)", "group": ""},
                     title="2 · Severity Ratio within each type of accident")
        fig.update_traces(texttemplate="%{text:.1f}%")
        fig.update_layout(height=430, margin=dict(l=0, r=0, t=40, b=0), legend=dict(orientation="h", y=-0.12))
        show_fig(fig, key="cv_within")

    # decomposition: mix vs within
    rates = base.groupby(CELLS).SEVERE.mean().rename("rate")
    c = cur.join(rates, on=CELLS)
    expected = c.rate.fillna(base.SEVERE.mean()).mean() * 100
    base_sr, obs_sr = base.SEVERE.mean() * 100, cur.SEVERE.mean() * 100
    w3, w4 = st.columns([1, 1.4])
    with w3:
        dec = pd.DataFrame({"": ["normal", f"expected from {ph} mix", f"observed in {ph}"],
                            "Severity Ratio (%)": [base_sr, expected, obs_sr]})
        fig = px.bar(dec, x="", y="Severity Ratio (%)", text="Severity Ratio (%)", color="",
                     color_discrete_sequence=["#9ca3af", "#fdae61", "#d73027"],
                     title="3 · Mix effect vs 'same accident, worse outcome'")
        fig.update_traces(texttemplate="%{text:.2f}%")
        fig.update_layout(height=360, margin=dict(l=0, r=0, t=40, b=0), showlegend=False)
        show_fig(fig, key="cv_dec")
    with w4:
        st.markdown(f"""
**How to read chart 3.** *Expected* is the Severity Ratio {ph} would have had if each type of accident
(built-up area × road type × collision type × cyclist yes/no) had been as severe as normal, so only the
**mix** changed.

- Mix effect: **{expected - base_sr:+.2f} pp** (from {base_sr:.2f}% to {expected:.2f}%)
- Within effect: **{obs_sr - expected:+.2f} pp** (positive = the same kind of accident had a worse outcome than normal)

{"Most of the increase is a **within effect**: the same kinds of accidents ended worse." if obs_sr - expected > expected - base_sr and obs_sr > base_sr else "There is no clear within effect."}
""")

    cur1, base1, _, _ = period_vs_baseline(a, "Lockdown 1")
    pm = pd.DataFrame({"n": mix_profile(base1), "l": mix_profile(cur1)})
    ph = "Lockdown 1"
    st.markdown(f"""
**Explanation**

1. **Less traffic, so fewer accidents.** In Lockdown 1, workplace and transit mobility fell by about half and
   stringency rose above 75 (out of 100). With far fewer cars on the road, there were far fewer collisions,
   especially at rush hour and on motorways (motorway share {pm.n["on a motorway"]:.1f}% → {pm.l["on a motorway"]:.1f}%
   in {ph}).
2. **Empty roads, higher speeds.** The Severity Ratio of the *same kind* of accident went up (chart 2 and the
   within effect in chart 3). This fits the higher speeds and more speeding on empty roads that Belgian
   road-safety researchers (Vias institute) reported in spring 2020. Our data has no speed measurements, so this
   is the most likely explanation, not a proof.
3. **A different mix of road users.** More cycling and walking for recreation: the cyclist share rose from
   {pm.n["cyclist involved"]:.0f}% to {pm.l["cyclist involved"]:.0f}%. Single-vehicle crashes rose from
   {pm.n["single vehicle / obstacle"]:.0f}% to {pm.l["single vehicle / obstacle"]:.0f}%. Unprotected road users
   and single-vehicle crashes are more often severe.
4. **Why not in Lockdown 2?** The second lockdown (Nov 2020 – Apr 2021) was lighter for traffic: schools and
   most jobs kept going, and mobility dropped far less. It also fell in the dark, wet season, when roads are not
   empty and speeds stay lower. So fewer accidents, but **no** rise in severity.

**Caveats:** the data is monthly (no day), so March 2020 mixes 17 normal days with 14 lockdown days.
Google mobility measures visits to places, not kilometres driven. The stringency index is national. In small
areas (Brussels) monthly ratios are noisy.
""")

    with st.expander("Data behind this tab: raw and processed files, and how they were processed"):
        d1, d2, d3, d4 = st.tabs(["Phases", "Processed: covid_monthly", "Raw: Google mobility", "Raw: OxCGRT"])
        with d1:
            st.dataframe(phases, hide_index=True, width="stretch")
            st.code(D.load_covid_log(), language=None)
        with d2:
            st.caption("`Data/Processed Data/covid_monthly_2017-2024.csv`: 4 areas × 96 months. Built by "
                       "`Scripts/prepare_covid.py`.")
            st.dataframe(mon, hide_index=True, width="stretch", height=350)
        with d3:
            raw_m = D.load_mobility_raw()
            st.caption(f"`Data/Raw Data/COVID Mobility/` · {fmt(len(raw_m))} rows · "
                       f"{raw_m.date.min()} → {raw_m.date.max()} · per country, region and province. "
                       "There is no 'driving' category. Values are % change against a Jan–Feb 2020 baseline.")
            miss = raw_m.filter(like="percent_change").isna().mean().mul(100).round(1).rename("% missing")
            st.dataframe(miss, width="stretch")
            st.dataframe(raw_m.head(500), width="stretch", height=300)
        with d4:
            raw_o = D.load_measures_raw()
            st.caption(f"`Data/Raw Data/COVID Measures/OxCGRT_compact_national_v1.csv` (all countries, shown: "
                       f"Belgium) · {fmt(len(raw_o))} days.")
            st.dataframe(raw_o, width="stretch", height=300)


# =================================================================== LAYOUT
st.title("🚦 Road accidents in Belgium 2017–2024")
main1, main2, main3 = st.tabs(["📊 Data Explorer", "❓ Density vs severity", "🦠 COVID lockdowns"])
with main1:
    s1, s2 = st.tabs(["1.1 Raw Data Explorer", "1.2 Processed Data Explorer"])
    with s1:
        raw_explorer()
    with s2:
        processed_explorer()
with main2:
    answer_tab()
with main3:
    covid_tab()
