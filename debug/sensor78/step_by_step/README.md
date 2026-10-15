# Detector 78: step-by-step calculation results

Follow the numbered folders to inspect each input, arithmetic operation and result. **78 is the detector ID:** this is one fixed 57-bin worked example, averaged from 16 complete weekdays. It is separate from the 137 retained paper episodes and does not replace any of them.

| Step | Open | What you can check |
| --- | --- | --- |
| 1 | [Raw records and day screening](01_raw_day_screening/README.md) | All 5,999 records, 21 day decisions and the 16-day retained sample. |
| 2 | [Average weekday](02_average_weekday/README.md) | The count sums and count/speed sums behind all 288 averages. |
| 3 | [Selected window](03_selected_window/README.md) | The 57 bins from 14:45 to 19:30, counts, travel times and vehicle-hours. |
| 4 | [Traffic calculation](04_traffic_calculation/README.md) | Existing calibration inputs; demand, duration, delay, queue speed and time allocation. |
| 5 | [VSP and emission-rate calculation](05_emission_rates/README.md) | Per-method VSP power terms, separate lookup decisions, age weights and cubic terms. |
| 6 | [Five method calculations](06_method_calculations/README.md) | O/S/R/M/A arithmetic for all four pollutants, including each integration group. |
| 7 | [Common-clock profiles](07_common_clock/README.md) | The node-to-bin allocation and all five speeds, rates, emissions and cumulative totals. |
| 8 | [Totals and differences](08_totals_and_errors/README.md) | Final totals, error components and reconciliation to the existing report. |

Each CSV holds full-precision calculated values, with formulas in its step guide. For live cell formulas, use the existing [Excel workbook](../workbook/Sensor78_Emission_Comparison_Simple.xlsx). [Column definitions](column_dictionary.csv) cover every column in every numbered CSV; the [inventory](table_inventory.csv) gives row counts.

**Each numbered guide includes a diagnostic figure**, with an editable SVG beside its PNG preview. The VSP arithmetic and rate lookup are separate tables: this makes it possible to see whether a difference arises before or after rate selection. The common-clock VSP comparison is weighted by operating time and does not substitute VSP at a whole-link equivalent speed for the two-speed states.

## Quantities used throughout

| Symbol | Meaning | Unit |
| --- | --- | --- |
| $d_i$, $v_i$ | Average count and harmonic speed of observed bin $i$ | veh/lane; mph |
| $D=\sum_i d_i$ | Count over the selected window | veh/lane |
| $L$, $v_f$, $C$, $k_j$ | Link length, free speed, hourly capacity, jam density | mi; mph; veh/h/lane; veh/mi/lane |
| $x=D/C$, $P$ | Capacity-clearing duration and fitted congestion duration | h |
| $T_f=L/v_f$, $w$, $\bar w$ | Uncongested travel time, fitted delay, mean delay | h/veh |
| $\mu$, $v_q$ | Fitted discharge rate and FD queue speed | veh/h/lane; mph |
| $t_f$, $t_q$ | Time spent at free and queue operating speeds | h/veh |
| $H$ | Sum of whole-link vehicle travel times | veh h/lane |
| $u_j$, $g_j$, $N_j$ | Integration position, Gauss weight, modeled group count | dimensionless; dimensionless; veh/lane |
| $r_p(v)$, $\widetilde r_p(v)$ | Lookup and cubic rate for pollutant $p$ | g/(veh h) |
| $E_{m,p}$ | Total for method $m$ and pollutant $p$ | g/lane |

The recalculated demand is **4,789.25 veh/lane**; observed and fitted vehicle-hours are **211.434** and **197.040 veh h/lane**. All **20** method/pollutant totals match the current report within floating-point precision: [verification](verification.json).

The O reference treats detector speed as a whole-link trip-speed proxy. It is not measured tailpipe emissions or observed vehicle trajectories. The shared-clock series assigns complete-trip emissions to counted vehicle groups; it does not infer when exhaust was physically released.

## Recreate these tables

From the repository root, with Python, NumPy, pandas and Matplotlib:

```sh
python debug/sensor78/step_by_step/build_steps.py
```

New numerical tables go to `debug/output/sensor78_steps/`; `--output-dir PATH` permits another empty directory. The builder protects canonical inputs and published references. It reconstructs the results from [canonical inputs](../../../data/inputs/detector78/README.md), uses the existing PM calibration without refitting, and compares against the current result tables. These guides accompany the published tables; the rebuild writes numerical outputs and verification, not a new report.
