# 11. Five-minute comparisons for every retained episode

Open **[the case list](EPISODES.md)** to view all 137 cases directly in GitHub, or open **[the episode browser](index.html)** locally for filtering. Each case has five separate pages: traffic, CO₂, NOₓ, CO and HC. Each page pairs one figure with one error table. [episode_index.csv](episode_index.csv) maps the compact `ep001`–`ep137` labels to full original episode IDs, detector, date, direction and period.

Browse the [episode folders](episodes/), or go directly to [Arizona detector 141, November 2016, episode ep014](episodes/ep014_AZ_I10_W_141_20161101/README.md), the case used in the separate worked-example PDF.

The **collapsible left sidebar** links the overview, traffic inputs and separate inverse/FD pages. Nested sections can be expanded, and the whole sidebar can be hidden for more table space. The active page is highlighted. Each page contains one main data table; wide tables scroll horizontally. The traffic-parameter table also has optional column groups and thick borders between groups.

Equations are typeset with **native MathML**, including fractions, subscripts and superscripts. No external math service, font download or internet connection is required. The CSVs retain full-precision values; displayed rounding is only for reading.

| Dashboard page | What to inspect |
|---|---|
| [Episode overview](index.html) | Sort or filter all 137 episodes using six traffic-error measures. |
| [Traffic parameters](traffic_parameters.html) | Observed/fitted traffic, QVDF coefficients, FD inputs and capacity provenance. |
| [Emission-target queue speed](inverse_emissions.html) | One shared queue speed per episode under a CO₂ target or equal-weight four-pollutant target. |
| [Three backward FD calculations](inverse_fd.html) | Recover discharge, wave speed or jam density while holding the other two fixed. |
| [Bounded FD pairs](fd_sensitivity.html) | Episode-level density/wave-speed candidates under primary or expanded bounds. |
| [FD sensitivity summary](fd_summary.html) | Four rows comparing target reachability, capacity preservation and reoptimization. |
| [Fixed versus freely varying capacity](fd_capacity_comparison.html) | Side-by-side emission-target solutions with fitted traffic held fixed. |
| [Separate capacity sensitivity report](../../../capacity_sensitivity/report.html) | Capacity provenance and the effect of propagating capacity changes through traffic predictions and emissions. |

These are the same 137 retained average-profile episodes used in the reported comparison. The archived parameters, model totals and sample decisions are preserved. Newly calculated diagnostic alternatives are identified separately.

Dates in the index identify the source average profiles; Arizona dates are monthly profile labels, not individual observed days. The full episode ID and source-profile label are retained in the index for joining back to the earlier calculation steps.

## Files and reading order

| File | Contents |
|---|---|
| `episodes/<case>/index.html` | Traffic figure and its single consolidated error table; local navigation to the four pollutant pages. |
| `episodes/<case>/emissions_CO2.html`, `emissions_NOx.html`, `emissions_CO.html`, `emissions_HC.html` | One pollutant figure and one corresponding error table per page. |
| `episodes/<case>/traffic_timeseries.csv` | Every observed five-minute bin × O/S/R/M/A: count, travel time, delay, equivalent speed, exposure-weighted VSP, VSP at equivalent speed, and M/A free/queue times and distances. |
| `episodes/<case>/emissions_timeseries.csv` | Every bin × five methods × four pollutants: vehicle-hours, effective rate, assigned bin emission, cumulative emission and cumulative count. |
| `episodes/<case>/node_to_bin_allocation.csv` | Positive overlaps between each observed count interval and modeled integration-node count interval; the explicit allocation weights. |
| `episodes/<case>/error_metrics.csv` | 90 comparisons with O: scalar APE; five-minute WAPE, signed bias, MAE and RMSE; units and reference denominators. |
| `episodes/<case>/traffic_profiles.png` and `.svg` | Speed, travel time, delay, VSP, two-speed time allocation and two-speed distance allocation. |
| `episodes/<case>/emissions_<pollutant>.png` and `.svg` | Rate, five-minute emissions, cumulative emissions versus time, and the **same cumulative series** versus cumulative vehicles. |
| [all_traffic_timeseries.csv.gz](all_traffic_timeseries.csv.gz) | All 24,000 bin-method traffic rows in one compressed CSV. |
| [all_emissions_timeseries.csv.gz](all_emissions_timeseries.csv.gz) | All 96,000 bin-method-pollutant rows in one compressed CSV. |
| [all_error_metrics.csv](all_error_metrics.csv) | All 12,330 per-episode error records. No averaging of episode percentage errors is used. |
| [total_reconciliation.csv](total_reconciliation.csv) | 2,740 method-pollutant totals: common-clock sum, native discrete calculation and preserved episode total. |
| [verification.json](verification.json) | Numerical conservation/identity checks and source hashes. |

Join on `episode_id`, `bin_index`, `method` and, for emissions, `pollutant`. Bin numbers restart within each episode. `bin_start` is inclusive and `bin_end` is exclusive; every bin spans five minutes. Counts, vehicle-hours, emissions and cumulative emissions are **per lane**. Expand `.csv.gz` before opening in a spreadsheet. SVGs and the plotting code remain editable.

All 4,800 retained observed bins and all modeled node weights have positive vehicle counts, which the generator verifies before dividing by counts or exposure. The generator is intentionally specific to this preserved cohort; new zero-count inputs require an explicit undefined-rate policy rather than silently filling those rates.

## Common-clock alignment: what it means

O has observed five-minute bins. R/M/A are represented by 384 integration nodes over their predicted episode duration, which can differ from the observed duration. To compare them on a common clock, the model's vehicle groups are assigned to observed bins by **cumulative-count overlap**. This preserves ordering and episode totals; it does not reconstruct when specific vehicles traversed the link.

Let $n_i$ be the observed count in bin $i$, and $N_j$ the model-node vehicle weight. Define cumulative edges $B_i=\sum_{k\le i}n_k$ and $Q_j=\sum_{k\le j}N_k$, both starting at zero and ending at $D$. The allocation is

$$a_{ij}=\max\{0,\min(B_i,Q_j)-\max(B_{i-1},Q_{j-1})\}.$$

Then $\sum_ja_{ij}=n_i$ and $\sum_i a_{ij}\approx N_j$. If $T_j$ is node travel time and $E_{mj}$ its emission contribution,

$$H_{mi}=\sum_ja_{ij}T_j,\qquad E_{mi}=\sum_ja_{ij}\frac{E_{mj}}{N_j}\qquad(m=R,M,A).$$

O retains its original bin values. S has a constant observed mean travel time and mean-speed rate, so its total vehicle-hours and emissions are assigned in proportion to $n_i/D$. **Observed counts are identical across methods.** No speed or emission total is refitted to improve these plots.

## Traffic calculations

For each aligned bin, with link length $L$ and $T_f=L/v_f$:

$$\bar T_i=H_i/n_i,\qquad \bar w_i=\bar T_i-T_f,\qquad \bar v_i=\frac{n_iL}{H_i}=\frac L{\bar T_i}.$$

Observed delay is kept signed. A recorded speed exceeding the calibrated $v_f$ can give a negative bin delay; values are not clipped. R, M and A share predicted vehicle-hours and therefore share travel time, delay and equivalent speed. The traffic plots label this shared curve **R = M = A** instead of drawing three indistinguishable lines.

For M/A, average the model state times over allocated vehicles:

$$\bar t_{fi}=\frac{\sum_ja_{ij}t_{fj}}{n_i},\qquad
\bar t_{qi}=\frac{\sum_ja_{ij}t_{qj}}{n_i},$$
$$\bar t_{fi}+\bar t_{qi}=\bar T_i,\qquad
v_f\bar t_{fi}+\widehat v_q\bar t_{qi}=L,\qquad
\bar v_i=\frac{v_f\bar t_{fi}+\widehat v_q\bar t_{qi}}{\bar t_{fi}+\bar t_{qi}}.$$

This is a **travel-time-weighted average of the state speeds**, equal to total distance divided by total travel time. The CSV provides both forms for checking. `mean_free_time_h`, `mean_queue_time_h` and state-distance fields are intentionally blank for O/S/R, which do not use two operating states for their emission-rate calculation. The node delay profile and state-time formulas remain in [step 8](../08_reconstruction_and_two_speed/README.md).

## Two distinct VSP quantities

`vsp_at_equivalent_speed_kw_t` evaluates the common zero-acceleration VSP function at $\bar v_i$. `exposure_weighted_vsp_kw_t` instead averages the method's **operating-state VSP**, weighted by its vehicle-hours:

$$\bar z_{Ri}=\frac{\sum_ja_{ij}T_j\mathrm{VSP}(v_{Rj})}{H_i},$$
$$\bar z_{Mi}=\bar z_{Ai}=\frac{\sum_ja_{ij}[t_{fj}\mathrm{VSP}(v_f)+t_{qj}\mathrm{VSP}(\widehat v_q)]}{H_i}.$$

O uses its bin's recorded-speed VSP; S uses VSP at its constant mean speed. The traffic dashboard plots exposure-weighted VSP, while both definitions are supplied in the CSV. Equal equivalent speed does not imply equal operating-state VSP. M and A have the same VSP; they differ only in lookup versus cubic emission rates.

## Rate, emissions and cumulative plots

The effective rate for a method, bin and pollutant is

$$e_{mi}^{eff}=E_{mi}/H_{mi}.$$

It is an exposure-weighted effective rate, not generally the lookup rate evaluated at the bin's equivalent speed. In particular, do not reapply the lookup to $\bar v_i$ and expect M/A's two-state emission result.

`cumulative_emission_g_per_lane` is $\sum_{k\le i}E_{mk}$ and `cumulative_count_veh_per_lane` is $B_i$. Both cumulative panels begin at **zero emission and zero vehicles at the first bin's start**. One uses bin-end clock time as $x$; the other uses cumulative observed vehicles as $x$. They display the same cumulative emission values at the same bin boundaries. Joining those endpoints with lines is a display choice, not a claim about within-bin trajectories.

## Interpretation and checks

### Error columns and tables

The HTML index can be filtered and sorted. Its six error columns compare the fitted traffic quantities shared by R/M/A with O: duration $P$, calibrated minimum speed $v_{t_2}$, five-minute equivalent speed, episode average speed, five-minute travel time and five-minute delay. Each case's traffic page has one consolidated traffic error table; its four pollutant pages each have one pollutant error table. Each table sits beside its figure and moves below it on narrow screens.

For equal five-minute bins, with reference $y_{Oi}$ and estimate $y_{mi}$:

$$\mathrm{WAPE}=100\frac{\sum_i|y_{mi}-y_{Oi}|}{\sum_i|y_{Oi}|},\qquad
\mathrm{Bias}=100\frac{\sum_i(y_{mi}-y_{Oi})}{\sum_i|y_{Oi}|}.$$

These sums have **no additional count weighting**. Signed observed delay is retained; its denominator is $\sum_i|w_{Oi}|$, not $|\sum_iw_{Oi}|$. A zero denominator produces an undefined percentage, shown as a dash. The CSV also supplies $\mathrm{MAE}=\mathrm{mean}(|y_m-y_O|)$ and $\mathrm{RMSE}=\sqrt{\mathrm{mean}((y_m-y_O)^2)}$ in the stated units; travel time and delay errors use minutes.

For one episode-level quantity, $\mathrm{APE}=100|y_m-y_O|/|y_O|$. The scalar quantities are:

| Quantity | Reference and estimate |
|---|---|
| $P$ | Archived observed whole-episode duration and calibrated duration; no independent S duration calibration. |
| $v_{t_2}$ | Minimum recorded speed over the observed episode versus $L/(T_f+\widehat w_{t_2})$. The fitted target is **not** replaced by the minimum of a bin-averaged profile and is **not** FD queue speed $\widehat v_q$. |
| Episode average speed | $DL/\sum_i H_{mi}$, a count-weighted harmonic speed. S equals O by construction. |
| Pollutant total | $\sum_i E_{mi}$ versus $\sum_i E_{Oi}$. Signed total bias indicates over- or underestimation. |

VSP errors use **exposure-weighted operating-state VSP**, matching the plotted profiles. No error is assigned to free/queue state times and distances because O does not supply independently observed state allocations.

Cumulative-path WAPE uses cumulative values at the observed bin ends. Both horizontal axes (clock time and cumulative vehicles) display exactly those same values and therefore have one common error measure. These cumulative discrepancies are correlated; they are descriptive path comparisons, not independent emission observations. Final-total APE can be smaller than five-minute emission WAPE because positive and negative bin errors can cancel.

### Reference limitations

The reference O uses five-minute point speed as a proxy for whole-link travel speed. All VSP calculations assume zero acceleration and zero grade. Thus differences in these profiles are comparisons under a common diagnostic alignment, **not pointwise errors against measured trajectory VSP or tailpipe emissions**.

The audit checks allocation counts, travel-time/distance identities, VSP exposure conservation and all 2,740 episode-method-pollutant totals. Discrete M/A integration can differ slightly from the closed-form episode total because of quadrature; the reconciliation reports this explicitly, using a $10^{-9}$ relative and $10^{-8}$ g absolute comparison tolerance. Model duration remains visible in every case and is not forced to equal the observed window.

## Regeneration

### Traffic parameters and conditional inverse diagnostics

[traffic_parameters.csv](traffic_parameters.csv) joins the saved episode estimates, detector FD parameters, calibration support and PeMS network metadata. The metadata's total capacity is divided by its lane count; Arizona metadata capacity is left missing. Queue speeds labeled observed are **FD-inferred from $D/P$**, not directly measured; algebraic values outside the congested FD domain are flagged. S3 speed at capacity and the episode-detection threshold are distinct quantities.

For a candidate queue speed $q$ (here a speed, not flow), retain $D,L,v_f,\widehat{\bar w},\widehat w_{max}$ and calculate

$$\bar t_q(q)=\frac{v_f\widehat{\bar w}}{v_f-q},\qquad
\bar t_f(q)=T_f-\frac{q\widehat{\bar w}}{v_f-q},\qquad
M_p(q)=D[\bar t_f(q)r_p(v_f)+\bar t_q(q)r_p(q)].$$

The physical range is $0<q\le L/(T_f+\widehat w_{max})$, which ensures nonnegative free-state time throughout the episode, not only on average. The CO₂ strategy minimizes $|M_{CO2}/O_{CO2}-1|$. The balanced strategy minimizes $\frac14\sum_p(M_p/O_p-1)^2$, with one common speed for all four pollutants. These are inverse diagnostics against the recorded-speed reference O, not independent FD calibration or measured emissions.

The solver treats every lookup interval separately, retains all exact roots and checks one-sided limits at rate jumps. Among equal optima, it selects the speed nearest the original fitted speed. A theoretical boundary limit need not be attained; the CSV records both its limiting objective and the actual residual at a nearby in-band speed. [Numerical tolerances and assumptions](inverse_queue_speed_equations.json) are explicit.

With positive backward-wave magnitude $\omega$, the three conditional FD inverses are

$$\mu^*=\frac{k_{j0}q\omega_0}{\omega_0+q},\qquad
\omega^*=\frac{\mu_0q}{k_{j0}q-\mu_0},\qquad
k_j^*=\frac{\mu_0}{q}+\frac{\mu_0}{\omega_0}.$$

Each holds the other two quantities fixed. A positive finite $\omega^*$ requires $k_{j0}q>\mu_0$. The discharge alternative implies a new duration $D/\mu^*$. A changed wave/density pair implies $C^*=v_f\omega^*k_j^*/(v_f+\omega^*)$; a changed capacity would require revisiting D/C and the QVDF predictions before adoption.

The bounded joint analysis holds $\mu_0=D/\widehat P$ fixed. Exact pairs satisfy $k_j(\omega)=\mu_0/q+\mu_0/\omega$. It preserves the original capacity when that is compatible with the selected emission optimum; otherwise it selects the closest implied capacity among pairs attaining that optimum. Unreachable targets are reoptimized over physically attainable speeds inside the parameter box. Thus this existing analysis **already allows capacity to change**; it does not impose fixed capacity as a constraint. The primary exploratory bounds are $k_j\in[150,300]$ veh/mi/lane and $\omega\in[5,20]$ mph; the secondary run lowers the wave bound to 3 mph. The [bounded-pair page](fd_sensitivity.html), [summary page](fd_summary.html) and [FD verification record](fd_sensitivity_verification.json) document these assumptions.

The new [capacity comparison](fd_capacity_comparison.html) adds a **strictly fixed-capacity alternative**. Both alternatives retain demand, free-flow speed, fitted duration, delay and discharge, and optimize the same emission objective inside the same FD bounds. The free-capacity alternative reproduces the existing bounded emission optimum. The strict alternative additionally requires the original capacity to remain unchanged. Its capacity constraint can make some cases infeasible, so pooled comparisons use the same feasible cases.

The [separate capacity report](../../../capacity_sensitivity/report.html) goes further: it propagates capacity changes through the demand-to-capacity ratio and subsequent traffic predictions. It distinguishes unchanged coefficients from the stated duration-coefficient rescaling and reports physical feasibility and common-cohort errors. Neither analysis replaces the archived calibration.

| File | Use |
|---|---|
| [inverse_queue_speed.csv](inverse_queue_speed.csv) | Two target strategies per episode, four pollutant outcomes and all three FD inverses. |
| [inverse_queue_speed_candidates.csv](inverse_queue_speed_candidates.csv) | Interval roots, stationary points, endpoints and one-sided limits with actual and limiting objectives. |
| [inverse_queue_speed_roots.csv](inverse_queue_speed_roots.csv) | Exact pollutant-specific roots for diagnosing uniqueness; these are not the primary common-speed strategies. |
| [fd_parameter_sensitivity.csv](fd_parameter_sensitivity.csv) | Primary bounded joint pairs, capacity consequences and residual emission errors. |
| [fd_parameter_sensitivity_expanded.csv](fd_parameter_sensitivity_expanded.csv) | Corresponding results allowing backward-wave magnitudes down to 3 mph. |
| [fd_bound_sensitivity_summary.csv](fd_bound_sensitivity_summary.csv) | Feasibility and capacity-preservation counts under both explicit boxes. |
| [fd_capacity_comparison.csv](fd_capacity_comparison.csv) | Side-by-side strict/free capacity results, 137 cases × two targets × two FD boxes. |
| [Separate full capacity comparison](../../../capacity_sensitivity/fixed_traffic_comparison.csv) | Both capacity policies in long form, including feasibility and pollutant totals. |

Candidate pairs are episode-level diagnostics. Repeated episodes at a detector require a consistent detector FD before any revised parameters can be adopted.

### Reproduce the pages

From the repository root after installing the project dependencies:

```bash
python debug/full_experiment/scripts/build_episode_time_series.py
```

The default output is the ignored `debug/output/episode_time_series/` directory. It writes all CSVs, HTML pages and 685 diagnostic figures, each in PNG and SVG. The published tables in this folder are protected from accidental overwrite. `--workers 2` controls plotting concurrency; `--skip-figures` reproduces all numerical results and checks without regenerating figures. The HTML pages expect the figures from a full run.

`--plots-only` redraws figures from an existing numerical run. Optional `--plot-start 1 --plot-end 35` limits this to the inclusive case range in the index; separate processes can draw disjoint ranges. Use `--workers 1` if the environment does not permit Python process pools. After all ranges finish, `--verify-figures` checks all 685 PNG/SVG pairs and records completion without recalculating the tables.

This step reuses the full calculation tables in [step 7](../07_observed_and_single_speed/README.md), [step 8](../08_reconstruction_and_two_speed/README.md) and [step 9](../09_totals_and_comparison/README.md). It does not rerun episode detection or calibration.
