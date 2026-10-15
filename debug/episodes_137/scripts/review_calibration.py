"""Independent traffic-calibration audit of the retained 137-episode sample."""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

from _paths import ROOT, arguments
args = arguments(__doc__)
OUT = args.output
SOURCE = ROOT / "data/frozen/calibration/average_weekday"
ep = pd.read_csv(SOURCE / "episode_results_v2.csv")
z = ep.loc[ep.matched_ladder_pass].copy().reset_index(drop=True)
assert len(z) == 137
panel = pd.read_csv(SOURCE / "traffic_panel.csv.gz", usecols=["sensor_uid", "datetime", "flow_vph", "speed_mph"], parse_dates=["datetime"])
panel["date"] = panel.datetime.dt.strftime("%Y-%m-%d")
groups = {key: value for key, value in panel.groupby(["sensor_uid", "date"], sort=False)}
dt = 1/12
observed = []
for r in z.to_dict("records"):
    g = groups[(r["sensor_uid"], r["date"])]
    g = g[(g.datetime >= pd.Timestamp(r["t0"])) & (g.datetime < pd.Timestamp(r["t3"]))]
    v = g.speed_mph.to_numpy(float)
    count = g.flow_vph.to_numpy(float) * dt
    time = r["L_mi"] / v
    demand = count.sum()
    vht = np.sum(count*time)
    wbar = vht/demand - r["Tf_h"]
    peak = time.max()-r["Tf_h"]
    observed.append({
        "bins": len(g), "D_rebuilt": demand, "H_obs": vht,
        "wbar_rebuilt_h": wbar, "peak_rebuilt_h": peak,
        "P_rebuilt_h": (pd.Timestamp(r["t3"])-pd.Timestamp(r["t0"])).total_seconds()/3600,
        "mean_speed_rebuilt_mph": demand*r["L_mi"]/vht,
        "unweighted_mean_delay_h": float(np.mean(time-r["Tf_h"])),
        "minimum_bin_speed_mph": float(v.min()),
    })
z = pd.concat([z, pd.DataFrame(observed)], axis=1)
z["H_hat"] = z.D_veh*(z.Tf_h+z.wbar_hat_h)
z["delay_obs_veh_h"] = z.D_veh*z.wbar_h
z["delay_hat_veh_h"] = z.D_veh*z.wbar_hat_h
z["mean_delay_error_pct"] = 100*(z.wbar_hat_h/z.wbar_h-1)
z["mean_delay_APE_pct"] = z.mean_delay_error_pct.abs()
z["P_error_pct"] = 100*(z.P_hat_h/z.P_h-1)
z["P_APE_pct"] = z.P_error_pct.abs()
z["peak_error_pct"] = 100*(z.wt2_hat_h/z.wt2_h-1)
z["peak_APE_pct"] = z.peak_error_pct.abs()
z["conditional_peak_error_pct"] = 100*(z.wt2_conditional_hat_h/z.wt2_h-1)
z["conditional_peak_APE_pct"] = z.conditional_peak_error_pct.abs()
z["theta_error_pct"] = 100*(z.theta/z.theta_observed-1)
z["theta_APE_pct"] = z.theta_error_pct.abs()
z["H_error_pct"] = 100*(z.H_hat/z.H_obs-1)
z["H_APE_pct"] = z.H_error_pct.abs()
z["mean_delay_over_Tf"] = z.wbar_h/z.Tf_h
z["observed_delay_time_share"] = z.wbar_h/(z.Tf_h+z.wbar_h)
z["speed_reduction_fraction"] = 1-z.space_mean_speed_mph/z.vf_mph

# Exact mean-delay decomposition: first replace theta, then the conditional
# severity relationship, then estimated episode duration.
z["mean_delay_component_theta_h"] = (z.theta-z.theta_observed)*z.wt2_h
z["mean_delay_component_severity_h"] = z.theta*(z.wt2_conditional_hat_h-z.wt2_h)
z["mean_delay_component_duration_h"] = z.theta*(z.wt2_hat_h-z.wt2_conditional_hat_h)
component_columns = ["mean_delay_component_theta_h", "mean_delay_component_severity_h", "mean_delay_component_duration_h"]


def metric(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = np.isfinite(y)&np.isfinite(p)
    y, p = y[ok], p[ok]
    if not len(y):
        return {"n": 0}
    den = np.sum((y-y.mean())**2)
    return {"n": len(y), "R2": float(1-np.sum((p-y)**2)/den) if den > 0 else None,
            "RMSE": float(np.sqrt(np.mean((p-y)**2))), "MAE": float(np.mean(abs(p-y))),
            "WAPE_pct": float(100*np.sum(abs(p-y))/np.sum(abs(y))),
            "bias_pct": float(100*(p.sum()/y.sum()-1)),
            "median_APE_pct": float(np.median(100*abs(p/y-1))),
            "observed_sum": float(y.sum()), "predicted_sum": float(p.sum())}


def cohort(g, pollutant):
    o, m, s = g[f"O_{pollutant}"], g[f"M_{pollutant}"], g[f"S_{pollutant}"]
    bad = (m-o).abs() > (s-o).abs()+1e-9
    return {"N": len(g), "M_worse_N": int(bad.sum()), "M_worse_share": float(bad.mean()) if len(g) else None,
            "M_emission": metric(o, m), "S_emission": metric(o, s),
            **{f"median_{k}": float(g[k].median()) if len(g) else None
               for k in ["P_APE_pct", "peak_APE_pct", "conditional_peak_APE_pct", "mean_delay_APE_pct", "H_APE_pct", "theta_APE_pct", "P_h", "mean_delay_over_Tf", "speed_reduction_fraction"]}}


audits = {
    "max_D_difference_veh": float(abs(z.D_rebuilt-z.D_veh).max()),
    "max_wbar_difference_h": float(abs(z.wbar_rebuilt_h-z.wbar_h).max()),
    "max_peak_difference_h": float(abs(z.peak_rebuilt_h-z.wt2_h).max()),
    "max_duration_difference_h": float(abs(z.P_rebuilt_h-z.P_h).max()),
    "max_mean_speed_difference_mph": float(abs(z.mean_speed_rebuilt_mph-z.space_mean_speed_mph).max()),
    "max_predicted_P_difference_h": float(abs(np.maximum(z.fd*z.x_h**z.n,z.x_h)-z.P_hat_h).max()),
    "max_predicted_peak_difference_h": float(abs(z.Tf_h*z.fp*z.P_hat_h**z.s-z.wt2_hat_h).max()),
    "max_conditional_peak_difference_h": float(abs(z.Tf_h*z.fp*z.P_h**z.s-z.wt2_conditional_hat_h).max()),
    "max_mean_delay_decomposition_error_h": float(abs(z[component_columns].sum(axis=1)-(z.wbar_hat_h-z.wbar_h)).max()),
    "all_bins_match_episode_duration": bool(np.all(z.bins == np.rint(z.P_h/dt))),
}
assert audits["max_wbar_difference_h"] < 1e-12
assert audits["max_peak_difference_h"] < 1e-12
assert audits["max_mean_delay_decomposition_error_h"] < 1e-12

metrics = {name: metric(z[a],z[b]) for name,a,b in [
    ("duration_hours","P_h","P_hat_h"), ("peak_delay_hours","wt2_h","wt2_hat_h"),
    ("peak_delay_conditional_on_observed_duration_hours","wt2_h","wt2_conditional_hat_h"),
    ("mean_delay_hours_per_vehicle","wbar_h","wbar_hat_h"),
    ("vehicle_delay_hours","delay_obs_veh_h","delay_hat_veh_h"),
    ("vehicle_hours","H_obs","H_hat"), ("minimum_speed_mph","vt2_obs_mph","vt2_hat_mph"),
]}
components = []
total_delay_error = float(np.sum(z.D_veh*(z.wbar_hat_h-z.wbar_h)))
for column in component_columns:
    values = z.D_veh*z[column]
    components.append({"component": column, "sum_signed_vehicle_hours": float(values.sum()),
                       "sum_absolute_vehicle_hours": float(abs(values).sum()),
                       "signed_pct_observed_total_delay": float(100*values.sum()/z.delay_obs_veh_h.sum()),
                       "absolute_pct_observed_total_delay": float(100*abs(values).sum()/z.delay_obs_veh_h.sum())})

pollutant_results = {}
for p in ["CO2", "NOx", "CO", "HC"]:
    o, m, s = z[f"O_{p}"], z[f"M_{p}"], z[f"S_{p}"]
    excess = 100*((m-o).abs()-(s-o).abs())/o
    worse = excess > 1e-8
    cohorts = {
        "all": cohort(z,p), "M_worse_than_S": cohort(z[worse],p), "M_not_worse_than_S": cohort(z[~worse],p),
        "mean_delay_APE_at_most_10pct": cohort(z[z.mean_delay_APE_pct<=10],p),
        "mean_delay_APE_over_25pct": cohort(z[z.mean_delay_APE_pct>25],p),
        "VHT_APE_at_most_5pct": cohort(z[z.H_APE_pct<=5],p),
        "VHT_APE_over_20pct": cohort(z[z.H_APE_pct>20],p),
        "duration_APE_at_most_10pct": cohort(z[z.P_APE_pct<=10],p),
        "duration_APE_over_25pct": cohort(z[z.P_APE_pct>25],p),
        "mean_delay_at_most_half_Tf": cohort(z[z.mean_delay_over_Tf<=.5],p),
        "mean_delay_over_2Tf": cohort(z[z.mean_delay_over_Tf>2],p),
    }
    correlations = []
    for x in ["mean_delay_APE_pct", "H_APE_pct", "P_APE_pct", "peak_APE_pct", "conditional_peak_APE_pct", "theta_APE_pct", "mean_delay_error_pct", "H_error_pct", "P_error_pct", "P_h", "mean_delay_over_Tf", "vf_mph", "vq_hat_mph", "s"]:
        correlations.append({"feature":x,"Pearson":float(z[x].corr(excess)),"Spearman":float(z[x].rank().corr(excess.rank()))})
    pollutant_results[p] = {"cohorts":cohorts,"correlations_with_M_minus_S_absolute_error_percentage_points":correlations,
                            "by_corridor":{c:cohort(g,p) for c,g in z.groupby("corridor")}}

selected_cols = ["episode_id","sensor_uid","date","corridor","period","bins","D_veh","Tf_h","P_h","P_hat_h",
                 "wt2_h","wt2_hat_h","wt2_conditional_hat_h","wbar_h","wbar_hat_h","wbar_rebuilt_h","unweighted_mean_delay_h",
                 "theta_observed","theta","s","H_obs","H_hat","P_error_pct","P_APE_pct","peak_error_pct","peak_APE_pct",
                 "conditional_peak_error_pct","mean_delay_error_pct","mean_delay_APE_pct","H_error_pct","H_APE_pct"]+component_columns
report = {
    "source":(SOURCE / "episode_results_v2.csv").relative_to(ROOT).as_posix(),
    "source_sha256":hashlib.sha256((SOURCE / "episode_results_v2.csv").read_bytes()).hexdigest(),
    "matched_N":len(z),"total_episode_rows":len(ep),"corridors":z.corridor.value_counts().to_dict(),
    "calibration_split":z.calibration_split.value_counts().to_dict(),"holdout_N":int(z.holdout.sum()),
    "definitions":{
        "observed_mean_delay":"sum_i q_i*(L/v_i-Tf)/sum_i q_i = H_obs/D-Tf; dt=1/12 h cancels in weights. Uses traffic_panel speed_mph, no clipping negative individual bin delays.",
        "observed_peak_delay":"L/min_i(v_i)-Tf; same bins [t0,t3), not the older boundary-speed denominator.",
        "observed_duration":"(t3-t0) hours; selected bins t0 inclusive, t3 exclusive.",
        "predicted_duration":"max(fd*(D/C)^n,D/C)",
        "predicted_peak_delay":"Tf*fp*P_hat^s",
        "conditional_peak_delay":"Tf*fp*P_observed^s; counterfactual removes duration prediction error only.",
        "predicted_mean_delay":"theta*predicted_peak_delay; theta is fitted corridor-direction-period median of observed theta, with all-period fallback when needed.",
        "exact_mean_delay_error_decomposition":"(theta_hat-theta_obs)*peak_obs + theta_hat*(peak_conditional-peak_obs) + theta_hat*(peak_hat-peak_conditional). Path dependent; signed contributions can cancel; not independent causal shares.",
        "M_worse_than_S":"abs(M-O)>abs(S-O) separately for each pollutant and each episode; compares with point-speed proxy O, not measured emissions.",
    },
    "reproduction":audits,"traffic_metrics":metrics,"mean_delay_error_components":components,
    "total_signed_vehicle_delay_error_h":total_delay_error,
    "unweighted_vs_weighted_delay":{"median_relative_difference_pct":float(np.median(100*(z.unweighted_mean_delay_h/z.wbar_h-1))),
                                     "max_absolute_difference_minutes":float((60*abs(z.unweighted_mean_delay_h-z.wbar_h)).max())},
    "pollutants":pollutant_results,
    "episodes":z[selected_cols].to_dict(orient="records"),
    "source_code_locations":[
        "src/qvdfe/pipeline/_engine/model.py: observed_targets",
        "src/qvdfe/pipeline/_engine/model.py: fit_parameters",
        "src/qvdfe/pipeline/_engine/model.py: predictions",
        "src/qvdfe/pipeline/_engine/model.py: emission_ladder",
        "src/qvdfe/pipeline/_engine/calibration.py: calibration (average-profile labels)",
    ],
    "caveats":[
        "All 137 observations are average-profile fitted episodes; none is a held-out validation day.",
        "The matched sample is conditioned on calibration eligibility, predicted geometry, closed/nonnegative profile, cubic domain and positive finite results for all methods and pollutants. Its calibration metrics need not match metrics on all eligible episodes.",
        "Observed delay, peak delay and VHT derive from detector point-speed-as-link-speed proxies, not observed vehicle link traversals.",
        "The tests hold detector fundamental-diagram parameters fixed and do not diagnose their uncertainty.",
        "Correlations and thresholds describe this selected sample; no causal inference or independent validation is claimed. Thresholds 5/10/20/25 percent are diagnostic groupings, not calibration exclusion rules.",
        "Fitted severity exponent s can amplify duration error: peak_hat/peak_conditional=(P_hat/P_observed)^s.",
        "Queue speed obtained from flow and the fundamental diagram is not the observed detector minimum speed.",
    ],
}


def sanitize(value):
    if isinstance(value, dict):
        return {str(k):sanitize(v) for k,v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, (float,np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    return value


target = OUT / "support/calibration_review.json"
target.write_text(json.dumps(sanitize(report),indent=2,allow_nan=False))
print(json.dumps(sanitize({"output":str(target),"reproduction":audits,"traffic_metrics":metrics,
                          "delay_components":components,"pollutant_comparisons":{
                              p:{k:v for k,v in data["cohorts"].items() if k in ["all","mean_delay_APE_at_most_10pct","VHT_APE_at_most_5pct"]}
                              for p,data in pollutant_results.items()}}),indent=2))
