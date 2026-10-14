# Original data (to be added by the authors)

The frozen outputs in `data/frozen/` were derived from the sources below. Place the originals in the folders listed, keep file names stable, and add the licence or permission note of each provider. Nothing in the frozen folders is overwritten by adding originals.

| Folder | What to add | Format expected | Frozen files derived from it |
| --- | --- | --- | --- |
| `arizona_i10_5min/` | Legacy ADOT loop-detector records for the five westbound Arizona I-10 detectors (137, 78, 84, 139, 141), 258 weekdays of 2016, as cleaned, synchronized and post-processed for Zhou et al. (2022); research use only, no official ADOT release implied; detector mileposts | one CSV per detector or per month with columns date, time (5-min bin), lane, count, speed; a detector table with milepost and lane count | `data/frozen/calibration/daily_validation/traffic_panel.csv.gz`, `data/frozen/calibration/average_weekday/traffic_panel.csv.gz`, `i10_monthly_day_support.csv`, `sensor_parameters.csv` |
| `pems/` | Pointer only: the released October 2025 mean-weekday profiles for 347 links in Caltrans Districts 7 and 12 and the CBI implementation are at https://github.com/jacky850/pems-cbi-dv (commit 29a3c7d9ac5af42778879172605dd4ceca4130f5) | leave the files in that repository; add a `SOURCE.md` with the commit and download date | PeMS rows of `data/frozen/calibration/average_weekday/*` |
| `platoon/` | Raw 10 Hz GPS trajectories of the five ring-track runs of 25 passenger cars (Zheng, Jiang and Jia, 2023), with the written permission of the data providers | one file per run with vehicle id, time, position, speed | `data/frozen/transitions/ks1_observed_transitions.csv`, `ks1_vsp_transitions.csv`, `ks1_observed_summary.json`, `ks1_vsp_summary.json` |
| `moves_rates/` | The MOVES rate tables as exported (`input_vehicle_emission_rate.csv` and the vehicle inputs), the MOVES RunSpec and the export log that records version, calendar year and environmental settings | as exported from MOVES | `data/frozen/calibration/cubic_rate_coefficients.csv`, `data/frozen/transitions/cubic_rate_coefficients_transitions.csv`, `data/frozen/transitions/ks1_vsp_rate_config.json` |
| `corridor/` | If available, the time-space corridor series (`az_corridor_series.pkl`) produced by the authors' corridor-delay script | pickle as written by that script | `data/frozen/transitions/corridor/*.csv`, `summary.json` |

Notes

- The Arizona records are legacy ADOT loop-detector data that were cleaned, synchronized and post-processed for Zhou, Cheng, Wu, Li, Belezamo, Lu and Abbasi (2022), *Multimodal Transportation* 1, 100017. They are used for research purposes; do not describe them as an official or current ADOT dataset.

- The paper discloses that the original MOVES version, analysis year and environmental settings were not recorded with the supplied rate tables. Adding the RunSpec here resolves that disclosure.
- The retained daily/profile calibration and emission workflow is now in `pipeline/v19/`. Its empirical entry reuses the original preprocessing baseline and external source inputs. Read its exact input contract before arranging files; the descriptive folders above are not an automatic loader specification. The raw corridor and platoon processing are not part of that workflow.
- Do not commit personal identifiers. The platoon records contain vehicle positions only; the detector records are aggregate counts and speeds.
