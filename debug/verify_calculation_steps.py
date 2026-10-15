"""Read-only numerical checks of the published experiment calculation ledgers.

Requires NumPy and pandas. Does not rerun calibration, generate figures, update
reference values, or write any files. Run from any working directory.
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "debug/full_experiment/steps"
SENSOR = ROOT / "debug/sensor78/step_by_step"
POLS = ("CO2", "NOx", "CO", "HC")
METHODS = ("O", "S", "R", "M", "A")
CHECKS = []


def require(condition, message):
    if not bool(condition):
        raise AssertionError(message)
    CHECKS.append(message)


def close(name, actual, expected, *, rtol=1e-9, atol=1e-8):
    """Default accommodates CSV precision and 384-node quadrature residuals.

    Tighten explicitly for categorical mappings and VSP. Default absolute units
    are those of the compared column; the largest emission-unit allowance is
    1e-8 grams plus 1e-9 times the expected magnitude.
    """
    np.testing.assert_allclose(np.asarray(actual, float), np.asarray(expected, float),
                               rtol=rtol, atol=atol, equal_nan=True, err_msg=name)
    CHECKS.append(name)


def read_step(base, number, filename, rows=None, keys=None):
    matches = list(base.glob(f"{number:02d}_*"))
    require(len(matches) == 1, f"Unique step {number} under {base.name}")
    frame = pd.read_csv(matches[0] / filename)
    if rows is not None:
        require(len(frame) == rows, f"{filename}: {rows} rows")
    if keys:
        require(not frame.duplicated(keys).any(), f"{filename}: unique {keys}")
    return frame


def vsp(speed, vehicle):
    s = np.asarray(speed, float) * 0.44704
    return (float(vehicle["rolling_term_a"]) * s
            + float(vehicle["rotating_term_b"]) * s**2
            + float(vehicle["drag_term_c"]) * s**3) / float(vehicle["source_mass"])


def modes(speed, power):
    """Independent speed/VSP classification using the stated strict cutoffs."""
    speed, power = np.asarray(speed, float), np.asarray(power, float)
    require(np.isfinite(speed).all() and np.isfinite(power).all() and (speed > 0).all(),
            "Mode-classification inputs are finite with positive speed")
    result = []
    for v, z in zip(speed, power):
        if v < 25:
            cutoffs = [(0, 11), (3, 12), (6, 13), (9, 14), (12, 15)]
            last = 16
        elif v < 50:
            cutoffs = [(0, 21), (3, 22), (6, 23), (9, 24), (12, 25),
                       (18, 27), (24, 28), (30, 29)]
            last = 30
        else:
            cutoffs = [(6, 33), (12, 35), (18, 37), (24, 38), (30, 39)]
            last = 40
        result.append(next((m for boundary, m in cutoffs if z < boundary), last))
    return np.asarray(result, int)


def wasserstein(values_a, weights_a, values_b, weights_b):
    """Integrate the two normalized weighted empirical CDFs independently."""
    a, wa = np.asarray(values_a, float), np.asarray(weights_a, float)
    b, wb = np.asarray(values_b, float), np.asarray(weights_b, float)
    ia, ib = np.argsort(a), np.argsort(b)
    a, wa, b, wb = a[ia], wa[ia], b[ib], wb[ib]
    grid = np.unique(np.r_[a, b])
    ca = np.r_[0., np.cumsum(wa) / wa.sum()]
    cb = np.r_[0., np.cumsum(wb) / wb.sum()]
    fa = ca[np.searchsorted(a, grid[:-1], side="right")]
    fb = cb[np.searchsorted(b, grid[:-1], side="right")]
    return np.sum(np.abs(fa-fb) * np.diff(grid))


def verify_full():
    ep = pd.read_csv(ROOT / "data/frozen/calibration/average_weekday/episode_results_v2.csv").set_index("episode_id")
    retained = ep.loc[ep.matched_ladder_pass]
    funnel = [len(ep), int((~ep.qc_hard_fail).sum()),
              int((~ep.qc_hard_fail & ~ep.qc_outlier_fail).sum()),
              int((ep.calibration_eligible & ep.fd.notna()).sum()), len(retained)]
    require(funnel == [325, 294, 293, 286, 137], "Unchanged 325→294→293→286→137 sample funnel")
    require((retained.paper_corridor == "AZ_I10").sum() == 20, "20 retained Arizona episodes")
    require(retained[["sensor_uid", "date"]].drop_duplicates().shape[0] == 118,
            "118 retained detector/profile combinations")
    admission = read_step(FULL, 5, "physical_admission_325.csv", 325, ["episode_id"]).set_index("episode_id").loc[ep.index]
    require(np.array_equal(admission.matched_ladder_pass, ep.matched_ladder_pass), "Admission mask equals frozen mask")
    p = np.maximum(ep.fd * ep.x_h**ep.n, ep.x_h)
    tf = ep.L_mi / ep.vf_mph
    mu = ep.D_veh / p
    omega = ep.C_vphpl / (ep.kj - ep.C_vphpl/ep.vf_mph)
    vq = mu / (ep.kj - mu/omega)
    close("Fitted duration from parameters", admission.P_recomputed_h, p)
    close("Fitted peak delay from parameters", admission.peak_recomputed_h, tf*ep.fp*p**ep.s)
    close("Queue FD closure", admission.vq_recomputed_mph, vq)

    obs = read_step(FULL, 7, "observed_speed_vsp.csv", 4800, ["episode_id", "bin_index"])
    one = read_step(FULL, 7, "single_speed_vsp.csv", 137, ["episode_id"])
    node = read_step(FULL, 8, "reconstructed_speed_vsp.csv.gz", 52608, ["episode_id", "node_index"])
    states = read_step(FULL, 8, "two_speed_state_vsp.csv", 274, ["episode_id", "state"])
    terms = read_step(FULL, 8, "node_emission_terms.csv.gz", 210432, ["episode_id", "node_index", "pollutant"])
    total = read_step(FULL, 9, "episode_pollutant_calculation_steps.csv", 548, ["episode_id", "pollutant"])
    frozen_check = read_step(FULL, 9, "archived_result_reconciliation.csv", 2740, ["episode_id", "method", "pollutant"])
    metric = read_step(FULL, 9, "pooled_metric_calculation_steps.csv", 60, ["sample", "method", "pollutant"])
    moments = read_step(FULL, 8, "vsp_agreement_by_episode_method.csv", 685, ["episode_id", "method"])
    exposure = read_step(FULL, 8, "operating_mode_exposure_by_episode.csv", 15755, ["episode_id", "method", "OpModeID"])
    hist = read_step(FULL, 8, "pooled_vsp_exposure_distribution.csv", 640, ["method", "vsp_lower_kw_t"])
    total_index = total.set_index(["episode_id", "pollutant"])
    require(set(obs.episode_id) == set(retained.index) == set(node.episode_id), "All native calculations use the same retained episodes")
    close("Observed count from five-minute flow", obs.count_veh, obs.flow_vphpl/12)
    close("Observed whole-link travel time", obs.trip_time_h, ep.L_mi.reindex(obs.episode_id).to_numpy()/obs.speed_mph)
    close("Observed vehicle-hour product", obs.vehicle_hours, obs.count_veh*obs.trip_time_h)
    observed_agg = obs.groupby("episode_id").agg(D=("count_veh", "sum"), H=("vehicle_hours", "sum"))
    single = one.set_index("episode_id").loc[observed_agg.index]
    close("Observed demand equals frozen demand", observed_agg.D, ep.D_veh.reindex(observed_agg.index))
    close("Single-speed harmonic mean", single.speed_mph, observed_agg.D*single.L_mi/observed_agg.H)
    close("Single-speed retains observed vehicle-hours", single.sum_vehicle_hours, observed_agg.H)

    veh = pd.read_csv(ROOT / "data/frozen/calibration/emission_input/input_vehicle_type.csv")
    vehicle = veh.loc[veh.vehicle_type.eq(1)].iloc[0]
    for name, frame in [("O", obs), ("S", one), ("R", node), ("M/A", states)]:
        close(f"{name}: VSP from speed", frame.vsp_kw_t, vsp(frame.speed_mph, vehicle), rtol=1e-12, atol=1e-12)
        close(f"{name}: separate VSP terms", frame.vsp_kw_t,
              frame.rolling_vsp_kw_t+frame.rotating_vsp_kw_t+frame.drag_vsp_kw_t, rtol=1e-12, atol=1e-12)
        require(frame.vsp_kw_t.between(0, 32).all(), f"{name}: histogram range retains all VSP exposure")
    age = read_step(FULL, 6, "vehicle_age_weights.csv", 31, ["age"])
    close("Age weights equal supplied inputs", age.supplied_weight,
          [vehicle["percentage_of_age_"+str(a)] for a in age.age], rtol=1e-12, atol=1e-12)
    close("Age normalization", age.normalized_weight, age.supplied_weight/age.supplied_weight.sum(), rtol=1e-12, atol=1e-12)
    age_terms = read_step(FULL, 6, "age_rate_contributions.csv", 2852, ["age", "OpModeID", "pollutant"])
    close("Age-rate products", age_terms.weighted_contribution_g_veh_h,
          age_terms.normalized_weight*age_terms.input_rate_g_veh_h, rtol=1e-12, atol=1e-12)
    rates = read_step(FULL, 6, "age_weighted_operating_mode_rates.csv", 23, ["OpModeID"]).set_index("OpModeID")
    for pollutant, frame in age_terms.groupby("pollutant"):
        summed = frame.groupby("OpModeID").weighted_contribution_g_veh_h.sum()
        close(f"{pollutant}: age-mixture sums", summed, rates.loc[summed.index, "ER_"+("NOX" if pollutant == "NOx" else pollutant)], rtol=1e-12, atol=1e-12)
    for step, name, count, keys in [
        (7, "observed_rate_lookup.csv", 19200, ["episode_id", "bin_index", "pollutant"]),
        (7, "single_speed_rate_lookup.csv", 548, ["episode_id", "pollutant"]),
        (8, "reconstructed_rate_lookup.csv.gz", 210432, ["episode_id", "node_index", "pollutant"]),
        (8, "two_speed_lookup_and_cubic_rates.csv", 1096, ["episode_id", "state", "pollutant"])]:
        frame = read_step(FULL, step, name, count, keys)
        require(np.array_equal(frame.OpModeID, modes(frame.speed_mph, frame.vsp_kw_t)), name+": independent mode selection")
        for pollutant, selected in frame.groupby("pollutant"):
            close(name+": "+pollutant+" rate lookup", selected.lookup_rate_g_veh_h,
                  rates.reindex(selected.OpModeID)["ER_"+("NOX" if pollutant == "NOx" else pollutant)], rtol=1e-12, atol=1e-12)
        if name == "two_speed_lookup_and_cubic_rates.csv":
            state_rates = frame
    coeff = pd.read_csv(ROOT / "data/frozen/calibration/average_weekday/cubic_rate_coefficients.csv").set_index("pollutant")
    for pollutant, frame in state_rates.groupby("pollutant"):
        polynomial = sum(coeff.loc[pollutant, "c"+str(k)]*frame.speed_mph**k for k in range(4))
        close(pollutant+": cubic state rate", frame.cubic_rate_g_veh_h, polynomial)
    rn = retained.reindex(node.episode_id)
    nf = rn.L_mi.to_numpy()/rn.vf_mph.to_numpy()
    close("Node vehicle weights", node.vehicle_weight, rn.D_veh.to_numpy()*node.quadrature_weight*node.arrival_factor)
    require((node.vehicle_weight > 0).all() and (node.free_time_h >= 0).all() and (node.queue_time_h >= 0).all(), "Positive node counts and nonnegative time allocations")
    close("Node delay", node.delay_h, rn.wt2_hat_h.to_numpy()*node.shape_h)
    close("Node trip time", node.trip_time_h, nf+node.delay_h)
    close("Node equivalent speed", node.speed_mph, rn.L_mi.to_numpy()/node.trip_time_h)
    close("Node queue time", node.queue_time_h, rn.vf_mph.to_numpy()*node.delay_h/(rn.vf_mph.to_numpy()-rn.vq_hat_mph.to_numpy()))
    close("Node free time", node.free_time_h, nf-rn.vq_hat_mph.to_numpy()*node.delay_h/(rn.vf_mph.to_numpy()-rn.vq_hat_mph.to_numpy()))
    close("Node distance identity", rn.vf_mph.to_numpy()*node.free_time_h+rn.vq_hat_mph.to_numpy()*node.queue_time_h, rn.L_mi)
    close("Node vehicle-hours", node.vehicle_hours, node.vehicle_weight*node.trip_time_h)
    node_counts = node.groupby("episode_id").vehicle_weight.sum()
    close("Node demand conservation", node_counts, ep.D_veh.reindex(node_counts.index))
    close("Mean state vehicle-hours", states.vehicle_hours, states.mean_time_h*ep.D_veh.reindex(states.episode_id).to_numpy())
    close("R node emission product", terms.R_g, terms.vehicle_weight*terms.R_trip_time_h*terms.R_lookup_rate_g_veh_h)
    term_keys = pd.MultiIndex.from_frame(terms[["episode_id", "pollutant"]])
    for state in ("free", "queue"):
        selected_rates = state_rates.loc[state_rates.state.eq(state)].set_index(["episode_id", "pollutant"]).reindex(term_keys)
        for method, rate_column in [("M", "lookup_rate_g_veh_h"), ("A", "cubic_rate_g_veh_h")]:
            close(method+": "+state+" node emission products", terms[method+"_"+state+"_g"],
                  terms.vehicle_weight*terms[state+"_time_h"]*selected_rates[rate_column].to_numpy())
    max_node_relative = {}
    for method in ("R", "M", "A"):
        row_total = terms.R_g if method == "R" else terms[method+"_free_g"]+terms[method+"_queue_g"]
        summed = terms.assign(emission=row_total).groupby(["episode_id", "pollutant"]).emission.sum()
        target = total_index.loc[summed.index, method+"_g"]
        close(method+": node sums versus episode totals (quadrature tolerance)", summed, target)
        max_node_relative[method] = float(((summed-target)/target).abs().max())
    for method, name, count, keys in [("O", "observed_emission_terms.csv", 19200, ["episode_id", "bin_index", "pollutant"]),
                                     ("S", "single_speed_emission_terms.csv", 548, ["episode_id", "pollutant"])]:
        frame = read_step(FULL, 7, name, count, keys)
        close(method+": emission products", frame.emission_g, frame.vehicle_hours*frame.rate_g_veh_h)
        summed = frame.groupby(["episode_id", "pollutant"]).emission_g.sum()
        close(method+": episode sums", summed, total_index.loc[summed.index, method+"_g"])
    for method in METHODS:
        for pollutant in POLS:
            selected = total.loc[total.pollutant.eq(pollutant)].set_index("episode_id")
            close(method+" "+pollutant+": frozen totals", selected[method+"_g"], ep.reindex(selected.index)[method+"_"+pollutant])
    for pollutant, selected in total.groupby("pollutant"):
        speed = selected.D_veh*ep.L_mi.reindex(selected.episode_id).to_numpy()/selected.H_predicted_veh_h
        selected_modes = modes(speed, vsp(speed, vehicle))
        selected_rates = rates.reindex(selected_modes)["ER_"+("NOX" if pollutant == "NOx" else pollutant)].to_numpy()
        close(pollutant+": S_pred intermediate calculation", selected.S_pred_g, selected.H_predicted_veh_h*selected_rates)
    close("Reconciliation residual arithmetic", frozen_check.difference_g, frozen_check.recomputed_g-frozen_check.archived_g)
    close("Reconciled totals", frozen_check.recomputed_g, frozen_check.archived_g)
    for row in metric.itertuples():
        selected = total.loc[total.pollutant.eq(row.pollutant)]
        if row.sample == "Arizona I-10": selected = selected.loc[selected.paper_corridor.eq("AZ_I10")]
        elif row.sample == "California PeMS": selected = selected.loc[selected.paper_corridor.ne("AZ_I10")]
        else: require(row.sample == "All 137", "Known metric population")
        observed = selected.O_g.to_numpy(); predicted = selected[row.method+"_g"].to_numpy(); error = predicted-observed
        sse = np.sum(error**2); sst = np.sum((observed-observed.mean())**2)
        close(f"Metric {row.sample}/{row.pollutant}/{row.method}",
              [row.N, row.sum_reference_g, row.sum_method_g, row.sum_abs_error_g, row.sum_signed_error_g,
               row.sum_squared_error_g2, row.reference_sum_squared_deviation_g2, row.WAPE_pct, row.bias_pct, row.RMSE_g, row.R2],
              [len(selected), observed.sum(), predicted.sum(), abs(error).sum(), error.sum(), sse, sst,
               100*abs(error).sum()/abs(observed).sum(), 100*error.sum()/observed.sum(), np.sqrt(sse/len(selected)), 1-sse/sst])
    # Compare VSP distributions using time exposure, without substituting the
    # VSP at an equivalent speed for operating-state VSP.
    distributions = {"O": obs, "S": one.rename(columns={"sum_vehicle_hours": "vehicle_hours"}), "R": node, "M": states, "A": states}
    for method, frame in distributions.items():
        aggregate = frame.assign(zH=frame.vsp_kw_t*frame.vehicle_hours).groupby("episode_id").agg(zH=("zH", "sum"), H=("vehicle_hours", "sum"))
        reported = moments.loc[moments.method.eq(method)].set_index("episode_id").loc[aggregate.index]
        close(method+": VSP exposure means", reported.mean_vsp_kw_t, aggregate.zH/aggregate.H, rtol=1e-12, atol=1e-12)
        close(method+": histogram exposure conservation", hist.loc[hist.method.eq(method), "vehicle_hours"].sum(), frame.vehicle_hours.sum())
    close("M/A VSP equality", moments.loc[moments.method.eq("M"), "mean_vsp_kw_t"], moments.loc[moments.method.eq("A"), "mean_vsp_kw_t"], rtol=0, atol=0)
    close("Operating-mode shares sum to one", exposure.groupby(["episode_id", "method"]).share.sum(), 1, rtol=1e-12, atol=1e-12)
    for eid, observed_rows in obs.groupby("episode_id"):
        reference_mode = exposure.loc[exposure.episode_id.eq(eid) & exposure.method.eq("O")].set_index("OpModeID").share
        for method, frame in distributions.items():
            selected = frame.loc[frame.episode_id.eq(eid)]
            row = moments.loc[moments.episode_id.eq(eid) & moments.method.eq(method)].iloc[0]
            distance = wasserstein(observed_rows.vsp_kw_t, observed_rows.vehicle_hours, selected.vsp_kw_t, selected.vehicle_hours)
            close("Independent VSP CDF distance", row.wasserstein_vsp_distance_kw_t, distance, rtol=1e-11, atol=1e-11)
            shares = exposure.loc[exposure.episode_id.eq(eid) & exposure.method.eq(method)].set_index("OpModeID").share
            close("Operating-mode total variation", row.operating_mode_total_variation, .5*abs(shares-reference_mode).sum(), rtol=1e-12, atol=1e-12)
    return {"sample_funnel": funnel, "reconciled_totals": len(frozen_check), "pooled_metric_rows": len(metric),
            "VSP_distribution_comparisons": len(moments), "maximum_relative_node_vs_analytic_difference": max_node_relative}


def verify_sensor():
    cfg = json.loads((ROOT / "data/inputs/detector78/calibration_inputs.json").read_text())
    raw = read_step(SENSOR, 1, "raw_record_decisions.csv", 5999, ["raw_row_id"])
    days = read_step(SENSOR, 1, "day_decisions.csv", 21, ["date"])
    require(days.retained_day.sum() == 16 and raw.retained_day.sum() == 4608, "Detector 78: 16 complete days and 4608 contributing records")
    profile = read_step(SENSOR, 2, "average_weekday_arithmetic.csv", 288, ["clock_time"])
    retained = raw.loc[raw.retained_day]
    aggregate = retained.groupby("clock_time").agg(count=("volume_veh_5min", "sum"), inverse=("count_over_speed", "sum"))
    close("Detector 78: daily mean counts", profile.count_veh_5min, aggregate.reindex(profile.clock_time)["count"].to_numpy()/16)
    close("Detector 78: harmonic mean speeds", profile.speed_mph, (aggregate["count"]/aggregate.inverse).reindex(profile.clock_time))
    z = read_step(SENSOR, 3, "selected_window_arithmetic.csv", 57, ["bin_id"])
    q = read_step(SENSOR, 4, "quadrature_traffic_arithmetic.csv", 384, ["node_id"])
    power = read_step(SENSOR, 5, "method_vsp_arithmetic.csv", 1978, ["vsp_record_id"])
    decisions = read_step(SENSOR, 5, "method_lookup_decisions.csv", 1978, ["vsp_record_id"])
    close("Detector 78: independent VSP", power.vsp_kw_tonne, vsp(power.speed_mph, cfg["vehicle"]), rtol=1e-12, atol=1e-12)
    close("Detector 78: separate power terms", power.vsp_kw_tonne,
          (power.rolling_power_kw+power.rotating_power_kw+power.drag_power_kw)/power.mass_tonne, rtol=1e-12, atol=1e-12)
    require(np.array_equal(decisions.operating_mode, modes(decisions.speed_mph, decisions.vsp_kw_tonne)), "Detector 78: mode selection")
    aligned = decisions.set_index("vsp_record_id").loc[power.vsp_record_id]
    close("Detector 78: VSP/lookup separation join", aligned.vsp_kw_tonne, power.vsp_kw_tonne, rtol=0, atol=0)
    require(aligned.method.to_list() == power.method.to_list(), "Detector 78: VSP/lookup method keys")
    rates = read_step(SENSOR, 5, "age_weighted_mode_rates.csv", 92, ["operating_mode", "pollutant"]).set_index(["operating_mode", "pollutant"])
    for pollutant in POLS:
        expected = [rates.loc[(m, pollutant), "rate_g_veh_h"] for m in decisions.operating_mode]
        close("Detector 78: "+pollutant+" mode lookup", decisions["lookup_"+pollutant+"_g_veh_h"], expected, rtol=1e-12, atol=1e-12)
    total = read_step(SENSOR, 8, "method_totals.csv", 20, ["method", "pollutant"]).set_index(["method", "pollutant"])
    reference = pd.read_csv(ROOT / "debug/sensor78/results/emission_totals.csv").set_index(["method", "pollutant"])
    close("Detector 78: all 20 published totals", total.emission_g, reference.loc[total.index].emission_g)
    for method, count in [("O", 228), ("S", 4), ("R", 1536), ("M", 1536), ("A", 1536)]:
        frame = read_step(SENSOR, 6, method+"_calculation_rows.csv", count)
        if method in ("O", "S", "R"):
            close("Detector 78 "+method+": emission multiplication", frame.emission_g, frame.vehicle_hours*frame.rate_g_veh_h)
        else:
            close("Detector 78 "+method+": free emission", frame.free_emission_g, frame.free_vehicle_hours*frame.free_rate_g_veh_h)
            close("Detector 78 "+method+": queue emission", frame.queue_emission_g, frame.queue_vehicle_hours*frame.queue_rate_g_veh_h)
            close("Detector 78 "+method+": state sum", frame.emission_g, frame.free_emission_g+frame.queue_emission_g)
        summed = frame.groupby("pollutant").emission_g.sum()
        close("Detector 78 "+method+": method sum", summed, total.loc[method].loc[summed.index].emission_g)
    common = read_step(SENSOR, 7, "common_clock_calculations.csv", 1140, ["bin_id", "method", "pollutant"])
    cpower = read_step(SENSOR, 7, "common_clock_vsp.csv", 285, ["bin_id", "method"])
    close("Detector 78: common-bin effective-rate product", common.emission_g, common.vehicle_hours*common.effective_rate_g_veh_h)
    summed = common.groupby(["method", "pollutant"]).emission_g.sum()
    close("Detector 78: common-clock sums", summed, total.loc[summed.index].emission_g)
    close("Detector 78: M/A common-clock VSP equality", cpower.loc[cpower.method.eq("M"), "exposure_weighted_vsp_kw_tonne"], cpower.loc[cpower.method.eq("A"), "exposure_weighted_vsp_kw_tonne"], rtol=0, atol=0)
    overlap = read_step(SENSOR, 7, "node_to_bin_allocation.csv", 440, ["bin_id", "node_id"])
    allocated = overlap.groupby("bin_id").overlap_count.sum()
    close("Detector 78: allocated bin counts", allocated, z.set_index("bin_id").loc[allocated.index].count_veh_5min)
    close("Detector 78: node-fraction allocation", overlap.node_fraction, overlap.overlap_count/q.set_index("node_id").loc[overlap.node_id].vehicle_weight.to_numpy())
    return {"retained_days": 16, "selected_bins": len(z), "VSP_rows": len(power), "reconciled_totals": len(total)}


def main():
    result = {"full_experiment": verify_full(), "sensor78": verify_sensor()}
    print(json.dumps({"passed": True, "checks": len(CHECKS), "read_only": True, **result}, indent=2))


if __name__ == "__main__":
    main()
