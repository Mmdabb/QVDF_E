"""Separate daily validation and independently calibrated monthly/profile inputs."""
from pathlib import Path
import hashlib
import json
import logging
import shutil

import numpy as np
import pandas as pd

from . import v15_data as base
from . import v16_data

LOG = logging.getLogger('qvdfe_cbi')
MIN_MONTH_DAYS = 5


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(root, out, baseline):
    daily_dir = out/'daily_validation'; avg_dir = out/'average_weekday'
    for folder in [daily_dir, avg_dir]: folder.mkdir(parents=True, exist_ok=True)
    original_inputs = json.loads((baseline/'input_sha256.json').read_text())
    for entry in original_inputs:
        assert digest(root/entry['path'].replace('\\','/')) == entry['sha256'], entry['path']
    names = ['traffic_panel.csv.gz','sensor_parameters.csv','episodes_detected.csv',
             'detector_fd_calibration.csv','cubic_rate_coefficients.csv']
    provenance = {'source_directory':baseline.name,
                  'preprocessed_sha256':{name:digest(baseline/name) for name in names},
                  'original_inputs_verified':True,'original_inputs':original_inputs,
                  'daily_detector_and_FD_reused':'unchanged raw observations, smoothing and train-only FD parameters',
                  'average_policy':'calendar-month mean weekday profiles; at least five complete sensor-days; mean flow and flow-weighted harmonic speed',
                  'minimum_complete_weekdays_per_sensor_month':MIN_MONTH_DAYS}
    (out/'input_reuse_provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    panel = pd.read_csv(baseline/'traffic_panel.csv.gz', parse_dates=['datetime'], low_memory=False)
    panel['date'] = panel.datetime.dt.strftime('%Y-%m-%d')
    cards = pd.read_csv(baseline/'sensor_parameters.csv')
    episodes = pd.read_csv(baseline/'episodes_detected.csv')
    az = panel[panel.corridor.eq('AZ_I10_W')].copy()
    az_cards = cards[cards.corridor.eq('AZ_I10_W')].copy()
    az.to_csv(daily_dir/'traffic_panel.csv.gz',index=False)
    az_cards.to_csv(daily_dir/'sensor_parameters.csv',index=False)
    episodes[episodes.corridor.eq('AZ_I10_W')].to_csv(daily_dir/'episodes_detected.csv',index=False)
    fd_old = pd.read_csv(baseline/'detector_fd_calibration.csv')
    fd_old[fd_old.corridor.eq('AZ_I10_W')].to_csv(daily_dir/'detector_fd_calibration.csv',index=False)

    az['minute'] = az.datetime.dt.hour*60+az.datetime.dt.minute
    az['month'] = az.datetime.dt.strftime('%Y-%m')
    az['valid_bin'] = np.isfinite(az.speed_mph)&az.speed_mph.gt(0)&az.speed_mph.le(90)&np.isfinite(az.flow_vph)&az.flow_vph.ge(0)
    support = az.groupby(['sensor_uid','month','date']).agg(bins=('minute','nunique'),valid_bins=('valid_bin','sum')).reset_index()
    support['complete_day'] = support.bins.eq(288)&support.valid_bins.eq(288)
    counts = support.groupby(['sensor_uid','month']).complete_day.sum().rename('complete_weekdays').reset_index()
    counts['included'] = counts.complete_weekdays.ge(MIN_MONTH_DAYS)
    support = support.merge(counts,on=['sensor_uid','month'])
    support['included'] = support.included & support.complete_day
    support.to_csv(avg_dir/'i10_monthly_day_support.csv',index=False)
    counts.to_csv(avg_dir/'i10_monthly_profile_support.csv',index=False)
    selected = az.merge(support[support.included][['sensor_uid','date']],on=['sensor_uid','date'],validate='many_to_one')
    selected['flow_over_speed'] = selected.flow_vph/selected.speed_mph
    avg = selected.groupby(['sensor_uid','month','minute'],as_index=False).agg(
        flow_vph=('flow_vph','mean'),mean_flow_over_speed=('flow_over_speed','mean'),
        mean_empty_speed=('speed_mph','mean'),days=('date','nunique'))
    avg['speed_mph'] = np.where(avg.flow_vph.gt(0),avg.flow_vph/avg.mean_flow_over_speed,avg.mean_empty_speed)
    avg['zero_flow_speed_fallback'] = avg.flow_vph.eq(0)
    avg['datetime'] = pd.to_datetime(avg.month+'-01')+pd.to_timedelta(avg.minute,unit='min')
    avg['date'] = avg.datetime.dt.strftime('%Y-%m-%d')
    avg['dataset'] = 'I10_monthly_average_weekday'
    avg['profile_kind'] = 'constructed_monthly_average_weekday'
    avg['corridor'] = 'AZ_I10_W'; avg['direction']='W'; avg['holdout']=False
    avg['all_lanes_present'] = True
    avg = avg.merge(az_cards[['sensor_uid','lanes']],on='sensor_uid',validate='many_to_one')
    relative_error = np.max(np.abs(avg.flow_vph/avg.speed_mph-avg.mean_flow_over_speed)/np.maximum(1,abs(avg.mean_flow_over_speed)))
    assert relative_error < 1e-12
    assert avg.groupby(['sensor_uid','month']).size().eq(288).all()

    # Only the five Arizona detector FDs are newly fitted to these independent
    # average-profile observations. Their fallback inputs are also profile based.
    for i,row in az_cards.iterrows():
        g=avg[avg.sensor_uid.eq(row.sensor_uid)]
        if g.empty: raise ValueError('No supported monthly profile for '+row.sensor_uid)
        az_cards.loc[i,'C_vphpl']=g.flow_vph.quantile(.995)
        az_cards.loc[i,'vf_mph']=g.speed_mph.quantile(.95)
    az_cards['dataset']='I10_monthly_average_weekday'
    az_cards['capacity_source']='monthly_average_profile_q995'
    az_cards['vf_source']='monthly_average_profile_speed_q95'
    fd_dir=avg_dir/'i10_fd_fit';fd_dir.mkdir(exist_ok=True)
    fitted_az=v16_data.fit_detector_cards(avg,az_cards,fd_dir)
    az_fd=pd.read_csv(fd_dir/'detector_fd_calibration.csv')
    az_fd['fit_scope']='constructed_monthly_average_weekday'
    new_cards=pd.concat([fitted_az,cards[~cards.corridor.eq('AZ_I10_W')]],ignore_index=True)
    new_cards.to_csv(avg_dir/'sensor_parameters.csv',index=False)
    report=pd.concat([az_fd,fd_old[~fd_old.corridor.eq('AZ_I10_W')]],ignore_index=True)
    report.to_csv(avg_dir/'detector_fd_calibration.csv',index=False)
    (avg_dir/'fd_calibration_summary.json').write_text(json.dumps({
        'detectors':len(report),'accepted':int(report.accepted.sum()),'fallback':int((~report.accepted).sum()),
        'by_dataset':report.groupby('dataset').accepted.agg(['count','sum']).to_dict('index'),
        'pems_fits_reused_unchanged':True,'i10_fits_independent_of_daily_validation':True},indent=2),encoding='utf-8')
    avg,_=base.prepare_panel(avg,new_cards[new_cards.corridor.eq('AZ_I10_W')])
    ca=panel[~panel.corridor.eq('AZ_I10_W')].copy()
    ca['month']='2025-10';ca['profile_kind']='released_monthly_average_weekday'
    combined=pd.concat([avg,ca],ignore_index=True).sort_values(['sensor_uid','datetime']).reset_index(drop=True)
    combined.to_csv(avg_dir/'traffic_panel.csv.gz',index=False)
    LOG.info('Detecting monthly-average I10 and released PeMS profile episodes')
    detected=base.detect(combined,new_cards,avg_dir)
    summary={
        'i10_monthly_profiles':len(counts[counts.included]),'i10_months':sorted(avg.month.unique().tolist()),
        'i10_selected_complete_sensor_days':int(support.included.sum()),
        'i10_all_complete_sensor_days':int(support.complete_day.sum()),
        'i10_omitted_sensor_months':int((~counts.included).sum()),
        'i10_profile_day_count_range':[int(avg.days.min()),int(avg.days.max())],
        'i10_average_VHT_preservation_relative_error':float(relative_error),
        'zero_flow_speed_fallback_bins':int(avg.zero_flow_speed_fallback.sum()),
        'pems_profiles':int(ca.sensor_uid.nunique()),
        'detected_by_corridor':detected.groupby('corridor').size().to_dict(),
        'daily_validation_train_dates':int(az.loc[~az.holdout,'date'].nunique()),
        'daily_validation_test_dates':int(az.loc[az.holdout,'date'].nunique()),
        'daily_validation_last_train_date':az.loc[~az.holdout,'date'].max(),
        'daily_validation_first_test_date':az.loc[az.holdout,'date'].min(),
        'daily_data_values_changed':0,'average_profiles_are_in_sample':True}
    (out/'data_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    for dest in [out,daily_dir,avg_dir]:
        shutil.copy2(baseline/'cubic_rate_coefficients.csv',dest/'cubic_rate_coefficients.csv')
    for name in ['input_sha256.json','fd_estimation_protocol.json']:
        shutil.copy2(baseline/name,out/name)
    for source in baseline.glob('cbi_*.csv'):shutil.copy2(source,out/source.name)
    shutil.copytree(baseline/'repository_reference',out/'repository_reference',dirs_exist_ok=True)
    LOG.info('V19 data support: %s',summary)
