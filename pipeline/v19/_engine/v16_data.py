"""Detector-specific FD revision, preserving the recorded V15 traffic panel.

The FD acceptance rule is fixed before downstream outcome calculation. S3 is
the empirical observation fit; the manuscript's triangular queue-state closure
continues to use the same accepted capacity and free-flow speed.
"""


from pathlib import Path


import hashlib


import json


import logging


import shutil


import numpy as np


import pandas as pd


from .fd import fit_measured_s3, s3_flow, s3_speed


from . import v15_data as base


LOG = logging.getLogger('qvdfe_cbi')


POLICY = dict(
    minimum_positive_qv_pairs=50,
    minimum_pairs_each_branch=12,
    free_branch_density_max_ratio=.90,
    congested_branch_density_min_ratio=1.10,
    accepted_capacity_range_vphpl=[500,3500],
    accepted_free_speed_range_mph=[40,90],
    acceptance_requires_solver_success=True,
    acceptance_requires_no_active_bound=True,
    objective='joint normalized q(k) and v(k) residuals; soft_l1, f_scale=0.20',
    density='recorded per-lane q/v; derived, not independent occupancy density',
    initialization='vf0=clip(speed q95,45,85); kc0=clip(flow q99/(.70 vf0),10,100); m0=4',
    bounds='vf:[max(40,.90 vf0),min(90,1.10 vf0)], kc:[5,150], m:[.5,15]',
    fallback='original training/profile q995 capacity and q95 free speed; m=4',
    fit_speed_filter='finite 0<v<=90, finite q>0; all other raw readings retained for detector and QC',
    az_fit_support='training dates only; existing later-date split unchanged',
    pems_fit_support='released average-weekday profile only; not a daily holdout',
    detection_cutoff='0.70 times accepted vf, independent of fitted S3 critical speed',
    outcome_selection='No acceptance rule uses QVDF fit, emissions, or downstream physical pass',
)


def fit_detector_cards(panel,cards,out):
    rows=[]
    for i,(sid,g) in enumerate(panel.groupby('sensor_uid',sort=True)):
        old=cards[cards.sensor_uid.eq(sid)].iloc[0].to_dict()
        fitdata=g[~g.holdout.astype(bool)].copy()
        usable=np.isfinite(fitdata.speed_mph)&fitdata.speed_mph.gt(0)&fitdata.speed_mph.le(90)&np.isfinite(fitdata.flow_vph)&fitdata.flow_vph.gt(0)
        fitdata['qc_pass_repaired']=usable
        fitdata['density_vpm']=fitdata.flow_vph/fitdata.speed_mph.where(fitdata.speed_mph>0)
        fitdata['speed_mph_clean_repaired']=fitdata.speed_mph
        result=fit_measured_s3(fitdata)
        valid=fitdata[usable];k=valid.density_vpm.to_numpy()
        low=high=0
        reasons=[]
        if len(valid)<POLICY['minimum_positive_qv_pairs']:reasons.append('insufficient_pairs')
        if not result.get('fit_success',False):reasons.append('solver_failure')
        if result.get('bound_active',False):reasons.append('active_parameter_bound')
        if result.get('fit_success',False):
            low=int((k<=.90*result['kc_vpmpl']).sum())
            high=int((k>=1.10*result['kc_vpmpl']).sum())
            if min(low,high)<12:reasons.append('insufficient_two_branch_support')
            if not 500<=result['capacity_vphpl']<=3500:reasons.append('capacity_outside_range')
            if not 40<=result['vf_mph']<=90:reasons.append('free_speed_outside_range')
        accepted=not reasons
        row=dict(sensor_uid=sid,corridor=old['corridor'],dataset=old['dataset'],
                 old_C_vphpl=old['C_vphpl'],old_vf_mph=old['vf_mph'],
                 n_fit_pairs=len(valid),n_free_branch=low,n_congested_branch=high,
                 accepted=accepted,fallback_reason=';'.join(reasons),
                 fit_scope='training_dates' if old['dataset']=='new_I10_daily' else 'released_profile',
                 **{'candidate_'+key:value for key,value in result.items()})
        if accepted:
            C=result['capacity_vphpl'];vf=result['vf_mph'];m=result['s3_m'];kc=result['kc_vpmpl']
            old['capacity_source']='detector_robust_s3';old['vf_source']='detector_robust_s3'
        else:
            C=old['C_vphpl'];vf=old['vf_mph'];m=4.;kc=C/(vf*2**(-2/m))
            old['capacity_source']+=';s3_fallback';old['vf_source']+=';s3_fallback'
        old.update(C_vphpl=C,vf_mph=vf,s3_m=m,s3_kc_vpmpl=kc,s3_vc_mph=vf*2**(-2/m),
                   fd_fit_accepted=accepted,fd_fallback_reason=row['fallback_reason'])
        row.update(C_vphpl=C,vf_mph=vf,s3_m=m,s3_kc_vpmpl=kc,s3_vc_mph=old['s3_vc_mph'],
                   recorded_flow_above_fitted_C_share=float(valid.flow_vph.gt(C).mean()))
        # Independent residual summaries are diagnostics, never acceptance criteria.
        predq=s3_flow(k,vf,kc,m);predv=s3_speed(k,vf,kc,m)
        for name,truth,pred in [('flow',valid.flow_vph.to_numpy(),predq),('speed',valid.speed_mph.to_numpy(),predv)]:
            den=np.sum((truth-truth.mean())**2)
            row[name+'_rmse']=float(np.sqrt(np.mean((truth-pred)**2)))
            row[name+'_r2']=float(1-np.sum((truth-pred)**2)/den) if den>0 else np.nan
        row['C_change_pct']=100*(C/row['old_C_vphpl']-1)
        row['vf_change_pct']=100*(vf/row['old_vf_mph']-1)
        rows.append((row,old))
        if (i+1)%25==0:LOG.info('Detector FD candidates completed: %s',i+1)
    report=pd.DataFrame([r for r,_ in rows]);updated=pd.DataFrame([r for _,r in rows])
    report.to_csv(out/'detector_fd_calibration.csv',index=False)
    updated['kc']=updated.C_vphpl/updated.vf_mph
    updated['kj']=220.
    updated['omega_mph']=updated.C_vphpl/(updated.kj-updated.kc)
    updated['metadata_capacity_flag']=updated.C_vphpl.gt(3500)|updated.C_vphpl.lt(500)|updated.kc.ge(updated.kj)
    updated.to_csv(out/'sensor_parameters.csv',index=False)
    summary=dict(detectors=len(report),accepted=int(report.accepted.sum()),fallback=int((~report.accepted).sum()),
                 by_dataset=report.groupby('dataset').accepted.agg(['count','sum']).to_dict('index'),
                 fallback_reasons=report.loc[~report.accepted,'fallback_reason'].value_counts().to_dict(),
                 accepted_m_range=[float(report.loc[report.accepted,'s3_m'].min()),float(report.loc[report.accepted,'s3_m'].max())])
    (out/'fd_calibration_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    LOG.info('FD selection completed: %s',summary)
    return updated
