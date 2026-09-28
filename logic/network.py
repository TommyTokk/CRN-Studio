"""Network extraction and Cytoscape mapping for SBML Chemical Reaction Networks."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import libsbml
import networkx as nx
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ImportanceGraphAnnotations:
    """Store target-specific Shapley effects and highlighted network paths.

    Parameters
    ----------
    player_effects : dict of str to str
        Effect category for every knocked species.
    node_effects : dict of str to str
        Combined effect category for nodes on highlighted paths.
    edge_effects : dict of tuple of str to str
        Combined effect category for directed graph edges on highlighted paths.
    secondary_edges : frozenset of tuple of str
        Edges used only by fallback paths that ignore edge direction.
    secondary_players : tuple of str
        Players whose target connection required an undirected fallback path.
    unreachable_players : tuple of str
        Players disconnected from the target even when direction is ignored.

    Examples
    --------
    >>> result = ImportanceGraphAnnotations({}, {}, {}, frozenset(), (), ())
    >>> result.secondary_players
    ()
    """

    player_effects: dict[str, str]
    node_effects: dict[str, str]
    edge_effects: dict[tuple[str, str], str]
    secondary_edges: frozenset[tuple[str, str]]
    secondary_players: tuple[str, ...]
    unreachable_players: tuple[str, ...]


def build_importance_graph_annotations(
    graph: nx.DiGraph,
    target_id: str,
    shapley_scores: Mapping[str, float] | pd.Series,
    operation: str,
    neutral_atol: float = 1e-8,
) -> ImportanceGraphAnnotations:
    """Classify knock effects and find every shortest path to one target.

    Directed paths are preferred. When a player cannot reach the target while
    respecting edge direction, the function finds shortest paths in an undirected
    view and marks their edges as secondary. Path unions are derived from BFS
    distance maps, so equivalent paths are not enumerated individually.

    Parameters
    ----------
    graph : networkx.DiGraph
        Directed bipartite chemical-reaction network.
    target_id : str
        Species ID whose Shapley column is being visualized.
    shapley_scores : mapping of str to float or pandas.Series
        Raw Shapley values indexed by knocked species ID.
    operation : str
        Either ``knockout`` or ``knockin``.
    neutral_atol : float, default 1e-8
        Absolute magnitude at or below which an effect is neutral.

    Returns
    -------
    ImportanceGraphAnnotations
        Player classifications, path classifications, and fallback metadata.

    Raises
    ------
    TypeError
        If `graph` is not a directed NetworkX graph.
    ValueError
        If the target, operation, tolerance, or a player ID is invalid.

    Examples
    --------
    >>> graph = nx.DiGraph([("A", "R"), ("R", "B")])
    >>> result = build_importance_graph_annotations(
    ...     graph, "B", {"A": 2.0}, "knockout"
    ... )
    >>> result.player_effects["A"]
    'promoter'
    >>> result.edge_effects[("A", "R")]
    'promoter'
    """
    if not isinstance(graph, nx.DiGraph):
        raise TypeError("A directed NetworkX graph is required.")
    if target_id not in graph:
        raise ValueError(f"Unknown target node: {target_id}")
    if operation not in ("knockout", "knockin"):
        raise ValueError("Operation must be 'knockout' or 'knockin'.")
    if not np.isfinite(neutral_atol) or neutral_atol < 0:
        raise ValueError("Neutral tolerance must be finite and non-negative.")

    scores = dict(shapley_scores)
    unknown_players = [player for player in scores if player not in graph]
    if unknown_players:
        raise ValueError(f"Unknown player node: {unknown_players[0]}")

    player_effects: dict[str, str] = {}
    node_memberships: defaultdict[str, set[str]] = defaultdict(set)
    edge_memberships: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    edge_path_types: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    secondary_players: list[str] = []
    unreachable_players: list[str] = []

    reversed_graph = graph.reverse(copy=False)
    directed_to_target = nx.single_source_shortest_path_length(
        reversed_graph, target_id
    )
    undirected_graph = graph.to_undirected(as_view=True)
    undirected_to_target = nx.single_source_shortest_path_length(
        undirected_graph, target_id
    )

    for player, raw_value in scores.items():
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = float("nan")

        if not np.isfinite(value):
            player_effects[player] = "unavailable"
            continue
        if abs(value) <= neutral_atol:
            effect = "neutral"
        else:
            promotes_target = value > 0 if operation == "knockout" else value < 0
            effect = "promoter" if promotes_target else "inhibitor"
        player_effects[player] = effect

        if player == target_id:
            continue

        directed_distance = directed_to_target.get(player)
        if directed_distance is not None:
            from_player = nx.single_source_shortest_path_length(
                graph, player, cutoff=directed_distance
            )
            path_nodes = {
                node
                for node, source_distance in from_player.items()
                if node in directed_to_target
                and source_distance + directed_to_target[node] == directed_distance
            }
            path_edges = {
                (source, target)
                for source, target in graph.edges
                if source in from_player
                and target in directed_to_target
                and from_player[source] + 1 + directed_to_target[target]
                == directed_distance
            }
            path_type = "directed"
        else:
            fallback_distance = undirected_to_target.get(player)
            if fallback_distance is None:
                unreachable_players.append(player)
                continue
            secondary_players.append(player)
            from_player = nx.single_source_shortest_path_length(
                undirected_graph, player, cutoff=fallback_distance
            )
            path_nodes = {
                node
                for node, source_distance in from_player.items()
                if node in undirected_to_target
                and source_distance + undirected_to_target[node] == fallback_distance
            }
            path_edges = {
                (source, target)
                for source, target in graph.edges
                if (
                    source in from_player
                    and target in undirected_to_target
                    and from_player[source] + 1 + undirected_to_target[target]
                    == fallback_distance
                )
                or (
                    target in from_player
                    and source in undirected_to_target
                    and from_player[target] + 1 + undirected_to_target[source]
                    == fallback_distance
                )
            }
            path_type = "secondary"

        for node in path_nodes:
            node_memberships[node].add(effect)
        for edge in path_edges:
            edge_memberships[edge].add(effect)
            edge_path_types[edge].add(path_type)

    node_effects: dict[str, str] = {}
    for node, effects in node_memberships.items():
        if {"promoter", "inhibitor"}.issubset(effects):
            node_effects[node] = "mixed"
        elif "promoter" in effects:
            node_effects[node] = "promoter"
        elif "inhibitor" in effects:
            node_effects[node] = "inhibitor"
        else:
            node_effects[node] = "neutral"

    edge_effects: dict[tuple[str, str], str] = {}
    for edge, effects in edge_memberships.items():
        if {"promoter", "inhibitor"}.issubset(effects):
            edge_effects[edge] = "mixed"
        elif "promoter" in effects:
            edge_effects[edge] = "promoter"
        elif "inhibitor" in effects:
            edge_effects[edge] = "inhibitor"
        else:
            edge_effects[edge] = "neutral"

    secondary_edges = frozenset(
        edge
        for edge, path_types in edge_path_types.items()
        if path_types == {"secondary"}
    )
    return ImportanceGraphAnnotations(
        player_effects=player_effects,
        node_effects=node_effects,
        edge_effects=edge_effects,
        secondary_edges=secondary_edges,
        secondary_players=tuple(secondary_players),
        unreachable_players=tuple(unreachable_players),
    )


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
