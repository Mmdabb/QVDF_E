"""Independently verify the 137-episode dashboard metrics without writing files.

Requires NumPy and pandas only. By default, verify the published step-11 folder;
use --directory debug/output/episode_time_series to check a generated candidate.
No generator/helper functions are imported. Calibration targets come from the
frozen episode table; profile errors are recalculated from each case's CSVs.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STEPS = ROOT / "debug/full_experiment/steps"
DEFAULT = STEPS / "11_episode_time_series"
METHODS = ("O", "S", "R", "M", "A")
POLLUTANTS = ("CO2", "NOx", "CO", "HC")
KEYS = ["case_id", "episode_id", "group", "pollutant", "quantity", "method"]
CHECKS: list[str] = []


def require(condition, message):
    if not bool(condition):
        raise AssertionError(message)
    CHECKS.append(message)


def close(message, actual, expected, *, rtol=2e-11, atol=2e-9):
    """Tolerances cover CSV roundoff; emission totals allow quadrature separately."""
    np.testing.assert_allclose(np.asarray(actual, float), np.asarray(expected, float),
                               rtol=rtol, atol=atol, equal_nan=True, err_msg=message)
    CHECKS.append(message)


def frames(message, actual, expected, keys):
    a = actual.sort_values(keys).reset_index(drop=True)
    b = expected.sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False, rtol=2e-11, atol=2e-9,
                                  obj=message)
    CHECKS.append(message)


def power(speed, vehicle):
    s = np.asarray(speed, float) * vehicle["mph_to_mps"]
    return (vehicle["rolling_term_a"]*s + vehicle["rotating_term_b"]*s**2
            + vehicle["drag_term_c"]*s**3) / vehicle["source_mass"]


def statistics(actual, model, scalar):
    """Independent definitions, including signed-delay and scalar conventions."""
    actual, model = np.asarray(actual, float), np.asarray(model, float)
    require(actual.shape == model.shape and actual.size > 0, "Paired metric arrays")
    require(np.isfinite(actual).all() and np.isfinite(model).all(), "Finite metric arrays")
    denominator = np.sum(np.abs(actual))
    absolute_error = np.abs(model - actual)
    percent = 100*np.sum(absolute_error)/denominator if denominator else np.nan
    return {
        "n_pairs": actual.size,
        "reference_value": actual[0] if scalar else np.nan,
        "model_value": model[0] if scalar else np.nan,
        "reference_mean": np.mean(actual), "model_mean": np.mean(model),
        "reference_sum": np.sum(actual), "model_sum": np.sum(model),
        "denominator_abs_sum": denominator,
        "wape_pct": np.nan if scalar else percent,
        "ape_pct": percent if scalar else np.nan,
        "bias_pct": 100*np.sum(model-actual)/denominator if denominator else np.nan,
        "mae": np.mean(absolute_error), "rmse": np.sqrt(np.mean((model-actual)**2)),
    }


def verify(directory):
    catalog = pd.read_csv(directory / "episode_index.csv")
    all_metrics = pd.read_csv(directory / "all_error_metrics.csv").fillna({"pollutant": ""})
    frozen = pd.read_csv(ROOT / "data/frozen/calibration/average_weekday/episode_results_v2.csv")
    frozen = frozen.loc[frozen.matched_ladder_pass].sort_values("episode_id").set_index("episode_id")
    observed = pd.read_csv(STEPS / "07_observed_and_single_speed/observed_speed_vsp.csv")
    nodes = pd.read_csv(STEPS / "08_reconstruction_and_two_speed/reconstructed_speed_vsp.csv.gz")
    pars = pd.read_csv(STEPS / "06_rate_construction/vsp_input_parameters.csv")
    vehicle = dict(zip(pars.quantity, pars.value))
    obs_groups = {k: v.sort_values("bin_index") for k, v in observed.groupby("episode_id")}
    node_groups = {k: v.sort_values("node_index") for k, v in nodes.groupby("episode_id")}
    require(len(catalog) == len(frozen) == 137, "Exactly 137 retained episodes")
    require(list(catalog.episode_id) == list(frozen.index), "Index order and cohort match frozen targets")
    require(catalog.case_id.tolist() == [f"ep{i:03d}" for i in range(1, 138)], "Stable case identifiers")
    require(len(all_metrics) == 12330 and not all_metrics.duplicated(KEYS).any(), "12,330 unique metrics")
    collected_metrics, collected_traffic, collected_emissions = [], [], []
    expected_records = []
    negative_delays = 0
    distinct_peak_targets = 0

    for meta in catalog.to_dict("records"):
        case, eid = meta["case_id"], meta["episode_id"]
        target = frozen.loc[eid]
        sensor = re.sub(r"[^A-Za-z0-9_-]", "_", str(target.sensor_uid).split("::")[-1])
        expected_folder = f"episodes/{case}_{target.corridor}_{sensor}_{str(target.date).replace('-', '')}"
        require(meta["folder"] == expected_folder, case + " folder mapping")
        folder = directory / meta["folder"]
        traffic = pd.read_csv(folder / "traffic_timeseries.csv")
        emission = pd.read_csv(folder / "emissions_timeseries.csv")
        metrics = pd.read_csv(folder / "error_metrics.csv").fillna({"pollutant": ""})
        collected_traffic.append(traffic); collected_emissions.append(emission); collected_metrics.append(metrics)
        require(len(metrics) == 90 and not metrics.duplicated(KEYS).any(), case + " 90 unique metrics")
        require(traffic.case_id.eq(case).all() and traffic.episode_id.eq(eid).all(), case + " traffic identity")
        require(emission.case_id.eq(case).all() and emission.episode_id.eq(eid).all(), case + " emission identity")
        require(set(traffic.method) == set(METHODS) and set(emission.method) == set(METHODS), case + " five methods")
        ts = {m: traffic.loc[traffic.method.eq(m)].sort_values("bin_index") for m in METHODS}
        base, obs, nd = ts["O"], obs_groups[eid], node_groups[eid]
        n, L, vf, Tf = base.count_veh_per_lane.to_numpy(), target.L_mi, target.vf_mph, target.Tf_h
        D, bins = n.sum(), len(base)
        require(len(traffic) == bins*5 and len(emission) == bins*20, case + " complete time-series rows")
        require(not traffic.duplicated(["method", "bin_index"]).any(), case + " unique traffic bins")
        require(not emission.duplicated(["method", "pollutant", "bin_index"]).any(), case + " unique emission bins")
        require((n > 0).all(), case + " positive count basis")
        close(case + " frozen episode volume", D, target.D_veh)
        close(case + " observed duration from bins", bins/12, target.P_h)
        close(case + " observed duration from boundaries", (pd.Timestamp(target.t3)-pd.Timestamp(target.t0)).total_seconds()/3600, target.P_h)
        close(case + " free-flow time", Tf, L/vf)
        close(case + " frozen observed counts", n, obs.count_veh)
        close(case + " frozen observed speed", base.equivalent_speed_mph, obs.speed_mph)
        close(case + " frozen observed VSP", base.exposure_weighted_vsp_kw_t, obs.vsp_kw_t)
        close(case + " frozen minimum-speed target", base.equivalent_speed_mph.min(), target.vt2_obs_mph)
        close(case + " predicted minimum-speed formula", L/(Tf+target.wt2_hat_h), target.vt2_hat_mph)
        close(case + " predicted duration formula", max(target.fd*target.x_h**target.n, target.x_h), target.P_hat_h)
        negative_delays += int(base.mean_delay_h.lt(0).sum())
        distinct_peak_targets += int(abs(ts["R"].equivalent_speed_mph.min()-target.vt2_hat_mph) > 1e-7)

        # Reconstruct the common-count allocation independently from the source
        # nodes; the dashboard never replaces its calibrated P or minimum speed
        # with the duration/minimum of these displayed, count-aligned bins.
        N = nd.vehicle_weight.to_numpy()
        require((N > 0).all(), case + " positive model-node counts")
        b = np.r_[0., np.cumsum(n)]; q = np.r_[0., np.cumsum(N)]; b[-1] = q[-1] = D
        overlap = np.maximum(0, np.minimum(b[1:, None], q[None, 1:])
                             - np.maximum(b[:-1, None], q[None, :-1]))
        close(case + " overlap preserves observed counts", overlap.sum(axis=1), n)
        close(case + " overlap preserves model-node counts", overlap.sum(axis=0), N)
        Hfit = overlap @ nd.trip_time_h.to_numpy()
        free = overlap @ nd.free_time_h.to_numpy()/n
        queue = overlap @ nd.queue_time_h.to_numpy()/n
        trip_fit = Hfit/n
        vr_vsp = overlap @ (nd.trip_time_h*nd.vsp_kw_t).to_numpy()/Hfit
        vma_vsp = (free*power(vf, vehicle)+queue*power(target.vq_hat_mph, vehicle))/trip_fit
        averages = {}
        for m, z in ts.items():
            require(z.bin_index.tolist() == base.bin_index.tolist(), case + m + " bin alignment")
            require(z.bin_start.tolist() == base.bin_start.tolist() and z.bin_end.tolist() == base.bin_end.tolist(), case + m + " clock alignment")
            close(case + m + " count equality", z.count_veh_per_lane, n)
            close(case + m + " five-minute duration", (pd.to_datetime(z.bin_end)-pd.to_datetime(z.bin_start)).dt.total_seconds(), 300)
            close(case + m + " speed/trip identity", z.equivalent_speed_mph, L/z.mean_trip_time_h)
            close(case + m + " exposure/trip identity", z.vehicle_hours_per_lane, n*z.mean_trip_time_h)
            close(case + m + " signed delay identity", z.mean_delay_h, z.mean_trip_time_h-Tf, atol=2e-14)
            close(case + m + " VSP at equivalent speed", z.vsp_at_equivalent_speed_kw_t, power(z.equivalent_speed_mph, vehicle))
            expected_H = obs.vehicle_hours.to_numpy() if m == "O" else n*base.vehicle_hours_per_lane.sum()/D if m == "S" else Hfit
            close(case + m + " exposure from preserved inputs", z.vehicle_hours_per_lane, expected_H)
            averages[m] = D*L/z.vehicle_hours_per_lane.sum()
            z_expected = power(z.equivalent_speed_mph, vehicle) if m in ("O", "S") else vr_vsp if m == "R" else vma_vsp
            close(case + m + " operating-exposure VSP", z.exposure_weighted_vsp_kw_t, z_expected)
            if m in ("M", "A"):
                close(case + m + " free-state time", z.mean_free_time_h, free)
                close(case + m + " queue-state time", z.mean_queue_time_h, queue)
                close(case + m + " distance identity", vf*z.mean_free_time_h+target.vq_hat_mph*z.mean_queue_time_h, L)
        close(case + " S harmonic average preserved", averages["S"], averages["O"])
        for m in ("M", "A"):
            for col in ("equivalent_speed_mph", "mean_trip_time_h", "mean_delay_h"):
                close(case + m + " common fitted " + col, ts[m][col], ts["R"][col])
        close(case + " M/A VSP equality", ts["M"].exposure_weighted_vsp_kw_t, ts["A"].exposure_weighted_vsp_kw_t)

        def record(group, quantity, method, actual, fitted, unit, pollutant="", scalar=False):
            expected_records.append(dict(case_id=case, episode_id=eid, group=group,
                pollutant=pollutant, quantity=quantity, method=method, reference="O",
                aggregation="episode_scalar" if scalar else "equal_five_minute_bins",
                unit=unit, **statistics(actual, fitted, scalar)))

        for m in METHODS[1:]:
            if m != "S":
                record("traffic", "duration", m, [target.P_h], [target.P_hat_h], "h", scalar=True)
                record("traffic", "minimum_speed", m, [target.vt2_obs_mph], [target.vt2_hat_mph], "mph", scalar=True)
            record("traffic", "average_speed", m, [averages["O"]], [averages[m]], "mph", scalar=True)
            for quantity, column, scale, unit in [
                ("speed_5min", "equivalent_speed_mph", 1, "mph"),
                ("travel_time_5min", "mean_trip_time_h", 60, "min"),
                ("delay_5min", "mean_delay_h", 60, "min"),
                ("vsp_5min", "exposure_weighted_vsp_kw_t", 1, "kW/t"),
            ]:
                record("traffic", quantity, m, base[column].to_numpy()*scale,
                       ts[m][column].to_numpy()*scale, unit)

        for p in POLLUTANTS:
            es = {m: emission.loc[emission.method.eq(m)&emission.pollutant.eq(p)].sort_values("bin_index") for m in METHODS}
            for m, z in es.items():
                require(z.bin_index.tolist() == base.bin_index.tolist(), case + m + p + " emission bin alignment")
                require(z.bin_start.tolist() == base.bin_start.tolist() and z.bin_end.tolist() == base.bin_end.tolist(), case + m + p + " emission clock alignment")
                close(case + m + p + " emission exposure", z.vehicle_hours_per_lane, ts[m].vehicle_hours_per_lane)
                close(case + m + p + " effective rate product", z.effective_rate_g_veh_h*z.vehicle_hours_per_lane, z.emission_g_per_lane)
                close(case + m + p + " cumulative definition", z.cumulative_emission_g_per_lane, z.emission_g_per_lane.cumsum())
                close(case + m + p + " cumulative count definition", z.cumulative_count_veh_per_lane, n.cumsum())
                close(case + m + p + " frozen episode total", z.emission_g_per_lane.sum(), target[m+"_"+p], rtol=1e-9, atol=1e-8)
                if m == "O":
                    continue
                for quantity, column, unit in [
                    ("effective_rate_5min", "effective_rate_g_veh_h", "g/vehicle-hour"),
                    ("emission_5min", "emission_g_per_lane", "g/lane/bin"),
                    ("cumulative_emission", "cumulative_emission_g_per_lane", "g/lane"),
                ]:
                    # For cumulative WAPE, exactly the bin-end samples enter;
                    # the display's initial zero adds no extra observation.
                    record("emission", quantity, m, es["O"][column], z[column], unit, p)
                record("emission", "total_emission", m, [es["O"].emission_g_per_lane.sum()],
                       [z.emission_g_per_lane.sum()], "g/lane", p, scalar=True)

        for col in ("corridor", "paper_corridor", "sensor_uid", "date", "period"):
            require(meta[col] == target[col], case + " index " + col)
        require(meta["bin_start"] == base.bin_start.iloc[0] == target.t0, case + " start boundary")
        require(meta["bin_end"] == base.bin_end.iloc[-1] == target.t3, case + " end boundary")
        expected_meta = dict(observed_bins=bins, model_nodes=len(nd), observed_duration_h=target.P_h,
            predicted_duration_h=target.P_hat_h, D_veh_per_lane=D, L_mi=L, vf_mph=vf,
            vq_hat_mph=target.vq_hat_mph, Tf_h=Tf,
            observed_vehicle_hours_per_lane=base.vehicle_hours_per_lane.sum(),
            predicted_vehicle_hours_per_lane=Hfit.sum(), minimum_aligned_free_time_s=free.min()*3600,
            maximum_count_residual_veh=np.max(abs(overlap.sum(axis=1)-n)),
            maximum_distance_residual_mi=np.max(abs(vf*free+target.vq_hat_mph*queue-L)),
            maximum_time_residual_h=np.max(abs(free+queue-trip_fit)),
            maximum_average_speed_residual_mph=np.max(abs((vf*free+target.vq_hat_mph*queue)/(free+queue)-L/trip_fit)))
        expected_case = pd.DataFrame(expected_records[-90:])
        fitted_metrics = expected_case.loc[expected_case.group.eq("traffic")&expected_case.method.eq("R")].set_index("quantity")
        for quantity in ("duration", "minimum_speed", "average_speed"):
            expected_meta[quantity+"_ape_pct"] = fitted_metrics.loc[quantity, "ape_pct"]
            expected_meta["observed_"+quantity] = fitted_metrics.loc[quantity, "reference_value"]
            expected_meta["predicted_"+quantity] = fitted_metrics.loc[quantity, "model_value"]
        for quantity in ("speed_5min", "travel_time_5min", "delay_5min", "vsp_5min"):
            expected_meta[quantity+"_wape_pct"] = fitted_metrics.loc[quantity, "wape_pct"]
        for key, value in expected_meta.items():
            close(case + " index " + key, meta[key], value)
        require(set(meta) == {"case_id", "folder", "episode_id", "corridor", "paper_corridor", "sensor_uid", "date", "period", "bin_start", "bin_end"} | set(expected_meta), case + " every index field checked")

    require(negative_delays == 1, "Preserved signed-delay edge case")
    require(distinct_peak_targets > 0, "Calibration minimum-speed target differs from binned minimum")
    expected = pd.DataFrame(expected_records)
    # Match published field order without depending on implementation order.
    expected = expected[all_metrics.columns]
    frames("Every statistical value and metric definition", all_metrics, expected, KEYS)
    frames("Combined metrics match per-case CSVs", all_metrics, pd.concat(collected_metrics, ignore_index=True), KEYS)
    frames("Combined traffic matches per-case CSVs", pd.read_csv(directory/"all_traffic_timeseries.csv.gz"), pd.concat(collected_traffic, ignore_index=True), ["case_id", "method", "bin_index"])
    frames("Combined emissions match per-case CSVs", pd.read_csv(directory/"all_emissions_timeseries.csv.gz"), pd.concat(collected_emissions, ignore_index=True), ["case_id", "method", "pollutant", "bin_index"])
    require(sum(len(x) for x in collected_traffic) == 24000 and sum(len(x) for x in collected_emissions) == 96000, "All 4,800 observed bins and five methods retained")
    scalar = all_metrics.loc[all_metrics.aggregation.eq("episode_scalar")]
    profile = all_metrics.loc[all_metrics.aggregation.eq("equal_five_minute_bins")]
    require(scalar.wape_pct.isna().all() and profile.ape_pct.isna().all(), "APE and WAPE not interchanged")
    require(not ((all_metrics.method == "S") & all_metrics.quantity.isin(["duration", "minimum_speed"])).any(), "S has no invented duration or calibrated minimum-speed target")
    for quantity, predicted, actual in [("duration", "P_hat_h", "P_h"), ("minimum_speed", "vt2_hat_mph", "vt2_obs_mph")]:
        z = scalar.loc[scalar.method.eq("R")&scalar.quantity.eq(quantity)]
        pooled = 100*(z.mae*z.n_pairs).sum()/z.denominator_abs_sum.sum()
        direct = 100*(frozen[predicted]-frozen[actual]).abs().sum()/frozen[actual].abs().sum()
        close("Pooled scalar " + quantity + " uses numerator/denominator sums", pooled, direct)
        print(f"Pooled {quantity} WAPE: {pooled:.10f}%")
    for method in ("S", "R", "M", "A"):
        result = []
        for quantity in ("speed_5min", "travel_time_5min", "delay_5min", "vsp_5min"):
            z = profile.loc[profile.method.eq(method)&profile.quantity.eq(quantity)]
            result.append(f"{quantity}={100*(z.mae*z.n_pairs).sum()/z.denominator_abs_sum.sum():.10f}%")
        print(method + ": " + ", ".join(result))
    print(f"PASS: {len(CHECKS):,} assertions; all 12,330 metrics and 137 index records verified.")
    print(f"Checked {directory}; no files written.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT,
                        help="Published or generated step-11 directory")
    verify(parser.parse_args().directory.resolve())
