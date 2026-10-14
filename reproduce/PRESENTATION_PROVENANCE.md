# Figure sources and interpretation

The integration updates presentation using the author's final editable v33 sources while retaining the original empirical fit and emission results. No traffic fit, sample mask, rate coefficient or Pigou assignment is changed by these figure entries.

| Figure | Frozen input | Calculation and scope |
| --- | --- | --- |
| 1, overview | `calibration/daily_validation/parameter_card.csv` | Four period fits, normalized as `w_peak/Tf = fp * P**s`; other panels are explicitly illustrative queue/transition constructions. |
| 2, US06 | `presentation/us06/*.csv`, `calibration/emission_input/*.csv`, `calibration/cubic_rate_coefficients.csv` | Passenger-car age-weighted operating-mode rates; zero acceleration at the same speed; cubic limited to 5–75 mph. Integrates 600 one-second intervals from records at 1…600 s. |
| 5, fixed-parameter Gamma | `calibration/audit/table3_reference_state.json` | Holds all traffic and rate parameters fixed. Plots `Gamma/r(vf)` against queue speed and demand `x = D/C`; the demand panel ends at the finite-link peak-delay constraint. |
| 10, calibration | `calibration/average_weekday/episode_results_v2.csv` | Keeps the original 286 calibration-eligible episodes and each panel's finite-pair mask. Adds distinct observed/fitted and Arizona/PeMS legend keys; does not apply the emission sample's finite-link screen. |

All paths in the table are relative to `data/frozen/`, or to the directory selected by `QVDFE_DATA`. The new US06 inputs have SHA-256 hashes in `data/frozen/presentation/PROVENANCE.json`. Existing rate, reference-state, daily-fit and episode files are reused rather than duplicated. `fig02_rates_and_gamma.py` also records hashes for every input it reads.

The US06 source bundle supplies a prescribed driving cycle and model-assigned rates. Its phase threshold is ±0.5 mph/s; idling is speed below 1 mph. Braking is the operating-mode classification and is displayed with open diamonds. The recalculation checks all 701 supplied speed-only lookup entries and the supplied phase totals. Full-cycle CO2 is 2,830.2103 g, the same-speed zero-acceleration total is 2,388.1377 g, and their difference is 442.0726 g. These values describe a model counterfactual, not a measured or causal acceleration effect.

The empirical Gamma scatter is retained separately from the fixed-parameter illustration. Its points can have different detector parameters and calibration coefficients; its visual spread therefore does not show a single Gamma function.

During integration, the four updated PDFs were regenerated and rendered against the author's v33 exports using the same local fonts and renderer: all four rendered images were identical. The five emitted curve/phase CSVs were also value-identical. Export checks found 7.07-inch width, editable text, no Type 3 fonts, 600-dpi PNG, and no clipped text or text/stroke collision candidates. These checks apply to the four updated layouts, not to every historical figure in the repository.

The queue/scheduling geometry source matches the archived editable construction and keeps its geometry tests. It now also exports SVG; the later manuscript layout remains a retained-asset limitation. No original map layers or raw platoon trajectories are added by this integration.
