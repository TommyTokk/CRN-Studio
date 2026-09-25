"""Page 2 — Kinetics & Dynamic Simulation UI."""

from __future__ import annotations

import hashlib

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from shapcrn.utils.simulation import load_roadrunner_model

from logic import experiments as exp
from ui.components import page_header, panel_heading, placeholder

# -----------------------------------------------------------------------------
# Page header
# -----------------------------------------------------------------------------

page_header(
    eyebrow="Kinetics, numerical integration & convergence",
    title="Kinetics & Dynamic Simulation",
    subtitle=(
        "Time-dependent trajectories, adaptive steady-state simulation, "
        "and perturbation experiments."
    ),
    status="Simulation Engine Ready",
)

ODE_MODE = "Deterministic ODE"
STEADY_STATE_MODE = "Until steady state"


# -----------------------------------------------------------------------------
# Model state
# -----------------------------------------------------------------------------

model_loaded = "shapcrn_loaded_model" in st.session_state
loaded_model = st.session_state.get("shapcrn_loaded_model")


def _active_model_signature() -> str | None:
    """Return a stable signature used to reject stale experiment results."""
    model_bytes = st.session_state.get("shapcrn_model_bytes")
    if isinstance(model_bytes, (bytes, bytearray)) and model_bytes:
        return hashlib.sha1(bytes(model_bytes)).hexdigest()
    if loaded_model is None:
        return None
    return ":".join(
        [
            loaded_model.getId() or "model",
            str(loaded_model.getNumSpecies()),
            str(loaded_model.getNumReactions()),
            str(id(loaded_model)),
        ]
    )


def _model_entity_label(entity_id: str, entity_type: str) -> str:
    """Format an SBML entity as ``ID — Name`` when a name is available."""
    if loaded_model is None:
        return entity_id
    getter = (
        loaded_model.getSpecies
        if entity_type == "Species"
        else loaded_model.getReaction
    )
    entity = getter(entity_id)
    name = entity.getName().strip() if entity is not None and entity.getName() else ""
    return f"{entity_id} — {name}" if name else entity_id


def _format_percentage_change(value: float) -> str:
    """Format a percentage for Plotly hover text."""
    if pd.isna(value):
        return "N/D"
    return f"{value:+.2f}%".replace("-", "−").replace(".", ",")


def _species_id_from_selection(selection: object) -> str:
    """Return the SBML species ID represented by a RoadRunner selection."""
    selection_text = str(selection)
    if selection_text.startswith("[") and selection_text.endswith("]"):
        return selection_text[1:-1]
    return selection_text


def _simulation_display_frame(
    results: pd.DataFrame,
    colnames: list[str] | None,
) -> pd.DataFrame:
    """Apply RoadRunner columns and human-readable species labels for plotting."""
    display_frame = results.copy()
    if colnames is not None and len(colnames) == len(display_frame.columns):
        display_frame.columns = list(colnames)

    renamed_columns: dict[object, str] = {}
    for column in display_frame.columns[1:]:
        species_id = _species_id_from_selection(column)
        if loaded_model is not None and loaded_model.getSpecies(species_id) is not None:
            renamed_columns[column] = _model_entity_label(species_id, "Species")

    return display_frame.rename(columns=renamed_columns)


model_signature = _active_model_signature()

# Results must never survive a switch to another active SBML model.
if st.session_state.get("kinetics_experiment_model_signature") != model_signature:
    for state_key in (
        "simulation_results",
        "simulation_colnames",
        "simulation_config",
        "simulation_steady_state",
        "knock_results",
        "knock_config",
        "perturbation_sweep_result",
        "perturbation_sweep_config",
        "knock_entity_species",
        "knock_entity_reaction",
        "perturbation_species",
        "perturbation_input_species",
        "perturbation_target_species",
    ):
        st.session_state.pop(state_key, None)
    st.session_state["kinetics_experiment_model_signature"] = model_signature

# Remove the legacy value that previously fed the deleted steady-state panel.
st.session_state.pop("simulation_steady_state", None)


# -----------------------------------------------------------------------------
# Simulation session state
# -----------------------------------------------------------------------------

if "simulation_results" not in st.session_state:
    st.session_state["simulation_results"] = None

if "simulation_colnames" not in st.session_state:
    st.session_state["simulation_colnames"] = None

if "simulation_config" not in st.session_state:
    st.session_state["simulation_config"] = None

if "knock_results" not in st.session_state:
    st.session_state["knock_results"] = None

if "knock_config" not in st.session_state:
    st.session_state["knock_config"] = None

if "perturbation_sweep_result" not in st.session_state:
    st.session_state["perturbation_sweep_result"] = None

if "perturbation_sweep_config" not in st.session_state:
    st.session_state["perturbation_sweep_config"] = None


# -----------------------------------------------------------------------------
# Simulation controls
# -----------------------------------------------------------------------------

config = st.container(border=True)

with config:
    panel_heading(
        "Analysis Configuration & Simulation Mode",
        "Choose a fixed time course or simulate until convergence",
        "⚗",
    )

    c1, c2, c3, c4 = st.columns(4, gap="medium")

    with c1:
        simulation_mode = st.selectbox(
            "Simulation mode",
            [ODE_MODE, STEADY_STATE_MODE],
            key="simulation_mode",
        )

    with c2:
        end_time = st.slider(
            "Horizon / maximum time (s)",
            min_value=1,
            max_value=500,
            value=100,
            key="simulation_end_time",
        )

    with c3:
        rtol = st.number_input(
            "rtol",
            value=1e-6,
            format="%.1e",
            key="simulation_rtol",
        )

        atol = st.number_input(
            "atol",
            value=1e-9,
            format="%.1e",
            key="simulation_atol",
        )

    with c4:
        scan_enabled = st.toggle(
            "Parameter scan",
            value=False,
            key="simulation_scan_enabled",
        )

        scan_note = st.text_input(
            "Scan parameter",
            placeholder="e.g. k_PFK",
            key="simulation_scan_parameter",
        )

    run_simulation = st.button(
        "▶ Run Simulation",
        type="primary",
        disabled=not model_loaded,
        key="run_simulation_button",
    )


# -----------------------------------------------------------------------------
# Simulation execution
# -----------------------------------------------------------------------------

if model_loaded and run_simulation:
    try:
        rr_model = load_roadrunner_model(st.session_state["shapcrn_loaded_model"])

        if simulation_mode == STEADY_STATE_MODE:
            sim_res, steady_state_time, colnames = exp.simulate_with_steady_state(
                rr_model,
                start_time=0,
                max_end_time=end_time,
            )
        else:
            sim_res, steady_state_time, colnames = exp.simulate(
                rr_model,
                start_time=0,
                end_time=end_time,
            )

        res_df = pd.DataFrame(sim_res, columns=colnames)

        if not res_df.empty:
            st.session_state["simulation_results"] = res_df
            st.session_state["simulation_colnames"] = colnames

            st.session_state["simulation_config"] = {
                "mode": simulation_mode,
                "end_time": end_time,
                "steady_state_time": steady_state_time,
                "rtol": rtol,
                "atol": atol,
                "scan_enabled": scan_enabled,
                "scan_parameter": scan_note,
            }

        else:
            st.warning("The simulation completed but returned no trajectory data.")

    except Exception as exc:
        st.error(f"Simulation failed: {exc}")


# -----------------------------------------------------------------------------
# Retrieve persistent simulation results
# -----------------------------------------------------------------------------

res_df = st.session_state.get("simulation_results")
simulation_colnames = st.session_state.get("simulation_colnames")
simulation_config = st.session_state.get("simulation_config")


# -----------------------------------------------------------------------------
# Detect whether controls changed after the last simulation
# -----------------------------------------------------------------------------

simulation_settings_changed = False

if simulation_config is not None:
    stored_mode = simulation_config.get("mode", ODE_MODE)
    simulation_settings_changed = any(
        [
            stored_mode != simulation_mode,
            simulation_config.get("end_time") != end_time,
            simulation_config.get("rtol") != rtol,
            simulation_config.get("atol") != atol,
            simulation_config.get("scan_enabled") != scan_enabled,
            simulation_config.get("scan_parameter") != scan_note,
        ]
    )


# -----------------------------------------------------------------------------
# Trajectory panel
# -----------------------------------------------------------------------------

st.write("")

trajectory_panel = st.container(border=True)

with trajectory_panel:
    panel_heading(
        "Concentration vs. Time Dynamics",
        "Species state trajectories X(t) over the simulated manifold",
        "〽",
    )

    if (
        model_loaded
        and res_df is not None
        and isinstance(res_df, pd.DataFrame)
        and not res_df.empty
    ):
        if simulation_config is not None:
            stored_mode = simulation_config.get("mode", ODE_MODE)
            st.caption(
                "Last simulation: "
                f"{stored_mode} · "
                f"0–{simulation_config['end_time']} s"
            )

            if stored_mode == STEADY_STATE_MODE:
                steady_state_time = simulation_config.get("steady_state_time")
                if steady_state_time is not None:
                    st.success(
                        "Steady state reached at "
                        f"t = {float(steady_state_time):g} s."
                    )
                else:
                    st.warning(
                        "Steady state was not reached before the maximum time "
                        f"of {simulation_config['end_time']} s."
                    )

        if simulation_settings_changed:
            st.info(
                "Simulation settings have changed since the last run. "
                "The plot below still shows the previous simulation."
            )

        simulation_display_df = _simulation_display_frame(
            res_df,
            simulation_colnames,
        )
        fig = px.line(
            simulation_display_df,
            x=simulation_display_df.columns[0],
            y=simulation_display_df.columns[1:],
            labels={
                simulation_display_df.columns[0]: "Time (s)",
                "value": "Concentration (M)",
                "variable": "Species",
            },
            title="Species Concentration Trajectories",
        )

        fig.update_layout(
            xaxis_title="Time (s)",
            yaxis_title="Concentration (M)",
            legend_title="Species",
            hovermode="x unified",
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            theme="streamlit",
            config={
                "displayModeBar": True,
                "displaylogo": False,
            },
        )

    else:
        placeholder(
            "Simulation trajectory",
            "RUN A SIMULATION TO DISPLAY THE TIME-COURSE TRAJECTORY.",
            min_height=300,
        )


# -----------------------------------------------------------------------------
# Phase space panel
# -----------------------------------------------------------------------------

st.write("")

phase_panel = st.container(border=True)

with phase_panel:
    panel_heading(
        "Phase Space Trajectory",
        "Limit-cycle projection / attractor view",
    )

    placeholder(
        "Phase plane",
        "INSERT X-vs-Y TRAJECTORY / BIFURCATION VIEW HERE.",
        min_height=300,
    )


# -----------------------------------------------------------------------------
# Knock experiment
# -----------------------------------------------------------------------------

st.write("")

knock_panel = st.container(border=True)

with knock_panel:
    panel_heading(
        "Knock Experiment",
        "Knockout / knock-in followed by simulation of the modified model",
    )

    knock_operation_col, entity_type_col, entity_col, knock_time_col = st.columns(
        [1.0, 1.1, 1.5, 1.0]
    )

    with knock_operation_col:
        knock_operation = st.radio(
            "Operation",
            ["Knockout", "Knock-in"],
            horizontal=True,
            key="knock_operation",
        )

    with entity_type_col:
        knock_entity_type = st.radio(
            "Entity type",
            ["Species", "Reaction"],
            horizontal=True,
            key="knock_entity_type",
        )

    if loaded_model is not None:
        if knock_entity_type == "Species":
            knock_entity_options = [
                species.getId() for species in loaded_model.getListOfSpecies()
            ]
        else:
            knock_entity_options = [
                reaction.getId() for reaction in loaded_model.getListOfReactions()
            ]
    else:
        knock_entity_options = []

    with entity_col:
        selected_knock_entity = st.selectbox(
            "Entity",
            knock_entity_options,
            format_func=lambda entity_id: _model_entity_label(
                entity_id, knock_entity_type
            ),
            disabled=not knock_entity_options,
            key=f"knock_entity_{knock_entity_type.lower()}",
            placeholder="Load a model to list entities",
        )

    with knock_time_col:
        knock_end_time = st.number_input(
            "End time",
            min_value=0.01,
            value=120.0,
            step=10.0,
            key="knock_end_time",
        )

    run_knock = st.button(
        "Run knock experiment",
        type="primary",
        disabled=not model_loaded or selected_knock_entity is None,
        key="run_knock_button",
    )

    if run_knock and loaded_model is not None and selected_knock_entity is not None:
        try:
            knock_results = exp.run_knock_experiment(
                loaded_model,
                operation=knock_operation,
                entity_type=knock_entity_type,
                entity_id=selected_knock_entity,
                end_time=float(knock_end_time),
                rel_tol=float(rtol),
                abs_tol=float(atol),
            )
            st.session_state["knock_results"] = knock_results
            st.session_state["knock_config"] = {
                "model_signature": model_signature,
                "operation": knock_operation,
                "entity_type": knock_entity_type,
                "entity_id": selected_knock_entity,
                "end_time": float(knock_end_time),
                "rtol": float(rtol),
                "atol": float(atol),
            }
        except Exception as exc:
            st.error(f"Knock experiment failed: {exc}")

    knock_results = st.session_state.get("knock_results")
    knock_config = st.session_state.get("knock_config")
    current_knock_config = {
        "model_signature": model_signature,
        "operation": knock_operation,
        "entity_type": knock_entity_type,
        "entity_id": selected_knock_entity,
        "end_time": float(knock_end_time),
        "rtol": float(rtol),
        "atol": float(atol),
    }

    if isinstance(knock_results, pd.DataFrame) and not knock_results.empty:
        if knock_config != current_knock_config:
            st.info(
                "Knock settings have changed. The chart still shows the previous run."
            )

        st.caption(
            f"Last run: {knock_config['operation']} · "
            f"{knock_config['entity_type']} {knock_config['entity_id']} · "
            f"0–{knock_config['end_time']:g} s"
        )
        knock_fig = px.line(
            knock_results,
            x=knock_results.columns[0],
            y=knock_results.columns[1:],
            labels={
                knock_results.columns[0]: "Time (s)",
                "value": "Concentration / amount (SBML units)",
                "variable": "Species",
            },
            title="Post-knock Species Trajectories",
        )
        knock_fig.update_layout(
            xaxis_title="Time (s)",
            yaxis_title="Concentration / amount (SBML units)",
            legend_title="Species",
            hovermode="x unified",
        )
        st.plotly_chart(
            knock_fig,
            use_container_width=True,
            theme="streamlit",
            config={"displayModeBar": True, "displaylogo": False},
        )
    else:
        placeholder(
            "Post-knock trajectories",
            "SELECT AN ENTITY AND RUN A KNOCK EXPERIMENT.",
            min_height=250,
        )


# -----------------------------------------------------------------------------
# Perturbation sweep
# -----------------------------------------------------------------------------

st.write("")

perturbation_panel = st.container(border=True)

with perturbation_panel:
    panel_heading(
        "Perturbation Sweep",
        "Independent input perturbations and target-specific response envelopes",
    )

    perturbable_species: list[str] = []
    rejected_species: dict[str, str] = {}
    all_species: list[str] = []
    if loaded_model is not None:
        perturbable_species, rejected_species = exp.list_perturbable_species(
            loaded_model
        )
        all_species = [species.getId() for species in loaded_model.getListOfSpecies()]

    input_species_col, target_species_col = st.columns(2, gap="medium")

    with input_species_col:
        selected_input_species = st.multiselect(
            "Species to perturb",
            perturbable_species,
            format_func=lambda species_id: _model_entity_label(species_id, "Species"),
            disabled=not perturbable_species,
            key="perturbation_input_species",
            placeholder="Select one or more input species",
        )

    observable_species = [
        species_id
        for species_id in all_species
        if species_id not in selected_input_species
    ]
    previous_target_species = st.session_state.get(
        "perturbation_target_species",
        [],
    )
    valid_target_species = [
        species_id
        for species_id in previous_target_species
        if species_id in observable_species
    ]
    if valid_target_species != previous_target_species:
        st.session_state["perturbation_target_species"] = valid_target_species

    with target_species_col:
        selected_target_species = st.multiselect(
            "Target species to observe",
            observable_species,
            format_func=lambda species_id: _model_entity_label(species_id, "Species"),
            disabled=not observable_species,
            key="perturbation_target_species",
            placeholder="Select one or more non-perturbed species",
        )

    variation_col, levels_col, sweep_time_col = st.columns(3)

    with variation_col:
        perturbation_variation = st.slider(
            "Variation (±%)",
            min_value=1,
            max_value=100,
            value=20,
            step=1,
            key="perturbation_variation",
        )

    with levels_col:
        perturbation_levels = st.select_slider(
            "Sweep levels",
            options=list(range(3, 22, 2)),
            value=9,
            key="perturbation_levels",
        )

    with sweep_time_col:
        perturbation_end_time = st.number_input(
            "End time",
            min_value=0.01,
            value=120.0,
            step=10.0,
            key="perturbation_sweep_end_time",
        )

    combination_count = (
        int(perturbation_levels) ** len(selected_input_species)
        if selected_input_species
        else 0
    )
    combinations_exceeded = combination_count > 2000
    if selected_input_species:
        st.caption(
            f"Planned simulations: {perturbation_levels}^{len(selected_input_species)} "
            f"= {combination_count:,} combinations (limit: 2,000)."
        )
    if combinations_exceeded:
        st.error(
            "The Cartesian sweep exceeds 2,000 combinations. "
            "Reduce the selected input species or the number of levels."
        )

    if rejected_species:
        rejected_ids = ", ".join(rejected_species)
        st.caption(
            "Unavailable because their initial value is controlled by an SBML rule "
            f"or cannot be resolved: {rejected_ids}."
        )

    zero_initial_inputs: list[str] = []
    if loaded_model is not None:
        for species_id in selected_input_species:
            species = loaded_model.getSpecies(species_id)
            if species is not None and (
                (species.isSetInitialAmount() and species.getInitialAmount() == 0)
                or (
                    species.isSetInitialConcentration()
                    and species.getInitialConcentration() == 0
                )
            ):
                zero_initial_inputs.append(species_id)
    if zero_initial_inputs:
        st.warning(
            "These input species start at zero, so percentage changes are undefined: "
            f"{', '.join(zero_initial_inputs)}. ShapCRN will use its small "
            "absolute-value fallback for their sweep values."
        )

    run_perturbation = st.button(
        "Run perturbation sweep",
        type="primary",
        disabled=(
            not model_loaded
            or not selected_input_species
            or not selected_target_species
            or combinations_exceeded
        ),
        key="run_perturbation_sweep_button",
    )

    perturbation_results_area = st.empty()

    with perturbation_results_area.container():
        sweep_error: Exception | None = None
        if (
            run_perturbation
            and loaded_model is not None
            and selected_input_species
            and selected_target_species
            and not combinations_exceeded
        ):
            try:
                with st.spinner(
                    f"Running {combination_count:,} perturbation simulations…"
                ):
                    sweep_result = exp.run_perturbation_sweep(
                        loaded_model,
                        input_species_ids=selected_input_species,
                        target_species_ids=selected_target_species,
                        variation_percentage=float(perturbation_variation),
                        level_count=int(perturbation_levels),
                        end_time=float(perturbation_end_time),
                        rel_tol=float(rtol),
                        abs_tol=float(atol),
                        max_combinations=2000,
                    )
                st.session_state["perturbation_sweep_result"] = sweep_result
                st.session_state["perturbation_sweep_config"] = {
                    "model_signature": model_signature,
                    "input_species_ids": tuple(selected_input_species),
                    "target_species_ids": tuple(selected_target_species),
                    "variation": float(perturbation_variation),
                    "level_count": int(perturbation_levels),
                    "end_time": float(perturbation_end_time),
                    "rtol": float(rtol),
                    "atol": float(atol),
                }
            except Exception as exc:
                sweep_error = exc

        if sweep_error is not None:
            st.error(f"Perturbation sweep failed: {sweep_error}")

        sweep_result = st.session_state.get("perturbation_sweep_result")
        sweep_config = st.session_state.get("perturbation_sweep_config")
        current_sweep_config = {
            "model_signature": model_signature,
            "input_species_ids": tuple(selected_input_species),
            "target_species_ids": tuple(selected_target_species),
            "variation": float(perturbation_variation),
            "level_count": int(perturbation_levels),
            "end_time": float(perturbation_end_time),
            "rtol": float(rtol),
            "atol": float(atol),
        }

        if isinstance(sweep_result, exp.PerturbationSweepResult):
            if sweep_config != current_sweep_config:
                st.info(
                    "Perturbation settings have changed. "
                    "The chart still shows the previous run."
                )

            levels_label = ", ".join(
                f"{level:+g}%" for level in sweep_result.variation_levels
            )
            inputs_label = ", ".join(sweep_config["input_species_ids"])
            st.caption(
                f"Last run: inputs {inputs_label} · "
                f"{sweep_result.combination_count:,} combinations · "
                f"levels {levels_label}"
            )

            target_tabs = st.tabs(
                [
                    _model_entity_label(species_id, "Species")
                    for species_id in sweep_config["target_species_ids"]
                ]
            )
            for target_tab, species_id in zip(
                target_tabs,
                sweep_config["target_species_ids"],
                strict=True,
            ):
                with target_tab:
                    envelope = sweep_result.envelopes[species_id]
                    band_x = (
                        envelope["time"].tolist() + envelope["time"].iloc[::-1].tolist()
                    )
                    band_y = (
                        envelope["maximum"].tolist()
                        + envelope["minimum"].iloc[::-1].tolist()
                    )
                    maximum_hover = [
                        [_format_percentage_change(value)]
                        for value in envelope["maximum_change_pct"]
                    ]
                    minimum_hover = [
                        [_format_percentage_change(value)]
                        for value in envelope["minimum_change_pct"]
                    ]
                    sweep_fig = go.Figure()
                    sweep_fig.add_trace(
                        go.Scatter(
                            x=band_x,
                            y=band_y,
                            mode="lines",
                            line={
                                "width": 1,
                                "color": "rgba(55, 139, 143, 0.85)",
                            },
                            fill="toself",
                            fillcolor="rgba(55, 139, 143, 0.32)",
                            hoverinfo="skip",
                            name="Perturbation range",
                        )
                    )
                    sweep_fig.add_trace(
                        go.Scatter(
                            x=envelope["time"],
                            y=envelope["maximum"],
                            customdata=maximum_hover,
                            mode="lines",
                            line={
                                "width": 1.25,
                                "color": "rgba(55, 139, 143, 0.9)",
                            },
                            name="Maximum",
                            showlegend=False,
                            hovertemplate=(
                                "Max: %{y:.5g}<br>"
                                "Δ baseline: %{customdata[0]}<extra></extra>"
                            ),
                        )
                    )
                    sweep_fig.add_trace(
                        go.Scatter(
                            x=envelope["time"],
                            y=envelope["minimum"],
                            customdata=minimum_hover,
                            mode="lines",
                            line={
                                "width": 1.25,
                                "color": "rgba(55, 139, 143, 0.9)",
                            },
                            name="Minimum",
                            showlegend=False,
                            hovertemplate=(
                                "Min: %{y:.5g}<br>"
                                "Δ baseline: %{customdata[0]}<extra></extra>"
                            ),
                        )
                    )
                    sweep_fig.add_trace(
                        go.Scatter(
                            x=envelope["time"],
                            y=envelope["baseline"],
                            mode="lines",
                            line={"color": "#B46E8D", "width": 2.5},
                            name="Baseline (0%)",
                            hovertemplate=(
                                "Baseline: %{y:.5g}<br>Δ baseline: 0,00%<extra></extra>"
                            ),
                        )
                    )
                    sweep_fig.update_layout(
                        title=f"Perturbation Envelope — {species_id}",
                        xaxis_title="Time (s)",
                        yaxis_title="Concentration / amount (SBML units)",
                        legend_title="Trajectory",
                        hovermode="x unified",
                    )
                    st.plotly_chart(
                        sweep_fig,
                        use_container_width=True,
                        theme="streamlit",
                        key=f"perturbation_chart_{species_id}",
                        config={"displayModeBar": True, "displaylogo": False},
                    )
        else:
            placeholder(
                "Target perturbation envelopes",
                "SELECT INPUT AND TARGET SPECIES, THEN RUN A PERTURBATION SWEEP.",
                min_height=250,
            )


# -----------------------------------------------------------------------------
# Artifacts / exports
# -----------------------------------------------------------------------------

st.write("")

artifact_panel = st.container(border=True)

with artifact_panel:
    panel_heading(
        "Simulation Artifacts & Raw Trajectories",
        "Exportable scientific outputs",
    )

    buttons = st.columns(3)

    buttons[0].button(
        "⇩ Download Trajectories (.csv)",
        disabled=True,
        use_container_width=True,
    )

    buttons[1].button(
        "▧ Export Report (.pdf)",
        disabled=True,
        use_container_width=True,
    )

    buttons[2].button(
        "<> Export Python Script",
        disabled=True,
        use_container_width=True,
    )
