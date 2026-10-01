"""Scrollable concentration readouts for species trajectory charts."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as st_components
from plotly.graph_objects import Figure


def trajectory_chart(
    figure: Figure,
    key: str,
    palette: Mapping[str, str],
) -> None:
    """Render trajectories above a persistent, scrollable hover readout.

    Parameters
    ----------
    figure : Figure
        Species line traces sharing the same sampled time axis. Axis titles
        supply the time and concentration units for the readout.
    key : str
        Unique, stable Streamlit key containing letters and underscores.
    palette : mapping of str to str
        Active theme colours for the panel surface, text, and border.

    Returns
    -------
    None
        Render the chart and update its readout in the browser without reruns.

    Examples
    --------
    >>> import plotly.graph_objects as go
    >>> from ui.styles import get_theme_palette
    >>> trajectory_chart(  # doctest: +SKIP
    ...     go.Figure(go.Scatter(x=[0, 1], y=[1, 0], name="S1")),
    ...     "simulation_trajectory", get_theme_palette(),
    ... )
    """
    figure.update_traces(hoverinfo="none", hovertemplate=None)
    figure.update_layout(hovermode="x", hoverdistance=-1)
    figure.update_xaxes(showspikes=True, spikemode="across", spikesnap="data")
    payload = {
        "time": [float(value) for value in figure.data[0].x] if figure.data else [],
        "species": [
            {
                "name": trace.name,
                "values": [
                    float(value) if math.isfinite(float(value)) else None
                    for value in trace.y
                ],
            }
            for trace in figure.data
        ],
        "timeLabel": figure.layout.xaxis.title.text or "Time",
        "valueLabel": figure.layout.yaxis.title.text or "Concentration",
    }
    # Escape script delimiters in model names before embedding JSON in HTML.
    encoded = json.dumps(payload, allow_nan=False).replace("<", "\\u003c")
    signature = hashlib.sha1(encoded.encode()).hexdigest()
    runtime = Path(__file__).with_suffix(".js").read_text()

    with st.container(key=key):
        st.plotly_chart(
            figure,
            key=f"{key}_chart",
            use_container_width=True,
            theme=None,
            config={"displayModeBar": True, "displaylogo": False},
        )
        st.html(
            f"""
            <style>
            .st-key-{key} .trajectory-readout {{
                width: 100%; max-height: 400px; overflow-y: auto; box-sizing: border-box;
                background: {palette['plot_bg']}; color: {palette['text']};
                border: 1px solid {palette['border']}; border-radius: 8px;
                font-family: Inter, sans-serif; font-size: 14px;
            }}
            .st-key-{key} .trajectory-readout header {{
                position: sticky; top: 0; z-index: 1; padding: 12px;
                background: {palette['plot_bg']};
                border-bottom: 1px solid {palette['border']};
            }}
            .st-key-{key} .trajectory-readout header strong {{ display: block; }}
            .st-key-{key} .trajectory-readout-body {{ padding: 12px; }}
            .st-key-{key} .trajectory-readout-row {{
                display: grid; grid-template-columns: 18px minmax(0, 1fr) auto;
                gap: 8px; align-items: baseline; padding: 6px 0;
            }}
            .st-key-{key} .trajectory-readout-name {{ overflow-wrap: anywhere; }}
            .st-key-{key} .trajectory-readout-value {{ font-variant-numeric: tabular-nums; }}
            .st-key-{key} .trajectory-readout-swatch {{ border-top: 3px solid; }}
            </style>
            <section class="trajectory-readout" tabindex="0"
                     aria-label="Species concentrations">
                <header><strong>Species concentrations</strong>
                    <span class="trajectory-readout-time"></span>
                </header>
                <div class="trajectory-readout-body">
                    Hover over the chart to inspect concentrations.
                </div>
            </section>
            """
        )
        st_components.html(
            "<script>\n"
            f"const chartKey = {json.dumps(key)};\n"
            f"const signature = {json.dumps(signature)};\n"
            f"const payload = {encoded};\n"
            + runtime
            + "\n</script>",
            height=0,
            width=0,
        )
