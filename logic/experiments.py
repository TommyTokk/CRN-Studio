"""Simulation and knockout/knock-in experiment placeholders."""


def run_simulation(*, model_source, end_time: float, points: int, **kwargs):
    # -------------------------------------------------------------------------
    # INSERT SIMULATION HERE
    # -------------------------------------------------------------------------
    # Call ShapCRN/RoadRunner and return trajectory data in a UI-friendly form.
    raise NotImplementedError("INSERT SIMULATION HERE")


def run_perturbation_experiment(*, model_source, operation: str, entity_type: str, entity_id: str, **kwargs):
    # -------------------------------------------------------------------------
    # INSERT KO / KI + BASELINE COMPARISON HERE
    # -------------------------------------------------------------------------
    # Suggested result: a dataclass/dict containing baseline trajectory,
    # perturbed trajectory, metrics, and optional perturbed SBML bytes.
    raise NotImplementedError("INSERT PERTURBATION LOGIC HERE")
