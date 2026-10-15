# Whole experiment: step-by-step calculation results

**The 137 episodes are the common emission-comparison sample.** The average-profile experiment starts with 325 detected episodes. Traffic calibration, daily validation, reporting-period totals and the other experiments have their own samples. This guide follows the calculations in order and keeps those samples explicit.

Every numbered folder contains numerical results, a short explanation of the equations and assumptions, and a diagnostic figure with an editable SVG. You can follow the calculations without reading the scripts. Existing calibration and scientific results are preserved; newly calculated intermediate values are checked against them.

| Step | Open | Main results to inspect |
|---|---|---|
| 1 | [Inputs and constants](steps/01_inputs/README.md) | Source-file inventory, baseline support and fixed numerical settings |
| 2 | [Prepared traffic profiles](steps/02_prepared_profiles/README.md) | Monthly mean counts, harmonic speeds, smoothing inputs and daily split |
| 3 | [Whole episodes and screening](steps/03_episode_detection/README.md) | Observed targets, outlier residuals, eligibility and every exclusion decision |
| 4 | [Calibration](steps/04_calibration/README.md) | Fit membership, period/fallback coefficients, confidence intervals and predictions |
| 5 | [Physical admission](steps/05_physical_admission/README.md) | All 325 records, queue-speed calculation, finite-link limit and time allocation |
| 6 | [Construct VSP and emission rates](steps/06_rate_construction/README.md) | Vehicle coefficients, age-weighted rates, speed-to-VSP arithmetic and cubic terms |
| 7 | [Recorded and single-speed calculations](steps/07_observed_and_single_speed/README.md) | 4,800 observed bins; VSP, rate lookup and emission multiplication in separate tables |
| 8 | [Reconstructed and two-speed calculations](steps/08_reconstruction_and_two_speed/README.md) | 52,608 modeled groups, separate VSP/rate tables, free/queue contributions and VSP differences |
| 9 | [Episode totals and comparison](steps/09_totals_and_comparison/README.md) | 548 episode–pollutant calculations, all 2,740 method totals, and pooled error numerators/denominators |
| 10 | [Other experiment branches](steps/10_other_experiments/README.md) | Daily validation, period/day totals, CBI, Gamma/power approximation, Pigou and transitions |
| 11 | [Every episode at five-minute resolution](steps/11_episode_time_series/README.md) | Separate traffic/four-pollutant pages for all 137 episodes; one table per page, collapsible navigation and offline equations |

The [local dashboard](steps/11_episode_time_series/index.html) also links separate pages for traffic parameters, inverse-emission queue speeds, backward FD calculations, bounded pairs and their summary. The [capacity comparison](steps/11_episode_time_series/fd_capacity_comparison.html) adds a strict fixed-capacity alternative to the existing bounded analysis, which already permitted capacity changes. The [separate capacity sensitivity report](../capacity_sensitivity/report.html) propagates those changes through the traffic equations. These diagnostic alternatives preserve the original experiment results.

## How the emission sample is formed

| Stage | Remaining average-profile episodes |
|---|---:|
| Detected | 325 |
| Hard quality checks pass | 294 |
| Outlier checks pass | 293 |
| Supported calibration available | 286 |
| Predicted queue fits within the link | 137 |
| Closed profile, rate domain and all five methods available | 137 |

The 137 comprise **20 Arizona and 117 California episodes**, from 118 detector/profile combinations. The separate daily track has **1,477 detected episodes**, with 924 eligible training and 174 eligible testing episodes. Traffic-fit scores use eligible finite pairs, rather than the final emission sample. See step 3 for the complete ledger.

## Following one calculation

Use `episode_id` to join steps 3–9. Within an episode, `bin_index` identifies an observed five-minute interval and `node_index` identifies a modeled integration group. Add `pollutant` when joining rate and emission tables. Integration nodes are not five-minute observations.

The calculation sequence is **speed → VSP → operating-mode lookup → rate × vehicle-hours → episode total**. The two-speed calculation has separate free-flow and queue operating speeds and times. Its equivalent whole-link speed is used for comparison plots; it does not replace either operating speed in VSP or rate calculation.

| Method | Speed supplied to VSP/rate calculation |
|---|---|
| O | Each recorded five-minute speed, used as a whole-link speed proxy |
| S | One observed count-weighted harmonic mean speed |
| R | A reconstructed whole-link speed for each modeled group |
| M | Free-flow speed and FD queue speed, with their respective travel times |
| A | The same speeds and time allocation as M; cubic rates replace direct lookup |

All VSP calculations use the supplied passenger-car coefficients, zero acceleration and level road. An exposure-weighted mean VSP is generally different from VSP evaluated at an average speed. Similar VSP values can fall in different speed/VSP bins, while different VSP values can share one emission rate. Step 8 therefore reports VSP distribution differences and operating-mode exposure differences separately. These compare model representations with O; they are not errors against measured vehicle-level VSP or exhaust.

## Files, figures and reproducibility

- CSV files contain full-precision values; equations and units are in each guide. Large node tables are compressed as `.csv.gz`. Decompress them to open in Excel; their adjacent 24-row previews are only previews, not the full sample.
- Figures are generated from the included numerical results with plotting code. PNGs provide previews and SVGs retain editable vector objects. Colors are consistent across methods: O black, S blue, R purple, M green and A orange.
- Original raw files and the prepared baseline are linked rather than duplicated. The preserved pipeline starts from that baseline: this trace does not claim to reconstruct it independently from the original raw sources.
- Parameter and bootstrap estimates remain frozen. This is an arithmetic and provenance trace, not a new calibration or experiment sample.

Run from the repository root after installing its Python dependencies:

```sh
python debug/full_experiment/scripts/build_precalibration_trace.py
python debug/full_experiment/scripts/build_emission_steps.py
python debug/full_experiment/scripts/build_other_experiment_trace.py
python debug/full_experiment/scripts/build_episode_time_series.py
```

Outputs go to separate subfolders of `debug/output/full_experiment/`. Checks are recorded in [step 4](steps/04_calibration/06_trace_reconciliation.csv), the [emission trace audit](audits/emission_trace_audit.json), and the [other-branches audit](steps/10_other_experiments/arithmetic_audit.json).

For a smaller worked calculation, use [detector 78](../sensor78/step_by_step/README.md). For a case with close traffic estimates but a much larger two-speed emission error, use [detector 141's November profile](../case_studies/az_i10_detector141_november/README.md).
