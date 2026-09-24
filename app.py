"""ShapCRN Studio application shell.

This file owns everything that must persist while the user changes pages:
- global page configuration
- global CSS / active theme
- custom sidebar and theme selector
- workspace topbar
- multipage routing

Scientific/page-specific UI lives in ``pages/``. Keeping the shell here is
important in Streamlit: widgets rendered by the entrypoint remain stable across
page switches, unlike widgets defined separately inside each page.
"""

from __future__ import annotations

import streamlit as st

from ui.components import render_sidebar, render_topbar
from ui.model_library import ensure_model_library, get_active_model
from ui.styles import apply_global_styles, ensure_ui_state


def main() -> None:
    """Render the Streamlit shell in the main application process only."""
    st.set_page_config(
        page_title="ShapCRN Studio",
        page_icon="🧬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # -------------------------------------------------------------------------
    # APP-WIDE UI STATE
    # -------------------------------------------------------------------------
    # Theme state is created before navigation so it belongs to the application
    # shell rather than to an individual page.
    ensure_ui_state()
    apply_global_styles()

    # -------------------------------------------------------------------------
    # ROUTING
    # -------------------------------------------------------------------------
    # ``st.navigation`` turns app.py into a persistent entrypoint. The files
    # below are page bodies only; they no longer create their own sidebar/theme
    # widgets. This prevents the theme from resetting across page changes.
    overview_page = st.Page(
        "pages/0_Model_Overview.py",
        title="Model Overview & Network Graph",
        icon="🧬",
        default=True,
    )
    kinetics_page = st.Page(
        "pages/1_Kinetics_Simulation.py",
        title="Kinetics & Simulation",
        icon="⚗️",
    )
    importance_page = st.Page(
        "pages/2_Importance_Analysis.py",
        title="Importance & Sensitivity Analysis",
        icon="📊",
    )

    current_page = st.navigation(
        [overview_page, kinetics_page, importance_page],
        position="hidden",  # We render our own scientific control rail.
    )

    active_by_title = {
        "Model Overview & Network Graph": "overview",
        "Kinetics & Simulation": "kinetics",
        "Importance & Sensitivity Analysis": "importance",
    }
    active_page = active_by_title.get(current_page.title, "overview")

    # -------------------------------------------------------------------------
    # SHARED APP SHELL
    # -------------------------------------------------------------------------
    # The shell owns the raw-file model library so model selection persists
    # while pages change. Scientific parsing still belongs in logic/model.py.
    model_library = ensure_model_library()
    render_sidebar(
        active=active_page,
        models=model_library,
        species_count=st.session_state.get("num_species", "—"),
        reaction_count=st.session_state.get("num_reactions", "—"),
        compartment_count=st.session_state.get("num_compartments", "—"),
    )

    # render_sidebar may change the model, so read the active record again.
    active_model = get_active_model()
    workspace_name = active_model["name"] if active_model else "local_session"
    render_topbar(status="LSODA Idle", workspace=f"WORKSPACE: {workspace_name}")

    # -------------------------------------------------------------------------
    # RUN SELECTED PAGE
    # -------------------------------------------------------------------------
    current_page.run()


if __name__ == "__main__":
    main()
