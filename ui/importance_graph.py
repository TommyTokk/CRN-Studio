"""Cytoscape presentation helpers for target-specific importance graphs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import networkx as nx
import numpy as np
import streamlit as st

from logic.network import ImportanceGraphAnnotations
from ui.graph_interaction import install_graph_interaction_guard

try:
    from streamlit_cytoscape import EdgeStyle, Event, NodeStyle, streamlit_cytoscape

    HAS_CYTOSCAPE = True
    CYTOSCAPE_IMPORT_ERROR: Exception | None = None
except ImportError as error:
    HAS_CYTOSCAPE = False
    CYTOSCAPE_IMPORT_ERROR = error
    EdgeStyle = None  # type: ignore[assignment,misc]
    Event = None  # type: ignore[assignment,misc]
    NodeStyle = None  # type: ignore[assignment,misc]
    streamlit_cytoscape = None  # type: ignore[assignment]


LAYOUT_OPTIONS = ("Hierarchical", "Force-directed", "Circular", "Bipartite")


def build_importance_cytoscape_elements(
    graph: nx.DiGraph,
    annotations: ImportanceGraphAnnotations,
    target_id: str,
    shapley_scores: Mapping[str, float],
    operation: str,
    layout_name: str,
    focused_annotations: ImportanceGraphAnnotations | None = None,
    selected_player_id: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Convert a complete annotated network into Cytoscape elements.

    Parameters
    ----------
    graph : networkx.DiGraph
        Complete directed chemical-reaction network.
    annotations : ImportanceGraphAnnotations
        Target-specific effects and shortest-path annotations.
    target_id : str
        Species displayed as the current target.
    shapley_scores : mapping of str to float
        Raw target-column Shapley values indexed by knocked species.
    operation : str
        Cached importance operation, either ``knockout`` or ``knockin``.
    layout_name : str
        One of the supported values in `LAYOUT_OPTIONS`.
    focused_annotations : ImportanceGraphAnnotations, optional
        Path annotations calculated for the selected player only.
    selected_player_id : str, optional
        Knocked species whose complete shortest-path union is focused.

    Returns
    -------
    dict of str to list of dict
        Cytoscape nodes and edges, including preset positions for Bipartite.

    Raises
    ------
    ValueError
        If the target or layout is invalid.

    Examples
    --------
    >>> graph = nx.DiGraph([("A", "R"), ("R", "B")])
    >>> nx.set_node_attributes(graph, "species", "node_type")
    >>> graph.nodes["R"]["node_type"] = "reaction"
    >>> annotations = ImportanceGraphAnnotations(
    ...     {"A": "promoter"}, {"A": "promoter", "R": "promoter"},
    ...     {("A", "R"): "promoter"}, frozenset(), (), ()
    ... )
    >>> elements = build_importance_cytoscape_elements(
    ...     graph, annotations, "B", {"A": 2.0}, "knockout", "Hierarchical"
    ... )
    >>> elements["nodes"][0]["data"]["label"]
    'KNOCK_PROMOTER'
    """
    if target_id not in graph:
        raise ValueError(f"Unknown target node: {target_id}")
    if layout_name not in LAYOUT_OPTIONS:
        raise ValueError(f"Unsupported graph layout: {layout_name}")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    scores = dict(shapley_scores)
    effect_labels = {
        "promoter": "Promoter",
        "inhibitor": "Inhibitor",
        "neutral": "Neutral",
        "mixed": "Mixed",
        "unavailable": "N/A",
    }
    focus_active = focused_annotations is not None and selected_player_id is not None

    for node_id, node_data in graph.nodes(data=True):
        node_type = str(node_data.get("node_type", "species")).lower()
        node_kind = "REACTION" if node_type == "reaction" else "SPECIES"
        graph_label = str(node_data.get("label") or node_id)
        visible_name = (
            node_id if graph_label == node_id else f"{node_id} — {graph_label}"
        )
        player_effect = annotations.player_effects.get(node_id)
        path_effect = annotations.node_effects.get(node_id)

        focused_path_effect = (
            focused_annotations.node_effects.get(node_id)
            if focused_annotations is not None
            else None
        )

        if focus_active and node_id == selected_player_id:
            category = f"FOCUSED_KNOCK_{player_effect.upper()}"
            role = "Selected knocked species"
            effect = effect_labels[player_effect]
        elif node_id == target_id:
            category = "FOCUSED_TARGET" if focus_active else "TARGET"
            role = "Target species"
            effect = "Target"
        elif focus_active and focused_path_effect is not None:
            category = f"FOCUSED_PATH_{focused_path_effect.upper()}_{node_kind}"
            role = f"{node_kind.title()} on selected path"
            effect = effect_labels[focused_path_effect]
        elif player_effect is not None:
            prefix = "DIMMED_KNOCK" if focus_active else "KNOCK"
            category = f"{prefix}_{player_effect.upper()}"
            role = "Knocked species"
            effect = effect_labels[player_effect]
        elif path_effect is not None:
            prefix = "DIMMED_PATH" if focus_active else "PATH"
            category = f"{prefix}_{path_effect.upper()}_{node_kind}"
            role = f"{node_kind.title()} on highlighted path"
            effect = effect_labels[path_effect]
        else:
            category = f"BACKGROUND_{node_kind}"
            role = f"Background {node_kind.lower()}"
            effect = "Not highlighted"

        raw_score = scores.get(node_id)
        try:
            numeric_score = float(raw_score)
        except (TypeError, ValueError):
            numeric_score = float("nan")
        shapley_value = (
            f"{numeric_score:.8g}" if np.isfinite(numeric_score) else "N/A"
        )
        node = {
            "data": {
                "id": node_id,
                "label": category,
                "name": visible_name,
                "element_type": node_kind.title(),
                "role": role,
                "effect": effect,
                "shapley": shapley_value,
                "operation": "KO" if operation == "knockout" else "KI",
            }
        }
        if player_effect is not None:
            node["data"]["_is_knock"] = "true"
        nodes.append(node)

    for source, target, edge_data in graph.edges(data=True):
        edge = (source, target)
        effect = annotations.edge_effects.get(edge)
        focused_effect = (
            focused_annotations.edge_effects.get(edge)
            if focused_annotations is not None
            else None
        )
        role = str(edge_data.get("role", "connection"))
        if focus_active and focused_effect is not None:
            prefix = (
                "FOCUSED_SECONDARY"
                if edge in focused_annotations.secondary_edges
                else "FOCUSED_PATH"
            )
            category = f"{prefix}_{focused_effect.upper()}"
            path_type = (
                "Secondary undirected fallback"
                if prefix == "FOCUSED_SECONDARY"
                else "Directed shortest path"
            )
            effect_label = effect_labels[focused_effect]
        elif effect is None:
            if role == "modifier":
                category = "BACKGROUND_MODIFIER"
            elif role.startswith("reversible"):
                category = "BACKGROUND_REVERSIBLE"
            else:
                category = "BACKGROUND_EDGE"
            path_type = "Background"
            effect_label = "Not highlighted"
        else:
            if focus_active:
                prefix = (
                    "DIMMED_SECONDARY"
                    if edge in annotations.secondary_edges
                    else "DIMMED_PATH"
                )
            else:
                prefix = "SECONDARY" if edge in annotations.secondary_edges else "PATH"
            category = f"{prefix}_{effect.upper()}"
            path_type = (
                "Secondary undirected fallback"
                if "SECONDARY" in prefix
                else "Directed shortest path"
            )
            effect_label = effect_labels[effect]

        stoichiometry = edge_data.get("stoichiometry")
        stoichiometry_label = (
            "N/A" if stoichiometry is None else f"{float(stoichiometry):g}"
        )
        edges.append(
            {
                "data": {
                    "id": f"edge::{source}::{target}",
                    "source": source,
                    "target": target,
                    "label": category,
                    "role": role,
                    "effect": effect_label,
                    "path_type": path_type,
                    "stoichiometry": stoichiometry_label,
                }
            }
        )

    if layout_name == "Bipartite":
        species_nodes = [
            node
            for node in nodes
            if node["data"]["element_type"] == "Species"
        ]
        reaction_nodes = [
            node
            for node in nodes
            if node["data"]["element_type"] == "Reaction"
        ]
        for column_x, column_nodes in ((180.0, species_nodes), (860.0, reaction_nodes)):
            for index, node in enumerate(column_nodes):
                node["position"] = {
                    "x": column_x,
                    "y": (index - (len(column_nodes) - 1) / 2.0) * 120.0,
                }

    return {"nodes": nodes, "edges": edges}


def importance_cytoscape_styles(
    palette: Mapping[str, str],
) -> tuple[list[Any], list[Any]]:
    """Create themed Cytoscape styles for importance nodes and paths.

    Parameters
    ----------
    palette : mapping of str to str
        Active application theme palette.

    Returns
    -------
    tuple of list
        Node styles followed by edge styles. Both are empty when the optional
        Cytoscape component cannot be imported.

    Examples
    --------
    >>> styles = importance_cytoscape_styles({
    ...     "text": "#111111", "text_soft": "#555555", "plot_bg": "#ffffff",
    ...     "graph_species": "#008888", "graph_reaction": "#cc6600",
    ...     "graph_edge": "#777777", "graph_modifier": "#884466",
    ...     "positive": "#dd6644", "negative": "#448866", "amber": "#ccaa44",
    ...     "data_1": "#3366aa", "data_4": "#8844aa", "data_8": "#666666",
    ... })
    >>> len(styles) == 2
    True
    """
    if not HAS_CYTOSCAPE:
        return [], []

    common_node = {
        "width": 46,
        "height": 46,
        "border-width": 2,
        "border-color": palette["plot_bg"],
        "font-size": 12,
        "font-weight": 600,
        "color": palette["text"],
        "text-wrap": "wrap",
        "text-max-width": 150,
        "text-background-color": palette["plot_bg"],
        "text-background-opacity": 0.88,
        "text-background-padding": 4,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 7,
    }
    effect_colors = {
        "PROMOTER": palette["positive"],
        "INHIBITOR": palette["negative"],
        "NEUTRAL": palette["amber"],
        "MIXED": palette["data_4"],
        "UNAVAILABLE": palette["data_8"],
    }
    node_styles = [
        NodeStyle(
            label="BACKGROUND_SPECIES",
            color=palette["graph_species"],
            caption="name",
            custom_styles={
                **common_node,
                "shape": "ellipse",
                "opacity": 0.24,
                "text-opacity": 0.48,
            },
        ),
        NodeStyle(
            label="BACKGROUND_REACTION",
            color=palette["graph_reaction"],
            caption="name",
            custom_styles={
                **common_node,
                "shape": "diamond",
                "width": 40,
                "height": 40,
                "opacity": 0.24,
                "text-opacity": 0.48,
            },
        ),
        NodeStyle(
            label="TARGET",
            color=palette["data_1"],
            caption="name",
            custom_styles={
                **common_node,
                "shape": "ellipse",
                "width": 58,
                "height": 58,
                "border-width": 5,
                "border-color": palette["text"],
            },
        ),
        NodeStyle(
            label="FOCUSED_TARGET",
            color=palette["data_1"],
            caption="name",
            custom_styles={
                **common_node,
                "shape": "ellipse",
                "width": 62,
                "height": 62,
                "border-width": 6,
                "border-color": palette["text"],
            },
        ),
    ]
    for effect, color in effect_colors.items():
        knock_style = {
            **common_node,
            "shape": "ellipse",
            "width": 52,
            "height": 52,
            "border-width": 4,
            "border-color": palette["text"],
        }
        if effect == "UNAVAILABLE":
            knock_style["border-style"] = "dashed"
        node_styles.append(
            NodeStyle(
                label=f"KNOCK_{effect}",
                color=color,
                caption="name",
                custom_styles=knock_style,
            )
        )
        node_styles.extend(
            [
                NodeStyle(
                    label=f"FOCUSED_KNOCK_{effect}",
                    color=color,
                    caption="name",
                    custom_styles={
                        **knock_style,
                        "width": 60,
                        "height": 60,
                        "border-width": 6,
                    },
                ),
                NodeStyle(
                    label=f"DIMMED_KNOCK_{effect}",
                    color=color,
                    caption="name",
                    custom_styles={
                        **knock_style,
                        "opacity": 0.2,
                        "text-opacity": 0.35,
                    },
                ),
            ]
        )
        if effect != "UNAVAILABLE":
            node_styles.extend(
                [
                    NodeStyle(
                        label=f"PATH_{effect}_SPECIES",
                        color=color,
                        caption="name",
                        custom_styles={**common_node, "shape": "ellipse"},
                    ),
                    NodeStyle(
                        label=f"PATH_{effect}_REACTION",
                        color=color,
                        caption="name",
                        custom_styles={
                            **common_node,
                            "shape": "diamond",
                            "width": 40,
                            "height": 40,
                        },
                    ),
                    NodeStyle(
                        label=f"FOCUSED_PATH_{effect}_SPECIES",
                        color=color,
                        caption="name",
                        custom_styles={
                            **common_node,
                            "shape": "ellipse",
                            "border-width": 4,
                            "border-color": palette["text"],
                        },
                    ),
                    NodeStyle(
                        label=f"FOCUSED_PATH_{effect}_REACTION",
                        color=color,
                        caption="name",
                        custom_styles={
                            **common_node,
                            "shape": "diamond",
                            "width": 44,
                            "height": 44,
                            "border-width": 4,
                            "border-color": palette["text"],
                        },
                    ),
                    NodeStyle(
                        label=f"DIMMED_PATH_{effect}_SPECIES",
                        color=color,
                        caption="name",
                        custom_styles={
                            **common_node,
                            "shape": "ellipse",
                            "opacity": 0.14,
                            "text-opacity": 0.28,
                        },
                    ),
                    NodeStyle(
                        label=f"DIMMED_PATH_{effect}_REACTION",
                        color=color,
                        caption="name",
                        custom_styles={
                            **common_node,
                            "shape": "diamond",
                            "width": 40,
                            "height": 40,
                            "opacity": 0.14,
                            "text-opacity": 0.28,
                        },
                    ),
                ]
            )

    background_edge = {"width": 1.5, "opacity": 0.18, "arrow-scale": 0.75}
    edge_styles = [
        EdgeStyle(
            label="BACKGROUND_EDGE",
            color=palette["graph_edge"],
            directed=True,
            curve_style="bezier",
            custom_styles=background_edge,
        ),
        EdgeStyle(
            label="BACKGROUND_REVERSIBLE",
            color=palette["graph_edge"],
            directed=True,
            curve_style="bezier",
            custom_styles={**background_edge, "line-style": "dashed"},
        ),
        EdgeStyle(
            label="BACKGROUND_MODIFIER",
            color=palette["graph_modifier"],
            directed=True,
            curve_style="bezier",
            custom_styles={**background_edge, "line-style": "dotted"},
        ),
    ]
    for effect, color in effect_colors.items():
        if effect == "UNAVAILABLE":
            continue
        edge_styles.extend(
            [
                EdgeStyle(
                    label=f"PATH_{effect}",
                    color=color,
                    directed=True,
                    curve_style="bezier",
                    custom_styles={"width": 4, "opacity": 0.94, "arrow-scale": 1},
                ),
                EdgeStyle(
                    label=f"SECONDARY_{effect}",
                    color=color,
                    directed=True,
                    curve_style="bezier",
                    custom_styles={
                        "width": 4,
                        "opacity": 0.9,
                        "arrow-scale": 1,
                        "line-style": "dashed",
                    },
                ),
                EdgeStyle(
                    label=f"FOCUSED_PATH_{effect}",
                    color=color,
                    directed=True,
                    curve_style="bezier",
                    custom_styles={"width": 6, "opacity": 1, "arrow-scale": 1.15},
                ),
                EdgeStyle(
                    label=f"FOCUSED_SECONDARY_{effect}",
                    color=color,
                    directed=True,
                    curve_style="bezier",
                    custom_styles={
                        "width": 6,
                        "opacity": 1,
                        "arrow-scale": 1.15,
                        "line-style": "dashed",
                    },
                ),
                EdgeStyle(
                    label=f"DIMMED_PATH_{effect}",
                    color=color,
                    directed=True,
                    curve_style="bezier",
                    custom_styles={
                        "width": 2,
                        "opacity": 0.12,
                        "arrow-scale": 0.75,
                    },
                ),
                EdgeStyle(
                    label=f"DIMMED_SECONDARY_{effect}",
                    color=color,
                    directed=True,
                    curve_style="bezier",
                    custom_styles={
                        "width": 2,
                        "opacity": 0.12,
                        "arrow-scale": 0.75,
                        "line-style": "dashed",
                    },
                ),
            ]
        )
    return node_styles, edge_styles


def importance_layout_config(layout_name: str, node_count: int) -> dict[str, Any]:
    """Return a Cytoscape layout configuration for the selected view.

    Parameters
    ----------
    layout_name : str
        One of the supported values in `LAYOUT_OPTIONS`.
    node_count : int
        Number of graph nodes used to tune spacing.

    Returns
    -------
    dict
        Cytoscape.js layout configuration.

    Raises
    ------
    ValueError
        If `layout_name` is unsupported.

    Examples
    --------
    >>> importance_layout_config("Hierarchical", 10)["name"]
    'breadthfirst'
    """
    if layout_name not in LAYOUT_OPTIONS:
        raise ValueError(f"Unsupported graph layout: {layout_name}")
    spacing = 2.2 if node_count >= 35 else 1.7
    padding = 60 if node_count >= 35 else 45
    if layout_name == "Hierarchical":
        return {
            "name": "breadthfirst",
            "directed": True,
            "circle": False,
            "grid": False,
            "fit": True,
            "padding": padding,
            "spacingFactor": spacing,
            "avoidOverlap": True,
            "nodeDimensionsIncludeLabels": True,
        }
    if layout_name == "Circular":
        return {
            "name": "circle",
            "fit": True,
            "padding": padding,
            "spacingFactor": spacing,
            "avoidOverlap": True,
            "nodeDimensionsIncludeLabels": True,
        }
    if layout_name == "Bipartite":
        return {"name": "preset", "fit": True, "padding": padding, "animate": False}
    return {
        "name": "fcose",
        "fit": True,
        "padding": padding,
        "animate": False,
        "randomize": True,
        "nodeRepulsion": 18000 if node_count >= 35 else 12000,
        "idealEdgeLength": 160 if node_count >= 35 else 135,
        "nodeDimensionsIncludeLabels": True,
        "tile": True,
    }


def render_importance_graph(
    graph: nx.DiGraph,
    annotations: ImportanceGraphAnnotations,
    target_id: str,
    shapley_scores: Mapping[str, float],
    operation: str,
    layout_name: str,
    palette: Mapping[str, str],
    component_key: str,
    focused_annotations: ImportanceGraphAnnotations | None = None,
    selected_player_id: str | None = None,
) -> dict[str, Any] | None:
    """Render one interactive target-specific Cytoscape graph.

    Parameters
    ----------
    graph : networkx.DiGraph
        Complete directed chemical-reaction network.
    annotations : ImportanceGraphAnnotations
        Target-specific effects and paths.
    target_id : str
        Selected target species ID.
    shapley_scores : mapping of str to float
        Raw Shapley values for the selected target.
    operation : str
        Cached importance operation.
    layout_name : str
        Selected graph layout.
    palette : mapping of str to str
        Active application theme palette.
    component_key : str
        Stable Streamlit component key.
    focused_annotations : ImportanceGraphAnnotations, optional
        Annotations restricted to the currently selected knock.
    selected_player_id : str, optional
        Currently selected knocked species.

    Returns
    -------
    dict or None
        Cytoscape event payload, or None when no event was emitted or the
        optional component is unavailable.

    Examples
    --------
    >>> render_importance_graph(  # doctest: +SKIP
    ...     graph, annotations, "B", {"A": 2.0}, "knockout",
    ...     "Hierarchical", palette, "importance_graph"
    ... )
    None
    """
    if not HAS_CYTOSCAPE:
        st.error(
            "The Cytoscape component is unavailable, so the target influence "
            "network cannot be rendered. The numerical analysis remains available."
        )
        if CYTOSCAPE_IMPORT_ERROR is not None:
            st.caption(f"Import error: {CYTOSCAPE_IMPORT_ERROR}")
        return None

    elements = build_importance_cytoscape_elements(
        graph,
        annotations,
        target_id,
        shapley_scores,
        operation,
        layout_name,
        focused_annotations,
        selected_player_id,
    )
    node_styles, edge_styles = importance_cytoscape_styles(palette)
    event = streamlit_cytoscape(
        elements=elements,
        layout=importance_layout_config(layout_name, len(elements["nodes"])),
        node_styles=node_styles,
        edge_styles=edge_styles,
        height=620,
        key=component_key,
        events=[Event("importance_knock_tap", "tap", "node[_is_knock = 'true']")],
        hide_underscore_attrs=True,
    )
    install_graph_interaction_guard(
        component_key,
        palette,
        infopanel_title_field="name",
        managed_selected_node_id=selected_player_id,
    )
    return dict(event) if isinstance(event, Mapping) else None
