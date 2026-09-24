"""Page 1 — Model Overview & Network Graph.

This file is a page body only. The shared Streamlit shell (theme, sidebar,
workspace topbar, and global CSS) lives in ``app.py`` and is executed before
every page through ``st.navigation``.
"""

from __future__ import annotations

import hashlib
from typing import Any

import streamlit as st
import streamlit.components.v1 as st_components

try:
    from streamlit_cytoscape import EdgeStyle, NodeStyle, streamlit_cytoscape

    HAS_CYTOSCAPE = True
    CYTOSCAPE_IMPORT_ERROR: Exception | None = None
except ImportError as error:
    HAS_CYTOSCAPE = False
    CYTOSCAPE_IMPORT_ERROR = error
    EdgeStyle = None  # type: ignore[assignment,misc]
    NodeStyle = None  # type: ignore[assignment,misc]
    streamlit_cytoscape = None  # type: ignore[assignment]

from logic.model import (
    get_reactions_dataframe,
    get_species_dataframe,
    load_model,
    model_summary,
)
from logic.network import (
    build_cytoscape_elements,
    build_network,
    format_stoichiometric_matrix_display,
    get_stoichiometric_matrix,
)
from ui.components import (
    page_header,
    panel_heading,
    placeholder,
    stat_card,
)
from ui.model_library import (
    begin_uploader_generation,
    ensure_model_library,
    sync_uploaded_models,
)

# Used to request exactly one extra rerun when the active parsed model changes.
# The app shell/sidebar executes before this page body, so without this handshake
# the sidebar would display the previous model's statistics until another widget
# happened to trigger a rerun.
_SIDEBAR_SYNC_SIGNATURE_KEY = "_shapcrn_sidebar_sync_signature"


# -----------------------------------------------------------------------------
# Cytoscape adapter
# -----------------------------------------------------------------------------

# Simplified graph palette: one visual class for all species, one for reactions.
GRAPH_PALETTE = {
    "surface": "#FFFFFF",
    "text": "#403A48",
    "edge": "#CFC1C8",
    "reaction": "#F5A77A",
    "species": "#73B8BA",
    "modifier": "#B46E8D",
    "other": "#AAA2B2",
}


def _column_y(index: int, count: int, spacing: float = 120.0) -> float:
    """Return a centered y-coordinate for one node in a vertical column."""
    if count <= 1:
        return 0.0
    return (index - (count - 1) / 2.0) * spacing


def _cytoscape_component_key(
    layout_name: str, raw_elements: list[dict[str, Any]]
) -> str:
    """Return a stable Cytoscape key for the current model/topology.

    A new model must mount a fresh Cytoscape frontend instance. Reusing the same
    Streamlit component key across unrelated graphs lets Cytoscape retain positions
    and internal element state from the previous model, which can make the new
    force-directed graph collapse. Visibility toggles are deliberately excluded
    from the key so hiding/showing one CRN partition does not remount the canvas.
    """
    model_bytes = st.session_state.get("shapcrn_model_bytes")

    if isinstance(model_bytes, (bytes, bytearray)) and model_bytes:
        model_signature = hashlib.sha1(bytes(model_bytes)).hexdigest()[:12]
    else:
        # Defensive fallback for models loaded by another page/source. Include
        # node/edge identity so unrelated topologies cannot share frontend state.
        tokens: list[str] = []
        for element in raw_elements:
            data = element.get("data", {})
            if "source" in data and "target" in data:
                tokens.append(
                    f"e:{data.get('source')}->{data.get('target')}:{data.get('role', '')}"
                )
            else:
                tokens.append(
                    f"n:{data.get('id')}:{data.get('label', '')}:{data.get('node_type', '')}"
                )
        model_signature = hashlib.sha1(
            "|".join(sorted(tokens)).encode("utf-8")
        ).hexdigest()[:12]

    layout_signature = layout_name.lower().replace("-", "_").replace(" ", "_")
    return f"crn_cytoscape_canvas_{model_signature}_{layout_signature}"


def _node_category(graph: Any, node_id: str, node_type: str) -> str:
    """Return the two visual node classes used by the graph.

    Species are deliberately not split into reactant/product/modifier classes. A
    species can participate in different roles across reactions, so role-specific
    node colours are misleading and make the network harder to scan.
    """
    return "REACTION" if node_type == "reaction" else "SPECIES"


def _prepare_cytoscape_elements(
    raw_elements: list[dict[str, Any]],
    graph: Any,
    *,
    show_species: bool,
    show_reactions: bool,
    bipartite_layout: bool,
) -> dict[str, list[dict[str, Any]]]:
    """Adapt generic Cytoscape elements to ``streamlit-cytoscape``.

    Visibility toggles intentionally DO NOT remove nodes from the element list.
    A CRN is bipartite: if one partition is physically removed, every remaining
    node becomes isolated and force layouts collapse into a pile.  Hidden nodes
    therefore remain as transparent layout anchors while their incident edges
    are hidden too.  This keeps the current graph geometry stable when either
    node-type toggle is changed.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    visible_by_id: dict[str, bool] = {}

    # Nodes first so edge visibility can be derived from both endpoints.
    for element in raw_elements:
        data = dict(element.get("data", {}))
        if not data or "source" in data or "target" in data:
            continue

        node_id = str(data.get("id", ""))
        node_type = str(data.get("node_type", "species")).lower()
        visible_name = str(data.get("label") or node_id)
        category = _node_category(graph, node_id, node_type)
        is_visible = show_reactions if node_type == "reaction" else show_species

        data["name"] = visible_name
        data["category"] = category
        data["label"] = category if is_visible else f"HIDDEN_{node_type.upper()}"
        visible_by_id[node_id] = is_visible
        nodes.append({"data": data})

    for element in raw_elements:
        data = dict(element.get("data", {}))
        if not data or "source" not in data or "target" not in data:
            continue

        source = str(data.get("source", ""))
        target = str(data.get("target", ""))
        role = str(data.get("role", "reactant"))
        stoichiometry_label = str(data.get("label", ""))
        edge_visible = visible_by_id.get(source, False) and visible_by_id.get(
            target, False
        )

        data["stoichiometry"] = stoichiometry_label
        if not edge_visible:
            data["label"] = "HIDDEN_EDGE"
        elif role.startswith("reversible"):
            data["label"] = "REVERSIBLE"
        elif role == "modifier":
            data["label"] = "MODIFIER_EDGE"
        else:
            data["label"] = "CONNECTION"
        edges.append({"data": data})

    if bipartite_layout and nodes:
        # Hidden nodes are deliberately included here as layout anchors.
        species_nodes = [
            node for node in nodes if node["data"].get("category") != "REACTION"
        ]
        reaction_nodes = [
            node for node in nodes if node["data"].get("category") == "REACTION"
        ]

        for index, node in enumerate(species_nodes):
            node["position"] = {
                "x": 180.0,
                "y": _column_y(index, len(species_nodes)),
            }

        for index, node in enumerate(reaction_nodes):
            node["position"] = {
                "x": 860.0,
                "y": _column_y(index, len(reaction_nodes)),
            }

    return {"nodes": nodes, "edges": edges}


def _cytoscape_styles() -> tuple[list[Any], list[Any]]:
    """Return the reference-viewer Cytoscape style for this page."""
    if not HAS_CYTOSCAPE:
        return [], []

    common_node_style = {
        "width": 48,
        "height": 48,
        "border-width": 2,
        "border-color": "#FFFFFF",
        "font-size": 12,
        "font-weight": 600,
        "color": GRAPH_PALETTE["text"],
        "text-wrap": "wrap",
        "text-max-width": 150,
        "text-background-color": GRAPH_PALETTE["surface"],
        "text-background-opacity": 0.90,
        "text-background-padding": 4,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 7,
    }

    node_styles = [
        NodeStyle(
            label="REACTION",
            color=GRAPH_PALETTE["reaction"],
            caption="name",
            custom_styles={
                **common_node_style,
                "shape": "diamond",
                "width": 52,
                "height": 52,
            },
        ),
        NodeStyle(
            label="SPECIES",
            color=GRAPH_PALETTE["species"],
            caption="name",
            custom_styles={**common_node_style, "shape": "ellipse"},
        ),
        # Keep hidden partitions in Cytoscape's layout calculation without
        # displaying them. This prevents the species/reaction toggle collapse bug.
        NodeStyle(
            label="HIDDEN_SPECIES",
            color=GRAPH_PALETTE["other"],
            caption=None,
            custom_styles={
                **common_node_style,
                "shape": "ellipse",
                "opacity": 0.001,
                "text-opacity": 0,
                "border-opacity": 0,
                "events": "no",
            },
        ),
        NodeStyle(
            label="HIDDEN_REACTION",
            color=GRAPH_PALETTE["other"],
            caption=None,
            custom_styles={
                **common_node_style,
                "shape": "diamond",
                "width": 52,
                "height": 52,
                "opacity": 0.001,
                "text-opacity": 0,
                "border-opacity": 0,
                "events": "no",
            },
        ),
    ]

    common_edge_style = {
        "width": 2,
        "opacity": 0.82,
        "arrow-scale": 0.9,
    }

    edge_styles = [
        EdgeStyle(
            label="CONNECTION",
            color=GRAPH_PALETTE["edge"],
            directed=True,
            curve_style="bezier",
            custom_styles=common_edge_style,
        ),
        EdgeStyle(
            label="REVERSIBLE",
            color=GRAPH_PALETTE["edge"],
            directed=True,
            curve_style="bezier",
            custom_styles={**common_edge_style, "line-style": "dashed"},
        ),
        EdgeStyle(
            label="MODIFIER_EDGE",
            color=GRAPH_PALETTE["modifier"],
            directed=True,
            curve_style="bezier",
            custom_styles={**common_edge_style, "line-style": "dotted"},
        ),
        EdgeStyle(
            label="HIDDEN_EDGE",
            color=GRAPH_PALETTE["edge"],
            directed=False,
            curve_style="bezier",
            custom_styles={"width": 2, "opacity": 0.0, "events": "no"},
        ),
    ]

    return node_styles, edge_styles


def _layout_config(layout_name: str, node_count: int = 0) -> dict[str, Any]:
    """Return Cytoscape layout settings with extra room for larger networks.

    The spacing grows with the number of nodes so dense CRNs do not collapse into
    an unreadable cluster.  The values are intentionally conservative for small
    models and become progressively more spacious for medium/large models.
    """
    if node_count >= 80:
        spacing_factor = 2.6
        repulsion = 24000
        ideal_edge_length = 190
        padding = 70
    elif node_count >= 35:
        spacing_factor = 2.25
        repulsion = 18000
        ideal_edge_length = 160
        padding = 60
    else:
        spacing_factor = 1.9
        repulsion = 12000
        ideal_edge_length = 135
        padding = 50

    if layout_name == "Bipartite":
        # Positions are assigned explicitly in _prepare_cytoscape_elements().
        return {
            "name": "preset",
            "fit": True,
            "padding": padding,
            "animate": False,
        }

    if layout_name == "Circular":
        return {
            "name": "circle",
            "padding": padding,
            "fit": True,
            "avoidOverlap": True,
            "nodeDimensionsIncludeLabels": True,
            "spacingFactor": spacing_factor,
        }

    if layout_name == "Hierarchical":
        return {
            "name": "breadthfirst",
            "directed": True,
            "circle": False,
            "grid": False,
            "spacingFactor": spacing_factor,
            "padding": padding,
            "fit": True,
            "avoidOverlap": True,
            "nodeDimensionsIncludeLabels": True,
        }

    return {
        "name": "fcose",
        "padding": padding,
        "fit": True,
        "animate": False,
        "randomize": True,
        "nodeRepulsion": repulsion,
        "idealEdgeLength": ideal_edge_length,
        "edgeElasticity": 0.35,
        "nodeDimensionsIncludeLabels": True,
        "tile": True,
        "tilingPaddingVertical": 24,
        "tilingPaddingHorizontal": 24,
    }


def _install_graph_interaction_guard(component_key: str) -> None:
    """Install a click-to-enter shield over the Cytoscape component.

    The shield, not the Cytoscape iframe, owns the pointer while the graph is
    locked.  That distinction is important: wheel/trackpad events then belong to
    the Streamlit page, so scrolling over the graph scrolls the page instead of
    zooming Cytoscape.

    The shield is visually transparent until hovered.  Hovering reveals the
    "Click to enter graph view" message; clicking removes the shield from pointer
    hit-testing and exposes the graph with all of its normal interactions.  A small
    "Lock graph" control restores the shield without causing a Streamlit rerun.
    """
    guard_token = hashlib.sha1(component_key.encode("utf-8")).hexdigest()[:12]

    st_components.html(
        f"""
        <script>
        (() => {{
            const TOKEN = '{guard_token}';
            const OVERLAY_ID = 'shapcrn-graph-overlay-' + TOKEN;
            const LOCK_ID = 'shapcrn-graph-lock-' + TOKEN;
            const STATE_ATTR = 'data-shapcrn-graph-state-' + TOKEN;

            const install = (attempt = 0) => {{
                try {{
                    const doc = window.parent.document;
                    const helperFrame = window.frameElement;
                    if (!doc || !helperFrame) return;

                    /*
                     * This helper component is rendered immediately after
                     * Cytoscape. Find the nearest earlier iframe that has graph-
                     * sized dimensions. The retry handles the short interval in
                     * which Streamlit has mounted the iframe but has not sized it.
                     */
                    const frames = Array.from(doc.querySelectorAll('iframe'));
                    const helperIndex = frames.indexOf(helperFrame);
                    let graphFrame = null;

                    if (helperIndex > 0) {{
                        for (let i = helperIndex - 1; i >= 0; i -= 1) {{
                            const candidate = frames[i];
                            if (candidate === helperFrame) continue;

                            const rect = candidate.getBoundingClientRect();
                            if (rect.width >= 300 && rect.height >= 300) {{
                                graphFrame = candidate;
                                break;
                            }}
                        }}
                    }}

                    if (!graphFrame) {{
                        if (attempt < 20) {{
                            window.setTimeout(() => install(attempt + 1), 100);
                        }}
                        return;
                    }}

                    /*
                     * Use the iframe's immediate wrapper.  This avoids depending
                     * on private Streamlit test IDs, which have changed between
                     * Streamlit releases.
                     */
                    const host = graphFrame.parentElement;
                    if (!host) return;

                    const computed = window.getComputedStyle(host);
                    if (computed.position === 'static') {{
                        host.style.position = 'relative';
                    }}
                    host.style.isolation = 'isolate';

                    /* Remove guards from older graph/model tokens on this host. */
                    host.querySelectorAll('[data-shapcrn-graph-guard="true"]').forEach((el) => {{
                        if (el.id !== OVERLAY_ID && el.id !== LOCK_ID) el.remove();
                    }});

                    let overlay = host.querySelector('#' + OVERLAY_ID);
                    let lockButton = host.querySelector('#' + LOCK_ID);

                    const isUnlocked = () => host.getAttribute(STATE_ATTR) === 'unlocked';

                    if (!overlay) {{
                        overlay = doc.createElement('div');
                        overlay.id = OVERLAY_ID;
                        overlay.setAttribute('data-shapcrn-graph-guard', 'true');
                        overlay.setAttribute('role', 'button');
                        overlay.setAttribute('tabindex', '0');
                        overlay.setAttribute('aria-label', 'Click to enter graph view');

                        Object.assign(overlay.style, {{
                            position: 'absolute',
                            inset: '0',
                            zIndex: '2147483000',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            cursor: 'pointer',
                            borderRadius: '10px',
                            background: 'rgba(255,255,255,0)',
                            opacity: '0',
                            visibility: 'visible',
                            pointerEvents: 'auto',
                            transition: 'opacity 130ms ease, background 130ms ease',
                            touchAction: 'pan-y',
                            boxSizing: 'border-box'
                        }});

                        const message = doc.createElement('div');
                        message.innerHTML = `
                            <div style="
                                display:flex;
                                align-items:center;
                                gap:8px;
                                padding:10px 15px;
                                border:1px solid rgba(232,221,216,.96);
                                border-radius:999px;
                                background:rgba(255,255,255,.94);
                                color:#403A48;
                                font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                                font-size:13px;
                                font-weight:650;
                                line-height:1;
                                box-shadow:0 8px 24px rgba(78,57,72,.10);
                                backdrop-filter:blur(8px);
                                -webkit-backdrop-filter:blur(8px);
                                pointer-events:none;
                                user-select:none;
                            ">
                                <span style="font-size:15px;">⌖</span>
                                <span>Click to enter graph view</span>
                            </div>
                        `;
                        overlay.appendChild(message);
                        host.appendChild(overlay);
                    }}

                    if (!lockButton) {{
                        lockButton = doc.createElement('button');
                        lockButton.id = LOCK_ID;
                        lockButton.type = 'button';
                        lockButton.setAttribute('data-shapcrn-graph-guard', 'true');
                        lockButton.setAttribute('aria-label', 'Lock graph view');
                        lockButton.textContent = '🔒 Lock graph';

                        Object.assign(lockButton.style, {{
                            position: 'absolute',
                            top: '12px',
                            right: '12px',
                            zIndex: '2147483001',
                            display: 'none',
                            border: '1px solid #E8DDD8',
                            borderRadius: '999px',
                            padding: '7px 11px',
                            background: 'rgba(255,255,255,.95)',
                            color: '#403A48',
                            fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
                            fontSize: '12px',
                            fontWeight: '650',
                            lineHeight: '1',
                            boxShadow: '0 5px 16px rgba(78,57,72,.10)',
                            cursor: 'pointer',
                            backdropFilter: 'blur(7px)',
                            WebkitBackdropFilter: 'blur(7px)'
                        }});
                        host.appendChild(lockButton);
                    }}

                    const lock = () => {{
                        host.setAttribute(STATE_ATTR, 'locked');

                        /*
                         * Do NOT disable pointer events on the iframe itself.
                         * The transparent shield sits above it and catches the
                         * mouse. Wheel events therefore remain in the parent page
                         * and naturally scroll Streamlit.
                         */
                        overlay.style.pointerEvents = 'auto';
                        overlay.style.opacity = '0';
                        overlay.style.background = 'rgba(255,255,255,0)';
                        lockButton.style.display = 'none';
                    }};

                    const unlock = () => {{
                        host.setAttribute(STATE_ATTR, 'unlocked');
                        overlay.style.opacity = '0';
                        overlay.style.background = 'rgba(255,255,255,0)';
                        overlay.style.pointerEvents = 'none';
                        lockButton.style.display = 'block';
                    }};

                    if (overlay.getAttribute('data-bound') !== 'true') {{
                        overlay.setAttribute('data-bound', 'true');

                        overlay.addEventListener('mouseenter', () => {{
                            if (isUnlocked()) return;
                            overlay.style.opacity = '1';
                            overlay.style.background = 'rgba(255,255,255,.08)';
                        }});

                        overlay.addEventListener('mouseleave', () => {{
                            if (isUnlocked()) return;
                            overlay.style.opacity = '0';
                            overlay.style.background = 'rgba(255,255,255,0)';
                        }});

                        overlay.addEventListener('click', (event) => {{
                            event.preventDefault();
                            event.stopPropagation();
                            unlock();
                        }});

                        overlay.addEventListener('keydown', (event) => {{
                            if (event.key === 'Enter' || event.key === ' ') {{
                                event.preventDefault();
                                unlock();
                            }}
                        }});
                    }}

                    if (lockButton.getAttribute('data-bound') !== 'true') {{
                        lockButton.setAttribute('data-bound', 'true');
                        lockButton.addEventListener('click', (event) => {{
                            event.preventDefault();
                            event.stopPropagation();
                            lock();
                        }});
                    }}

                    /*
                     * A new component key/token starts locked. Re-executions of
                     * the helper for the same graph keep the user's current state.
                     */
                    if (isUnlocked()) {{
                        unlock();
                    }} else {{
                        lock();
                    }}
                }} catch (error) {{
                    console.debug('ShapCRN graph interaction guard:', error);
                }}
            }};

            install();
        }})();
        </script>
        """,
        height=0,
        width=0,
        scrolling=False,
    )


def _graph_legend() -> None:
    """Render the simplified species/reaction node legend."""
    st.markdown(
        f"""
        <div style="display:flex;flex-wrap:wrap;gap:.55rem 1rem;align-items:center;
                    padding:.55rem .7rem;margin:.15rem 0 .75rem 0;
                    border:1px solid #E8DDD8;border-radius:10px;background:#FFFFFF;">
          <span style="display:inline-flex;align-items:center;gap:.38rem;font-size:.76rem;color:#403A48;font-weight:600;">
            <span style="width:10px;height:10px;border-radius:50%;display:inline-block;background:{GRAPH_PALETTE["species"]};"></span>Species
          </span>
          <span style="display:inline-flex;align-items:center;gap:.38rem;font-size:.76rem;color:#403A48;font-weight:600;">
            <span style="width:10px;height:10px;display:inline-block;transform:rotate(45deg);background:{GRAPH_PALETTE["reaction"]};"></span>Reaction
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _get_loaded_model() -> Any | None:
    return st.session_state.get("shapcrn_loaded_model")


# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------

page_header(
    eyebrow="Topology & systems biology engine",
    title="CRN Model Overview & Topology Explorer",
    subtitle=(
        "Upload and inspect SBML/XML chemical reaction network models, structural "
        "conservation relations, and interactive bipartite topology."
    ),
    status="Parser Ready · libSBML",
)


# -----------------------------------------------------------------------------
# Model input
# -----------------------------------------------------------------------------

upload_col, _ = st.columns([3.6, 1.25], gap="large")
with upload_col:
    input_panel = st.container(border=True)
    with input_panel:
        panel_heading("Upload Bio-Model", "SBML / XML / JSON", "⇧")

        begin_uploader_generation()
        uploaded_files = st.file_uploader(
            "Model files",
            type=["xml", "sbml", "json"],
            accept_multiple_files=True,
            key="shapcrn_model_upload_queue",
            label_visibility="collapsed",
            help=(
                "Add one or more models. Use the × beside a file to remove it "
                "from the current upload batch."
            ),
        )

        sync_uploaded_models(uploaded_files)
        model_library = ensure_model_library()

        if model_library:
            model_word = "model" if len(model_library) == 1 else "models"
            st.success(f"{len(model_library)} {model_word} available in this session.")

            try:
                model_bytes = st.session_state.get("shapcrn_model_bytes")
                if not model_bytes:
                    raise ValueError(
                        "The selected model does not contain readable data."
                    )

                model = load_model(model_bytes)
                summary = model_summary(model)

                st.session_state["shapcrn_model_summary"] = summary
                st.session_state["shapcrn_loaded_model"] = model

                # The persistent app shell renders before this page.  When the
                # active model changes, request one additional rerun *after* the
                # authoritative summary has been stored so the sidebar can read
                # the fresh values at the beginning of the next run.
                sidebar_signature = (
                    st.session_state.get("shapcrn_model_name"),
                    summary.get("num_species"),
                    summary.get("num_reactions"),
                    summary.get("num_compartments"),
                )
                if (
                    st.session_state.get(_SIDEBAR_SYNC_SIGNATURE_KEY)
                    != sidebar_signature
                ):
                    st.session_state[_SIDEBAR_SYNC_SIGNATURE_KEY] = sidebar_signature
                    st.rerun()

            except ValueError as error:
                st.error(str(error))
                st.session_state["shapcrn_model_summary"] = None
                st.session_state.pop("shapcrn_loaded_model", None)

        else:
            # Avoid showing a stale graph/sidebar after the last model has been
            # removed.  A second controlled rerun lets the persistent shell see
            # the cleared state immediately.
            had_synced_model = (
                st.session_state.get(_SIDEBAR_SYNC_SIGNATURE_KEY) is not None
            )

            st.session_state.pop("shapcrn_model_summary", None)
            st.session_state.pop("shapcrn_loaded_model", None)
            st.session_state[_SIDEBAR_SYNC_SIGNATURE_KEY] = None

            if had_synced_model:
                st.rerun()

            st.caption(
                "Drag and drop one or more network models here · use + to add "
                "additional files"
            )


# -----------------------------------------------------------------------------
# Model statistics
# -----------------------------------------------------------------------------

st.write("")
summary_data = st.session_state.get("shapcrn_model_summary")

if summary_data:
    num_species = summary_data.get("num_species", 0)
    num_compartments = summary_data.get("num_compartments", 1)

    num_reactions = summary_data.get("num_reactions", 0)
    num_reversible = summary_data.get("num_reversible_reactions", 0)
    num_irreversible = max(0, num_reactions - num_reversible)

    num_complexes = summary_data.get("num_complexes", "—")
    deficiency = summary_data.get("deficiency", "—")
    rank = summary_data.get("rank", "—")

    num_conservation_laws = summary_data.get("num_conservation_laws")
    if num_conservation_laws is None:
        if isinstance(num_species, (int, float)) and isinstance(rank, (int, float)):
            num_conservation_laws = max(0, int(num_species - rank))
        else:
            num_conservation_laws = "—"

    species_sub = (
        f"{num_compartments} compartment{'s' if num_compartments != 1 else ''}"
    )
    reactions_sub = f"{num_reversible} rev · {num_irreversible} irrev"
    complexes_sub = (
        f"Deficiency δ = {deficiency}" if deficiency != "—" else "Topology analysis"
    )
    conservation_sub = f"Rank = {rank}" if rank != "—" else "Mass balance"
else:
    num_species = "—"
    num_reactions = "—"
    num_complexes = "—"
    num_conservation_laws = "—"

    species_sub = "No model loaded"
    reactions_sub = "No model loaded"
    complexes_sub = "No model loaded"
    conservation_sub = "No model loaded"

stats = st.columns(4, gap="medium")
with stats[0]:
    stat_card("Total species", str(num_species), species_sub, "terra", "Species")
with stats[1]:
    stat_card("Reactions", str(num_reactions), reactions_sub, "amber", "Flux")
with stats[2]:
    stat_card(
        "Network complexes",
        str(num_complexes),
        complexes_sub,
        "sage",
        "Topology",
    )
with stats[3]:
    stat_card(
        "Conservation laws",
        str(num_conservation_laws),
        conservation_sub,
        "slate",
        "Balance",
    )


# -----------------------------------------------------------------------------
# Interactive network stage
# -----------------------------------------------------------------------------

st.write("")
network_panel = st.container(border=True)

with network_panel:
    control_a, control_b, control_c, control_d = st.columns([1.3, 1, 1, 1.1])

    with control_a:
        layout_name = st.selectbox(
            "Layout",
            ["Force-directed", "Bipartite", "Circular", "Hierarchical"],
            key="shapcrn_network_layout",
        )

    with control_b:
        show_species = st.toggle(
            "Species nodes",
            value=True,
            key="shapcrn_show_species_nodes",
        )

    with control_c:
        show_reactions = st.toggle(
            "Reaction nodes",
            value=True,
            key="shapcrn_show_reaction_nodes",
        )

    with control_d:
        min_degree = st.number_input(
            "Min degree",
            min_value=0,
            value=0,
            step=1,
            key="shapcrn_min_degree",
        )

    _graph_legend()

    loaded_model = _get_loaded_model()

    if loaded_model is None:
        placeholder(
            "Interactive network canvas",
            "Upload a valid SBML model to view its bipartite reaction topology.",
            min_height=520,
        )

    elif not HAS_CYTOSCAPE:
        st.error(
            "The Cytoscape component is not available. Install the current "
            "package with `python -m pip install -U streamlit-cytoscape`, then "
            "restart Streamlit."
        )
        if CYTOSCAPE_IMPORT_ERROR is not None:
            st.caption(f"Import error: {CYTOSCAPE_IMPORT_ERROR}")

    else:
        try:
            graph = build_network(loaded_model)

            # Always build both CRN partitions. The visibility toggles are applied
            # by the adapter as transparent styles instead of deleting nodes; this
            # preserves the bipartite layout and prevents isolated nodes collapsing.
            raw_elements, _ = build_cytoscape_elements(
                graph,
                show_species=True,
                show_reactions=True,
                min_degree=int(min_degree),
            )

            cy_elements = _prepare_cytoscape_elements(
                raw_elements,
                graph,
                show_species=show_species,
                show_reactions=show_reactions,
                bipartite_layout=layout_name == "Bipartite",
            )

            if not cy_elements["nodes"]:
                placeholder(
                    "No nodes match the current filters",
                    "Lower the minimum degree to display more nodes.",
                    min_height=520,
                )
            else:
                node_styles, edge_styles = _cytoscape_styles()

                cytoscape_key = _cytoscape_component_key(layout_name, raw_elements)

                streamlit_cytoscape(
                    elements=cy_elements,
                    layout=_layout_config(layout_name, len(cy_elements["nodes"])),
                    node_styles=node_styles,
                    edge_styles=edge_styles,
                    height=620,
                    # Force a fresh frontend instance only when the actual model
                    # or layout changes. Species/reaction visibility toggles keep
                    # the same key and therefore preserve the graph geometry.
                    key=cytoscape_key,
                )

                # Protect page scrolling from accidental Cytoscape zoom/pan. The
                # graph starts locked and becomes interactive only after a click.
                _install_graph_interaction_guard(cytoscape_key)

        except Exception as error:
            st.error("The network graph could not be rendered.")
            st.exception(error)


# -----------------------------------------------------------------------------
# Structural tables
# -----------------------------------------------------------------------------

st.write("")
tab_matrix, tab_species, tab_reactions = st.tabs(
    [
        "▦ Stoichiometry Matrix (N)",
        "▤ Species Catalog",
        "ƒx Reactions & Rate Laws",
    ]
)

with tab_matrix:
    panel_heading(
        "Stoichiometric Matrix",
        "Mass-balance coefficients N ∈ ℝ^(species × reactions)",
    )

    loaded_model = _get_loaded_model()
    if loaded_model is not None:
        N_raw = get_stoichiometric_matrix(loaded_model, use_names=False)
        N_display = format_stoichiometric_matrix_display(N_raw)

        _, col_download = st.columns([3, 1])
        with col_download:
            csv_bytes = N_raw.to_csv().encode("utf-8")
            st.download_button(
                label="⇓ Export Matrix (CSV)",
                data=csv_bytes,
                file_name=(
                    f"{st.session_state.get('shapcrn_model_name', 'model')}"
                    "_stoichiometry.csv"
                ),
                mime="text/csv",
                use_container_width=True,
            )

        st.dataframe(
            N_display,
            use_container_width=True,
            height=380,
        )
    else:
        placeholder(
            "Stoichiometry matrix",
            "Upload an SBML model to extract and inspect the stoichiometric matrix N.",
            min_height=320,
        )

with tab_species:
    panel_heading(
        "Species Catalog",
        "Chemical species, compartments, and boundary conditions",
    )

    loaded_model = _get_loaded_model()
    if loaded_model is not None:
        df_species = get_species_dataframe(loaded_model)
        st.dataframe(df_species, use_container_width=True, height=380)
    else:
        placeholder(
            "Species catalog",
            "Upload an SBML model to inspect the species catalog.",
            min_height=320,
        )

with tab_reactions:
    panel_heading(
        "Reactions & Rate Laws",
        "Chemical equations and kinetic law formulas",
    )

    loaded_model = _get_loaded_model()
    if loaded_model is not None:
        df_reactions = get_reactions_dataframe(loaded_model)
        st.dataframe(df_reactions, use_container_width=True, height=380)
    else:
        placeholder(
            "Reactions & rate laws",
            "Upload an SBML model to inspect kinetic rate laws.",
            min_height=320,
        )
