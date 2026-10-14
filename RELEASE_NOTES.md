# Release notes

## v1.1.0 (integration branch)

- Added the portable v19 empirical calibration/emission, surrogate-fit and Pigou optimization workflow. External preprocessing/data requirements are explicit; raw restricted data are not added.
- Added the original zero-acceleration lookup-rate loader for empirical method M. The named cubic loader and backward-compatible default remain available for approximation A and derivatives.
- Added complete downstream episode-screening diagnostics and analytic minimum-arrival checks, including the exact-parabola endpoint case.
- Ported the current editable overview, US06 rate comparison, fixed-parameter Gamma and calibration figures, with consistent styling and export checks.
- Added the explicit v33 reporting sample and pooled period/daytime summaries without changing the original frozen results.
- Retained tutorials, finite-transition/corridor analyses, numerical audits, the mathematical API and original release data; added automated scientific checks.

## v1.0.0

First public release:

- `src/qvdfe`: core functions for bottleneck episodes, two-speed emissions, demand-dependent response and finite transitions.
- `teaching/`: four tutorials, exercises, instructor solutions and advanced readings.
- `examples/`: three runnable examples with expected results.
- `reproduce/`: entries that regenerate the paper's supported figures, applicability calculations and numerical audit from the frozen data.
- `tests/`: identity and conservation tests, and reproduction of published values.
- `FORMULA_CODE_MAP.md`, `data/DATA_DICTIONARY.md` and an optional dashboard in `docs/`.
- Licence: the code is under the MIT License; the authors make no claim on the data.
