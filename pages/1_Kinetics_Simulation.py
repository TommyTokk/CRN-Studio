"""Page 2 — Kinetics & Dynamic Simulation UI."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from shapcrn.utils.simulation import load_roadrunner_model

from logic import experiments as exp
from ui import phase_plot_3d as phase3d
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


def _trajectory_species_ids(
    results: pd.DataFrame,
    colnames: Sequence[object] | None,
) -> list[str]:
    """Return model species that are present in a stored trajectory."""
    selections: list[object] = (
        list(colnames)
        if colnames is not None and len(colnames) == len(results.columns)
        else list(results.columns)
    )
    available_ids = {
        _species_id_from_selection(selection) for selection in selections
    }
    if loaded_model is None:
        return []
    return [
        species.getId()
        for species in loaded_model.getListOfSpecies()
        if species.getId() in available_ids
    ]


def _phase_figure(
    phase_data: pd.DataFrame,
    phase_config: dict[str, object],
) -> go.Figure:
    """Build a 2D or 3D phase-trajectory figure for one simulation."""
    species_ids = list(phase_config["species_ids"])
    species_labels = list(phase_config["species_labels"])
    is_3d = len(species_ids) == 3
    source_label = str(phase_config["source_label"])
    is_standard = source_label == "Standard simulation"
    if is_3d:
        points = phase_data[species_ids].to_numpy(dtype=float)
        times = phase_data["time"].to_numpy(dtype=float)
        transform = phase3d.SceneTransform.from_point_sets([points])
        gradient = (
            phase3d.STANDARD_GRADIENT
            if is_standard
            else phase3d.KNOCK_GRADIENT
        )
        radius = (
            phase3d.STANDARD_TUBE_RADIUS
            if is_standard
            else phase3d.KNOCK_TUBE_RADIUS
        )
        figure = go.Figure()
        _add_3d_trajectory(
            figure,
            points,
            times,
            transform=transform,
            name="Trajectory",
            hover_label=source_label,
            species_labels=species_labels,
            gradient=gradient,
            radius=radius,
            max_rings=phase3d.SINGLE_MAX_RINGS,
            legendgroup="trajectory",
            showlegend=False,
        )
        if np.allclose(points[0], points[-1], rtol=1e-9, atol=1e-12):
            _add_3d_endpoint(
                figure,
                points[0],
                float(times[0]),
                transform=transform,
                radius=radius * 1.6,
                color=gradient[1],
                name="Stationary endpoint",
                hover_label=source_label,
                event="Start / End",
                species_labels=species_labels,
                legendgroup="trajectory",
            )
        else:
            for index, event, color in (
                (0, "Start", phase3d.START_ANCHOR_COLOR),
                (-1, "End", gradient[1]),
            ):
                _add_3d_endpoint(
                    figure,
                    points[index],
                    float(times[index]),
                    transform=transform,
                    radius=radius * 1.55,
                    color=color,
                    name=f"Trajectory {event.lower()}",
                    hover_label=source_label,
                    event=event,
                    species_labels=species_labels,
                    legendgroup="trajectory",
                )
        phase3d.apply_scientific_scene(
            figure,
            title=f"3D Phase Trajectory — {source_label}",
            axis_titles=species_labels,
            transform=transform,
            legend_mode="hidden",
        )
        return figure

    line = {
        "color": "#17324D" if is_standard else "#C86B4A",
        "width": 4 if is_standard else 3,
    }
    coordinates: dict[str, object] = {
        "x": phase_data[species_ids[0]],
        "y": phase_data[species_ids[1]],
    }
    endpoint_coordinates: dict[str, object] = {
        "x": phase_data[species_ids[0]].iloc[[0, len(phase_data) - 1]],
        "y": phase_data[species_ids[1]].iloc[[0, len(phase_data) - 1]],
    }
    axis_hover = (
        f"{species_labels[0]}: %{{x:.8g}}<br>"
        f"{species_labels[1]}: %{{y:.8g}}<br>"
    )
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            **coordinates,
            customdata=phase_data["time"],
            mode="lines",
            name="Trajectory",
            line=line,
            opacity=1.0,
            hovertemplate=(
                axis_hover
                + "Time: %{customdata:.8g} s<extra>Trajectory</extra>"
            ),
        )
    )
    figure.add_trace(
        go.Scatter(
            **endpoint_coordinates,
            customdata=phase_data["time"].iloc[[0, len(phase_data) - 1]],
            mode="markers+text",
            name="Endpoints",
            text=["Start", "End"],
            textposition="top center",
            marker={
                "size": 7,
                "color": ["#4E8B75", "#D39A34"],
                "line": {"color": "white", "width": 1},
            },
            hovertemplate=(
                axis_hover
                + "Time: %{customdata:.8g} s<extra>%{text}</extra>"
            ),
        )
    )
    figure.update_layout(
        title=f"{len(species_ids)}D Phase Trajectory — {source_label}",
        legend={"orientation": "h"},
        margin={"l": 0, "r": 0, "b": 0, "t": 55},
    )
    figure.update_layout(
        xaxis_title=species_labels[0],
        yaxis_title=species_labels[1],
    )
    return figure


def _perturbation_color(trajectory_id: str) -> str:
    """Return a stable, high-contrast color derived from a perturbation ID."""
    try:
        identifier = int(trajectory_id.removeprefix("P"))
    except ValueError:
        identifier = sum(ord(character) for character in trajectory_id)
    hue = (identifier * 137.508) % 360
    return f"hsl({hue:.1f}, 65%, 45%)"


def _mesh_hover_template(
    hover_label: str,
    species_labels: Sequence[str],
) -> str:
    """Return a hover template that reports the tube centerline values."""
    return (
        f"{hover_label}<br>"
        f"{species_labels[0]}: %{{customdata[0]:.8g}}<br>"
        f"{species_labels[1]}: %{{customdata[1]:.8g}}<br>"
        f"{species_labels[2]}: %{{customdata[2]:.8g}}<br>"
        "Time: %{customdata[3]:.8g} s<extra></extra>"
    )


def _endpoint_hover_template(
    hover_label: str,
    species_labels: Sequence[str],
) -> str:
    """Return a hover template for a volumetric trajectory anchor."""
    return (
        f"{hover_label} · %{{customdata[4]}}<br>"
        f"{species_labels[0]}: %{{customdata[0]:.8g}}<br>"
        f"{species_labels[1]}: %{{customdata[1]:.8g}}<br>"
        f"{species_labels[2]}: %{{customdata[2]:.8g}}<br>"
        "Time: %{customdata[3]:.8g} s<extra></extra>"
    )


def _add_3d_trajectory(
    figure: go.Figure,
    points: np.ndarray,
    times: np.ndarray,
    *,
    transform: phase3d.SceneTransform,
    name: str,
    hover_label: str,
    species_labels: Sequence[str],
    gradient: tuple[str, str],
    radius: float,
    max_rings: int,
    legendgroup: str,
    opacity: float = 1.0,
    showlegend: bool = True,
) -> None:
    """Append one shaded tube, if the trajectory has non-zero length."""
    tube = phase3d.tube_mesh_trace(
        points,
        times,
        transform=transform,
        name=name,
        gradient=gradient,
        radius=radius,
        hovertemplate=_mesh_hover_template(hover_label, species_labels),
        max_rings=max_rings,
        opacity=opacity,
        legendgroup=legendgroup,
        showlegend=showlegend,
    )
    if tube is not None:
        figure.add_trace(tube)


def _add_3d_endpoint(
    figure: go.Figure,
    point: Sequence[float],
    time: float,
    *,
    transform: phase3d.SceneTransform,
    radius: float,
    color: str,
    name: str,
    hover_label: str,
    event: str,
    species_labels: Sequence[str],
    legendgroup: str,
) -> None:
    """Append one shaded spherical anchor to a 3D phase figure."""
    figure.add_trace(
        phase3d.sphere_mesh_trace(
            point,
            transform=transform,
            radius=radius,
            color=color,
            name=name,
            time=time,
            event=event,
            hovertemplate=_endpoint_hover_template(hover_label, species_labels),
            legendgroup=legendgroup,
        )
    )


def _phase_comparison_figure_3d(
    comparison: dict[str, pd.DataFrame],
    species_ids: Sequence[str],
    species_labels: Sequence[str],
    metadata_by_id: dict[str, exp.PerturbationTrajectoryMetadata],
    selected_trajectory_ids: Sequence[str],
    *,
    standard_only: bool,
) -> go.Figure:
    """Build the volumetric Standard-versus-perturbations phase plot."""
    visible_ids = [] if standard_only else list(selected_trajectory_ids)
    standard = comparison["standard"]
    points_by_id = {
        "standard": standard[list(species_ids)].to_numpy(dtype=float),
        **{
            trajectory_id: comparison[trajectory_id][list(species_ids)].to_numpy(
                dtype=float
            )
            for trajectory_id in visible_ids
        },
    }
    transform = phase3d.SceneTransform.from_point_sets(points_by_id.values())
    figure = go.Figure()

    standard_points = points_by_id["standard"]
    standard_times = standard["time"].to_numpy(dtype=float)
    _add_3d_trajectory(
        figure,
        standard_points,
        standard_times,
        transform=transform,
        name="Standard",
        hover_label="Standard",
        species_labels=species_labels,
        gradient=phase3d.STANDARD_GRADIENT,
        radius=phase3d.STANDARD_TUBE_RADIUS,
        max_rings=phase3d.STANDARD_MAX_RINGS,
        legendgroup="standard",
    )

    perturbation_limit = phase3d.perturbation_ring_limit(len(visible_ids))
    for trajectory_id in visible_ids:
        frame = comparison[trajectory_id]
        metadata = metadata_by_id[trajectory_id]
        _add_3d_trajectory(
            figure,
            points_by_id[trajectory_id],
            frame["time"].to_numpy(dtype=float),
            transform=transform,
            name=metadata.label,
            hover_label=metadata.label,
            species_labels=species_labels,
            gradient=phase3d.perturbation_gradient(trajectory_id),
            radius=phase3d.PERTURBATION_TUBE_RADIUS,
            max_rings=perturbation_limit,
            legendgroup=trajectory_id,
            opacity=0.92,
        )

    all_start_points = [standard_points[0]] + [
        points_by_id[trajectory_id][0] for trajectory_id in visible_ids
    ]
    all_starts_common = len(all_start_points) > 1 and all(
        np.allclose(all_start_points[0], point, rtol=1e-9, atol=1e-12)
        for point in all_start_points[1:]
    )
    perturbation_starts_common = len(visible_ids) > 1 and all(
        np.allclose(
            points_by_id[visible_ids[0]][0],
            points_by_id[trajectory_id][0],
            rtol=1e-9,
            atol=1e-12,
        )
        for trajectory_id in visible_ids[1:]
    )

    if all_starts_common:
        _add_3d_endpoint(
            figure,
            all_start_points[0],
            float(standard_times[0]),
            transform=transform,
            radius=phase3d.STANDARD_TUBE_RADIUS * 1.65,
            color=phase3d.START_ANCHOR_COLOR,
            name="Shared origin",
            hover_label="All trajectories",
            event="Common Start",
            species_labels=species_labels,
            legendgroup="anchors",
        )
    else:
        _add_3d_endpoint(
            figure,
            standard_points[0],
            float(standard_times[0]),
            transform=transform,
            radius=phase3d.STANDARD_TUBE_RADIUS * 1.55,
            color=phase3d.START_ANCHOR_COLOR,
            name="Standard start",
            hover_label="Standard",
            event="Start",
            species_labels=species_labels,
            legendgroup="standard",
        )
        if perturbation_starts_common:
            first_id = visible_ids[0]
            first_frame = comparison[first_id]
            _add_3d_endpoint(
                figure,
                points_by_id[first_id][0],
                float(first_frame["time"].iloc[0]),
                transform=transform,
                radius=phase3d.PERTURBATION_TUBE_RADIUS * 1.65,
                color=phase3d.START_ANCHOR_COLOR,
                name="Perturbation origin",
                hover_label="Perturbations",
                event="Common Start",
                species_labels=species_labels,
                legendgroup="anchors",
            )

    _add_3d_endpoint(
        figure,
        standard_points[-1],
        float(standard_times[-1]),
        transform=transform,
        radius=phase3d.STANDARD_TUBE_RADIUS * 1.55,
        color=phase3d.STANDARD_GRADIENT[1],
        name="Standard end",
        hover_label="Standard",
        event="End",
        species_labels=species_labels,
        legendgroup="standard",
    )

    for trajectory_id in visible_ids:
        frame = comparison[trajectory_id]
        points = points_by_id[trajectory_id]
        metadata = metadata_by_id[trajectory_id]
        if not all_starts_common and not perturbation_starts_common:
            _add_3d_endpoint(
                figure,
                points[0],
                float(frame["time"].iloc[0]),
                transform=transform,
                radius=phase3d.PERTURBATION_TUBE_RADIUS * 1.5,
                color=phase3d.START_ANCHOR_COLOR,
                name=f"{trajectory_id} start",
                hover_label=metadata.label,
                event="Start",
                species_labels=species_labels,
                legendgroup=trajectory_id,
            )
        gradient = phase3d.perturbation_gradient(trajectory_id)
        _add_3d_endpoint(
            figure,
            points[-1],
            float(frame["time"].iloc[-1]),
            transform=transform,
            radius=phase3d.PERTURBATION_TUBE_RADIUS * 1.5,
            color=gradient[1],
            name=f"{trajectory_id} end",
            hover_label=metadata.label,
            event="End",
            species_labels=species_labels,
            legendgroup=trajectory_id,
        )

    phase3d.apply_scientific_scene(
        figure,
        title="Standard vs. Perturbation Phase Trajectories",
        axis_titles=species_labels,
        transform=transform,
        legend_mode="comparison",
    )
    return figure


def _phase_comparison_figure(
    comparison: dict[str, pd.DataFrame],
    species_ids: Sequence[str],
    species_labels: Sequence[str],
    metadata_by_id: dict[str, exp.PerturbationTrajectoryMetadata],
    selected_trajectory_ids: Sequence[str],
    *,
    standard_only: bool,
) -> go.Figure:
    """Build a 2D/3D Standard-versus-perturbations phase plot."""
    is_3d = len(species_ids) == 3
    if is_3d:
        return _phase_comparison_figure_3d(
            comparison,
            species_ids,
            species_labels,
            metadata_by_id,
            selected_trajectory_ids,
            standard_only=standard_only,
        )

    trace_class = go.Scatter
    figure = go.Figure()

    def coordinates(frame: pd.DataFrame, indices: Sequence[int] | None = None):
        selected_frame = frame if indices is None else frame.iloc[list(indices)]
        values: dict[str, object] = {
            "x": selected_frame[species_ids[0]],
            "y": selected_frame[species_ids[1]],
        }
        if is_3d:
            values["z"] = selected_frame[species_ids[2]]
        return values

    axis_hover = (
        f"{species_labels[0]}: %{{x:.8g}}<br>"
        f"{species_labels[1]}: %{{y:.8g}}<br>"
        + (f"{species_labels[2]}: %{{z:.8g}}<br>" if is_3d else "")
    )

    standard = comparison["standard"]
    figure.add_trace(
        trace_class(
            **coordinates(standard),
            customdata=standard["time"],
            mode="lines",
            name="Standard",
            line={"color": "#17324D", "width": 4},
            opacity=1.0,
            hovertemplate=(
                "Standard<br>"
                + axis_hover
                + "Time: %{customdata:.8g} s<extra></extra>"
            ),
        )
    )
    standard_endpoint_indices = [0, len(standard) - 1]
    figure.add_trace(
        trace_class(
            **coordinates(standard, standard_endpoint_indices),
            customdata=[
                [standard["time"].iloc[0], "Start"],
                [standard["time"].iloc[-1], "End"],
            ],
            mode="markers",
            name="Standard endpoints",
            showlegend=False,
            marker={
                "size": 7,
                "color": "#17324D",
                "symbol": ["circle", "diamond"],
                "line": {"color": "white", "width": 1},
            },
            hovertemplate=(
                "Standard · %{customdata[1]}<br>"
                + axis_hover
                + "Time: %{customdata[0]:.8g} s<extra></extra>"
            ),
        )
    )

    visible_perturbation_ids = (
        [] if standard_only else list(selected_trajectory_ids)
    )
    perturbation_frames = [
        comparison[trajectory_id]
        for trajectory_id in visible_perturbation_ids
    ]
    common_start = False
    if len(perturbation_frames) > 1:
        first_start = np.array(
            [perturbation_frames[0][species_id].iloc[0] for species_id in species_ids]
        )
        common_start = all(
            np.allclose(
                first_start,
                np.array([frame[species_id].iloc[0] for species_id in species_ids]),
                rtol=1e-9,
                atol=1e-12,
            )
            for frame in perturbation_frames[1:]
        )

    for trajectory_id in visible_perturbation_ids:
        frame = comparison[trajectory_id]
        metadata = metadata_by_id[trajectory_id]
        color = _perturbation_color(trajectory_id)
        figure.add_trace(
            trace_class(
                **coordinates(frame),
                customdata=frame["time"],
                mode="lines",
                name=metadata.label,
                line={"color": color, "width": 1.75},
                opacity=0.65,
                hovertemplate=(
                    f"{metadata.label}<br>"
                    + axis_hover
                    + "Time: %{customdata:.8g} s<extra></extra>"
                ),
            )
        )
        endpoint_indices = [len(frame) - 1] if common_start else [0, len(frame) - 1]
        endpoint_events = ["End"] if common_start else ["Start", "End"]
        figure.add_trace(
            trace_class(
                **coordinates(frame, endpoint_indices),
                customdata=[
                    [frame["time"].iloc[index], event]
                    for index, event in zip(
                        endpoint_indices,
                        endpoint_events,
                        strict=True,
                    )
                ],
                mode="markers",
                name=f"{trajectory_id} endpoints",
                showlegend=False,
                marker={
                    "size": 5,
                    "color": color,
                    "symbol": (
                        ["diamond"] if common_start else ["circle", "diamond"]
                    ),
                    "line": {"color": "white", "width": 0.75},
                },
                hovertemplate=(
                    f"{metadata.label} · %{{customdata[1]}}<br>"
                    + axis_hover
                    + "Time: %{customdata[0]:.8g} s<extra></extra>"
                ),
            )
        )

    if common_start:
        first_frame = perturbation_frames[0]
        figure.add_trace(
            trace_class(
                **coordinates(first_frame, [0]),
                customdata=[[first_frame["time"].iloc[0]]],
                mode="markers",
                name="Common perturbation start",
                showlegend=False,
                marker={
                    "size": 7,
                    "color": "#6B7280",
                    "symbol": "circle",
                    "line": {"color": "white", "width": 1},
                },
                hovertemplate=(
                    "Common perturbation Start<br>"
                    + axis_hover
                    + "Time: %{customdata[0]:.8g} s<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        title="Standard vs. Perturbation Phase Trajectories",
        legend={"orientation": "h"},
        margin={"l": 0, "r": 0, "b": 0, "t": 55},
    )
    if is_3d:
        figure.update_layout(
            scene={
                "xaxis_title": species_labels[0],
                "yaxis_title": species_labels[1],
                "zaxis_title": species_labels[2],
                "dragmode": "orbit",
            }
        )
    else:
        figure.update_layout(
            xaxis_title=species_labels[0],
            yaxis_title=species_labels[1],
        )
    return figure


def _render_phase_tab(
    *,
    source_key: str,
    source_label: str,
    results: pd.DataFrame | None,
    colnames: Sequence[object] | None,
    revision: int,
    source_signature: tuple[object, ...] = (),
    unavailable_message: str,
) -> None:
    """Render one independently persisted phase-plot source tab."""
    source_available = isinstance(results, pd.DataFrame) and not results.empty
    available_species = (
        _trajectory_species_ids(results, colnames)
        if source_available and results is not None
        else []
    )
    species_state_key = f"phase_plot_species_{source_key}"
    previous_species = st.session_state.get(species_state_key, [])
    valid_species = [
        species_id
        for species_id in previous_species
        if species_id in available_species
    ][:3]
    if valid_species != previous_species:
        st.session_state[species_state_key] = valid_species

    selected_species = st.multiselect(
        "Species (axis order: X, Y, Z)",
        available_species,
        format_func=lambda species_id: _model_entity_label(species_id, "Species"),
        max_selections=3,
        disabled=not source_available,
        key=species_state_key,
        placeholder="Select two or three species",
    )
    valid_selection = len(selected_species) in (2, 3)
    generate_plot = st.button(
        "Generate phase plot",
        type="primary",
        disabled=not source_available or not valid_selection,
        key=f"generate_phase_plot_{source_key}_button",
    )

    if not source_available:
        st.info(unavailable_message)
    elif not valid_selection:
        st.caption("Select exactly two or three species to enable the phase plot.")

    phase_data_by_source = st.session_state["phase_plot_data_by_source"]
    phase_config_by_source = st.session_state["phase_plot_config_by_source"]
    current_signature = (
        int(revision),
        tuple(selected_species),
        tuple(source_signature),
    )
    if generate_plot and results is not None:
        try:
            phase_data_by_source[source_key] = exp.downsample_phase_trajectory(
                exp.prepare_phase_trajectory(
                    results,
                    selected_species,
                    column_selections=colnames,
                ),
                max_points=exp.PHASE_PLOT_MAX_POINTS,
            )
            phase_config_by_source[source_key] = {
                "signature": current_signature,
                "source_label": source_label,
                "species_ids": tuple(selected_species),
                "species_labels": tuple(
                    _model_entity_label(species_id, "Species")
                    for species_id in selected_species
                ),
            }
        except Exception as exc:
            st.error(f"Phase plot generation failed: {exc}")

    stored_data = phase_data_by_source.get(source_key)
    stored_config = phase_config_by_source.get(source_key)
    if (
        isinstance(stored_data, pd.DataFrame)
        and not stored_data.empty
        and isinstance(stored_config, dict)
    ):
        if stored_config.get("signature") != current_signature:
            st.info(
                "Phase plot selections or source data have changed. The chart "
                "still shows the previously generated trajectory."
            )
        st.plotly_chart(
            _phase_figure(stored_data, stored_config),
            width="stretch",
            theme=(
                None
                if len(tuple(stored_config.get("species_ids", ()))) == 3
                else "streamlit"
            ),
            config={
                "displayModeBar": True,
                "displaylogo": False,
                "scrollZoom": True,
            },
            key=f"phase_plot_chart_{source_key}",
        )
    else:
        placeholder(
            "3D phase trajectory",
            "SELECT TWO OR THREE SPECIES, THEN GENERATE THE PLOT.",
            min_height=300,
        )


model_signature = _active_model_signature()

# Results must never survive a switch to another active SBML model.
if st.session_state.get("kinetics_experiment_model_signature") != model_signature:
    for state_key in (
        "simulation_results",
        "simulation_colnames",
        "simulation_config",
        "simulation_steady_state",
        "simulation_result_revision",
        "knock_results",
        "knock_config",
        "knock_result_revision",
        "phase_plot_data_by_source",
        "phase_plot_config_by_source",
        "phase_plot_species_simulation",
        "phase_plot_species_knock",
        "phase_plot_species_perturbation",
        "phase_perturbation_selector_revision",
        "phase_perturbation_selection_revision",
        "phase_perturbation_trajectory_ids",
        "phase_perturbation_standard_only",
        "phase_plot_data",
        "phase_plot_config",
        "phase_plot_source",
        "phase_plot_species",
        "perturbation_sweep_result",
        "perturbation_sweep_config",
        "perturbation_result_revision",
        "knock_entity_species",
        "knock_entity_reaction",
        "perturbation_species",
        "perturbation_input_species",
        "perturbation_target_species",
    ):
        st.session_state.pop(state_key, None)
    for state_key in tuple(st.session_state):
        if str(state_key).startswith("phase_perturbation_level_"):
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

if "simulation_result_revision" not in st.session_state:
    st.session_state["simulation_result_revision"] = 0

if "knock_results" not in st.session_state:
    st.session_state["knock_results"] = None

if "knock_config" not in st.session_state:
    st.session_state["knock_config"] = None

if "knock_result_revision" not in st.session_state:
    st.session_state["knock_result_revision"] = 0

if "phase_plot_data_by_source" not in st.session_state:
    st.session_state["phase_plot_data_by_source"] = {}

if "phase_plot_config_by_source" not in st.session_state:
    st.session_state["phase_plot_config_by_source"] = {}

if "perturbation_sweep_result" not in st.session_state:
    st.session_state["perturbation_sweep_result"] = None

if "perturbation_sweep_config" not in st.session_state:
    st.session_state["perturbation_sweep_config"] = None

if "perturbation_result_revision" not in st.session_state:
    st.session_state["perturbation_result_revision"] = 0


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
            st.session_state["simulation_result_revision"] += 1

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
            st.session_state["knock_result_revision"] += 1
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
    estimated_trajectory_bytes = exp.estimate_perturbation_trajectory_bytes(
        combination_count,
        len(all_species),
    )
    trajectory_memory_exceeded = (
        estimated_trajectory_bytes
        > exp.PERTURBATION_TRAJECTORY_MEMORY_LIMIT_BYTES
    )
    if selected_input_species:
        st.caption(
            f"Planned simulations: {perturbation_levels}^{len(selected_input_species)} "
            f"= {combination_count:,} combinations (limit: 2,000) · "
            f"full trajectories ≈ {estimated_trajectory_bytes / 1024**2:.1f} MiB "
            "(limit: 128 MiB)."
        )
    if combinations_exceeded:
        st.error(
            "The Cartesian sweep exceeds 2,000 combinations. "
            "Reduce the selected input species or the number of levels."
        )
    if trajectory_memory_exceeded:
        st.error(
            "Saving all species trajectories would exceed the 128 MiB session "
            "limit. Reduce the selected input species or the number of levels."
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
            or trajectory_memory_exceeded
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
            and not trajectory_memory_exceeded
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
                        max_trajectory_bytes=(
                            exp.PERTURBATION_TRAJECTORY_MEMORY_LIMIT_BYTES
                        ),
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
                st.session_state["perturbation_result_revision"] += 1
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
# Phase space panel
# -----------------------------------------------------------------------------

st.write("")

phase_panel = st.container(border=True)

with phase_panel:
    panel_heading(
        "Phase Space Trajectory",
        "Interactive 2D and 3D projections for standard, knock, and perturbation runs",
    )

    standard_phase_tab, knock_phase_tab, perturbation_phase_tab = st.tabs(
        ["Standard", "Knock", "Perturbation"]
    )

    with standard_phase_tab:
        _render_phase_tab(
            source_key="simulation",
            source_label="Standard simulation",
            results=res_df if isinstance(res_df, pd.DataFrame) else None,
            colnames=simulation_colnames,
            revision=st.session_state["simulation_result_revision"],
            unavailable_message=(
                "Run a standard simulation before generating this phase plot."
            ),
        )

    with knock_phase_tab:
        _render_phase_tab(
            source_key="knock",
            source_label="Knock experiment",
            results=(
                knock_results
                if isinstance(knock_results, pd.DataFrame)
                else None
            ),
            colnames=(
                list(knock_results.columns)
                if isinstance(knock_results, pd.DataFrame)
                else None
            ),
            revision=st.session_state["knock_result_revision"],
            unavailable_message=(
                "Run a knock experiment before generating this phase plot."
            ),
        )

    with perturbation_phase_tab:
        standard_available = isinstance(res_df, pd.DataFrame) and not res_df.empty
        sweep_available = isinstance(
            sweep_result,
            exp.PerturbationSweepResult,
        )
        comparison_available = standard_available and sweep_available
        perturbation_revision = st.session_state["perturbation_result_revision"]
        if (
            st.session_state.get("phase_perturbation_selection_revision")
            != perturbation_revision
        ):
            st.session_state["phase_perturbation_trajectory_ids"] = []
            st.session_state["phase_perturbation_selection_revision"] = (
                perturbation_revision
            )

        metadata_by_id = (
            sweep_result.trajectory_metadata if sweep_available else {}
        )
        selectable_trajectory_ids = (
            [
                metadata.trajectory_id
                for metadata in sweep_result.trajectory_metadata.values()
                if metadata.combination_index != sweep_result.baseline_index
            ]
            if sweep_available
            else []
        )
        common_species = (
            list(
                exp.phase_species_intersection(
                    res_df,
                    simulation_colnames,
                    sweep_result,
                )
            )
            if comparison_available
            else []
        )

        previous_trajectory_ids = st.session_state.get(
            "phase_perturbation_trajectory_ids",
            [],
        )
        valid_trajectory_ids = [
            trajectory_id
            for trajectory_id in previous_trajectory_ids
            if trajectory_id in selectable_trajectory_ids
        ]
        if valid_trajectory_ids != previous_trajectory_ids:
            st.session_state["phase_perturbation_trajectory_ids"] = (
                valid_trajectory_ids
            )

        previous_species = st.session_state.get(
            "phase_plot_species_perturbation",
            [],
        )
        valid_species = [
            species_id
            for species_id in previous_species
            if species_id in common_species
        ][:3]
        if valid_species != previous_species:
            st.session_state["phase_plot_species_perturbation"] = valid_species

        standard_only = st.checkbox(
            "Mostra solo simulazione Standard",
            value=False,
            disabled=not comparison_available,
            key="phase_perturbation_standard_only",
        )
        selected_trajectory_ids = st.multiselect(
            "Perturbation trajectories",
            selectable_trajectory_ids,
            format_func=lambda trajectory_id: metadata_by_id[trajectory_id].label,
            disabled=not comparison_available or standard_only,
            key="phase_perturbation_trajectory_ids",
            placeholder="Select one or more perturbation combinations",
        )
        selected_species = st.multiselect(
            "Species (axis order: X, Y, Z)",
            common_species,
            format_func=lambda species_id: _model_entity_label(species_id, "Species"),
            max_selections=3,
            disabled=not comparison_available,
            key="phase_plot_species_perturbation",
            placeholder="Select two or three species",
        )

        if not standard_available:
            st.info(
                "Run a Standard simulation before comparing perturbation trajectories."
            )
        elif not sweep_available:
            st.info(
                "Run a perturbation sweep before comparing trajectories."
            )
        elif len(selected_species) not in (2, 3):
            st.caption("Select exactly two or three species to display the phase plot.")

        visible_perturbation_count = (
            0 if standard_only else len(selected_trajectory_ids)
        )
        recommended_limit = 15 if len(selected_species) == 2 else 8
        if (
            len(selected_species) in (2, 3)
            and visible_perturbation_count > recommended_limit
        ):
            st.warning(
                f"You selected {visible_perturbation_count} perturbation trajectories. "
                f"For responsive {len(selected_species)}D rendering, no more than "
                f"{recommended_limit} are recommended."
            )

        if comparison_available and len(selected_species) in (2, 3):
            try:
                comparison = exp.prepare_phase_comparison(
                    res_df,
                    selected_species,
                    sweep_result,
                    (
                        []
                        if standard_only
                        else selected_trajectory_ids
                    ),
                    standard_column_selections=simulation_colnames,
                    max_points=exp.PHASE_PLOT_MAX_POINTS,
                )
                species_labels = [
                    _model_entity_label(species_id, "Species")
                    for species_id in selected_species
                ]
                st.plotly_chart(
                    _phase_comparison_figure(
                        comparison,
                        selected_species,
                        species_labels,
                        metadata_by_id,
                        selected_trajectory_ids,
                        standard_only=standard_only,
                    ),
                    width="stretch",
                    theme=None if len(selected_species) == 3 else "streamlit",
                    config={
                        "displayModeBar": True,
                        "displaylogo": False,
                        "scrollZoom": True,
                    },
                    key="phase_plot_chart_perturbation",
                )
            except Exception as exc:
                st.error(f"Perturbation phase plot failed: {exc}")
        else:
            placeholder(
                "Perturbation comparison",
                "RUN STANDARD AND PERTURBATION SIMULATIONS, THEN SELECT SPECIES.",
                min_height=300,
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
