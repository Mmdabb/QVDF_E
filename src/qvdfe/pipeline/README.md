# QVDF-E experiment pipeline

This package supplies the calibration and emission workflow that produced the verified QVDF-E experiments. The pipeline is part of the `qvdfe` package, alongside reusable formulas and the repository's later analyses. Existing frozen results are inputs for comparison, not files to overwrite.

## What can be run

| Command | Inputs | Work performed |
|---|---|---|
| `check-inputs` | Included preprocessed baseline, original-source root, MOVES-derived rate files | Verify required files and original source hashes |
| `empirical --stage all` | Same included inputs | Construct profile inputs, calibrate daily and average tracks, calculate emissions and confidence intervals, audit |
| `empirical --stage data/daily/average/metrics/audit` | Same paths; prior stages where appropriate | Resume one named stage; metrics only resamples fixed predictions |
| `surrogate` | Full average-profile parameter cards, detector cards, episode results, cubic coefficients | Compress admitted full-model curves into signed power functions |
| `pigou` | Surrogate outputs plus average-profile episodes | Solve full and compressed two-route assignments, weight sensitivity and price of anarchy |

The surrogate and Pigou commands work with the frozen calibration data in this repository. The empirical command uses the preserved baseline and source files in `data/inputs/empirical/`, together with the existing emission tables. **This is the verified baseline-reuse entry point, not an unattended raw-data bootstrap.** It reads prepared observations and verifies the original source hashes; it does not reconstruct the baseline from those originals. A new raw-data source requires explicit adaptation and reconstruction of that baseline and constitutes a separate experiment.

From the repository root, after installing its Python dependencies:

```bash
python -m qvdfe.pipeline surrogate --data data/frozen/calibration/average_weekday --output build/qvdfe_surrogate
python -m qvdfe.pipeline pigou --data data/frozen/calibration/average_weekday --surrogate build/qvdfe_surrogate --output build/qvdfe_pigou
```

For a complete empirical rerun with the bundled inputs, run from the repository root:

```bash
python -m qvdfe.pipeline check-inputs --data-root data/inputs/empirical/source_files --baseline data/inputs/empirical/baseline --emission-input data/frozen/calibration/emission_input
python -m qvdfe.pipeline empirical --data-root data/inputs/empirical/source_files --baseline data/inputs/empirical/baseline --emission-input data/frozen/calibration/emission_input --output build/qvdfe_empirical --bootstrap 400
```

Use the same output directory to resume an empirical stage. New output directories are initialized with a workflow marker; the command refuses to take ownership of an unrelated nonempty directory. Inputs and frozen data are protected against nested or ancestor output destinations. The workflow reads the bundled inputs without changing them. Input hashes and source mappings are recorded separately from the immutable release manifest in [`data/inputs/`](../../../data/inputs/).

## Input contract

The included baseline is `data/inputs/empirical/baseline/`. An alternative baseline must satisfy the same contract:

- `traffic_panel.csv.gz`: original prepared five-minute sensor observations, including raw speed, per-lane flow, sensor/date metadata and chronological holdout flags.
- `sensor_parameters.csv`: detector-specific capacity, free-flow speed, link length, jam-density and metadata flags.
- `episodes_detected.csv`: original whole-episode boundaries, recovery observations, period assignment and metadata.
- `detector_fd_calibration.csv` and `fd_estimation_protocol.json`: accepted/fallback FD fits and declared selection rules.
- `cubic_rate_coefficients.csv`: four-pollutant cubic approximation used alongside direct lookup.
- `episode_results_v2.csv`: baseline targets required by the final preservation audit.
- `input_sha256.json`: nonempty list of records with relative `path` and `sha256` fields. Paths resolve under `--data-root`; Windows separators are accepted. In the bundled copy, paths name `arizona_i10/I10-mph.csv`, `arizona_i10/I10-vol.csv`, `pems/pems_average_weekday_5min.csv.gz` and `pems/pems_link_meta.csv` under `data/inputs/empirical/source_files/`. The source bytes and hashes are unchanged; the original manifest and path mapping are recorded in `data/inputs/provenance.json`.
- `repository_reference/`: saved PeMS CBI reference outputs. Optional `cbi_*.csv` comparisons are carried forward if supplied.

The separate emission-input directory must contain `input_vehicle_type.csv` and `input_vehicle_emission_rate.csv`, following the original MOVES-derived table schema. Vehicle type 1 and normalized age shares are retained. The rerun records SHA-256 values for both rate files as well as the baseline and original source files.

The bundled preprocessing baseline and the frozen daily/average calibration folders contain traffic panels for their respective processing stages. Full calibration fields are read from `parameter_card.csv` or `parameter_card_full.csv`. A display-only parameter table without the full calibration fields is insufficient.

## Scientific conventions retained

| Item | Rule |
|---|---|
| Loading | Whole-episode volume divided by hourly capacity: $x=D/C$, in hours |
| Duration | $\widehat P=\max(f_d x^n,x)$ |
| Delay | $\widehat w_{\max}=T_f f_p\widehat P^s$, $\bar w=\theta\widehat w_{\max}$ |
| Service and queue speed | $\mu=D/\widehat P$; triangular FD with $k_j=220$ veh/mi/lane |
| Periods | AM 06–10, MD 10–16, PM 16–20, NT 20–06; assign the whole episode by its observed minimum-speed time |
| Detection | Raw speeds retained and flagged; 5-bin, degree-2 Savitzky–Golay smoothing for boundaries; minimum duration 30 min and merge gap 15 min |
| Calibration support | At least 8 eligible episodes per corridor-direction-period, then same-direction all-period fallback; otherwise unavailable |
| Residual outliers | Training-only robust residual references; 3.5-scale threshold, at least 2 of 4 votes; normalized peak delay $w_{\max}/T_f$ |
| Monthly profiles | At least 5 complete weekdays; 288 valid five-minute bins per complete day; mean flow and flow-weighted harmonic speed |
| Uncertainty | Default 400 block-bootstrap draws, deterministic retained seeds; conditional intervals, not future-observation prediction intervals |
| Profile integration | 384-node Gauss–Legendre quadrature and an analytical maximum-slope feasibility check |

The daily Arizona track fits training dates and evaluates later dates. The average-weekday track independently fits Arizona monthly profiles and the released California average profiles. Directions remain separate during estimation and are pooled only for reporting.

Replication preserves the recorded analysis cohort. Constructed-profile counts are not automatically episode-analysis counts: use the saved detector/episode support and audit tables for the actual sample. The original period aggregation is retained here for numerical replication; use the repository's separately labeled current-reporting support correction when reporting revised period totals. That reporting correction does not refit traffic parameters or change the matched episode cohort.

## Emission and validity meanings

For any rate function $r(v)$,

$$
\Gamma[r]=\frac{v_f r(v_q)-v_q r(v_f)}{v_f-v_q},\qquad
E[r]=D\left[T_f r(v_f)+\bar w\Gamma[r]\right].
$$

- **O**: observed-bin lookup reference (traffic observations combined with rates, not measured exhaust).
- **R**: reconstructed-profile lookup.
- **M**: two-state analytical emission using the direct lookup. This is the primary empirical analytical result.
- **A**: corresponding cubic-rate result, retained for smooth mathematical analysis.
- **S**: observed space-mean-speed lookup comparator.

A does not replace M. Negative $\Gamma$ and signed increments are retained. The matched comparison requires all five methods to be finite and positive for all four pollutants on the **same** admitted episodes.

Admission combines observed-data QC and outlier eligibility, a supported parameter fit, a finite-link queue constraint, nonnegative reconstructed arrivals, the supported cubic speed domain and finite positive comparison totals. The reusable response-level `valid` flag alone is not a complete empirical sample-selection rule. The pipeline retains the full check.

Surrogate and Pigou analyses use the explicitly labeled smooth cubic-rate branch. The surrogate chooses an actual participating detector nearest median capacity for each corridor-period. The Pigou experiment uses CO2 in its generalized routing cost and reports all four pollutants. Baseline and affected background vehicles remain in every objective; no low-flow continuation is introduced.

## Outputs and provenance

The empirical command writes `daily_validation/`, `average_weekday/`, `input_contract_verified.json`, `input_reuse_provenance.json`, and `workflow_audit.json`. Intermediate flags remain in episode tables so sample attrition is inspectable. The main original average-profile reference has 325 detected, 293 eligible, 286 fitted and 137 matched episodes; those are reference counts, not constraints imposed on new inputs.

Surrogate results include branch coefficients, curves, contexts, rate coefficients and hashes. Pigou results include assignments, objectives, weight sensitivities and independent solver checks. Its selected-curve overlay is written as `selected_surrogate_curves.csv` in the Pigou output; the source surrogate curves stay unchanged.

`SOURCE_PROVENANCE.json` records original file hashes, retained function hashes and portability edits. Historical filenames appear only in provenance and archived validation records. Active module names describe their functions; manuscript revision numbers do not name software components. Historical manuscript builders, unrelated runners and raw-data adapters were excluded. Formula implementations were retained; changes concern imports, explicit paths, source labels, output isolation and concise generated reporting.
