# Retained 137-episode diagnostic analysis

Start with the [seven-page report](reports/QVDFE_137_Episode_Error_Analysis.pdf), then use the [short episode table](results/episode_review_137.csv) to investigate individual cases. This bundle preserves the current results and the reorganized report. It does not recalibrate the model or change the paper's sample.

The [whole-experiment calculation guide](../full_experiment/README.md) now traces the preceding profile construction, screening and calibration, followed by separate VSP, lookup-rate, emission-contribution and comparison tables for all 137 retained episodes.

## Navigate by question

| Question | Start here |
|---|---|
| Why do the emission methods disagree? | [Report](reports/QVDFE_137_Episode_Error_Analysis.pdf), especially **Sources of error** |
| Which episodes have larger two-speed error than single-speed error? | [Episode review](results/episode_review_137.csv); each pollutant has its own comparison flag |
| What are every episode's rates, travel times, totals, and errors? | [Full 137-row table](results/episode_calculations_137.csv) and [column definitions](results/column_definitions.csv) |
| Can I compare one pollutant at a time? | [548 episode–pollutant rows](results/episode_pollutant_calculations_548.csv) |
| What are the pooled scores? | [Method metrics](results/comparison_metrics.csv), [traffic metrics](results/traffic_error_metrics.csv), and [matched counterfactual metrics](results/counterfactual_metrics.csv) |
| Are flat speed profiles or calibration errors associated with the gap? | [Profile groups](results/diagnostic_groups.csv), [rank correlations](results/diagnostic_correlations.csv), and [corridor diagnostics](results/corridor_diagnostics.csv) |
| Does the FD/QVDF average-speed identity hold? | [137-row identity check](results/average_speed_identity_check_137.csv) and [summary](audits/average_speed_identity_summary.json) |
| Where is the detailed checking evidence? | [Calibration audit](audits/calibration_review.json), [emission attribution audit](audits/attribution_review.json), and [recomputed quantities](audits/reproduction_checks.csv) |
| How can I edit the report or figure? | [Report template](reports/source/analysis_report_template.tex), [complete editable LaTeX](reports/source/QVDFE_137_Episode_Error_Analysis.tex), and [report builder](scripts/build_analysis_report.py) |

## Layout

- `reports/`: current PDF and editable LaTeX source. The template and Python builder produce the tables and the current vector TikZ rate-chord figure.
- `results/`: unchanged calculation tables and summary statistics.
- `audits/`: detailed reproduction, calibration, attribution, average-speed identity, and formatting evidence.
- `scripts/`: portable optional workflows for regenerating the calculations and report.
- `figures/`: editable SVG companion of the rate-chord illustration. Its layout predates the current TikZ report figure; use the report builder for the exact current report style.
- `provenance.json`: input locations and SHA-256 fingerprints. Common inputs remain in `data/`, without duplicate copies here.

## Inputs and interpretation

The analysis selects `matched_ladder_pass == True` from [the frozen episode results](../../data/frozen/calibration/average_weekday/episode_results_v2.csv). The retained sample contains 137 episodes, 118 detector/date profiles, and 4,800 five-minute bins; 20 episodes are Arizona I-10 and 117 are California PeMS. It is a fitted average-profile sample, not an independent daily holdout sample.

The [traffic panel](../../data/frozen/calibration/average_weekday/traffic_panel.csv.gz), [cubic coefficients](../../data/frozen/calibration/average_weekday/cubic_rate_coefficients.csv), and [compact detector calculation inputs](../../data/inputs/detector78/calculation_inputs.json) supply the archived profiles, rates, and quadrature. The independent attribution check also loads the [original MOVES input tables](../../data/frozen/calibration/emission_input/) through the maintained QVDF-E rate loader. Input provenance is documented in [the shared input guide](../../data/inputs/README.md).

The comparison reference **O** treats recorded five-minute detector speeds as link speeds; it is an emission proxy, not measured exhaust or independently observed vehicle trajectories. **S** uses observed mean travel time, whereas **R/M/A** use calibrated delay. **S_pred** is an additional same-predicted-travel-time diagnostic, not a sixth original method. WAPE sums absolute episode errors before division by summed reference emissions; signed total bias permits cancellation. No new equal-episode average-error table is included.

Correcting mean delay is a counterfactual with fixed fitted queue speed and rates. It has 133 mean-admissible cases and 110 fully admissible profiles; the report labels each comparison's sample explicitly. The average-speed identity check recomputes FD/QVDF inputs and tests 53,019 locations, including all peaks and endpoints. All 137 cases pass the identity and finite-link checks; this is internal consistency rather than trajectory validation.

## Reproduce

Run from the repository root with Python 3.10 or newer. Install the repository and optional PDF-reading dependency:

```text
python -m pip install -e ".[reproduce]"
python debug/episodes_137/scripts/analyze_episodes.py
python debug/episodes_137/scripts/review_calibration.py
python debug/episodes_137/scripts/attribution_review.py
python debug/episodes_137/scripts/check_speed_identity.py
python debug/episodes_137/scripts/verify_results.py
```

All generated files go to `debug/output/episodes_137/`; checked-in references stay unchanged. Each script accepts `--output PATH`. That destination must be empty or already owned by this workflow, and must be outside the protected source/reference folders. The main table workflow delegates to [the maintained analysis implementation](../../reproduce/episode_error_audit.py), avoiding a second scientific implementation.

To typeset the report, install a LaTeX distribution with `pdflatex`, `lmodern`, `amsmath`, `amssymb`, `booktabs`, `array`, `tabularx`, `xcolor`, `microtype`, `fancyhdr`, `tikz`, `graphicx`, and `hyperref`:

```text
python debug/episodes_137/scripts/build_analysis_report.py --results debug/output/episodes_137
```

The PDF and complete generated `.tex` appear under `debug/output/episodes_137/reports/`. Omit `--results` to rebuild directly from bundled reference tables, or supply `--pdflatex PATH` if the compiler is not on PATH. The builder checks page count and typesetting diagnostics; inspect any changed layout visually before replacing a reference report.

## Release checks

The portable workflows reproduce all 11 result CSVs, the detailed reproduction-check CSV, and four numerical JSON reports at `rtol=atol=1e-10`. The 137×20 archived method totals agree with direct recomputation to a maximum relative discrepancy of `6.44e-13`. The portable report builder compiles seven pages with no layout warnings. See [bundle verification](audits/bundle_reproduction_check.json) and [the original visual/layout audit](audits/readability_revision_audit.json).

Only the current analysis is published. Superseded backups, temporary build files, cache directories, ZIP duplicates, and the withdrawn average-error table are omitted.
