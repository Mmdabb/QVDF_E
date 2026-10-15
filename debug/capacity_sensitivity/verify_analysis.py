"""Read-only independent audit of the capacity sensitivity CSVs.

Uses numpy/pandas and frozen input tables only; imports no result generator or
QVDF-E calculation functions. Reconstructs rates, traffic, physical flags,
piecewise emission objective minima, and pooled metrics. Never writes data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / 'data/frozen/calibration/average_weekday'
PUBLISHED = ROOT / 'debug/full_experiment/steps/11_episode_time_series'
POLS = ('CO2', 'NOx', 'CO', 'HC')
CHECKS = 0


def require(condition, message):
    global CHECKS
    CHECKS += 1
    if not bool(np.all(condition)):
        raise AssertionError(message)


def close(actual, expected, message, rtol=1e-9, atol=1e-8):
    global CHECKS
    CHECKS += 1
    np.testing.assert_allclose(actual, expected, rtol=rtol, atol=atol,
                               equal_nan=True, err_msg=message)


def read(path):
    return pd.read_csv(path, float_precision='round_trip', low_memory=False)


class IndependentRates:
    def __init__(self):
        source = ROOT / 'data/frozen/calibration/emission_input'
        vehicle = read(source/'input_vehicle_type.csv')
        self.vehicle = vehicle[vehicle.vehicle_type.eq(1)].iloc[0]
        weights = {int(k.removeprefix('percentage_of_age_')): float(v)
                   for k, v in self.vehicle.items() if k.startswith('percentage_of_age_')}
        weight_sum = sum(weights.values())
        raw = read(source/'input_vehicle_emission_rate.csv')
        raw = raw[raw.vehicle_type.eq(1)].copy()
        raw['weight'] = raw.age.map(weights)/weight_sum
        names = ('CO2', 'NOX', 'CO', 'HC')
        self.rates = {int(mode): np.array([
            (g[f'meanBaseRate_{p}_(g/hr)']*g.weight).sum() for p in names])
            for mode, g in raw.groupby('OpModeID')}
        self.cuts = sorted(set([25., 50.] + [
            self.vsp_root(t) for t in (3., 6., 9., 12., 18., 24., 30.)]))

    def vsp(self, speed):
        u = speed*0.44704
        v = self.vehicle
        return (v.rolling_term_a*u+v.rotating_term_b*u*u+v.drag_term_c*u**3)/v.source_mass

    def vsp_root(self, target):
        lo, hi = 0., 150.
        for _ in range(100):
            mid = (lo+hi)/2
            if self.vsp(mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo+hi)/2

    def __call__(self, speed):
        vsp = self.vsp(speed)
        if speed <= 0:
            mode = 1
        elif speed < 25:
            mode = (11, 12, 13, 14, 15, 16)[np.searchsorted([0, 3, 6, 9, 12], vsp, side='right')]
        elif speed < 50:
            mode = (21, 22, 23, 24, 25, 27, 28, 29, 30)[np.searchsorted([0, 3, 6, 9, 12, 18, 24, 30], vsp, side='right')]
        else:
            mode = (33, 35, 37, 38, 39, 40)[np.searchsorted([6, 12, 18, 24, 30], vsp, side='right')]
        return self.rates[mode]


def emissions(ep, q, mean, rates):
    tq = ep.vf_mph*mean/(ep.vf_mph-q)
    tf = ep.Tf_h-q*mean/(ep.vf_mph-q)
    return ep.D_veh*(tf*rates(ep.vf_mph)+tq*rates(q))


def objective(predicted, observed, strategy):
    relative = predicted/observed-1
    return abs(relative[0]) if strategy == 'co2_target' else np.mean(relative**2)


def independent_infimum(ep, lower, upper, strategy, rates):
    """Enumerate exact constant-rate intervals; do not grid or interpolate jumps."""
    O = np.array([ep['O_'+p] for p in POLS])
    rf = rates(ep.vf_mph)
    A = ep.D_veh*(ep.Tf_h+ep.wbar_hat_h)*rf
    a = A/O-1
    cuts = [lower]+[q for q in rates.cuts if lower < q < upper]+[upper]
    values = [objective(emissions(ep, q, ep.wbar_hat_h, rates), O, strategy)
              for q in (lower, upper)]
    for lo, hi in zip(cuts[:-1], cuts[1:]):
        B = ep.D_veh*ep.vf_mph*ep.wbar_hat_h*(rates((lo+hi)/2)-rf)
        b = B/O
        zs = [1/(ep.vf_mph-lo), 1/(ep.vf_mph-hi)]
        if strategy == 'co2_target':
            if b[0] != 0:
                zs.append(float(np.clip(-a[0]/b[0], *zs)))
        elif np.dot(b, b) > 0:
            zs.append(float(np.clip(-np.dot(a, b)/np.dot(b, b), *zs)))
        for z in zs:
            relative = a+b*z
            values.append(abs(relative[0]) if strategy == 'co2_target' else np.mean(relative**2))
    return min(values)


def interval(ep, policy, wave_min):
    mu, C, vf = ep.mu_hat_vphpl, ep.C_vphpl, ep.vf_mph
    physical = ep.L_mi/(ep.Tf_h+ep.wt2_hat_h)
    if policy == 'strict_baseline_capacity':
        if not 0 < mu < C or 300 <= C/vf:
            return None
        lo = max(wave_min, C/(300-C/vf))
        hi = min(20., C/(150-C/vf)) if 150 > C/vf else 20.
        if lo > hi:
            return None
        qlo = mu/(C/vf+(C-mu)/lo)
        qhi = min(mu/(C/vf+(C-mu)/hi), physical)
    else:
        if 300 <= mu/20.:
            return None
        qlo = mu/(300-mu/20.)
        den = 150-mu/wave_min
        qhi = min(mu/den if den > 0 else np.inf, physical, np.nextafter(vf, 0.))
    return None if qlo > qhi+1e-10 else (min(qlo, qhi), qhi)


def verify_fixed(table, ep, rates):
    require(len(table) == 1096, '137 episodes x 2 bounds x 2 strategies x 2 policies')
    keys = ['episode_id', 'bounds_profile', 'strategy', 'capacity_policy']
    require(not table.duplicated(keys).any(), 'Unique fixed-traffic rows')
    for r in table.itertuples(index=False):
        e = ep.loc[r.episode_id]
        domain = interval(e, r.capacity_policy, r.wave_lower_mph)
        require(r.valid == (domain is not None), f'{r.case_id}: strict/free feasibility')
        close([r.baseline_C_vphpl, r.baseline_q_mph, r.baseline_mu_vphpl],
              [e.C_vphpl, e.vq_hat_mph, e.mu_hat_vphpl], 'Frozen fixed-traffic inputs')
        for p in POLS:
            close([getattr(r, 'O_'+p+'_g'), getattr(r, 'baseline_M_'+p+'_g')],
                  [e['O_'+p], e['M_'+p]], 'Frozen emission inputs')
        if domain is None:
            require(pd.isna(r.selected_q_mph) and pd.isna(r.objective_value), 'Infeasible row is retained without a fabricated solution')
            continue
        close([r.q_min_mph, r.q_max_mph], domain, 'Exact strict/free speed interval')
        q, k, w, mu = r.selected_q_mph, r.selected_kj_veh_mi_lane, r.selected_omega_mph, e.mu_hat_vphpl
        require(domain[0]-1e-9 <= q <= domain[1]+1e-9, 'Selected q inside physical interval')
        require(150-1e-8 <= k <= 300+1e-8 and r.wave_lower_mph-1e-8 <= w <= 20+1e-8, 'Selected FD bounds')
        close(q, mu/(k-mu/w), 'FD reconstructed queue speed')
        close(r.selected_C_vphpl, k*e.vf_mph*w/(e.vf_mph+w), 'Implied triangular capacity')
        close(r.capacity_change_pct, 100*(r.selected_C_vphpl/e.C_vphpl-1), 'Capacity change percentage')
        if r.capacity_policy == 'strict_baseline_capacity':
            close(r.selected_C_vphpl, e.C_vphpl, 'Strict capacity preservation')
        predicted = emissions(e, q, e.wbar_hat_h, rates)
        O = np.array([e['O_'+p] for p in POLS])
        close([getattr(r, 'M_'+p+'_g') for p in POLS], predicted, 'Selected fixed-traffic emissions')
        close([getattr(r, p+'_error_pct') for p in POLS], 100*(predicted/O-1), 'Selected pollutant errors')
        close(r.objective_value, objective(predicted, O, r.strategy), 'Objective units and actual value', atol=1e-10)
        optimum = independent_infimum(e, *domain, r.strategy, rates)
        close(r.objective_infimum, optimum, 'Independent rate-band global infimum', atol=2e-9)
        require(r.objective_value >= optimum-2e-9 and r.objective_value <= optimum+2e-8, 'Selected actual speed approximates global infimum')
    idx = ['bounds_profile', 'strategy', 'episode_id']
    strict = table[table.capacity_policy.eq('strict_baseline_capacity')].set_index(idx)
    free = table[table.capacity_policy.eq('free_capacity')].set_index(idx)
    paired = strict.valid & free.valid
    require((free.loc[paired, 'objective_infimum'] <= strict.loc[paired, 'objective_infimum']+2e-9).all(), 'Free-C objective no worse on paired feasible rows')
    for r in table.itertuples(index=False):
        require(r.jointly_feasible_strict_and_free == paired.loc[(r.bounds_profile, r.strategy, r.episode_id)], 'Paired cohort flag')
    for bounds, filename in [('primary_omega_5_20', 'fd_parameter_sensitivity.csv'), ('expanded_omega_3_20', 'fd_parameter_sensitivity_expanded.csv')]:
        old = read(PUBLISHED/filename).set_index(['episode_id', 'strategy'])
        new = table[table.capacity_policy.eq('free_capacity') & table.bounds_profile.eq(bounds)].set_index(['episode_id', 'strategy']).loc[old.index]
        close(new.objective_infimum, old.selected_objective_infimum, 'Free-C optimum reconciles prior published sensitivity', atol=2e-9)
        close(new.objective_value, old.selected_objective_value, 'Free-C actual objective reconciles prior published sensitivity', atol=2e-8)


def maximum_profile_slope(ep):
    a = ep.profile_shape_a
    if ep.theta > 2/3:
        close(a, ep.theta/(1-ep.theta), 'Flat-top shape parameter', atol=1e-10)
        return 2*a
    if abs(a-1) < 1e-9:
        return 4.
    u = (1-1/np.sqrt(2*a-1))/2
    return a*4*(1-2*u)*(4*u*(1-u))**(a-1)


def verify_sweep(table, ep, rates):
    require(len(table) == 1918, '137 episodes x 7 capacity scenarios x 2 coefficient policies')
    require(not table.duplicated(['episode_id', 'scenario', 'coefficient_policy']).any(), 'Unique sweep rows')
    metadata = read(PUBLISHED/'traffic_parameters.csv').set_index('episode_id')
    for r in table.itertuples(index=False):
        e = ep.loc[r.episode_id]
        C = (metadata.loc[r.episode_id, 'metadata_capacity_vphpl'] if r.scenario == 'metadata_capacity'
             else e.C_vphpl*float(r.scenario.removeprefix('multiplier_')))
        close(r.selected_C_vphpl, C, 'Scenario capacity source')
        close([r.baseline_C_vphpl, r.baseline_P_h, r.baseline_peak_delay_h, r.baseline_mean_delay_h, r.baseline_mu_vphpl],
              [e.C_vphpl, e.P_hat_h, e.wt2_hat_h, e.wbar_hat_h, e.mu_hat_vphpl], 'Frozen sweep traffic inputs')
        for p in POLS:
            close([getattr(r, 'O_'+p+'_g'), getattr(r, 'baseline_M_'+p+'_g')], [e['O_'+p], e['M_'+p]], 'Frozen sweep emissions')
        require(r.gauge_common_parameter_card == (r.scenario != 'metadata_capacity'), 'Common-card versus per-row control label')
        require(r.inherited_capacity_range_500_3500_pass == (np.isfinite(C) and 500 <= C <= 3500), 'Inherited capacity-screen flag')
        if not np.isfinite(C):
            require(not r.valid and r.invalid_reason == 'metadata_capacity_unavailable', 'Missing metadata preserved as unavailable')
            require(pd.isna(r.M_CO2_g), 'No emission from absent capacity')
            continue
        ratio = C/e.C_vphpl
        fd = e.fd*ratio**e.n if r.coefficient_policy == 'fd_rescaled' else e.fd
        x = e.D_veh/C
        power = fd*x**e.n
        P = max(x, power)
        peak = e.Tf_h*e.fp*P**e.s
        mean = e.theta*peak
        mu = e.D_veh/P
        wave = C/(220-C/e.vf_mph)
        kq = 220-mu/wave
        q = mu/kq if kq > 0 else np.nan
        qmax = e.L_mi/(e.Tf_h+peak)
        arrival = 1-peak/P*maximum_profile_slope(e)
        fd_valid = bool(0 < mu < C and kq > 0 and 0 < q < e.vf_mph)
        physical = bool(fd_valid and q <= qmax+8*np.spacing(qmax))
        closure = bool(arrival >= -1e-10)
        values = dict(fd_used=fd, x_h=x, power_duration_h=power, P_h=P, peak_delay_h=peak,
                      mean_delay_h=mean, trip_time_h=e.Tf_h+mean, mu_vphpl=mu, omega_mph=wave,
                      kq_veh_mi_lane=kq, q_mph=q, physical_q_max_mph=qmax,
                      minimum_relative_arrival_rate=arrival, duration_closure_error_veh=mu*P-e.D_veh)
        for key, expected in values.items():
            close(getattr(r, key), expected, 'Sweep arithmetic: '+key, atol=2e-9)
        flags = dict(fd_domain_valid=fd_valid, finite_link_valid=physical, profile_closure_valid=closure,
                     lower_branch=bool(x > power), cubic_speed_domain_5_75_pass=bool(5 <= q < e.vf_mph <= 75),
                     power_branch_gauge_eligible=bool(r.coefficient_policy == 'fd_rescaled' and power >= x),
                     valid=bool(fd_valid and physical and closure))
        for key, expected in flags.items():
            require(getattr(r, key) == expected, 'Sweep flag: '+key)
        require((not r.valid) == bool(str(r.invalid_reason) not in ('', 'nan')), 'Rejected row has explicit reason')
        if r.valid:
            predicted = emissions(e, min(q, qmax), mean, rates)
            close([getattr(r, 'M_'+p+'_g') for p in POLS], predicted, 'Sweep emission arithmetic')
            O = np.array([e['O_'+p] for p in POLS])
            close([getattr(r, p+'_error_pct') for p in POLS], 100*(predicted/O-1), 'Sweep pollutant errors')
        else:
            require(all(pd.isna(getattr(r, 'M_'+p+'_g')) for p in POLS), 'Invalid scenario emission is not silently reported')
        if r.scenario == 'multiplier_1':
            require(r.valid, 'Baseline remains valid')
            close([P, peak, mean, mu, q], [e.P_hat_h, e.wt2_hat_h, e.wbar_hat_h, e.mu_hat_vphpl, e.vq_hat_mph], 'Baseline traffic reconciliation')
            close([getattr(r, 'M_'+p+'_g') for p in POLS], [e['M_'+p] for p in POLS], 'Baseline frozen M reconciliation')
        if flags['power_branch_gauge_eligible']:
            close([P, peak, mean, mu], [e.P_hat_h, e.wt2_hat_h, e.wbar_hat_h, e.mu_hat_vphpl], 'Power-branch gauge invariance')
        if r.scenario.startswith('multiplier_') and ratio >= 1 and r.coefficient_policy == 'fd_rescaled':
            require(flags['power_branch_gauge_eligible'] and r.valid, 'All 137 gauge-increase predictions remain valid')
    masks = {'common_all_multiplier_scenarios': ~table.scenario.eq('metadata_capacity'),
             'common_all_including_metadata': pd.Series(True, index=table.index),
             'common_capacity_increase_scenarios': ~table.scenario.eq('metadata_capacity') & table.capacity_multiplier.ge(1)}
    for key, mask in masks.items():
        expected = table[mask].groupby('episode_id').valid.all()
        require((table[key].to_numpy() == table.episode_id.map(expected).to_numpy()).all(), 'Common cohort flag: '+key)


def audit_metrics(row, observed, predicted):
    O, P = np.asarray(observed, float), np.asarray(predicted, float)
    require(np.isfinite(O).all() and np.isfinite(P).all(), 'Summary uses only finite selected rows')
    require(row.N == len(O), 'Summary cohort count')
    delta = P-O
    denominator = np.sum((O-O.mean())**2) if len(O) else 0
    expected = [O.sum(), P.sum(), 100*np.abs(delta).sum()/np.abs(O).sum() if len(O) else np.nan,
                100*delta.sum()/O.sum() if len(O) else np.nan,
                1-np.sum(delta**2)/denominator if denominator > 0 else np.nan,
                np.sqrt(np.mean(delta**2)) if len(O) else np.nan]
    close([row.observed_total, row.predicted_total, row.WAPE_pct, row.bias_pct, row.R2, row.RMSE],
          expected, 'Independent pooled metrics')


def verify_metrics(fixed, sweep, directory):
    fmetrics = read(directory/'fixed_traffic_metrics.csv')
    require(len(fmetrics) == 128, 'All fixed-traffic metric combinations')
    for r in fmetrics.itertuples(index=False):
        g = fixed[fixed.bounds_profile.eq(r.bounds_profile) & fixed.strategy.eq(r.strategy) & fixed.capacity_policy.eq(r.capacity_policy)]
        z = g[g.valid & (g.jointly_feasible_strict_and_free if r.cohort == 'paired_strict_free' else True)]
        audit_metrics(r, z['O_'+r.pollutant+'_g'], z[r.method+'_'+r.pollutant+'_g'])
    smetrics = read(directory/'capacity_sweep_metrics.csv')
    require(len(smetrics) == 784, 'All sweep metric combinations including common-increase cohort')
    cohort_columns = {'common_all_multipliers': 'common_all_multiplier_scenarios',
                      'common_including_metadata': 'common_all_including_metadata',
                      'common_capacity_increases': 'common_capacity_increase_scenarios'}
    quantities = {p: ('O_'+p+'_g', 'M_'+p+'_g', 'baseline_M_'+p+'_g') for p in POLS}
    quantities.update(duration=('observed_P_h', 'P_h', 'baseline_P_h'),
                      peak_delay=('observed_peak_delay_h', 'peak_delay_h', 'baseline_peak_delay_h'),
                      mean_delay=('observed_mean_delay_h', 'mean_delay_h', 'baseline_mean_delay_h'))
    for r in smetrics.itertuples(index=False):
        g = sweep[sweep.coefficient_policy.eq(r.coefficient_policy) & sweep.scenario.eq(r.scenario)]
        mask = g.valid.copy()
        if r.cohort != 'available_valid':
            mask &= g[cohort_columns[r.cohort]]
        require((r.original_cohort_N, r.valid_N, r.invalid_N) == (len(g), int(g.valid.sum()), int((~g.valid).sum())), 'Sweep scenario retained and rejected counts')
        obs, fit, baseline = quantities[r.quantity]
        z = g[mask]
        audit_metrics(r, z[obs], z[fit if r.method == 'sensitivity' else baseline])


def verify_detector_audit(directory, ep):
    audit = read(directory/'detector_capacity_audit.csv').set_index('sensor_uid')
    sensors = read(FROZEN/'sensor_parameters.csv').set_index('sensor_uid')
    fit = read(FROZEN/'detector_fd_calibration.csv').set_index('sensor_uid')
    panel = read(FROZEN/'traffic_panel.csv.gz')
    require(len(audit) == 352 and audit.index.is_unique, 'All 352 detector diagnostics retained')
    close(audit.loc[sensors.index, ['C_vphpl', 'vf_mph', 'kj_veh_mi_lane', 'omega_mph']].to_numpy(),
          sensors[['C_vphpl', 'vf_mph', 'kj', 'omega_mph']].to_numpy(), 'Frozen detector FD inputs')
    counts = ep.groupby('sensor_uid').size()
    for sid, g in panel.groupby('sensor_uid'):
        r, f = audit.loc[sid], fit.loc[sid]
        valid = np.isfinite(g.speed_mph) & g.speed_mph.gt(0) & g.speed_mph.le(90) & np.isfinite(g.flow_vph) & g.flow_vph.gt(0) & ~g.holdout.astype(bool)
        q = g.loc[valid, 'flow_vph']
        require(r.profile_positive_pairs == len(q), 'Detector positive source pair count')
        close([r.profile_q95_vphpl, r.profile_q995_vphpl, r.profile_max_flow_vphpl, r.profile_share_above_C],
              [q.quantile(.95), q.quantile(.995), q.max(), q.gt(r.C_vphpl).mean()], 'Direct source profile capacity context')
        close(r.pre_S3_C_vphpl, f.old_C_vphpl, 'Pre-S3 source capacity')
        require(r.retained_emission_episodes == counts.get(sid, 0), 'Detector retained-episode count')
        require(r.represented_in_137 == (sid in counts), 'Detector selected-cohort membership')
    require(audit.retained_emission_episodes.sum() == 137, 'Detector audit sums to 137')


def main(directory):
    source = read(FROZEN/'episode_results_v2.csv')
    ep = source[source.matched_ladder_pass].set_index('episode_id')
    require(len(ep) == 137 and ep.index.is_unique, 'Frozen matched cohort')
    rates = IndependentRates()
    fixed, sweep = read(directory/'fixed_traffic_comparison.csv'), read(directory/'capacity_sweep.csv')
    verify_fixed(fixed, ep, rates)
    verify_sweep(sweep, ep, rates)
    verify_metrics(fixed, sweep, directory)
    verify_detector_audit(directory, ep)
    provenance = json.loads((directory/'verification.json').read_text())['input_sha256']
    for name, digest in provenance.items():
        require(hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, 'Input hash: '+name)
    print(json.dumps({'status': 'pass', 'checks': CHECKS, 'episodes': len(ep),
                      'fixed_traffic_rows': len(fixed), 'capacity_sweep_rows': len(sweep),
                      'directory': str(directory), 'read_only': True}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=ROOT/'debug/capacity_sensitivity')
    main(parser.parse_args().directory.resolve())
