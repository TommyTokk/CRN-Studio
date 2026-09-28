"""Interactive species Shapley attribution across fixed perturbations."""

from __future__ import annotations

import hashlib

import libsbml
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from shapcrn.utils.utils import normalize_asinh

from logic import importance
from logic.experiments import list_perturbable_species
from logic.model import load_model
from logic.network import build_importance_graph_annotations, build_network
from ui.components import page_header, panel_heading, stat_card
from ui.importance_graph import LAYOUT_OPTIONS, render_importance_graph
from ui.styles import apply_plotly_theme, current_theme, get_theme_palette

THEME_PALETTE = get_theme_palette()

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
    requested_compute_config = {
        "model_signature": signature,
        "input_species_ids": tuple(inputs),
        "variation_percentage": float(variation),
        "level_count": int(levels),
        "end_time": float(end_time),
        "operation": "knockout" if mode == "KO" else "knockin",
        "payoff": payoff,
    }
    cached_importance_config = st.session_state.get("importance_result_config")
    cached_importance_result = st.session_state.get("importance_result")
    importance_compute_matches = (
        isinstance(cached_importance_config, dict)
        and all(
            cached_importance_config.get(key) == value
            for key, value in requested_compute_config.items()
        )
    )
    importance_covered = (
        importance_compute_matches
        and isinstance(cached_importance_result, importance.ImportanceAnalysisResult)
        and set(players).issubset(cached_importance_config["knock_species_ids"])
    )
    run = st.button(
        "✓ Cached result active" if importance_covered else "Compute Shapley values",
        type="primary",
        key="importance_run",
        disabled=model is None
        or not inputs
        or not targets
        or not players
        or combinations > 2000
        or importance_covered,
    )

config = requested_compute_config | {
    "target_species_ids": tuple(eligible),
    "knock_species_ids": tuple(players),
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
        importance_compute_matches = True
        importance_covered = True
    except Exception as exc:  # noqa: BLE001 — preserve the last successful result.
        st.error(f"Importance analysis failed: {exc}")

result = st.session_state.get("importance_result")
if isinstance(result, importance.ImportanceAnalysisResult):
    stored = st.session_state["importance_result_config"]
    if not importance_covered:
        st.info(
            "Analysis settings have changed. The charts still show the previous run."
        )
    st.caption(
        f"Cached analysis: {stored['operation']} · payoff {stored['payoff']} · "
        f"end time {stored['end_time']:g} · {result.combination_count:,} combinations · "
        "levels " + ", ".join(f"{value:+g}%" for value in result.variation_levels)
    )
    displayed_targets = [
        species_id for species_id in targets if species_id in result.shapley_values.columns
    ]
    displayed_players = [
        species_id for species_id in players if species_id in result.shapley_values.index
    ]
    if not displayed_targets:
        displayed_targets = list(result.shapley_values.columns)
    if not displayed_players:
        displayed_players = list(result.shapley_values.index)
    result = importance.ImportanceAnalysisResult(
        shapley_values=result.shapley_values.loc[
            displayed_players,
            displayed_targets,
        ],
        variations=result.variations.loc[
            displayed_players,
            displayed_targets,
        ],
        variation_levels=result.variation_levels,
        combination_count=result.combination_count,
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
                max_magnitude = scores.abs().max()
                if max_magnitude == 0:
                    top_species = []
                    top_value = "No dominant effect"
                    top_help = "All valid Shapley values are zero."
                    direction_value = "No change"
                    direction_help = "The selected payoff is unchanged."
                    direction_accent = "slate"
                    variation_value = "N/A"
                    variation_help = "Not applicable without a dominant effect."
                else:
                    top_species = scores.index[
                        scores.abs() == max_magnitude
                    ].tolist()
                    if len(top_species) == 1:
                        top_value = labels.get(top_species[0], top_species[0])
                        top_help = (
                            "Highest absolute Shapley attribution for this target."
                        )
                    else:
                        top_value = f"Tie ({len(top_species)})"
                        top_help = " · ".join(
                            labels.get(sid, sid) for sid in top_species
                        )

                    top_scores = scores.loc[top_species]
                    has_positive = (top_scores > 0).any()
                    has_negative = (top_scores < 0).any()
                    knock_label = (
                        "KO" if stored["operation"] == "knockout" else "KI"
                    )
                    if has_positive and has_negative:
                        direction_value = "Mixed"
                        direction_help = (
                            "Tied species move the selected payoff in opposite "
                            "directions."
                        )
                        direction_accent = "amber"
                    elif has_positive:
                        direction_value = "Payoff ↓"
                        direction_help = (
                            f"{knock_label} produces a lower {stored['payoff']} "
                            "payoff than the original model."
                        )
                        direction_accent = "terra"
                    else:
                        direction_value = "Payoff ↑"
                        direction_help = (
                            f"{knock_label} produces a higher {stored['payoff']} "
                            "payoff than the original model."
                        )
                        direction_accent = "sage"

                    top_variations = result.variations.loc[
                        top_species, target
                    ].dropna()
                    if top_variations.empty:
                        variation_value = "—"
                        variation_help = (
                            "No variation value is available for the top species."
                        )
                    elif len(top_species) == 1:
                        variation_value = f"{top_variations.iloc[0]:.8g}"
                        variation_help = (
                            "Median |log₂ ratio| for the top species across "
                            "perturbations."
                        )
                    else:
                        variation_value = (
                            f"{top_variations.min():.8g}–"
                            f"{top_variations.max():.8g}"
                        )
                        variation_help = (
                            "Range of median |log₂ ratio| values for the tied "
                            "species."
                        )

                cards = st.columns(4, gap="medium")
                with cards[0]:
                    stat_card(
                        "Top knock species",
                        top_value,
                        top_help,
                        "terra",
                        "Ranking",
                    )
                with cards[1]:
                    stat_card(
                        "Importance magnitude",
                        f"{max_magnitude:.8g}",
                        "Largest absolute raw Shapley value for this target.",
                        "amber",
                        "|Shapley|",
                    )
                with cards[2]:
                    stat_card(
                        "Knock effect",
                        direction_value,
                        direction_help,
                        direction_accent,
                        "Direction",
                    )
                with cards[3]:
                    stat_card(
                        "Perturbation variation",
                        variation_value,
                        variation_help,
                        "slate",
                        "|log₂ ratio|",
                    )

                figure = go.Figure(
                    go.Bar(
                        x=scores.tolist(),
                        y=[labels.get(sid, sid) for sid in scores.index],
                        orientation="h",
                        marker={
                            "color": [
                                THEME_PALETTE["positive"]
                                if value >= 0
                                else THEME_PALETTE["negative"]
                                for value in scores
                            ],
                            "pattern": {
                                "shape": ["" if value >= 0 else "/" for value in scores]
                            },
                            "line": {
                                "color": THEME_PALETTE["border_strong"],
                                "width": 1,
                            },
                        },
                        hovertemplate="%{y}<br>Shapley: %{x:.8g}<extra></extra>",
                    )
                )
                figure.update_layout(
                    title=f"Shapley — {labels.get(target, target)}",
                    xaxis_title="Shapley value (raw)",
                    yaxis={"autorange": "reversed"},
                    height=max(350, 28 * len(scores) + 120),
                )
                apply_plotly_theme(figure)
                st.plotly_chart(
                    figure,
                    use_container_width=True,
                    theme=None,
                    key=f"importance_bar_{target}",
                    config={"displaylogo": False},
                )

    with st.container(border=True):
        panel_heading(
            "Target Influence Network",
            "Full topology with target-specific knock effects and shortest paths",
        )
        if st.session_state.get("importance_graph_target") not in result_targets:
            st.session_state["importance_graph_target"] = result_targets[0]
        if st.session_state.get("importance_graph_layout") not in LAYOUT_OPTIONS:
            st.session_state["importance_graph_layout"] = "Hierarchical"

        graph_controls = st.columns(2)
        with graph_controls[0]:
            graph_target = st.selectbox(
                "Network target",
                result_targets,
                format_func=labels.get,
                key="importance_graph_target",
            )
        with graph_controls[1]:
            graph_layout = st.selectbox(
                "Network layout",
                LAYOUT_OPTIONS,
                key="importance_graph_layout",
            )

        st.markdown(
            f"""
            <div style="display:flex;flex-wrap:wrap;gap:.55rem 1rem;align-items:center;
                        padding:.6rem .7rem;border:1px solid var(--border);
                        border-radius:8px;background:var(--paper);font-size:.74rem;">
              <span><span style="color:{THEME_PALETTE['data_1']}">●</span> Target</span>
              <span><span style="color:{THEME_PALETTE['positive']}">●</span> Promoter</span>
              <span><span style="color:{THEME_PALETTE['negative']}">●</span> Inhibitor</span>
              <span><span style="color:{THEME_PALETTE['amber']}">●</span> Neutral (|Shapley| ≤ 1e-8)</span>
              <span><span style="color:{THEME_PALETTE['data_8']}">◌</span> N/A</span>
              <span><span style="color:{THEME_PALETTE['data_4']}">━━</span> Mixed path</span>
              <span><span style="color:{THEME_PALETTE['graph_edge']}">┄┄</span> Secondary path</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        try:
            network_graph = build_network(model)
            graph_scores = result.shapley_values[graph_target]
            annotations = build_importance_graph_annotations(
                network_graph,
                graph_target,
                graph_scores,
                stored["operation"],
            )
            selected_player = st.session_state.get(
                "importance_graph_selected_player"
            )
            if (
                st.session_state.get("importance_graph_focus_target")
                != graph_target
                or selected_player not in graph_scores.index
            ):
                selected_player = None
                st.session_state["importance_graph_selected_player"] = None
            st.session_state["importance_graph_focus_target"] = graph_target

            focused_annotations = None
            if selected_player is not None:
                focused_annotations = build_importance_graph_annotations(
                    network_graph,
                    graph_target,
                    {selected_player: graph_scores[selected_player]},
                    stored["operation"],
                )
            graph_key_token = hashlib.sha1(
                f"{graph_target}|{graph_layout}".encode("utf-8")
            ).hexdigest()[:10]
            graph_event = render_importance_graph(
                network_graph,
                annotations,
                graph_target,
                graph_scores,
                stored["operation"],
                graph_layout,
                THEME_PALETTE,
                (
                    f"importance_target_graph_{signature[:12]}_"
                    f"{graph_key_token}_{current_theme()}"
                ),
                focused_annotations,
                selected_player,
            )

            event_timestamp = (
                graph_event.get("timestamp") if graph_event is not None else None
            )
            event_data = (
                graph_event.get("data", {}) if graph_event is not None else {}
            )
            tapped_player = event_data.get("target_id")
            if (
                graph_event is not None
                and graph_event.get("action") == "importance_knock_tap"
                and tapped_player in graph_scores.index
                and event_timestamp
                != st.session_state.get("importance_graph_event_timestamp")
            ):
                st.session_state["importance_graph_event_timestamp"] = event_timestamp
                st.session_state["importance_graph_selected_player"] = (
                    None if tapped_player == selected_player else tapped_player
                )
                st.rerun()

            if selected_player is not None and focused_annotations is not None:
                raw_value = float(graph_scores[selected_player])
                effect = focused_annotations.player_effects[selected_player]
                effect_label = {
                    "promoter": "Promoter",
                    "inhibitor": "Inhibitor",
                    "neutral": "Neutral",
                    "unavailable": "N/A",
                }[effect]
                shapley_label = (
                    f"{raw_value:.8g}" if np.isfinite(raw_value) else "N/A"
                )
                if selected_player in focused_annotations.secondary_players:
                    path_label = "undirected topological fallback"
                elif (
                    selected_player in focused_annotations.unreachable_players
                    or not focused_annotations.edge_effects
                ):
                    path_label = "no path to the target"
                else:
                    path_label = "directed shortest path"
                operation_label = (
                    "KO" if stored["operation"] == "knockout" else "KI"
                )
                st.info(
                    f"Selected knock: {labels.get(selected_player, selected_player)} · "
                    f"{effect_label} · {operation_label} · "
                    f"Shapley {shapley_label} · {path_label}."
                )

            if annotations.secondary_players:
                st.caption(
                    "Dashed paths ignore edge direction and indicate topological, "
                    "not necessarily causal, connections for: "
                    + ", ".join(
                        labels.get(player, player)
                        for player in annotations.secondary_players
                    )
                )
            if annotations.unreachable_players:
                st.warning(
                    "No topological path to this target was found for: "
                    + ", ".join(
                        labels.get(player, player)
                        for player in annotations.unreachable_players
                    )
                    + ". Their knock nodes remain classified by Shapley value."
                )
            st.caption(
                "Promoter/inhibitor describes the observed KO/KI payoff effect. "
                "Click a knocked species to focus all of its shortest paths."
            )
        except Exception as exc:  # noqa: BLE001 — keep numerical results usable.
            st.error(f"The target influence network could not be rendered: {exc}")

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
                    "colorscale": [
                        [0, THEME_PALETTE["negative"]],
                        [0.5, THEME_PALETTE["neutral"]],
                        [1, THEME_PALETTE["positive"]],
                    ],
                    "zmid": 0,
                }
                if name == "Shapley"
                else {
                    "colorscale": [
                        [0, THEME_PALETTE["neutral"]],
                        [1, THEME_PALETTE["positive"]],
                    ],
                    "zmin": 0,
                }
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
            apply_plotly_theme(figure)
            st.plotly_chart(
                figure,
                use_container_width=True,
                theme=None,
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
