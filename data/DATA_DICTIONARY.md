# Data dictionary

All paths are relative to `data/`. The original release outputs (`frozen/calibration`, `frozen/transitions`, `frozen/applicability`) remain immutable. Their SHA-256 hashes are in the original `MANIFEST_SHA256.json` at the repository root. Current manuscript reporting is stored separately under `reporting/v33/`; it uses an explicit profile-support table and does not refit or overwrite the original results.

## Units used throughout

| Quantity | Unit | Typical column suffix |
| --- | --- | --- |
| Flow, capacity, service rate | veh/h/lane | `_vph`, `_vphpl` |
| Density | veh/mi/lane | `kj`, `kq`, `kc` |
| Speed | mph | `_mph` |
| Length | mi | `_mi` |
| Time, duration, delay | h, unless the column ends in `_min` (minutes) or `_s` (seconds) | `_h` |
| Loading x = D/C | h | `x_h` |
| Emission rate | g/(veh·h) at zero acceleration | `c0..c3` |
| Emissions per vehicle or per episode | g/veh or g/lane | `O_`, `M_`, `S_` columns: g per lane over the episode |
| Acceleration | m/s² | `a_down`, `a_up` |

## Sources and provenance

| Source | Used for | Terms |
| --- | --- | --- |
| Arizona I-10 westbound detectors | Daily validation and Arizona average-weekday profiles | Legacy Arizona Department of Transportation (ADOT) loop-detector data, cleaned, synchronized and post-processed for Zhou et al. (2022), *Multimodal Transportation* 1, 100017. Used for research purposes. The raw ADOT files are not redistributed, and no official ADOT release is implied |
| California PeMS average-weekday profiles | Average-weekday calibration on ten directional corridors (District 12: I-405 N/S, I-5 N/S; District 7: I-10 E/W, I-210 E/W, I-405 N/S) | Released profiles and CBI implementation at [jacky850/pems-cbi-dv](https://github.com/jacky850/pems-cbi-dv) |
| Platoon car-following experiment | Measured transitions (Section 6.6) | Provided by Prof. Rui Jiang's group, Beijing Jiaotong University. Raw trajectories are not redistributed. Derived transition records are in `frozen/transitions` |
| MOVES-derived passenger-car rates | All emission calculations | Archived lookup tables in `frozen/calibration/emission_input` and their cubic fit. The original MOVES version, analysis year and settings were not recorded, so emission results can only be reproduced starting from these derived tables |

## Files used by the core package, examples and tutorials

| File | Content | Key fields |
| --- | --- | --- |
| `frozen/calibration/cubic_rate_coefficients.csv` | Cubic zero-acceleration rate r(v) = c0 + c1 v + c2 v² + c3 v³ per pollutant | `pollutant`, `c0..c3` in g/(veh·h) with v in mph; `speed_min_mph`, `speed_max_mph` (validity 5–75 mph); fit `rate_r2`, `rate_rmse_gph` |
| `frozen/calibration/emission_input/` | Archived MOVES-derived lookup rates by operating mode and the vehicle parameters for VSP | `input_vehicle_emission_rate.csv`, `input_vehicle_type.csv` |
| `reporting/v33/arizona_episode_profile_scope.csv` | Explicit Arizona sensor-month support for current episode-based reporting | `sensor_uid`, `month`, `complete_weekdays`; 41 profiles |
| `reporting/v33/period_emission_metrics.csv` | Checked v33 planning-period and daytime pooled metrics | `window`, `sample`, `method`, `pollutant`, `N`, `R2`, `bias_pct`, `WAPE_pct`; daytime N225 |
| `frozen/calibration/average_weekday/parameter_card.csv` | Calibrated QVDF per corridor and period | `fd`, `n`, `fp`, `s`, `theta`, `alpha`, `beta` (= n s); `x_min_h`, `x_median_h`, `x_max_h`; `calibration_scope`; bootstrap intervals `*_lo`, `*_hi` |
| `frozen/calibration/average_weekday/sensor_parameters.csv` | Fundamental diagram and link of each detector | `C_vphpl`, `vf_mph`, `L_mi`, `kj`, `kc`, `omega_mph`, `lanes` |
| `frozen/calibration/average_weekday/episode_results_v2.csv` | One row per average-weekday episode (325) | Observed `P_h`, `D_veh`, `x_h`, `wt2_h`, `wbar_h`. Fitted `P_hat_h`, `mu_hat_vphpl`, `vq_hat_mph`, `wt2_hat_h`, `wbar_hat_h`, `theta`, `profile_shape_a`, `profile_family`. Flags `calibration_eligible`, `physical_predicted_pass` (Eq. 9), `matched_ladder_pass` (the 137 admitted episodes). Emissions `O_*` (recorded speeds), `M_*` (two-speed), `S_*` (single episode speed). `Gamma_cubic_*` |
| `frozen/calibration/average_weekday/traffic_panel.csv.gz` | Five-minute average-weekday profiles by sensor and month | `minute` (minute of day), `flow_vph` (veh/h/lane, arithmetic mean over days), `speed_mph` (flow-weighted harmonic mean), `days` |
| `frozen/calibration/average_weekday/period_results_v2.csv` | Planning-period totals per sensor-period | `H_h`, `V_veh`, `D_veh`, `O_H_*`, `S_H_*`, `M_H_*`, support flags |
| `frozen/calibration/average_weekday/marginal_emission_card.csv` | Elasticity and marginal-emission cards at each card's median loading (11 valid per pollutant; reproduced by `qvdfe.response`) | `x_h`, `vq`, `Gamma`, `epsilon_Gamma_x`, `beta_plus_epsilon`, `congestion_g_per_vehicle`, `toll_g_per_vehicle`, `valid` |
| `frozen/calibration/daily_validation/` | The same structure for daily Arizona episodes (holdout validation) | as above, by `date` |
| `frozen/calibration/audit/table3_reference_state.json` | Detector-78 reference state of Appendix F at full precision | `x_h`, `P_h`, `mu_vphpl`, `vq_mph`, `peak_delay_h`, `mean_delay_h`, `transition_geometry` |
| `frozen/calibration/audit/*.csv` | Exclusion ledger, reproduced metrics, null benchmark, robustness checks | regenerated identically by `reproduce/audit_numerics.py` |
| `frozen/calibration/pigou/` | Two-route illustration of Appendix E (full and surrogate functions) | `assignment_results.csv`, `network_curves.csv`, `price_of_anarchy.csv`, `weight_sensitivity.csv`, `pigou_selection.json` |
| `frozen/calibration/surrogate/` | Power-surrogate emission functions and the 32 reference cards per pollutant drawn in Fig. 12 | `figure10_reference_states.csv`, coefficients, curves |
| `frozen/transitions/corridor/` | Arizona I-10 corridor-delay records over 4.591 mi (derived; the time-space series is not shipped) | `az_detector_vs_corridor.csv` (`wt2_local_min`, `corridor_peak_delay_min`, `corridor_Tff_min`), `az_corridor_episodes.csv`, `summary.json` |
| `frozen/transitions/ks1_*` | Measured platoon transitions and their VSP-based emission components (Section 6.6) | transition records, rate configuration, summaries |
| `frozen/applicability/` | The three applicability calculations and the Fig. 7 audit | cohort shares by peak magnitudes; corridor admissibility counts; daytime-window totals and metrics |
| `examples/detector78_2016-11_*` | Small extract for `examples/02_weekdays_vs_average` (detector 78, November 2016, 12 complete weekdays) | `days.csv` (`date`, `minute`, `flow_vph`, `speed_mph`); `average.csv`; `daily_episodes.csv`; `meta.json` (source hashes). Built by `tools/make_example_extracts.py` |
