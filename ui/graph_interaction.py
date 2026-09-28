"""Shared interaction helpers for embedded Cytoscape graphs."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

import streamlit.components.v1 as st_components


def install_graph_interaction_guard(
    component_key: str,
    palette: Mapping[str, str],
) -> None:
    """Install a click-to-enter shield over the preceding graph component.

    Parameters
    ----------
    component_key : str
        Stable key of the graph protected by the shield.
    palette : mapping of str to str
        Theme colours containing surface, text, border, focus, and shadow.

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
