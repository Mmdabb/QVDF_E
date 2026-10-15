"""Export a numerical calculation ledger for the preserved detector-78 example.

Run from any directory with Python, NumPy and pandas. Inputs and calibration stay
unchanged; generated output defaults to debug/output/sensor78_steps.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUT = ROOT / "data/inputs/detector78"
REFERENCE = ROOT / "debug/sensor78/results"
POLS = ("CO2", "NOx", "CO", "HC")
STEPS = ("01_raw_day_screening", "02_average_weekday", "03_selected_window",
         "04_traffic_calculation", "05_emission_rates", "06_method_calculations",
         "07_common_clock", "08_totals_and_errors")


def output_path():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "debug/output/sensor78_steps")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    generated = ROOT / "debug/output"
    if out == ROOT or out in ROOT.parents:
        parser.error("Output cannot be the repository or an ancestor.")
    protected = [ROOT / s for s in ("data", "src", "reproduce", "tools", "tests", ".git")]
    protected += [p for p in (ROOT / "debug").iterdir() if p.is_dir() and p.name != "output"]
    if any(out == p or p in out.parents or out in p.parents for p in protected):
        parser.error("Output overlaps canonical input, code or published references.")
    if ROOT / "debug" in out.parents and not (out == generated or generated in out.parents):
        parser.error("Inside debug, generated output must be under debug/output.")
    marker = out / ".sensor78-step-ledger.json"
    if out.exists() and not out.is_dir():
        parser.error("Output must be a directory.")
    if out.exists() and any(out.iterdir()):
        try:
            owned = json.loads(marker.read_text())["owner"] == "qvdfe-sensor78-step-ledger"
        except (OSError, ValueError, KeyError):
            owned = False
        if not owned:
            parser.error("Choose an empty output directory or a previous step-ledger output.")
    out.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"owner": "qvdfe-sensor78-step-ledger", "schema": 1}))
    return out


def build(out):
    cfg = json.loads((INPUT / "calibration_inputs.json").read_text())
    compact = json.loads((INPUT / "calculation_inputs.json").read_text())
    raw_source = json.loads((INPUT / "raw_source.json").read_text())
    card = cfg["tracks"]["average_weekday"]["sensor_card"]
    par = cfg["tracks"]["average_weekday"]["calibration_by_period"][0]
    dictionary = []
    tables = []
    definitions = {}

    def define(names, unit, meaning):
        for name in names.split():
            definitions[name] = (unit, meaning)

    define("raw_row_id", "index", "One-based supplied raw record order, stable join key.")
    define("date", "YYYY-MM-DD", "Supplied January 2016 date.")
    define("clock_time", "HH:MM:SS", "Start of the five-minute detector bin.")
    define("sensor", "ID", "Detector ID, 78.")
    define("volume_veh_5min count_veh_5min", "veh/lane/bin", "Supplied or averaged count; multiplier 1, no division by five lanes.")
    define("speed_mph", "mph", "Speed specified for the row; raw, harmonic mean or reconstructed as documented by its step.")
    define("length_mi", "mi", "Supplied link length.")
    define("source_retained_date", "flag", "Original source flag, preserved for comparison, not used in retention.")
    define("source_travel_time_h", "h", "Original source time, preserved; not used because calculations use L/v.")
    define("weekday valid_speed valid_count valid_record retained_day", "Boolean", "Named condition: weekday; 0<v<=90; count>=0; all three; or complete retained day.")
    define("count_over_speed", "veh h/(mi lane)", "Count/speed; denominator contribution to the count-weighted harmonic speed.")
    define("row_count unique_times valid_rows contributing_days", "count", "Named count of records, distinct timestamps, valid records or retained days contributing.")
    define("retention_reason", "text", "Retained or explicit failed day-level rule(s).")
    define("sum_count", "veh/lane", "Sum of counts across the 16 retained days at this time of day.")
    define("sum_count_over_speed", "veh h/(mi lane)", "Sum of count/speed over retained days at this time of day.")
    define("clock_h", "h after midnight", "Clock time converted to decimal hours.")
    define("bin_id node_id", "index", "One-based chronological bin or quadrature-node join key.")
    define("trip_time_h", "h/veh", "Whole-link travel time L/v = Tf+w for reconstructed groups.")
    define("vehicle_hours", "veh h/lane", "Vehicle count times whole-link travel time.")
    define("cum_count_start cum_count_end", "veh/lane", "Start/end cumulative count boundary for this observed bin or modeled group.")
    define("cum_vehicle_hours", "veh h/lane", "Cumulative whole-link vehicle-hours through this row.")
    define("key value unit formula_or_source note", "see row", "Named input or result, numeric value, unit, formula/source and interpretation.")
    define("u gauss_weight h dh_du arrival_factor", "dimensionless", "Respectively quadrature position, integration weight, normalized delay shape, shape derivative, and 1+(w_peak/P)*dh/du.")
    define("entry_elapsed_h delay_h free_time_h queue_time_h", "h/veh", "Elapsed entry-time coordinate, fitted delay, free-flow time or queue time.")
    define("vehicle_weight", "veh/lane", "D times Gauss weight times arrival factor; integration group count, not a raw observed count.")
    define("arrival_rate_veh_h_lane", "veh/h/lane", "mu times arrival factor.")
    define("free_distance_mi queue_distance_mi distance_residual_mi", "mi", "vf*tf, vq*tq, or their sum minus L.")
    define("time_residual_h", "h", "tf+tq-(Tf+w); zero within floating-point precision.")
    define("age", "years", "Vehicle age in the supplied passenger-car age mixture.")
    define("raw_weight normalized_weight", "weight", "Supplied age weight or raw weight divided by the sum of all age weights.")
    define("operating_mode", "ID", "MOVES operating-mode lookup selected from speed and VSP bands.")
    define("pollutant", "name", "CO2, NOx, CO or HC.")
    define("raw_rate_g_veh_h weighted_rate_g_veh_h rate_g_veh_h lookup_rate_g_veh_h cubic_rate_g_veh_h", "g/(veh h)", "Named raw, age-weighted contribution, selected, lookup or cubic emission rate.")
    define("speed_lower_mph speed_upper_mph", "mph", "Positive-speed lookup interval; blank final upper bound means unbounded.")
    define("lower_inclusive upper_inclusive", "Boolean", "Whether the lookup interval includes the named endpoint.")
    define("vsp_kw_tonne", "kW/tonne", "Steady-speed, level-road VSP using supplied vehicle coefficients and mph-to-m/s conversion.")
    define("c0", "g/(veh h)", "Constant term in cubic rate c0+c1*v+c2*v^2+c3*v^3.")
    define("c1", "g/(veh h mph)", "Linear-speed coefficient.")
    define("c2", "g/(veh h mph^2)", "Quadratic-speed coefficient.")
    define("c3", "g/(veh h mph^3)", "Cubic-speed coefficient.")
    define("speed_min_mph speed_max_mph", "mph", "Supplied cubic fit domain endpoint, 5 and 75 mph.")
    define("state", "name", "One of free speed, queue speed, observed mean speed or fitted mean speed.")
    define("free_speed_mph queue_speed_mph", "mph", "Operating speeds vf and vq, common to modeled groups.")
    define("free_rate_g_veh_h queue_rate_g_veh_h", "g/(veh h)", "Rate evaluated at vf or vq, lookup for M and cubic for A.")
    define("free_vehicle_hours queue_vehicle_hours", "veh h/lane", "Group count times free-flow or queue time.")
    define("free_emission_g queue_emission_g emission_g", "g/lane", "Free contribution, queue contribution or total complete-link emissions for the row.")
    define("cubic_constant_g_veh_h cubic_linear_g_veh_h cubic_quadratic_g_veh_h cubic_cubic_g_veh_h", "g/(veh h)", "Separate c0, c1*v, c2*v^2 or c3*v^3 terms before summation.")
    define("method", "code", "O recorded proxy; S single mean; R reconstructed; M two-speed lookup; A two-speed cubic; S_pred is a diagnostic intermediate.")
    define("overlap_count", "veh/lane", "Intersection length of observed-bin and modeled-node cumulative-count intervals.")
    define("node_fraction", "fraction", "Overlap count divided by node vehicle weight; allocates node time/emissions conservatively.")
    define("effective_speed_mph", "mph", "Bin count*L/bin vehicle-hours; common to R/M/A.")
    define("effective_rate_g_veh_h", "g/(veh h)", "Bin emission/bin vehicle-hours; not generally lookup at effective speed.")
    define("cumulative_emission_g", "g/lane", "Sum of assigned bin emissions through this clock bin.")
    define("O_reference_g signed_error_g absolute_error_g", "g/lane", "O episode total, method-minus-O difference, or its absolute value.")
    define("signed_error_pct absolute_error_pct", "%", "100*(method/O-1), or its absolute value; one-case WAPE equals the latter.")
    define("stage", "index", "Ordered signed-accounting stage, 1 through 5.")
    define("component", "text", "Meaning of a sequential change between emission representations.")
    define("from_g to_g delta_g", "g/lane", "Emission before/after one accounting step and after-minus-before change.")
    define("delta_pct_of_O", "% of O", "100*delta_g/O; signed components add to a signed discrepancy.")
    define("H_observed H_predicted", "veh h/lane", "Observed-proxy or fitted complete-link vehicle-hours.")
    define("rate_observed_mean_g_veh_h rate_predicted_mean_g_veh_h", "g/(veh h)", "Lookup at DL/H_observed or DL/H_predicted.")
    define("exposure_component_g rate_component_g net_component_g", "g/lane", "Exact symmetric decomposition of S_pred-S into vehicle-hours and induced mean-speed/rate terms.")
    define("published_emission_g difference_g relative_difference", "see name", "Published current total (g), recalculated minus published total (g), and difference/published.")
    define("vsp_record_id", "index", "Stable one-based key joining separate operating-speed VSP arithmetic to rate selection.")
    define("operating_state", "name", "Whole-link speed, or free/queue operating speed. Missing bin/node IDs mean a whole-episode aggregate.")
    define("speed_mps", "m/s", "speed_mph times 0.44704.")
    define("rolling_power_kw rotating_power_kw drag_power_kw total_power_kw", "kW", "A*s, B*s^2, Cd*s^3, or their sum, for speed s in m/s.")
    define("mass_tonne", "tonne", "Supplied passenger-car mass; total road-load power divided by this gives VSP.")
    define("speed_band", "mph interval", "MOVES speed class: (0,25), [25,50), or [50,infinity); used with VSP to select the operating mode.")
    define("rate_use", "text", "Whether the selected lookup rate is an actual input or an M-versus-A diagnostic comparison; A uses the cubic rate.")
    define("exposure_weighted_vsp_kw_tonne vsp_at_effective_speed_kw_tonne difference_from_O_vsp_kw_tonne", "kW/tonne", "Within-bin time-weighted operating VSP, VSP evaluated at the whole-link equivalent bin speed, or the first quantity minus O's bin VSP.")
    define("mean_vsp_kw_tonne vsp_sd_kw_tonne vsp_mean_bias_vs_O_kw_tonne vsp_MAE_vs_O_kw_tonne vsp_RMSE_vs_O_kw_tonne", "kW/tonne", "Operating-VSP exposure mean/standard deviation, or common-bin VSP difference bias/MAE/RMSE weighted by O vehicle-hours; descriptive differences from the proxy, not validation against measured VSP.")
    for p in POLS:
        define(f"lookup_{p}_g_veh_h", "g/(veh h)", f"Age-weighted {p} rate at the selected operating mode; supplied to O/S/R/M, compared with A cubic evaluation.")

    def csv(step, name, frame):
        frame = pd.DataFrame(frame)
        folder = out / STEPS[step - 1]
        folder.mkdir(parents=True, exist_ok=True)
        relative = f"{STEPS[step-1]}/{name}"
        for col in frame.columns:
            if col not in definitions:
                raise ValueError(f"Missing column definition: {relative}:{col}")
            unit, meaning = definitions[col]
            dictionary.append({"file": relative, "column": col, "unit": unit, "definition": meaning})
        frame.to_csv(folder / name, index=False, lineterminator="\n")
        tables.append({"file": relative, "rows": len(frame), "columns": len(frame.columns)})
        return frame

    raw = pd.DataFrame(raw_source["raw_rows"], columns=raw_source["raw_columns"])
    raw.insert(0, "raw_row_id", np.arange(1, len(raw) + 1))
    dt = pd.to_datetime(raw.date + " " + raw.clock_time)
    raw["weekday"] = dt.dt.dayofweek < 5
    raw["valid_speed"] = raw.speed_mph.between(0, 90, inclusive="right")
    raw["valid_count"] = raw.volume_veh_5min.ge(0)
    raw["valid_record"] = raw.weekday & raw.valid_speed & raw.valid_count
    days = raw.groupby("date").agg(row_count=("date", "size"), unique_times=("clock_time", "nunique"), valid_rows=("valid_record", "sum")).reset_index()
    days["retained_day"] = (days.row_count == 288) & (days.unique_times == 288) & (days.valid_rows == 288)
    days["retention_reason"] = days.apply(lambda r: "retained" if r.retained_day else "; ".join([s for flag, s in [(r.row_count != 288, "row count != 288"), (r.unique_times != 288, "unique times != 288"), (r.valid_rows != r.row_count, "one or more invalid records")] if flag]), axis=1)
    retained = days.loc[days.retained_day, "date"]
    raw["retained_day"] = raw.date.isin(retained)
    raw["count_over_speed"] = np.where(raw.valid_speed, raw.volume_veh_5min / raw.speed_mph, np.nan)
    csv(1, "raw_record_decisions.csv", raw)
    csv(1, "day_decisions.csv", days)
    selected = raw.loc[raw.retained_day]
    profile = selected.groupby("clock_time").agg(contributing_days=("date", "nunique"), sum_count=("volume_veh_5min", "sum"), sum_count_over_speed=("count_over_speed", "sum")).reset_index()
    profile["count_veh_5min"] = profile.sum_count / len(retained)
    profile["speed_mph"] = profile.sum_count / profile.sum_count_over_speed
    profile["clock_h"] = profile.clock_time.map(lambda s: sum(float(x)*k for x, k in zip(s.split(":"), [1, 1/60, 1/3600])))
    csv(2, "average_weekday_arithmetic.csv", profile)
    z = profile.loc[profile.clock_h.ge(14.75) & profile.clock_h.lt(19.5), ["clock_time", "clock_h", "count_veh_5min", "speed_mph"]].reset_index(drop=True)
    z.insert(0, "bin_id", np.arange(1, len(z)+1))
    L, vf, C, kj = (card[k] for k in ("L_mi", "vf_mph", "C_vphpl", "kj"))
    z["trip_time_h"] = L / z.speed_mph
    z["vehicle_hours"] = z.count_veh_5min * z.trip_time_h
    z["cum_count_end"] = z.count_veh_5min.cumsum()
    z["cum_count_start"] = z.cum_count_end - z.count_veh_5min
    z["cum_vehicle_hours"] = z.vehicle_hours.cumsum()
    csv(3, "selected_window_arithmetic.csv", z)
    D = z.count_veh_5min.sum(); Tf = L/vf; x = D/C
    power_P = par["fd"] * x**par["n"]; P = max(power_P, x)
    peak = Tf*par["fp"]*P**par["s"]; mean = par["theta"]*peak
    mu = D/P; omega = C/(kj-C/vf); vq = mu/(kj-mu/omega)
    tqbar = vf*mean/(vf-vq); tfbar = Tf-vq*mean/(vf-vq)
    Ho = z.vehicle_hours.sum(); Hp = D*(Tf+mean); vs = D*L/Ho; vp = D*L/Hp
    inputrows = [{"key": r["key"], "value": r["value"], "unit": r["unit"], "formula_or_source": "data/inputs/detector78/calculation_inputs.json:traffic_inputs", "note": r["note"]} for r in compact["traffic_inputs"]]
    inputrows += [{"key": "N_source_PM_calibration", "value": par["N_source"], "unit": "source episodes", "formula_or_source": "calibration_inputs.json:tracks.average_weekday.calibration_by_period", "note": "Existing AZ_I10_W PM corridor-direction calibration, reused without refitting."}, {"key": "shape_bisection_iterations", "value": 60, "unit": "iterations", "formula_or_source": "Maintained detector-78 Python analysis", "note": "The Excel helper uses 50; this ledger follows the current Python calculations (60)."}]
    csv(4, "input_parameters.csv", inputrows)
    state = [("D", D, "veh/lane", "sum_i d_i"), ("Tf", Tf, "h", "L/vf"), ("x", x, "h", "D/C"), ("P_power", power_P, "h", "fd*x^n"), ("P", P, "h", "max(P_power,x)"), ("w_peak", peak, "h", "Tf*fp*P^s"), ("w_mean", mean, "h", "theta*w_peak"), ("mu", mu, "veh/h/lane", "D/P"), ("omega", omega, "mph", "C/(kj-C/vf)"), ("vq", vq, "mph", "mu/(kj-mu/omega)"), ("tq_mean", tqbar, "h", "vf*w_mean/(vf-vq)"), ("tf_mean", tfbar, "h", "Tf-vq*w_mean/(vf-vq)"), ("H_observed", Ho, "veh h/lane", "sum_i d_i*L/v_i"), ("H_predicted", Hp, "veh h/lane", "D*(Tf+w_mean)"), ("v_observed_mean", vs, "mph", "D*L/H_observed"), ("v_predicted_mean", vp, "mph", "D*L/H_predicted"), ("delay_allowance", L*(1/vq-1/vf), "h", "L*(1/vq-1/vf)"), ("peak_free_time", Tf-vq*peak/(vf-vq), "h", "Tf-vq*w_peak/(vf-vq)")]
    lo, hi = 1., 10000.
    bisect = []
    for iteration in range(1, 61):
        a = (lo+hi)/2
        area = math.exp(a*math.log(4)+2*math.lgamma(a+1)-math.lgamma(2*a+2))
        bisect.append({"key": f"iteration_{iteration:02d}", "value": a, "unit": "shape exponent", "formula_or_source": f"lower={lo:.17g}; upper={hi:.17g}; integral={area:.17g}; theta={par['theta']:.17g}", "note": "Set lower=mid if integral>theta; otherwise upper=mid."})
        if area > par["theta"]: lo = a
        else: hi = a
    a = (lo+hi)/2
    state.append(("shape_a", a, "dimensionless", "4^a*Beta(a+1,a+1)=theta; 60 bisection steps"))
    csv(4, "traffic_arithmetic.csv", [{"key": k, "value": v, "unit": u, "formula_or_source": f, "note": "Calculated from preserved inputs; no new calibration."} for k, v, u, f in state])
    csv(4, "shape_bisection.csv", bisect)
    quad = pd.DataFrame(cfg["gauss_legendre_384"])
    u = quad.u.to_numpy(); gw = quad.weight.to_numpy()
    h = (4*u*(1-u))**a; dh = 4*a*(1-2*u)*(4*u*(1-u))**(a-1)
    arrival = 1+peak/P*dh; N = D*gw*arrival; w = peak*h; T = Tf+w; vr = L/T
    tq = vf*w/(vf-vq); tf = Tf-vq*w/(vf-vq)
    q = pd.DataFrame({"node_id": np.arange(1,len(u)+1), "u": u, "gauss_weight": gw, "h": h, "dh_du": dh, "entry_elapsed_h": u*P, "arrival_factor": arrival, "arrival_rate_veh_h_lane": mu*arrival, "vehicle_weight": N, "delay_h": w, "trip_time_h": T, "speed_mph": vr, "free_time_h": tf, "queue_time_h": tq, "free_distance_mi": vf*tf, "queue_distance_mi": vq*tq, "distance_residual_mi": vf*tf+vq*tq-L, "time_residual_h": tf+tq-T})
    q["cum_count_end"] = np.cumsum(N)
    q["cum_count_start"] = q.cum_count_end - N
    csv(4, "quadrature_traffic_arithmetic.csv", q)

    ages = pd.DataFrame(cfg["age_weights"])
    ages["normalized_weight"] = ages.raw_weight/ages.raw_weight.sum()
    csv(5, "normalized_age_weights.csv", ages)
    rawrates = pd.DataFrame(cfg["passenger_car_raw_rates"])
    rawrates = rawrates.merge(ages[["age", "normalized_weight"]], on="age", validate="many_to_one")
    wr = []
    for p in POLS:
        pname = "NOX" if p == "NOx" else p
        for r in rawrates.to_dict("records"):
            rate0 = r[f"meanBaseRate_{pname}_(g/hr)"]
            wr.append({"age": r["age"], "operating_mode": int(r["OpModeID"]), "pollutant": p, "normalized_weight": r["normalized_weight"], "raw_rate_g_veh_h": rate0, "weighted_rate_g_veh_h": rate0*r["normalized_weight"]})
    wr = csv(5, "age_rate_contributions.csv", wr)
    mode_rates = wr.groupby(["operating_mode", "pollutant"], as_index=False).weighted_rate_g_veh_h.sum().rename(columns={"weighted_rate_g_veh_h": "rate_g_veh_h"})
    csv(5, "age_weighted_mode_rates.csv", mode_rates)
    rate_map = mode_rates.set_index(["operating_mode", "pollutant"]).rate_g_veh_h.to_dict()
    bands = pd.DataFrame(compact["rate_table"])
    coeff = {r["pollutant"]: np.array([r[f"c{i}"] for i in range(4)]) for r in cfg["cubic_coefficients"]}
    bandrows = []
    for row in compact["rate_table"]:
        for p in POLS:
            bandrows.append({"speed_lower_mph": row["speed_lower_mph"], "speed_upper_mph": row["speed_upper_mph"], "lower_inclusive": row["lower_inclusive"], "upper_inclusive": row["upper_inclusive"], "operating_mode": row["source_operating_mode"], "pollutant": p, "rate_g_veh_h": rate_map[row["source_operating_mode"],p]})
            assert math.isclose(rate_map[row["source_operating_mode"],p],row[f"{p}_g_per_veh_h"],rel_tol=1e-12)
    csv(5, "positive_speed_rate_bands.csv", bandrows)
    csv(5, "cubic_coefficients.csv", pd.DataFrame(cfg["cubic_coefficients"])[["pollutant", "speed_min_mph", "speed_max_mph", "c0", "c1", "c2", "c3"]])
    csv(5, "vehicle_vsp_inputs.csv", [{"key": k, "value": cfg["vehicle"][k], "unit": unit, "formula_or_source": "calibration_inputs.json:vehicle", "note": "Supplied passenger-car parameters; acceleration=0 and grade=0."} for k,unit in [("rolling_term_a","kW s/m"),("rotating_term_b","kW s^2/m^2"),("drag_term_c","kW s^3/m^3"),("source_mass","tonne")]] + [{"key": "mph_to_mps", "value": .44704, "unit": "m/s per mph", "formula_or_source": "unit conversion", "note": "Exact conversion."}])
    def vsp(v):
        ms = np.asarray(v)*.44704; veh = cfg["vehicle"]
        return (veh["rolling_term_a"]*ms+veh["rotating_term_b"]*ms**2+veh["drag_term_c"]*ms**3)/veh["source_mass"]
    def mode(v):
        return np.array([int(bands.iloc[np.searchsorted(bands.speed_lower_mph.to_numpy(), speed, side="right")-1].source_operating_mode) for speed in np.atleast_1d(v)])
    def rate(v,p):
        return np.array([rate_map[m,p] for m in mode(v)])
    def cubic(v,p):
        return np.polynomial.polynomial.polyval(v, coeff[p])
    # VSP is exported before lookup decisions: the operating speed assumption
    # changes VSP; selecting an emission rate is a separate subsequent step.
    vsp_rows = []
    def add_vsp(method, state, speed, exposure, bin_id=None, node_id=None):
        ms=float(speed)*.44704; vehicle=cfg["vehicle"]
        rolling=vehicle["rolling_term_a"]*ms
        rotating=vehicle["rotating_term_b"]*ms*ms
        drag=vehicle["drag_term_c"]*ms**3
        vsp_rows.append({"vsp_record_id":len(vsp_rows)+1,"method":method,"operating_state":state,"bin_id":bin_id,"node_id":node_id,"speed_mph":speed,"speed_mps":ms,"rolling_power_kw":rolling,"rotating_power_kw":rotating,"drag_power_kw":drag,"total_power_kw":rolling+rotating+drag,"mass_tonne":vehicle["source_mass"],"vsp_kw_tonne":(rolling+rotating+drag)/vehicle["source_mass"],"vehicle_hours":exposure})
    for r in z.itertuples(): add_vsp("O","whole_link",r.speed_mph,r.vehicle_hours,bin_id=r.bin_id)
    add_vsp("S","whole_link_mean",vs,Ho)
    for j in range(len(q)):
        add_vsp("R","whole_link",vr[j],N[j]*T[j],node_id=j+1)
        for m in ("M","A"):
            add_vsp(m,"free",vf,N[j]*tf[j],node_id=j+1)
            add_vsp(m,"queue",vq,N[j]*tq[j],node_id=j+1)
    vsp_table=csv(5,"method_vsp_arithmetic.csv",vsp_rows)
    decisions=[]
    for r in vsp_table.itertuples():
        pairs=([(0,11),(3,12),(6,13),(9,14),(12,15)] if r.speed_mph<25 else [(0,21),(3,22),(6,23),(9,24),(12,25),(18,27),(24,28),(30,29)] if r.speed_mph<50 else [(6,33),(12,35),(18,37),(24,38),(30,39)])
        chosen=next((m for threshold,m in pairs if r.vsp_kw_tonne<threshold),16 if r.speed_mph<25 else 30 if r.speed_mph<50 else 40)
        assert chosen==mode(r.speed_mph)[0]
        decisions.append({"vsp_record_id":r.vsp_record_id,"method":r.method,"operating_state":r.operating_state,"speed_mph":r.speed_mph,"vsp_kw_tonne":r.vsp_kw_tonne,"speed_band":"(0,25)" if r.speed_mph<25 else "[25,50)" if r.speed_mph<50 else "[50,infinity)","operating_mode":chosen,"rate_use":"comparison only; A uses cubic" if r.method=="A" else "actual lookup input",**{f"lookup_{p}_g_veh_h":rate_map[chosen,p] for p in POLS}})
    csv(5,"method_lookup_decisions.csv",decisions)
    states = []
    for s,v in [("free_speed",vf),("queue_speed",vq),("observed_mean_speed",vs),("predicted_mean_speed",vp)]:
        for p in POLS:
            terms = coeff[p] * v**np.arange(4)
            states.append({"state":s, "speed_mph":v, "vsp_kw_tonne":float(vsp(v)), "operating_mode":mode(v)[0], "pollutant":p, "lookup_rate_g_veh_h":rate(v,p)[0], "cubic_constant_g_veh_h":terms[0], "cubic_linear_g_veh_h":terms[1], "cubic_quadratic_g_veh_h":terms[2], "cubic_cubic_g_veh_h":terms[3], "cubic_rate_g_veh_h":sum(terms)})
    csv(5, "state_rate_arithmetic.csv", states)

    emissions = {}; native = {m: [] for m in ("O","S","R","M","A")}; totals = []
    for p in POLS:
        ro = rate(z.speed_mph,p); rr = rate(vr,p)
        eo = z.vehicle_hours.to_numpy()*ro; es = Ho*rate(vs,p)[0]
        er = N*T*rr; em = N*(tf*rate(vf,p)[0]+tq*rate(vq,p)[0]); ea = N*(tf*cubic(vf,p)+tq*cubic(vq,p))
        emissions[p] = {"O":eo,"S":es,"R":er,"M":em,"A":ea}
        for i, r in z.iterrows():
            native["O"].append({"bin_id":r.bin_id, "clock_time":r.clock_time, "pollutant":p, "count_veh_5min":r.count_veh_5min, "speed_mph":r.speed_mph, "trip_time_h":r.trip_time_h, "vehicle_hours":r.vehicle_hours, "vsp_kw_tonne":float(vsp(r.speed_mph)), "operating_mode":mode(r.speed_mph)[0], "rate_g_veh_h":ro[i], "emission_g":eo[i]})
        native["S"].append({"pollutant":p,"vehicle_weight":D,"speed_mph":vs,"trip_time_h":Ho/D,"vehicle_hours":Ho,"vsp_kw_tonne":float(vsp(vs)),"operating_mode":mode(vs)[0],"rate_g_veh_h":rate(vs,p)[0],"emission_g":es})
        for j in range(len(q)):
            native["R"].append({"node_id":j+1,"pollutant":p,"vehicle_weight":N[j],"delay_h":w[j],"trip_time_h":T[j],"speed_mph":vr[j],"vehicle_hours":N[j]*T[j],"vsp_kw_tonne":float(vsp(vr[j])),"operating_mode":mode(vr[j])[0],"rate_g_veh_h":rr[j],"emission_g":er[j]})
            for m,fn in [("M",rate),("A",cubic)]:
                rf=float(np.asarray(fn(vf,p)).item()); rq=float(np.asarray(fn(vq,p)).item())
                native[m].append({"node_id":j+1,"pollutant":p,"vehicle_weight":N[j],"free_speed_mph":vf,"queue_speed_mph":vq,"delay_h":w[j],"free_time_h":tf[j],"queue_time_h":tq[j],"free_vehicle_hours":N[j]*tf[j],"queue_vehicle_hours":N[j]*tq[j],"free_rate_g_veh_h":rf,"queue_rate_g_veh_h":rq,"free_emission_g":N[j]*tf[j]*rf,"queue_emission_g":N[j]*tq[j]*rq,"emission_g":em[j] if m=="M" else ea[j]})
        e0=float(eo.sum())
        for m in ("O","S","R","M","A"):
            e=float(np.sum(emissions[p][m])); delta=e-e0
            totals.append({"method":m,"pollutant":p,"emission_g":e,"O_reference_g":e0,"signed_error_g":delta,"absolute_error_g":abs(delta),"signed_error_pct":100*delta/e0,"absolute_error_pct":100*abs(delta)/e0})
    for m, rows in native.items(): csv(6, f"{m}_calculation_rows.csv", rows)

    edges=np.r_[0,z.count_veh_5min.cumsum().to_numpy()]; nedges=np.r_[0,np.cumsum(N)]
    edges[-1]=D; nedges[-1]=D
    overlap=np.maximum(0,np.minimum(edges[1:,None],nedges[None,1:])-np.maximum(edges[:-1,None],nedges[None,:-1]))
    ij=np.argwhere(overlap>0)
    csv(7,"node_to_bin_allocation.csv",[{"bin_id":int(i+1),"node_id":int(j+1),"overlap_count":overlap[i,j],"node_fraction":overlap[i,j]/N[j]} for i,j in ij])
    common=[]; sharedH=overlap@T
    for p in POLS:
        for m in ("O","S","R","M","A"):
            if m=="O": H=z.vehicle_hours.to_numpy(); E=emissions[p][m]
            elif m=="S": H=z.count_veh_5min.to_numpy()*Ho/D; E=z.count_veh_5min.to_numpy()*emissions[p][m]/D
            else: H=sharedH; E=overlap@(emissions[p][m]/N)
            cumulative=np.cumsum(E)
            for i in range(len(z)):
                common.append({"bin_id":i+1,"clock_time":z.clock_time.iloc[i],"clock_h":z.clock_h.iloc[i],"method":m,"pollutant":p,"count_veh_5min":z.count_veh_5min.iloc[i],"vehicle_hours":H[i],"effective_speed_mph":z.count_veh_5min.iloc[i]*L/H[i],"effective_rate_g_veh_h":E[i]/H[i],"emission_g":E[i],"cumulative_emission_g":cumulative[i]})
    common=csv(7,"common_clock_calculations.csv",common)
    vsp_common=[]; vsp_metrics=[]
    vsp_o=vsp(z.speed_mph.to_numpy())
    for m in ("O","S","R","M","A"):
        if m=="O": hbin=z.vehicle_hours.to_numpy(); zbin=vsp_o
        elif m=="S": hbin=z.count_veh_5min.to_numpy()*Ho/D; zbin=np.full(len(z),float(vsp(vs)))
        elif m=="R": hbin=sharedH; zbin=(overlap@(T*vsp(vr)))/hbin
        else: hbin=sharedH; zbin=(overlap@(tf*vsp(vf)+tq*vsp(vq)))/hbin
        equivalent=z.count_veh_5min.to_numpy()*L/hbin
        for i in range(len(z)):
            vsp_common.append({"bin_id":i+1,"clock_time":z.clock_time.iloc[i],"clock_h":z.clock_h.iloc[i],"method":m,"vehicle_hours":hbin[i],"effective_speed_mph":equivalent[i],"exposure_weighted_vsp_kw_tonne":zbin[i],"vsp_at_effective_speed_kw_tonne":float(vsp(equivalent[i])),"difference_from_O_vsp_kw_tonne":zbin[i]-vsp_o[i]})
        nativevsp=vsp_table.loc[vsp_table.method.eq(m)]
        meanz=np.average(nativevsp.vsp_kw_tonne,weights=nativevsp.vehicle_hours)
        stdz=np.sqrt(np.average((nativevsp.vsp_kw_tonne-meanz)**2,weights=nativevsp.vehicle_hours))
        difference=zbin-vsp_o
        vsp_metrics.append({"method":m,"vehicle_hours":float(hbin.sum()),"mean_vsp_kw_tonne":meanz,"vsp_sd_kw_tonne":stdz,"vsp_mean_bias_vs_O_kw_tonne":np.average(difference,weights=z.vehicle_hours),"vsp_MAE_vs_O_kw_tonne":np.average(abs(difference),weights=z.vehicle_hours),"vsp_RMSE_vs_O_kw_tonne":np.sqrt(np.average(difference**2,weights=z.vehicle_hours))})
    vsp_common_table=csv(7,"common_clock_vsp.csv",vsp_common)
    assert np.allclose(vsp_table.vsp_kw_tonne,vsp(vsp_table.speed_mph),rtol=1e-12)
    for metric in vsp_metrics:
        rows=vsp_common_table.loc[vsp_common_table.method.eq(metric["method"])]
        assert math.isclose(np.average(rows.exposure_weighted_vsp_kw_tonne,weights=rows.vehicle_hours),metric["mean_vsp_kw_tonne"],rel_tol=1e-12)
    assert np.allclose(vsp_common_table.loc[vsp_common_table.method.eq("M"),"exposure_weighted_vsp_kw_tonne"],vsp_common_table.loc[vsp_common_table.method.eq("A"),"exposure_weighted_vsp_kw_tonne"],rtol=1e-12)
    totals=csv(8,"method_totals.csv",totals)
    decomposition=[]; symmetric=[]
    labels=["Observed mean-rate aggregation","Fitted mean delay and speed","Reconstructed trip-speed variation","Two operating-speed allocation","Cubic rate approximation"]
    for p in POLS:
        es=totals.loc[totals.pollutant.eq(p)].set_index("method").emission_g.to_dict()
        sp=Hp*rate(vp,p)[0]; vals=[es["O"],es["S"],sp,es["R"],es["M"],es["A"]]
        for k in range(5):
            delta=vals[k+1]-vals[k]
            decomposition.append({"pollutant":p,"stage":k+1,"component":labels[k],"from_g":vals[k],"to_g":vals[k+1],"delta_g":delta,"delta_pct_of_O":100*delta/es["O"]})
        rs=rate(vs,p)[0]; rp=rate(vp,p)[0]
        exposure=(Hp-Ho)*(rp+rs)/2; ratepart=(rp-rs)*(Hp+Ho)/2
        symmetric.append({"pollutant":p,"H_observed":Ho,"H_predicted":Hp,"rate_observed_mean_g_veh_h":rs,"rate_predicted_mean_g_veh_h":rp,"exposure_component_g":exposure,"rate_component_g":ratepart,"net_component_g":exposure+ratepart})
    decomposition=csv(8,"signed_error_components.csv",decomposition)
    csv(8,"fitted_mean_symmetric_split.csv",symmetric)
    published=pd.read_csv(REFERENCE/"emission_totals.csv")
    comparison=totals[["method","pollutant","emission_g"]].merge(published[["method","pollutant","emission_g"]].rename(columns={"emission_g":"published_emission_g"}),on=["method","pollutant"],validate="one_to_one")
    comparison["difference_g"]=comparison.emission_g-comparison.published_emission_g
    comparison["relative_difference"]=comparison.difference_g/comparison.published_emission_g
    csv(8,"published_total_reconciliation.csv",comparison)
    csv(8,"vsp_comparison.csv",vsp_metrics)

    refprofile=pd.read_csv(REFERENCE/"average_weekday_profile.csv")
    refq=pd.read_csv(REFERENCE/"reconstructed_integration.csv")
    refcommon=pd.read_csv(REFERENCE/"common_time_series.csv")
    refdc=pd.read_csv(REFERENCE/"error_decomposition.csv")
    assert (len(raw),len(days),len(retained),len(profile),len(z),len(q)) == (5999,21,16,288,57,384)
    assert np.allclose(profile.speed_mph,refprofile.speed_mph,rtol=1e-12)
    assert np.allclose(profile.count_veh_5min,refprofile.count_veh_5min,rtol=1e-12)
    assert np.allclose(q.vehicle_weight,refq.vehicle_weight,rtol=1e-12)
    assert np.allclose(q.trip_time_h,refq.trip_time_h,rtol=1e-12)
    assert np.allclose(comparison.emission_g,comparison.published_emission_g,rtol=1e-10,atol=1e-8)
    max_common_error=0.
    for p in POLS:
        for m in ("O","S","R","M","A"):
            rows=common.loc[common.pollutant.eq(p)&common.method.eq(m)]
            ref=refcommon[f"E_{m}_{p}_g"].to_numpy()
            assert np.allclose(rows.emission_g,ref,rtol=1e-10,atol=1e-8)
            max_common_error=max(max_common_error,float(np.max(abs(rows.emission_g.to_numpy()-ref))))
    merged=decomposition.merge(refdc,on=["pollutant","stage"],suffixes=("","_reference"))
    assert np.allclose(merged.delta_g,merged.delta_g_reference,rtol=1e-10,atol=1e-8)
    assert np.all(tf>=0) and np.all(tq>=0) and np.all(N>0)
    assert math.isclose(float(np.sum(N)),D,rel_tol=1e-12)
    assert math.isclose(float(np.sum(N*T)),Hp,rel_tol=1e-12)
    pd.DataFrame(dictionary).to_csv(out/"column_dictionary.csv",index=False,lineterminator="\n")
    pd.DataFrame(tables).to_csv(out/"table_inventory.csv",index=False,lineterminator="\n")
    audit={"passed":True,"raw_records":len(raw),"supplied_dates":len(days),"retained_dates":len(retained),"average_weekday_bins":len(profile),"selected_bins":len(z),"quadrature_nodes":len(q),"method_pollutant_totals":len(comparison),"common_clock_rows":len(common),"positive_node_bin_overlaps":len(ij),"all_20_totals_match_published":True,"max_total_absolute_difference_g":float(comparison.difference_g.abs().max()),"max_total_relative_difference":float(comparison.relative_difference.abs().max()),"max_common_clock_difference_g":max_common_error,"max_distance_identity_residual_mi":float(abs(q.distance_residual_mi).max()),"max_time_identity_residual_h":float(abs(q.time_residual_h).max()),"minimum_free_time_h":float(tf.min()),"minimum_arrival_factor":float(arrival.min()),"vehicle_count_difference":float(N.sum()-D),"vehicle_hours_difference":float(np.sum(N*T)-Hp),"source_sha256":{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in [INPUT/"raw_source.json",INPUT/"calibration_inputs.json",INPUT/"calculation_inputs.json",REFERENCE/"emission_totals.csv",REFERENCE/"common_time_series.csv"]}}
    from plot_steps import make_figures
    make_figures(out)
    audit["vsp_operating_rows"]=len(vsp_table)
    audit["vsp_lookup_decisions_match_compact_mapping"]=True
    audit["vsp_native_and_common_clock_exposure_means_match"]=True
    audit["M_A_vsp_identical"]=True
    audit["common_clock_vsp_rows"]=len(vsp_common)
    audit["diagnostic_figures"]={"count":8,"formats":["png","svg"],"object_based":True}
    (out/"verification.json").write_text(json.dumps(audit,indent=2)+"\n")
    print(json.dumps(audit,indent=2))


if __name__ == "__main__":
    build(output_path())
