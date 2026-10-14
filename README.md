# QVDFE: from bottleneck episodes to travel and emission costs

Code, teaching materials and frozen data for

> Abbasi, M., Zhou, X. (2026). *From Bottleneck Episodes to Travel and Emission Costs: A Cross-Resolution Framework with Empirical Evaluation.* Manuscript.

It extends two tools of the ASU Trans+AI Lab from travel time to emissions: the queueing-based volume-delay function ([QVDF](https://github.com/asu-trans-ai-lab/QVDF)) and congestion and bottleneck identification ([CBI](https://github.com/asu-trans-ai-lab/CBI)).

[![License: MIT (code)](https://img.shields.io/badge/code%20license-MIT-blue.svg)](LICENSE)

<!-- The integrated repository is edited directly; frozen release inputs remain archived. -->

## The question

Vehicle-miles (VMT) and vehicle-hours (VHT) say how far and how long. They do not determine emissions, because emission rates are nonlinear in speed and acceleration. A freeway bottleneck episode supplies the missing information: the queued state and its service rate, the episode's duration and delay, and the transitions into and out of the queue. The paper establishes three results, each with its conditions:

1. **Episode aggregation.** On one link, a closed episode in which every vehicle travels at free-flow speed v_f and then at one common queue speed v_q, with zero-acceleration (speed-only) rates r(v), instantaneous speed switches and every delay within the finite-link allowance: episode volume and total delay determine the episode emission total. In VMT/VHT form, E_P = [r(v_f)/v_f]·VMT + Γ(v_q)·(VHT − VMT/v_f). The conversion factor Γ can be negative: with the archived CO₂ rates it is negative for queue speeds above about 27 mph, which includes 75 of the paper's 137 admitted episodes.
2. **Demand-dependent response.** With a calibrated QVDF, the service rate, queue speed and conversion factor Γ change with loading. The elasticity of the emission increment can therefore differ from the delay elasticity. The two coincide where Γ is locally constant, including under fixed service.
3. **Finite-transition correction.** Finite decelerations and accelerations that preserve time and distance change emissions by a closed-form speed-only term. A separate time–distance condition delimits where the common correction applies.

**Notation used throughout.**

| Symbol | Meaning |
| --- | --- |
| v_f, v_q | Free-flow speed, and speed of queued vehicles (mph) |
| C, μ | Capacity and bottleneck service rate (veh/h/lane) |
| ω, k_j, k_q | Backward-wave speed (mph), jam density and queued density (veh/mi/lane) |
| D, P | Episode volume (veh/lane) and duration (h) |
| x = D/C | Loading in hours: the time the bottleneck would need to serve D at capacity |
| w, w̄_P, W_P | Delay of a vehicle, the episode mean delay (h), and total delay W_P = D·w̄_P (veh·h/lane) |
| r(v) | Emission rate at speed v and zero acceleration (g/(veh·h)) |
| e₀ | Free-flow emission of a traversal (g/veh) |
| Γ(v_q) | Emission change per hour of queued delay (g/(veh·h)) |
| QVDF parameters f_d, n, f_p, s, θ | Calibrated duration and peak-delay parameters; see tutorial T3 |
| Admitted episode | Satisfies the finite-link condition and the reconstruction and rate-domain checks of Section 6 |

<!-- AUTHORS: end of editable introduction -->

## Install

```bash
git clone https://github.com/asu-trans-ai-lab/QVDF_E.git
cd QVDF_E
pip install -e .                                # core package qvdfe (numpy >= 2, pandas, scipy, matplotlib)
pip install -e ".[teaching,dev,reproduce]"     # adds JupyterLab, pytest and the PDF renderer used by reproduce/run_all.py
pip install -r requirements.txt                # optional: original release's environment snapshot
```

Python 3.10 or later. Install **editable from a clone** (`-e`): the package reads the frozen data in the clone's `data/` folder. To use the data from elsewhere, set the environment variable `QVDFE_DATA` to that `data` folder. The examples and tutorials also run without installation, because each one finds `src/qvdfe` itself.

## Integrated experiment workflow

The repository now includes the QVDF-E calibration and emission workflow alongside the reusable formulas, tutorials and later applicability analyses. The archived empirical results remain unchanged. The original workflow and the public formulas are checked against the same saved episodes; this integration does not replace the paper's results with a new experiment.

| Task | Entry point | Inputs |
| --- | --- | --- |
| Refit the daily and average-weekday models and calculate emissions | `python -m qvdfe.pipeline empirical --help` | The preserved preprocessing baseline and external source data; see [`src/qvdfe/pipeline/README.md`](src/qvdfe/pipeline/README.md) |
| Refit the smooth emission surrogate | `python -m qvdfe.pipeline surrogate --help` | Included frozen calibration inputs |
| Rerun the Pigou routing comparison and price of anarchy | `python -m qvdfe.pipeline pigou --help` | Included calibration and surrogate inputs |
| Reproduce figures and later applicability analyses | `python reproduce/run_all.py` | Included frozen inputs and current figure sources |
| Reproduce the current reporting sample | `python reproduce/current_reporting.py` | Retained period results and explicit v33 profile support |

After the editable installation, run the QVDF-E pipeline with `python -m qvdfe.pipeline`. It writes to a separate output directory and preserves its inputs. Raw Arizona and platoon data are not redistributed. The empirical path starts with the preserved preprocessing baseline used for the verified experiments; it is not a new raw-data acquisition workflow. [`docs/INTEGRATION.md`](docs/INTEGRATION.md) explains the scientific choices and validation.

## Choose the emission-rate representation explicitly

The main empirical two-speed calculation **M** uses the archived zero-acceleration lookup. The smooth approximation **A** uses a cubic fitted to that same table. Both share the same traffic model and emission identity, but can give different numerical emissions.

```python
import qvdfe

lookup = qvdfe.load_lookup_rates()       # M: pollutant -> callable, rates in g/(vehicle h)
cubic = qvdfe.load_cubic_rates()         # A: pollutant -> coefficient metadata
episode = qvdfe.load_episodes().query('matched_ladder_pass').iloc[0]
M_CO2 = qvdfe.episode_total(
    episode.D_veh, episode.wbar_hat_h, episode.L_mi,
    episode.vf_mph, episode.vq_hat_mph, lookup['CO2'])
checks = qvdfe.screen_episode(episode)   # complete downstream matched-comparison checks
assert checks['matched_ladder_pass']
```

The existing `load_rates()` default remains cubic for compatibility with tutorials. Use `load_lookup_rates()` or `load_rates(representation='lookup')` for M. Analytical derivatives in `response()` use cubic coefficients. Its `valid` flag is a response-domain check; it does not perform observation QC or the complete matched-comparison screen. `screen_episode()` requires upstream calibration eligibility and all comparison totals. Negative Γ is retained.

## Minimal example

```bash
python examples/01_synthetic_episode/run.py
```

Expected output, using synthetic values from `examples/01_synthetic_episode/config.json`:

```
SYNTHETIC EXAMPLE (illustrative values, not observed data)
1. queued state: omega = 12.00 mph, k_q = 75.00 veh/mi/lane, v_q = 20.00 mph
2. closed queue: D = mu P = 3000 veh/lane (numerical 3000.000); W_P = 44.444 veh h/lane (numerical 44.444); peak delay 1.580 min, mean delay 0.889 min; mean/peak = 0.5625 (9/16 for the Newell model only)
3. finite link: allowance L(1/vq - 1/vf) = 2.000 min; peak-delay vehicle fits (T_free = 0.210 min)
4. CO2: e0 = 277.80 g/veh, Gamma = 1772.36 g/(veh h), mean-delay vehicle e = 304.06 g;
   episode total 912.1717 kg/lane (delay form) = 912.1717 kg/lane (VMT/VHT form)
checks: conservation_D PASS, total_delay_W PASS, closed_queue PASS, peak_vehicle_fits_link PASS, two_forms_agree PASS
compared 29 values with expected/results.json: 29 agree
```

Here ω is the backward-wave speed and k_q the queued density. The script also writes `examples/01_synthetic_episode/figure.png`; the reference copy is `expected/figure.png`.

## Where to go next

| I want to … | Go to |
| --- | --- |
| learn the theory step by step | [`teaching/`](teaching/): four tutorials (bottleneck and closed episode; two speeds and emissions; demand-dependent response; finite transitions), exercises, instructor solutions, advanced readings |
| run the original empirical calibration, surrogate fitting or routing optimization | [`src/qvdfe/pipeline/`](src/qvdfe/pipeline/) |
| run small examples | [`examples/`](examples/): synthetic episode; weekdays versus the average weekday (Fig. 7); long-episode applicability (Appendix F) |
| use the functions in my own code | [`src/qvdfe/`](src/qvdfe/): `queue_speed`, `closed_queue`, `link_emission`, `gamma`, `episode_total`, `vmt_vht_form`, `qvdf`, `response`, `transition_band`, `cohort_shares`, `subset_total`, … |
| reproduce the paper's figures, tables and applicability calculations from the frozen data | [`reproduce/`](reproduce/): `python reproduce/run_all.py` |
| find where an equation is implemented | [`FORMULA_CODE_MAP.md`](FORMULA_CODE_MAP.md) |
| explore interactively | [`docs/index.html`](docs/index.html) (optional dashboard; open locally or via GitHub Pages) |
| check the data and their sources | [`data/DATA_DICTIONARY.md`](data/DATA_DICTIONARY.md) |

## Checks

```bash
pytest                         # mathematical identities and conservation; frozen published values
python tools/verify_frozen_inputs.py  # verify the original data against the release manifest
python reproduce/run_all.py    # regenerate figures and calculations; compare with the frozen files
```

The tests come in two groups:
- **Identity and conservation tests** need only the cubic rate table. They cover D = μP, W_P = ∫Q dt, the two emission forms, Γ, the 9/140 coefficient, the transition band and the input checks of the core functions.
- **Reproduction tests** recompute published values: Table F1 at full precision and at display rounding, Table 8, Table F2, the Appendix F reference values and the episode counts. They also check that the core functions reproduce the frozen two-speed totals and elasticity cards, and that the committed tutorials match their generator.

[`reproduce/README.md`](reproduce/README.md) lists what is redrawn from frozen outputs here and what can only be rebuilt from the original data.

`MANIFEST_SHA256.json` is the **original release manifest**, retained as an immutable reference. It is not a checksum list for subsequently edited code. New figure and reporting inputs have separate provenance records. Current reporting uses the reviewed v33 support (225 supported daytime windows); historical reproduction remains available separately and does not silently change archived values.

## Data and reproduction limits

- **Arizona I-10** data are legacy Arizona Department of Transportation (ADOT) loop-detector records. They were cleaned, synchronized and post-processed for Zhou et al. (2022), *Multimodal Transportation* 1, 100017, and are used for research purposes. The raw files are not redistributed, and no official ADOT release is implied.
- **California** profiles come from the PeMS CBI-DV release at [jacky850/pems-cbi-dv](https://github.com/jacky850/pems-cbi-dv).
- **Platoon transitions**: derived records only. The raw trajectories were provided by Prof. Rui Jiang's group and are not redistributed.
- **Emission rates** come from archived MOVES-derived passenger-car tables. The original MOVES version, analysis year and settings were not recorded, so emission results can only be reproduced starting from the supplied derived rate tables.

## To do

- [ ] **Figs. 4 and D1.** `reproduce/fig04_figD1_queue_and_scheduling.py` redraws the closed fluid queue (Fig. 4) and the scheduling figure (Fig. D1) with the same Newell episode, and its geometry checks pass. It still uses an earlier layout. Port the final style of these two figures so that the regenerated PDFs match the published figures.

## Licence and citation

The **code** is open source under the MIT License (`LICENSE`). The authors make **no claim on the data**: the files in `data/` remain subject to the terms of their original providers above and are shared for research use (`data/NOTICE.md`). Details are in `LICENSE.md`. To cite this work, use `CITATION.cff`. 
