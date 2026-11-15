"""Road accidents in Belgium 2017-2024 - Streamlit app.

Run from the project folder:   streamlit run app.py
Data comes from pipeline.py (run `python pipeline.py` first). Every number shows where it was created
("Source: step ..."), and the tab "Pipeline & method" shows every step, the rows in/out and why.
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from pyproj import Transformer
from scipy import stats

import app_data as D
import pipeline as P

st.set_page_config(page_title="Road accidents BE 2017-2024", page_icon="🚦", layout="wide")

SEV_COLORS = ["#313695", "#4575b4", "#74add1", "#fdae61", "#f46d43", "#d73027", "#a50026"]
SEV_SCALE = [[i / (len(SEV_COLORS) - 1), c] for i, c in enumerate(SEV_COLORS)]
SEV_RANGE = (0, 20)
GREY = "#6b7280"
BE_CENTER = {"lat": 50.52, "lon": 4.47}
QUESTION = "Is it true that as the density of the population increases, the severity of the accidents decreases? Why?"
COVID_Q = "Did the COVID-19 lockdowns make road accidents fewer but more severe? Why?"

# ---------------------------------------------------------------- assumptions (same as decision_log.md)
ASSUMPTIONS = {
    "casualties": ("Only accidents with casualties",
                   "This dataset contains only accidents with at least one death or injury. Accidents with only "
                   "material damage are not included, so the most dangerous place according to this data is not the "
                   "same as the place with the most accidents. The Severity Ratio is therefore a share among injury "
                   "accidents, not among all accidents."),
    "coordinates": ("Missing / abnormal coordinates",
                    "36,628 accidents (12.7%) have no usable own coordinate: 35,881 missing, 2 impossible, 745 more than "
                    "1 km outside their municipality. 15-19% per year before 2022, 3-6% from 2022. They get the "
                    "municipality centre (step 6) so they still count in all numbers grouped by municipality, but they are "
                    "by default not drawn in the grey GPS heat layer (step 8). A switch on the map adds them at the "
                    "municipality centre."),
    "denominator": ("The denominator problem",
                    "More accidents in a place can simply mean more residents or more traffic. This project does not "
                    "rank places by accident counts. It uses (1) the Severity Ratio, a share that does not grow with "
                    "traffic volume, and (2) population density from Statbel as the explanatory variable. Accidents per "
                    "1,000 inhabitants are shown in the tables. There is NO traffic-volume (vehicle-km) data, so "
                    "'risk per km driven' cannot be computed."),
    "categories": ("Categories are a choice",
                   "Severe = class 1, 2, 3. Density classes, collision groups, road-user groups and COVID phases are our "
                   "own classification rules. The full list per chart is in the tab 'Pipeline & method' → 'Category rules'."),
    "ecological": ("Areas, not individuals",
                   "Relations are measured between areas (municipalities, months), not between individual drivers "
                   "(ecological fallacy). Small municipalities give noisy ratios."),
    "covid": ("COVID assumptions",
              "Months only (no day): March 2020 counts as Lockdown 1 although it started on 18/03. 'Normal' = average of "
              "the same month in 2017-2019. Google mobility measures visits to places, not kilometres driven. The "
              "stringency index is national."),
}


def fmt(n):
    return f"{n:,.0f}".replace(",", " ")


def E(key):
    """Explanation dot text (pipeline.EXPLANATIONS)."""
    return P.explain(key)


def show_fig(fig, key=None, explain=None, title=None):
    """Chart with its title as a heading carrying an explanation dot (?) - the title moves out of the figure."""
    if explain:
        t = title or (fig.layout.title.text if fig.layout.title and fig.layout.title.text else "")
        st.markdown(f"**{t}**" if t else "&nbsp;", help=E(explain))
        fig.update_layout(title=None)
    st.plotly_chart(fig, width="stretch", key=key)


def table(data, **kwargs):
    """st.dataframe with an explanation dot (?) on every column header found in pipeline.COLUMN_HELP."""
    df = data.to_frame() if isinstance(data, pd.Series) else data
    cfg = {c: st.column_config.Column(help=P.COLUMN_HELP[c]) for c in getattr(df, "columns", [])
           if isinstance(c, str) and c in P.COLUMN_HELP}
    cfg.update(kwargs.pop("column_config", None) or {})
    return st.dataframe(df, column_config=cfg, **kwargs)


def dot(label, key):
    """A small caption line with an explanation dot."""
    st.caption(label, help=E(key))


def src(text):
    """Lineage line under a number or chart: where it was created."""
    st.caption(f"🔎 *Source:* {text}")


def assumptions_box(keys, title="Assumptions behind this tab"):
    with st.expander(f"⚠️ {title}"):
        for k in keys:
            t, body = ASSUMPTIONS[k]
            st.markdown(f"**{t}.** {body}")


def rows_used(rows):
    """Small table: rows used for each element of a tab, and why rows are left out."""
    with st.expander("🧮 Rows used in this tab (and what is left out)"):
        table(pd.DataFrame(rows, columns=["element", "rows in", "rows used", "left out", "why"]),
                     hide_index=True, width="stretch")


# =================================================================== Row funnel (top of the Pipeline & method tab)
def top_funnel():
    steps = D.load_steps()
    acc_steps = steps[steps.order.str.fullmatch(r"\d")]
    raw_n = int(acc_steps.rows_in.iloc[0])
    geo_n = int(acc_steps.rows_out.iloc[-1])
    c1, c2 = st.columns([2.2, 1])
    with c1:
        fig = go.Figure(go.Funnel(
            y=[f"{r.order}. {r.step}" for r in acc_steps.itertuples()], x=acc_steps.rows_out,
            textinfo="value+percent initial", marker=dict(color=["#4575b4"] * (len(acc_steps) - 1) + ["#f46d43"]),
            connector=dict(line=dict(color="#d1d5db"))))
        fig.update_layout(height=290, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(tickfont=dict(size=11)))
        show_fig(fig, key="funnel", explain="funnel", title="Row funnel – accident rows after each step")
    with c2:
        st.markdown("**Row funnel – where data disappears**")
        st.markdown(f"- Raw accidents: **{fmt(raw_n)}**\n"
                    f"- Steps 2–7 drop **0 rows**: they fix or add values\n"
                    f"- Step 8 is **not** a drop from the data: **{fmt(raw_n - geo_n)} ({(raw_n - geo_n) / raw_n * 100:.1f}%)** "
                    f"have no usable own coordinate → by default not drawn in the GPS heat layer (switch on the map)\n"
                    f"- All counts and ratios use all **{fmt(raw_n)}** rows (grouped by municipality code)")
        st.caption("Details per step: the expanders below.")


# =================================================================== PIPELINE & METHOD
LINEAGE = [
    ("Pipeline & method: row funnel", "rows in/out per step", "pipeline.run_all → pipeline_steps.csv", "steps 1–8"),
    ("1.1 Raw: missing / unknown / issues / checks", "counts per column", "app_data.raw_quality on the raw xlsx", "step 1 (raw)"),
    ("1.1 Raw: coordinate status", "ok / missing / out of range / > 1 km", "pipeline.step_check_coordinates → COORD_STATUS, DIST_TO_OWN_MUNTY_M", "step 5"),
    ("1.2 Processed: columns removed", "14 FR columns", "pipeline.step_drop_french", "step 2"),
    ("1.2 Processed: province filled", "30,022 rows", "pipeline.step_fill_province", "step 3"),
    ("1.2 Processed / tab 2: POPULATION, AREA_KM2, POP_DENSITY", "per municipality and year",
     "pipeline.build_density → population_density_2017-2024.csv; joined in pipeline.step_add_density", "P1 + step 4"),
    ("1.2 Processed: coordinates replaced", "36,628 rows", "pipeline.step_impute_coordinates → COORD_IMPUTED", "step 6"),
    ("Maps: LAT / LON", "WGS84 positions", "pipeline.step_add_wgs84", "step 7"),
    ("Tab 2: grey heat layer", "accidents at GPS position", "switch off: pipeline.step_select_georeferenced (step 8, own "
     "coordinates only) · switch on: all rows, replaced ones at the municipality centre (step 6)", "steps 6–8"),
    ("Tab 2: severe / Severity Ratio (all)", "class 1-3 share", "pipeline.is_severe, pipeline.severity_ratio", "analysis"),
    ("Tab 2: dots on the map + table", "per region / province / municipality / BE",
     "pipeline.aggregate_by_level (density = Σ population / Σ area; centre from unit_centers.csv)", "analysis (uses steps 4, 7)"),
    ("1.1 / 1.2 / tab 2: municipality borders and centres", "581 municipalities", "pipeline.build_municipalities → municipality_centers_2024.csv", "G1"),
    ("Tab 2: unit centres and borders", "LAT / LON of each dot", "pipeline.build_units → unit_centers.csv, outlines_*.geojson", "G2"),
    ("Tab 2: Spearman ρ, trend", "relation density ↔ SR", "scipy.stats.spearmanr / numpy.polyfit in app.py on aggregate_by_level", "analysis"),
    ("Tab 2: 'Why' charts", "per density class", "pipeline.density_class_profile, pipeline.collision_group", "analysis"),
    ("Tab 3: monthly accidents, SR, normal, mobility, stringency", "per month and area",
     "pipeline.covid_monthly → covid_monthly_2017-2024.csv", "C1, C2, C3"),
    ("Tab 3: lockdown metrics, chi-square", "per lockdown vs normal", "pipeline.period_vs_baseline + scipy.stats.chi2_contingency", "analysis"),
    ("Tab 3: mix vs within effect", "standardised SR", "pipeline.mix_decomposition", "analysis"),
    ("Tab 3: accident mix / SR per group", "shares and SR", "pipeline.mix_profile, pipeline.road_user_group", "analysis"),
]


def pipeline_tab():
    st.subheader("Pipeline & method")
    st.markdown("Every number in this app comes from a function in `pipeline.py`. `python pipeline.py` runs the steps "
                "below in order and writes the files in `Data/Processed Data`. The app only reads those files.")
    top_funnel()
    t1, t2, t3, t4, t5 = st.tabs(["Steps (rows in/out)", "Where does each number come from?", "Assumptions",
                                  "Category rules", "Decision log & tests"])
    with t1:
        steps = D.load_steps()
        table(steps[["order", "dataset", "step", "tabs", "rows_in", "rows_out", "rows_dropped", "rows_changed",
                            "function", "why"]].rename(columns={"dataset": "data set", "tabs": "used in tab(s)"}),
                     hide_index=True, width="stretch")
        st.markdown("Steps **G1–G2** build the **geography**, **P1** the **population density**, **1–8** work on the "
                    "**accident data**, **C1–C3** on the **COVID data**. Each title shows the data set, what the step "
                    "does, and the tabs that use the result. Steps that *group* rows (G1, G2, P1, C3) lose nothing: "
                    "fewer rows out means rows were combined.")
        for r in steps.itertuples():
            label = (f"Step {r.order} · {r.dataset} · {r.step}  →  used in: {r.tabs}  —  in {fmt(r.rows_in)} → out {fmt(r.rows_out)}"
                     f"{(' · not drawn in heat layer by default ' if r.order == '8' else ' · dropped ') + fmt(r.rows_dropped) if r.rows_dropped else ''}"
                     f"{' · changed ' + fmt(r.rows_changed) if r.rows_changed else ''}")
            with st.expander(label):
                c = st.columns(4)
                c[0].metric("Rows in", fmt(r.rows_in), help=E("step_rows_in"))
                c[1].metric("Rows out", fmt(r.rows_out), help=E("step_rows_out"))
                c[2].metric("Dropped", fmt(r.rows_dropped), help=E("step_dropped"))
                c[3].metric("Changed", fmt(r.rows_changed), help=E("step_changed"))
                st.markdown(f"**Data set:** {r.dataset}  \n**Used in tab(s):** {r.tabs}  \n**Why:** {r.why}")
                st.caption(f"Function: `pipeline.{r.function}`")
                sample = D.load_sample(r.order)
                if sample is not None:
                    st.markdown("Sample after this step (rows the step changed, if any):")
                    table(sample, width="stretch", hide_index=True)
        st.markdown("**Rows without usable own coordinate, per year (excluded from the GPS heat layer)**")
        cy = D.load_coords_by_year()
        fig = px.bar(cy, x="YEAR", y="excluded_pct", text="excluded_from_gps_map",
                     labels={"excluded_pct": "% of accidents", "YEAR": "Year"})
        fig.update_traces(marker_color="#f46d43", texttemplate="%{text:,}")
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0))
        show_fig(fig, key="cy", explain="coords_by_year", title="Accidents without usable own coordinate, per year (%)")
        table(cy, hide_index=True, width="stretch")
        src("pipeline.coordinates_by_year → coordinates_by_year.csv (step 5 status per year)")
    with t2:
        table(pd.DataFrame(LINEAGE, columns=["where in the app", "number", "created by", "step"]),
                     hide_index=True, width="stretch", height=600)
    with t3:
        for t, body in ASSUMPTIONS.values():
            st.markdown(f"**{t}.** {body}")
    with t4:
        table(pd.DataFrame(P.CATEGORY_RULES, columns=["category / chart", "rule", "note"]),
                     hide_index=True, width="stretch", height=560)
        src("pipeline.CATEGORY_RULES (same rules as in CLAUDE.md)")
    with t5:
        a, b = st.tabs(["decision_log.md", "tests/TEST_GAPS.md"])
        with a:
            st.markdown(D.load_markdown(D.DECISION_LOG))
        with b:
            st.markdown(D.load_markdown(D.TEST_GAPS))


# =================================================================== DATA EXPLORER
def raw_explorer():
    st.subheader("Raw data – Accidents")
    st.caption(f"Source: Statbel, *Geolocatie van de verkeersongevallen 2017–2024* · `{P.RAW_ACCIDENTS.name}`, "
               f"`{P.VAR_LIST.name}`")
    st.markdown("#### Variable list (`VAR_LIST_ACC_OPENDATA_MAP.xlsx`)")
    table(D.load_var_list(), width="stretch", hide_index=True, height=420)

    raw, q = D.load_raw(), D.raw_quality()
    st.markdown("#### Accident data (`OPENDATA_MAP_2017-2024.xlsx`)")
    c = st.columns(5)
    c[0].metric("Rows (accidents)", fmt(len(raw)), help=E("raw_rows"))
    c[1].metric("Columns", raw.shape[1], help=E("raw_columns"))
    c[2].metric("Municipalities (CD_NIS)", raw.CD_NIS.nunique(), help=E("raw_municipalities"))
    c[3].metric("Rows with ≥1 missing value", fmt(raw.isna().any(axis=1).sum()), help=E("raw_rows_missing"))
    c[4].metric("Exact duplicate rows", fmt(raw.duplicated().sum()), help=E("raw_duplicates"))
    src("step 1 – raw file as delivered by Statbel (pipeline.load_raw_accidents)")
    with st.expander("Browse the raw data"):
        n = st.slider("Rows to show", 100, 5000, 500, step=100, key="raw_rows")
        yr = st.multiselect("Year", sorted(raw.DT_YEAR_COLLISION.unique()), key="raw_year")
        table((raw[raw.DT_YEAR_COLLISION.isin(yr)] if yr else raw).head(n), width="stretch", height=400)

    st.markdown("### Data quality")
    t1, t2, t3, t4 = st.tabs(["Missing values", "Unknown / unspecified", "Inconsistent & incorrect", "Coordinates"])
    with t1:
        m = q["missing"]
        st.markdown(f"**{len(m)} of {raw.shape[1]} columns** have empty cells. Everything else is complete.")
        fig = px.bar(m, x="missing", y="column", orientation="h", text="missing %",
                     labels={"missing": "Empty cells", "column": ""})
        fig.update_traces(marker_color="#d73027", texttemplate="%{text:.1f}%")
        fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0))
        show_fig(fig, explain="raw_missing", title="Empty cells per column")
        table(m, hide_index=True, width="stretch")
        miss_rgn = raw[raw.TX_PROV_COLLISION_NL.isna()].TX_RGN_COLLISION_NL.value_counts()
        st.info(f"Province is empty only for **{', '.join(miss_rgn.index)}** ({fmt(miss_rgn.sum())} rows): Brussels "
                "does not belong to a province, so this is structural, not an error.")
        src("app_data.raw_quality – raw file (step 1)")
    with t2:
        st.markdown("Cells that are filled in but mean *unknown / not specified*. They are not empty, so they do not "
                    "show up as missing values.")
        u = q["unknown"]
        fig = px.bar(u, x="% of rows", y="column", orientation="h", text="rows")
        fig.update_traces(marker_color="#fdae61", texttemplate="%{text:,}")
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"))
        show_fig(fig, explain="raw_unknown", title="Cells meaning 'unknown' per column (% of rows)")
        table(u, hide_index=True, width="stretch")
        src("app_data.raw_quality with pipeline.UNKNOWN_CODES – raw file (step 1)")
        col = st.selectbox("Distribution of a coded column", list(D.CODE_LABEL)[:-1], index=6, key="dist_col")
        lab = D.CODE_LABEL[col]
        dist = raw.groupby([col, lab], dropna=False).size().reset_index(name="rows")
        dist["unknown"] = dist[col].isin(P.UNKNOWN_CODES.get(col, []))
        dist["label"] = dist[col].astype(str) + " – " + dist[lab].astype(str)
        fig = px.bar(dist.sort_values("rows"), x="rows", y="label", color="unknown", orientation="h",
                     color_discrete_map={True: "#fdae61", False: "#4575b4"}, labels={"label": ""})
        fig.update_layout(height=max(250, 28 * len(dist)), margin=dict(l=0, r=0, t=10, b=0))
        show_fig(fig, explain="raw_code_dist", title="Accidents per code")
    with t3:
        table(q["issues"], hide_index=True, width="stretch",
                     column_config={"rows": st.column_config.NumberColumn(format="%d", help=P.COLUMN_HELP["rows"]),
                                    "issue": st.column_config.TextColumn(width="large", help=P.COLUMN_HELP["issue"])})
        a, b = st.columns(2)
        with a:
            st.markdown("**Code ↔ label consistency** (each code should have exactly one label)")
            table(q["code_label"], hide_index=True, width="stretch")
        with b:
            st.markdown("**Checks passed / failed**")
            table(q["checks"].assign(passed=q["checks"].passed.map({True: "✅", False: "❌"})),
                         hide_index=True, width="stretch")
        src("app_data.raw_quality – raw file (step 1); 'handling' column = the pipeline step that deals with it")
        dups = raw[raw.duplicated(keep=False)].sort_values(list(raw.columns[:4]))
        with st.expander(f"Show the {fmt(len(dups))} rows involved in exact duplicates"):
            table(dups, width="stretch", height=300)
    with t4:
        status = D.raw_coordinate_status()
        counts = status.value_counts().rename_axis("status").reset_index(name="rows")
        counts["%"] = (counts.rows / len(status) * 100).round(2)
        a, b = st.columns([1, 2])
        with a:
            st.markdown("Each point (Lambert 72) is checked against the border of the municipality in `CD_NIS` "
                        "(Statbel 2024 statistical sectors).")
            table(counts, hide_index=True, width="stretch")
        with b:
            cy = D.load_coords_by_year()
            long = cy.melt(id_vars="YEAR", value_vars=[c for c in ["missing", "out_of_range", "outside_municipality"] if c in cy],
                           var_name="status", value_name="rows")
            fig = px.bar(long, x="YEAR", y="rows", color="status", labels={"YEAR": "Year", "rows": "Rows with a problem"},
                         color_discrete_sequence=["#d73027", "#a50026", "#fdae61"])
            fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), legend_title="")
            show_fig(fig, explain="raw_coord_year", title="Coordinate problems per year")
        src("pipeline.step_check_coordinates (step 5) → COORD_STATUS, DIST_TO_OWN_MUNTY_M")
        p = D.load_processed()
        bad = p[p.COORD_STATUS == "outside_municipality"]
        lon, lat = Transformer.from_crs(31370, 4326, always_xy=True).transform(bad.MS_X_COORD_ORIG.values,
                                                                               bad.MS_Y_COORD_ORIG.values)
        fig = go.Figure(go.Scattermap(
            lat=lat, lon=lon, mode="markers",
            marker=dict(size=7, color=np.minimum(bad.DIST_TO_OWN_MUNTY_M / 1000, 50), colorscale="OrRd", cmin=0, cmax=50,
                        colorbar=dict(title="km outside")),
            text=bad.TX_MUNTY_COLLISION_NL,
            hovertemplate="Recorded municipality: %{text}<br>%{marker.color:.1f} km outside<extra></extra>"))
        fig.update_layout(map=dict(style="carto-positron", center=BE_CENTER, zoom=6.4), height=480,
                          margin=dict(l=0, r=0, t=30, b=0),
                          title=f"Where the {fmt(len(bad))} points lying > 1 km outside their municipality were recorded")
        show_fig(fig, explain="raw_coord_map")


def processed_explorer():
    st.subheader("Processed data")
    st.caption("Built by `pipeline.py` from the raw accident data, Statbel population figures and Statbel borders.")
    p, dens, raw_cols = D.load_processed(), D.load_density(), list(D.load_raw().columns)
    t1, t2, t3, t4 = st.tabs(["Tables", "What changed", "Coordinates fixed", "Population density"])
    with t1:
        which = st.radio("Data set", ["accidents_processed_2017-2024", "population_density_2017-2024.csv",
                                      "municipality_centers_2024.csv", "unit_centers.csv", "covid_monthly_2017-2024.csv",
                                      "covid_phases.csv"], horizontal=True)
        if which.startswith("accidents"):
            c = st.columns(3)
            c[0].metric("Rows", fmt(len(p)), help=E("proc_rows"))
            c[1].metric("Columns", p.shape[1], help=E("proc_columns"))
            c[2].metric("Empty cells in key columns",
                        int(p[["MS_X_COORD", "MS_Y_COORD", "TX_PROV_COLLISION_NL", "POP_DENSITY"]].isna().sum().sum()),
                        help=E("proc_empty_key"))
            src("output of step 7 (accidents_processed_2017-2024.csv / .parquet)")
            f1, f2, f3 = st.columns(3)
            yr = f1.multiselect("Year", sorted(p.DT_YEAR_COLLISION.unique()))
            rg = f2.multiselect("Region", sorted(p.TX_RGN_COLLISION_NL.unique()))
            only = f3.selectbox("Rows", ["All", "Only rows with replaced coordinates"])
            v = p
            if yr:
                v = v[v.DT_YEAR_COLLISION.isin(yr)]
            if rg:
                v = v[v.TX_RGN_COLLISION_NL.isin(rg)]
            if only != "All":
                v = v[v.COORD_IMPUTED]
            st.caption(f"{fmt(len(v))} matching rows. The first 2,000 are shown.")
            table(v.head(2000), width="stretch", height=450)
        else:
            path = {"population": P.OUT_DENSITY, "municipality": P.OUT_CENTERS, "unit": P.OUT_UNIT_CENTERS,
                    "covid_monthly": P.OUT_COVID_MONTHLY, "covid_phases": P.OUT_COVID_PHASES}
            key = next(k for k in path if which.startswith(k))
            table(D.read_csv(path[key]), width="stretch", height=450, hide_index=True)
        with st.expander("Processing log (processing_log.txt)"):
            st.code(D.load_log(), language=None)
    with t2:
        removed = [c for c in raw_cols if c not in p.columns]
        added = [c for c in p.columns if c not in raw_cols]
        desc = {"POPULATION": "Population on 1 January of the accident year (step 4)",
                "AREA_KM2": "Area of the municipality in km² (step 4)",
                "POP_DENSITY": "Inhabitants per km² for that municipality and year (step 4)",
                "MS_X_COORD_ORIG": "Original X coordinate (step 5)", "MS_Y_COORD_ORIG": "Original Y coordinate (step 5)",
                "DIST_TO_OWN_MUNTY_M": "Distance (m) from the original point to its municipality; 0 = inside (step 5)",
                "COORD_STATUS": "ok / missing / out_of_range / outside_municipality (step 5)",
                "COORD_IMPUTED": "True if MS_X/Y_COORD were replaced by the municipality centre (step 6)",
                "LAT": "Latitude (WGS84) of the final coordinates (step 7)",
                "LON": "Longitude (WGS84) of the final coordinates (step 7)"}
        a, b = st.columns(2)
        with a:
            st.markdown(f"**➖ Removed (step 2): {len(removed)} French columns**")
            table(pd.DataFrame({"column": removed}), hide_index=True, width="stretch", height=300)
        with b:
            st.markdown(f"**➕ Added: {len(added)} columns**")
            table(pd.DataFrame({"column": added, "meaning": [desc.get(c, "") for c in added]}),
                         hide_index=True, width="stretch", height=300)
        raw = D.load_raw()
        before = raw[["TX_PROV_COLLISION_NL", "MS_X_COORD"]].isna().sum()
        comp = pd.DataFrame({
            "column": ["TX_PROV_COLLISION_NL", "MS_X_COORD / MS_Y_COORD", "POP_DENSITY"],
            "step": ["3", "5-6", "4"],
            "empty before": [before.TX_PROV_COLLISION_NL, before.MS_X_COORD, len(p)],
            "values changed": [before.TX_PROV_COLLISION_NL, int(p.COORD_IMPUTED.sum()), len(p)],
            "empty after": [p.TX_PROV_COLLISION_NL.isna().sum(), p.MS_X_COORD.isna().sum(), p.POP_DENSITY.isna().sum()],
            "how": ["Filled with 'Brussels Hoofdstedelijk Gewest' (province view)",
                    "Missing, impossible or > 1 km outside municipality → centre of the municipality",
                    "New column: joined from Statbel on CD_NIS + year"]})
        st.markdown("**🔧 Values fixed / filled**")
        table(comp, hide_index=True, width="stretch")
        prov = p.TX_PROV_COLLISION_NL.value_counts().rename_axis("province").reset_index(name="accidents")
        fig = px.bar(prov, x="accidents", y="province", orientation="h",
                     color=prov.province.eq(P.BRUSSELS).map({True: "filled (step 3)", False: "original"}),
                     color_discrete_map={"filled (step 3)": "#f46d43", "original": "#4575b4"},
                     labels={"color": "", "province": ""}, title="Accidents per province after filling Brussels")
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0), yaxis=dict(autorange="reversed"))
        show_fig(fig, explain="proc_provinces")
    with t3:
        s = p.COORD_STATUS.value_counts().rename_axis("status").reset_index(name="rows")
        c = st.columns(len(s) + 1)
        c[0].metric("Coordinates replaced", fmt(p.COORD_IMPUTED.sum()), f"{p.COORD_IMPUTED.mean() * 100:.1f}% of rows",
                    delta_color="off", help=E("coord_replaced"))
        for i, r in s.iterrows():
            c[i + 1].metric(r.status, fmt(r.rows), help=E(f"status_{r.status}"))
        src("step 5 (COORD_STATUS) and step 6 (COORD_IMPUTED)")
        by = p[p.COORD_IMPUTED].groupby(["DT_YEAR_COLLISION", "COORD_STATUS"]).size().reset_index(name="rows")
        fig = px.bar(by, x="DT_YEAR_COLLISION", y="rows", color="COORD_STATUS",
                     labels={"DT_YEAR_COLLISION": "Year", "rows": "Rows replaced", "COORD_STATUS": ""},
                     color_discrete_sequence=["#d73027", "#fdae61", "#a50026"], title="Replaced coordinates per year")
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0))
        show_fig(fig, explain="proc_replaced_year")
        st.markdown("**Points > 1 km outside their municipality: original position → municipality centre**")
        bad = p[p.COORD_STATUS == "outside_municipality"]
        olon, olat = Transformer.from_crs(31370, 4326, always_xy=True).transform(bad.MS_X_COORD_ORIG.values,
                                                                                 bad.MS_Y_COORD_ORIG.values)
        fig = go.Figure()
        fig.add_trace(go.Scattermap(lat=np.column_stack([olat, bad.LAT, np.full(len(bad), np.nan)]).ravel(),
                                    lon=np.column_stack([olon, bad.LON, np.full(len(bad), np.nan)]).ravel(),
                                    mode="lines", line=dict(width=1, color=GREY), name="moved", hoverinfo="skip"))
        fig.add_trace(go.Scattermap(lat=olat, lon=olon, mode="markers", marker=dict(size=6, color="#d73027"),
                                    name="original (wrong) position", text=bad.TX_MUNTY_COLLISION_NL,
                                    hovertemplate="%{text}<extra>original</extra>"))
        fig.add_trace(go.Scattermap(lat=bad.LAT, lon=bad.LON, mode="markers", marker=dict(size=8, color="#1a9850"),
                                    name="municipality centre (new)", text=bad.TX_MUNTY_COLLISION_NL,
                                    hovertemplate="%{text}<extra>new</extra>"))
        fig.update_layout(map=dict(style="carto-positron", center=BE_CENTER, zoom=6.4), height=520,
                          margin=dict(l=0, r=0, t=0, b=0), legend=dict(x=0, y=1, bgcolor="rgba(255,255,255,.8)"))
        show_fig(fig, explain="proc_moved_map", title="Original position → municipality centre")
        st.caption(f"{fmt(((p.DIST_TO_OWN_MUNTY_M > 0) & (p.DIST_TO_OWN_MUNTY_M <= 1000)).sum())} points less than 1 km "
                   "outside their municipality (mostly border roads) were kept as they are.")
    with t4:
        st.markdown("Population density = population on 1 January / area. **2019–2024** come straight from Statbel "
                    "(`Pop_density_en.xlsx`). For **2017–2018** the population (`Bevolking_per_gemeente.xlsx`) was "
                    "converted to the 2019 municipalities (7 mergers + Hainaut renumbering) and divided by the 2019 area.")
        tot = dens.groupby(["YEAR", "SOURCE"]).agg(municipalities=("CD_NIS", "nunique"),
                                                   population=("POPULATION", "sum")).reset_index()
        table(tot, hide_index=True, width="stretch")
        src("pipeline.build_density → population_density_2017-2024.csv (used in step 4)")
        fig = px.box(dens, x="YEAR", y="POP_DENSITY", log_y=True, points=False,
                     labels={"POP_DENSITY": "Inhabitants / km² (log)", "YEAR": "Year"},
                     title="Distribution of municipal population density per year")
        fig.update_traces(marker_color="#4575b4")
        fig.update_layout(height=360, margin=dict(l=0, r=0, t=40, b=0))
        show_fig(fig, explain="proc_density_box")


# =================================================================== TAB 2: density vs severity
def heat_map(agg, level, geo_acc, heat_mode):
    fig = go.Figure()
    if heat_mode != "Off":
        a = geo_acc[geo_acc.CD_CLASS_ACCIDENTS.isin(P.SEVERE_CLASSES)] if heat_mode == "Severe accidents" else geo_acc
        grid = (a.assign(lat=(a.LAT / 0.02).round() * 0.02, lon=(a.LON / 0.03).round() * 0.03)
                .groupby(["lat", "lon"]).size().reset_index(name="n"))
        fig.add_trace(go.Densitymap(
            lat=grid.lat, lon=grid.lon, z=np.log1p(grid.n), radius=14, hoverinfo="skip", showscale=False,
            colorscale=[[0, "rgba(90,90,90,0)"], [0.3, "rgba(90,90,90,0.25)"], [1, "rgba(40,40,40,0.75)"]]))
    d = np.log10(agg.POP_DENSITY)
    size = (10 + 26 * (d - d.min()) / max(d.max() - d.min(), 1e-9)) if len(agg) > 1 else pd.Series([40])
    if level == "Municipalities":
        size = size * 0.55
    fig.add_trace(go.Scattermap(
        lat=agg.LAT, lon=agg.LON, mode="markers",
        marker=dict(size=size, color=agg.SEVERITY_RATIO, colorscale=SEV_SCALE, cmin=SEV_RANGE[0], cmax=SEV_RANGE[1],
                    opacity=0.92, colorbar=dict(title=dict(text="Severity<br>Ratio (%)"), thickness=14, len=0.75)),
        customdata=np.column_stack([agg.NAME, agg.POP_DENSITY, agg.ACCIDENTS, agg.SEVERE, agg.SEVERITY_RATIO,
                                    agg.ACCIDENTS_PER_1000_INH_YEAR]),
        hovertemplate=("<b>%{customdata[0]}</b><br>Population density: %{customdata[1]:,.0f} inh./km²"
                       "<br>Injury accidents: %{customdata[2]:,} (%{customdata[5]:.2f} per 1,000 inh. per year)"
                       "<br>Severe (class 1-3): %{customdata[3]:,}<br><b>Severity Ratio: %{customdata[4]:.1f}%</b>"
                       "<extra></extra>")))
    fig.update_layout(map=dict(style="carto-positron", center=BE_CENTER, zoom=6.55,
                               layers=[dict(source=D.load_outline(level), type="line", color="#374151",
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
                                 hoverinfo="skip"))
        rho, pval = stats.spearmanr(a.POP_DENSITY, a.SEVERITY_RATIO)
        res = dict(rho=rho, p=pval, slope=slope, n=len(a))
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0), coloraxis_showscale=False, showlegend=False)
    return fig, res


def density_tab():
    st.subheader(QUESTION)
    assumptions_box(["casualties", "denominator", "coordinates", "categories", "ecological"])
    acc, dens, look, units = D.load_processed(), D.load_density(), D.load_lookup(), D.load_unit_centers()

    c1, c2, c3 = st.columns([2, 1.3, 1.3])
    level = c1.segmented_control("Border view", ["Regions", "Provinces", "Municipalities", "BE"],
                                 default="Provinces", key="level") or "Provinces"
    years = c2.select_slider("Years", options=list(range(2017, 2025)), value=(2017, 2024))
    heat_mode = c3.radio("Accident heat layer (GPS positions)", ["All accidents", "Severe accidents", "Off"], horizontal=True)
    n_imputed_sel = int(acc[acc.DT_YEAR_COLLISION.between(*years)].COORD_IMPUTED.sum())
    include_imputed = c3.toggle(f"Include accidents placed at the municipality centre ({fmt(n_imputed_sel)})", value=False,
                                key="heat_imputed",
                                help="Off: only accidents at their own GPS position (step 8). On: also the accidents "
                                     "whose coordinate was missing or abnormal, drawn at the centre of their municipality (step 6).")
    yrs = list(range(years[0], years[1] + 1))
    a, _ = P.filter_years(acc, yrs)
    own_geo, _ = P.step_select_georeferenced(a)
    geo = a if include_imputed else own_geo
    agg = P.aggregate_by_level(acc, dens, look, units, level, yrs)
    mun = P.aggregate_by_level(acc, dens, look, units, "Municipalities", yrs)
    prof = P.density_class_profile(a)

    rho, pval = stats.spearmanr(mun.POP_DENSITY, mun.SEVERITY_RATIO)
    sev = P.is_severe(a.CD_CLASS_ACCIDENTS)
    k = st.columns(4)
    k[0].metric("Injury accidents", fmt(len(a)), help=E("d_accidents"))
    k[1].metric("Severe (class 1–3)", fmt(sev.sum()), help=E("d_severe"))
    k[2].metric("Severity Ratio Belgium", f"{sev.mean() * 100:.1f}%", help=E("d_sr_be"))
    k[3].metric("Spearman ρ density ↔ SR (581 municipalities)", f"{rho:.2f}",
                "p < 0.001" if pval < 0.001 else f"p = {pval:.3f}", delta_color="off", help=E("d_rho"))
    src("rows: steps 1–7 + year filter · severe: pipeline.is_severe (class 1-3) · SR: pipeline.severity_ratio · "
        "ρ: scipy.stats.spearmanr on pipeline.aggregate_by_level('Municipalities')")
    verdict = "Yes" if rho < 0 and pval < 0.05 else "No clear evidence"
    st.success(f"**{verdict}.** The Severity Ratio is **{prof['Severity Ratio (%)'].iloc[0]:.1f}%** in municipalities "
               f"with fewer than 250 inhabitants/km² and **{prof['Severity Ratio (%)'].iloc[-1]:.1f}%** in municipalities "
               f"with more than 5,000 inhabitants/km². Denser areas have more injury accidents, but a smaller share of "
               f"them are severe. The *why* is explained below the map.")
    dot("ⓘ How is this answer computed?", "d_answer")
    st.caption("Severity Ratio = accidents of class 1 (deaths), 2 (fatally injured) and 3 (seriously injured) ÷ all "
               "recorded injury accidents × 100. Each accident counts once.")

    st.markdown(f"#### Heat map – {level.lower() if level != 'BE' else 'Belgium'}")
    st.caption("Each **dot** sits at the centre of a unit. **Colour** = Severity Ratio (blue = low, red = high). "
               "**Size** = population density. The grey **heat layer** shows accidents at their own GPS position.")
    excl = len(a) - len(geo)
    n_imp = len(a) - len(own_geo)
    if include_imputed:
        st.caption(f"⚠️ Heat layer: **all {fmt(len(a))} accidents** are drawn, including **{fmt(n_imp)} "
                   f"({n_imp / len(a) * 100:.1f}%)** placed at the **centre of their municipality** (step 6). Dark spots on "
                   f"municipality centres are partly caused by these replaced coordinates, not by where the accidents "
                   f"really happened.")
    else:
        st.caption(f"⚠️ Heat layer: **{fmt(excl)} accidents ({excl / len(a) * 100:.1f}%)** without a usable own coordinate "
                   f"are **not drawn** (step 8). Use the switch to draw them at their municipality centre. They are always "
                   f"counted in the dots, which are grouped by municipality code.")
    m1, m2 = st.columns([3, 2])
    with m1:
        show_fig(heat_map(agg, level, geo, heat_mode), key="map", explain="d_map", title="Heat map")
        src("dots: pipeline.aggregate_by_level (centres: unit_centers.csv from pipeline.build_units) · "
            "heat layer: LAT/LON from step 7; switch off = step 8 (own coordinates only), on = also step-6 centres")
    min_n = 1
    with m2:
        if level == "Municipalities":
            min_n = st.slider("Only municipalities with at least N accidents (small numbers = noisy ratios)", 1, 500, 30,
                              key="min_n")
        if level == "BE":
            r = agg.iloc[0]
            st.markdown(f"**Belgium** · density **{r.POP_DENSITY:,.0f} inh./km²** · **{fmt(r.ACCIDENTS)}** injury "
                        f"accidents · Severity Ratio **{r.SEVERITY_RATIO:.1f}%**")
            st.info("At BE level there is only one dot, so no relationship can be seen. Use regions, provinces or "
                    "municipalities, or the density classes below.")
        else:
            fig, res = relation_scatter(agg, level, min_n)
            show_fig(fig, key="scatter", explain="d_scatter", title="Population density vs Severity Ratio")
            if res:
                st.caption(f"{res['n']} units · Spearman ρ = **{res['rho']:.2f}** (p = {res['p']:.2g}) · trend: "
                           f"**{res['slope']:+.1f} percentage points** of Severity Ratio per 10× more density.")
            src("pipeline.aggregate_by_level · ρ: scipy.stats.spearmanr · trend: numpy.polyfit (weights √accidents)")
    with st.expander(f"Table – {level}"):
        cols = ["NAME", "POPULATION", "AREA_KM2", "POP_DENSITY", "ACCIDENTS", "ACCIDENTS_PER_1000_INH_YEAR", "SEVERE",
                "DEATHS", "SEVERITY_RATIO", "LAT", "LON"]
        table(agg[cols].sort_values("POP_DENSITY", ascending=False).round(2), hide_index=True, width="stretch")
        src("pipeline.aggregate_by_level")

    st.markdown("---")
    st.markdown("### Why? What changes as density increases")
    w1, w2 = st.columns(2)
    with w1:
        fig = px.bar(prof, x="DENSITY_CLASS", y="Severity Ratio (%)", text="Severity Ratio (%)", color="Severity Ratio (%)",
                     color_continuous_scale=SEV_COLORS, range_color=SEV_RANGE, hover_data={"accidents": ":,"},
                     labels={"DENSITY_CLASS": "Population density of the municipality (inh./km²)"},
                     title="1 · Severity Ratio by density class")
        fig.update_traces(texttemplate="%{text:.1f}%")
        fig.update_layout(height=380, coloraxis_showscale=False, margin=dict(l=0, r=0, t=40, b=0))
        show_fig(fig, explain="d_ch1")
    with w2:
        long = prof.melt(id_vars="DENSITY_CLASS", value_vars=["outside built-up area (%)", "single vehicle / obstacle (%)",
                                                               "night, no street lighting (%)"],
                         var_name="factor", value_name="% of accidents")
        fig = px.line(long, x="DENSITY_CLASS", y="% of accidents", color="factor", markers=True,
                      labels={"DENSITY_CLASS": "Population density (inh./km²)", "factor": ""},
                      title="2 · Where and how accidents happen, by density class",
                      color_discrete_sequence=["#d73027", "#f46d43", "#313695"])
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0), legend=dict(orientation="h", y=-0.25))
        show_fig(fig, explain="d_ch2")
    src("charts 1–2: pipeline.density_class_profile (classes: pipeline.DENSITY_BINS; rules: tab Pipeline & method → Category rules)")
    w3, w4 = st.columns(2)
    known_bu = P.add_density_class(a[a.CD_BUILD_UP_AREA.isin([1, 2])])
    with w3:
        bu = (known_bu.assign(SEV=P.is_severe(known_bu.CD_CLASS_ACCIDENTS).values)
              .groupby(["DENSITY_CLASS", "TX_BUILD_UP_AREA_NL"], observed=True).SEV.mean().mul(100)
              .reset_index(name="Severity Ratio (%)"))
        fig = px.bar(bu, x="DENSITY_CLASS", y="Severity Ratio (%)", color="TX_BUILD_UP_AREA_NL", barmode="group",
                     labels={"DENSITY_CLASS": "Population density (inh./km²)", "TX_BUILD_UP_AREA_NL": ""},
                     color_discrete_map={"binnen bebouwde kom": "#4575b4", "buiten bebouwde kom": "#d73027"},
                     title="3 · Severity Ratio inside vs outside built-up areas")
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0), legend=dict(orientation="h", y=-0.25))
        show_fig(fig, explain="d_ch3")
        st.caption(f"{fmt(len(a) - len(known_bu))} accidents with unknown built-up area (code 9) are left out of this chart.")
    with w4:
        sit = (a.assign(situation=P.collision_group(a), SEV=P.is_severe(a.CD_CLASS_ACCIDENTS).values)
               .groupby("situation").agg(n=("SEV", "size"), SR=("SEV", "mean")).reset_index())
        sit["SR"] *= 100
        fig = px.bar(sit.sort_values("SR"), x="SR", y="situation", orientation="h", text="SR", color="SR",
                     color_continuous_scale=SEV_COLORS, range_color=SEV_RANGE, hover_data={"n": ":,"},
                     labels={"SR": "Severity Ratio (%)", "situation": ""},
                     title="4 · Severity Ratio by type of collision (all of Belgium)")
        fig.update_traces(texttemplate="%{text:.1f}%")
        fig.update_layout(height=380, coloraxis_showscale=False, margin=dict(l=0, r=0, t=40, b=0))
        show_fig(fig, explain="d_ch4")
    src("chart 3: built-up area code 1/2 only · chart 4: pipeline.collision_group")

    out_lo, out_hi = prof["outside built-up area (%)"].iloc[[0, -1]]
    sv_lo, sv_hi = prof["single vehicle / obstacle (%)"].iloc[[0, -1]]
    bu_p = bu.pivot(index="DENSITY_CLASS", columns="TX_BUILD_UP_AREA_NL", values="Severity Ratio (%)")
    st.markdown(f"""
**Explanation**

1. **Speed (the main reason).** In the least dense municipalities, **{out_lo:.0f}%** of injury accidents happen *outside*
   built-up areas, on 70–90 km/h roads. In the densest municipalities this is only **{out_hi:.0f}%** (chart 2). Crash energy
   rises with the square of speed, so an accident outside a built-up area is far more often serious or fatal (chart 3, red bars).
2. **Type of crash.** Low-density areas have more single-vehicle crashes and crashes into trees, posts or ditches
   (**{sv_lo:.0f}%** vs **{sv_hi:.0f}%**). These are among the most severe types (chart 4). In cities, most crashes are low-speed
   rear-end, side and flank collisions.
3. **Even inside built-up areas, density helps.** Inside built-up areas the ratio still drops from
   **{bu_p.iloc[0].get('binnen bebouwde kom', np.nan):.1f}%** to **{bu_p.iloc[-1].get('binnen bebouwde kom', np.nan):.1f}%**
   (chart 3, blue bars): congestion, 30 km/h zones, traffic lights, better street lighting, ambulances and trauma centres closer by.
4. **More minor accidents are recorded.** Cities have many more small injury accidents (the denominator) and police nearby
   to record them. This lowers the *ratio*, although the absolute number of severe accidents in cities is high. This is a
   hypothesis: the data cannot prove it.
""")
    with st.expander("Data behind the charts (by density class)"):
        table(prof.round(2), hide_index=True, width="stretch")

    rows_used([
        ("Selected years", len(acc), len(a), len(acc) - len(a), "Outside the year selection"),
        ("Dots, table, charts 1-2-4", len(a), len(a), 0, "All rows (grouped by municipality code)"),
        ("Grey heat layer", len(a), len(geo), excl,
         "Switch on: nothing left out (replaced coordinates drawn at the municipality centre)" if include_imputed
         else "No usable own coordinate (step 8); use the switch on the map to include them at the municipality centre"),
        ("Chart 3 (inside / outside built-up area)", len(a), len(known_bu), len(a) - len(known_bu), "Built-up area unknown (code 9)"),
        ("Scatter (municipalities, units)", len(mun), int((mun.ACCIDENTS >= min_n).sum()) if level == "Municipalities" else len(mun),
         int((mun.ACCIDENTS < min_n).sum()) if level == "Municipalities" else 0, f"Fewer than {min_n} accidents (slider)"),
    ])


# =================================================================== TAB 3: COVID
AREAS = {"Belgium": "België", "Flanders": "Vlaams Gewest", "Wallonia": "Waals Gewest", "Brussels": P.BRUSSELS}
PHASE_FILL = {"L1": "rgba(215,48,39,0.16)", "L2": "rgba(215,48,39,0.16)",
              "R1": "rgba(253,174,97,0.14)", "R2": "rgba(253,174,97,0.14)"}


def add_phase_shading(fig, phases):
    for _, r in phases.iterrows():
        if r.CODE in PHASE_FILL:
            fig.add_vrect(x0=pd.Timestamp(r.FIRST_MONTH + "-01") - pd.Timedelta(days=15),
                          x1=pd.Timestamp(r.LAST_MONTH + "-01") + pd.Timedelta(days=15),
                          fillcolor=PHASE_FILL[r.CODE], line_width=0, layer="below",
                          annotation_text=r.PHASE, annotation_position="top left", annotation_font_size=10)


def covid_tab():
    st.subheader(COVID_Q)
    st.caption("Sources: processed accident data (Statbel) · Google COVID-19 Community Mobility Reports (Belgium, "
               "2020–2022) · Oxford COVID-19 Government Response Tracker (OxCGRT). **Normal** = average of the same "
               "calendar month in 2017–2019.")
    assumptions_box(["casualties", "covid", "denominator", "categories"])
    mon, phases, acc = D.load_covid_monthly(), D.load_covid_phases(), D.load_covid_accidents()

    area_label = st.segmented_control("Area", list(AREAS), default="Belgium", key="covid_area") or "Belgium"
    area = AREAS[area_label]
    a = acc if area == "België" else acc[acc.TX_RGN_COLLISION_NL == area]
    m = mon[mon.AREA == area].sort_values("DATE")

    res = {}
    for ph in ["Lockdown 1", "Lockdown 2"]:
        cur, base, bn, bs = P.period_vs_baseline(a, ph)
        both = pd.concat([cur, base])
        p = stats.chi2_contingency(pd.crosstab(both.PHASE, both.SEVERE))[1]
        res[ph] = dict(n=len(cur), sev=int(cur.SEVERE.sum()), bn=bn, bs=bs, sr=cur.SEVERE.mean() * 100,
                       bsr=bs / bn * 100, p=p, base_rows=len(base))
    for col, ph in zip(st.columns(2), res):
        r, row = res[ph], phases.set_index("PHASE").loc[ph]
        with col:
            st.markdown(f"**{ph}** ({row.FIRST_MONTH} → {row.LAST_MONTH})")
            k = st.columns(3)
            k[0].metric("Injury accidents vs normal", fmt(r["n"]), f"{(r['n'] / r['bn'] - 1) * 100:+.0f}%", delta_color="inverse",
                        help=E("c_acc_vs_normal"))
            k[1].metric("Severe accidents vs normal", fmt(r["sev"]), f"{(r['sev'] / r['bs'] - 1) * 100:+.0f}%", delta_color="inverse",
                        help=E("c_sev_vs_normal"))
            k[2].metric("Severity Ratio", f"{r['sr']:.1f}%", f"{r['sr'] - r['bsr']:+.1f} pp vs {r['bsr']:.1f}%",
                        delta_color="inverse", help=E("c_sr_vs_normal"))
            st.caption(f"Chi-square test, Severity Ratio vs normal: p = {r['p']:.2g} "
                       f"({'significant' if r['p'] < 0.05 else 'not significant'} at 5%)")
    src("pipeline.period_vs_baseline (phase from pipeline.assign_phase; normal = same months 2017-2019 / 3) · "
        "p: scipy.stats.chi2_contingency")
    l1, l2 = res["Lockdown 1"], res["Lockdown 2"]
    l1_yes, l2_yes = l1["sr"] > l1["bsr"] and l1["p"] < 0.05, l2["sr"] > l2["bsr"] and l2["p"] < 0.05

    def fewer(r):
        ch = (r["n"] / r["bn"] - 1) * 100
        return f"{abs(ch):.0f}% {'fewer' if ch < 0 else 'more'}"

    (st.success if l1_yes else st.info)(
        f"**{'Yes' if l1_yes else 'No'} for the first lockdown, {'yes' if l2_yes else 'no'} for the second.** In "
        f"{area_label}, Lockdown 1 had {fewer(l1)} injury accidents than normal, and a Severity Ratio of **{l1['sr']:.1f}%** "
        f"(normal {l1['bsr']:.1f}%, p = {l1['p']:.2g}). Lockdown 2 had {fewer(l2)} accidents and a ratio of "
        f"**{l2['sr']:.1f}%** (normal {l2['bsr']:.1f}%, p = {l2['p']:.2g}).")
    dot("ⓘ How is this answer computed?", "c_answer")

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
        show_fig(fig, key="cv_n", explain="c_ts_n")
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
        show_fig(fig, key="cv_sr", explain="c_ts_sr")
    src("pipeline.covid_monthly → covid_monthly_2017-2024.csv (ACCIDENTS, SEVERE, SEVERITY_RATIO, BASE_*)")

    st.markdown("#### Measures and mobility")
    mm = m[(m.DATE >= "2020-02-01") & (m.DATE <= "2022-10-01")]
    t3, t4 = st.columns(2)
    with t3:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=mm.DATE, y=mm.STRINGENCY, name="Stringency index (0–100)", marker_color="#fdae61",
                             opacity=0.6), secondary_y=False)
        for c, lab, colr in [("MOB_WORKPLACES", "workplaces", "#313695"), ("MOB_TRANSIT_STATIONS", "transit", "#74add1"),
                             ("MOB_RESIDENTIAL", "residential", "#a50026")]:
            fig.add_trace(go.Scatter(x=mm.DATE, y=mm[c], name=f"mobility: {lab}", line=dict(color=colr)), secondary_y=True)
        fig.update_yaxes(title_text="Stringency", secondary_y=False, range=[0, 100])
        fig.update_yaxes(title_text="% change vs pre-COVID", secondary_y=True)
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=-0.15),
                          title="Strictness of measures (OxCGRT) and mobility (Google)")
        show_fig(fig, key="cv_mob", explain="c_mob")
        src("STRINGENCY: step C2 + pipeline.measures_monthly · MOB_*: step C1 pipeline.mobility_monthly")
    sc = mon[(mon.AREA != "België") & (mon.DATE >= "2020-03-01")].copy()
    sc_used = sc[sc.MOB_WORKPLACES.notna()].assign(region=lambda d: d.AREA.map({v: k for k, v in AREAS.items()}))
    with t4:
        y_sel = st.radio("Y axis", ["Accidents vs normal (%)", "Severity Ratio vs normal (pp)"], horizontal=True, key="cv_y")
        ycol = "ACCIDENTS_CHANGE_PCT" if y_sel.startswith("Accidents") else "SR_DIFF_PP"
        fig = px.scatter(sc_used, x="MOB_WORKPLACES", y=ycol, color="region", hover_data=["YEAR", "MONTH", "PHASE"],
                         color_discrete_map={"Flanders": "#4575b4", "Wallonia": "#f46d43", "Brussels": "#a50026"},
                         labels={"MOB_WORKPLACES": "Workplace mobility vs pre-COVID (%)", ycol: y_sel})
        rho, p = stats.spearmanr(sc_used.MOB_WORKPLACES, sc_used[ycol])
        fig.add_hline(y=0, line_color=GREY, line_dash="dot")
        fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=-0.2))
        show_fig(fig, key="cv_sc", explain="c_scatter", title="Mobility vs accidents / Severity Ratio")
        st.caption(f"Each dot = one region in one month with mobility data (Mar 2020 – Oct 2022). Spearman ρ = "
                   f"**{rho:.2f}** (p = {p:.2g}).")
        src("covid_monthly_2017-2024.csv · ρ: scipy.stats.spearmanr")

    st.markdown("---")
    st.markdown("### Why? What was different about lockdown accidents")
    ph = st.radio("Compare with normal (same months 2017–2019)", ["Lockdown 1", "Lockdown 2"], horizontal=True, key="cv_phase")
    cur, base, _, _ = P.period_vs_baseline(a, ph)
    w1, w2 = st.columns(2)
    with w1:
        prof = pd.DataFrame({"normal": P.mix_profile(base), ph: P.mix_profile(cur)}).reset_index(names="share of accidents")
        long = prof.melt(id_vars="share of accidents", var_name="period", value_name="%")
        fig = px.bar(long, y="share of accidents", x="%", color="period", barmode="group", orientation="h", text="%",
                     color_discrete_map={"normal": "#9ca3af", ph: "#d73027"},
                     title="1 · Which accidents happened (% of all injury accidents)")
        fig.update_traces(texttemplate="%{text:.0f}%")
        fig.update_layout(height=430, margin=dict(l=0, r=0, t=40, b=0), yaxis=dict(autorange="reversed", title=""),
                          legend=dict(orientation="h", y=-0.12))
        show_fig(fig, key="cv_mix", explain="c_mix")
        src("pipeline.mix_profile (rules: Category rules)")
    with w2:
        g = pd.concat([base.assign(period="normal"), cur.assign(period=ph)])
        g["group"] = P.road_user_group(g)
        s = g.groupby(["group", "period"]).agg(n=("SEVERE", "size"), SR=("SEVERE", "mean")).reset_index()
        s["SR"] *= 100
        fig = px.bar(s, y="group", x="SR", color="period", barmode="group", orientation="h", text="SR",
                     hover_data={"n": ":,"}, color_discrete_map={"normal": "#9ca3af", ph: "#d73027"},
                     labels={"SR": "Severity Ratio (%)", "group": ""}, title="2 · Severity Ratio within each type of accident")
        fig.update_traces(texttemplate="%{text:.1f}%")
        fig.update_layout(height=430, margin=dict(l=0, r=0, t=40, b=0), legend=dict(orientation="h", y=-0.12))
        show_fig(fig, key="cv_within", explain="c_within")
        src("pipeline.road_user_group (one group per accident, first matching rule)")

    dec = P.mix_decomposition(cur, base)
    w3, w4 = st.columns([1, 1.4])
    with w3:
        dd = pd.DataFrame({"": ["normal", f"expected from {ph} mix", f"observed in {ph}"],
                           "Severity Ratio (%)": [dec["base_sr"], dec["expected_sr"], dec["observed_sr"]]})
        fig = px.bar(dd, x="", y="Severity Ratio (%)", text="Severity Ratio (%)", color="",
                     color_discrete_sequence=["#9ca3af", "#fdae61", "#d73027"],
                     title="3 · Mix effect vs 'same accident, worse outcome'")
        fig.update_traces(texttemplate="%{text:.2f}%")
        fig.update_layout(height=360, margin=dict(l=0, r=0, t=40, b=0), showlegend=False)
        show_fig(fig, key="cv_dec", explain="c_dec")
        src("pipeline.mix_decomposition (cells: pipeline.MIX_CELLS)")
    with w4:
        st.markdown(f"""
**How to read chart 3.** *Expected* is the Severity Ratio {ph} would have had if each type of accident (built-up area ×
road type × collision type × cyclist yes/no) had been as severe as normal, so only the **mix** changed.

- Mix effect: **{dec['mix_effect_pp']:+.2f} pp** (from {dec['base_sr']:.2f}% to {dec['expected_sr']:.2f}%)
- Within effect: **{dec['within_effect_pp']:+.2f} pp** (positive = the same kind of accident had a worse outcome than normal)
- {dec['cells_without_baseline']} accidents fell in a type that did not occur in the normal months; they got the overall normal rate.

{"Most of the increase is a **within effect**: the same kinds of accidents ended worse." if dec['within_effect_pp'] > dec['mix_effect_pp'] and dec['observed_sr'] > dec['base_sr'] else "There is no clear within effect."}
""")

    cur1, base1, _, _ = P.period_vs_baseline(a, "Lockdown 1")
    pm = pd.DataFrame({"n": P.mix_profile(base1), "l": P.mix_profile(cur1)})
    st.markdown(f"""
**Explanation (Lockdown 1)**

1. **Less traffic, so fewer accidents.** Workplace and transit mobility fell by about half and stringency rose above 75
   (out of 100). Far fewer cars meant far fewer collisions, especially at rush hour and on motorways (motorway share
   {pm.n["on a motorway"]:.1f}% → {pm.l["on a motorway"]:.1f}%).
2. **Empty roads, higher speeds.** The Severity Ratio of the *same kind* of accident went up (chart 2 and the within effect
   in chart 3). This fits the higher speeds on empty roads that Belgian road-safety researchers (Vias institute) reported
   in spring 2020. The data has no speed measurements, so this is the most likely explanation, not a proof.
3. **A different mix of road users.** More cycling and walking for recreation: cyclist share {pm.n["cyclist involved"]:.0f}%
   → {pm.l["cyclist involved"]:.0f}%; single-vehicle crashes {pm.n["single vehicle / obstacle"]:.0f}% →
   {pm.l["single vehicle / obstacle"]:.0f}%. Unprotected road users and single-vehicle crashes are more often severe.
4. **Why not in Lockdown 2?** It was lighter for traffic (schools and most jobs continued, mobility dropped far less) and
   fell in the dark, wet season, when roads are not empty. So fewer accidents, but **no** rise in severity.
""")

    rows_used([
        (f"Area: {area_label}", len(acc), len(a), len(acc) - len(a), "Other regions" if area != "België" else "-"),
        ("Lockdown 1 accidents", len(a), res["Lockdown 1"]["n"], len(a) - res["Lockdown 1"]["n"], "Months outside Mar-May 2020"),
        ("Normal for Lockdown 1", len(a), res["Lockdown 1"]["base_rows"], len(a) - res["Lockdown 1"]["base_rows"],
         "Only Mar-May of 2017-2019"),
        ("Lockdown 2 accidents", len(a), res["Lockdown 2"]["n"], len(a) - res["Lockdown 2"]["n"], "Months outside Nov 2020-Apr 2021"),
        ("Normal for Lockdown 2", len(a), res["Lockdown 2"]["base_rows"], len(a) - res["Lockdown 2"]["base_rows"],
         "Only Nov-Apr of 2017-2019"),
        ("Mobility scatter (region-months)", len(sc), len(sc_used), len(sc) - len(sc_used),
         "No Google mobility data after 15/10/2022"),
    ])

    with st.expander("Data behind this tab: phases, processed and raw files"):
        d1, d2, d3, d4 = st.tabs(["Phases", "Processed: covid_monthly", "Raw: Google mobility", "Raw: OxCGRT (Belgium)"])
        with d1:
            table(phases, hide_index=True, width="stretch")
        with d2:
            table(mon, hide_index=True, width="stretch", height=350)
        with d3:
            raw_m = D.load_mobility_raw()
            st.caption(f"`Data/Raw Data/COVID Mobility/` · {fmt(len(raw_m))} rows · {raw_m.date.min()} → "
                       f"{raw_m.date.max()} · country, regions and provinces. No 'driving' category.")
            table(raw_m.filter(like="percent_change").isna().mean().mul(100).round(1).rename("% missing"),
                         width="stretch")
            table(raw_m.head(500), width="stretch", height=300)
        with d4:
            o = D.load_measures_bel()
            st.caption(f"Belgium (national) rows of OxCGRT_compact_national_v1.csv (step C2) · {fmt(len(o))} days.")
            table(o, width="stretch", height=300)


# =================================================================== LAYOUT
st.title("🚦 Road accidents in Belgium 2017–2024")
st.caption("Hover over a **?** next to a number, chart title or column header to see what it means, how it is "
           "calculated and in which pipeline step it is created.")
tab0, tab1, tab2, tab3 = st.tabs(["🔧 Pipeline & method", "📊 Data Explorer", "❓ Density vs severity", "🦠 COVID lockdowns"])
with tab0:
    pipeline_tab()
with tab1:
    s1, s2 = st.tabs(["1.1 Raw Data Explorer", "1.2 Processed Data Explorer"])
    with s1:
        raw_explorer()
    with s2:
        processed_explorer()
with tab2:
    density_tab()
with tab3:
    covid_tab()
