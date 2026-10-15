# Original sources and remaining reproduction inputs

The empirical traffic source files and preserved preprocessing baseline are included in [`data/inputs/`](../inputs/). They are organized there alongside their source mappings and checksums, rather than duplicated under this directory. The table below distinguishes included inputs from the sources still absent. Adding inputs does not overwrite the frozen outputs in `data/frozen/`.

| Source or location | Availability | Format | Frozen files derived from it |
| --- | --- | --- | --- |
| `data/inputs/empirical/source_files/arizona_i10/` | Included: supplied lane-speed and lane-volume files for the five westbound Arizona I-10 detectors (137, 78, 84, 139, 141), 258 weekdays of 2016, cleaned, synchronized and post-processed for Zhou et al. (2022) | `I10-mph.csv`, `I10-vol.csv` in their original supplied layouts | `data/frozen/calibration/daily_validation/traffic_panel.csv.gz`, `data/frozen/calibration/average_weekday/traffic_panel.csv.gz`, `i10_monthly_day_support.csv`, `sensor_parameters.csv` |
| `data/inputs/empirical/source_files/pems/` | Included: exact released October 2025 mean-weekday profiles for 347 links in Caltrans Districts 7 and 12, from https://github.com/jacky850/pems-cbi-dv (commit 29a3c7d9ac5af42778879172605dd4ceca4130f5) | `pems_average_weekday_5min.csv.gz`, `pems_link_meta.csv` | PeMS rows of `data/frozen/calibration/average_weekday/*` |
| `data/inputs/empirical/baseline/` | Included: prepared traffic observations, detector metadata and fits, detected episodes, original results for preservation checks, and saved PeMS CBI reference outputs | CSV, gzip CSV and JSON; see the exact pipeline input contract | Daily and average-weekday calibration/emission results |
| Platoon raw trajectories | Not included: raw 10 Hz GPS trajectories of the five ring-track runs of 25 passenger cars (Zheng, Jiang and Jia, 2023); redistribution requires the providers' written permission | One file per run with vehicle id, time, position and speed | `data/frozen/transitions/ks1_observed_transitions.csv`, `ks1_vsp_transitions.csv`, `ks1_observed_summary.json`, `ks1_vsp_summary.json` |
| `data/frozen/calibration/emission_input/` | Included: archived MOVES-derived rate and vehicle tables. Not included: the original RunSpec and export log recording version, calendar year and environmental settings | `input_vehicle_emission_rate.csv`, `input_vehicle_type.csv` | `data/frozen/calibration/cubic_rate_coefficients.csv`, `data/frozen/transitions/cubic_rate_coefficients_transitions.csv`, `data/frozen/transitions/ks1_vsp_rate_config.json` |
| Corridor time-space series | Not included: `az_corridor_series.pkl` produced by the authors' corridor-delay script; derived records remain available | Pickle as written by that script | `data/frozen/transitions/corridor/*.csv`, `summary.json` |

Notes

- The Arizona records are legacy ADOT loop-detector data that were cleaned, synchronized and post-processed for Zhou, Cheng, Wu, Li, Belezamo, Lu and Abbasi (2022), *Multimodal Transportation* 1, 100017. They are used for research purposes; do not describe them as an official or current ADOT dataset.

- The paper discloses that the original MOVES version, analysis year and environmental settings were not recorded with the supplied rate tables. The included rate tables reproduce the calculations but cannot reconstruct those missing settings.
- The daily/profile calibration and emission workflow is in `src/qvdfe/pipeline/`. Its empirical entry reuses the included preprocessing baseline and verifies the source files under `data/inputs/empirical/source_files/`. Read its [exact input contract](../../src/qvdfe/pipeline/README.md#input-contract) and portable commands. Raw preprocessing, corridor processing and platoon processing are not part of that entry point.
- Do not commit personal identifiers. The platoon records contain vehicle positions only; the detector records are aggregate counts and speeds.
