"""Reusable visual components for the Streamlit shell.

These helpers deliberately contain no ShapCRN logic. They only render structure,
labels, and placeholders.
"""

from __future__ import annotations

from html import escape
from typing import Any, Literal

import streamlit as st

from ui.model_library import (
    ACTIVE_MODEL_KEY,
    get_active_model,
    remove_model,
    set_active_model,
)
from ui.styles import THEME_STATE_KEY, ensure_ui_state


PageName = Literal["overview", "kinetics", "importance"]


def _sidebar_network_counts(
    species_count: str | int = "—",
    reaction_count: str | int = "—",
    compartment_count: str | int = "—",
) -> tuple[str | int, str | int, str | int]:
    """Return the freshest network counts available in session state.

    ``app.py`` renders the persistent sidebar before the selected page body runs.
    The Overview page stores the authoritative parsed-model summary in
    ``shapcrn_model_summary``. Reading that summary here prevents the shell from
    depending on duplicate ``model_*_count`` keys that can easily become stale.

    The explicit arguments remain as fallbacks so this component stays backwards
    compatible with callers that already provide counts.
    """
    summary = st.session_state.get("shapcrn_model_summary")
    if not isinstance(summary, dict):
        return species_count, reaction_count, compartment_count

    return (
        summary.get("num_species", species_count),
        summary.get("num_reactions", reaction_count),
        summary.get("num_compartments", compartment_count),
    )


def render_topbar(
    status: str = "LSODA Idle", workspace: str = "workspace: local_session"
) -> None:
    st.markdown(
        f"""
        <div class="topbar">
            <div class="topbar-left">
                <span class="status-pill">↻ {escape(status)}</span>
                <span>{escape(workspace)}</span>
            </div>
            <div class="topbar-right">
                <span class="topbar-link">⇩ Export Report</span>
                <span class="topbar-link">&lt;&gt; GitHub Repo</span>
                <span class="topbar-link">▣ Documentation</span>
                <span class="science-chip terra">USER</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(
    active: PageName,
    models: dict[str, dict[str, Any]] | None = None,
    species_count: str = "—",
    reaction_count: str = "—",
    compartment_count: str = "—",
) -> dict[str, Any] | None:
    """Render the persistent control rail and return the active raw model record.

    The raw model registry is UI state only. Parsing/loading still belongs in
    ``logic/model.py``.
    """

    models = models or {}

    # The parsed model summary is the single source of truth for these values.
    # This also makes the sidebar independent from legacy ``model_*_count`` keys.
    species_count, reaction_count, compartment_count = _sidebar_network_counts(
        species_count, reaction_count, compartment_count
    )

    with st.sidebar:
        st.markdown(
            """
            <div class="brand-lockup">
                <div class="brand-mark"></div>
                <div>
                    <div class="brand-title">CRN Studio</div>
                    <div class="brand-subtitle">CRN analysis workspace</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="sidebar-kicker">Navigation</div>', unsafe_allow_html=True
        )
        _nav_entry(
            "overview",
            active,
            "⌘  Model Overview & Network Graph",
            "pages/0_Model_Overview.py",
        )
        _nav_entry(
            "kinetics",
            active,
            "⌁  Kinetics & Simulation",
            "pages/1_Kinetics_Simulation.py",
        )
        _nav_entry(
            "importance",
            active,
            "▣  Importance & Sensitivity Analysis",
            "pages/2_Importance_Analysis.py",
        )

        st.markdown(
            '<div class="sidebar-kicker">Input Source</div>', unsafe_allow_html=True
        )

        active_model = get_active_model()
        if models:
            model_ids = list(models)
            current_id = st.session_state.get(ACTIVE_MODEL_KEY)
            current_index = (
                model_ids.index(current_id) if current_id in model_ids else 0
            )

            if len(model_ids) > 1:
                selected_id = st.selectbox(
                    "Active model",
                    model_ids,
                    index=current_index,
                    format_func=lambda model_id: models[model_id]["name"],
                    help="Choose which loaded model the analysis pages should use.",
                    key="sidebar_active_model_selector",
                )
                # Changing the active model mutates the shared model bytes/name.
                # Stop this run here and restart from the persistent app shell so
                # page bodies never render halfway through a model transition.
                if selected_id != current_id:
                    set_active_model(selected_id)
                    st.rerun()

                active_model = get_active_model()

            shown_name = escape(
                active_model["name"] if active_model else "No model loaded"
            )
            count_label = (
                f"{len(models)} model" if len(models) == 1 else f"{len(models)} models"
            )
            st.markdown(
                f"""
                <div class="sidebar-file">
                    <div style="display:flex;justify-content:space-between;gap:.5rem;align-items:center;">
                        <span class="micro-label">Model File</span>
                        <span class="science-chip sage">{escape(count_label)}</span>
                    </div>
                    <div class="sidebar-file-name">▧ {shown_name}</div>
                    <div class="sidebar-meta">Active model · SBML / XML / JSON</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if active_model and st.button(
                "Remove active model",
                key="remove_active_model",
                use_container_width=True,
                help="Remove the active file from this browser session only.",
            ):
                remove_model(active_model["id"])
                st.rerun()
        else:
            st.markdown(
                """
                <div class="sidebar-file">
                    <div style="display:flex;justify-content:space-between;gap:.5rem;align-items:center;">
                        <span class="micro-label">Model File</span>
                        <span class="science-chip amber">Waiting</span>
                    </div>
                    <div class="sidebar-file-name">▧ No model loaded</div>
                    <div class="sidebar-meta">SBML / XML / JSON</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div class="sidebar-kicker" style="margin-top:1.4rem">Loaded Network</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="sidebar-summary">
                <div><strong>{escape(str(species_count))}</strong><span>Species</span></div>
                <div><strong>{escape(str(reaction_count))}</strong><span>Reactions</span></div>
                <div><strong>{escape(str(compartment_count))}</strong><span>Compartments</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="sidebar-kicker">Appearance</div>', unsafe_allow_html=True
        )

        ensure_ui_state()
        st.radio(
            "Theme",
            options=["light", "dark"],
            key=THEME_STATE_KEY,
            horizontal=True,
            format_func=lambda value: value.title(),
            help="The selected appearance is shared by all pages in this browser session.",
        )
        st.caption(
            "Warm linen interface"
            if st.session_state[THEME_STATE_KEY] == "light"
            else "Deep mineral / umber interface"
        )

    return get_active_model()


def _nav_entry(page: PageName, active: PageName, label: str, target: str) -> None:
    if page == active:
        st.markdown(
            f'<div class="nav-active">{escape(label)}</div>', unsafe_allow_html=True
        )
    else:
        st.page_link(target, label=label, use_container_width=True)


def page_header(
    eyebrow: str,
    title: str,
    subtitle: str,
    status: str | None = None,
) -> None:
    left, right = st.columns([4.7, 1.3])
    with left:
        st.markdown(
            f'<div class="eyebrow">{escape(eyebrow)}</div>', unsafe_allow_html=True
        )
        st.title(title)
        st.markdown(
            f'<div class="page-subtitle">{escape(subtitle)}</div>',
            unsafe_allow_html=True,
        )
    if status:
        with right:
            st.write("")
            st.markdown(
                f'<div class="header-status">● {escape(status)}</div>',
                unsafe_allow_html=True,
            )


def panel_heading(title: str, subtitle: str = "", icon: str = "") -> None:
    icon_html = f"<span>{escape(icon)}</span>" if icon else ""
    st.markdown(
        f'<div class="panel-title">{icon_html}<span>{escape(title)}</span></div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(
            f'<div class="panel-subtitle">{escape(subtitle)}</div>',
            unsafe_allow_html=True,
        )


def stat_card(
    label: str,
    value: str | int | float,
    help_text: str,
    accent: Literal["terra", "sage", "amber", "slate"] = "terra",
    chip: str | None = None,
) -> None:
    css_class = {"terra": "", "sage": "sage", "amber": "amber", "slate": "slate"}[
        accent
    ]
    chip_html = (
        f'<span class="science-chip {accent}">{escape(chip)}</span>' if chip else ""
    )
    st.markdown(
        f"""
        <div class="stat-card {css_class}">
            <div style="display:flex;justify-content:space-between;gap:.6rem;align-items:start;">
                <div class="stat-label">{escape(label)}</div>{chip_html}
            </div>
            <div class="stat-value">{escape(str(value))}</div>
            <div class="stat-help">{escape(help_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def placeholder(title: str, copy: str, *, min_height: int = 190) -> None:
    st.markdown(
        f"""
        <div class="placeholder-box" style="min-height:{int(min_height)}px">
            <div class="placeholder-title">{escape(title)}</div>
            <div class="placeholder-copy">{escape(copy)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def network_legend() -> None:
    st.markdown(
        f"""
        <div class="graph-legend">
            <span class="legend-item"><span class="legend-dot" style="background:var(--terracotta)"></span>Species node</span>
            <span class="legend-item"><span class="legend-diamond" style="background:var(--amber)"></span>Reaction node</span>
            <span class="legend-item"><span style="color:var(--terracotta-dark)">━━</span>Substrate consumption</span>
            <span class="legend-item"><span style="color:var(--sage-dark)">━━</span>Product formation</span>
            <span class="legend-item"><span style="color:var(--mineral)">┄┄</span>Allosteric modifier</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ko_target_legend() -> None:
    st.markdown(
        """
        <div style="background:var(--paper);border:1px solid var(--border);border-radius:8px;padding:.65rem .75rem;">
            <div class="micro-label" style="font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;color:var(--text-soft)">KO → target Shapley effect</div>
            <div class="gradient-legend"></div>
            <div class="legend-labels"><span>Negative / suppressor</span><span>≈ 0</span><span>Positive / driver</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
