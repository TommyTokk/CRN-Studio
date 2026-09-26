"""Interactive species Shapley attribution across fixed perturbations."""

from __future__ import annotations

import hashlib

import libsbml
import plotly.graph_objects as go
import streamlit as st
from shapcrn.utils.utils import normalize_asinh

from logic import importance
from logic.experiments import list_perturbable_species
from logic.model import load_model
from ui.components import page_header, panel_heading

page_header(
    eyebrow="Species attribution across perturbations",
    title="Importance & Sensitivity Analysis",
    subtitle="Explore target-specific Shapley values and KO/KI effects.",
)

model = st.session_state.get("shapcrn_loaded_model")
source_bytes = st.session_state.get("shapcrn_model_bytes", b"")
if "shapcrn_model_library" in st.session_state and not source_bytes:
    model = None
fallback_bytes = (
    libsbml.writeSBMLToString(model.getSBMLDocument()).encode("utf-8")
    if model is not None
    else b""
)
signature = hashlib.sha256(source_bytes or fallback_bytes).hexdigest()
if st.session_state.get("importance_model_signature") != signature:
    for key in list(st.session_state):
        if str(key).startswith("importance_"):
            del st.session_state[key]
    st.session_state["importance_model_signature"] = signature

# Sidebar model changes do not rerun Overview, which owns the shared parsed model.
if source_bytes:
    try:
        if "importance_prepared_model" not in st.session_state:
            st.session_state["importance_prepared_model"] = load_model(source_bytes)
        model = st.session_state["importance_prepared_model"]
    except Exception as exc:  # noqa: BLE001 — surface loader failures in the page.
        model = None
        st.error(f"Unable to load the active model: {exc}")
# Uploaded source files may be JSON; serialize the prepared model as SBML.
model_bytes = (
    libsbml.writeSBMLToString(model.getSBMLDocument()).encode("utf-8")
    if model is not None
    else b""
)

species_ids = (
    [species.getId() for species in model.getListOfSpecies()]
    if model is not None
    else []
)
labels = {
    sid: f"{sid} — {model.getSpecies(sid).getName()}"
    if model.getSpecies(sid).getName()
    else sid
    for sid in species_ids
}
perturbable, rejected = (
    list_perturbable_species(model) if model is not None else ([], {})
)
if model is None:
    st.info("Load a model in Model Overview to configure an importance analysis.")

with st.container(border=True):
    panel_heading(
        "Perturbation Sweep",
        "Independent input perturbations and target-specific Shapley attribution",
    )
    left, right = st.columns(2)
    with left:
        st.session_state["importance_inputs"] = [
            sid
            for sid in st.session_state.get("importance_inputs", [])
            if sid in perturbable
        ]
        inputs = st.multiselect(
            "Species to perturb",
            perturbable,
            format_func=labels.get,
            key="importance_inputs",
            disabled=not perturbable,
        )
    eligible = [sid for sid in species_ids if sid not in inputs]
    with right:
        st.session_state["importance_targets"] = [
            sid
            for sid in st.session_state.get("importance_targets", [])
            if sid in eligible
        ]
        targets = st.multiselect(
            "Target species to observe",
            eligible,
            format_func=labels.get,
            key="importance_targets",
            disabled=not eligible,
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        variation = st.slider("Variation (±%)", 1, 100, 20, key="importance_variation")
    with c2:
        levels = st.select_slider(
            "Sweep levels",
            options=list(range(3, 22, 2)),
            value=9,
            key="importance_levels",
        )
    with c3:
        end_time = st.number_input(
            "End time",
            min_value=0.01,
            value=120.0,
            step=10.0,
            key="importance_end_time",
        )

    st.session_state["importance_players"] = [
        sid
        for sid in st.session_state.get("importance_players", eligible)
        if sid in eligible
    ]
    players = st.multiselect(
        "Species included in knock experiments",
        eligible,
        format_func=labels.get,
        key="importance_players",
        disabled=not eligible,
    )
    c1, c2 = st.columns(2)
    with c1:
        mode = st.radio(
            "Knock mode",
            ["KO", "KI"],
            horizontal=True,
            key="importance_operation",
        )
    with c2:
        payoff = st.selectbox(
            "Payoff",
            ["last", "max", "min"],
            key="importance_payoff",
            help="Final value, maximum, or minimum of each target trajectory.",
        )

    combinations = levels ** len(inputs) if inputs else 0
    if inputs:
        st.caption(
            f"Perturbation grid: {levels}^{len(inputs)} = {combinations:,} "
            "combinations (limit: 2,000). Each player requires its own KO/KI "
            "simulations in addition to the original model."
        )
    if combinations > 2000:
        st.error(
            "The Cartesian sweep exceeds 2,000 combinations. "
            "Reduce the input species or sweep levels."
        )
    if rejected:
        st.caption(
            "Unavailable because their initial value cannot be perturbed: "
            + ", ".join(rejected)
        )
    zero_inputs = [
        sid
        for sid in inputs
        if (
            model.getSpecies(sid).isSetInitialAmount()
            and model.getSpecies(sid).getInitialAmount() == 0
        )
        or (
            model.getSpecies(sid).isSetInitialConcentration()
            and model.getSpecies(sid).getInitialConcentration() == 0
        )
    ]
    if zero_inputs:
        st.warning(
            "These input species start at zero: "
            + ", ".join(zero_inputs)
            + ". ShapCRN uses its small absolute-value fallback for sweep values."
        )
    run = st.button(
        "Compute Shapley values",
        type="primary",
        key="importance_run",
        disabled=model is None
        or not inputs
        or not targets
        or not players
        or combinations > 2000,
    )

config = {
    "model_signature": signature,
    "input_species_ids": tuple(inputs),
    "target_species_ids": tuple(targets),
    "knock_species_ids": tuple(players),
    "variation_percentage": float(variation),
    "level_count": int(levels),
    "end_time": float(end_time),
    "operation": "knockout" if mode == "KO" else "knockin",
    "payoff": payoff,
}
if run:
    try:
        with st.spinner("Computing Shapley values across perturbations…"):
            result = importance.run_importance_analysis(
                model_bytes,
                **{
                    key: value
                    for key, value in config.items()
                    if key != "model_signature"
                },
            )
        st.session_state["importance_result"] = result
        st.session_state["importance_result_config"] = config
    except Exception as exc:  # noqa: BLE001 — preserve the last successful result.
        st.error(f"Importance analysis failed: {exc}")

result = st.session_state.get("importance_result")
if isinstance(result, importance.ImportanceAnalysisResult):
    stored = st.session_state["importance_result_config"]
    if stored != config:
        st.info(
            "Analysis settings have changed. The charts still show the previous run."
        )
    st.caption(
        f"Last run: {stored['operation']} · payoff {stored['payoff']} · "
        f"end time {stored['end_time']:g} · {result.combination_count:,} combinations · "
        "levels " + ", ".join(f"{value:+g}%" for value in result.variation_levels)
    )
    panel_heading(
        "Shapley Value Attribution",
        "Positive means original payoff exceeds KO/KI payoff; negative means the reverse.",
    )
    result_targets = list(result.shapley_values.columns)
    target_tabs = st.tabs([labels.get(sid, sid) for sid in result_targets])
    for tab, target in zip(target_tabs, result_targets, strict=True):
        with tab:
            scores = result.shapley_values[target].dropna()
            scores = scores.loc[scores.abs().sort_values(ascending=False).index]
            if scores.empty:
                st.info(
                    "No valid attribution values for this target; self-comparisons are unavailable."
                )
            else:
                figure = go.Figure(
                    go.Bar(
                        x=scores.tolist(),
                        y=[labels.get(sid, sid) for sid in scores.index],
                        orientation="h",
                        marker_color=[
                            "#C86B4A" if value >= 0 else "#6F8F79" for value in scores
                        ],
                        hovertemplate="%{y}<br>Shapley: %{x:.8g}<extra></extra>",
                    )
                )
                figure.update_layout(
                    title=f"Shapley — {labels.get(target, target)}",
                    xaxis_title="Shapley value (raw)",
                    yaxis={"autorange": "reversed"},
                    height=max(350, 28 * len(scores) + 120),
                )
                st.plotly_chart(
                    figure,
                    use_container_width=True,
                    key=f"importance_bar_{target}",
                    config={"displaylogo": False},
                )

    normalized, scale = normalize_asinh(result.shapley_values)
    for name, raw, colored in (
        ("Shapley", result.shapley_values, normalized),
        ("Variations", result.variations, result.variations),
    ):
        with st.container(border=True):
            panel_heading(
                f"{name} Heatmap",
                "Rows: KO/KI players · Columns: target species · Unavailable/self-comparisons are blank",
            )
            color_options = (
                {
                    "colorscale": [[0, "#6F8F79"], [0.5, "#F5F0E8"], [1, "#C86B4A"]],
                    "zmid": 0,
                }
                if name == "Shapley"
                else {"colorscale": [[0, "#F5F0E8"], [1, "#C86B4A"]], "zmin": 0}
            )
            figure = go.Figure(
                go.Heatmap(
                    z=colored.to_numpy().tolist(),
                    customdata=raw.to_numpy().tolist(),
                    x=[labels.get(sid, sid) for sid in raw.columns],
                    y=[labels.get(sid, sid) for sid in raw.index],
                    hoverongaps=False,
                    hovertemplate="Player: %{y}<br>Target: %{x}<br>Raw value: %{customdata:.8g}<extra></extra>",
                    colorbar={
                        "title": "asinh(Shapley / s)"
                        if name == "Shapley"
                        else "|log₂ ratio|"
                    },
                    **color_options,
                )
            )
            figure.update_layout(
                height=max(350, 28 * len(raw) + 140),
                yaxis={"autorange": "reversed"},
            )
            st.plotly_chart(
                figure,
                use_container_width=True,
                key=f"importance_heatmap_{name.lower()}",
                config={"displaylogo": False},
            )
            if name == "Shapley":
                st.caption(
                    f"Color: asinh(value / s), s = {scale:.6g}. Hover shows the original Shapley value."
                )
            else:
                st.caption(
                    "Median absolute log₂ ratio of final target values across perturbations, as returned by ShapCRN; this measures magnitude, not direction, independently of the Shapley payoff choice."
                )
