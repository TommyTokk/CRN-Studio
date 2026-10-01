# CRN-Studio

CRN-Studio is an interactive application for inspecting chemical reaction networks, simulating their dynamics, and exploring the effects of knockouts, knock-ins, and changes to initial species values. The interface displays the name **ShapCRN Studio** and uses **ShapCRN** for model preparation, numerical simulation, model transformations, and importance assessment.

The application runs through Streamlit and is operated in a web browser. It has three main pages:

| Page | Purpose |
| --- | --- |
| Model Overview & Network Graph | Load models, inspect structural statistics, explore the reaction network, and inspect species, reactions, and stoichiometry. |
| Kinetics & Simulation | Run deterministic simulations, detect numerical steady state, perform KO/KI experiments, and compare perturbation trajectories. |
| Importance & Sensitivity Analysis | Assess species-specific KO/KI effects across an input perturbation grid and explore rankings, heatmaps, and target influence networks. |

This manual covers the current implementation. Features visible in the interface but not implemented are identified in [Current limitations](#current-limitations).

## Contents

- [Installation and startup](#installation-and-startup)
- [Quick start](#quick-start)
- [Models, navigation, and session state](#models-navigation-and-session-state)
- [Model Overview and Network Graph](#model-overview-and-network-graph)
- [Kinetics and Simulation](#kinetics-and-simulation)
- [Importance and Sensitivity Analysis](#importance-and-sensitivity-analysis)
- [End-to-end workflow](#end-to-end-workflow)
- [Troubleshooting](#troubleshooting)
- [Current limitations](#current-limitations)
- [Developer guide](#developer-guide)

## Installation and startup

### Prerequisites

You need a local copy of this repository, Python, and a browser. Run the commands below from the repository root, where `app.py` and `requirements.txt` are located.

**Python 3.12 is the setup used for the instructions below.** The locally inspected ShapCRN 0.2.0 package declares Python `>=3.10,<3.13`. This repository does not declare a separate Python compatibility range or pin every dependency, so that declaration alone does not establish that every possible dependency combination works on every Python version. Dependency resolution may also change with newer ShapCRN releases.

### Create an isolated environment

On macOS or Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell prevents activation, you can use `.venv\Scripts\python.exe` in place of `python` for installation and startup. An existing compatible Conda environment is also suitable; activate it before installing the requirements.

The direct dependencies are:

| Package | Repository requirement | Role |
| --- | --- | --- |
| Streamlit | `>=1.40` | Application shell, navigation, widgets, and session state. |
| pandas | `>=2.0` | Tables and numerical result frames. |
| ShapCRN | `>=0.2.0` | Scientific loading, transformations, simulation helpers, and importance assessment. |
| streamlit-cytoscape | `==0.2.1` | Interactive network canvases. |
| Plotly | `>=5` | Time-course plots, phase plots, rankings, and heatmaps. |
| NetworkX | `>=3` | Network construction and structural/path analysis. |

ShapCRN supplies additional dependencies, including NumPy, SciPy, python-libSBML, and libRoadRunner. libSBML handles SBML models; RoadRunner performs numerical integration. Installing the requirements should install these transitive dependencies as well.

### Start and stop the application

```bash
python -m streamlit run app.py
```

Keep this terminal running. Open the **Local URL** printed by Streamlit, normally `http://localhost:8501`, in your browser. The repository sets `server.headless = true`, so a browser window may not open automatically.

If that port is occupied:

```bash
python -m streamlit run app.py --server.port 8502
```

Press **Ctrl+C** in the terminal to stop the server. Use `deactivate` when you want to leave a virtual environment. Restarting the server starts new application sessions; uploaded models and computed results are not saved as a project.

## Quick start

1. Start the application and open its Local URL.
2. On **Model Overview & Network Graph**, upload a valid SBML model using **Upload Bio-Model**.
3. Confirm that species and reaction counts, the network, and the structural tables appear.
4. Open **Kinetics & Simulation**. Keep **Deterministic ODE**, choose a time horizon, and click **Run Simulation**.
5. Use **Species to display** to inspect the relevant time courses.
6. In the phase-space section, open **Standard** and select exactly two or three species.
7. To explore sensitivity, choose at least one input under **Species to perturb**, a different species under **Target species to observe**, and click **Run perturbation sweep**.
8. For species importance, open **Importance & Sensitivity Analysis**, select inputs, targets, and KO/KI species, then click **Compute Shapley values**.

Start with a small input selection and a modest number of sweep levels. Each added input multiplies the computational workload.

## Models, navigation, and session state

### Accepted files and preparation

The uploader allows `.xml` and `.sbml` filenames. **The current loading path expects UTF-8 SBML XML content.** In the inspected ShapCRN implementation, the bytes loader decodes the file and passes it directly to libSBML; it does not convert a JSON model into SBML. Ordinary JSON is therefore not a supported model representation despite the uploader label. Use an SBML XML export from your modeling tool.

A model must contain a valid SBML model object and pass the dependency's validation. Successful structural loading does not guarantee that every kinetic law, rule, event, or transformation is supported by the simulation and KO/KI workflows.

During loading, the application asks ShapCRN to **split reversible reactions** into forward and reverse reactions. Consequently:

- Reaction counts, identifiers, formulas, and the graph describe the prepared model.
- The reaction catalog may differ from the source file's original reaction list.
- A reaction KO/KI selection refers to a prepared reaction. To affect both directions of an originally reversible reaction, inspect and select the appropriate prepared reactions.
- Uploading does not overwrite the source file on disk.

### Manage multiple models

You can upload multiple files at once and add more files through the uploader. The newest newly added model becomes active. When more than one model is available, use **Active model** in the sidebar to select one.

The library identifies models by their file content. Two files containing identical bytes share one library entry, even if their filenames differ.

To remove a model:

- Use the uploader's **×** to remove a file belonging to the current upload batch.
- Use **Remove active model** in the sidebar to remove the active library entry from the session.

Removing an entry does not delete the original local file. If other entries remain, the application chooses another model. Returning to Overview after visiting another page preserves the independent model library, even when Streamlit recreates the uploader.

**After selecting another model, visit Model Overview before running kinetics experiments.** Overview refreshes the shared parsed model used by the kinetics page. The importance page separately prepares the active file. This sequence avoids working with stale parsed-model state.

### Navigation and appearance

The sidebar provides navigation, active-model information, species/reaction/compartment counts, and a **Theme** selector. **Light** and **Dark** affect the application and scientific plots and persist while navigating within the session.

### What is retained

Models and numerical results live in Streamlit session state. Navigation within the same session retains them, subject to the invalidation rules below. A server restart or a new browser session requires reloading models and recomputing results; a browser reload can also establish a new session. There is no project save/load mechanism.

Computed results are cached for reuse:

| Action | Effect |
| --- | --- |
| Change displayed species, a layout, or the theme | Update the view without rerunning the scientific calculation. |
| Shorten a standard, knock, or kinetics-sweep horizon | Reuse the covered part of a compatible cached trajectory. The displayed endpoint is interpolated when needed. |
| Increase a horizon beyond the cached run | Run the calculation again to cover the longer interval. |
| Change simulation mode or numerical tolerances | Require a new compatible simulation. |
| Change KO/KI operation, entity type, or selected entities | Require a new knock experiment. |
| Change sweep inputs, amplitude, levels, tolerances, or model source | Require a new kinetics sweep. |
| Change kinetics-sweep targets | Derive new envelopes from cached full-species trajectories when available. |
| Change importance targets or select a subset of previously computed players | Reuse cached matrices when the other analysis settings match. |
| Add importance players or change its inputs, amplitude, levels, horizon, operation, or payoff | Require a new importance calculation. |
| Switch the active model | Invalidate the previous model's analysis results as the analysis pages detect the changed model. |
| Run a new knock experiment | Invalidate a kinetics sweep based on the previous post-knock model. |

When a compatible result already covers the request, the relevant button displays **Cached result active** and is disabled. Changed settings do not always immediately hide the last successful result: read the cached-run caption and any warning before interpreting a plot as the result of your current configuration. Failed computations may leave the previous successful result visible.

## Model Overview and Network Graph

### Structural statistics

The summary cards describe the prepared network:

| Metric | Interpretation |
| --- | --- |
| Total species | Number of species, including boundary and constant species. |
| Reactions | Number of prepared reactions after reversible-reaction splitting. |
| Network complexes | Number of distinct reactant/product combinations, including their stoichiometric coefficients. |
| Deficiency | Structural index `δ = n − l − s`, where `n` is the complex count, `l` the number of linkage classes, and `s` the stoichiometric rank. |
| Rank | Numerical rank of the stoichiometric matrix. |
| Conservation laws | Displayed estimate `number of species − rank(N)`. |

Linkage classes are connected components of the undirected **complex graph**. Complexes are combinations such as `A + B` or `2 C`; they are different from the species and reaction nodes in the interactive canvas.

The conservation count is a structural estimate, not a list of conserved quantities verified against all model rules, events, or boundary behavior. Deficiency alone does not establish uniqueness of an equilibrium, convergence, or the absence of oscillations. Such conclusions require additional kinetic and network assumptions.

### Explore the network

The canvas is a directed bipartite graph:

- **Species** appear as circles.
- **Reactions** appear as diamonds.
- Reactants connect from species to reactions; products connect from reactions to species.
- Declared modifiers also connect from species to reactions. Their participation does not mean they are consumed, and the edge alone does not identify an activating or inhibiting effect.

Choose a **Layout**:

| Layout | Use |
| --- | --- |
| Force-directed | Explore the overall connectivity. |
| Bipartite | Separate the species and reaction partitions. |
| Circular | Arrange nodes around a circular layout. |
| Hierarchical | Inspect layered network organization. |

**Species nodes** and **Reaction nodes** toggle visibility. Hidden nodes remain layout anchors so toggling a partition does not collapse the other partition. **Min degree** filters nodes by connectivity; if no nodes remain, lower it toward zero.

The graph initially shows **Click to enter graph view**. Click to enable canvas interaction, then pan, zoom, and inspect nodes. Use **Lock graph** to restore normal page scrolling over the canvas. Changing the model or layout can recreate the graph view.

### Inspect the structural tables

**Stoichiometry Matrix (N)** displays a matrix with species as rows and reactions as columns. Each coefficient is product stoichiometry minus reactant stoichiometry:

- Negative: net consumption by the reaction.
- Positive: net production by the reaction.
- Zero: no net stoichiometric change.

For a reaction `A → 2 B`, the corresponding entries are `−1` for `A` and `+2` for `B`. Modifiers have no consumption/production coefficient merely because they modify the rate. The matrix alone does not encode kinetic laws or all SBML rules.

Use **Export Matrix (CSV)** to download the raw numerical matrix. Display formatting does not change the exported coefficients; the download includes the species row identifiers.

**Species Catalog** contains ID, name, compartment, initial value, boundary condition, and constant status. The column named **Initial Concentration** falls back to an initial amount when concentration is not set; inspect the source SBML to distinguish those quantities. Missing names or unset values may appear as `—`.

**Reactions & Rate Laws** contains reaction IDs and names, reaction formulas, reversibility, and kinetic-law formulas. These are useful for identifying the prepared reaction you intend to perturb.

## Kinetics and Simulation

### Standard simulation

Load and inspect the active model on Overview first. In **Analysis Configuration & Simulation Mode**, configure:

| Control | Default | Behavior |
| --- | --- | --- |
| Simulation mode | Deterministic ODE | Fixed-horizon simulation or numerical steady-state detection. |
| Horizon / maximum time (s) | 100 | Integer between 1 and 500; final time for ODE mode, upper time bound for steady-state mode. |
| rtol | `1e-6` | Relative integration tolerance. |
| atol | `1e-9` | Absolute integration tolerance. |
| Parameter scan | Off | Present in the interface, but does not execute a parameter scan. |
| Scan parameter | Empty | Stored configuration text; does not change a kinetic parameter. |

Use finite, positive tolerances. Smaller values request tighter numerical accuracy and can increase computation time. `atol` matters especially for values close to zero. These controls set integration tolerances, not the steady-state detection threshold.

Click **Run Simulation**. Both modes delegate to ShapCRN's RoadRunner helpers, whose inspected default integrator is **CVODE**. The topbar text **LSODA Idle** is a static label and does not identify the actual solver or report live solver activity.

**Deterministic ODE** integrates from time zero to the selected horizon. **Until steady state** integrates in adaptive blocks and checks changes in monitored species between block endpoints. In the inspected ShapCRN 0.2.0 implementation, the directly called helper starts with 10-unit blocks and defaults to a change threshold of `1e-12` and three consecutive successful checks; near-zero values use an absolute-change check. These settings are supplied by the dependency and are not exposed as application controls.

A success message reports the detected steady-state time. If convergence is not detected within the maximum time, the page warns you and still allows inspection of the trajectory. Numerical convergence over a finite interval is not proof of global stability or a unique equilibrium.

### Read time-course plots

**Concentration vs. Time Dynamics** displays the standard simulation. Use **Species to display** to choose traces. An empty selection produces no species curves; select at least one species to restore them.

Hover to inspect values and use the available plot controls for zooming and navigation. The caption identifies the cached run and the currently visible horizon. Ordinary RoadRunner output can omit boundary or constant species; KO/KI and sweep workflows explicitly request all model species.

**Units come from the SBML model.** Some standard plot labels say seconds and molar concentration, but the application does not convert every model into those units. Depending on species definitions, simulated symbols can represent concentrations or amounts. Compare runs using the same model units and inspect SBML unit definitions before reporting physical quantities.

### Knockout and knock-in experiments

In **Knock Experiment**:

1. Choose **Knockout** or **Knock-in**.
2. Choose **Species** or **Reaction** as the entity type.
3. Select one or more **Entities**.
4. Set **End time**; the default is 120, with a minimum of 0.01.
5. Click **Run knock experiment**.

The selected entities are modified together in one cloned model and then simulated from time zero. The original active model is retained. The experiment uses the `rtol` and `atol` controls from the standard simulation configuration and runs a fixed time course, independently of the standard simulation mode.

The inspected transformations have the following meaning:

| Experiment | Behavior |
| --- | --- |
| Species KO | Set the species to zero, mark it as boundary, and adjust supported rules, assignments, and participating reactions so it remains knocked out. This can disable reactions consuming the species and alter product references. |
| Reaction KO | Set the reaction's kinetic law to zero while retaining the reaction and its references. |
| Species KI | Fix the species at an automatically determined peak value, marking it boundary and constant. The peak is obtained from ShapCRN reference simulation helpers. |
| Reaction KI | Replace the selected reaction with a copy using fixed copies of its reactants, initialized from automatically determined reactant peaks. Shared reactants across the selected reactions share fixed copies. |

Here, **knock-in does not mean importing a new gene or adding an arbitrary reaction**, and there is no user-entered KI value. Peak estimation uses dependency helper settings; do not assume it uses the exact horizon of your displayed standard run.

Unsupported rule dependencies, `fast=true` reactions, inconsistent shared-reactant values, or invalid kinetic laws can make a transformation fail. A species KO is a model intervention, not simply hiding its trace.

The resulting trajectories are shown in the knock-results section. Select displayed species and compare with the standard time course at compatible horizons and tolerances. The modified model becomes available as **Post-knock model** for the kinetics perturbation sweep.

### Initial-value perturbation sweeps

The kinetics **Perturbation Sweep** varies initial species symbol values and simulates every combination. It does not vary kinetic rate parameters.

1. Choose **Original model** or, after a successful knock experiment, **Post-knock model** under **Model to perturb**.
2. Select at least one **Species to perturb**.
3. Select at least one different **Target species to observe**.
4. Configure **Variation (±%)**, **Sweep levels**, and **End time**.
5. Check the displayed simulation count and estimated trajectory memory.
6. Click **Run perturbation sweep**.

| Setting | Default | Allowed interface values |
| --- | --- | --- |
| Variation (±%) | 20 | 1–100%. |
| Sweep levels | 9 | Odd integers from 3 to 21. |
| End time | 120 | At least 0.01. |

For a nonzero initial value `x₀`, a level `p` gives `x₀ × (1 + p/100)`. For example, three levels at ±20% are `−20%, 0%, +20%`, giving `0.8 x₀`, `x₀`, and `1.2 x₀`. Odd, equally spaced levels include the zero-perturbation baseline.

Only species whose initial symbol values can be resolved safely are selectable as inputs. Species controlled by unsupported assignment/algebraic initialization are excluded. Inputs are excluded from target choices.

**Zero-valued inputs need special interpretation.** Percentage changes around zero are undefined. The inspected ShapCRN fixed-grid helper uses `abs(p) × 1e-10` instead, so opposite signed levels can produce the same absolute value. The grid still has the planned number of combinations, but some trajectories can be duplicates.

#### Workload and memory limits

With `L` levels and `m` inputs, the grid contains `L^m` combinations:

| Inputs | Levels | Combinations | Within the 2,000-combination cap? |
| --- | --- | --- | --- |
| 1 | 9 | 9 | Yes |
| 2 | 9 | 81 | Yes |
| 3 | 9 | 729 | Yes |
| 4 | 9 | 6,561 | No |
| 4 | 5 | 625 | Yes |

The kinetics sweep also limits stored full trajectories to **128 MiB**. Its estimate uses 100 output rows, all model species plus time, and 8 bytes per numerical value:

```text
estimated bytes = combinations × 100 × (number of species + 1) × 8
```

Actual trajectory memory is checked after simulation as well. This is a trajectory-storage cap, not a bound on the total application's RAM usage. Reducing displayed targets does not reduce the full-species trajectory allocation. Reduce inputs or levels to reduce the grid; shortening the horizon does not reduce the estimate's fixed output-row count.

#### Read the envelopes

Each target has its own tab showing:

- **Baseline (0%)**: the trajectory for the all-zero perturbation combination of the chosen model source.
- **Minimum** and **Maximum**: the extrema across all combinations at each sampled time.
- **Perturbation range**: the shaded region between those extrema.

The envelope is a sampled range, not a confidence interval. Its boundary can switch between different combinations over time and need not be an individual simulated trajectory.

Hover information reports percentage differences from the baseline. They are shown as unavailable when the baseline magnitude is at or below the stored absolute tolerance. An unavailable percentage does not mean a missing concentration or no effect.

### Phase-space plots

Use the **Standard**, **Knock**, and **Perturbation** tabs in the phase-space section.

Select exactly **two species** for a 2D plot or **three species** for a 3D plot. Selection order defines **X, Y, Z**. Plots refresh automatically when selections change; **Refresh phase plot** is available for the standard and knock views.

Time is encoded along the trajectory rather than displayed as an axis. In the perturbation comparison, a circle marks the start, a diamond marks the end, and 3D gradients indicate progression along a curve. Hover curves or markers to inspect coordinates and time.

For **Perturbation**:

- Run both a sweep and its matching reference simulation: standard for the original source, or knock for the post-knock source.
- Choose combinations under **Perturbation trajectories**. Labels identify their input settings; the sweep baseline is excluded from this selector.
- Choose axes from species shared by the reference and sweep outputs.
- Use **Mostra solo riferimento Standard** or **Mostra solo riferimento Post-knock** to display only the reference. These controls currently retain Italian labels.

The comparison reference is the separately computed standard/knock trajectory; the envelope baseline comes from the sweep's own zero-level combination. Match horizons and numerical settings when comparing them. A reference computed over a shorter interval cannot show the later portion of a longer sweep.

Phase plotting uses at most 500 points per trajectory for display. This does not change the cached numerical experiment. For responsive comparisons, the interface recommends no more than 15 selected perturbation trajectories in 2D or 8 in 3D; these recommendations are not hard simulation limits.

A trajectory settling toward a point is consistent with convergence in the selected coordinates. A loop or crossing in a projection is not by itself proof of an oscillation or an intersection in the full state space.

## Importance and Sensitivity Analysis

This page runs a separate ShapCRN importance calculation on the **active prepared model**. It does not consume the kinetics page's cached sweep or its post-knock model. KO/KI interventions here are assessed for individual species players, rather than the combined multi-entity experiment on the kinetics page.

### Configure the analysis

1. Select **Species to perturb**: initial-value inputs defining the grid.
2. Select **Target species to observe**: outputs whose responses you want to inspect.
3. Set **Variation (±%)**, **Sweep levels**, and **End time**.
4. Select **Species included in knock experiments**: species players evaluated with individual interventions.
5. Choose **KO** or **KI** under **Knock mode**.
6. Choose a **Payoff** and click **Compute Shapley values**.

Inputs must be distinct from both targets and players. Targets and players may overlap, but self-comparisons are unavailable. The player selector initially includes the eligible non-input species; reduce it if you need a smaller analysis.

Defaults are ±20%, 9 levels, end time 120, KO, and `last` payoff. Levels are odd integers from 3 to 21; the grid is limited to 2,000 combinations. Each player adds KO/KI simulations in addition to the original-model simulations, so 2,000 combinations is not a cap on the total number of simulations across players.

| Payoff | Meaning |
| --- | --- |
| `last` | Final sampled target value at the analysis horizon. |
| `max` | Maximum sampled target value over the trajectory. |
| `min` | Minimum sampled target value over the trajectory. |

The analysis uses fixed-horizon CVODE simulations with `steady_state=False`; the final value is not necessarily an equilibrium value. The page does not expose integration-tolerance controls and does not inherit the kinetics page's tolerances. Zero-valued inputs use the same dependency fallback described for kinetics sweeps.

### Interpret Shapley attribution

The page displays raw ShapCRN attribution values derived from payoff differences across the selected perturbation grid. The difference is **original payoff minus KO/KI payoff**:

| Raw value | Interpretation |
| --- | --- |
| Positive | The original model has a greater payoff than the intervened model in the aggregate attribution. |
| Negative | The intervened model has a greater payoff than the original model in the aggregate attribution. |
| Zero | No net attribution for this target under the configured calculation. |
| Unavailable | No valid comparison, including masked player-versus-itself entries. |

A larger absolute value ranks a player as more influential for the selected target and configuration. It is not a percentage, probability, or universal biological importance score. Opposing effects across the grid can cancel. Compare rankings with the same payoff, inputs, levels, horizon, and intervention mode.

For each target, **Shapley Value Attribution** provides a bar ranking and cards for the top knock species, largest importance magnitude, intervention direction, and the associated variation statistic. Ties are reported explicitly; all-zero results report no dominant effect.

The app delegates the attribution formula to ShapCRN. In the inspected 0.2.0 implementation, it scales the sum of payoff differences by a combinatorial factor determined by the input count and combination count. The page does not enumerate all coalitions of simultaneously knocked species. Read its values as this implementation's perturbation-based attribution, rather than assuming a general coalition-based SHAP explanation.

### Target influence network

Choose **Network target** and **Network layout** to inspect the full prepared network with target-specific annotations. The legend distinguishes target, promoter, inhibitor, neutral, unavailable, mixed path, and secondary path.

Classification depends on the intervention:

| Mode | Promoter | Inhibitor |
| --- | --- | --- |
| KO | Positive attribution: removing the player lowers the payoff. | Negative attribution: removing the player raises the payoff. |
| KI | Negative attribution: fixing the player at its KI value raises the payoff. | Positive attribution: fixing the player at its KI value lowers the payoff. |

The graph classifies `abs(Shapley) ≤ 1e-8` as neutral. This is a display classification threshold, not a statistical significance test.

Annotations follow shortest directed paths toward the target. Where no directed path exists, an undirected fallback can be shown as a secondary path. Shared paths can have mixed classifications; unreachable players can retain a numerical classification without a connecting path. Click a knocked species to focus the union of its shortest paths.

**Paths show topology, not demonstrated causal mechanisms.** A promoter/inhibitor label describes the simulated intervention's payoff effect. It does not establish that every reaction on the highlighted path directly activates or inhibits the target.

### Heatmaps

Both matrices use **KO/KI players as rows** and **targets as columns**. Self-comparisons and unavailable entries are blank.

**Shapley Heatmap** colors values using `asinh(raw value / s)` to preserve sign while compressing large magnitudes. In the inspected helper, `s` is the 75th percentile of finite absolute values, falling back to 1 when the scale is empty, invalid, or nonpositive. The page reports the scale, and hovering shows the **raw value**. The transformation changes the coloring, not the underlying attribution. Colors can rescale when the displayed matrix changes.

**Variations Heatmap** shows ShapCRN's median absolute log₂ ratio of final target values between intervened and original runs across perturbations. It measures magnitude independently of whether the Shapley payoff is `last`, `max`, or `min`:

- A value near 0 indicates little multiplicative difference in final values.
- For positive nonzero values, a consistent twofold increase or decrease has absolute log₂ ratio 1.
- The statistic does not distinguish an increase from a decrease.
- Near-zero values are handled by the dependency's numerical safeguards, so ratios involving zeros need care.

This matrix is distinct from the kinetics envelope's percentage deviations. Changing the importance payoff can change Shapley values without changing the underlying definition of the variation statistic.

## End-to-end workflow

Use this procedure with your own SBML model; no bundled example model is required.

1. **Check the model.** Upload SBML XML, inspect the species catalog and prepared reaction list, and confirm initial values, units, and kinetic laws. Inspect the stoichiometric matrix and export it if needed.
2. **Establish a reference.** Run Deterministic ODE with the default tolerances and a suitable horizon. Select relevant species. Extend the horizon or use Until steady state if your question concerns long-time behavior.
3. **Inspect state-space behavior.** Choose two or three meaningful species in the Standard phase tab. Use the time courses to support interpretation of the projection.
4. **Test an intervention.** Run one KO or KI experiment first. Compare its time course with the reference before expanding to a combined multi-entity intervention.
5. **Explore initial-value sensitivity.** Choose the original or post-knock source. Start with one nonzero input, one distinct target, three levels, and ±20%. Run the sweep and inspect the baseline and range. Increase inputs or levels only as needed.
6. **Compare individual combinations.** Run the matching reference if necessary, open the Perturbation phase tab, select a few combinations, and inspect trajectories using the same axes.
7. **Rank individual species effects.** Open Importance & Sensitivity Analysis, select inputs, a target, and a small player set. Use KO and `last` initially. Read the ranking, direction, variation magnitude, and network together.
8. **Check robustness of the interpretation.** Repeat with a scientifically appropriate horizon, payoff, or grid. Record model provenance, prepared reaction identifiers, species selections, units, tolerances where applicable, and all analysis settings.

Do not treat unchanged colors or a cached-result button as evidence of a new calculation. Consult run captions when documenting results. At present, the dedicated downloadable numerical output is the stoichiometric CSV; preserve the source model and configuration outside the session for reproducibility.

## Troubleshooting

| Symptom | Likely explanation and action |
| --- | --- |
| Installation fails for the Python version | Use Python 3.12 in a fresh environment. ShapCRN 0.2.0 declares `>=3.10,<3.13`; inspect the installed version's requirements and the resolver error. |
| `ModuleNotFoundError` | Install requirements with the same interpreter used to launch Streamlit. Confirm that the intended environment is active. |
| RoadRunner or libSBML cannot be imported | Confirm that ShapCRN's transitive dependencies installed successfully. Check the native-package installation error and Python/platform compatibility. |
| The browser does not open | Headless mode is configured. Open the Local URL printed in the terminal manually. |
| Upload fails or no valid model appears | Use UTF-8 SBML XML with a valid model object. Inspect the validation message, kinetic definitions, and reversible-reaction preparation. A `.json` extension does not enable JSON conversion. |
| Kinetics appears to use an old model | Return to Overview after changing Active model, confirm the new catalog, then return to Kinetics. |
| The canvas cannot be rendered | Check that `streamlit-cytoscape==0.2.1` is installed in the active environment and restart Streamlit. Inspect any displayed import error. |
| No nodes match the graph filters | Lower Min degree and enable species/reaction visibility. |
| Scrolling zooms the network | Click Lock graph after interacting with the canvas. |
| A calculation button is disabled | Load a model and complete required selections; check grid/memory limits. Cached result active instead means a compatible calculation is already available. |
| Simulation fails | Inspect the error and the model's kinetic laws, rules, events, initial values, and units. Use finite positive tolerances and a practical horizon. |
| Steady state is not reached | The maximum time was exhausted without numerical convergence. Extend the horizon within the interface range or inspect whether the model actually exhibits settling behavior. |
| A species is unavailable as a sweep input | Its initial symbol value cannot be safely resolved or overridden. Inspect its initialization and controlling rules. |
| Perturbing a zero input gives duplicate curves | Signed percentage levels use a small absolute-value fallback and can map to identical values. Use a suitable nonzero input when percentage interpretation is required. |
| Percentage hover values show N/A | The baseline is too close to zero for meaningful relative percentage changes. Inspect absolute values instead. |
| The grid exceeds 2,000 combinations | Reduce input species or sweep levels; the count grows as `levels^inputs`. Reducing targets does not shrink the grid. |
| Trajectories exceed 128 MiB | Reduce kinetics-sweep inputs or levels. The estimate includes all species and a fixed number of output rows. |
| A KO/KI experiment fails | Read the transformation error. Unsupported dependencies, fast reactions, missing rate laws, or incompatible shared-reactant values can prevent the intervention. |
| Phase plots are unavailable | Compute the source trajectory and select exactly two or three species. Perturbation comparisons also need the matching reference and common species. |
| Plots still show previous results | Configuration changes or a failed run may retain old results. Read the caption and rerun when the requested settings are not covered. |
| A heatmap cell is blank | Self-comparisons and unavailable/nonfinite entries are intentionally left blank. This does not mean a zero effect. |

## Current limitations

- **Parameter scan** and **Scan parameter** do not perform a kinetic parameter scan. Their settings are retained and participate in standard-simulation cache matching, but are not passed as a parameter variation to the simulation engine.
- **Download Trajectories (.csv)**, **Export Report (.pdf)**, and **Export Python Script** are disabled placeholders. There is no dedicated importance-matrix export or modified-model download in the current UI. Plotly toolbar image downloads, where available, are plot images rather than exported numerical experiment data.
- The uploader advertises JSON, but the current bytes-loading path parses SBML XML.
- Models and results are session-local, without durable project persistence.
- The topbar's **LSODA Idle** is static; current inspected simulation paths use RoadRunner/CVODE.
- Some plot labels assume seconds and molar concentration; no general unit conversion is performed.
- Overview displays a reversible/irreversible breakdown using a summary key that does not match the producer's key. Treat that breakdown cautiously; inspect prepared reactions rather than using it to recover the original file's reversibility counts.
- After switching models, Overview must refresh the parsed model before kinetics work.
- Kinetics sweeps are capped at 2,000 combinations and 128 MiB of stored trajectories. Importance grids are capped at 2,000 combinations, with additional work per player; they do not use the kinetics trajectory-memory guard.
- The interface exposes deterministic simulation workflows. Dependency support for other solver modes does not make those modes selectable here.
- Dependency versions are mostly lower-bounded rather than locked. Helper defaults, supported SBML transformations, and compatible library APIs can vary between installations.

## Developer guide

### Repository structure

```text
CRN-Studio/
├── app.py                 # Persistent Streamlit shell and page routing
├── pages/                 # Overview, kinetics, and importance page bodies
├── logic/                 # Scientific adapters and result processing
├── ui/                    # Shared widgets, themes, and visualization helpers
├── tests/                 # Automated numerical-contract and UI checks
├── .streamlit/config.toml # Default theme and headless server configuration
├── requirements.txt       # Application dependency requirements
├── AGENTS.md              # Python development and documentation conventions
└── README.md              # This manual
```

`app.py` owns global page configuration, navigation, the sidebar, theme state, and the workspace topbar. Page bodies implement their scientific workflows. Keep widgets that must remain stable across navigation in the persistent shell.

The `logic` package separates scientific processing from rendering:

- `model.py` loads and prepares models and extracts species/reaction metadata.
- `crnt.py` computes complex counts, linkage classes, stoichiometric rank, and deficiency.
- `network.py` constructs the bipartite graph, stoichiometric matrices, and importance path annotations.
- `experiments.py` wraps simulation, KO/KI batches, cached trajectory processing, sweep grids, and envelopes.
- `importance.py` validates importance requests, calls ShapCRN, and aligns player/target result matrices.

The `ui` package contains shared components, the raw-file model library, light/dark palettes, Plotly styling, Cytoscape adapters and interaction guards, and phase/trajectory visualization helpers. Browser-side helpers, including `trajectory_hover.js`, support chart interaction.

### Data flow and integration boundaries

```text
Uploaded bytes → session model library → active file
             → ShapCRN/libSBML preparation → prepared model
             → metadata, stoichiometry, and network views
             → RoadRunner simulations / model interventions
             → cached trajectories → time courses, envelopes, and phase plots
             → ShapCRN importance analysis → matrices, rankings, and influence graph
```

`KnockExperimentResult` pairs a cloned modified model with its trajectory. `PerturbationSweepResult` retains full trajectories, grid levels, initial/sample values, combination metadata, baseline position, and envelopes. `ImportanceAnalysisResult` retains raw Shapley and variation matrices, grid levels, and combination count.

The importance adapter serializes the prepared model into a temporary SBML file because the dependency API takes a model path, then removes that temporary directory on exit. It does not produce a persistent report directory.

Model-content signatures and computation configurations guard result reuse. Display changes should operate on cached data; model or scientific-setting changes should trigger invalidation or a new computation. Post-knock sweeps additionally track knock-result revisions.

Some integrations use ShapCRN helpers from internal utility modules. When updating dependencies, check those imports and transformation semantics as well as the public API. Review implementation behavior rather than relying solely on legacy comments that refer to placeholders or an earlier UI skeleton.

### Run checks

With requirements installed, run the test suite from the repository root:

```bash
python -m unittest discover -s tests -v
```

The tracked tests include importance request/result contracts, Streamlit importance-page behavior, influence-graph annotations, theme tokens, and plot presentation. Run those files individually when working on the corresponding subsystem:

```bash
python -m unittest discover -s tests -p 'test_importance.py' -v
python -m unittest discover -s tests -p 'test_theme.py' -v
```

UI tests use `streamlit.testing.v1.AppTest`; some scientific calls are mocked. Passing these tests does not replace a browser check of JavaScript interaction or real-model integration. When changing those areas, manually check uploads, model switching, theme persistence, graph locking/focus, numerical workflows, cached-result messages, and 2D/3D plots as applicable.

To check dependency consistency:

```bash
python -m pip check
```

For reproducible research, record the resolved environment alongside model provenance and experiment settings. A requirements file with version ranges is not a lockfile.

### Contribution conventions

Follow [AGENTS.md](AGENTS.md): keep changes simple and targeted, avoid unnecessary abstractions, and do not reorganize unrelated code. Python classes, functions, and methods require NumPy/Pandas-style docstrings with a concise summary, applicable parameter/return/error sections, and at least one practical doctest example. Inline comments should explain non-obvious reasoning rather than restating code.

Keep this manual aligned with the implemented controls, limits, dependency behavior, and export capabilities whenever a workflow changes.
