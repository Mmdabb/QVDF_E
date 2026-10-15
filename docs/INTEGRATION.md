# Integrated QVDF-E workflow

This integration starts from public release commit `b79cde22f70907280acaec6ea0391883e4c5f7b0` and the verified QVDF-E experiment implementation. It adds the executable experiment workflow while retaining the public mathematical API, teaching materials, frozen outputs and later applicability analyses.

The software is **QVDF-E** and its executable experiment workflow is `qvdfe.pipeline`. Module names describe their functions. Manuscript revision labels identify reporting snapshots and historical provenance, rather than separate software packages.

## Organization

| Location | Purpose |
| --- | --- |
| `src/qvdfe/pipeline/` | Empirical calibration/emissions, power-surrogate fitting and Pigou optimization; explicit inputs and separate outputs |
| `src/qvdfe/` | Reusable equations, exact lookup and cubic rate loaders, profile/episode screening and transitions |
| `reproduce/` | Editable figures, historical calculation reproduction and current reporting |
| `data/frozen/` | Original released results and derived inputs, plus separately documented figure inputs |
| `data/inputs/` | Preserved empirical preprocessing baseline, Arizona/PeMS source files, detector-78 calculation inputs, and separate provenance/checksums |
| `data/reporting/v33/` | Explicit current reporting support and expected aggregate metrics |
| `tests/` | Identity, scientific regression, sample selection, reporting and output-protection checks |
| `docs/validation/` | Integration's numerical comparison record; no raw observations |

The empirical engine uses functional module names for data preparation, detector calibration, model equations and calibration. Its scientific functions were preserved, with source/function hashes and portability adaptations in `src/qvdfe/pipeline/SOURCE_PROVENANCE.json`. A large refactor into the public API would make historical reproducibility harder to assess; regression tests instead establish their agreement.

## Choices made explicit

**Traffic model.** Loading remains whole-episode demand divided by hourly capacity, $x=D/C$ in hours. Calibration remains by corridor, direction and time period, with the original same-direction fallback. Raw speeds are retained and flagged; smoothed speeds support episode detection. Daily validation and average-weekday emission calibration remain separate.

**Emission rates.** Empirical M uses the original age-weighted, zero-acceleration operating-mode lookup. Cubic A is a fitted representation of the same rate table and supports smooth analytical derivatives. Both use

$$E[r]=D\left[\frac{L}{v_f}r(v_f)+\bar w\frac{v_f r(v_q)-v_qr(v_f)}{v_f-v_q}\right].$$

`load_lookup_rates()` returns pollutant-specific callable rates; `load_cubic_rates()` returns coefficients. The old `load_rates()` default stays cubic for compatibility, with an explicit `representation='lookup'` option. Neither reconstructs the missing original MOVES run settings. Negative Gamma is retained. The archived M/A values are not replaced.

**Screening.** `response.valid` checks the response's mathematical/physical domain. `screen_episode(row)` also requires upstream calibration eligibility, admissible reconstructed arrivals, rate support and finite positive O/R/M/A/S totals for all pollutants. It returns each component and failure reasons. It does not infer observation quality from a valid formula. The complete experiment workflow performs its original upstream quality checks.

**Arrival feasibility.** The reusable profile now checks the analytic minimum arrival rate, using the retained QVDF-E slope calculation. This fixes the exact-parabola endpoint case that a sampled grid can miss. The returned `lambda_min` is analytic; `lambda_min_sampled` preserves the diagnostic meaning of the old grid value. No archived matched-episode flag changes.

**Representative detectors.** Empirical episode predictions use their own detector properties. Surrogate fitting retains the participating detector nearest median capacity in each corridor-period. `load_cards()` retains the public tutorial convenience selection; use an explicit episode/reference detector for substantive comparisons rather than treating that convenience choice as a refit.

**Reporting and figures.** Original frozen results remain the historical comparison reference. Current period/daytime reporting applies the explicit v33 episode-analysis support and reproduces 225 supported daytime windows without recalibration. Four current figure layouts are ported from editable sources. Transition/corridor applicability, later-date robustness diagnostics and the original teaching examples remain available. Figure source limitations are listed in `reproduce/README.md`.

## Integration verification

Verified on 14 October 2026:

| Check | Outcome |
| --- | --- |
| Full empirical run, including 400 bootstrap draws | All 33 built-in audits passed |
| Average-profile sample | 325 detected; 293 eligible; 286 fitted; 137 matched for emissions |
| Daily sample | 1,477 detected; 1,098 eligible (924 training and 174 testing) |
| Original versus integrated outputs | 61 CSV/gzip tables compared; all common numeric/text columns agree, including confidence intervals, with numeric tolerance `rtol=1e-8`, `atol=1e-9` |
| Surrogate and full/compressed Pigou optimizations | Completed, independent solver audits passed |
| Main empirical lookup totals | All 137 episodes × four pollutants reproduced by the public API |
| Lookup implementation cross-check | Exact equality at 9,001 speeds from 0–90 mph for all four pollutants; empirical comparison still uses its stated 5–75 mph support |
| Complete saved episode mask | All 325 saved flags reproduced, including the 137 matched episodes |
| Original frozen/example files | All 118 checked against the original release manifest; no differences |
| Full figure/calculation reproduction runner | All entries passed; all 21 compared calculation/audit files agree with the original frozen references |
| Current reporting | All 48 pooled metric rows reproduce the checked v33 values; 388 profiles and 225 supported daytime windows |
| Four updated figure layouts | Rendered images match v33 locally; curve tables match; no clipping/overlap candidates in export checks |
| Tutorials and instructor notebook | All five executed successfully in memory; committed notebook sources unchanged |

The 61-table comparison is recorded in [`validation/numerical_regression.json`](validation/numerical_regression.json). One intentional schema relocation protects inputs: Pigou's selection flags now go to its own `selected_surrogate_curves.csv`, rather than modifying the input surrogate curve table. The comparison records those columns separately.

The full empirical check originally used the authors' local baseline and source files. Those empirical inputs are now included in `data/inputs/empirical/`, with source hashes, the preserved original manifest and a path mapping in `data/inputs/provenance.json`. The copied baseline manifest uses portable paths; the original source data and frozen result files are unchanged. The complete empirical rerun can therefore use the clone's inputs. This remains a baseline-reuse calculation: the command does not rebuild the original preprocessing from raw files. CI's regression tests and downstream reproductions are separate from the full 400-bootstrap empirical run.

## Reproduce the checks

```bash
python -m pip install -e '.[dev,teaching,reproduce]'
python -m pytest -q
python tools/verify_frozen_inputs.py
python reproduce/run_all.py
python reproduce/verify_current_figures.py
python tools/make_formula_code_map.py
python -m qvdfe.pipeline check-inputs --data-root data/inputs/empirical/source_files --baseline data/inputs/empirical/baseline --emission-input data/frozen/calibration/emission_input
python -m qvdfe.pipeline empirical --data-root data/inputs/empirical/source_files --baseline data/inputs/empirical/baseline --emission-input data/frozen/calibration/emission_input --output build/qvdfe_empirical --bootstrap 400
python -m qvdfe.pipeline surrogate --data data/frozen/calibration/average_weekday --output build/surrogate
python -m qvdfe.pipeline pigou --data data/frozen/calibration/average_weekday --surrogate build/surrogate --output build/pigou
```

For empirical input requirements and the 400-bootstrap command, see [`src/qvdfe/pipeline/README.md`](../src/qvdfe/pipeline/README.md). A new dataset or expanded analysis sample requires a separate scientifically reviewed run; the frozen reference tables are never silently updated.
