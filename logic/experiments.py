"""Simulation, knock, and concentration-perturbation experiments."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True)
class PerturbationSweepResult:
    """Target envelopes produced by a fixed-percentage perturbation sweep."""

    envelopes: dict[str, pd.DataFrame]
    variation_levels: tuple[float, ...]
    initial_values: dict[str, float]
    species_selections: dict[str, str]
    combination_count: int


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
) -> PerturbationSweepResult:
    """Perturb multiple inputs and return one pointwise envelope per target."""
    if variation_percentage <= 0:
        raise ValueError("Perturbation amplitude must be greater than zero.")
    if level_count < 3 or level_count % 2 == 0:
        raise ValueError("Perturbation levels must be an odd number of at least three.")
    if end_time <= 0:
        raise ValueError("Experiment end time must be greater than zero.")
    if max_combinations < 1:
        raise ValueError("Maximum combinations must be at least one.")

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
    if len(combinations) != combination_count:
        raise ValueError(
            "ShapCRN generated an unexpected number of perturbation combinations."
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
    selections = list(rr_model.timeCourseSelections)
    if "time" not in selections:
        selections.insert(0, "time")
    for selection in species_selections.values():
        if selection not in selections:
            selections.append(selection)
    rr_model.timeCourseSelections = selections
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

    arrays = [np.asarray(trajectory, dtype=float) for trajectory in trajectories]
    expected_shape = arrays[0].shape
    if any(array.shape != expected_shape for array in arrays):
        raise ValueError("Perturbation trajectories do not share the same time grid.")

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

    return PerturbationSweepResult(
        envelopes=envelopes,
        variation_levels=variation_levels,
        initial_values=initial_values,
        species_selections=species_selections,
        combination_count=combination_count,
    )
