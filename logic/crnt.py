import libsbml
import networkx as nx
import numpy as np


def compute_crn_deficiency(sbml_model: libsbml.Model) -> dict[str, int]:
    """Compute network complexes, linkage classes, rank, and Feinberg deficiency.

    Calculates the fundamental topological parameters of a Chemical Reaction
    Network (CRN) based on Feinberg's Chemical Reaction Network Theory (CRNT).
    The deficiency is defined as:

    .. math::

        \\delta = n - l - s

    where :math:`n` is the number of complexes, :math:`l` is the number of
    linkage classes (connected components in the complex graph), and :math:`s`
    is the rank of the stoichiometric matrix.

    Parameters
    ----------
    sbml_model : libsbml.Model
        An active libSBML Model object containing species and reactions.

    Returns
    -------
    dict of str to int
        A dictionary containing the calculated CRNT metrics:

        - ``"num_complexes"`` : Total number of distinct complexes (:math:`n`).
        - ``"linkage_classes"`` : Number of linkage classes (:math:`l`).
        - ``"rank"`` : Rank of the stoichiometric matrix (:math:`s`).
        - ``"deficiency"`` : Feinberg deficiency index (:math:`\\delta`).

    Notes
    -----
    A deficiency of zero (:math:`\\delta = 0`) implies strong structural constraints
    on the network's dynamics under mass-action kinetics, often ruling out
    multistability and oscillations regardless of rate constant values.

    Examples
    --------
    >>> import libsbml
    >>> reader = libsbml.SBMLReader()
    >>> doc = reader.readSBMLFromString(sbml_string)
    >>> model = doc.getModel()
    >>> metrics = compute_crn_deficiency(model)
    >>> print(metrics["deficiency"])
    0
    """
    # Map species IDs to 0-based indices for stoichiometric matrix assembly
    species_id_map = {
        species.getId(): idx
        for idx, species in enumerate(sbml_model.getListOfSpecies())
    }
    num_species = len(species_id_map)
    num_reactions = sbml_model.getNumReactions()

    # Guard clause for empty or uninitialized SBML models
    if num_species == 0 or num_reactions == 0:
        return {
            "num_complexes": 0,
            "linkage_classes": 0,
            "rank": 0,
            "deficiency": 0,
        }

    complexes_map: dict[tuple[tuple[int, float], ...], int] = {}
    complex_index = 0
    complex_graph = nx.Graph()  # Undirected graph to identify linkage classes (l)

    # Initialize stoichiometric matrix N: shape (num_species, num_reactions)
    N = np.zeros((num_species, num_reactions), dtype=np.float64)

    for r_idx, reaction in enumerate(sbml_model.getListOfReactions()):
        # Construct sorted tuples representing unique reactant and product complexes:
        # e.g., ((species_idx_1, stoich_1), (species_idx_2, stoich_2))
        reactants = tuple(
            sorted(
                [
                    (species_id_map[ref.getSpecies()], ref.getStoichiometry())
                    for ref in reaction.getListOfReactants()
                ]
            )
        )
        products = tuple(
            sorted(
                [
                    (species_id_map[ref.getSpecies()], ref.getStoichiometry())
                    for ref in reaction.getListOfProducts()
                ]
            )
        )

        # Populate the stoichiometric matrix N
        for spec_idx, stoich in reactants:
            N[spec_idx, r_idx] -= stoich
        for spec_idx, stoich in products:
            N[spec_idx, r_idx] += stoich

        # Register novel complexes and assign internal IDs
        if reactants not in complexes_map:
            complexes_map[reactants] = complex_index
            complex_index += 1
        if products not in complexes_map:
            complexes_map[products] = complex_index
            complex_index += 1

        reactant_id = complexes_map[reactants]
        product_id = complexes_map[products]

        # Add nodes and connecting reaction edge to the complex graph
        complex_graph.add_node(reactant_id)
        complex_graph.add_node(product_id)
        complex_graph.add_edge(reactant_id, product_id)

    # Extract fundamental CRNT topological quantities
    n = len(complexes_map)
    l = nx.number_connected_components(complex_graph)
    s = int(np.linalg.matrix_rank(N))

    # Compute Feinberg deficiency (enforcing non-negativity against precision artifacts)
    deficiency = max(0, n - l - s)

    return {
        "num_complexes": n,
        "linkage_classes": l,
        "rank": s,
        "deficiency": deficiency,
    }
