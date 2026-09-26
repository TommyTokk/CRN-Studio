"""ShapCRN importance assessment and normalized result matrices."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import libsbml
import numpy as np
import pandas as pd
from shapcrn import assess_importance

from logic.experiments import list_perturbable_species


@dataclass(frozen=True)
class ImportanceAnalysisResult:
    """Store raw attribution matrices and the perturbation grid.

    Parameters
    ----------
    shapley_values, variations : pandas.DataFrame
        Player IDs as rows and target IDs as columns.
    variation_levels : tuple of float
        Fixed percentage changes supplied to ShapCRN.
    combination_count : int
        Number of Cartesian perturbation combinations.

    Examples
    --------
    >>> result = ImportanceAnalysisResult(pd.DataFrame(), pd.DataFrame(), (), 0)
    >>> result.combination_count
    0
    """

    shapley_values: pd.DataFrame
    variations: pd.DataFrame
    variation_levels: tuple[float, ...]
    combination_count: int


def run_importance_analysis(
    model_bytes: bytes,
    *,
    input_species_ids: Sequence[str],
    target_species_ids: Sequence[str],
    knock_species_ids: Sequence[str],
    variation_percentage: float = 20.0,
    level_count: int = 9,
    end_time: float = 120.0,
    operation: str = "knockout",
    payoff: str = "last",
    max_combinations: int = 2000,
) -> ImportanceAnalysisResult:
    """Assess KO/KI effects across a fixed Cartesian perturbation grid.

    Parameters
    ----------
    model_bytes : bytes
        Current model serialized as SBML XML.
    input_species_ids, target_species_ids, knock_species_ids : sequence of str
        Perturbed inputs, observed targets, and individual KO/KI players.
        Inputs must be disjoint from both other selections.
    variation_percentage : float, default 20
        Symmetric percentage amplitude, between 1 and 100.
    level_count : int, default 9
        Odd number of equidistant levels between 3 and 21.
    end_time : float, default 120
        Positive simulation horizon.
    operation : str, default "knockout"
        Either ``knockout`` or ``knockin``.
    payoff : str, default "last"
        ``last``, ``max``, or ``min`` trajectory statistic.
    max_combinations : int, default 2000
        Upper bound on the Cartesian grid size.

    Returns
    -------
    ImportanceAnalysisResult
        Raw matrices restricted and ordered by the requested players/targets.

    Raises
    ------
    ValueError
        If the model, configuration, selections, or result schema is invalid.
    TypeError
        If ShapCRN does not return DataFrame result matrices.

    Examples
    --------
    >>> run_importance_analysis(b"", input_species_ids=[],
    ...     target_species_ids=[], knock_species_ids=[])
    Traceback (most recent call last):
        ...
    ValueError: Non-empty SBML model bytes are required.
    """
    if not isinstance(model_bytes, bytes) or not model_bytes:
        raise ValueError("Non-empty SBML model bytes are required.")
    if not np.isfinite(variation_percentage) or not 1 <= variation_percentage <= 100:
        raise ValueError("Variation must be between 1 and 100 percent.")
    if (
        isinstance(level_count, bool)
        or not np.isfinite(level_count)
        or int(level_count) != level_count
        or not 3 <= level_count <= 21
        or level_count % 2 == 0
    ):
        raise ValueError("Sweep levels must be an odd integer between 3 and 21.")
    if not np.isfinite(end_time) or end_time <= 0:
        raise ValueError("End time must be finite and greater than zero.")
    if max_combinations < 1:
        raise ValueError("Maximum combinations must be positive.")
    if operation not in ("knockout", "knockin") or payoff not in ("last", "max", "min"):
        raise ValueError("Unsupported operation or payoff.")

    document = libsbml.readSBMLFromString(model_bytes.decode("utf-8"))
    model = document.getModel()
    if model is None or document.getNumErrors(libsbml.LIBSBML_SEV_ERROR):
        raise ValueError("A valid SBML model is required.")
    inputs, targets, players = map(
        list, (input_species_ids, target_species_ids, knock_species_ids)
    )
    for label, ids in (
        ("input", inputs),
        ("target", targets),
        ("KO/KI player", players),
    ):
        if not ids or len(ids) != len(set(ids)):
            raise ValueError(
                f"Select at least one {label}; duplicates are not allowed."
            )
        if any(model.getSpecies(sid) is None for sid in ids):
            raise ValueError(f"Unknown species in {label} selection.")
    if set(inputs) & (set(targets) | set(players)):
        raise ValueError("Inputs must be distinct from targets and KO/KI players.")
    perturbable, _ = list_perturbable_species(model)
    if not set(inputs).issubset(perturbable):
        raise ValueError("Selected inputs include species that cannot be perturbed.")
    combination_count = int(level_count) ** len(inputs)
    if combination_count > max_combinations:
        raise ValueError(f"The sweep exceeds {max_combinations:,} combinations.")
    levels = tuple(
        float(value)
        for value in np.linspace(
            -variation_percentage, variation_percentage, int(level_count)
        )
    )

    with TemporaryDirectory(prefix="crn-importance-") as directory:
        model_path = Path(directory) / "model.xml"
        model_path.write_bytes(model_bytes)
        result = assess_importance(
            model_path,
            operation=operation,
            input_species=inputs,
            knocked_species=players,
            target_nodes=targets,
            preserve_inputs=True,
            use_perturbations=True,
            fixed_perturbations=list(levels),
            max_combinations=max_combinations,
            payoff=payoff,
            end_time=float(end_time),
            steady_state=False,
            integrator="cvode",
            output_dir=None,
        )

    matrices = []
    for frame in (result.shapley_values, result.variations):
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("ShapCRN did not return the required result matrices.")
        normalized = frame.rename(
            columns=lambda name: str(name).removeprefix("[").removesuffix("]")
        )
        if (
            not normalized.columns.is_unique
            or not normalized.index.is_unique
            or not set(targets).issubset(normalized.columns)
            or not set(players).issubset(normalized.index)
        ):
            raise ValueError(
                "ShapCRN returned missing or ambiguous player/target labels."
            )
        matrices.append(normalized.loc[players, targets].copy())
    return ImportanceAnalysisResult(matrices[0], matrices[1], levels, combination_count)
