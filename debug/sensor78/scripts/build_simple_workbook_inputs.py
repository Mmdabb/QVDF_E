"""Prepare compact inputs and independent audit data; does not author Excel files."""
from pathlib import Path
import bisect
import hashlib
import json
import math

import numpy as np
import pandas as pd

from debug_support import locations, load_inputs
HERE, ROOT, OUT = locations()
_, cfg, expected = load_inputs(ROOT)
SUPPORT = ROOT / 'data/inputs/detector78'
state = json.loads((OUT / "calculation_inputs_and_state.json").read_text())
profile = pd.read_csv(OUT / "observed_episode_profile.csv")
common = pd.read_csv(OUT / "common_time_series.csv")
qref = pd.read_csv(OUT / "reconstructed_integration.csv")
rates = {int(row["OpModeID"]): row for row in expected["lookup_rates"]}
pollutants = ["CO2", "NOx", "CO", "HC"]
vehicle = cfg["vehicle"]


def vsp(v):
    ms = float(v) * .44704
    return (vehicle["rolling_term_a"] * ms
            + vehicle["rotating_term_b"] * ms * ms
            + vehicle["drag_term_c"] * ms ** 3) / vehicle["source_mass"]


def mode(v):
    v = float(v)
    if v <= 0:
        return 1
    z = vsp(v)
    pairs = ([(0, 11), (3, 12), (6, 13), (9, 14), (12, 15)] if v < 25
             else [(0, 21), (3, 22), (6, 23), (9, 24), (12, 25),
                   (18, 27), (24, 28), (30, 29)] if v < 50
             else [(6, 33), (12, 35), (18, 37), (24, 38), (30, 39)])
    for threshold, code in pairs:
        if z < threshold:
            return code
    return 16 if v < 25 else 30 if v < 50 else 40


def transition(threshold):
    # First representable positive speed at which the strict VSP cutoff changes.
    lo, hi = 0., 200.
    while math.nextafter(lo, math.inf) < hi:
        mid = (lo + hi) / 2
        if mid == lo or mid == hi:
            break
        if vsp(mid) < threshold:
            lo = mid
        else:
            hi = mid
    assert vsp(hi) >= threshold
    assert vsp(math.nextafter(hi, -math.inf)) < threshold
    return hi


candidate = [25., 50.] + [transition(t) for t in [3., 6., 9., 12., 18., 24., 30.]]
breaks = [0.] + sorted(x for x in candidate
                        if mode(math.nextafter(x, -math.inf)) != mode(x))
rate_rows = []
for index, lower in enumerate(breaks):
    representative = math.nextafter(0., math.inf) if lower == 0 else lower
    code = mode(representative)
    rate_rows.append({
        "speed_lower_mph": lower,
        "speed_upper_mph": breaks[index + 1] if index + 1 < len(breaks) else None,
        "lower_inclusive": lower != 0,
        "upper_inclusive": False,
        "vsp_at_lower_kw_tonne": vsp(lower),
        "source_operating_mode": code,
        **{f"{p}_g_per_veh_h": rates[code][p] for p in pollutants},
    })


def compact_mode(v):
    if v <= 0:
        raise ValueError("The compact table is restricted to positive speeds.")
    return rate_rows[bisect.bisect_right(breaks, float(v)) - 1]["source_operating_mode"]


tests = list(np.linspace(.000001, 150., 300001))
for x in candidate:
    tests.extend([math.nextafter(x, -math.inf), x, math.nextafter(x, math.inf),
                  x - 1e-10, x + 1e-10, x - 1e-7, x + 1e-7])
tests.extend(profile.v.tolist())
tests.extend(qref.speed_mph.tolist())
tests.extend([state["vf"], state["vq"], state["v_mean"], state["pred_mean_speed"]])
mismatch = [(v, mode(v), compact_mode(v)) for v in tests if mode(v) != compact_mode(v)]
assert not mismatch, mismatch[:5]

card = cfg["tracks"]["average_weekday"]["sensor_card"]
par = cfg["tracks"]["average_weekday"]["calibration_by_period"][0]
traffic = [
    ("sensor", 78, "ID", "Worked example; AZ I-10 westbound detector 78."),
    ("length_mi", card["L_mi"], "mi", "Upstream detector spacing."),
    ("capacity_veh_h_lane", card["C_vphpl"], "veh/h/lane", "Retained detector calibration."),
    ("free_speed_mph", card["vf_mph"], "mph", "Retained detector calibration."),
    ("jam_density_veh_mi_lane", card["kj"], "veh/mi/lane", "Fixed traffic assumption."),
    ("fd", par["fd"], "h^(1-n)", "PM corridor-direction calibration."),
    ("n", par["n"], "dimensionless", "PM corridor-direction calibration."),
    ("fp", par["fp"], "h^(-s)", "PM corridor-direction calibration."),
    ("s", par["s"], "dimensionless", "PM corridor-direction calibration."),
    ("theta", par["theta"], "dimensionless", "Mean delay divided by peak delay."),
    ("bin_minutes", 5, "min", "Fixed input time step."),
    ("profile_start_hour", 14.75, "h", "Fixed selected episode start, inclusive."),
    ("profile_end_hour", 19.5, "h", "Fixed selected episode end, exclusive."),
    ("volume_multiplier", 1., "dimensionless", "Input counts assumed per represented lane; do not divide by five."),
    ("cubic_min_speed_mph", 5., "mph", "Lower fitted cubic-rate limit."),
    ("cubic_max_speed_mph", 75., "mph", "Upper fitted cubic-rate limit."),
]

result = {
    "schema": "detector78_compact_workbook_inputs_1",
    "purpose": "Eight-sheet workbook with live formulas. Raw observations and numerical integration inputs are constants; derived time series must be formulas.",
    "sheet_order": ["01 Traffic inputs", "02 Emission inputs", "03 O recorded", "04 S mean speed", "05 R reconstructed", "06 M two speed", "07 A cubic two speed", "08 Results"],
    "traffic_inputs": [{"key": k, "value": v, "unit": u, "note": n} for k, v, u, n in traffic],
    "profile_rows": [
        {"clock_time": r.clock_time, "excel_time": r.clock_h / 24.,
         "clock_hour": r.clock_h, "volume_veh_5min": r.d, "speed_mph": r.v}
        for r in profile.itertuples()],
    "rate_table": rate_rows,
    "rate_lookup_rule": "For positive speed v, use the last row with speed_lower_mph <= v. First row covers 0 < v < 25. No interpolation. The final row has no finite upper bound. Zero/negative speeds are invalid traffic inputs and must not use this positive-speed table.",
    "vsp_display_formula": "(0.156461*z + 0.00200193*z^2 + 0.000492646*z^3)/1.4788; z = mph*0.44704; acceleration=0, grade=0.",
    "rate_table_scope": "Passenger-car zero-acceleration rates with original normalized age mixture already aggregated; VSP shown is at the lower speed boundary. Editing rate cells changes lookup-based methods; it does not refit the cubic coefficients.",
    "cubic_coefficients": cfg["cubic_coefficients"],
    "cubic_coefficient_placement": "Small labeled calibrated-input block at top of A method sheet; retain emission input sheet as only speed/VSP/rate table.",
    "quadrature_384": cfg["gauss_legendre_384"],
    "shape_helper": {
        "location": "Visible secondary calculation block below R time series; no extra sheet.",
        "beta_branch_condition": "0 < theta <= 2/3",
        "beta_shape": "h(u)=[4u(1-u)]^a",
        "beta_integral_excel": "EXP(a*LN(4)+2*GAMMALN(a+1)-GAMMALN(2*a+2))",
        "bisection_iterations": 50,
        "initial_lower_a": 1.,
        "initial_upper_a": 10000.,
        "bisection_rule": "mid=(lo+hi)/2; if integral(mid)>theta use lo=mid else hi=mid; next step uses prior bounds.",
        "flatter_branch_condition": "2/3 < theta < 1",
        "flatter_exponent": "b=theta/(1-theta)",
        "flatter_shape": "h(u)=1-ABS(2u-1)^b",
        "checks": "0<theta<1; integral(initial_upper)<=theta for beta branch; nonnegative analytical minimum arrival weight; nonnegative free-flow time at peak; 5<=vq<vf<=75 for cubic method.",
    },
    "common_time_alignment": {
        "meaning": "Complete-link trip emissions attributed to recorded five-minute vehicle groups in cumulative-count order; not instantaneous roadway exhaust measured during that clock interval.",
        "formula": "overlap_ij=MAX(0,MIN(B_i,N_j)-MAX(B_(i-1),N_(j-1))); sum_j overlap_ij*per_vehicle_quantity_j; B is observed cumulative count and N is fitted quadrature cumulative count.",
        "efficient_alternative": "Build cumulative node counts and cumulative weighted quantities. Piecewise-linearly interpolate each cumulative quantity at observed bin count edges with INDEX/MATCH, then difference adjacent edges. Clamp final cumulative node count to D only for roundoff (<1e-8 at default).",
        "R_effective_speed": "d_i*L/H_R_i",
        "M_A_effective_speed": "L/(mean_Tfree_i+mean_Tqueue_i); same as R after conservative attribution",
        "effective_rate": "E_i/H_i; for R this is generally not r0(effective_speed_i) because sub-bin speed groups use separate rates.",
    },
    "provenance": {
        "retained_weekdays": state["retained_days"],
        "number_retained_weekdays": len(state["retained_days"]),
        "calibration_scope": par["calibration_scope"],
        "calibration_period": par["period"],
        "calibration_source_episodes": par["N_source"],
        "calibration_source": "data/inputs/detector78/calibration_inputs.json",
        "profile_source": "debug/output/sensor78/detector78/observed_episode_profile.csv",
        "common_time_reference_source": "debug/output/sensor78/detector78/common_time_series.csv",
        "profile_sha256": hashlib.sha256((OUT / "observed_episode_profile.csv").read_bytes()).hexdigest(),
        "scope": "Standalone worked example of 57 bins, not a reproduction of a retained paper episode. Fixed episode boundaries are not redetected when inputs change. Monthly averaging was already completed upstream.",
    },
    "validation_only": {
        "expected_state": state,
        "expected_common_time_rows": common.to_dict(orient="records"),
        "rate_breakpoint_audit": {"tested_speed_values": len(tests), "dense_grid_min_mph": .000001, "dense_grid_max_mph": 150., "mismatches": len(mismatch), "positive_speed_bands": len(rate_rows), "boundary_neighbors_tested": True},
    },
}
target = OUT / "simple_workbook_inputs.json"
target.write_text(json.dumps(result, indent=2, allow_nan=False))
audit = result["validation_only"]["rate_breakpoint_audit"]
(OUT / "simple_workbook_input_audit.json").write_text(json.dumps(audit, indent=2))
print(json.dumps({"output": str(target), "bytes": target.stat().st_size, "traffic_rows": len(profile), "rate_bands": len(rate_rows), "nodes": len(cfg["gauss_legendre_384"]), "rate_audit": audit}, indent=2))
