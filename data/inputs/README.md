# Inputs for empirical replication and emission diagnostics

This folder adds the inputs needed to run the QVDF-E empirical workflow from a clone. It also supplies the separate detector-78 worked example. The original calibration results, full daily/average five-minute panels and MOVES-derived rate tables remain in `data/frozen/`; they are referenced below instead of duplicated.

## Where each input belongs

| Location (relative to repository root) | Contents and use |
| --- | --- |
| `data/inputs/empirical/source_files/arizona_i10/` | Original supplied `I10-mph.csv` and `I10-vol.csv`, kept byte-for-byte. These are lane-speed and lane-volume inputs from the legacy cleaned Arizona records. |
| `data/inputs/empirical/source_files/pems/` | Exact released five-minute average-weekday profiles and link metadata used in the experiment. Source: [PeMS CBI-DV](https://github.com/jacky850/pems-cbi-dv/tree/29a3c7d9ac5af42778879172605dd4ceca4130f5). |
| `data/inputs/empirical/baseline/traffic_panel.csv.gz` | Prepared five-minute traffic observations used to construct the daily and average calibration tracks. |
| `data/inputs/empirical/baseline/sensor_parameters.csv` | Detector/link properties and retained fundamental-diagram parameters. |
| `data/inputs/empirical/baseline/episodes_detected.csv` | Whole-episode boundaries, observations, period assignments and eligibility metadata. |
| `data/inputs/empirical/baseline/detector_fd_calibration.csv` and `fd_estimation_protocol.json` | Detector fit outcomes and the rules used to select them. |
| `data/inputs/empirical/baseline/cubic_rate_coefficients.csv` | Preserved cubic approximation of the emission rates. |
| `data/inputs/empirical/baseline/episode_results_v2.csv` | Earlier reference results used by the preservation audit; these are distinct from the final average-weekday comparison cohort. |
| `data/inputs/empirical/baseline/input_sha256.json` | Portable paths and unchanged checksums of the four source files. Paths resolve under `source_files/`. |
| `data/inputs/empirical/baseline/repository_reference/` and `cbi_*.csv` | Saved PeMS CBI reference outputs and comparisons. |
| `data/frozen/calibration/emission_input/` | Original supplied MOVES-derived vehicle and emission-rate tables. |
| `data/frozen/calibration/average_weekday/` | All 325 saved episode records, the full prepared five-minute panel, sensor parameters, QVDF calibration cards and cubic coefficients. The flag `matched_ladder_pass` selects the retained 137-episode comparison. |
| `data/frozen/calibration/daily_validation/` | Daily Arizona panels, calibration parameters, episode results and holdout information. |
| `data/inputs/detector78/` | January detector-78 source records, date support, average profile, selected window, calibrated inputs, rate bands and integration nodes. See its [input guide](detector78/README.md). |

The empirical command starts from the preserved preprocessing baseline. It verifies the original source-file hashes, then constructs and fits the calibration tracks. It does **not** reconstruct that baseline directly from raw files. The detector-78 example uses separately supplied January records and is not a replacement for the 137-episode sample.

## Check the inputs

From the repository root, after `pip install -e .`:

```bash
python tools/verify_input_data.py
python tools/verify_frozen_inputs.py
python -m qvdfe.pipeline check-inputs --data-root data/inputs/empirical/source_files --baseline data/inputs/empirical/baseline --emission-input data/frozen/calibration/emission_input
```

`MANIFEST_SHA256.json` in this folder lists new data and the existing frozen inputs reused by these analyses. It is separate from the immutable original release manifest. `provenance.json` preserves the original source manifest and maps its historical paths to the included files. Only path fields in the copied baseline manifest were changed; numerical source files were not edited. Detector-78 provenance separately records the removal of local computer paths and unused workbook outputs.

## Run the empirical calculation

```bash
python -m qvdfe.pipeline empirical --data-root data/inputs/empirical/source_files --baseline data/inputs/empirical/baseline --emission-input data/frozen/calibration/emission_input --output build/qvdfe_empirical --bootstrap 400
```

Use `--stage data` to construct and check the two traffic tracks without recalibrating QVDF parameters or emissions. Other stages and calculation assumptions are described in the [pipeline guide](../../src/qvdfe/pipeline/README.md).

## Reproduce the 137-episode error analysis

```bash
python reproduce/episode_error_audit.py
```

The command writes episode-level calculations, pollutant-specific comparisons, delay diagnostics, WAPE tables and source-reproduction checks to `reproduce/output/episode_error_audit/`. It uses the unchanged frozen average-weekday traffic and episode files plus the exact rate bands and 384 integration nodes in the detector-78 calculation inputs. The latter are shared numerical inputs; no detector-78 observed profile is substituted into the 137-episode sample. To choose a separate empty output directory, pass `--output`.

The five main methods retain their meanings: recorded-speed reference O, reconstructed-speed R, two-speed lookup M, two-speed cubic A, and observed-mean-speed S. The additional `S_pred` diagnostic uses predicted vehicle-hours. Errors are relative to the recorded-speed emission proxy, not measured tailpipe emissions. This input release changes no published result or sample mask.

## Source terms and remaining limits

See [the data notice](../NOTICE.md). Code licensing does not replace the original providers' data terms. Arizona inputs are legacy cleaned research records, not an official ADOT release; the California files retain their PeMS provenance. Raw platoon trajectories and the corridor time-space pickle belong to separate analyses and are not included in this empirical input bundle. The original MOVES RunSpec/version/environment settings were not recorded; the supplied rate tables remain the reproducible starting point for emissions.
