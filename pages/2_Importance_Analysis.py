"""Page 3 — Importance & Sensitivity Analysis UI skeleton."""

from __future__ import annotations

import streamlit as st

from ui.components import (
    ko_target_legend,
    page_header,
    panel_heading,
    placeholder,
    stat_card,
)


# Shared theme/sidebar/topbar are rendered once by app.py before this page runs.

page_header(
    eyebrow="Phase III · CRN sensitivity engine",
    title="Importance & Sensitivity Analysis",
    subtitle="Uncover key regulatory species, bottlenecks, and KO → target effects using Shapley-style attribution and sensitivity metrics.",
    status="Analysis ready",
)


# -----------------------------------------------------------------------------
# INSERT MODEL PREPARATION / SPECIES OPTIONS HERE
# -----------------------------------------------------------------------------
# from logic.model import load_model
# model = load_model(st.session_state["shapcrn_model_bytes"])
# species_options = sorted(...)
species_options: list[str] = []


config = st.container(border=True)
with config:
    panel_heading(
        "Analysis Configuration & Solver Engine",
        "Configure knock scope, objective target, and sampling density",
        "⚗",
    )
    c1, c2, c3, c4 = st.columns([1.35, 1.45, 0.9, 0.9])
    with c1:
        method = st.selectbox(
            "Attribution methodology", ["Shapley Value Network Attribution", "Custom"]
        )
    with c2:
        target = st.selectbox(
            "Target objective",
            ["INSERT TARGETS AFTER MODEL LOADING"],
            disabled=True,
        )
    with c3:
        operation = st.radio("Knock mode", ["KO", "KI"], horizontal=True)
    with c4:
        end_time = st.number_input("End time", min_value=1.0, value=120.0, step=10.0)

    st.markdown(
        "<div class='sidebar-kicker'>Knock experiment scope</div>",
        unsafe_allow_html=True,
    )
    scope_left, scope_right = st.columns([2.2, 1])
    with scope_left:
        knock_species = st.multiselect(
            "Species included in knock experiments",
            species_options,
            default=species_options,
            help="All species should be selected by default once species_options is populated.",
        )
    with scope_right:
        samples = st.number_input(
            "Monte Carlo samples", min_value=1, value=5000, step=100
        )

    run_analysis = st.button(
        "⚡ Compute Ranking",
        type="primary",
        disabled=True,  # Enable after wiring logic/importance.py.
    )

# -----------------------------------------------------------------------------
# INSERT IMPORTANCE ANALYSIS HERE
# -----------------------------------------------------------------------------
# if run_analysis:
#     from logic.importance import run_importance_analysis
#     result = run_importance_analysis(...)
#     st.session_state["importance_analysis"] = result


st.write("")
summary_cards = st.columns(3, gap="medium")
with summary_cards[0]:
    stat_card(
        "#1 regulatory species",
        "—",
        "INSERT most important KO/player here",
        "terra",
        "Max Shapley",
    )
with summary_cards[1]:
    stat_card(
        "Most sensitive parameter",
        "—",
        "INSERT Sobol / sensitivity leader here",
        "sage",
        "Sensitivity",
    )
with summary_cards[2]:
    stat_card(
        "Critical bottleneck",
        "—",
        "INSERT target / pathway bottleneck here",
        "amber",
        "Flux control",
    )


st.write("")
main_left, main_right = st.columns([2.25, 1], gap="large")
with main_left:
    shap_panel = st.container(border=True)
    with shap_panel:
        panel_heading(
            "Shapley Value Attribution Spectrum",
            "Signed contribution to the selected target",
        )
        ko_target_legend()
        # INSERT TARGET-SPECIFIC DIVERGING SHAPLEY BAR CHART HERE
        placeholder(
            "Shapley attribution chart",
            "INSERT HORIZONTAL DIVERGING BAR CHART HERE. Positive drivers use terracotta; negative/suppressor effects use sage.",
            min_height=410,
        )

with main_right:
    network_panel = st.container(border=True)
    with network_panel:
        panel_heading(
            "KO → Target Network Map", "Topology coloured by signed Shapley(KO, target)"
        )
        # ---------------------------------------------------------------------
        # INSERT KO -> TARGET NETWORK COLOURING HERE
        # ---------------------------------------------------------------------
        # from logic.importance import target_scores
        # scores = target_scores(result["shapley_matrix"], selected_target)
        # map signed values to the same diverging terracotta ↔ sage scale.
        placeholder(
            "Target network",
            "INSERT CYTOSCAPE NETWORK HERE. Highlight the selected target and colour every KO/player by its signed Shapley(KO, target) value.",
            min_height=410,
        )


st.write("")
sensitivity_panel = st.container(border=True)
with sensitivity_panel:
    panel_heading(
        "Logarithmic Sensitivity Matrix",
        "Target/parameter response coefficients and clustered structure",
    )
    # INSERT SENSITIVITY HEATMAP HERE
    placeholder(
        "Sensitivity matrix",
        "INSERT HEATMAP HERE. Use sage for negative values, linen around zero, and terracotta for positive values; keep labels monospace.",
        min_height=360,
    )


st.write("")
ranking_panel = st.container(border=True)
with ranking_panel:
    panel_heading(
        "Integrated Sensitivity & Centrality Ranking",
        "Composite ranking table across attribution, sensitivity, and topology",
    )
    search = st.text_input(
        "Search", placeholder="Search feature, species, or parameter"
    )
    # INSERT INTEGRATED RANKING DATAFRAME HERE
    placeholder(
        "Ranking table",
        "INSERT RANK / FEATURE / TYPE / SHAPLEY / SENSITIVITY / CENTRALITY / ROLE TABLE HERE.",
        min_height=330,
    )

st.caption("INSERT METHODOLOGY / VALIDATION FOOTER HERE")
