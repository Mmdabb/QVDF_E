"""Exploratory capacity diagnostics; frozen experiment inputs stay read-only.

The fixed-traffic comparison is an in-sample conditional emission optimization.
The capacity sweep is a mechanical sensitivity, not a new calibrated experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / 'debug/full_experiment/scripts'
FROZEN = ROOT / 'data/frozen/calibration/average_weekday'
PUBLISHED = ROOT / 'debug/full_experiment/steps/11_episode_time_series'
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(ROOT / 'src'))
import build_inverse_queue_speed as inverse
import build_fd_parameter_sensitivity as fd_tools
from qvdfe.pipeline._engine.model import profile_grid

POLS = inverse.POLS
MULTIPLIERS = (.8, 1., 1.1, 1.25, 1.5, 2.)
STRATEGIES = ('co2_target', 'balanced_four_pollutants')


def safe_output(path):
    out = Path(path).resolve()
    root, working = ROOT.resolve(), (ROOT / 'debug/output').resolve()
    if root.is_relative_to(out) or (out.is_relative_to(root) and not out.is_relative_to(working)):
        raise ValueError('Use debug/output or an external working directory, separate from reference files.')
    marker = out / '.capacity-sensitivity.json'
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not marker.is_file())):
        raise ValueError('Choose an empty directory or one owned by this generator.')
    out.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"owner":"capacity-sensitivity"}\n', encoding='utf-8')
    return out


def save(frame, out, name):
    frame.to_csv(out / name, index=False, lineterminator='\n')


def fixed_capacity_interval(mu, vf, capacity, physical_max, wave_min):
    """Exact q image of the fixed-C FD curve inside the exploratory rectangle."""
    if not (0 < mu < capacity and fd_tools.K_MAX > capacity/vf):
        return None
    lo = max(wave_min, capacity/(fd_tools.K_MAX-capacity/vf))
    hi = fd_tools.W_MAX
    if fd_tools.K_MIN > capacity/vf:
        hi = min(hi, capacity/(fd_tools.K_MIN-capacity/vf))
    if lo > hi:
        return None
    q = lambda w: mu/(capacity/vf+(capacity-mu)/w)
    qlo, qhi = q(lo), min(q(hi), physical_max)
    if qlo > qhi:
        return None
    return float(qlo), float(qhi)


def objective(emissions, observed, strategy):
    errors = emissions/observed-1
    return float(abs(errors[0]) if strategy == 'co2_target' else np.mean(errors**2))


def metrics(observed, predicted):
    observed, predicted = np.asarray(observed, float), np.asarray(predicted, float)
    assert np.isfinite(observed).all() and np.isfinite(predicted).all()
    error = predicted-observed
    denominator = np.sum((observed-observed.mean())**2) if len(observed) else 0
    return dict(N=len(observed), observed_total=float(observed.sum()), predicted_total=float(predicted.sum()),
                WAPE_pct=float(100*np.abs(error).sum()/np.abs(observed).sum()) if len(observed) else np.nan,
                bias_pct=float(100*error.sum()/observed.sum()) if len(observed) else np.nan,
                R2=float(1-np.sum(error**2)/denominator) if denominator > 0 else np.nan,
                RMSE=float(np.sqrt(np.mean(error**2))) if len(observed) else np.nan)


def fixed_traffic(episodes, rates):
    records = []
    for wave_min in (5., 3.):
        bounds = 'primary_omega_5_20' if wave_min == 5 else 'expanded_omega_3_20'
        for r in episodes.itertuples(index=False):
            mu, vf, C = r.mu_hat_vphpl, r.vf_mph, r.C_vphpl
            qmax = r.L_mi/(r.Tf_h+r.wt2_hat_h)
            observed = np.array([getattr(r, 'O_'+p) for p in POLS])
            for strategy in STRATEGIES:
                for policy in ('strict_baseline_capacity', 'free_capacity'):
                    interval = (fixed_capacity_interval(mu, vf, C, qmax, wave_min)
                                if policy == 'strict_baseline_capacity' else
                                fd_tools.attainable_queue_interval(mu, vf, qmax, wave_min))
                    record = dict(case_id=r.case_id, episode_id=r.episode_id, sensor_uid=r.sensor_uid,
                                  corridor=r.corridor, date=r.date, period=r.period, bounds_profile=bounds,
                                  strategy=strategy, capacity_policy=policy, valid=interval is not None,
                                  objective_name=('CO2_absolute_relative_error' if strategy=='co2_target' else 'mean_squared_relative_error_four_pollutants'),
                                  status='no_physical_pair_at_fixed_capacity' if interval is None else 'solved',
                                  baseline_C_vphpl=C, baseline_q_mph=r.vq_hat_mph, baseline_mu_vphpl=mu,
                                  physical_q_max_mph=qmax, wave_lower_mph=wave_min, wave_upper_mph=20.,
                                  kj_lower_veh_mi_lane=150., kj_upper_veh_mi_lane=300.)
                    for p in POLS:
                        record['O_'+p+'_g'] = getattr(r, 'O_'+p)
                        record['baseline_M_'+p+'_g'] = getattr(r, 'M_'+p)
                    if interval is not None:
                        solution = inverse.solve_restricted_interval(r, strategy, *interval, rates=rates)
                        desired_q = solution['q_inverse_mph']
                        pair = fd_tools.choose_pair(mu, vf, C, desired_q, r.omega_mph, wave_min)
                        assert pair is not None
                        pair, emissions = fd_tools.stable_pair(pair, r, desired_q, qmax, wave_min, rates, inverse)
                        if policy == 'strict_baseline_capacity':
                            np.testing.assert_allclose(pair['selected_implied_capacity_vphpl'], C, rtol=1e-10, atol=1e-8)
                        record.update(q_min_mph=interval[0], q_max_mph=interval[1],
                                      selected_q_mph=pair['selected_queue_speed_mph'],
                                      selected_kj_veh_mi_lane=pair['selected_kj_veh_mi_lane'],
                                      selected_omega_mph=pair['selected_omega_mph'],
                                      selected_C_vphpl=pair['selected_implied_capacity_vphpl'],
                                      capacity_change_pct=pair['capacity_change_pct'],
                                      capacity_preserved=pair['baseline_capacity_preserved'],
                                      objective_value=objective(emissions, observed, strategy),
                                      objective_infimum=solution['objective_infimum'],
                                      solution_status=solution['solution_status'], limit_attained=solution['limit_attained'])
                        np.testing.assert_allclose(record['objective_value'], solution['objective_value'],rtol=1e-7,atol=1e-10)
                        for p, value in zip(POLS, emissions):
                            record['M_'+p+'_g'] = float(value)
                            record[p+'_error_pct'] = float(100*(value/getattr(r, 'O_'+p)-1))
                    records.append(record)
    table = pd.DataFrame(records)
    group = ['bounds_profile', 'strategy', 'episode_id']
    strict = table[table.capacity_policy.eq('strict_baseline_capacity')].set_index(group)
    free = table[table.capacity_policy.eq('free_capacity')].set_index(group)
    assert free.valid.all()
    joint = strict.valid & free.valid
    assert (free.loc[joint, 'objective_infimum'] <= strict.loc[joint, 'objective_infimum'] + 1e-10).all()
    table['jointly_feasible_strict_and_free'] = [bool(joint.loc[tuple(r[k] for k in group)]) for r in table.to_dict('records')]
    rows = []
    for (bounds, strategy), g in table.groupby(['bounds_profile', 'strategy']):
        for cohort in ('available_valid', 'paired_strict_free'):
            for policy, z in g.groupby('capacity_policy'):
                z = z[z.valid & (z.jointly_feasible_strict_and_free if cohort == 'paired_strict_free' else True)]
                for p in POLS:
                    for method in ('baseline_M', 'M'):
                        rows.append(dict(bounds_profile=bounds, strategy=strategy, capacity_policy=policy,
                                         cohort=cohort, method=method, pollutant=p,
                                         **metrics(z['O_'+p+'_g'], z[method+'_'+p+'_g'])))
    return table, pd.DataFrame(rows)


def sweep(episodes, rates):
    records = []
    for r in episodes.itertuples(index=False):
        for scenario, C in [(f'multiplier_{m:g}', r.C_vphpl*m) for m in MULTIPLIERS] + [('metadata_capacity', r.metadata_capacity_vphpl)]:
            for policy in ('frozen_coefficients', 'fd_rescaled'):
                row = dict(case_id=r.case_id, episode_id=r.episode_id, sensor_uid=r.sensor_uid,
                           corridor=r.corridor, date=r.date, period=r.period, scenario=scenario,
                           coefficient_policy=policy, baseline_C_vphpl=r.C_vphpl, selected_C_vphpl=C,
                           capacity_multiplier=C/r.C_vphpl, vf_mph=r.vf_mph, kj_veh_mi_lane=220.,
                           D_veh=r.D_veh, Tf_h=r.Tf_h, fd_baseline=r.fd, n=r.n, fp=r.fp, s=r.s, theta=r.theta,
                           baseline_P_h=r.P_hat_h, baseline_peak_delay_h=r.wt2_hat_h,
                           baseline_mean_delay_h=r.wbar_hat_h, baseline_mu_vphpl=r.mu_hat_vphpl,
                           baseline_q_mph=r.vq_hat_mph, observed_P_h=r.P_h,
                           observed_peak_delay_h=r.wt2_h, observed_mean_delay_h=r.wbar_h,
                           observed_trip_time_h=r.Tf_h+r.wbar_h,
                           gauge_common_parameter_card=(scenario != 'metadata_capacity'),
                           metadata_available=bool(r.metadata_capacity_available),
                           inherited_capacity_range_500_3500_pass=bool(np.isfinite(C) and 500<=C<=3500))
                for p in POLS:
                    row['O_'+p+'_g'] = getattr(r, 'O_'+p)
                    row['baseline_M_'+p+'_g'] = getattr(r, 'M_'+p)
                reasons = []
                if not np.isfinite(C):
                    reasons.append('metadata_capacity_unavailable')
                elif not 0 < C < r.vf_mph*220.:
                    reasons.append('capacity_outside_triangular_domain')
                if not reasons:
                    ratio = C/r.C_vphpl
                    fd = r.fd*ratio**r.n if policy == 'fd_rescaled' else r.fd
                    x = r.D_veh/C
                    power = fd*x**r.n
                    P = max(power, x)
                    peak = r.Tf_h*r.fp*P**r.s
                    mean = r.theta*peak
                    mu = r.D_veh/P
                    omega = C/(220.-C/r.vf_mph)
                    kq = 220.-mu/omega
                    q = mu/kq if kq > 0 else np.nan
                    qmax = r.L_mi/(r.Tf_h+peak)
                    _, _, _, _, _, closure, arrival_min = profile_grid(P, peak, r.theta)
                    fd_valid = bool(0 < mu < C and kq > 0 and 0 < q < r.vf_mph)
                    physical = bool(fd_valid and q <= qmax + 8*np.spacing(qmax))
                    if not fd_valid: reasons.append('not_strictly_congested_fd_state')
                    if not physical: reasons.append('negative_peak_free_time_or_invalid_fd')
                    if not closure: reasons.append('negative_profile_arrival_rate')
                    tf_peak = r.Tf_h-q*peak/(r.vf_mph-q) if fd_valid else np.nan
                    row.update(fd_used=fd, x_h=x, power_duration_h=power, lower_branch=bool(x > power),
                               P_h=P, peak_delay_h=peak, mean_delay_h=mean, trip_time_h=r.Tf_h+mean,
                               mu_vphpl=mu, omega_mph=omega, kq_veh_mi_lane=kq, q_mph=q,
                               physical_q_max_mph=qmax, minimum_peak_free_time_h=tf_peak,
                               fd_domain_valid=fd_valid, finite_link_valid=physical,
                               cubic_speed_domain_5_75_pass=bool(5<=q<r.vf_mph<=75),
                               profile_closure_valid=closure, minimum_relative_arrival_rate=arrival_min,
                               duration_closure_error_veh=mu*P-r.D_veh,
                               power_branch_gauge_eligible=bool(policy == 'fd_rescaled' and power >= x),
                               P_change_pct=100*(P/r.P_hat_h-1), peak_delay_change_pct=100*(peak/r.wt2_hat_h-1),
                               mean_delay_change_pct=100*(mean/r.wbar_hat_h-1), mu_change_pct=100*(mu/r.mu_hat_vphpl-1))
                    if not reasons:
                        modified = r._replace(wbar_hat_h=mean, wt2_hat_h=peak)
                        emissions = inverse.emissions_at_speed(modified, min(q,qmax), rates)
                        for p, value in zip(POLS, emissions):
                            row['M_'+p+'_g'] = float(value)
                            row[p+'_error_pct'] = float(100*(value/getattr(r, 'O_'+p)-1))
                    if policy == 'fd_rescaled' and power >= x:
                        np.testing.assert_allclose([P, peak, mean, mu],
                                                   [r.P_hat_h, r.wt2_hat_h, r.wbar_hat_h, r.mu_hat_vphpl],
                                                   rtol=1e-11, atol=1e-11)
                row['valid'] = not reasons
                row['invalid_reason'] = ';'.join(reasons)
                records.append(row)
    table = pd.DataFrame(records)
    baseline = table[table.scenario.eq('multiplier_1')]
    assert baseline.valid.all()
    for p in POLS:
        np.testing.assert_allclose(baseline['M_'+p+'_g'], baseline['baseline_M_'+p+'_g'], rtol=1e-9, atol=1e-8)
    common = table[~table.scenario.eq('metadata_capacity')].groupby('episode_id').valid.all()
    common_increase = table[table.scenario.isin([f'multiplier_{m:g}' for m in MULTIPLIERS if m>=1])].groupby('episode_id').valid.all()
    common_meta = table.groupby('episode_id').valid.all()
    table['common_all_multiplier_scenarios'] = table.episode_id.map(common)
    table['common_capacity_increase_scenarios'] = table.episode_id.map(common_increase)
    table['common_all_including_metadata'] = table.episode_id.map(common_meta)
    rows = []
    for (policy, scenario), g in table.groupby(['coefficient_policy', 'scenario']):
        for cohort in ('available_valid', 'common_capacity_increases', 'common_all_multipliers', 'common_including_metadata'):
            mask = g.valid.copy()
            if cohort == 'common_capacity_increases': mask &= g.common_capacity_increase_scenarios
            if cohort == 'common_all_multipliers': mask &= g.common_all_multiplier_scenarios
            if cohort == 'common_including_metadata': mask &= g.common_all_including_metadata
            z = g[mask]
            for quantity, obs, fit, base in [
                    *[(p, 'O_'+p+'_g', 'M_'+p+'_g', 'baseline_M_'+p+'_g') for p in POLS],
                    ('duration', 'observed_P_h', 'P_h', 'baseline_P_h'),
                    ('peak_delay', 'observed_peak_delay_h', 'peak_delay_h', 'baseline_peak_delay_h'),
                    ('mean_delay', 'observed_mean_delay_h', 'mean_delay_h', 'baseline_mean_delay_h')]:
                for method, prediction in [('sensitivity', fit), ('baseline_same_rows', base)]:
                    rows.append(dict(coefficient_policy=policy, scenario=scenario, cohort=cohort,
                                     quantity=quantity, method=method, original_cohort_N=len(g),
                                     valid_N=int(g.valid.sum()), invalid_N=int((~g.valid).sum()),
                                     **metrics(z[obs], z[prediction])))
    return table, pd.DataFrame(rows)


def capacity_audit(episodes):
    sensor = pd.read_csv(FROZEN/'sensor_parameters.csv')
    fd = pd.read_csv(FROZEN/'detector_fd_calibration.csv')
    panel = pd.read_csv(FROZEN/'traffic_panel.csv.gz', low_memory=False)
    metadata = pd.read_csv(ROOT/'data/inputs/empirical/source_files/pems/pems_link_meta.csv')
    meta = metadata.set_index(['corridor','link_id'])
    counts = episodes.groupby('sensor_uid').size()
    rows = []
    for r in sensor.itertuples(index=False):
        z = panel[panel.sensor_uid.eq(r.sensor_uid)]
        valid = (np.isfinite(z.speed_mph)&z.speed_mph.gt(0)&z.speed_mph.le(90)&
                 np.isfinite(z.flow_vph)&z.flow_vph.gt(0)&~z.holdout.astype(bool))
        q = z.loc[valid, 'flow_vph']
        f = fd[fd.sensor_uid.eq(r.sensor_uid)].iloc[0]
        key = (r.corridor, str(r.sensor))
        md = meta.loc[key] if key in meta.index else None
        mC = float(md.network_capacity_vph/md.lanes) if md is not None else np.nan
        q995 = float(q.quantile(.995))
        row = dict(sensor_uid=r.sensor_uid, corridor=r.corridor, dataset=r.dataset,
                   retained_emission_episodes=int(counts.get(r.sensor_uid,0)), represented_in_137=r.sensor_uid in counts,
                   C_vphpl=r.C_vphpl, vf_mph=r.vf_mph, kj_veh_mi_lane=r.kj, omega_mph=r.omega_mph,
                   capacity_source=r.capacity_source, fd_fit_accepted=bool(r.fd_fit_accepted),
                   fd_fallback_reason=r.fd_fallback_reason, profile_positive_pairs=len(q),
                   profile_q95_vphpl=float(q.quantile(.95)), profile_q995_vphpl=q995,
                   profile_max_flow_vphpl=float(q.max()), C_over_profile_q995=r.C_vphpl/q995,
                   profile_share_above_C=float(q.gt(r.C_vphpl).mean()),
                   pre_S3_C_vphpl=f.old_C_vphpl, C_over_pre_S3_C=r.C_vphpl/f.old_C_vphpl,
                   flow_r2=f.flow_r2, speed_r2=f.speed_r2,
                   free_branch_pairs=f.n_free_branch, congested_branch_pairs=f.n_congested_branch,
                   fit_scope=f.fit_scope, metadata_capacity_vphpl=mC,
                   metadata_capacity_available=md is not None, C_over_metadata_capacity=r.C_vphpl/mC,
                   metadata_daily_q995_reported_vph=float(md.daily_p995_flow_vph) if md is not None else np.nan,
                   metadata_lane_count=float(md.lanes) if md is not None else np.nan,
                   source_lane_count=r.lanes,
                   capacity_warning_outside_500_3500=not 500<=r.C_vphpl<=3500)
        rows.append(row)
    audit = pd.DataFrame(rows)
    summaries = []
    for label, g in [('all_352_detectors',audit), ('104_detectors_in_137',audit[audit.represented_in_137])]:
        for corridor, z in [('ALL',g), *list(g.groupby('corridor'))]:
            summaries.append(dict(cohort=label,corridor=corridor,N=len(z),
                                  accepted_S3=int(z.fd_fit_accepted.sum()),metadata_available=int(z.metadata_capacity_available.sum()),
                                  C_min=float(z.C_vphpl.min()),C_median=float(z.C_vphpl.median()),C_max=float(z.C_vphpl.max()),
                                  median_C_over_profile_q995=float(z.C_over_profile_q995.median()),
                                  median_C_over_metadata=float(z.C_over_metadata_capacity.median()),
                                  median_profile_share_above_C=float(z.profile_share_above_C.median()),
                                  median_flow_R2=float(z.flow_r2.median()),median_speed_R2=float(z.speed_r2.median()),
                                  capacities_below_1000=int(z.C_vphpl.lt(1000).sum()),
                                  capacities_outside_500_3500=int(z.capacity_warning_outside_500_3500.sum())))
    return audit, pd.DataFrame(summaries)


def build(out):
    out = safe_output(out)
    episode_source = FROZEN/'episode_results_v2.csv'
    ep = pd.read_csv(episode_source, float_precision='round_trip')
    ep = ep[ep.matched_ladder_pass].copy()
    extra = pd.read_csv(PUBLISHED/'traffic_parameters.csv', float_precision='round_trip')
    ep = ep.merge(extra[['episode_id','case_id','metadata_capacity_vphpl','metadata_capacity_available']],
                  on='episode_id',validate='one_to_one')
    assert len(ep) == 137
    rates = inverse.canonical_rates()
    fixed, fixed_metrics = fixed_traffic(ep, rates)
    sweep_table, sweep_metrics = sweep(ep, rates)
    audit, audit_summary = capacity_audit(ep)
    for table, name in [(fixed,'fixed_traffic_comparison.csv'),(fixed_metrics,'fixed_traffic_metrics.csv'),
                        (sweep_table,'capacity_sweep.csv'),(sweep_metrics,'capacity_sweep_metrics.csv'),
                        (audit,'detector_capacity_audit.csv'),(audit_summary,'detector_capacity_summary.csv')]:
        save(table,out,name)
    comparisons = []
    for bounds, name in [('primary_omega_5_20','fd_parameter_sensitivity.csv'),
                         ('expanded_omega_3_20','fd_parameter_sensitivity_expanded.csv')]:
        old = pd.read_csv(PUBLISHED/name)
        new = fixed[fixed.capacity_policy.eq('free_capacity')&fixed.bounds_profile.eq(bounds)]
        both = new.merge(old,on=['episode_id','strategy'],validate='one_to_one',suffixes=('_new','_old'))
        np.testing.assert_allclose(both.objective_infimum, both.selected_objective_infimum,rtol=1e-8,atol=1e-10)
        comparisons.append(dict(bounds_profile=bounds,rows=len(both),
                                max_free_objective_difference_from_previous=float(abs(both.objective_infimum-both.selected_objective_infimum).max())))
    policies = fixed.groupby(['bounds_profile','strategy','capacity_policy']).agg(
        N=('episode_id','size'),feasible=('valid','sum')).reset_index()
    gauge = sweep_table[sweep_table.power_branch_gauge_eligible.fillna(False)]
    verification = dict(status='pass',episodes=137,fixed_traffic_rows=len(fixed),sweep_rows=len(sweep_table),
                        detector_rows=len(audit),baseline_emissions_reproduced=True,
                        free_objective_no_worse_than_strict_on_common_rows=True,
                        previous_free_capacity_result_comparison=comparisons,
                        gauge_rows_checked=len(gauge),
                        maximum_gauge_P_change_pct=float(gauge.P_change_pct.abs().max()),
                        maximum_duration_closure_error_veh=float(sweep_table.duration_closure_error_veh.abs().max()),
                        input_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in [episode_source,FROZEN/'sensor_parameters.csv',FROZEN/'detector_fd_calibration.csv',
                                                FROZEN/'traffic_panel.csv.gz',PUBLISHED/'traffic_parameters.csv']})
    summary = dict(fixed_traffic_feasibility=policies.to_dict('records'),
                   capacity_audit=audit_summary[audit_summary.corridor.eq('ALL')].to_dict('records'),
                   sweep_invalid=sweep_table.groupby(['coefficient_policy','scenario','invalid_reason'],dropna=False).size().rename('N').reset_index().to_dict('records'),
                   common_all_multiplier_episodes=int(sweep_table.groupby('episode_id').common_all_multiplier_scenarios.first().sum()),
                   common_capacity_increase_episodes=int(sweep_table.groupby('episode_id').common_capacity_increase_scenarios.first().sum()),
                   common_including_metadata_episodes=int(sweep_table.groupby('episode_id').common_all_including_metadata.first().sum()),
                   assumptions={'FD_box':'exploratory kj 150–300 veh/mi/lane; omega 5–20 mph primary, 3–20 mph secondary',
                                'fixed_traffic':'same D, vf, P, delay, mu; only FD queue speed and its two-state allocation change',
                                'sweep':'same 137 selected episodes; no episode detection or calibration rerun; vf and kj=220 fixed',
                                'fd_rescaling':'fd_new=fd*(C_new/C_old)^n, only a valid common card for a common multiplier within a fit group',
                                'metadata_rescaling':'row-level algebraic control; detector-varying ratios are not a common calibrated parameter card',
                                'emission_reference':'O is the observed point-speed emission proxy, not measured trajectory emissions',
                                'optimization':'conditional in-sample error minimization, not independent predictive validation'})
    (out/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
    (out/'analysis_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({**{k:v for k,v in verification.items() if k!='input_sha256'},'feasibility':policies.to_dict('records')},indent=2))
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'debug/output/capacity_sensitivity')
    build(parser.parse_args().output)
