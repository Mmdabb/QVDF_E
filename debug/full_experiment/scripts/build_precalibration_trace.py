"""Expose the preserved experiment's inputs, targets, screening and calibration.

This is a trace, not a new detection or calibration run. Frozen episode boundaries,
fit coefficients and masks remain authoritative. Numeric intermediates are freshly
calculated and checked against those references. Run from any working directory.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from qvdfe.pipeline._engine import model, calibration
from qvdfe.pipeline._engine.episodes import _base_frame, _config
from qvdfe.pipeline._engine.cbi_state_transition import detection_speed_series

DATA = ROOT / "data/frozen/calibration"
BASE = ROOT / "data/inputs/empirical/baseline"
STEPS = ["01_inputs", "02_prepared_profiles", "03_episode_detection", "04_calibration"]
TRACKS = ["average_weekday", "daily_validation"]
DT = 1 / 12


def safe_output(value: str | None) -> Path:
    out = Path(value).resolve() if value else ROOT / "debug/output/full_experiment/precalibration"
    for source in [ROOT / "data", ROOT / "src", ROOT / "reproduce", ROOT / "tools", ROOT / "debug/full_experiment/steps", ROOT / "debug/episodes_137", ROOT / "debug/sensor78"]:
        if out == source or source in out.parents or out in source.parents:
            raise ValueError(f"Output overlaps protected source/reference path: {source.relative_to(ROOT)}")
    if ROOT / "debug/full_experiment/scripts" == out or ROOT / "debug/full_experiment/scripts" in out.parents or out in (ROOT / "debug/full_experiment/scripts").parents:
        raise ValueError("Output overlaps generator source")
    marker = out / ".qvdfe-precalibration-trace.json"
    if out.exists() and any(out.iterdir()) and not marker.exists():
        raise ValueError("Nonempty output directory is not owned by this trace generator")
    out.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"owner":"qvdfe-precalibration-trace"}\n', encoding="utf-8")
    for name in STEPS:
        (out / name).mkdir(exist_ok=True)
    return out


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    options = {"compression": {"method": "gzip", "mtime": 0}} if path.suffix == ".gz" else {}
    frame.to_csv(path, index=False, lineterminator="\n", **options)


def check_numeric(checks: list, label: str, calculated, stored, atol=1e-8, rtol=1e-10):
    a, b = np.asarray(calculated, dtype=float), np.asarray(stored, dtype=float)
    passed = np.isclose(a, b, atol=atol, rtol=rtol, equal_nan=True)
    finite = np.isfinite(a) & np.isfinite(b)
    checks.append({"check": label, "N": int(a.size), "failures": int((~passed).sum()),
                   "max_absolute_difference": float(np.max(np.abs(a[finite] - b[finite]))) if finite.any() else 0.,
                   "absolute_tolerance": atol, "relative_tolerance": rtol})


def inputs(out: Path):
    rows = []
    source_root = ROOT / "data/inputs/empirical/source_files"
    raw = json.loads((BASE / "input_sha256.json").read_text())
    sources = [(source_root / r["path"], "supplied source", r["sha256"]) for r in raw]
    sources += [(BASE / name, "preserved preprocessing baseline", "") for name in ["traffic_panel.csv.gz", "sensor_parameters.csv", "episodes_detected.csv", "detector_fd_calibration.csv"]]
    for track in TRACKS:
        sources += [(DATA / track / name, track + " frozen input/result", "") for name in ["traffic_panel.csv.gz", "sensor_parameters.csv", "episodes_detected.csv", "episode_results_v2.csv", "detector_fd_calibration.csv", "parameter_card_full.csv", "parameter_bootstrap.csv.gz"]]
    for path, role, expected in sources:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected and digest != expected:
            raise ValueError(f"Supplied source hash changed: {path.relative_to(ROOT)}")
        frame = pd.read_csv(path, low_memory=False)
        rows.append(dict(path=path.relative_to(ROOT).as_posix(), role=role, rows=len(frame), columns=len(frame.columns), bytes=path.stat().st_size, sha256=digest, original_hash_matches=digest == expected if expected else "not_applicable"))
    write_csv(pd.DataFrame(rows), out / "01_inputs/01_source_inventory.csv")
    baseline = pd.read_csv(BASE / "traffic_panel.csv.gz", parse_dates=["datetime"], low_memory=False)
    baseline["date"] = baseline.datetime.dt.strftime("%Y-%m-%d")
    baseline["profile_key"] = baseline.sensor_uid + "::" + baseline.date
    grouped = baseline.groupby(["corridor", "dataset"], dropna=False).agg(five_minute_rows=("datetime", "size"), sensors=("sensor_uid", "nunique"), profiles=("profile_key", "nunique"), dates=("date", "nunique"), first_datetime=("datetime", "min"), last_datetime=("datetime", "max"))
    write_csv(grouped.reset_index(), out / "01_inputs/02_baseline_support_by_corridor.csv")
    constants = [
        ("time_step", DT, "hour", "five-minute observations"),
        ("daily_expected_bins", 288, "bins", "a complete 24-hour day"),
        ("minimum_complete_weekdays", 5, "days per detector-month", "Arizona monthly profile support"),
        ("observation_valid_speed_max", 90, "mph", "FD fitting, averaging support and episode hard QC; raw records retained"),
        ("jam_density", 220, "vehicles/mile/lane", "triangular queue-state closure"),
        ("minimum_fit_episodes", 8, "episodes", "local period fit, otherwise same direction all periods"),
        ("outlier_MAD_multiplier", 1.4826, "dimensionless", "robust scale"),
        ("outlier_z_threshold", 3.5, "robust scale units", "strictly greater than"),
        ("outlier_votes_to_fail", 2, "votes", "among three relationships and marginal log-duration"),
        ("relationship_scale_floor", .10, "log units", "MAD scale minimum"),
        ("duration_scale_floor", .20, "log units", "marginal duration MAD scale minimum"),
        ("bootstrap_replicates", 400, "draws", "preserved parameter and metric uncertainty"),
        ("bootstrap_lower_quantile", .025, "probability", "95% interval"),
        ("bootstrap_upper_quantile", .975, "probability", "95% interval"),
        ("parameter_bootstrap_seed", 15020910, "integer", "stored model calibrate routine"),
        ("duration_log_fd_bounds", "[-6,6]", "log coefficient", "soft_l1 fit"),
        ("duration_n_bounds", "[0.15,4]", "exponent", "soft_l1 fit"),
        ("severity_s_bounds", "[0.05,6]", "exponent", "robust log-linear fit"),
        ("duration_soft_l1_scale", .2, "log residual", "maximum 80 function evaluations"),
        ("AM", "06:00–10:00", "clock time", "episode assigned by minimum-speed time t2"),
        ("MD", "10:00–16:00", "clock time", "whole episodes retained"),
        ("PM", "16:00–20:00", "clock time", "whole episodes retained"),
        ("NT", "20:00–06:00", "clock time", "cross-midnight period; calendar-censored episodes excluded from fit"),
    ]
    write_csv(pd.DataFrame(constants, columns=["setting", "value", "unit", "meaning"]), out / "01_inputs/03_calculation_constants.csv")
    return baseline


def profiles(out: Path, panels: dict, episodes: dict, checks: list):
    records, smoothed = [], []
    for track, panel in panels.items():
        counts = episodes[track].groupby(["sensor_uid", "date"]).size()
        for (sid, date), g in panel.groupby(["sensor_uid", "date"], sort=True):
            valid = np.isfinite(g.speed_mph) & g.speed_mph.gt(0) & g.speed_mph.le(90) & np.isfinite(g.flow_vph) & g.flow_vph.ge(0)
            r = g.iloc[0]
            allowed = pd.Timestamp(date).dayofweek < 5
            records.append(dict(analysis_track=track, sensor_uid=sid, date=date, corridor=r.corridor, holdout=bool(r.holdout), bins=len(g), valid_bins=int(valid.sum()), unique_timestamps=g.datetime.nunique(), complete_24h_profile=len(g)==288 and valid.all(), detection_calendar_filter_pass=allowed, detected_episodes=int(counts.get((sid,date),0)), five_minute_volume_sum_veh_per_lane=float((g.flow_vph*DT).sum(min_count=1)), VHT_veh_h_per_lane=float((g.flow_vph*DT*r.L_mi/g.speed_mph.where(valid)).sum(min_count=1)), VHT_valid_bin_count=int(valid.sum())))
            if track == "average_weekday":
                frame = _base_frame(g)
                cfg = _config(r.vf_mph, .7*r.vf_mph, 30., 15., True)
                v = detection_speed_series(frame, cfg)
                smoothed.append(pd.DataFrame({"sensor_uid":sid,"date":date,"datetime":frame.timestamp,"recorded_speed_mph":frame.speed_mph,"detection_speed_mph":v,"flow_vphpl":frame.flow,"volume_veh_per_lane":frame.flow*DT,"free_speed_mph":r.vf_mph,"congestion_threshold_mph":.7*r.vf_mph,"free_threshold_mph":.85*r.vf_mph,"calendar_filter_pass":allowed,"recorded_speed_missing":~np.isfinite(frame.speed_mph),"recorded_qc_flagged":frame.speed_qc_flagged,"note":"smoothing reconstructed; frozen episode boundaries preserved"}))
    write_csv(pd.DataFrame(records), out / "02_prepared_profiles/01_profile_support_ledger.csv")
    write_csv(pd.concat(smoothed, ignore_index=True), out / "02_prepared_profiles/02_average_profile_detection_inputs.csv.gz")
    support = pd.read_csv(DATA / "average_weekday/i10_monthly_day_support.csv")
    month = pd.read_csv(DATA / "average_weekday/i10_monthly_profile_support.csv")
    write_csv(support, out / "02_prepared_profiles/03_arizona_day_support.csv")
    write_csv(month, out / "02_prepared_profiles/04_arizona_month_support.csv")
    az = panels["daily_validation"].copy()
    az["month"] = az.datetime.dt.strftime("%Y-%m")
    az["minute"] = az.datetime.dt.hour*60 + az.datetime.dt.minute
    selected = az.merge(support[support.included][["sensor_uid","date"]], on=["sensor_uid","date"], validate="many_to_one")
    selected["q_over_v"] = selected.flow_vph/selected.speed_mph
    z = selected.groupby(["sensor_uid","month","minute"],as_index=False).agg(days=("date","nunique"),sum_q_vphpl=("flow_vph","sum"),sum_q_over_v_veh_per_mi_lane=("q_over_v","sum"),mean_empty_speed_mph=("speed_mph","mean"))
    z["mean_flow_vphpl"] = z.sum_q_vphpl/z.days
    z["mean_q_over_v"] = z.sum_q_over_v_veh_per_mi_lane/z.days
    z["harmonic_speed_mph"] = np.where(z.mean_flow_vphpl>0,z.sum_q_vphpl/z.sum_q_over_v_veh_per_mi_lane,z.mean_empty_speed_mph)
    old = panels["average_weekday"].query("corridor == 'AZ_I10_W'")[["sensor_uid","month","minute","flow_vph","speed_mph","L_mi"]]
    z = z.merge(old,on=["sensor_uid","month","minute"],validate="one_to_one")
    z["volume_veh_per_lane"] = z.mean_flow_vphpl*DT
    z["VHT_veh_h_per_lane"] = z.volume_veh_per_lane*z.L_mi/z.harmonic_speed_mph
    z["source_mean_VHT_veh_h_per_lane"] = DT*z.L_mi*z.mean_q_over_v
    z["flow_minus_frozen_vphpl"] = z.mean_flow_vphpl-z.flow_vph
    z["speed_minus_frozen_mph"] = z.harmonic_speed_mph-z.speed_mph
    check_numeric(checks,"Arizona monthly mean flow",z.mean_flow_vphpl,z.flow_vph)
    check_numeric(checks,"Arizona harmonic mean speed",z.harmonic_speed_mph,z.speed_mph)
    check_numeric(checks,"Arizona averaging preserves vehicle hours",z.VHT_veh_h_per_lane,z.source_mean_VHT_veh_h_per_lane)
    write_csv(z,out/"02_prepared_profiles/05_arizona_monthly_bin_calculations.csv")
    dates = az.groupby(["date","holdout"],as_index=False).agg(sensors=("sensor_uid","nunique"),bins=("datetime","size"))
    dates["split"] = np.where(dates.holdout,"later_date","training")
    write_csv(dates,out/"02_prepared_profiles/06_daily_validation_date_split.csv")


def screening(out: Path, panels: dict, episodes: dict, checks: list):
    observations, ledgers, thresholds, residuals = [], [], [], []
    for track, ep in episodes.items():
        groups = {k:g for k,g in panels[track].groupby(["sensor_uid","date"])}
        for r in ep.itertuples():
            g = groups[(r.sensor_uid,r.date)]
            g = g[(g.datetime >= pd.Timestamp(r.t0)) & (g.datetime < pd.Timestamp(r.t3))]
            q, v = g.flow_vph.to_numpy(), g.speed_mph.to_numpy()
            complete = len(g)==round(r.P_h/DT) and np.isfinite(q).all() and np.isfinite(v).all()
            valid = complete and (q>=0).all() and (v>0).all() and (v<=90).all()
            D = np.sum(q)*DT if np.isfinite(q).all() else np.nan
            Tf=r.L_mi/r.vf_mph
            peak=r.L_mi/np.min(v)-Tf if valid else np.nan
            vht=np.sum(q*DT*r.L_mi/v) if valid else np.nan
            delay=np.sum(q*DT*(r.L_mi/v-Tf)) if valid else np.nan
            mean=delay/D if valid and D>0 else np.nan
            rows=dict(analysis_track=track,episode_id=r.episode_id,sensor_uid=r.sensor_uid,date=r.date,corridor=r.corridor,period=r.period,holdout=r.holdout,t0=r.t0,t2=r.t2,t3=r.t3,P_h=r.P_h,expected_bins=round(r.P_h/DT),actual_bins=len(g),complete=complete,valid_speed_and_flow=valid,L_mi=r.L_mi,vf_mph=r.vf_mph,C_vphpl=r.C_vphpl,sum_flow_vphpl=np.sum(q),D_calculated_veh_per_lane=D,x_calculated_h=D/r.C_vphpl,mu_calculated_vphpl=D/r.P_h,Tf_calculated_h=Tf,VHT_calculated_veh_h_per_lane=vht,delay_total_veh_h_per_lane=delay,peak_delay_calculated_h=peak,mean_delay_calculated_h=mean,theta_calculated=mean/peak if peak>0 else np.nan,minimum_speed_calculated_mph=np.min(v) if valid else np.nan,D_frozen_veh_per_lane=r.D_veh,x_frozen_h=r.x_h,Tf_frozen_h=r.Tf_h,peak_delay_frozen_h=r.wt2_h,mean_delay_frozen_h=r.wbar_h,theta_frozen=r.theta_observed)
            observations.append(rows)
        e = ep.copy()
        e.insert(0,"analysis_track",track)
        cols=["analysis_track","episode_id","sensor_uid","date","corridor","period","calibration_split","t0","t2","t3","P_h","D_veh","x_h","vt2_obs_mph","is_valid_for_mu","n_episode_missing_speeds","n_episode_flagged_speeds","incomplete_episode","invalid_observed_speed_or_flow","day_boundary_censored","metadata_capacity_flag","qc_hard_fail","qc_reason","outlier_votes","outlier_duration_relation","outlier_normalized_severity_relation","outlier_recovery_relation","outlier_duration_marginal","qc_outlier_fail","calibration_eligible","calibration_scope","physical_observed_pass","physical_predicted_pass","physical_failure_reason"]
        if "matched_ladder_pass" in e: cols += ["profile_closed_pass","cubic_domain_pass","matched_ladder_pass"]
        e=e[[c for c in cols if c in e]].copy()
        e["fit_parameters_available"] = np.isfinite(ep.P_hat_h)
        e["first_exclusion_stage"] = np.select([ep.qc_hard_fail, ep.qc_outlier_fail, ~np.isfinite(ep.P_hat_h), ~ep.physical_predicted_pass], ["hard_QC","outlier_votes","parameters_unavailable","predicted_finite_link_bound"], default="retained_emission_comparison" if track=="average_weekday" else "eligible_daily_traffic_validation")
        if track=="daily_validation":
            e["first_exclusion_stage"] = np.where(ep.calibration_eligible,"retained_daily_traffic_validation",np.where(ep.qc_hard_fail,"hard_QC","outlier_votes"))
        ledgers.append(e)
        for corridor,g in ep.groupby("corridor"):
            train=g[~g.holdout & ~g.qc_hard_fail]
            for x,y,flag in [("x_h","P_h","outlier_duration_relation"),("P_h","wt2_normalized","outlier_normalized_severity_relation"),("x_h","mu_obs_vphpl","outlier_recovery_relation"),(None,"P_h","outlier_duration_marginal")]:
                z=train if x is None else train[(train[x]>0)&(train[y]>0)&np.isfinite(train[y])]
                available=len(train)>=8 and len(z)>=8
                intercept=slope=center=scale=np.nan
                if available:
                    if x is None:
                        train_res=np.log(z.P_h); target=np.log(g.P_h); floor=.2
                    else:
                        intercept,slope=model.robust_line(np.log(z[x].to_numpy()),np.log(z[y].to_numpy()))
                        train_res=np.log(z[y])-(intercept+slope*np.log(z[x]));target=np.log(g[y].where(g[y]>0))-(intercept+slope*np.log(g[x].where(g[x]>0)));floor=.1
                    center=np.median(train_res);scale=max(1.4826*np.median(abs(train_res-center)),floor)
                    score=np.abs(target-center)/scale
                    result=(score>3.5).fillna(False)
                else:
                    target=score=pd.Series(np.nan,index=g.index);result=pd.Series(False,index=g.index)
                thresholds.append(dict(analysis_track=track,corridor=corridor,relationship=flag,x=x or "none",y=y,N_training=len(z),available=available,log_intercept=intercept,log_slope=slope,median_residual=center,MAD_scaled_with_floor=scale,rejection_distance=3.5*scale))
                residuals.append(pd.DataFrame({"analysis_track":track,"episode_id":g.episode_id,"corridor":corridor,"relationship":flag,"observed_log_residual":target,"center":center,"scale":scale,"absolute_robust_z":score,"calculated_vote":result,"frozen_vote":g[flag]}))
                check_numeric(checks,f"{track} {corridor} {flag}",result,g[flag],atol=0,rtol=0)
    obs=pd.DataFrame(observations)
    for a,b in [("D_calculated_veh_per_lane","D_frozen_veh_per_lane"),("x_calculated_h","x_frozen_h"),("Tf_calculated_h","Tf_frozen_h"),("peak_delay_calculated_h","peak_delay_frozen_h"),("mean_delay_calculated_h","mean_delay_frozen_h"),("theta_calculated","theta_frozen")]:
        check_numeric(checks,a,obs[a],obs[b])
    write_csv(obs,out/"03_episode_detection/01_observed_target_calculations.csv")
    write_csv(pd.concat(ledgers,ignore_index=True),out/"03_episode_detection/02_episode_screening_ledger.csv")
    write_csv(pd.DataFrame(thresholds),out/"03_episode_detection/03_outlier_fit_thresholds.csv")
    write_csv(pd.concat(residuals,ignore_index=True),out/"03_episode_detection/04_outlier_residual_calculations.csv")
    cfg=asdict(_config(70.,49.,30.,15.,True))
    cfg.pop("stage1_dir");cfg.pop("output_folder")
    write_csv(pd.DataFrame([dict(setting=k,value=v,source="effective episode-detector configuration; vf=70 only illustrates fixed ratios") for k,v in cfg.items()]),out/"03_episode_detection/05_detection_configuration.csv")
    funnels=[]
    for track,ep in episodes.items():
        for group,g in [("All",ep),*list(ep.groupby("corridor"))]:
            masks=[("detected",np.ones(len(g),bool)),("hard_QC_pass",~g.qc_hard_fail),("calibration_eligible",g.calibration_eligible),("eligible_with_parameters",g.calibration_eligible&np.isfinite(g.P_hat_h)),("predicted_geometry_pass",g.calibration_eligible&g.physical_predicted_pass),("observed_geometry_diagnostic",g.calibration_eligible&g.physical_observed_pass)]
            if track=="average_weekday":masks.append(("matched_emission_comparison",g.matched_ladder_pass))
            for name,mask in masks:funnels.append(dict(analysis_track=track,group=group,stage=name,N=int(np.sum(mask)),meaning="diagnostic only; not admission" if name=="observed_geometry_diagnostic" else "daily geometry is diagnostic; all eligible finite pairs used for traffic scores" if track=="daily_validation" and name=="predicted_geometry_pass" else "stored result mask"))
    write_csv(pd.DataFrame(funnels),out/"03_episode_detection/06_sample_flow_counts.csv")


def fit_trace(out:Path,episodes:dict,checks:list):
    cards,fd_cards,preds,memberships,metrics=[],[],[],[],[]
    for track,ep in episodes.items():
        folder=DATA/track
        cards_i=pd.read_csv(folder/"parameter_card_full.csv")
        if "analysis_track" not in cards_i:cards_i.insert(0,"analysis_track",track)
        cards_i["alpha_calculated"]=cards_i.theta*cards_i.fp*cards_i.fd**cards_i.s
        cards_i["beta_calculated"]=cards_i.n*cards_i.s
        check_numeric(checks,track+" alpha identity",cards_i.alpha_calculated,cards_i.alpha)
        check_numeric(checks,track+" beta identity",cards_i.beta_calculated,cards_i.beta)
        cards.append(cards_i)
        fd=pd.read_csv(folder/"detector_fd_calibration.csv");fd.insert(0,"analysis_track",track)
        sensor=pd.read_csv(folder/"sensor_parameters.csv")
        fd=fd.merge(sensor[["sensor_uid","L_mi","lanes","kj","kc","omega_mph"]],on="sensor_uid",validate="one_to_one")
        fd["queue_critical_density_calculated"]=fd.C_vphpl/fd.vf_mph
        fd["backward_wave_speed_calculated_mph"]=fd.C_vphpl/(fd.kj-fd.queue_critical_density_calculated)
        fd["s3_critical_speed_calculated_mph"]=fd.vf_mph*2**(-2/fd.s3_m)
        fd_cards.append(fd)
        for c in cards_i.itertuples():
            local=ep[ep.calibration_eligible&~ep.holdout&ep.corridor.eq(c.corridor)&ep.period.eq(c.period)]
            source=local if c.calibration_scope=="corridor_period" else ep[ep.calibration_eligible&~ep.holdout&ep.corridor.eq(c.corridor)]
            check_numeric(checks,f"{track} {c.corridor} {c.period} N_train",[len(local)],[c.N_train],0,0)
            check_numeric(checks,f"{track} {c.corridor} {c.period} N_source",[len(source)],[c.N_source],0,0)
            theta_median=source.theta_observed.median() if c.calibration_scope!="unavailable" else np.nan
            cards_i.loc[c.Index,"theta_source_median"]=theta_median
            check_numeric(checks,f"{track} {c.corridor} {c.period} theta median",[theta_median],[c.theta])
            for r in source.itertuples():
                log_P_fit=np.log(max(c.fd*r.x_h**c.n,r.x_h)) if np.isfinite(c.fd) else np.nan
                log_severity_fit=np.log(c.fp)+c.s*np.log(r.P_h) if np.isfinite(c.fp) else np.nan
                memberships.append(dict(analysis_track=track,parameter_corridor=c.corridor,parameter_period=c.period,calibration_scope=c.calibration_scope,fit_available=c.calibration_scope!="unavailable",episode_id=r.episode_id,episode_period=r.period,sensor_uid=r.sensor_uid,date=r.date,x_h=r.x_h,P_h=r.P_h,normalized_peak_delay=r.wt2_h/r.Tf_h,theta_observed=r.theta_observed,log_x=np.log(r.x_h),log_P=np.log(r.P_h),log_normalized_peak_delay=np.log(r.wt2_h/r.Tf_h),log_duration_fit=log_P_fit,log_duration_residual=log_P_fit-np.log(r.P_h),log_severity_fit_at_observed_P=log_severity_fit,log_severity_residual=log_severity_fit-np.log(r.wt2_h/r.Tf_h)))
        columns=["episode_id","sensor_uid","date","corridor","period","calibration_split","calibration_eligible","calibration_scope","L_mi","vf_mph","C_vphpl","kj","x_h","D_veh","P_h","Tf_h","wt2_h","wbar_h","vt2_obs_mph","vq_mph","fd","n","fp","s","theta","P_hat_h","wt2_hat_h","wbar_hat_h","vt2_hat_mph","mu_hat_vphpl","vq_hat_mph","predicted_bound_h","physical_predicted_pass"]
        z=ep[columns].copy();z.insert(0,"analysis_track",track)
        z["P_power_h"]=z.fd*z.x_h**z.n
        z["P_calculated_h"]=np.maximum(z.P_power_h,z.x_h)
        z["normalized_peak_calculated"]=z.fp*z.P_calculated_h**z.s
        z["peak_delay_calculated_h"]=z.Tf_h*z.normalized_peak_calculated
        z["mean_delay_calculated_h"]=z.theta*z.peak_delay_calculated_h
        z["minimum_speed_calculated_mph"]=z.vf_mph/(1+z.normalized_peak_calculated)
        z["discharge_calculated_vphpl"]=z.D_veh/z.P_calculated_h
        z["omega_calculated_mph"]=z.C_vphpl/(z.kj-z.C_vphpl/z.vf_mph)
        z["queue_density_calculated"]=z.kj-z.discharge_calculated_vphpl/z.omega_calculated_mph
        z["queue_speed_calculated_mph"]=z.discharge_calculated_vphpl/z.queue_density_calculated
        z["maximum_delay_allowed_h"]=z.L_mi*(1/z.queue_speed_calculated_mph-1/z.vf_mph)
        z["delay_minus_limit_h"]=z.peak_delay_calculated_h-z.maximum_delay_allowed_h
        z["duration_error_h"]=z.P_calculated_h-z.P_h
        z["peak_delay_error_h"]=z.peak_delay_calculated_h-z.wt2_h
        z["mean_delay_error_h"]=z.mean_delay_calculated_h-z.wbar_h
        z["minimum_speed_error_mph"]=z.minimum_speed_calculated_mph-z.vt2_obs_mph
        z["queue_state_speed_error_mph"]=z.queue_speed_calculated_mph-z.vq_mph
        for a,b in [("P_calculated_h","P_hat_h"),("peak_delay_calculated_h","wt2_hat_h"),("mean_delay_calculated_h","wbar_hat_h"),("minimum_speed_calculated_mph","vt2_hat_mph"),("discharge_calculated_vphpl","mu_hat_vphpl"),("queue_speed_calculated_mph","vq_hat_mph"),("maximum_delay_allowed_h","predicted_bound_h")]:check_numeric(checks,track+" "+a,z[a],z[b])
        preds.append(z)
        metric=pd.read_csv(folder/("average_metrics_ci.csv" if track=="average_weekday" else "daily_metrics_ci.csv"))
        metrics.append(metric)
    write_csv(pd.concat(cards,ignore_index=True),out/"04_calibration/01_parameter_cards_with_derived_coefficients.csv")
    write_csv(pd.concat(fd_cards,ignore_index=True),out/"04_calibration/02_detector_FD_inputs_and_outcomes.csv")
    write_csv(pd.DataFrame(memberships),out/"04_calibration/03_parameter_fit_episode_membership.csv")
    write_csv(pd.concat(preds,ignore_index=True),out/"04_calibration/04_prediction_calculations_all_episodes.csv")
    write_csv(pd.concat(metrics,ignore_index=True),out/"04_calibration/05_traffic_fit_metrics_and_intervals.csv")


def diagnostic_figures(out: Path, panels: dict, episodes: dict):
    """Editable vector figures derived from the displayed calculation tables."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    blue,teal,amber,text,grid="#2563EB","#168C69","#E69F00","#17324D","#E2E8F0"
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.labelcolor":text,"text.color":text,"xtick.color":text,"ytick.color":text,"axes.edgecolor":grid,"axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":"white","axes.facecolor":"white","svg.fonttype":"none","savefig.facecolor":"white"})

    def save(fig, step):
        fig.savefig(out/step/"diagnostic.svg",bbox_inches="tight")
        fig.savefig(out/step/"diagnostic.png",dpi=180,bbox_inches="tight")
        plt.close(fig)

    support=pd.read_csv(out/"01_inputs/02_baseline_support_by_corridor.csv").sort_values("corridor")
    fig,axes=plt.subplots(1,2,figsize=(11,5.5),layout="constrained")
    names=support.corridor.str.replace("_"," ")
    for ax,column,title in zip(axes,["sensors","profiles"],["Detectors in the prepared baseline","Detector-date/profile records"]):
        ax.barh(names,support[column],color=[amber if v=="AZ_I10_W" else blue for v in support.corridor])
        ax.invert_yaxis();ax.set_xlabel("Count");ax.set_title(title,loc="left",fontweight="bold");ax.set_axisbelow(True);ax.grid(axis="x",color=grid)
        ax.set_xlim(0,support[column].max()*1.20)
        for i,value in enumerate(support[column]):ax.text(value+support[column].max()*.015,i,f"{value:,}",va="center",fontsize=9)
    fig.suptitle("Input support before the daily and average-profile tracks separate",fontsize=13,fontweight="bold")
    fig.supxlabel("Arizona rows represent daily observations; California rows represent released average profiles.",fontsize=10)
    save(fig,"01_inputs")

    sid,month="AZ_I10_W::137","2016-01"
    support=pd.read_csv(out/"02_prepared_profiles/03_arizona_day_support.csv")
    dates=support.loc[support.sensor_uid.eq(sid)&support.month.eq(month)&support.included,"date"]
    raw=panels["daily_validation"]
    raw=raw[raw.sensor_uid.eq(sid)&raw.date.isin(dates)]
    average=pd.read_csv(out/"02_prepared_profiles/05_arizona_monthly_bin_calculations.csv")
    average=average[average.sensor_uid.eq(sid)&average.month.eq(month)].sort_values("minute")
    fig,axes=plt.subplots(2,1,figsize=(10,6.5),sharex=True,layout="constrained")
    for _,g in raw.groupby("date"):
        g=g.sort_values("datetime");hours=g.datetime.dt.hour+g.datetime.dt.minute/60
        axes[0].plot(hours,g.flow_vph,color="#B8C6D5",linewidth=.65,alpha=.65)
        axes[1].plot(hours,g.speed_mph,color="#B8C6D5",linewidth=.65,alpha=.65)
    axes[0].plot(average.minute/60,average.mean_flow_vphpl,color=blue,linewidth=2.3)
    axes[1].plot(average.minute/60,average.harmonic_speed_mph,color=teal,linewidth=2.3)
    for ax,ylabel in zip(axes,["Flow (veh/h/lane)","Speed (mph)"]):
        ax.set_ylabel(ylabel);ax.grid(color=grid,linewidth=.6);ax.set_xlim(0,24);ax.set_xticks(np.arange(0,25,3))
    axes[1].set_xlabel("Hour of day")
    axes[0].legend(handles=[Line2D([0],[0],color="#B8C6D5",label=f"{len(dates)} complete contributing weekdays"),Line2D([0],[0],color=blue,linewidth=2.3,label="Mean flow"),Line2D([0],[0],color=teal,linewidth=2.3,label="Flow-weighted harmonic speed")],loc="upper left",ncol=1,frameon=True,framealpha=.95)
    fig.suptitle("Monthly profile calculation: Arizona I-10 detector 137, January 2016",fontsize=13,fontweight="bold")
    save(fig,"02_prepared_profiles")

    ep=episodes["average_weekday"]
    values=[len(ep),int((~ep.qc_hard_fail).sum()),int(ep.calibration_eligible.sum()),int((ep.calibration_eligible&np.isfinite(ep.P_hat_h)).sum()),int(ep.matched_ladder_pass.sum())]
    fig,axes=plt.subplots(1,2,figsize=(11,4.8),layout="constrained")
    labels=["Detected","Hard QC passed","Outlier rule passed","Fitted parameters","Matched emissions"]
    axes[0].barh(labels,values,color=[blue,blue,blue,blue,teal]);axes[0].invert_yaxis();axes[0].set_xlim(0,365)
    for i,value in enumerate(values):axes[0].text(value+5,i,str(value),va="center")
    axes[0].set_xlabel("Average-profile episodes");axes[0].set_title("Selection to the 137-episode comparison",loc="left",fontweight="bold")
    votes=ep.loc[~ep.qc_hard_fail,"outlier_votes"].value_counts().reindex(range(5),fill_value=0)
    axes[1].bar(votes.index,votes.values,color=[blue,blue,amber,amber,amber]);axes[1].set_xticks(range(5));axes[1].set_xlabel("Number of outlier votes");axes[1].set_ylabel("Episodes passing hard QC")
    axes[1].set_ylim(0,max(votes)*1.16)
    for x,y in votes.items():axes[1].text(x,y+max(votes)*.02,str(y),ha="center")
    axes[1].set_title("At least two votes are required to exclude",loc="left",fontweight="bold")
    for ax in axes:ax.set_axisbelow(True);ax.grid(axis="x" if ax==axes[0] else "y",color=grid)
    fig.suptitle("Episode screening: frozen selection, independently checked target and outlier arithmetic",fontsize=12,fontweight="bold")
    save(fig,"03_episode_detection")

    fig,axes=plt.subplots(2,2,figsize=(10.8,8.0),layout="constrained")
    for ax,target,prediction,label,factor in zip(axes.flat,["P_h","wt2_h","vt2_obs_mph","vq_mph"],["P_hat_h","wt2_hat_h","vt2_hat_mph","vq_hat_mph"],["Episode duration (h)","Peak delay (min)","Minimum whole-link speed (mph)","Congested-state speed (mph)"],[1,60,1,1]):
        eligible=ep.calibration_eligible&np.isfinite(ep[target])&np.isfinite(ep[prediction])
        if target=="vq_mph":eligible&=ep.vq_mph.gt(0)&ep.vq_mph.lt(ep.vf_mph)&ep.vq_hat_mph.gt(0)&ep.vq_hat_mph.lt(ep.vf_mph)
        g=ep[eligible];scores=model.scores(g[target],g[prediction]);a=g[target]*factor;b=g[prediction]*factor
        for matched,color in [(False,amber),(True,teal)]:
            m=g.matched_ladder_pass.eq(matched);ax.scatter(a[m],b[m],s=15,color=color,alpha=.68,edgecolors="none")
        maximum=max(float(a.max()),float(b.max()))*1.04
        ax.plot([0,maximum],[0,maximum],color="#64748B",linestyle="--",linewidth=1)
        ax.set_xlim(0,maximum);ax.set_ylim(0,maximum);ax.set_aspect("equal",adjustable="box");ax.grid(color=grid,linewidth=.5);ax.set_axisbelow(True)
        ax.set_xlabel("Observed "+label[0].lower()+label[1:]);ax.set_ylabel("Predicted "+label[0].lower()+label[1:]);ax.set_title(f"N = {len(g)}; pooled R² = {scores['R2']:.3f}",loc="left",fontsize=11)
    fig.suptitle("Traffic calibration: eligible finite pairs before emission admission",fontsize=13,fontweight="bold")
    fig.legend(handles=[Line2D([0],[0],marker="o",linestyle="",color=teal,label="Retained for matched emissions"),Line2D([0],[0],marker="o",linestyle="",color=amber,label="Traffic pair outside emission subset"),Line2D([0],[0],color="#64748B",linestyle="--",label="Equality")],loc="outside lower center",ncol=3,frameon=False)
    save(fig,"04_calibration")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",help="empty directory, or an existing output owned by this generator")
    args=parser.parse_args();out=safe_output(args.output)
    checks=[]
    inputs(out)
    panels={track:pd.read_csv(DATA/track/"traffic_panel.csv.gz",parse_dates=["datetime"],low_memory=False) for track in TRACKS}
    for panel in panels.values():panel["date"]=panel.datetime.dt.strftime("%Y-%m-%d")
    episodes={track:pd.read_csv(DATA/track/"episode_results_v2.csv",low_memory=False) for track in TRACKS}
    profiles(out,panels,episodes,checks)
    screening(out,panels,episodes,checks)
    fit_trace(out,episodes,checks)
    diagnostic_figures(out,panels,episodes)
    result=pd.DataFrame(checks)
    write_csv(result,out/"04_calibration/06_trace_reconciliation.csv")
    failures=int(result.failures.sum())
    print(json.dumps({"checks":len(result),"failures":failures,"average_episodes":len(episodes["average_weekday"]),"daily_episodes":len(episodes["daily_validation"]),"output":str(out)},indent=2))
    if failures:raise SystemExit("Trace reconciliation failed; inspect 06_trace_reconciliation.csv")


if __name__=="__main__":main()
