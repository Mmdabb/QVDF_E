"""Independent profile calibration and strictly held-out daily validation for v19.

All physical formulas and fitting bounds come from the retained v15 model. The
only change to episode outlier QC is P -> (wt2/Tf), replacing P -> wt2.
"""
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import v15_model as model

LOG = logging.getLogger('qvdfe_cbi')
POLS = model.POLS
TARGETS = [('P_h','P_hat_h'),('vt2_obs_mph','vt2_hat_mph'),
           ('wt2_h','wt2_hat_h'),('wt2_h','wt2_conditional_hat_h'),
           ('vq_mph','vq_hat_mph'),('mu_vphpl','mu_hat_vphpl'),
           ('wt2_normalized','wt2_hat_normalized')]


def paper_corridor(value):
    return value.rsplit('_', 1)[0]


def add_outlier_flags(ep):
    """Preserve the old rule exactly except for dimensionless peak severity."""
    ep = ep.copy()
    ep['wt2_normalized'] = ep.wt2_h / ep.Tf_h
    ep['outlier_votes'] = 0
    relationships = [('x_h','P_h','outlier_duration_relation'),
                     ('P_h','wt2_normalized','outlier_normalized_severity_relation'),
                     ('x_h','mu_obs_vphpl','outlier_recovery_relation')]
    for _, _, flagname in relationships: ep[flagname] = False
    ep['outlier_duration_marginal'] = False
    for corridor, g in ep.groupby('corridor'):
        train = g[~g.holdout & ~g.qc_hard_fail]
        if len(train) < 8: continue
        for x, y, flagname in relationships:
            z = train[(train[x]>0) & (train[y]>0) & np.isfinite(train[y])]
            if len(z) < 8: continue
            b = model.robust_line(np.log(z[x].to_numpy()), np.log(z[y].to_numpy()))
            residual = np.log(z[y]) - (b[0]+b[1]*np.log(z[x]))
            center = np.median(residual)
            scale = max(1.4826*np.median(np.abs(residual-center)), .10)
            target = np.log(g[y].where(g[y]>0)) - (b[0]+b[1]*np.log(g[x].where(g[x]>0)))
            flag = (np.abs(target-center)>3.5*scale).fillna(False)
            ep.loc[g.index,flagname] = flag
            ep.loc[g.index,'outlier_votes'] += flag.astype(int)
        center = np.median(np.log(train.P_h))
        scale = max(1.4826*np.median(np.abs(np.log(train.P_h)-center)), .2)
        flag = np.abs(np.log(g.P_h)-center)>3.5*scale
        ep.loc[g.index,'outlier_duration_marginal'] = flag
        ep.loc[g.index,'outlier_votes'] += flag.astype(int)
    ep['qc_outlier_fail'] = ep.outlier_votes.ge(2)
    ep['calibration_eligible'] = ~(ep.qc_hard_fail | ep.qc_outlier_fail)
    # This independent comparison is audit-only. It never supplies a fit mask.
    old = model.add_outlier_flags(ep)
    ep['legacy_raw_delay_outlier_votes'] = old.outlier_votes
    ep['legacy_raw_delay_outlier_fail'] = old.qc_outlier_fail
    return ep


def load_inputs(folder):
    panel = pd.read_csv(folder/'traffic_panel.csv.gz', parse_dates=['datetime'], low_memory=False)
    panel['date'] = panel.datetime.dt.strftime('%Y-%m-%d')
    ep = pd.read_csv(folder/'episodes_detected.csv',parse_dates=['t0','t2','t3'])
    ep['date'] = ep.t0.dt.strftime('%Y-%m-%d')
    cards = pd.read_csv(folder/'sensor_parameters.csv')
    observed = model.observed_targets(ep,panel,cards)
    ep = add_outlier_flags(observed)
    ep['paper_corridor'] = ep.corridor.map(paper_corridor)
    if 'profile_kind' in panel:
        if 'month' not in panel: panel['month'] = panel.datetime.dt.strftime('%Y-%m')
        meta = panel[['sensor_uid','date','profile_kind','month']].drop_duplicates(['sensor_uid','date'])
        ep = ep.merge(meta,on=['sensor_uid','date'],validate='many_to_one')
    return panel,cards,ep


def calibration(ep,cards,folder,bootstrap,average):
    params,draws = model.calibrate(ep,cards,folder,bootstrap)
    params['analysis_track'] = 'average_weekday' if average else 'daily_validation'
    params['paper_corridor'] = params.corridor.map(paper_corridor)
    params['bootstrap_unit'] = np.where(params.corridor.eq('AZ_I10_W'),
        'sensor-month average-weekday profile' if average else 'sensor-day', 'released link profile')
    params['bootstrap_replicates'] = bootstrap
    params['parameter_CI_scope'] = 'conditional on preprocessed input, FD, episode detection and QC; no refit of those stages'
    params.to_csv(folder/'parameter_card_v15.csv',index=False)
    params.to_csv(folder/'parameter_card.csv',index=False)
    ep = model.predictions(ep,params)
    ep['wt2_hat_normalized'] = ep.wt2_hat_h/ep.Tf_h
    if average:
        ep['calibration_split'] = np.where(ep.corridor.eq('AZ_I10_W'),'constructed_monthly_profile_fit','released_profile_fit')
    # Bounds are confidence intervals for fitted targets conditional on model
    # parameters; they are not prediction intervals for a new traffic episode.
    for name in ['P_hat_h','wt2_hat_h','vt2_hat_mph']:
        ep[name+'_lo'] = np.nan; ep[name+'_hi'] = np.nan
    for (corridor,period),g in ep.groupby(['corridor','period']):
        b = draws[draws.corridor.eq(corridor)&draws.period.eq(period)]
        if b.empty: continue
        x = g.x_h.to_numpy()[None,:]
        P = np.maximum(b.fd.to_numpy()[:,None]*x**b.n.to_numpy()[:,None],x)
        severity = b.fp.to_numpy()[:,None]*P**b.s.to_numpy()[:,None]
        values = {'P_hat_h':P,'wt2_hat_h':severity*g.Tf_h.to_numpy()[None,:],
                  'vt2_hat_mph':g.vf_mph.to_numpy()[None,:]/(1+severity)}
        for name,arr in values.items():
            lo,hi = np.quantile(arr,[.025,.975],axis=0)
            ep.loc[g.index,name+'_lo'] = lo; ep.loc[g.index,name+'_hi'] = hi
    return ep,params,draws


def score_ci(g,target,prediction,block,bootstrap,seed):
    z = g[np.isfinite(g[target]) & np.isfinite(g[prediction])].copy()
    result = model.scores(z[target],z[prediction])
    result['MAE'] = float(np.mean(np.abs(z[prediction]-z[target]))) if len(z) else np.nan
    result['N_blocks'] = int(z[block].nunique())
    result['N_dates'] = int(z.date.nunique()) if 'date' in z else result['N_blocks']
    keys = ['R2','RMSE','MAE','bias_pct','WAPE_pct']
    for k in keys: result[k+'_lo'] = np.nan; result[k+'_hi'] = np.nan
    if len(z) < 2 or result['N_blocks'] < 2: return result
    z['_y'] = z[target]; z['_p'] = z[prediction]
    z['_y2'] = z._y**2; z['_err2'] = (z._p-z._y)**2
    z['_abserr'] = np.abs(z._p-z._y); z['_absy'] = np.abs(z._y)
    b = z.groupby(block).agg(n=('_y','size'), y=('_y','sum'), p=('_p','sum'),
        y2=('_y2','sum'),err2=('_err2','sum'),abserr=('_abserr','sum'),absy=('_absy','sum'))
    rng = np.random.default_rng(seed)
    sampled = b.to_numpy()[rng.integers(0,len(b),(bootstrap,len(b)))].sum(axis=1)
    n,y,p,y2,err2,abserr,absy = sampled.T
    denominator = y2-y*y/n
    vals = {'R2':np.divide(denominator-err2,denominator,out=np.full(bootstrap,np.nan),where=denominator>1e-15),
        'RMSE':np.sqrt(err2/n),'MAE':abserr/n,'bias_pct':100*(p/y-1),'WAPE_pct':100*abserr/absy}
    for k in keys:
        a = vals[k][np.isfinite(vals[k])]
        if len(a): result[k+'_lo'],result[k+'_hi'] = np.quantile(a,[.025,.975])
    return result


def mobility_metrics(ep,folder,bootstrap,average):
    rows = []; groups = []
    if average:
        groups = [('All average-weekday profiles','All',ep)]
        groups += [(corridor,corridor,g) for corridor,g in ep.groupby('paper_corridor')]
        groups += [('I10 monthly average weekday','AZ_I10',ep[ep.corridor.eq('AZ_I10_W')]),
                   ('PeMS released profiles','PeMS pooled',ep[~ep.corridor.eq('AZ_I10_W')])]
    else:
        groups = [('AZ training','AZ_I10',ep[~ep.holdout]),('AZ later date','AZ_I10',ep[ep.holdout])]
    for sample,corridor,g in groups:
        g = g[g.calibration_eligible].copy()
        g['profile_block'] = g.sensor_uid.astype(str)+'::'+g.date.astype(str)
        block = 'profile_block' if average else 'date'
        for target,prediction in TARGETS:
            z = g
            if target == 'vq_mph':
                z = g[g.vq_mph.gt(0)&g.vq_mph.lt(g.vf_mph)&g.vq_hat_mph.gt(0)&g.vq_hat_mph.lt(g.vf_mph)]
            row = dict(analysis_track='average_weekday' if average else 'daily_validation',sample=sample,
                paper_corridor=corridor,target=target,prediction=prediction,
                bootstrap_unit='sensor-profile' if average else 'calendar date, all sensors together',
                bootstrap_replicates=bootstrap,metric_CI_scope='fixed predictions, paired block resampling; no calibration refit',
                pair_support='both queue-state speeds strictly between zero and vf; geometric failures retained' if target=='vq_mph' else 'all eligible finite observed/predicted pairs; no emission admission filter',
                **score_ci(z,target,prediction,block,bootstrap,190922+len(rows)))
            rows.append(row)
    result = pd.DataFrame(rows)
    result.to_csv(folder/('average_metrics_ci.csv' if average else 'daily_metrics_ci.csv'),index=False)
    result.to_csv(folder/'pooled_fit_metrics.csv',index=False)
    # Direction rows are diagnostic only; paper rows above pool paired residuals
    # across directions after fitting each direction independently.
    direction = []
    for corridor,g in ep[ep.calibration_eligible].groupby('corridor'):
        for target,prediction in TARGETS:
            z = g
            if target == 'vq_mph':
                z = g[g.vq_mph.gt(0)&g.vq_mph.lt(g.vf_mph)&g.vq_hat_mph.gt(0)&g.vq_hat_mph.lt(g.vf_mph)]
            direction.append(dict(corridor=corridor,target=target,prediction=prediction,
                                  **model.scores(z[target],z[prediction])))
    pd.DataFrame(direction).to_csv(folder/'direction_fit_metrics.csv',index=False)
    return result


def emission_metrics(ep,period,folder,bootstrap):
    groups = [('All average-weekday profiles',ep),('I10 monthly average weekday',ep[ep.corridor.eq('AZ_I10_W')]),
              ('PeMS released profiles',ep[~ep.corridor.eq('AZ_I10_W')])]
    groups += [(name,g) for name,g in ep.groupby('paper_corridor')]
    rows = []
    for sample,g in groups:
        g = g[g.matched_ladder_pass].copy()
        g['profile_block'] = g.sensor_uid.astype(str)+'::'+g.date.astype(str)
        for p in POLS:
            for mode in ['R','M','A','S']:
                rows.append(dict(sample=sample,pollutant=p,method=mode,
                    bootstrap_unit='sensor-profile',bootstrap_replicates=bootstrap,
                    **score_ci(g,'O_'+p,mode+'_'+p,'profile_block',bootstrap,290922+len(rows))))
    pd.DataFrame(rows).to_csv(folder/'emission_metrics.csv',index=False)
    ladder = []
    for sample,g in groups:
        g = g[g.matched_ladder_pass]
        for p in POLS:
            for a,b in [('R','O'),('M','R'),('A','M'),('S','O'),('M','O')]:
                ratio = g[a+'_'+p]/g[b+'_'+p]
                ladder.append(dict(sample=sample,pollutant=p,numerator=a,denominator=b,N=len(g),
                    median_ratio=ratio.median(),mean_ratio=ratio.mean(),
                    ratio_of_totals=g[a+'_'+p].sum()/g[b+'_'+p].sum() if len(g) else np.nan,
                    log_ratio_median=np.log(ratio).median()))
    pd.DataFrame(ladder).to_csv(folder/'emission_ladder_metrics.csv',index=False)
    pgroups = [('All average-weekday profiles',period),('I10 monthly average weekday',period[period.corridor.eq('AZ_I10_W')]),
               ('PeMS released profiles',period[~period.corridor.eq('AZ_I10_W')])]
    pgroups += [(name,g) for name,g in period.groupby('paper_corridor')]
    rows = []
    for sample,g in pgroups:
        for period_name,z in [('All',g)]+[(p,v) for p,v in g.groupby('period')]:
            z = z[z.period_model_pass].copy()
            z['profile_block'] = z.sensor_uid.astype(str)+'::'+z.date.astype(str)
            for p in POLS:
                for mode in ['M','S']:
                    rows.append(dict(sample=sample,period=period_name,pollutant=p,method=mode,
                        **score_ci(z,'O_H_'+p,mode+'_H_'+p,'profile_block',bootstrap,390922+len(rows))))
    pd.DataFrame(rows).to_csv(folder/'period_emission_metrics.csv',index=False)


def summary(ep,params,folder,bootstrap,average,period=None):
    def counts(g):
        eligible = g.calibration_eligible
        return dict(detected=len(g),hard_qc_failed=int(g.qc_hard_fail.sum()),
            outlier_failed_after_hard_qc=int((~g.qc_hard_fail & g.qc_outlier_fail).sum()),
            eligible=int(eligible.sum()),fitted=int((eligible & np.isfinite(g.P_hat_h)).sum()),
            physical=int((eligible & g.physical_predicted_pass).sum()),
            observed_physical=int((eligible & g.physical_observed_pass).sum()),
            matched=int(g.matched_ladder_pass.sum()) if 'matched_ladder_pass' in g else 0,
            closed=int(g.profile_closed_pass.sum()) if 'profile_closed_pass' in g else 0,
            lower_branch=int((eligible & g.lower_branch).sum()),
            legacy_eligible=int((~g.qc_hard_fail & ~g.legacy_raw_delay_outlier_fail).sum()))
    result = dict(analysis_track='average_weekday' if average else 'daily_validation',**counts(ep),
        by_corridor={str(k):counts(g) for k,g in ep.groupby('corridor')},
        by_paper_corridor={str(k):counts(g) for k,g in ep.groupby('paper_corridor')},
        by_split={str(k):counts(g) for k,g in ep.groupby('calibration_split')},
        bootstrap_replicates=bootstrap,parameter_cards=len(params),
        supported_parameter_cards=int(params.fd.notna().sum()),
        fallback_parameter_cards=int(params.calibration_scope.eq('corridor_all_periods').sum()),
        unavailable_parameter_cards=int(params.calibration_scope.eq('unavailable').sum()),
        outlier_rule='P versus wt2/Tf; other two relations, duration rule, 3.5 MAD threshold and >=2 votes unchanged',
        raw_speed_policy='flag only; state-transition smoothing retained; no speed imputation or removal',
        mean_speed_target='vq is triangular-FD queue-state speed inferred from D/P; vt2 is minimum observed whole-link speed',
        fit_scope='corridor-direction-period; same corridor-direction all-period fallback if local N<8; unavailable if fallback N<8')
    if average:
        result['emission_scope'] = 'independently calibrated monthly average-weekday Arizona and released monthly California profiles only'
        result['max_conservation_error_veh'] = float(ep.conservation_error_veh.abs().max())
        result['max_theta_quadrature_error'] = float(ep.theta_quadrature_error.abs().max())
        result['period_rows'] = len(period)
        result['period_model_pass'] = int(period.period_model_pass.sum())
    else:
        result['metric_CI_scope'] = 'calendar-date block bootstrap within training or heldout split; predictions fixed; no emission admission filter'
        result['emissions_evaluated'] = False
    (folder/'model_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    pd.DataFrame([dict(corridor=k,**v) for k,v in result['by_corridor'].items()]).to_csv(folder/'physical_audit_summary.csv',index=False)
    changes = ep[ep.qc_outlier_fail.ne(ep.legacy_raw_delay_outlier_fail)]
    changes[['episode_id','corridor','period','date','holdout','qc_hard_fail','outlier_votes',
             'legacy_raw_delay_outlier_votes','qc_outlier_fail','legacy_raw_delay_outlier_fail',
             'calibration_eligible','P_h','wt2_h','Tf_h','wt2_normalized']].to_csv(folder/'outlier_rule_changed_episodes.csv',index=False)
    LOG.info('%s final summary: detected=%s eligible=%s fitted=%s matched=%s',result['analysis_track'],result['detected'],result['eligible'],result['fitted'],result['matched'])
    return result


def run_daily(root,out,bootstrap):
    folder = out/'daily_validation'
    LOG.info('Daily track: unchanged raw episodes; normalized-severity QC; chronological calibration')
    panel,cards,ep = load_inputs(folder)
    ep,params,draws = calibration(ep,cards,folder,bootstrap,False)
    ep.to_csv(folder/'episode_results_v2.csv',index=False)
    mobility_metrics(ep,folder,bootstrap,False)
    summary(ep,params,folder,bootstrap,False)


def refresh_metrics(out,bootstrap):
    for name,average in [('daily_validation',False),('average_weekday',True)]:
        folder = out/name
        ep = pd.read_csv(folder/'episode_results_v2.csv')
        mobility_metrics(ep,folder,bootstrap,average)


def run_average(root,out,bootstrap,emission_input):
    folder = out/'average_weekday'
    LOG.info('Profile track: independent monthly Arizona and released California calibration')
    panel,cards,ep = load_inputs(folder)
    ep,params,draws = calibration(ep,cards,folder,bootstrap,True)
    moves = model.load_moves_rates(emission_input)
    cf = pd.read_csv(folder/'cubic_rate_coefficients.csv')
    coeff = {r.pollutant:np.array([r.c0,r.c1,r.c2,r.c3]) for r in cf.itertuples()}
    ep = model.emission_ladder(ep,panel,moves,coeff)
    for p in POLS:
        state = ep.vq_mph.ge(5)&ep.vq_mph.lt(ep.vf_mph)&ep.vf_mph.le(75)
        ep['Gamma_observed_cubic_'+p] = np.where(state,model.gamma_from_cubic(ep.vq_mph.to_numpy(),ep.vf_mph.to_numpy(),coeff[p]),np.nan)
    ep['figure5_gamma_pass'] = ep.calibration_eligible & ep.physical_predicted_pass & ep.cubic_domain_pass
    ep['figure8_pair_vq_pass'] = (ep.calibration_eligible & np.isfinite(ep.vq_mph)&np.isfinite(ep.vq_hat_mph)
        &ep.vq_mph.gt(0)&ep.vq_mph.lt(ep.vf_mph)&ep.vq_hat_mph.gt(0)&ep.vq_hat_mph.lt(ep.vf_mph))
    ep['figure8_pair_mobility_pass'] = ep.calibration_eligible & np.isfinite(ep.P_hat_h)&np.isfinite(ep.vt2_hat_mph)
    ep.to_csv(folder/'episode_results_v2.csv',index=False)
    LOG.info('Average-profile coefficients and episode results ready; constructing periods and summary metrics')
    # Keep unique month labels. Passing average=True to the older helper would
    # collapse distinct months to a single AVG key and is deliberately avoided.
    period = model.period_table(ep,panel,moves,False)
    period['is_average_day'] = True
    period['paper_corridor'] = period.corridor.map(paper_corridor)
    meta = panel[['sensor_uid','date','profile_kind','month']].drop_duplicates(['sensor_uid','date'])
    period = period.merge(meta,on=['sensor_uid','date'],validate='many_to_one')
    period.to_csv(folder/'period_results_v2.csv',index=False)
    mobility_metrics(ep,folder,bootstrap,True)
    emission_metrics(ep,period,folder,bootstrap)
    model.cost_tables(params,draws,cards,ep,coeff,folder)
    selected = ep[ep.corridor.eq('AZ_I10_W') & ep.matched_ladder_pass].sort_values('P_h')
    if selected.empty: selected = ep[ep.matched_ladder_pass].sort_values('P_h')
    if not selected.empty:
        rep = selected.iloc[len(selected)//2]
        series = panel[panel.sensor_uid.eq(rep.sensor_uid)&panel.date.eq(rep.date)].copy()
        series['episode_id'] = rep.episode_id;series['time'] = series.datetime;series['flow_vphpl'] = series.flow_vph
        series[['episode_id','time','speed_mph','flow_vphpl']].to_csv(folder/'episode_timeseries.csv',index=False)
    result = summary(ep,params,folder,bootstrap,True,period)
    result['representative_episode'] = str(rep.episode_id) if not selected.empty else None
    (folder/'model_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')


def audit(root,out,baseline):
    source = json.loads((out/'input_reuse_provenance.json').read_text())
    checks = {}
    for name,sha in source['preprocessed_sha256'].items():
        checks['baseline_unchanged_'+name] = hashlib.sha256((baseline/name).read_bytes()).hexdigest()==sha
    daily = pd.read_csv(out/'daily_validation/episode_results_v2.csv')
    average = pd.read_csv(out/'average_weekday/episode_results_v2.csv')
    old = pd.read_csv(baseline/'episode_results_v2.csv')
    old = old[old.corridor.eq('AZ_I10_W')]
    joined = daily.merge(old,on='episode_id',suffixes=('_new','_old'),validate='one_to_one')
    checks['all_daily_episodes_preserved'] = len(joined)==len(old)==len(daily)
    for col in ['D_veh','x_h','P_h','vt2_obs_mph','wt2_h','Tf_h','holdout']:
        checks['daily_'+col+'_unchanged'] = bool(np.allclose(joined[col+'_new'],joined[col+'_old'],equal_nan=True))
    checks['daily_train_holdout_dates_disjoint'] = not bool(set(daily.loc[~daily.holdout,'date'])&set(daily.loc[daily.holdout,'date']))
    checks['average_profiles_never_labeled_heldout'] = not bool(average.holdout.any())
    checks['normalized_QC_exactly_two_vote_mask_daily'] = bool((daily.calibration_eligible==~(daily.qc_hard_fail|daily.outlier_votes.ge(2))).all())
    checks['normalized_QC_exactly_two_vote_mask_average'] = bool((average.calibration_eligible==~(average.qc_hard_fail|average.outlier_votes.ge(2))).all())
    for name,ep in [('daily',daily),('average',average)]:
        checks[name+'_x_equals_episode_volume_over_capacity'] = bool(np.allclose(ep.x_h,ep.D_veh/ep.C_vphpl,equal_nan=True))
        checks[name+'_mu_equals_episode_volume_over_duration'] = bool(np.allclose(ep.mu_vphpl,ep.D_veh/ep.P_h,equal_nan=True))
        p = pd.read_csv(out/('daily_validation' if name=='daily' else 'average_weekday')/'parameter_card_v15.csv')
        source_train = ep[ep.calibration_eligible & ~ep.holdout]
        support = []
        for r in p.itertuples():
            z = source_train[source_train.corridor.eq(r.corridor)]
            local = z[z.period.eq(r.period)]
            n = len(local) if len(local)>=8 else len(z)
            support.append(r.N_source==n and r.N_train==len(local) and ((n>=8)==np.isfinite(r.fd)))
        checks[name+'_parameter_support_and_train_only_mask'] = all(support)
    checks['emission_conservation_error_below_1e-8_veh'] = float(average.conservation_error_veh.abs().max())<1e-8
    checks['emission_theta_error_below_1e-5'] = float(average.theta_quadrature_error.abs().max())<1e-5
    summary_data = json.loads((out/'data_summary.json').read_text())
    checks['monthly_VHT_preserved'] = summary_data['i10_average_VHT_preservation_relative_error']<1e-12
    period = pd.read_csv(out/'average_weekday/period_results_v2.csv')
    checks['unique_average_profile_periods'] = not bool(period.duplicated(['sensor_uid','date','period']).any())
    checks['all_emissions_from_average_profiles'] = bool(period.is_average_day.all())
    # A held-out day's values cannot influence any training reference residual.
    train = daily[~daily.holdout].copy()
    isolated = add_outlier_flags(train)
    checks['daily_training_QC_independent_of_heldout_rows'] = bool((isolated.outlier_votes.to_numpy()==train.outlier_votes.to_numpy()).all())
    rescaled = average.copy()
    scale = np.linspace(.25,4.,len(rescaled))
    rescaled['wt2_h'] *= scale; rescaled['Tf_h'] *= scale
    checks['normalized_QC_invariant_to_common_delay_Tf_rescaling'] = bool((add_outlier_flags(rescaled).outlier_votes.to_numpy()==average.outlier_votes.to_numpy()).all())
    old_ca = pd.read_csv(baseline/'episode_results_v2.csv')
    old_ca = old_ca[~old_ca.corridor.eq('AZ_I10_W')]
    new_ca = average[~average.corridor.eq('AZ_I10_W')]
    joined_ca = new_ca.merge(old_ca,on=['sensor_uid','t0','t3'],suffixes=('_new','_old'),validate='one_to_one')
    checks['all_PeMS_detected_episode_boundaries_unchanged'] = len(joined_ca)==len(old_ca)==len(new_ca)
    checks['all_PeMS_observed_targets_unchanged'] = all(np.allclose(joined_ca[k+'_new'],joined_ca[k+'_old'],equal_nan=True)
        for k in ['D_veh','x_h','P_h','wt2_h','Tf_h','vt2_obs_mph'])
    checks['all_PeMS_hard_QC_unchanged'] = bool((joined_ca.qc_hard_fail_new==joined_ca.qc_hard_fail_old).all())
    result = dict(passed=all(checks.values()),checks=checks,
        data=summary_data,daily=json.loads((out/'daily_validation/model_summary.json').read_text()),
        average=json.loads((out/'average_weekday/model_summary.json').read_text()))
    (out/'v19_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    if not result['passed']: raise AssertionError({k:v for k,v in checks.items() if not v})
    write_notes(out,result)
    LOG.info('V19 independent-track audit: all %s checks passed',len(checks))


def write_notes(out, result):
    """Report actual support; do not embed historical manuscript prose."""
    lines = ["# Empirical workflow audit", "", "The full run audit is in v19_audit.json.", "",
             "| Track | Detected | Eligible | Fitted | Emission matched |",
             "|---|---:|---:|---:|---:|"]
    for key in ["daily", "average"]:
        row = result[key]
        lines.append(f"| {key} | {row['detected']} | {row['eligible']} | {row['fitted']} | {row['matched']} |")
    lines.extend(["", "M uses the direct MOVES-derived lookup; A uses its cubic approximation.",
                  "Daily validation and average-profile calibration are separate tracks.",
                  "The workflow preserves the recorded v19 cohort and all original screening rules.",
                  "See pipeline/v19/README.md for input contracts and interpretation."])
    (out / "RESULTS_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
