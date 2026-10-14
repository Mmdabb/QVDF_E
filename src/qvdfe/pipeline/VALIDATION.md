# Integration validation

Verified on 2026-10-14. Generated outputs are kept under ignored `build/validation/`; no original inputs or frozen results were replaced.

| Check | Outcome |
|---|---|
| Full empirical rerun from the original preprocessed baseline | Completed with 400 bootstrap replicates |
| Original experiment audit | All 33 checks passed |
| Daily track support | 1,477 detected, 1,098 eligible/fitted |
| Average-profile support | 325 detected, 293 eligible, 286 fitted, 137 emission-matched |
| Surrogate rerun from public frozen calibration files | Completed: 44 parameter cards, 188 branch rows, 139 fitted branches |
| Full and surrogate Pigou optimization | Both completed; derivative, Wardrop, doubled-grid and independent optimizer checks passed |
| Regression against original experiment outputs | 61 CSV/gzip tables: all shared numeric and text columns match; numeric tolerance `rtol=1e-8, atol=1e-9` |
| Pipeline regression tests | 7 passed |
| Independent direct-rate comparison | Same direct lookup rates at 9,001 speeds over 0–90 mph for all four pollutants |

The 61-table regression includes point estimates, bootstrap parameter bounds, confidence intervals, episode/period outcomes, surrogate curves and routing results. It is a comparison against the original pipeline outputs, not only internal equation tests.

The only intentional output-column relocation is that Pigou selection flags now live in `selected_surrogate_curves.csv` inside the Pigou output. The source surrogate curves remain immutable. Provenance directory labels and the concise generated summary also differ, without changing numerical results.

The empirical workflow deliberately reproduces the original sample and period aggregation. Separately labeled current-reporting corrections are validated by the repository reporting tests and do not change the matched episode results. The full local empirical verification requires the external inputs listed in the input contract; CI uses the public frozen artifacts and regression tests instead.
