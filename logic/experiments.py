"""Simulation, knock, and concentration-perturbation experiments."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import product
from typing import Any

import libsbml
import numpy as np
import pandas as pd
from shapcrn import (
    exceptions as shapcrn_exceptions,
    knockin_species,
    knockout_reaction,
    knockout_species,
)
from shapcrn.utils import simulation as sim_ut
from shapcrn.utils.sbml import species as species_ut
from shapcrn.utils.sbml import utils as sbml_ut
from shapcrn.utils.sbml.reactions import _replace_names
from shapcrn.utils.sbml.validation import (
    check,
    fresh_metaids,
    reject_dependencies,
    require_fixed_references,
    transact,
)


PERTURBATION_TRAJECTORY_MEMORY_LIMIT_BYTES = 128 * 1024**2
PERTURBATION_OUTPUT_ROWS = 100
PHASE_PLOT_MAX_POINTS = 500


@dataclass(frozen=True)
class KnockExperimentResult:
    """The in-memory model produced by a knock batch and its trajectory."""

    modified_model: Any
    trajectory: pd.DataFrame


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
    """Store full trajectories and derived fixed-percentage sweep metadata.

    Parameters
    ----------
    envelopes : dict of str to pandas.DataFrame
        Envelopes materialized for the targets requested during the run.
    variation_levels : tuple of float
        Percentage levels used by every perturbed input.
    initial_values : dict of str to float
        Unperturbed input values.
    species_selections : dict of str to str
        All available species IDs mapped to RoadRunner selections.
    combination_count : int
        Number of simulated Cartesian combinations.
    trajectories : tuple of numpy.ndarray
        Full trajectories for all combinations.
    trajectory_columns : tuple of str
        RoadRunner columns shared by the trajectories.
    input_samples : dict of str to tuple of float
        Absolute sampled values for every input.
    combination_level_indices : tuple of tuple of int
        Level indices corresponding to each trajectory.
    baseline_index : int
        Position of the unperturbed trajectory.
    trajectory_metadata : dict of str to PerturbationTrajectoryMetadata
        Stable identifiers and labels for individual trajectories.

    Examples
    --------
    >>> result = PerturbationSweepResult({}, (), {}, {}, 0, (), (), {}, (), 0, {})
    >>> result.combination_count
    0
    """

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


def truncate_trajectory(
    trajectory: pd.DataFrame,
    end_time: float,
    *,
    time_column: object = "time",
) -> pd.DataFrame:
    """Return a trajectory ending exactly at a requested time.

    A linearly interpolated row is appended when ``end_time`` falls between
    two samples. The input frame is never modified.

    Parameters
    ----------
    trajectory : pandas.DataFrame
        Numeric trajectory containing a monotonically increasing time column.
    end_time : float
        Inclusive upper bound for the returned trajectory.
    time_column : object, default "time"
        Label of the time column.

    Returns
    -------
    pandas.DataFrame
        Independent trajectory copy ending at ``end_time`` when interpolation
        is required.

    Raises
    ------
    ValueError
        If the trajectory, time column, values, or requested bound is invalid.

    Examples
    --------
    >>> frame = pd.DataFrame({"time": [0.0, 2.0], "S1": [1.0, 3.0]})
    >>> truncate_trajectory(frame, 1.0).to_dict("list")
    {'time': [0.0, 1.0], 'S1': [1.0, 2.0]}
    """
    if not isinstance(trajectory, pd.DataFrame) or trajectory.empty:
        raise ValueError("Trajectory data must be a non-empty DataFrame.")
    if time_column not in trajectory.columns:
        raise ValueError(f"Trajectory does not contain time column {time_column!r}.")
    if not np.isfinite(end_time):
        raise ValueError("Trajectory end time must be finite.")

    try:
        numeric = trajectory.apply(pd.to_numeric, errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Trajectory columns must contain numeric values.") from exc
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("Trajectory values must be finite.")

    times = numeric[time_column].to_numpy(dtype=float)
    if np.any(np.diff(times) <= 0):
        raise ValueError("Trajectory times must be strictly increasing.")
    requested_end = float(end_time)
    if requested_end < times[0]:
        raise ValueError("Trajectory end time precedes the first sample.")
    if requested_end >= times[-1]:
        return trajectory.copy().reset_index(drop=True)

    upper_index = int(np.searchsorted(times, requested_end, side="left"))
    if times[upper_index] == requested_end:
        return trajectory.iloc[: upper_index + 1].copy().reset_index(drop=True)

    lower_index = upper_index - 1
    fraction = (requested_end - times[lower_index]) / (
        times[upper_index] - times[lower_index]
    )
    interpolated = numeric.iloc[lower_index] + fraction * (
        numeric.iloc[upper_index] - numeric.iloc[lower_index]
    )
    interpolated[time_column] = requested_end
    return pd.concat(
        [numeric.iloc[:upper_index], interpolated.to_frame().T],
        ignore_index=True,
    )


def select_trajectory_species(
    trajectory: pd.DataFrame,
    species_ids: Sequence[str],
    *,
    column_selections: Sequence[object] | None = None,
) -> pd.DataFrame:
    """Return time plus selected species without modifying a trajectory.

    Parameters
    ----------
    trajectory : pandas.DataFrame
        Stored RoadRunner trajectory.
    species_ids : sequence of str
        Ordered species IDs to retain.
    column_selections : sequence of object, optional
        RoadRunner selections corresponding positionally to DataFrame columns.

    Returns
    -------
    pandas.DataFrame
        Independent frame with the original column labels and requested order.

    Raises
    ------
    ValueError
        If selections are empty, duplicated, missing, or ambiguous.

    Examples
    --------
    >>> frame = pd.DataFrame({"time": [0.0], "[S1]": [1.0], "[S2]": [2.0]})
    >>> list(select_trajectory_species(frame, ["S2"]).columns)
    ['time', '[S2]']
    """
    if not isinstance(trajectory, pd.DataFrame) or trajectory.empty:
        raise ValueError("Trajectory data must be a non-empty DataFrame.")
    requested = [str(species_id) for species_id in species_ids]
    if not requested or any(not species_id for species_id in requested):
        raise ValueError("Select at least one non-empty species ID.")
    if len(requested) != len(set(requested)):
        raise ValueError("Selected species must not contain duplicates.")

    selections = (
        list(column_selections)
        if column_selections is not None
        else list(trajectory.columns)
    )
    if len(selections) != len(trajectory.columns):
        raise ValueError("RoadRunner selections must match trajectory columns.")
    normalized = [_selection_id(selection) for selection in selections]
    time_indices = [
        index
        for index, selection in enumerate(normalized)
        if selection.lower() == "time"
    ]
    if len(time_indices) != 1:
        raise ValueError("Trajectory data must contain exactly one time column.")

    selected_indices = [time_indices[0]]
    for species_id in requested:
        matches = [
            index
            for index, selection in enumerate(normalized)
            if selection == species_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Trajectory must contain exactly one column for {species_id!r}."
            )
        selected_indices.append(matches[0])
    return trajectory.iloc[:, selected_indices].copy()


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
    end_time: float | None = None,
) -> dict[str, pd.DataFrame]:
    """Normalize Standard and perturbation trajectories for phase comparison.

    Parameters
    ----------
    standard_trajectory : pandas.DataFrame
        Reference trajectory.
    species_ids : sequence of str
        Two or three species defining the phase axes.
    sweep_result : PerturbationSweepResult
        Cached sweep providing comparison trajectories.
    trajectory_ids : sequence of str
        Stable perturbation trajectory identifiers to include.
    standard_column_selections : sequence of object, optional
        RoadRunner selections corresponding to reference DataFrame columns.
    max_points : int, default PHASE_PLOT_MAX_POINTS
        Maximum samples retained per trajectory.
    end_time : float, optional
        Inclusive display horizon applied before downsampling.

    Returns
    -------
    dict of str to pandas.DataFrame
        Prepared reference and perturbation trajectories keyed by identifier.

    Examples
    --------
    >>> callable(prepare_phase_comparison)
    True
    """
    standard_view = (
        truncate_trajectory(
            standard_trajectory,
            end_time,
            time_column=standard_trajectory.columns[0],
        )
        if end_time is not None
        else standard_trajectory
    )
    comparison = {
        "standard": downsample_phase_trajectory(
            prepare_phase_trajectory(
                standard_view,
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
        trajectory_view = (
            truncate_trajectory(trajectory, end_time)
            if end_time is not None
            else trajectory
        )
        comparison[trajectory_id] = downsample_phase_trajectory(
            prepare_phase_trajectory(
                trajectory_view,
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


def build_perturbation_envelopes(
    result: PerturbationSweepResult,
    target_species_ids: Sequence[str],
    *,
    end_time: float | None = None,
    abs_tol: float = 1e-9,
) -> dict[str, pd.DataFrame]:
    """Build target envelopes from cached perturbation trajectories.

    Parameters
    ----------
    result : PerturbationSweepResult
        Cached sweep containing every full trajectory.
    target_species_ids : sequence of str
        Ordered species IDs for which envelopes should be derived.
    end_time : float, optional
        Inclusive display horizon. Values between samples are interpolated.
    abs_tol : float, default 1e-9
        Baseline magnitude below which percentage changes are unavailable.

    Returns
    -------
    dict of str to pandas.DataFrame
        Envelope frames keyed by target species ID.

    Raises
    ------
    TypeError
        If ``result`` is not a perturbation sweep result.
    ValueError
        If targets, stored trajectories, or tolerance are invalid.

    Examples
    --------
    >>> metadata = {"P0001": PerturbationTrajectoryMetadata(
    ...     "P0001", 0, (0,), (("S1", 0.0),), (("S1", 1.0),), "baseline")}
    >>> result = PerturbationSweepResult({}, (0.0,), {"S1": 1.0},
    ...     {"S1": "[S1]"}, 1, (np.array([[0.0, 1.0], [2.0, 3.0]]),),
    ...     ("time", "[S1]"), {"S1": (1.0,)}, ((0,),), 0, metadata)
    >>> float(build_perturbation_envelopes(
    ...     result, ["S1"], end_time=1.0)["S1"]["baseline"].iloc[-1])
    2.0
    """
    if not isinstance(result, PerturbationSweepResult):
        raise TypeError("A PerturbationSweepResult is required.")
    targets = [str(species_id) for species_id in target_species_ids]
    if not targets or len(targets) != len(set(targets)):
        raise ValueError("Select unique target species.")
    if not np.isfinite(abs_tol) or abs_tol < 0:
        raise ValueError("Absolute tolerance must be finite and non-negative.")
    if not result.trajectories:
        raise ValueError("The perturbation sweep contains no trajectories.")
    if not 0 <= result.baseline_index < len(result.trajectories):
        raise ValueError("The perturbation baseline index is invalid.")

    columns = list(result.trajectory_columns)
    try:
        time_index = columns.index("time")
    except ValueError as exc:
        raise ValueError("Perturbation trajectories do not contain time.") from exc
    arrays: list[np.ndarray] = []
    for trajectory in result.trajectories:
        array = np.asarray(trajectory, dtype=float)
        if array.ndim != 2 or array.shape[1] != len(columns):
            raise ValueError("A perturbation trajectory has an invalid shape.")
        arrays.append(array)

    reference_times = arrays[0][:, time_index]
    if any(
        len(array) != len(reference_times)
        or not np.allclose(
            array[:, time_index],
            reference_times,
            rtol=0,
            atol=0,
        )
        for array in arrays[1:]
    ):
        raise ValueError("Perturbation trajectories do not share the same time grid.")

    time_view = (
        truncate_trajectory(
            pd.DataFrame({"time": reference_times}),
            float(end_time),
        )["time"].to_numpy(dtype=float)
        if end_time is not None
        else reference_times.copy()
    )
    exact_sample_count = int(np.searchsorted(reference_times, time_view[-1], side="right"))
    interpolate_end = time_view[-1] not in reference_times

    envelopes: dict[str, pd.DataFrame] = {}
    for species_id in targets:
        selection = result.species_selections.get(species_id)
        if selection is None or selection not in columns:
            raise ValueError(
                f"Perturbation trajectories do not contain target {species_id!r}."
            )
        species_index = columns.index(selection)
        values = np.vstack([array[:, species_index] for array in arrays])
        if interpolate_end:
            upper_index = exact_sample_count
            lower_index = upper_index - 1
            fraction = (time_view[-1] - reference_times[lower_index]) / (
                reference_times[upper_index] - reference_times[lower_index]
            )
            interpolated = values[:, lower_index] + fraction * (
                values[:, upper_index] - values[:, lower_index]
            )
            values = np.column_stack(
                [values[:, :upper_index], interpolated]
            )
        else:
            values = values[:, :exact_sample_count]
        baseline = values[result.baseline_index]
        minimum = np.min(values, axis=0)
        maximum = np.max(values, axis=0)
        envelopes[species_id] = pd.DataFrame(
            {
                "time": time_view,
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
    return envelopes


def _all_species_selections(sbml_model: Any) -> list[str]:
    """Return time plus every species symbol, including fixed species."""
    return ["time"] + [
        species_ut.symbol_selection(species)
        for species in sbml_model.getListOfSpecies()
    ]


def _unique_sid(sbml_model: Any, base_id: str, reserved: set[str]) -> str:
    """Allocate a deterministic, model-wide unique SBML identifier."""
    candidate = base_id
    suffix = 2
    while (
        candidate in reserved
        or sbml_model.getElementBySId(candidate) is not None
        or sbml_model.getFunctionDefinition(candidate) is not None
    ):
        candidate = f"{base_id}_{suffix}"
        suffix += 1
    reserved.add(candidate)
    return candidate


def _batch_knockin_reactions(
    sbml_model: Any,
    reaction_ids: Sequence[str],
    values_by_reaction: dict[str, tuple[float, ...]],
) -> Any:
    """Knock in reactions atomically, sharing fixed copies of common reactants."""
    modified_model = sbml_model.clone()
    if modified_model is None:
        raise ValueError("The SBML model could not be cloned.")

    def operation(model: Any) -> None:
        reserved_ids: set[str] = set()
        reaction_clones: list[tuple[str, Any]] = []
        reactant_values: dict[str, float] = {}

        for reaction_id in reaction_ids:
            reaction = model.getReaction(reaction_id)
            if reaction is None:
                raise ValueError(f"Reaction not found: {reaction_id}.")
            if reaction.getFast():
                raise shapcrn_exceptions.ModelModificationError(
                    "knock in reaction",
                    reaction_id,
                    "fast=true reactions are unsupported",
                )
            require_fixed_references(model, reaction)
            reject_dependencies(model, [reaction_id], reaction_id)

            references = list(reaction.getListOfReactants())
            values = values_by_reaction[reaction_id]
            if len(values) != len(references):
                raise ValueError(
                    f"Reaction {reaction_id!r} requires one value per reactant."
                )
            local_values: dict[str, float] = {}
            for reference, value in zip(references, values, strict=True):
                species_id = reference.getSpecies()
                numeric_value = float(value)
                if (
                    species_id in local_values
                    and local_values[species_id] != numeric_value
                ):
                    raise ValueError(
                        f"Reaction {reaction_id!r} provides inconsistent values "
                        f"for repeated reactant {species_id!r}."
                    )
                local_values[species_id] = numeric_value
                if (
                    species_id in reactant_values
                    and not np.isclose(
                        reactant_values[species_id],
                        numeric_value,
                        rtol=1e-12,
                        atol=0.0,
                    )
                ):
                    raise ValueError(
                        f"Shared reactant {species_id!r} has inconsistent "
                        "knock-in values."
                    )
                reactant_values[species_id] = numeric_value

        copy_ids: dict[str, str] = {}
        for species_id, value in reactant_values.items():
            species = model.getSpecies(species_id)
            if species is None:
                raise ValueError(f"Reactant species not found: {species_id}.")
            copy_id = _unique_sid(model, f"{species_id}_KI", reserved_ids)
            clone = species.clone()
            check(clone.setId(copy_id), copy_id)
            fresh_metaids(model, clone, f"_KI_{copy_id}")
            species_ut.set_symbol_value(clone, value)
            check(clone.setBoundaryCondition(True), copy_id)
            check(clone.setConstant(True), copy_id)
            check(model.addSpecies(clone), copy_id)
            copy_ids[species_id] = copy_id

        for reaction_id in reaction_ids:
            reaction = model.getReaction(reaction_id)
            law = reaction.getKineticLaw()
            if law is None or law.getMath() is None:
                raise shapcrn_exceptions.InvalidKineticLawError(reaction_id)

            new_id = _unique_sid(model, f"{reaction_id}_KI", reserved_ids)
            clone = reaction.clone()
            check(clone.setId(new_id), new_id)
            mapping: dict[str, Any] = {}
            for reference in clone.getListOfReactants():
                old_species_id = reference.getSpecies()
                copy_id = copy_ids[old_species_id]
                check(reference.setSpecies(copy_id), new_id)
                mapping[old_species_id] = libsbml.parseL3Formula(copy_id)

            parameters = (
                law.getListOfLocalParameters()
                if model.getLevel() == 3
                else law.getListOfParameters()
            )
            for parameter in parameters:
                mapping.pop(parameter.getId(), None)
            check(
                clone.getKineticLaw().setMath(
                    _replace_names(law.getMath(), mapping)
                ),
                new_id,
            )
            fresh_metaids(model, clone, f"_KI_{new_id}")
            reaction_clones.append((new_id, clone))

        for reaction_id in reaction_ids:
            model.removeReaction(reaction_id)
        for new_id, clone in reaction_clones:
            check(model.addReaction(clone), new_id)

    transact(modified_model, operation)
    return modified_model


def run_knock_experiment(
    sbml_model: Any,
    *,
    operation: str,
    entity_type: str,
    entity_ids: Sequence[str],
    end_time: float = 120.0,
    output_rows: int = 100,
    rel_tol: float = 1e-6,
    abs_tol: float = 1e-9,
    integrator: str = "cvode",
) -> KnockExperimentResult:
    """Apply one knock operation to multiple targets and simulate the clone."""
    if end_time <= 0:
        raise ValueError("Experiment end time must be greater than zero.")
    if output_rows < 2:
        raise ValueError("At least two output rows are required.")

    normalized_operation = operation.strip().lower().replace("-", "")
    normalized_entity = entity_type.strip().lower()
    if normalized_operation not in {"knockout", "knockin"} or normalized_entity not in {
        "species",
        "reaction",
    }:
        raise ValueError(
            f"Unsupported knock experiment: {operation!r} on {entity_type!r}."
        )

    if isinstance(entity_ids, (str, bytes)):
        raise ValueError("Knock entities must be provided as a sequence of IDs.")
    requested_ids = [str(entity_id) for entity_id in entity_ids]
    if not requested_ids:
        raise ValueError("Select at least one entity for the knock experiment.")
    if len(set(requested_ids)) != len(requested_ids):
        raise ValueError("Knock entities must not contain duplicates.")

    entities = (
        list(sbml_model.getListOfSpecies())
        if normalized_entity == "species"
        else list(sbml_model.getListOfReactions())
    )
    available_ids = [entity.getId() for entity in entities]
    missing_ids = [
        entity_id
        for entity_id in requested_ids
        if entity_id not in available_ids
    ]
    if missing_ids:
        raise ValueError(
            f"{normalized_entity.title()} not found: {', '.join(missing_ids)}."
        )
    requested = set(requested_ids)
    ordered_ids = [entity_id for entity_id in available_ids if entity_id in requested]

    if normalized_operation == "knockin" and normalized_entity == "species":
        values = {
            entity_id: float(sim_ut.get_species_peak_value(sbml_model, entity_id))
            for entity_id in ordered_ids
        }
    elif normalized_operation == "knockin":
        values_by_reaction = {
            reaction_id: tuple(
                float(value)
                for value in sim_ut.get_reactants_peak_values(
                    sbml_model,
                    sbml_model.getReaction(reaction_id),
                )
            )
            for reaction_id in ordered_ids
        }

    if normalized_operation == "knockin" and normalized_entity == "reaction":
        modified_model = _batch_knockin_reactions(
            sbml_model,
            ordered_ids,
            values_by_reaction,
        )
    else:
        modified_model = sbml_model.clone()
        if modified_model is None:
            raise ValueError("The SBML model could not be cloned.")
        modifier = (
            knockout_species
            if normalized_operation == "knockout" and normalized_entity == "species"
            else knockout_reaction
            if normalized_operation == "knockout"
            else knockin_species
        )
        for entity_id in ordered_ids:
            kwargs = (
                {"value": values[entity_id]}
                if normalized_operation == "knockin"
                else {}
            )
            modified_model = modifier(
                modified_model,
                entity_id,
                inplace=True,
                **kwargs,
            )

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
    return KnockExperimentResult(
        modified_model=modified_model,
        trajectory=_as_trajectory_frame(values, columns),
    )


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
    """Perturb inputs and return envelopes plus every full trajectory.

    Parameters
    ----------
    sbml_model : object
        libSBML model to simulate.
    input_species_ids, target_species_ids : sequence of str
        Perturbed inputs and targets whose initial envelopes are materialized.
    variation_percentage : float, default 20
        Symmetric perturbation amplitude.
    level_count : int, default 9
        Odd number of fixed perturbation levels.
    end_time : float, default 120
        Positive simulation horizon.
    rel_tol, abs_tol : float
        RoadRunner integration tolerances.
    integrator : str, default "cvode"
        RoadRunner integrator name.
    max_combinations : int, default 2000
        Maximum Cartesian combinations.
    max_trajectory_bytes : int
        Maximum memory allocated to full trajectories.

    Returns
    -------
    PerturbationSweepResult
        Complete cached sweep and initially requested envelopes.

    Raises
    ------
    ValueError
        If configuration, model selections, output, or memory use is invalid.

    Examples
    --------
    >>> callable(run_perturbation_sweep)
    True
    """
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
        species.getId(): species_ut.symbol_selection(species)
        for species in sbml_model.getListOfSpecies()
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
    if "time" not in column_names:
        raise ValueError("Simulation output does not contain time.")
    species_selections = {
        species_id: selection
        for species_id, selection in species_selections.items()
        if selection in column_names
    }
    missing_targets = [
        species_id for species_id in target_ids if species_id not in species_selections
    ]
    if missing_targets:
        raise ValueError(
            "Simulation output does not contain target species: "
            + ", ".join(missing_targets)
            + "."
        )

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

    raw_result = PerturbationSweepResult(
        envelopes={},
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
    return replace(
        raw_result,
        envelopes=build_perturbation_envelopes(
            raw_result,
            target_ids,
            abs_tol=abs_tol,
        ),
    )
