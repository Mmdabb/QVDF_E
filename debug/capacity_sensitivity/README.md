# Capacity sensitivity diagnostics

Open [the separate report](report.html) for the interpretation. This is an exploratory analysis of the preserved 137-episode sample, not a recalibrated experiment.

- `fixed_traffic_comparison.csv`: two bounds × two objectives × fixed/free capacity × 137 episodes; invalid rows remain present.
- `capacity_sweep.csv`: six capacity multipliers plus metadata, with unchanged coefficients or an algebraic duration-coefficient rescaling. All 1,918 candidate rows remain present.
- `*_metrics.csv`: pooled episode-total metrics with explicit cohort and baseline-on-the-same-rows comparisons. For increases, use `common_capacity_increases` (104 episodes); the intersection including the 0.8 decrease contains only six.
- `detector_capacity_audit.csv`: one row for every 352 detector cards, including those outside the 137-episode sample.
- `figures/`: editable SVG and preview PNG plots. Values come directly from the CSVs.
- `verification.json`: equation checks and source hashes. The independent `verify_analysis.py` checks the equations, lookup rates, objective minima, validity flags, cohort summaries and source data without importing the analysis generator.

The previous bounded FD analysis already allowed capacity changes. The free-capacity optimum here reproduces it; the new comparison is with a strictly fixed-capacity alternative. The optimization uses the observed point-speed emission proxy O, not measured vehicle emissions.

From the repository root, regenerate into a separate working directory:

```text
python debug/capacity_sensitivity/scripts/build_capacity_sensitivity.py
python debug/capacity_sensitivity/scripts/build_capacity_report.py
```

Outputs default to `debug/output/capacity_sensitivity`. Reference data and production model files are never replaced.

Verify the published results in `debug/capacity_sensitivity`:

```text
python debug/capacity_sensitivity/verify_analysis.py
```

Verify newly regenerated results in the working directory:

```text
python debug/capacity_sensitivity/verify_analysis.py --directory debug/output/capacity_sensitivity
```
