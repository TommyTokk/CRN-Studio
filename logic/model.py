"""Model loading and metadata extraction.

Replace the placeholders below with your own ShapCRN/libSBML implementation.
"""

from shapcrn.utils.sbml import io
import libsbml

from .crnt import compute_crn_deficiency


import pandas as pd


def get_species_dataframe(model: libsbml.Model) -> pd.DataFrame:
    """Extract species metadata into a formatted DataFrame."""
    species_data = []
    for s in model.getListOfSpecies():
        species_data.append(
            {
                "ID": s.getId(),
                "Name": s.getName() or "—",
                "Compartment": s.getCompartment() or "—",
                "Initial Concentration": (
                    s.getInitialConcentration()
                    if s.isSetInitialConcentration()
                    else (s.getInitialAmount() if s.isSetInitialAmount() else "—")
                ),
                "Boundary Condition": s.getBoundaryCondition(),
                "Constant": s.getConstant(),
            }
        )
    return pd.DataFrame(species_data)


def get_reactions_dataframe(model: libsbml.Model) -> pd.DataFrame:
    """Extract reaction definitions, stoichiometry strings, and kinetic rate laws."""
    reactions_data = []
    for r in model.getListOfReactions():
        reactants = [
            f"{int(ref.getStoichiometry()) if ref.getStoichiometry().is_integer() else ref.getStoichiometry()} {ref.getSpecies()}".strip()
            for ref in r.getListOfReactants()
        ]
        products = [
            f"{int(ref.getStoichiometry()) if ref.getStoichiometry().is_integer() else ref.getStoichiometry()} {ref.getSpecies()}".strip()
            for ref in r.getListOfProducts()
        ]

        arrow = " ⇌ " if r.getReversible() else " → "
        equation = " + ".join(reactants) + arrow + " + ".join(products)

        kinetic_law = r.getKineticLaw()
        formula = kinetic_law.getFormula() if kinetic_law else "—"

        reactions_data.append(
            {
                "ID": r.getId(),
                "Name": r.getName() or "—",
                "Reaction Formula": equation,
                "Reversible": r.getReversible(),
                "Kinetic Law (Formula)": formula,
            }
        )
    return pd.DataFrame(reactions_data)


def load_model(file_bytes: bytes):
    # -------------------------------------------------------------------------
    # INSERT MODEL LOADING HERE
    # -------------------------------------------------------------------------

    # Call your ShapCRN loader/preparation function.
    _, sbml_model = io.load_and_prepare_model_from_bytes(
        file_bytes, split_reversible=True
    )

    return sbml_model


def model_summary(model: libsbml.Model) -> dict:
    # -------------------------------------------------------------------------
    # INSERT MODEL METADATA / COUNTS HERE
    # -------------------------------------------------------------------------
    # Return fields such as:
    # species, reactions, compartments, reactants, products, modifiers, etc.
    #
    n_reversible = 0

    for r in model.getListOfReactions():
        if r.getReversible():
            n_reversible += 1

    # Get deficiency infos
    def_info = compute_crn_deficiency(model)

    n_coplexes = def_info.get("num_complexes", 0)
    linkage_classes = def_info.get("linkage_classes", 0)
    rank = def_info.get("rank", 0)
    deficiency = def_info.get("deficiency", 0)

    summary = {
        "species": model.getListOfSpecies(),
        "num_species": model.getNumSpecies(),
        "reactions": model.getListOfReactions(),
        "num_reactions": model.getNumReactions(),
        "num_reversible": n_reversible,
        "compartments": model.getListOfCompartments(),
        "num_compartments": model.getNumCompartments(),
        "num_complexes": n_coplexes,
        "linkage_classes": linkage_classes,
        "rank": rank,
        "deficiency": deficiency,
    }

    return summary
