"""Importance / Shapley / sensitivity placeholders."""


def run_importance_analysis(*, model_source, knock_species, targets=None, **kwargs):
    # -------------------------------------------------------------------------
    # INSERT IMPORTANCE ANALYSIS HERE
    # -------------------------------------------------------------------------
    # Call ShapCRN assess_importance(...) and normalize the result into a shape
    # that the UI can consume (e.g. DataFrames + artifact paths).
    raise NotImplementedError("INSERT IMPORTANCE ANALYSIS HERE")


def target_scores(shapley_matrix, target: str):
    # -------------------------------------------------------------------------
    # INSERT KO -> TARGET SCORE EXTRACTION HERE
    # -------------------------------------------------------------------------
    # Return one signed score per KO/player for the selected target.
    # The UI uses these values to colour the network with a diverging scale.
    raise NotImplementedError("INSERT KO -> TARGET SCORE EXTRACTION HERE")
