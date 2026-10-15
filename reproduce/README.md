# Reproducing results and editable figures

Run from the repository root after installing the package and reproduction dependencies:

```bash
python reproduce/run_all.py                 # figures, calculations and audits
python reproduce/run_all.py --skip-figures  # calculations and audits only
python reproduce/verify_current_figures.py # export and layout checks after rendering
```

These entries read saved inputs through `qvdfe.paths` and write only to `reproduce/output/`. They do not detect new episodes or refit calibration parameters. The integrated upstream experiment workflow is separate; see the repository README for its commands. Archived calculations remain comparable with their original frozen files. `current_reporting.py` writes the current supported reporting scope separately to `output/current_reporting/`.

The upstream empirical workflow now has its complete baseline-reuse inputs in [`data/inputs/`](../data/inputs/): the preserved preprocessing baseline and the exact Arizona/PeMS source files, with the emission tables already in `data/frozen/calibration/emission_input/`. To verify and run those inputs from the repository root:

```bash
python -m qvdfe.pipeline check-inputs --data-root data/inputs/empirical/source_files --baseline data/inputs/empirical/baseline --emission-input data/frozen/calibration/emission_input
python -m qvdfe.pipeline empirical --data-root data/inputs/empirical/source_files --baseline data/inputs/empirical/baseline --emission-input data/frozen/calibration/emission_input --output build/qvdfe_empirical --bootstrap 400
```

This command constructs the analysis profiles from prepared baseline observations and refits the models; it verifies original source hashes but does not reconstruct the baseline from raw files. Full input and stage definitions are in the [pipeline README](../src/qvdfe/pipeline/README.md). Raw platoon trajectories and the original MOVES RunSpec remain unavailable in this repository.

`run_all.py` compares each historical calculation/audit file with its frozen counterpart, value by value. To compare figures with a local manuscript asset folder, set `QVDFE_PAPER_FIGS` to that folder. Use `--strict` to count figure differences as failures. Font and renderer versions can change pixels; the queue and scheduling generators retain an earlier layout. A figure comparison is not a new empirical validation.

## Available entries

The recent 137-episode error diagnostic can also be run with `python reproduce/episode_error_audit.py`. It uses the frozen average-weekday panel and calibrated episode records together with the exact lookup bands and quadrature nodes in `data/inputs/detector78/`. It writes separate CSV results under `reproduce/output/episode_error_audit/`; no frozen results are overwritten. See [the input inventory](../data/inputs/README.md).

Figure numbers below follow the revised manuscript (v33). Historical script and asset names are retained so existing commands and manuscript references to asset filenames continue to work.

| Entry | Current paper item | What is reproduced |
| --- | --- | --- |
| `fig01_overview.py` | Fig. 1 | Queue schematic, normalized duration–delay curves from the frozen daily fits, and vehicle transition; current layout |
| `fig02_rates_and_gamma.py` | Figs. 2 and 5 | Four-panel US06 operating-mode/zero-acceleration/cubic comparison, and fixed-parameter Gamma behavior; current layouts, plotted values and numerical checks |
| `fig03_shockwave.py` | Fig. 3 | Bottleneck shock waves |
| `fig04_figD1_queue_and_scheduling.py` | Figs. 4 and D1 | Closed fluid queue and scheduling; analytical geometry checks, earlier layout |
| `fig05_transition.py` | Fig. 6 | Finite transition |
| `fig07_paired_episode.py` | Fig. 8 | Individual weekdays and their monthly profile; bin-by-bin audit |
| `fig09_fig10_fig11_fig12_evidence.py` | Figs. 10–13 | Calibration (current legends/layout), emission comparison, Gamma at calibrated states, and elasticity; original frozen values and masks |
| `figE1_two_route.py` | Fig. E1 | Frozen Pigou experiment, with full and power-approximation results |
| `calc_cohort_admissibility.py` | Appendix F, Table F2 | Finite-transition admissibility across the common episode sample |
| `calc_corridor_admissibility.py` | Corridor applicability | Corridor-scale geometric admissibility |
| `calc_daytime_period.py` | Archived daytime analysis | Historical daytime-window results, retained for comparison |
| `current_reporting.py` | Current period/daytime reporting | Supported reporting windows and current summaries, kept separate from historical outputs |
| `audit_numerics.py` | Tables 8, F1 and diagnostics | Full-precision reference, exclusion ledger, emission metrics, recorded-speed recalculation and later-date sensitivity including a null benchmark |

The core test suite separately checks mathematical identities and frozen values. See [PRESENTATION_PROVENANCE.md](PRESENTATION_PROVENANCE.md) for the figure-source mapping and limits.

## Emission-rate interpretation

The empirical two-speed estimate **M** uses the archived zero-acceleration operating-mode lookup. The cubic **A** approximates the same rates and supports smooth analytical functions. Figure 2 shows both representations; its operating-mode rates also include acceleration. All three are model-assigned rates, not measured tailpipe emissions. The original MOVES run settings were not recorded, so the supplied rate tables are the reproducible starting point.

## Style and editable output

`reproduce/lib/polish_style.py` controls the shared blue/grey palette, white background, text and axes. The manuscript font is Times New Roman. When unavailable, rendering uses an installed serif fallback with a warning. Set `QVDFE_FIGURE_FONT` to an installed font name to choose explicitly; an unavailable explicit choice fails. Exact manuscript layout comparisons require the manuscript font.

The updated figure entries export vector PDF/SVG, 600-dpi PNG, curve CSVs and layout audit JSON. `verify_current_figures.py` checks the four current-layout exports for width, editable text, font types, image resolution, clipped text and text/line intersections. Its collision candidates supplement visual inspection; they do not prove that a figure is readable.

## Retained source limitations

The study map (Fig. 7), corridor time–space figure (Fig. 9), and measured platoon figure (Fig. 14) are not redrawn by these entries: complete original map/plotting or trajectory sources are not included here. Their available derived records remain in `data/frozen/`. The original MOVES configuration cannot be reconstructed from the rate tables alone. The queue/scheduling generator is retained with verified equations and editable outputs, but its final manuscript layout is not reproduced exactly.
