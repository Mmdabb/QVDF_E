# Detector 78: worked emission example

Start with the [six-page report](reports/QVDFE_Emission_Methods_and_Results.pdf), then the [standalone Excel workbook](workbook/Sensor78_Emission_Comparison_Simple.xlsx). The report explains the five calculations, compares their speeds and emission rates, shows cumulative emissions, and accounts for their differences. All current plotted values and editable figure sources are included here.

For the complete numerical sequence, open the [eight-step calculation guide](step_by_step/README.md). It separates speed-to-VSP arithmetic, operating-mode lookup and emission multiplication, with a diagnostic figure at each step.

This example uses the separately supplied **Arizona I-10 westbound detector-78 measurements**. It averages 16 complete weekdays in January 2016 and selects 57 five-minute bins, **14:45 inclusive to 19:30 exclusive**. It is not a reproduction of an episode in the retained 137-episode sample. The report's first two pages summarize that sample for context; the detector-78 example starts on page 3.

## Navigation

| Question | Open |
| --- | --- |
| What are the equations and results? | [Report PDF](reports/QVDFE_Emission_Methods_and_Results.pdf) |
| Can I inspect or change the calculation in Excel? | [Workbook folder and instructions](workbook/) |
| Where are the actual inputs? | [Canonical detector-78 inputs](../../data/inputs/detector78/README.md) |
| What was used for each five-minute plot? | [Common-clock series](results/common_time_series.csv) |
| What are the final emissions for all five methods and four pollutants? | [Emission totals](results/emission_totals.csv) |
| Where do the method differences enter? | [Signed error decomposition](results/error_decomposition.csv) and [method diagnostics](results/method_diagnostics.csv) |
| Can I edit the figure objects and equations? | [Main LaTeX source](reports/source/main.tex) and [figure sources](reports/source/detector78/) |
| How do I reproduce the calculations? | [Reproduction entry point](scripts/reproduce.py), with commands below |
| What was checked? | [Reproduction audit](results/reproduction_audit.json), [calculation checks](results/validation.json), [common-clock checks](results/common_time_validation.json), and [rate-boundary audit](results/simple_workbook_input_audit.json) |

The PDF and workbook are preserved delivered artifacts. The scripts use repository-relative input paths and write new files separately, so a reproduction cannot silently replace these references.

## Reproduce

From the repository root, with Python 3, NumPy and pandas installed:

```sh
python debug/sensor78/scripts/reproduce.py
```

This reconstructs the weekday profile from raw records, calculates all 20 method/pollutant totals, creates the plotted series and signed error decomposition, and creates the full compact input payload used by the Excel builder. It checks every published CSV against its reproduced counterpart and checks that the editable figure/report fragments are unchanged.

New outputs go to `debug/output/sensor78/`. The numerical tables and workbook payload are in its `detector78/` subfolder. To also compile the six-page report, install a TeX distribution with `pdflatex` on `PATH`, then run:

```sh
python debug/sensor78/scripts/reproduce.py --pdf
```

The TeX source uses standard `lmodern`, `amsmath`, `amssymb`, `booktabs`, `array`, `xcolor`, `microtype`, `geometry`, `fancyhdr`, `tikz`, `graphicx`, and `hyperref` packages. An optional `--output-dir PATH` changes the destination. Canonical input and published reference directories are protected from generated output.

The three individual calculation scripts also accept `--output-dir`; if run separately, use this order:

1. `build_detector78_appendix.py`: raw profile, fitted traffic quantities, five-method totals, native-profile figures and worked calculations.
2. `build_common_time_diagnostics.py`: conservative common-clock attribution, cumulative figures and error decomposition.
3. `build_simple_workbook_inputs.py`: compact emission-rate bands, workbook inputs and boundary checks.

These are diagnostic reproduction scripts for this fixed example. They do not recalibrate traffic parameters, redetect episodes, or overwrite the paper experiments. Their regression assertions are intentionally specific to the preserved case.

## Methods and plotting conventions

| Code | Speed and emission calculation |
| --- | --- |
| **O** | Recorded five-minute speed used as each counted vehicle's whole-link speed; sum count × link travel time × lookup rate. |
| **S** | One count-weighted harmonic mean speed, preserving O's total vehicle-hours; evaluate one lookup rate. |
| **R** | Reconstructed whole-link trip speeds by entry group, using fitted QVDF delay and lookup rates. |
| **M** | Free-flow and queue operating speeds with times that preserve fitted travel time and link distance; lookup rates. |
| **A** | Same two speeds and time allocation as M, replacing the lookup rates with fitted cubic rates. |

`S_pred` appears only as an intermediate error-accounting comparison: one speed using the same fitted vehicle-hours as R/M/A.

The common-clock plots **attribute each group's complete-link emissions to observed five-minute vehicle groups in cumulative-count order**. They do not estimate exhaust physically released during that clock interval. This preserves each original episode total. R, M and A have the same bin vehicle-hours and therefore the same equivalent whole-link speed in that plot. Their effective emission rates differ.

| Report plot | Data | Editable objects |
| --- | --- | --- |
| All five speeds; effective CO₂ rates; five-minute CO₂ contributions (page 4) | `common_time_series.csv` | `common_clock_profiles.tex` |
| Cumulative CO₂/NOₓ by vehicle share and clock time (page 5) | `common_time_series.csv`, `cumulative_*_CO2.csv`, `cumulative_*_NOx.csv`; S is linear in vehicle share | `common_cumulative.tex` |
| Emission differences (page 6) | `error_decomposition.csv`, `method_diagnostics.csv` | `common_time_pages.tex` |
| Supplementary native-clock/trip speed and rate panels | `observed_episode_profile.csv`, `reconstructed_entry_profile.csv`, `two_speed_trip_profile.csv` | `speed_rate_profiles.tex` |
| Supplementary speed-to-rate curves and cumulative panels | `rate_curves.csv`, cumulative CSVs | `rate_and_cumulative_profiles.tex` |

The last two figure sources are supporting views, retained for inspection and editing; the current six-page PDF uses the common-clock views. All figures are vector TikZ objects, not generated images. O/S/R/M/A use the same black/blue/purple/green/orange palette throughout.

## Data and assumptions

- Raw data and calibration inputs are in [`data/inputs/detector78`](../../data/inputs/detector78/README.md); they are not duplicated here. The JSON inputs include the selected PM calibration, vehicle parameters, emission-rate bands and 384 quadrature nodes.
- A retained day has 288 distinct five-minute times, speeds in `(0, 90]` mph and nonnegative counts. The weekday profile uses mean counts and count-weighted harmonic speeds. Sixteen days qualify.
- The selected window is fixed. Counts are treated as already representing one lane, with multiplier 1; they are not divided by the detector's five lanes again. Link times are recalculated as length/speed.
- Jam density is 220 vehicles/mile/lane. The example uses the PM corridor-direction calibration from 38 source episodes. The fixed 384-point quadrature and fitted delay-shape parameters are retained.
- Emission lookup uses passenger-car rates, the supplied age mixture, zero acceleration and level road. There is no interpolation between speed/VSP bands. Cubic rates retain their supplied coefficients over 5–75 mph.
- Numerical tables use grams, hours, miles and mph unless a column states otherwise. `rate_curves.csv` uses **kg/vehicle-hour for CO₂** and **g/vehicle-hour for NOₓ**, matching its displayed axes. Common-clock `rate_*_g_h` columns use g/vehicle-hour; `E_*_g` and `cum_*_g` use grams.
- `H_*` denotes vehicle-hours, `v_*` the equivalent whole-link speed, and `count_veh_5min` the bin's count. The mean free/queue times are per vehicle. `reconstructed_integration.csv` contains quadrature vehicle weights and per-node emissions.
- `simple_workbook_inputs.json` retains the full workbook-generation payload, including layout metadata and validation targets. `regression_reference.json` is a comparison target only; the scientific inputs come from the canonical input directory.

O is a detector-speed-based emission calculation, not measured tailpipe emissions or observed vehicle trajectories. The signed decomposition is order-dependent accounting; its components sum exactly, but absolute errors and WAPE do not add in the same way.
