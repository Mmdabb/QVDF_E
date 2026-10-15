# Detector 78 calculation inputs

These files contain the inputs used for the five-method emission example for Arizona I-10 westbound detector 78. They include the supplied January 2016 measurements, the selected traffic calibration, the emission-rate mapping and numerical integration inputs. All numerical values retain their source precision.

## Files

| File | Contents |
| --- | --- |
| `raw_5min.csv` | All 5,999 supplied five-minute records across 21 weekdays, including incomplete days. No records were dropped from this file. |
| `date_support.csv` | Supplied day-level completeness and retention flags. |
| `raw_source.json` | The same raw records and date support, source row locations and original input cautions. |
| `average_weekday_profile.csv` | The existing 288-bin average-weekday profile, copied without alteration. |
| `episode_profile.csv` | The 57 selected bins used by the worked example. |
| `calibration_inputs.json` | The detector traffic card, PM corridor calibration, vehicle/VSP parameters, normalized age weights, supplied passenger-car rates, cubic coefficients and integration controls. |
| `calculation_inputs.json` | The compact traffic inputs, 57-bin profile, exact rate bands, cubic coefficients, 384 integration nodes, delay-profile equations and time-attribution rules. |
| `emission_rate_bands.csv` | The same nine positive-speed lookup bands in readable CSV form. |
| `quadrature_384.csv` | The same 384 Gauss-Legendre nodes and weights on the unit interval. |
| `provenance.json` | Source hashes, repository references, publication changes and verification results. |

The JSON and CSV views contain the same inputs. The JSON files are the complete machine-readable input definitions; the CSV exports make individual tables easier to inspect.

## Sample and averaging

A day is retained when it has 288 rows, 288 unique five-minute times, positive speeds no greater than 90 mph and nonnegative counts. All retained dates are weekdays. Sixteen days satisfy these conditions. At each time of day, the count is the arithmetic mean across those days and speed is the count-weighted harmonic mean:

```text
d_i = sum_d(count_di) / 16
v_i = sum_d(count_di) / sum_d(count_di / speed_di)
```

The selected window is **14:45 inclusive to 19:30 exclusive**, giving 57 five-minute bins. It is fixed for this worked example. Changing input measurements does not automatically detect new episode boundaries. The complete daily profile is included so the surrounding traffic conditions remain inspectable.

Counts retain the original explicit assumption that they represent one lane. The volume multiplier is 1. They are not divided by the detector's five lanes again. The supplied `source_travel_time_h` column does not consistently equal `length_mi / speed_mph`; calculations use the latter relationship. The `source_retained_date` and `source_travel_time_h` columns remain in the raw CSV as supplied evidence, not as corrected calculation inputs.

## Calibration and emission rates

The selected calibration is for the **AZ_I10_W corridor, PM period**, using 38 source episodes. Detector length, capacity and free-flow speed come from the retained detector card. The corresponding complete repository sources are:

- [Average-weekday sensor parameters](../../frozen/calibration/average_weekday/sensor_parameters.csv)
- [Average-weekday calibration parameters](../../frozen/calibration/average_weekday/parameter_card.csv)
- [Cubic emission-rate coefficients](../../frozen/calibration/average_weekday/cubic_rate_coefficients.csv)
- [Supplied vehicle parameters](../../frozen/calibration/emission_input/input_vehicle_type.csv)
- [Supplied emission rates](../../frozen/calibration/emission_input/input_vehicle_emission_rate.csv)

Rates use the supplied passenger-car age mixture, zero acceleration and zero grade. Speed is in mph and rates are in grams per vehicle-hour. For positive speed, select the last rate-table row whose lower speed boundary is no greater than that speed. Do not interpolate between bands. The first band excludes zero, and a blank final upper boundary means no finite upper limit. The cubic approximation uses its supplied coefficients over 5–75 mph; editing lookup values does not refit that approximation.

The original MOVES RunSpec, version, analysis year and environmental settings were not recorded with the supplied rate export. They are not reconstructed or inferred here.

## Relation to the 137-episode analysis

This worked example uses the separately supplied sensor-78 measurements. Its averaged counts and speeds differ from the archived January profile. It must not be treated as a reproduction or replacement of an episode in the 137-episode comparison. The original archived sensor-78 January episode fails the fitted finite-link screen; validity of the worked example must be calculated from its own inputs.

The 137-episode analysis uses the [full frozen average-weekday episode table](../../frozen/calibration/average_weekday/episode_results_v2.csv), selecting `matched_ladder_pass == True`, together with the [full five-minute traffic panel](../../frozen/calibration/average_weekday/traffic_panel.csv.gz). Its compact rate lookup and quadrature are the same `rate_table` and `quadrature_384` arrays supplied in `calculation_inputs.json`. No additional episodes or traffic bins were selected for publication.

Five-minute plots for reconstructed and two-speed methods attribute complete-link trip emissions to observed vehicle groups in cumulative-count order. They are not measurements of instantaneous roadway exhaust. The exact conservation rule is recorded in `common_time_alignment` in `calculation_inputs.json`.

## Provenance and verification

The original workbook is identified by filename and SHA-256 in `provenance.json`; it is not needed to use these extracted inputs. Absolute local paths were removed. Historical source paths are retained only in that provenance record.

The release check verified all 5,999 raw CSV rows against the source JSON without numeric rounding, reconstructed the 288-bin profile from the 16 retained days, checked the selected 57 bins and verified the selected PM parameters against the original calculation record. The complete original workbook and calculated result arrays are excluded from this input bundle.

These Arizona observations are legacy detector records cleaned and post-processed for research. They are not represented as a current or official ADOT data release. See the repository's [original-data notes](../../original/README.md) for source attribution.
