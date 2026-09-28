"""Shared interaction helpers for embedded Cytoscape graphs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

import streamlit.components.v1 as st_components


def install_graph_interaction_guard(
    component_key: str,
    palette: Mapping[str, str],
    infopanel_title_field: str | None = None,
    managed_selected_node_id: str | None = None,
) -> None:
    """Install a click-to-enter shield over the preceding graph component.

    Parameters
    ----------
    component_key : str
        Stable key of the graph protected by the shield.
    palette : mapping of str to str
        Theme colours containing surface, text, border, focus, and shadow.
    infopanel_title_field : str, optional
        Node data field used as the information-panel title. When omitted, the
        component's native title remains unchanged.
    managed_selected_node_id : str, optional
        Node whose visual selection follows application state. Clearing a
        previously managed value also closes the information panel.

    Returns
    -------
    None
        The helper injects the interaction guard into the Streamlit parent page.

    Examples
    --------
    >>> install_graph_interaction_guard(  # doctest: +SKIP
    ...     "network_graph", {"surface": "#fff", "text": "#111",
    ...     "border": "#ddd", "focus": "#369", "shadow": "#0003"}
    ... )
    """
    guard_token = hashlib.sha1(component_key.encode("utf-8")).hexdigest()[:12]
    surface = palette.get("surface", palette.get("plot_bg", "#ffffff"))
    title_field = json.dumps(infopanel_title_field)
    selected_node_id = json.dumps(managed_selected_node_id)

    st_components.html(
        f"""
        <script>
        (() => {{
            const TOKEN = '{guard_token}';
            const OVERLAY_ID = 'shapcrn-graph-overlay-' + TOKEN;
            const LOCK_ID = 'shapcrn-graph-lock-' + TOKEN;
            const STATE_ATTR = 'data-shapcrn-graph-state-' + TOKEN;
            const PANEL_STYLE_ID = 'shapcrn-infopanel-style-' + TOKEN;
            const PANEL_RUNTIME_ID = 'shapcrn-infopanel-runtime-' + TOKEN;
            const TITLE_FIELD_ATTR = 'data-shapcrn-title-field-' + TOKEN;
            const SELECTED_NODE_ATTR = 'data-shapcrn-selected-node-' + TOKEN;
            const PREVIOUS_NODE_ATTR = 'data-shapcrn-previous-node-' + TOKEN;
            const INFO_TITLE_FIELD = {title_field};
            const MANAGED_SELECTED_NODE_ID = {selected_node_id};

            const install = (attempt = 0) => {{
                try {{
                    const doc = window.parent.document;
                    const helperFrame = window.frameElement;
                    if (!doc || !helperFrame) return;

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

                    const host = graphFrame.parentElement;
                    if (!host) return;

                    try {{
                        const graphDoc = graphFrame.contentDocument;
                        if (graphDoc) {{
                            graphDoc.documentElement.style.background = '{surface}';
                            graphDoc.body.style.background = '{surface}';
                            graphDoc.querySelectorAll('div').forEach((element) => {{
                                if (element.querySelector('canvas')) {{
                                    element.style.background = '{surface}';
                                }}
                            }});

                            const infopanel = graphDoc.getElementById('infopanel');

                            if (INFO_TITLE_FIELD && infopanel) {{
                                if (!graphDoc.getElementById(PANEL_STYLE_ID)) {{
                                    const style = graphDoc.createElement('style');
                                    style.id = PANEL_STYLE_ID;
                                    style.textContent = `
                                        .infopanel__name {{
                                            flex: 1 1 auto;
                                            width: auto;
                                            min-width: 0;
                                            height: auto;
                                            min-height: 2rem;
                                            padding: .2rem;
                                            line-height: 1.2;
                                            white-space: normal;
                                            overflow-wrap: anywhere;
                                            word-break: break-word;
                                        }}
                                        .infopanel__icon {{ flex: 0 0 2rem; }}
                                    `;
                                    graphDoc.head.appendChild(style);
                                }}

                                graphDoc.documentElement.setAttribute(
                                    TITLE_FIELD_ATTR,
                                    INFO_TITLE_FIELD
                                );
                                graphDoc.documentElement.setAttribute(
                                    SELECTED_NODE_ATTR,
                                    MANAGED_SELECTED_NODE_ID || ''
                                );

                                if (!graphDoc.getElementById(PANEL_RUNTIME_ID)) {{
                                    const runtime = graphDoc.createElement('script');
                                    runtime.id = PANEL_RUNTIME_ID;
                                    runtime.textContent = `
                                        (() => {{
                                            const root = document.documentElement;
                                            const titleAttr = '${{TITLE_FIELD_ATTR}}';
                                            const selectedAttr = '${{SELECTED_NODE_ATTR}}';
                                            const previousAttr = '${{PREVIOUS_NODE_ATTR}}';

                                            const start = (attempt = 0) => {{
                                                const cy = document.getElementById('cy')?._cyreg?.cy;
                                                const cyContainer = document.getElementById('cy');
                                                const panel = document.getElementById('infopanel');
                                                if (!cy || !cyContainer || !panel) {{
                                                    if (attempt < 20) {{
                                                        window.setTimeout(
                                                            () => start(attempt + 1),
                                                            100
                                                        );
                                                    }}
                                                    return;
                                                }}

                                                const refreshTitle = () => {{
                                                    if (
                                                        panel.getAttribute('data-expanded')
                                                        !== 'true'
                                                    ) return;
                                                    const selected = cy.$(':selected').first();
                                                    if (!selected || selected.length === 0) return;
                                                    const field = root.getAttribute(titleAttr);
                                                    const title = selected.data(field) || selected.id();
                                                    const element = document.querySelector(
                                                        '.infopanel__name'
                                                    );
                                                    if (
                                                        element
                                                        && element.textContent !== String(title)
                                                    ) element.textContent = String(title);
                                                }};

                                                const syncSelection = () => {{
                                                    const selectedId = root.getAttribute(
                                                        selectedAttr
                                                    );
                                                    const previousId = root.getAttribute(
                                                        previousAttr
                                                    );
                                                    if (selectedId) {{
                                                        const node = cy.getElementById(selectedId);
                                                        if (node.length > 0) {{
                                                            if (!node.selected()) node.select();
                                                            if (previousId !== selectedId) {{
                                                                root.setAttribute(
                                                                    previousAttr,
                                                                    selectedId
                                                                );
                                                            }}
                                                        }}
                                                    }} else if (previousId) {{
                                                        const previousNode = cy.getElementById(
                                                            previousId
                                                        );
                                                        if (previousNode.length > 0) {{
                                                            previousNode.unselect();
                                                        }}
                                                        root.removeAttribute(previousAttr);
                                                    }}
                                                }};

                                                let reservedWidth = null;
                                                const syncCanvasSpace = () => {{
                                                    const expanded = (
                                                        panel.getAttribute('data-expanded')
                                                        === 'true'
                                                    );
                                                    const container = document.getElementById(
                                                        'container'
                                                    );
                                                    const width = expanded && container
                                                        ? Math.ceil(
                                                            panel.getBoundingClientRect().right
                                                            - container.getBoundingClientRect().left
                                                        )
                                                        : 0;
                                                    if (reservedWidth === width) return;
                                                    reservedWidth = width;
                                                    cyContainer.style.marginLeft = width
                                                        ? width + 'px'
                                                        : '';
                                                    cyContainer.style.width = width
                                                        ? 'calc(100% - ' + width + 'px)'
                                                        : '';
                                                    window.requestAnimationFrame(() => {{
                                                        cy.resize();
                                                        cy.fit(undefined, 45);
                                                    }});
                                                }};

                                                new MutationObserver(() => {{
                                                    syncSelection();
                                                    refreshTitle();
                                                }}).observe(root, {{
                                                    attributes: true,
                                                    attributeFilter: [
                                                        titleAttr,
                                                        selectedAttr
                                                    ]
                                                }});
                                                new MutationObserver(() => {{
                                                    refreshTitle();
                                                    syncCanvasSpace();
                                                }}).observe(
                                                    panel,
                                                    {{
                                                        attributes: true,
                                                        childList: true,
                                                        characterData: true,
                                                        subtree: true
                                                    }}
                                                );
                                                syncSelection();
                                                refreshTitle();
                                                syncCanvasSpace();
                                            }};
                                            start();
                                        }})();
                                    `;
                                    graphDoc.body.appendChild(runtime);
                                }}
                            }}
                        }}
                    }} catch (error) {{
                        console.debug('ShapCRN graph canvas theme:', error);
                    }}

                    if (window.getComputedStyle(host).position === 'static') {{
                        host.style.position = 'relative';
                    }}
                    host.style.isolation = 'isolate';
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
                            position: 'absolute', inset: '0', zIndex: '2147483000',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            cursor: 'pointer', borderRadius: '10px', background: 'transparent',
                            opacity: '0', visibility: 'visible', pointerEvents: 'auto',
                            transition: 'opacity 130ms ease, background 130ms ease',
                            touchAction: 'pan-y', boxSizing: 'border-box'
                        }});

                        const message = doc.createElement('div');
                        message.innerHTML = `
                            <div style="display:flex;align-items:center;gap:8px;padding:10px 15px;
                                border:1px solid {palette['border']};border-radius:999px;
                                background:{surface};color:{palette['text']};
                                font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                                font-size:13px;font-weight:650;line-height:1;
                                box-shadow:0 8px 24px {palette['shadow']};
                                backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
                                pointer-events:none;user-select:none;">
                                <span style="font-size:15px;">⌖</span>
                                <span>Click to enter graph view</span>
                            </div>`;
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
                            position: 'absolute', top: '12px', right: '12px',
                            zIndex: '2147483001', display: 'none',
                            border: '1px solid {palette['border']}', borderRadius: '999px',
                            padding: '7px 11px', background: '{surface}',
                            color: '{palette['text']}',
                            fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
                            fontSize: '12px', fontWeight: '650', lineHeight: '1',
                            boxShadow: '0 5px 16px {palette['shadow']}', cursor: 'pointer',
                            backdropFilter: 'blur(7px)', WebkitBackdropFilter: 'blur(7px)'
                        }});
                        host.appendChild(lockButton);
                    }}

                    const lock = () => {{
                        host.setAttribute(STATE_ATTR, 'locked');
                        overlay.style.pointerEvents = 'auto';
                        overlay.style.opacity = '0';
                        overlay.style.background = 'transparent';
                        lockButton.style.display = 'none';
                    }};
                    const unlock = () => {{
                        host.setAttribute(STATE_ATTR, 'unlocked');
                        overlay.style.opacity = '0';
                        overlay.style.background = 'transparent';
                        overlay.style.pointerEvents = 'none';
                        lockButton.style.display = 'block';
                    }};

                    if (overlay.getAttribute('data-bound') !== 'true') {{
                        overlay.setAttribute('data-bound', 'true');
                        overlay.addEventListener('mouseenter', () => {{
                            if (isUnlocked()) return;
                            overlay.style.opacity = '1';
                            overlay.style.background = '{palette['focus']}18';
                        }});
                        overlay.addEventListener('mouseleave', () => {{
                            if (isUnlocked()) return;
                            overlay.style.opacity = '0';
                            overlay.style.background = 'transparent';
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

                    if (isUnlocked()) unlock(); else lock();
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
