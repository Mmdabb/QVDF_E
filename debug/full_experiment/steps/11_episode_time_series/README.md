# 11. Five-minute comparisons for every retained episode

Open **[the case list](EPISODES.md)** to view all 137 cases directly in GitHub, or open **[the episode browser](index.html)** locally for filtering. Each case contains a traffic dashboard, a dashboard for each of the four pollutants, and the corresponding calculation CSVs. [episode_index.csv](episode_index.csv) maps the compact `ep001`–`ep137` labels to full original episode IDs, detector, date, direction and period.

Browse the [episode folders](episodes/), or go directly to [Arizona detector 141, November 2016, episode ep014](episodes/ep014_AZ_I10_W_141_20161101/README.md), the case used in the separate worked-example PDF.

These are the same 137 retained average-profile episodes used in the reported comparison. No parameter, model total or sample decision is changed.

Dates in the index identify the source average profiles; Arizona dates are monthly profile labels, not individual observed days. The full episode ID and source-profile label are retained in the index for joining back to the earlier calculation steps.

## Files and reading order

| File | Contents |
|---|---|
| `episodes/<case>/traffic_timeseries.csv` | Every observed five-minute bin × O/S/R/M/A: count, travel time, delay, equivalent speed, exposure-weighted VSP, VSP at equivalent speed, and M/A free/queue times and distances. |
| `episodes/<case>/emissions_timeseries.csv` | Every bin × five methods × four pollutants: vehicle-hours, effective rate, assigned bin emission, cumulative emission and cumulative count. |
| `episodes/<case>/node_to_bin_allocation.csv` | Positive overlaps between each observed count interval and modeled integration-node count interval; the explicit allocation weights. |
| `episodes/<case>/traffic_profiles.png` and `.svg` | Speed, travel time, delay, VSP, two-speed time allocation and two-speed distance allocation. |
| `episodes/<case>/emissions_<pollutant>.png` and `.svg` | Rate, five-minute emissions, cumulative emissions versus time, and the **same cumulative series** versus cumulative vehicles. |
| [all_traffic_timeseries.csv.gz](all_traffic_timeseries.csv.gz) | All 24,000 bin-method traffic rows in one compressed CSV. |
| [all_emissions_timeseries.csv.gz](all_emissions_timeseries.csv.gz) | All 96,000 bin-method-pollutant rows in one compressed CSV. |
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

The reference O uses five-minute point speed as a proxy for whole-link travel speed. All VSP calculations assume zero acceleration and zero grade. Thus differences in these profiles are comparisons under a common diagnostic alignment, **not pointwise errors against measured trajectory VSP or tailpipe emissions**.

The audit checks allocation counts, travel-time/distance identities, VSP exposure conservation and all 2,740 episode-method-pollutant totals. Discrete M/A integration can differ slightly from the closed-form episode total because of quadrature; the reconciliation reports this explicitly, using a $10^{-9}$ relative and $10^{-8}$ g absolute comparison tolerance. Model duration remains visible in every case and is not forced to equal the observed window.

## Regeneration

From the repository root after installing the project dependencies:

```bash
python debug/full_experiment/scripts/build_episode_time_series.py
```

The default output is the ignored `debug/output/episode_time_series/` directory. It writes all CSVs, HTML pages and 685 diagnostic figures, each in PNG and SVG. The published tables in this folder are protected from accidental overwrite. `--workers 2` controls plotting concurrency; `--skip-figures` reproduces all numerical results and checks without regenerating figures. The HTML pages expect the figures from a full run.

`--plots-only` redraws figures from an existing numerical run. Optional `--plot-start 1 --plot-end 35` limits this to the inclusive case range in the index; separate processes can draw disjoint ranges. Use `--workers 1` if the environment does not permit Python process pools. After all ranges finish, `--verify-figures` checks all 685 PNG/SVG pairs and records completion without recalculating the tables.

This step reuses the full calculation tables in [step 7](../07_observed_and_single_speed/README.md), [step 8](../08_reconstruction_and_two_speed/README.md) and [step 9](../09_totals_and_comparison/README.md). It does not rerun episode detection or calibration.
