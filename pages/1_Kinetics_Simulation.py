"""Page 2 — Kinetics & Dynamic Simulation UI skeleton."""

from __future__ import annotations

import streamlit as st

from ui.components import page_header, panel_heading, placeholder


# Shared theme/sidebar/topbar are rendered once by app.py before this page runs.

page_header(
    eyebrow="Kinetics & numerical integration",
    title="Kinetics & Dynamic Simulation",
    subtitle="Time-dependent trajectory exploration, solver controls, steady-state inspection, and perturbation experiments.",
    status="ODE Engine Ready",
)


# -----------------------------------------------------------------------------
# Solver / simulation controls
# -----------------------------------------------------------------------------
config = st.container(border=True)
with config:
    panel_heading("Analysis Configuration & Solver Engine", "Controls only — insert execution logic below", "⚗")
    c1, c2, c3, c4 = st.columns(4, gap="medium")
    with c1:
        solver = st.selectbox("Solver engine", ["Deterministic ODE (LSODA)", "Stiff / BDF", "Custom"])
    with c2:
        end_time = st.slider("Horizon (s)", 1, 500, 100)
        points = st.number_input("Sampling steps", min_value=20, max_value=10000, value=1000, step=50)
    with c3:
        rtol = st.number_input("rtol", value=1e-6, format="%.1e")
        atol = st.number_input("atol", value=1e-9, format="%.1e")
    with c4:
        scan_enabled = st.toggle("Parameter scan", value=False)
        scan_note = st.text_input("Scan parameter", placeholder="e.g. k_PFK")

    run_simulation = st.button(
        "▶ Run Simulation",
        type="primary",
        disabled=True,  # Enable after wiring logic/experiments.py.
    )

# -----------------------------------------------------------------------------
# INSERT SIMULATION EXECUTION HERE
# -----------------------------------------------------------------------------
# if run_simulation:
#     from logic.experiments import run_simulation
#     result = run_simulation(...)
#     st.session_state["simulation_result"] = result


st.write("")
trajectory_panel = st.container(border=True)
with trajectory_panel:
    panel_heading("Concentration vs. Time Dynamics", "Species state trajectories X(t) over the simulated manifold", "〽")
    # INSERT TIME-SERIES CHART HERE
    placeholder(
        "Trajectory chart",
        "INSERT PLOTLY / STREAMLIT TIME-SERIES CHART HERE. The design reference uses warm dashed grid lines, monospace units, and a dark slate tooltip.",
        min_height=430,
    )


st.write("")
left, right = st.columns(2, gap="large")
with left:
    phase_panel = st.container(border=True)
    with phase_panel:
        panel_heading("Phase Space Trajectory", "Limit-cycle projection / attractor view")
        # INSERT PHASE-PLANE PLOT HERE
        placeholder("Phase plane", "INSERT X-vs-Y TRAJECTORY / BIFURCATION VIEW HERE.", min_height=300)

with right:
    steady_panel = st.container(border=True)
    with steady_panel:
        panel_heading("Steady-State & Conservation Law", "Stability verification and invariant mass balance")
        # INSERT STEADY-STATE / CONSERVATION TABLE HERE
        placeholder("Steady-state summary", "INSERT FIXED POINTS, NET FLUX, CONSERVATION CHECKS, AND STATUS BADGES HERE.", min_height=300)


st.write("")
experiment_panel = st.container(border=True)
with experiment_panel:
    panel_heading("Controlled Perturbation Experiment", "Knockout / knock-in baseline comparison")
    a, b, c = st.columns([1, 1.3, 1.3])
    with a:
        operation = st.radio("Experiment", ["Knockout", "Knock-in"], horizontal=True)
    with b:
        entity_type = st.radio("Entity type", ["Species", "Reaction"], horizontal=True)
    with c:
        # INSERT MODEL ENTITY OPTIONS HERE
        selected_entity = st.selectbox("Entity", ["INSERT MODEL ENTITIES HERE"], disabled=True)

    d, e = st.columns(2)
    with d:
        # INSERT RESULT TARGET OPTIONS HERE
        result_target = st.selectbox("Result target", ["INSERT TARGET SPECIES HERE"], disabled=True)
    with e:
        st.number_input("Experiment end time", min_value=0.01, value=120.0, step=10.0)

    run_experiment = st.button(
        "Run perturbation experiment",
        disabled=True,  # Enable after implementing run_perturbation_experiment(...)
    )

    # -------------------------------------------------------------------------
    # INSERT KO / KI LOGIC HERE
    # -------------------------------------------------------------------------
    placeholder("Baseline vs perturbed result", "INSERT METRICS + COMPARISON TRAJECTORY + DOWNLOADS HERE.", min_height=250)


st.write("")
artifact_panel = st.container(border=True)
with artifact_panel:
    panel_heading("Simulation Artifacts & Raw Trajectories", "Exportable scientific outputs")
    buttons = st.columns(3)
    buttons[0].button("⇩ Download Trajectories (.csv)", disabled=True, use_container_width=True)
    buttons[1].button("▧ Export Report (.pdf)", disabled=True, use_container_width=True)
    buttons[2].button("<> Export Python Script", disabled=True, use_container_width=True)
