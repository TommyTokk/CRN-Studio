"""Simulation, knock, and concentration-perturbation experiments."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product
from typing import Any

import numpy as np
import pandas as pd
from shapcrn import (
    knockin_reaction,
    knockin_species,
    knockout_reaction,
    knockout_species,
)
from shapcrn.utils import simulation as sim_ut
from shapcrn.utils.sbml import species as species_ut
from shapcrn.utils.sbml import utils as sbml_ut


PERTURBATION_TRAJECTORY_MEMORY_LIMIT_BYTES = 128 * 1024**2
PERTURBATION_OUTPUT_ROWS = 100
PHASE_PLOT_MAX_POINTS = 500


@dataclass(frozen=True)
class PerturbationTrajectoryMetadata:
    """Stable identity and input settings for one perturbation trajectory."""

    trajectory_id: str
    combination_index: int
    level_indices: tuple[int, ...]
    variations: tuple[tuple[str, float], ...]
    input_values: tuple[tuple[str, float], ...]
    label: str


@dataclass(frozen=True)
class PerturbationSweepResult:
    """Envelopes and full trajectories from a fixed-percentage sweep."""

    envelopes: dict[str, pd.DataFrame]
    variation_levels: tuple[float, ...]
    initial_values: dict[str, float]
    species_selections: dict[str, str]
    combination_count: int
    trajectories: tuple[np.ndarray, ...]
    trajectory_columns: tuple[str, ...]
    input_samples: dict[str, tuple[float, ...]]
    combination_level_indices: tuple[tuple[int, ...], ...]
    baseline_index: int
    trajectory_metadata: dict[str, PerturbationTrajectoryMetadata]


def estimate_perturbation_trajectory_bytes(
    combination_count: int,
    species_count: int,
    *,
    output_rows: int = PERTURBATION_OUTPUT_ROWS,
) -> int:
    """Estimate bytes required for full float64 perturbation trajectories."""
    if combination_count < 0:
        raise ValueError("Combination count must not be negative.")
    if species_count < 0:
        raise ValueError("Species count must not be negative.")
    if output_rows < 1:
        raise ValueError("Output rows must be at least one.")
    return int(combination_count) * int(output_rows) * (int(species_count) + 1) * 8


def perturbation_trajectory_for_levels(
    result: PerturbationSweepResult,
    level_indices: Sequence[int],
) -> pd.DataFrame:
    """Return the real sweep trajectory for one combination of level indices."""
    if not isinstance(result, PerturbationSweepResult):
        raise TypeError("A PerturbationSweepResult is required.")

    selected_indices_list: list[int] = []
    for index in level_indices:
        normalized_index = int(index)
        if normalized_index != index:
            raise ValueError("Perturbation level indices must be integers.")
        selected_indices_list.append(normalized_index)
    selected_indices = tuple(selected_indices_list)
    input_count = len(result.input_samples)
    if len(selected_indices) != input_count:
        raise ValueError(
            f"Expected {input_count} perturbation level indices, "
            f"received {len(selected_indices)}."
        )

    level_count = len(result.variation_levels)
    if any(index < 0 or index >= level_count for index in selected_indices):
        raise ValueError(
            f"Perturbation level indices must be between 0 and {level_count - 1}."
        )

    try:
        combination_index = result.combination_level_indices.index(selected_indices)
    except ValueError as exc:
        raise ValueError(
            "The selected perturbation level combination was not simulated."
        ) from exc

    trajectory = result.trajectories[combination_index]
    return pd.DataFrame(trajectory, columns=list(result.trajectory_columns))


def simulate(
    rr_model: Any,
    start_time: float = 0,
    end_time: float = 1000,
) -> tuple[Any, float | None, list[str]]:
    """Simulate a configured RoadRunner model."""
    return sim_ut.simulate(
        rr_model,
        start_time=start_time,
        end_time=end_time,
    )


def simulate_with_steady_state(
    rr_model: Any,
    start_time: float = 0,
    max_end_time: float = 1000,
) -> tuple[Any, float | None, list[str]]:
    """Simulate a RoadRunner model until steady state."""
    return sim_ut.simulate_with_steady_state(
        rr_model,
        start_time=start_time,
        max_end_time=max_end_time,
    )


def _as_trajectory_frame(values: Any, columns: list[str]) -> pd.DataFrame:
    """Normalize a RoadRunner result to a numeric DataFrame."""
    frame = pd.DataFrame(np.asarray(values), columns=list(columns))
    if frame.empty:
        raise ValueError("The simulation returned no trajectory data.")
    return frame


def _selection_id(selection: object) -> str:
    """Return the species ID represented by a RoadRunner selection."""
    selection_text = str(selection)
    if selection_text.startswith("[") and selection_text.endswith("]"):
        return selection_text[1:-1]
    return selection_text


def prepare_phase_trajectory(
    trajectory: pd.DataFrame,
    species_ids: Sequence[str],
    *,
    column_selections: Sequence[object] | None = None,
) -> pd.DataFrame:
    """Return time and two or three species columns for a phase plot.

    ``column_selections`` preserves the RoadRunner names associated with legacy
    DataFrames whose columns were replaced by integer labels. Species selections
    may use either the concentration form (``[S1]``) or the amount form (``S1``).
    The returned frame contains the original samples without interpolation.
    """
    if not isinstance(trajectory, pd.DataFrame) or trajectory.empty:
        raise ValueError("Phase plot data must be a non-empty DataFrame.")

    selected_species = [str(species_id) for species_id in species_ids]
    if len(selected_species) not in (2, 3):
        raise ValueError("Select exactly two or three species for the phase plot.")
    if len(set(selected_species)) != len(selected_species):
        raise ValueError("Phase plot species must not contain duplicates.")
    if any(not species_id for species_id in selected_species):
        raise ValueError("Phase plot species IDs must not be empty.")

    selections = (
        list(column_selections)
        if column_selections is not None
        else list(trajectory.columns)
    )
    if len(selections) != len(trajectory.columns):
        raise ValueError(
            "RoadRunner column selections must match the trajectory columns."
        )

    normalized_selections = [_selection_id(selection) for selection in selections]
    time_indices = [
        index
        for index, selection in enumerate(normalized_selections)
        if selection.lower() == "time"
    ]
    if len(time_indices) != 1:
        raise ValueError("Phase plot data must contain exactly one time column.")

    selected_indices: dict[str, int] = {}
    for species_id in selected_species:
        matches = [
            index
            for index, selection in enumerate(normalized_selections)
            if selection == species_id
        ]
        if not matches:
            raise ValueError(
                f"Phase plot data does not contain species {species_id!r}."
            )
        if len(matches) > 1:
            raise ValueError(
                f"Phase plot data contains multiple columns for species {species_id!r}."
            )
        selected_indices[species_id] = matches[0]

    phase_data: dict[str, pd.Series] = {}
    output_columns = [("time", time_indices[0])] + list(selected_indices.items())
    for output_name, column_index in output_columns:
        try:
            phase_data[output_name] = pd.to_numeric(
                trajectory.iloc[:, column_index],
                errors="raise",
            ).reset_index(drop=True)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Phase plot column {output_name!r} must contain numeric values."
            ) from exc

    return pd.DataFrame(phase_data)


def downsample_phase_trajectory(
    trajectory: pd.DataFrame,
    *,
    max_points: int = PHASE_PLOT_MAX_POINTS,
) -> pd.DataFrame:
    """Return at most ``max_points`` evenly spaced rows, including endpoints."""
    if not isinstance(trajectory, pd.DataFrame) or trajectory.empty:
        raise ValueError("Phase plot data must be a non-empty DataFrame.")
    if max_points < 2:
        raise ValueError("Phase plot maximum points must be at least two.")
    if len(trajectory) <= max_points:
        return trajectory.copy()

    sampled_indices = np.linspace(
        0,
        len(trajectory) - 1,
        num=max_points,
        dtype=int,
    )
    return trajectory.iloc[np.unique(sampled_indices)].reset_index(drop=True)


def phase_species_intersection(
    standard_trajectory: pd.DataFrame,
    standard_column_selections: Sequence[object] | None,
    sweep_result: PerturbationSweepResult,
) -> tuple[str, ...]:
    """Return species available in both the Standard and sweep trajectories."""
    if not isinstance(standard_trajectory, pd.DataFrame) or standard_trajectory.empty:
        return ()
    standard_selections = (
        list(standard_column_selections)
        if standard_column_selections is not None
        else list(standard_trajectory.columns)
    )
    if len(standard_selections) != len(standard_trajectory.columns):
        raise ValueError(
            "RoadRunner column selections must match the Standard trajectory columns."
        )

    sweep_species = {
        _selection_id(selection)
        for selection in sweep_result.trajectory_columns
        if _selection_id(selection).lower() != "time"
    }
    ordered_standard_species = [
        _selection_id(selection)
        for selection in standard_selections
        if _selection_id(selection).lower() != "time"
    ]
    return tuple(
        species_id
        for species_id in ordered_standard_species
        if species_id in sweep_species
    )


def perturbation_trajectories_for_ids(
    result: PerturbationSweepResult,
    trajectory_ids: Sequence[str],
) -> dict[str, pd.DataFrame]:
    """Return sweep trajectories keyed by their stable perturbation IDs."""
    if not isinstance(result, PerturbationSweepResult):
        raise TypeError("A PerturbationSweepResult is required.")

    selected_ids = [str(trajectory_id) for trajectory_id in trajectory_ids]
    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("Perturbation trajectory IDs must not contain duplicates.")

    metadata_by_id = result.trajectory_metadata
    unknown_ids = [
        trajectory_id
        for trajectory_id in selected_ids
        if trajectory_id not in metadata_by_id
    ]
    if unknown_ids:
        raise ValueError(
            "Unknown perturbation trajectory IDs: " + ", ".join(unknown_ids) + "."
        )

    selected_trajectories: dict[str, pd.DataFrame] = {}
    for trajectory_id in selected_ids:
        metadata = metadata_by_id[trajectory_id]
        if metadata.trajectory_id != trajectory_id:
            raise ValueError(
                f"Perturbation metadata key {trajectory_id!r} does not match "
                f"its trajectory ID {metadata.trajectory_id!r}."
            )
        if not 0 <= metadata.combination_index < len(result.trajectories):
            raise ValueError(
                f"Perturbation trajectory {trajectory_id!r} has an invalid "
                "combination index."
            )
        trajectory = np.asarray(result.trajectories[metadata.combination_index])
        if trajectory.ndim != 2 or trajectory.shape[1] != len(
            result.trajectory_columns
        ):
            raise ValueError(
                f"Perturbation trajectory {trajectory_id!r} does not match "
                "the stored RoadRunner columns."
            )
        selected_trajectories[trajectory_id] = pd.DataFrame(
            trajectory,
            columns=list(result.trajectory_columns),
            copy=False,
        )
    return selected_trajectories


def prepare_phase_comparison(
    standard_trajectory: pd.DataFrame,
    species_ids: Sequence[str],
    sweep_result: PerturbationSweepResult,
    trajectory_ids: Sequence[str],
    *,
    standard_column_selections: Sequence[object] | None = None,
    max_points: int = PHASE_PLOT_MAX_POINTS,
) -> dict[str, pd.DataFrame]:
    """Normalize and downsample Standard plus selected perturbation trajectories."""
    comparison = {
        "standard": downsample_phase_trajectory(
            prepare_phase_trajectory(
                standard_trajectory,
                species_ids,
                column_selections=standard_column_selections,
            ),
            max_points=max_points,
        )
    }
    for trajectory_id, trajectory in perturbation_trajectories_for_ids(
        sweep_result,
        trajectory_ids,
    ).items():
        comparison[trajectory_id] = downsample_phase_trajectory(
            prepare_phase_trajectory(
                trajectory,
                species_ids,
                column_selections=sweep_result.trajectory_columns,
            ),
            max_points=max_points,
        )
    return comparison


def _relative_percentage_change(
    values: np.ndarray,
    baseline: np.ndarray,
    *,
    abs_tol: float,
) -> np.ndarray:
    """Return pointwise percentage changes, masking unreliable baselines."""
    percentages = np.full(baseline.shape, np.nan, dtype=float)
    reliable_baseline = np.abs(baseline) > abs_tol
    np.divide(
        values - baseline,
        baseline,
        out=percentages,
        where=reliable_baseline,
    )
    percentages *= 100.0
    return percentages


def _all_species_selections(sbml_model: Any) -> list[str]:
    """Return time plus every species symbol, including fixed species."""
    return ["time"] + [
        species_ut.symbol_selection(species)
        for species in sbml_model.getListOfSpecies()
    ]


def run_knock_experiment(
    sbml_model: Any,
    *,
    operation: str,
    entity_type: str,
    entity_id: str,
    end_time: float = 120.0,
    output_rows: int = 100,
    rel_tol: float = 1e-6,
    abs_tol: float = 1e-9,
    integrator: str = "cvode",
) -> pd.DataFrame:
    """Apply a ShapCRN knock operation and simulate the modified clone.

    The public ShapCRN editing functions clone in-memory models by default, so
    the model held by Streamlit session state remains unchanged.
    """
    if end_time <= 0:
        raise ValueError("Experiment end time must be greater than zero.")
    if output_rows < 2:
        raise ValueError("At least two output rows are required.")

    normalized_operation = operation.strip().lower().replace("-", "")
    normalized_entity = entity_type.strip().lower()
    dispatch = {
        ("knockout", "species"): knockout_species,
        ("knockout", "reaction"): knockout_reaction,
        ("knockin", "species"): knockin_species,
        ("knockin", "reaction"): knockin_reaction,
    }

    try:
        modifier = dispatch[(normalized_operation, normalized_entity)]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported knock experiment: {operation!r} on {entity_type!r}."
        ) from exc

    modified_model = modifier(sbml_model, entity_id)
    rr_model = sim_ut.load_roadrunner_model(
        modified_model,
        rel_tol=rel_tol,
        abs_tol=abs_tol,
        integrator=integrator,
    )
    # RoadRunner's defaults omit boundary/constant species, which would hide the
    # knocked species itself after a species KO/KI.
    rr_model.timeCourseSelections = _all_species_selections(modified_model)
    values, _, columns = sim_ut.simulate(
        rr_model,
        start_time=0,
        end_time=end_time,
        output_rows=output_rows,
    )
    return _as_trajectory_frame(values, columns)


def list_perturbable_species(
    sbml_model: Any,
) -> tuple[list[str], dict[str, str]]:
    """Return species with a literal, resolvable initial symbol value.

    Assignment- or algebraic-rule-controlled initializations cannot safely be
    replaced by the RoadRunner perturbation helper and are reported separately.
    """
    valid: list[str] = []
    rejected: dict[str, str] = {}

    for species in sbml_model.getListOfSpecies():
        species_id = species.getId()
        try:
            species_ut.initial_symbol_value(sbml_model, species_id)
        except Exception as exc:  # ShapCRN exposes several domain error classes.
            rejected[species_id] = str(exc)
        else:
            valid.append(species_id)

    return valid, rejected


def run_perturbation_sweep(
    sbml_model: Any,
    *,
    input_species_ids: Sequence[str],
    target_species_ids: Sequence[str],
    variation_percentage: float = 20.0,
    level_count: int = 9,
    end_time: float = 120.0,
    rel_tol: float = 1e-6,
    abs_tol: float = 1e-9,
    integrator: str = "cvode",
    max_combinations: int = 2000,
    max_trajectory_bytes: int = PERTURBATION_TRAJECTORY_MEMORY_LIMIT_BYTES,
) -> PerturbationSweepResult:
    """Perturb inputs and return target envelopes plus every full trajectory."""
    if variation_percentage <= 0:
        raise ValueError("Perturbation amplitude must be greater than zero.")
    if level_count < 3 or level_count % 2 == 0:
        raise ValueError("Perturbation levels must be an odd number of at least three.")
    if end_time <= 0:
        raise ValueError("Experiment end time must be greater than zero.")
    if max_combinations < 1:
        raise ValueError("Maximum combinations must be at least one.")
    if max_trajectory_bytes < 1:
        raise ValueError("Maximum trajectory memory must be at least one byte.")

    input_ids = list(input_species_ids)
    target_ids = list(target_species_ids)
    if not input_ids:
        raise ValueError("Select at least one input species to perturb.")
    if not target_ids:
        raise ValueError("Select at least one target species to observe.")
    if len(set(input_ids)) != len(input_ids):
        raise ValueError("Input species must not contain duplicates.")
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("Target species must not contain duplicates.")

    missing_inputs = [
        species_id
        for species_id in input_ids
        if sbml_model.getSpecies(species_id) is None
    ]
    missing_targets = [
        species_id
        for species_id in target_ids
        if sbml_model.getSpecies(species_id) is None
    ]
    if missing_inputs:
        raise ValueError(f"Input species not found: {', '.join(missing_inputs)}.")
    if missing_targets:
        raise ValueError(f"Target species not found: {', '.join(missing_targets)}.")

    combination_count = int(level_count) ** len(input_ids)
    if combination_count > max_combinations:
        raise ValueError(
            f"The sweep requires {combination_count} combinations, exceeding "
            f"the limit of {max_combinations}. Reduce the inputs or sweep levels."
        )

    estimated_trajectory_bytes = estimate_perturbation_trajectory_bytes(
        combination_count,
        sbml_model.getNumSpecies(),
    )
    if estimated_trajectory_bytes > max_trajectory_bytes:
        raise ValueError(
            "Full perturbation trajectories require an estimated "
            f"{estimated_trajectory_bytes / 1024**2:.1f} MiB, exceeding the "
            f"limit of {max_trajectory_bytes / 1024**2:.0f} MiB. Reduce the "
            "selected inputs or sweep levels."
        )

    initial_values = {
        species_id: float(species_ut.initial_symbol_value(sbml_model, species_id))
        for species_id in input_ids
    }
    levels_array = np.linspace(
        -float(variation_percentage),
        float(variation_percentage),
        int(level_count),
    )
    variation_levels = tuple(float(level) for level in levels_array)
    samples = sbml_ut.get_fixed_combinations(
        sbml_model,
        input_ids,
        list(variation_levels),
    )
    combinations = list(sbml_ut.create_combinations(samples))
    combination_level_indices = tuple(
        tuple(indices)
        for indices in product(range(int(level_count)), repeat=len(input_ids))
    )
    if len(combinations) != combination_count:
        raise ValueError(
            "ShapCRN generated an unexpected number of perturbation combinations."
        )
    if len(combination_level_indices) != combination_count:
        raise ValueError(
            "The perturbation level index grid has an unexpected size."
        )

    baseline_level_index = int(np.argmin(np.abs(levels_array)))
    baseline_combination = tuple(
        species_samples[baseline_level_index] for species_samples in samples
    )
    baseline_index = next(
        (
            index
            for index, combination in enumerate(combinations)
            if np.allclose(combination, baseline_combination, rtol=0, atol=0)
        ),
        None,
    )
    if baseline_index is None:
        raise ValueError("The unperturbed baseline combination was not generated.")

    rr_model = sim_ut.load_roadrunner_model(
        sbml_model,
        rel_tol=rel_tol,
        abs_tol=abs_tol,
        integrator=integrator,
    )
    species_selections = {
        species_id: species_ut.symbol_selection(sbml_model.getSpecies(species_id))
        for species_id in target_ids
    }
    rr_model.timeCourseSelections = _all_species_selections(sbml_model)
    trajectories, columns = sim_ut.simulate_combinations(
        rr_model,
        combinations,
        input_ids,
        min_ss_time=end_time,
        end_time=end_time,
        max_end_time=end_time,
        steady_state=False,
        n_processes=-1,
        max_combinations=combination_count,
    )

    if len(trajectories) != combination_count:
        raise ValueError(
            "The perturbation sweep returned an unexpected number of trajectories."
        )

    column_names = list(columns)
    try:
        time_index = column_names.index("time")
    except ValueError as exc:
        raise ValueError("Simulation output does not contain time.") from exc

    target_indices: dict[str, int] = {}
    for species_id, selection in species_selections.items():
        try:
            target_indices[species_id] = column_names.index(selection)
        except ValueError as exc:
            raise ValueError(
                f"Simulation output does not contain target selection {selection!r}."
            ) from exc

    arrays = tuple(np.asarray(trajectory, dtype=float) for trajectory in trajectories)
    expected_shape = arrays[0].shape
    if any(array.shape != expected_shape for array in arrays):
        raise ValueError("Perturbation trajectories do not share the same time grid.")
    actual_trajectory_bytes = sum(array.nbytes for array in arrays)
    if actual_trajectory_bytes > max_trajectory_bytes:
        raise ValueError(
            "Full perturbation trajectories use "
            f"{actual_trajectory_bytes / 1024**2:.1f} MiB, exceeding the "
            f"limit of {max_trajectory_bytes / 1024**2:.0f} MiB."
        )

    envelopes: dict[str, pd.DataFrame] = {}
    for species_id, species_index in target_indices.items():
        values = np.vstack([array[:, species_index] for array in arrays])
        baseline = values[baseline_index]
        minimum = np.min(values, axis=0)
        maximum = np.max(values, axis=0)
        envelopes[species_id] = pd.DataFrame(
            {
                "time": arrays[baseline_index][:, time_index],
                "baseline": baseline,
                "minimum": minimum,
                "maximum": maximum,
                "minimum_change_pct": _relative_percentage_change(
                    minimum,
                    baseline,
                    abs_tol=abs_tol,
                ),
                "maximum_change_pct": _relative_percentage_change(
                    maximum,
                    baseline,
                    abs_tol=abs_tol,
                ),
            }
        )

    input_samples = {
        species_id: tuple(float(value) for value in species_samples)
        for species_id, species_samples in zip(input_ids, samples, strict=True)
    }
    trajectory_metadata: dict[str, PerturbationTrajectoryMetadata] = {}
    for combination_index, (level_indices, combination) in enumerate(
        zip(combination_level_indices, combinations, strict=True)
    ):
        trajectory_id = f"P{combination_index + 1:04d}"
        trajectory_metadata[trajectory_id] = PerturbationTrajectoryMetadata(
            trajectory_id=trajectory_id,
            combination_index=combination_index,
            level_indices=level_indices,
            variations=tuple(
                (species_id, variation_levels[level_index])
                for species_id, level_index in zip(
                    input_ids,
                    level_indices,
                    strict=True,
                )
            ),
            input_values=tuple(
                (species_id, float(combination[input_index]))
                for input_index, species_id in enumerate(input_ids)
            ),
            label=(
                f"{trajectory_id} · "
                + "; ".join(
                    f"{species_id} {variation_levels[level_index]:+g}% → "
                    f"{float(combination[input_index]):.8g}"
                    for input_index, (species_id, level_index) in enumerate(
                        zip(input_ids, level_indices, strict=True)
                    )
                )
            ),
        )

    return PerturbationSweepResult(
        envelopes=envelopes,
        variation_levels=variation_levels,
        initial_values=initial_values,
        species_selections=species_selections,
        combination_count=combination_count,
        trajectories=arrays,
        trajectory_columns=tuple(column_names),
        input_samples=input_samples,
        combination_level_indices=combination_level_indices,
        baseline_index=baseline_index,
        trajectory_metadata=trajectory_metadata,
    )
