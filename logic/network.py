"""Network extraction and Cytoscape mapping for SBML Chemical Reaction Networks."""

from __future__ import annotations

from typing import Any

import libsbml
import networkx as nx
import numpy as np
import pandas as pd


def get_stoichiometric_matrix(
    model: libsbml.Model, use_names: bool = False
) -> pd.DataFrame:
    """Extract the stoichiometric matrix N from a libSBML Model as a pandas DataFrame.

    Parameters
    ----------
    model : libsbml.Model
        An active libSBML Model instance.
    use_names : bool, default=False
        If True, uses human-readable species and reaction names as DataFrame
        index and column labels. If False or if a name is missing, falls back
        to SBML identifier strings (IDs).

    Returns
    -------
    pd.DataFrame
        A DataFrame of shape (num_species, num_reactions) representing the
        stoichiometric matrix N. Rows correspond to species, columns to reactions.
        Coefficients are negative for reactants, positive for products, and zero otherwise.

    Examples
    --------
    >>> import libsbml
    >>> # ... load sbml model ...
    >>> df_N = get_stoichiometric_matrix(model, use_names=True)
    >>> print(df_N.shape)
    (12, 8)
    """
    species_list = model.getListOfSpecies()
    reactions_list = model.getListOfReactions()

    num_species = len(species_list)
    num_reactions = len(reactions_list)

    if num_species == 0 or num_reactions == 0:
        return pd.DataFrame()

    # Map species ID to 0-based row index
    species_id_to_idx = {
        species.getId(): idx for idx, species in enumerate(species_list)
    }

    # Initialize stoichiometric matrix N
    N = np.zeros((num_species, num_reactions), dtype=np.float64)

    # Populate N with reactant (-) and product (+) stoichiometries
    for r_idx, reaction in enumerate(reactions_list):
        for ref in reaction.getListOfReactants():
            s_idx = species_id_to_idx.get(ref.getSpecies())
            if s_idx is not None:
                N[s_idx, r_idx] -= ref.getStoichiometry()

        for ref in reaction.getListOfProducts():
            s_idx = species_id_to_idx.get(ref.getSpecies())
            if s_idx is not None:
                N[s_idx, r_idx] += ref.getStoichiometry()

    # Determine Row (Species) and Column (Reactions) labels
    if use_names:
        row_labels = [species.getName() or species.getId() for species in species_list]
        col_labels = [
            reaction.getName() or reaction.getId() for reaction in reactions_list
        ]
    else:
        row_labels = [species.getId() for species in species_list]
        col_labels = [reaction.getId() for reaction in reactions_list]

    # Return structured DataFrame
    return pd.DataFrame(N, index=row_labels, columns=col_labels)


def format_stoichiometric_matrix_display(N_df: pd.DataFrame) -> pd.DataFrame:
    """Format the stoichiometric matrix for display in Streamlit or DataTables.

    Converts numerical floats to integer strings where applicable and replaces
    zeros with clean empty strings or dot placeholders for easier scanning.

    Parameters
    ----------
    N_df : pd.DataFrame
        The raw numeric stoichiometric matrix.

    Returns
    -------
    pd.DataFrame
        A formatted string DataFrame suitable for visual inspection.
    """
    if N_df.empty:
        return N_df

    def _format_val(val: float) -> str:
        if val == 0:
            return "·"  # Visual placeholder for zero entries
        if val == int(val):
            return f"{int(val):+d}"  # Explicit sign (+1, -2)
        return f"{val:+.2f}"

    return N_df.map(_format_val)


def build_network(model: libsbml.Model) -> nx.DiGraph:
    """Extract a bipartite directed graph from an SBML model using NetworkX.

    Nodes represent either Species or Reactions. Edges represent reactant-to-reaction
    or reaction-to-product relationships with their corresponding stoichiometry.

    Parameters
    ----------
    model : libsbml.Model
        An active libSBML Model instance.

    Returns
    -------
    nx.DiGraph
        A bipartite directed graph where nodes have a `node_type` attribute
        ('species' or 'reaction').
    """
    graph = nx.DiGraph()

    # 1. Add Species nodes
    for species in model.getListOfSpecies():
        s_id = species.getId()
        s_name = species.getName() or s_id
        graph.add_node(
            s_id,
            label=s_name,
            node_type="species",
            compartment=species.getCompartment(),
        )

    # 2. Add Reaction nodes and connecting edges
    for reaction in model.getListOfReactions():
        r_id = reaction.getId()
        r_name = reaction.getName() or r_id
        is_reversible = reaction.getReversible()

        graph.add_node(
            r_id,
            label=r_name,
            node_type="reaction",
            reversible=is_reversible,
        )

        # Modifier edges: Species -> Reaction. Modifiers influence the reaction
        # without being consumed, so they do not carry a stoichiometric label.
        for ref in reaction.getListOfModifiers():
            s_id = ref.getSpecies()
            graph.add_edge(s_id, r_id, stoichiometry=None, role="modifier")

        # Reactant edges: Species -> Reaction
        for ref in reaction.getListOfReactants():
            s_id = ref.getSpecies()
            stoich = ref.getStoichiometry()
            graph.add_edge(s_id, r_id, stoichiometry=stoich, role="reactant")

            # If reversible, draw the reverse flow: Reaction -> Species
            if is_reversible:
                graph.add_edge(
                    r_id, s_id, stoichiometry=stoich, role="reversible_reactant"
                )

        # Product edges: Reaction -> Species
        for ref in reaction.getListOfProducts():
            s_id = ref.getSpecies()
            stoich = ref.getStoichiometry()
            graph.add_edge(r_id, s_id, stoichiometry=stoich, role="product")

            # If reversible, draw the reverse flow: Species -> Reaction
            if is_reversible:
                graph.add_edge(
                    s_id, r_id, stoichiometry=stoich, role="reversible_product"
                )

    return graph


def build_cytoscape_elements(
    graph: nx.DiGraph,
    layout_name: str = "cose",
    show_species: bool = True,
    show_reactions: bool = True,
    min_degree: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build Cytoscape.js elements and visual stylesheet from a NetworkX graph.

    Parameters
    ----------
    graph : nx.DiGraph
        The bipartite network graph generated by `build_network`.
    layout_name : str, default="cose"
        Cytoscape layout identifier (e.g., 'cose', 'circle', 'grid', 'breadthfirst').
    show_species : bool, default=True
        Whether to include species nodes.
    show_reactions : bool, default=True
        Whether to include reaction nodes.
    min_degree : int, default=0
        Minimum total node degree required for inclusion in the network view.

    Returns
    -------
    tuple of (elements, stylesheet)
        - `elements`: List of node and edge dictionaries formatted for Cytoscape.js.
        - `stylesheet`: List of CSS-like style definitions for Cytoscape rendering.
    """
    elements: list[dict[str, Any]] = []

    # 1. Filter and add Nodes
    valid_nodes: set[str] = set()
    for node_id, data in graph.nodes(data=True):
        node_type = data.get("node_type", "species")
        degree = graph.degree(node_id)

        # Apply visibility toggles and degree thresholds
        if node_type == "species" and not show_species:
            continue
        if node_type == "reaction" and not show_reactions:
            continue
        if degree < min_degree:
            continue

        valid_nodes.add(node_id)
        elements.append(
            {
                "data": {
                    "id": node_id,
                    "label": data.get("label", node_id),
                    "node_type": node_type,
                    "degree": degree,
                }
            }
        )

    # 2. Add Edges between valid nodes
    for source, target, data in graph.edges(data=True):
        if source in valid_nodes and target in valid_nodes:
            role = data.get("role", "reactant")
            stoich = data.get("stoichiometry", 1.0)

            if role == "modifier" or stoich is None:
                stoich_label = ""
            else:
                numeric_stoich = float(stoich)
                stoich_label = (
                    str(int(numeric_stoich))
                    if numeric_stoich == int(numeric_stoich)
                    else f"{numeric_stoich:.1f}"
                )
                if numeric_stoich == 1.0:
                    stoich_label = ""

            elements.append(
                {
                    "data": {
                        "id": f"{source}_{target}",
                        "source": source,
                        "target": target,
                        "label": stoich_label,
                        "role": role,
                    }
                }
            )

    # 3. Define Cytoscape Visual Stylesheet
    stylesheet = [
        # Base Node Style
        {
            "selector": "node",
            "style": {
                "label": "data(label)",
                "color": "#e0e0e0",
                "font-size": "12px",
                "text-valign": "center",
                "text-halign": "center",
                "text-background-opacity": 0,
            },
        },
        # Species Nodes (Terra / Reddish circle)
        {
            "selector": 'node[node_type = "species"]',
            "style": {
                "shape": "ellipse",
                "background-color": "#d96b43",
                "width": "36px",
                "height": "36px",
            },
        },
        # Reaction Nodes (Amber / Yellowish square)
        {
            "selector": 'node[node_type = "reaction"]',
            "style": {
                "shape": "rectangle",
                "background-color": "#e5a93c",
                "width": "24px",
                "height": "24px",
                "border-width": "1px",
                "border-color": "#ffffff",
            },
        },
        # Base Edge Style
        {
            "selector": "edge",
            "style": {
                "width": 2,
                "line-color": "#5c6370",
                "target-arrow-color": "#5c6370",
                "target-arrow-shape": "triangle",
                "curve-style": "bezier",
                "font-size": "10px",
                "color": "#abb2bf",
                "label": "data(label)",
            },
        },
        # Modifier edges (dotted)
        {
            "selector": 'edge[role = "modifier"]',
            "style": {
                "line-style": "dotted",
                "line-color": "#B46E8D",
                "target-arrow-color": "#B46E8D",
            },
        },
        # Reversible / Secondary Edges (Dashed)
        {
            "selector": 'edge[role ^= "reversible"]',
            "style": {
                "line-style": "dashed",
                "line-color": "#3b4048",
                "target-arrow-color": "#3b4048",
            },
        },
    ]

    return elements, stylesheet
