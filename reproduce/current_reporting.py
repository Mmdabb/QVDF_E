"""Reproduce the v33 planning-period/daytime summaries on their stated sample.

The original frozen tables remain unchanged. Apply the reviewed profile support,
sum AM/MD/PM before scoring, and verify against the saved v33 aggregate metrics.
This is reporting from retained results, not episode detection or recalibration.
"""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from qvdfe.paths import data_dir, frozen_dir

POLLUTANTS = ('CO2', 'NOx', 'CO', 'HC')


def checked_periods(periods, scope):
    """Keep the declared Arizona profiles and all released PeMS profiles."""
    keys = ['sensor_uid', 'month']
    if scope.duplicated(keys).any():
        raise ValueError('Reporting scope contains duplicate sensor-month keys')
    frame = periods.copy()
    frame['month'] = frame.date.astype(str).str[:7]
    allowed = pd.MultiIndex.from_frame(scope[keys])
    observed = pd.MultiIndex.from_frame(frame.loc[frame.corridor.eq('AZ_I10_W'), keys])
    if len(allowed.difference(observed)):
        raise ValueError('Declared reporting profiles are absent from period inputs')
    selected = pd.MultiIndex.from_frame(frame[keys]).isin(allowed)
    frame = frame[~frame.corridor.eq('AZ_I10_W') | selected].drop(columns='month').copy()
    for col in ('period_model_pass', 'complete_observations', 'all_episodes_valid', 'holdout'):
        frame[col] = frame[col].astype(str).str.lower().eq('true')
    frame['sample'] = np.where(frame.corridor.eq('AZ_I10_W'), 'AZ', 'PeMS')
    return frame


def daytime_totals(periods):
    parts = periods[periods.period.isin(['AM', 'MD', 'PM'])]
    groups = ['sensor_uid', 'date']
    if parts.duplicated(groups + ['period']).any():
        raise ValueError('A daytime window contains a duplicate constituent period')
    aggregations = {c: 'sum' for c in ['H_h', 'V_veh', 'D_veh'] +
                    [f'{m}_H_{p}' for m in ('O', 'S', 'M') for p in POLLUTANTS]}
    aggregations.update({c: 'all' for c in
                         ['period_model_pass', 'complete_observations', 'all_episodes_valid']})
    aggregations.update({c: 'first' for c in ['sample', 'corridor', 'holdout']})
    result = parts.groupby(groups).agg(aggregations).reset_index()
    result['n_parts'] = parts.groupby(groups).size().to_numpy()
    if not ((result.n_parts == 3).all() and np.allclose(result.H_h, 14.0)):
        raise ValueError('A daytime window requires all three periods spanning 14 hours')
    return result


def pooled_metrics(periods, daytime):
    rows = []
    for window, frame in [('planning_period', periods), ('daytime', daytime)]:
        for sample in ['All', 'AZ', 'PeMS']:
            g = frame[frame.period_model_pass &
                      (True if sample == 'All' else frame['sample'].eq(sample))]
            for method in ['M', 'S']:
                for pol in POLLUTANTS:
                    obs, est = g[f'O_H_{pol}'].to_numpy(float), g[f'{method}_H_{pol}'].to_numpy(float)
                    den = np.sum((obs - obs.mean()) ** 2)
                    rows.append(dict(window=window, sample=sample, method=method, pollutant=pol,
                                     N=len(obs), R2=1 - np.sum((est-obs)**2)/den,
                                     bias_pct=100*(est.sum()/obs.sum()-1),
                                     WAPE_pct=100*np.abs(est-obs).sum()/obs.sum()))
    return pd.DataFrame(rows)


def main():
    source = frozen_dir() / 'calibration/average_weekday/period_results_v2.csv'
    scope_file = data_dir() / 'reporting/v33/arizona_episode_profile_scope.csv'
    expected_file = data_dir() / 'reporting/v33/period_emission_metrics.csv'
    p = checked_periods(pd.read_csv(source, low_memory=False), pd.read_csv(scope_file))
    day = daytime_totals(p)
    metrics = pooled_metrics(p, day)
    expected = pd.read_csv(expected_file)
    pd.testing.assert_frame_equal(metrics, expected, check_exact=False, rtol=1e-9, atol=1e-12)
    out = ROOT / 'reproduce/output/current_reporting'
    out.mkdir(parents=True, exist_ok=True)
    p.to_csv(out / 'planning_period_totals.csv', index=False)
    day.to_csv(out / 'daytime_period_totals.csv', index=False)
    metrics.to_csv(out / 'period_emission_metrics.csv', index=False)
    summary = {'reporting_version': 'v33', 'refitted': False,
               'daytime_profiles': len(day), 'supported_daytime_windows': int(day.period_model_pass.sum()),
               'expected_metrics_match': True,
               'inputs': {str(f.relative_to(data_dir())).replace('\\', '/'): hashlib.sha256(f.read_bytes()).hexdigest()
                          for f in (source, scope_file, expected_file)}}
    (out / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(f"Current reporting: {len(day)} profiles, {summary['supported_daytime_windows']} supported daytime windows; metrics verified.")


if __name__ == '__main__':
    main()
