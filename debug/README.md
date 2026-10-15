# QVDF-E experiment diagnostics

Start with the reports below. The supporting tables, editable figures, calculation scripts and checks are organized by analysis. You can inspect the delivered results without running any code.

| What you want to check | Open |
| --- | --- |
| Follow the whole experiment from inputs through calibration, VSP, lookup and emissions | [Step-by-step experiment results](full_experiment/README.md) |
| Inspect five-minute speed, travel time, delay, VSP and emissions for each of the 137 episodes | [Individual episode time series](full_experiment/steps/11_episode_time_series/README.md) |
| Sort episodes by traffic error and compare method errors beside each figure | [Local HTML dashboard](full_experiment/steps/11_episode_time_series/index.html) · [All error metrics CSV](full_experiment/steps/11_episode_time_series/all_error_metrics.csv) |
| Compare observed/fitted traffic, QVDF coefficients and FD inputs | [Traffic parameters](full_experiment/steps/11_episode_time_series/traffic_parameters.html) |
| Find emission-target queue speeds and inspect their FD consequences | [Inverse emissions](full_experiment/steps/11_episode_time_series/inverse_emissions.html) · [Three backward FD calculations](full_experiment/steps/11_episode_time_series/inverse_fd.html) |
| Inspect bounded density/wave-speed pairs and compare their feasibility | [Episode-level pairs](full_experiment/steps/11_episode_time_series/fd_sensitivity.html) · [Sensitivity summary](full_experiment/steps/11_episode_time_series/fd_summary.html) |
| Compare strictly fixed capacity with capacity allowed to vary | [Side-by-side dashboard](full_experiment/steps/11_episode_time_series/fd_capacity_comparison.html) |
| Follow capacity changes through traffic predictions and emissions | [Separate capacity sensitivity report](capacity_sensitivity/report.html) |
| Follow every calculation for detector 78, including separate VSP and lookup tables | [Detector 78 calculation steps](sensor78/step_by_step/README.md) |
| Inspect a case with close traffic estimates but much larger two-speed emission error | [Detector 141 November case](case_studies/az_i10_detector141_november/README.md) |
| Why the emission methods differ across 137 episodes | [137-episode analysis guide](episodes_137/README.md) |
| Delay calibration, equal-travel-time emission differences and error decomposition | [137-episode report](episodes_137/reports/QVDFE_137_Episode_Error_Analysis.pdf) |
| Individual episode calculations and the average-speed identity check | [137-episode results](episodes_137/results/) |
| How all five methods work for detector 78 | [Detector 78 guide](sensor78/README.md) |
| Speed, emission-rate, five-minute emission and cumulative profiles | [Detector 78 report](sensor78/reports/QVDFE_Emission_Methods_and_Results.pdf) |
| Change detector 78 inputs and inspect cell formulas | [Excel workbook and source guide](sensor78/workbook/README.md) |
| Locate the original traffic, calibration and emission inputs | [Shared input inventory](../data/inputs/README.md) |

The local dashboard has **one main results table per page**. Its left sidebar contains collapsible sections for the episode overview, parameter comparisons and FD diagnostics. Within a case, traffic and each of the four pollutants have separate pages, each pairing its figure with one error table. The navigation can be hidden to give wide tables more space. Equations use native MathML: the pages work offline without a math-rendering service or external scripts. Open the HTML files locally; the Markdown case list remains available for browsing directly on GitHub.

## Folder layout

```text
debug/
  full_experiment/   Eleven calculation stages, including all 137 individual time series
  capacity_sensitivity/  Separate capacity analysis, numerical results and HTML report
  case_studies/     Additional worked examples, reports, plots and calculation sources
  episodes_137/
    README.md       Reading order, file descriptions and rerun commands
    reports/        Current report and editable report source
    results/        Episode calculations, comparison tables and speed-identity check
    audits/         Independent calibration, attribution and reproduction checks
    scripts/        Calculation, verification and report-generation code
    figures/        Editable supplementary figure
  sensor78/
    README.md       Worked-example assumptions and rerun commands
    reports/        Current report and editable vector figure sources
    results/        Profiles, five-minute contributions, totals and diagnostics
    scripts/        Calculation, figure and report-generation code
    workbook/       Standalone Excel workbook, source and validation
    step_by_step/   Eight numbered calculation stages, VSP/lookup tables and diagnostics
  MANIFEST_SHA256.json
  verify_package.py
  output/           Local regenerated files; excluded from Git
```

The committed reports and results are reference copies. Rerun commands write under `debug/output/`, keeping the reference results and shared inputs unchanged. Each analysis guide identifies its input files and exact commands. The normal package installation is described in the [repository README](../README.md); PDF rebuilding additionally requires a local LaTeX installation. Workbook generation and recalculation requirements are described in its own guide.

## How to interpret these analyses

- The **137-episode analysis** uses the retained matched comparison sample from the frozen average-weekday experiment. It includes the latest FD/QVDF average-speed consistency check. The report retains WAPE; the withdrawn average-error table is not included.
- The **detector 78 example** uses the separately supplied January records: 16 complete weekdays form the average profile and 57 five-minute bins form the selected window. It is a worked example, not a replacement for an episode in the 137-case sample.
- **O** combines recorded five-minute point speeds with emission lookup rates. It is a calculation reference, not measured exhaust or observed whole-link trajectories. **S** uses observed mean trip speed; **R** uses reconstructed trip speeds; **M** uses two operating speeds with lookup rates; **A** uses the corresponding cubic rates. `S_pred` is an additional diagnostic using predicted vehicle-hours.
- The common-clock plots align modeled groups to observed vehicle-count bins. They preserve totals; their timing is illustrative rather than independently measured. Signed error components add to total bias, not to WAPE, and are not separately identified causal effects.
- The average-speed identity check verifies distance/time consistency and nonnegative state times within the fitted model. It does not validate that model against measured vehicle trajectories.
- The inverse analysis uses one common queue speed per episode, selected either for CO₂ or for equal-weight relative errors across four pollutants. Conditional discharge, wave-speed and jam-density calculations show the consequences. The existing bounded analysis already permits capacity changes when needed to reach the best emission objective; preserving capacity is a secondary choice among equally good emission solutions.
- The new capacity comparison adds a **strictly fixed-capacity alternative**, holding the fitted traffic quantities fixed in both alternatives. The separate capacity report then propagates capacity changes through the traffic equations and reports feasibility and errors on common cohorts. These diagnostics preserve the archived calibration and do not establish independently observed FD parameters.

## Verify the package

From the repository root:

```bash
python debug/verify_package.py
python debug/verify_calculation_steps.py
python debug/verify_dashboard_metrics.py
python debug/verify_parameter_diagnostics.py
node debug/verify_parameter_page.js
python tools/verify_input_data.py
python tools/verify_frozen_inputs.py
```

The JavaScript check requires Node.js 22 and executes the page controls against a static DOM substitute; it does not open a browser or assess visual layout.

The debug manifest covers the delivered reports, result tables, guides and code. The original frozen-data and input manifests are separate. Source records and portability changes are documented within each analysis folder. Data and derived analysis tables retain their original provider terms; see [the data notice](../data/NOTICE.md).
