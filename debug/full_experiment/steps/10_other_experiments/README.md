# 10. Other experiment branches

The **137 episodes are the common five-method emission comparison**, not the entire experiment. This folder shows the calculations for the other branches. Each CSV is a new, checked breakdown of saved results; the fitted parameters, observations, reporting scope and network assignments remain unchanged.

| Branch | Sample or calculation unit | Start here |
|---|---|---|
| Daily traffic validation | 924 training and 174 later-date eligible episodes | [Score arithmetic](daily_validation_score_arithmetic.csv) |
| Planning-period emissions | 1,588 archived windows; 1,210 supported windows in current reporting | [Period components](period_emission_components.csv) |
| Daytime emissions | 225 supported current windows, each AM + MD + PM | [Daytime addition](current_daytime_addition.csv) |
| PeMS CBI comparison | 281 detected QVDF-E episodes and 282 reference episodes; 263 temporal matches | [Inventory arithmetic](cbi_inventory_arithmetic.csv) |
| Fixed-parameter Gamma and power approximation | Five points per available saved branch | [Calculation samples](fixed_parameter_gamma_and_power_samples.csv) |
| Pigou route assignment | Selected AZ I-10 W / MD parameter set; full and power models | [Route totals](pigou_route_component_arithmetic.csv), [PoA](pigou_poa_arithmetic.csv) |
| Finite vehicle transitions | 282 transition records, four pollutants; retain the replacement flag | [Transition arithmetic](transition_component_arithmetic.csv) |

CSV files contain numerical values. Equations below specify the calculations, and the [reproduction script](../../scripts/build_other_experiment_trace.py) evaluates them. [The audit](arithmetic_audit.json) records the input hashes and agreement with the original results.

## Diagnostic figures

Each figure is also supplied as an editable SVG with the same filename. [Figure sources](figure_sources.json) identify its tables and sample restrictions.

| Figure | Calculation it helps inspect |
|---|---|
| [Daily validation](figures/01_daily_validation.png) | Predicted versus observed duration and peak delay, separating training and later dates |
| [Period emissions](figures/02_period_emissions.png) | CO₂ totals and error versus the congested-volume share on the current reporting sample |
| [Fixed-parameter Gamma](figures/03_fixed_parameter_gamma.png) | Gamma and power-correction behavior with one fixed parameter set |
| [Pigou assignment](figures/04_pigou.png) | Route shares and generalized-cost PoA as the CO₂ weight changes |
| [Finite transitions](figures/05_transition.png) | Speed and acceleration-load contributions, followed by the assigned-emission comparison |
| [CBI comparison](figures/06_cbi.png) | Episode duration agreement and five-minute temporal overlap |

## Daily traffic validation

1. Start with the [daily episode table](../../../../data/frozen/calibration/daily_validation/episode_results_v2.csv), retaining `calibration_eligible`. Training ends **2016-10-19**; later-date testing begins **2016-10-20**. The 1,477 detected episodes yield 924 eligible training and 174 eligible testing episodes.
2. Compare the saved traffic prediction with its observed target. Missing observed/predicted pairs are omitted for that target. Queue-speed comparisons additionally require both queue speeds strictly between zero and free-flow speed. Finite-link failures remain in these traffic scores.
3. Calculate, for pairs $y_i,\widehat y_i$:

$$\mathrm{WAPE}=100\frac{\sum_i|\widehat y_i-y_i|}{\sum_i|y_i|},\qquad
R^2=1-\frac{\sum_i(\widehat y_i-y_i)^2}{\sum_i(y_i-\bar y)^2}.$$

The [score arithmetic](daily_validation_score_arithmetic.csv) exposes every numerator and denominator. The saved 95% intervals use **400 calendar-date block resamples**, with all sensors on a date kept together and predictions fixed. The interval columns are retained from the [original metrics](../../../../data/frozen/calibration/daily_validation/daily_metrics_ci.csv); this trace does not repeat bootstrap estimation. Daily episodes do not feed the 137-episode emission comparison.

## Planning-period and daytime emissions

Periods are AM 06:00–10:00, MD 10:00–16:00, PM 16:00–20:00 and NT 20:00–06:00. Whole episodes remain intact for calibration; only their emission increments are allocated across overlapping reporting periods.

1. For period $H$, count all vehicles: $V_H=\sum_{i\in H}q_i/12$. Calculate the free-flow emission for every vehicle: $B_{H,p}=V_HT_fr_p(v_f)$.
2. For episode $e$ overlapping $H$, calculate its overlap volume $D_{e,H}=\sum_{i\in e\cap H}q_i/12$ and allocate its whole-episode increment:

$$I_{e,H,p}=\frac{D_{e,H}}{D_e}\,D_e\widehat{\bar w}_e\Gamma_{e,p}.$$

3. Sum $M_{H,p}=B_{H,p}+\sum_e I_{e,H,p}$. Keep a period only when observations are complete and every overlapping episode is eligible, has a physically admissible fitted queue and a feasible reconstructed profile. A failed episode does **not** become a zero increment. The trace leaves the final model total unavailable for failed periods.
4. The reference and single-speed totals remain $O_{H,p}=\sum_{i\in H}(q_i/12)(L/v_i)r_p(v_i)$ and $S_{H,p}=(\sum_{i\in H}(q_i/12)L/v_i)r_p(\bar v_H)$, respectively. These two columns are copied from the verified archived period table; their five-minute integration is not repeated in this branch trace.
5. Current daytime results add the three period totals for each sensor/profile, then score these **sums**, using only windows whose AM, MD and PM parts all pass.

| Inspect | What it exposes |
|---|---|
| [Episode allocations](period_episode_allocations.csv) | Episode ID, overlapping bins/volume, volume share, full increment and allocated increment |
| [Period components](period_emission_components.csv) | $V_H,T_f,r(v_f),B_H,\sum I_{e,H}$, recomputed $M_H$, saved O/S/M and all admission flags |
| [Daytime addition](current_daytime_addition.csv) | AM/MD/PM values and their sum for each method and pollutant |
| [Current score arithmetic](current_period_score_arithmetic.csv) | WAPE and $R^2$ numerators/denominators for current reporting |

The archived [period table](../../../../data/frozen/calibration/average_weekday/period_results_v2.csv) has **1,246 supported planning periods** and its original daytime analysis has 234 supported windows. The separately declared [current reporting scope](../../../../data/reporting/v33/arizona_episode_profile_scope.csv) gives **1,210 supported planning periods and 225 daytime windows**. Both scopes are explicit in these files; current totals do not silently replace archived totals. The 137-episode sample remains unchanged.

## PeMS CBI comparison

The comparison concerns **detected boundaries and counted volumes before the common emission admission filter**.

1. Use the [saved reference episodes](../../../../data/frozen/calibration/repository_reference/episodes.csv) and the QVDF-E detection results.
2. For each corridor, verify `matched + QVDF-E only = QVDF-E episodes` and `matched + reference only = reference episodes`.
3. Calculate temporal overlap as $\mathrm{IoU}=N_{\mathrm{intersection}}/N_{\mathrm{union}}$. This is a five-minute-bin overlap measure, not emission accuracy.
4. Inspect the [263 matched episode pairs](../../../../data/frozen/calibration/cbi_episode_matches.csv) for start, minimum-speed and end-time differences and for $P,D$ comparisons. [The period comparison](../../../../data/frozen/calibration/cbi_period_comparison.csv) retains the counted and speed-inferred volumes; [the original metrics](../../../../data/frozen/calibration/cbi_comparison_metrics.csv) report their paired scores.

The inventory table recomputes counts and IoU. It retains the original episode pairing; it does not rerun the external repository.

## Fixed-parameter Gamma and the power approximation

Here each curve holds **one actual detector and one calibrated corridor-direction-period parameter set fixed**. This allows the dependence on $x=D/C$ to be interpreted without mixing parameter sets.

1. On an admitted power branch, compute

$$P=f_dx^n,\quad \mu=Cx/P,\quad
\omega=\frac{C}{k_j-C/v_f},\quad k_q=k_j-\mu/\omega,\quad v_q=\mu/k_q.$$

2. Compute $T_f=L/v_f$, $\widehat w_{\max}=T_ff_pP^s$, $\widehat{\bar w}=\theta\widehat w_{\max}$ and the **cubic-rate** response

$$\Gamma_p(x)=\frac{v_fr_p(v_q(x))-v_q(x)r_p(v_f)}{v_f-v_q(x)},\qquad
e_p(x)=e_{0,p}+\widehat{\bar w}(x)\Gamma_p(x),\quad e_{0,p}=T_fr_p(v_f).$$

3. Evaluate the saved signed power approximation and diagnostic factor:

$$\widetilde e_p(x)=e_{0,p}\left[1+\sigma_pa_{e,p}(x/x_{\mathrm{ref}})^{\beta_{e,p}}\right],\qquad
k_p(x)=\frac{e_p(x)/e_{0,p}-1}{a_{e,p}(x/x_{\mathrm{ref}})^{\beta_{e,p}}}.$$

The sign $\sigma_p$ is fixed within a fitted branch. Negative increments are retained. The [sample table](fixed_parameter_gamma_and_power_samples.csv) exposes rate values, Gamma, free-flow and congestion contributions, power factor, signed $k$ and approximation error at the first, quarter, middle, three-quarter and last saved validation points. The [status table](power_branch_status.csv) includes failed and unavailable cases. **Only `fitted` branches support the approximation**; any diagnostic samples marked failed must not be treated as accepted fits.

The original fit uses **201 logarithmically spaced nodes** and validates on **1,001 independent linearly spaced nodes** per admitted constant-sign monotone-increment branch. Parameters compress the full calibrated model; they are not regressions to measured emissions. Full [curves](../../../../data/frozen/calibration/surrogate/surrogate_curves.csv), [coefficients](../../../../data/frozen/calibration/surrogate/surrogate_coefficients.csv) and [specification](../../../../data/frozen/calibration/surrogate/surrogate_specification.json) remain canonical. Separate [marginal-emission curves](../../../../data/frozen/calibration/average_weekday/marginal_emission_curves.csv) and [cards](../../../../data/frozen/calibration/average_weekday/marginal_emission_card.csv) retain the elasticity/toll calculation and its confidence intervals.

## Pigou example: route totals, generalized cost and PoA

The [selection](../../../../data/frozen/calibration/pigou/pigou_selection.json) fixes AZ I-10 westbound / MD, using detector 78 as the representative FD. This is a calibrated **illustrative network**, separate from the supplied January detector-78 worked example. It uses the smooth cubic emission branch.

1. Use fixed background demand $B$, flexible demand $N$ and flexible route-1 flow $y$. Total route flows are $D_1=B+y$ and $D_2=N-y$; background vehicles remain in all totals.
2. Evaluate route-1 $T_1,e_{1,p}$ from the full curve or its signed power approximation at $x=D_1/C$. Route 2 has fixed $T_2,e_{2,p}$.
3. Sum $\mathrm{VHT}=D_1T_1+D_2T_2$ and $E_p=D_1e_{1,p}+D_2e_{2,p}$. The [route-component table](pigou_route_component_arithmetic.csv) exposes both multiplications and their sum for all saved assignments, both model forms and all pollutants.
4. Generalized cost uses CO₂: $c_a=T_a+\eta s_e e_{a,\mathrm{CO2}}$, where $s_e=T_2/e_{2,\mathrm{CO2}}$. The objective is $J_\eta=\mathrm{VHT}+\eta s_eE_{\mathrm{CO2}}$. The [weight table](pigou_generalized_cost_arithmetic.csv) shows the time term and weighted-emission term for all **81 weights from 0 to 4**, at step 0.05, for both model forms.
5. For each objective $J$, compute

$$\mathrm{PoA}[J]=\frac{\max_{y\in\mathrm{UE}[J]}J(y)}{\min_{0\le y\le N}J(y)}.$$

The [PoA table](pigou_poa_arithmetic.csv) exposes numerator, denominator and ratio. Emission PoA for pollutant $p$ uses its own emission-cost equilibrium and its own emission optimum. An emission outcome under time-based equilibrium divided by the emission optimum is a separate cross-objective inefficiency measure, not the same PoA.

Saved flows are taken from the original solver. This trace verifies their objectives but does not independently establish equilibrium or global optimality again. The [full-model solver audit](../../../../data/frozen/calibration/pigou/full/audit.json), [power-model audit](../../../../data/frozen/calibration/pigou/surrogate/audit.json) and [full/power comparison](../../../../data/frozen/calibration/pigou/full_surrogate_comparison.csv) provide those retained checks.

## Finite-transition analysis

The trajectory transition records form a separate sample from the detector episodes. The table retains all **282 records** and flags the **281 replacement-admissible records**.

1. Start with two-speed, zero-acceleration emissions $E_{2s,0}$.
2. Replace the instantaneous speed change with the fitted smooth transition at zero acceleration in the emission rate: $\Delta E_{\mathrm{speed}}=E_{KS1,0}-E_{2s,0}$.
3. Include the transition's acceleration-dependent rate: $\Delta E_{\mathrm{load}}=E_{KS1,\mathrm{modal}}-E_{KS1,0}$.
4. Verify $E_{2s,0}+\Delta E_{\mathrm{speed}}+\Delta E_{\mathrm{load}}=E_{KS1,\mathrm{modal}}$, then compare with emissions assigned to the measured motion, $E_{\mathrm{measured\ motion,modal}}$.

The [component table](transition_component_arithmetic.csv) performs these subtractions and addition for four pollutants and retains record IDs, duration, endpoint speeds and validity. Its inputs are the [archived transition values](../../../../data/frozen/transitions/ks1_vsp_transitions.csv). Their rates are model assignments, not measured exhaust. Raw platoon trajectories are not bundled, so this trace checks the saved derived values rather than reconstructing raw transitions. [Cohort finite-transition admissibility](../../../../data/frozen/applicability/cohort_admissibility_summary.json) and [corridor applicability](../../../../data/frozen/applicability/corridor_admissibility_summary.json) are separate geometric diagnostics.

## Units and reproduction

| Symbol | Meaning and unit |
|---|---|
| $q_i$; $D,V,B,N,y$ | Per-lane flow (veh/h); vehicle counts per lane |
| $L,v_f,v_q$ | Link length (mi); speeds (mph) |
| $C,k_j,\omega$ | Capacity (veh/h/lane); jam density (veh/mi/lane); backward wave-speed magnitude (mph) |
| $x,P,T_f,T,w$ | Loading $D/C$, duration, travel times and delays (h) |
| $r,\Gamma$ | Rate and congestion-increment coefficient (g/veh/h) |
| $e,E$ | Per-vehicle emissions (g/veh); total emissions (g) |
| $\eta,s_e$ | Dimensionless routing weight; time/emission scale (h/g) |

Run from the repository root with Python, NumPy, pandas and Matplotlib:

```sh
python debug/full_experiment/scripts/build_other_experiment_trace.py
```

New tables go to `debug/output/full_experiment/10_other_experiments/`. Published results and canonical inputs are protected. All calculations use full saved precision; this folder adds explanations and arithmetic, not a new experiment.
