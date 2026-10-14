"""V15 measured-data adapters and state-transition episode inventory.

Recorded lane observations are retained in the input files. Aggregation requires
every declared mainline lane's count and speed; absent lanes are missing, never
zero-filled. Positive-flow zero speed is invalid travel-time evidence, not repaired.
"""


from pathlib import Path


import json, sys, hashlib, logging, io


import numpy as np


import pandas as pd


from scipy.optimize import linear_sum_assignment


from .episodes import run_detectors


from .cbi_stage1_qc import run_qc


PERIODS={'AM':(6,10),'MD':(10,16),'PM':(16,20),'NT':(20,30)}


DT=1/12


LOG=logging.getLogger('qvdfe_cbi')


def period_of(hour):
    if 6<=hour<10:return 'AM'
    if 10<=hour<16:return 'MD'
    if 16<=hour<20:return 'PM'
    return 'NT'


def prepare_panel(panel,cards):
    panel=panel.merge(cards[['sensor_uid','C_vphpl','vf_mph','L_mi','road_order']],on='sensor_uid',validate='many_to_one')
    panel['corridor_freeflow_speed_mph']=panel.vf_mph
    panel['fd_capacity_vphpl']=panel.C_vphpl;panel['fd_vc_mph']=.7*panel.vf_mph
    panel['length_mi']=panel.L_mi;panel['flow_synthetic']=False;panel['has_volume']=True
    panel['source_format']=panel.dataset
    panel=panel.sort_values(['sensor_uid','datetime']).reset_index(drop=True)
    original=panel.speed_mph.copy()
    panel,qa=run_qc(panel,speed_policy='flag_only')
    np.testing.assert_equal(panel.speed_mph.to_numpy(),original.to_numpy())
    return panel,qa


def detect(panel,cards,out,name='episodes_detected.csv'):
    ep=run_detectors(panel,('state_transition',),detection_smoothing=True)
    if ep.empty:return ep
    metadata=cards.set_index('sensor_uid')
    for col in ['C_vphpl','vf_mph','L_mi','dataset','sensor','lanes']:
        ep[col]=ep.sensor_uid.map(metadata[col])
    ep['holdout']=False
    daily=panel.groupby(['sensor_uid','date']).holdout.first()
    ep['holdout']=[bool(daily.loc[(s,d)]) for s,d in zip(ep.sensor_uid,ep.date)]
    ep['period']=ep.calibration_period
    ep['flow_source']='measured'
    ep['P_h']=ep.duration_min/60;ep['D_veh']=ep.episode_demand;ep['x_h']=ep.D_veh/ep.C_vphpl
    ep['vco_mph']=ep.threshold_used;ep['vt2_obs_mph']=ep.min_speed_mph
    ep['t0']=ep.t0_timestamp;ep['t2']=ep.t2_timestamp;ep['t3']=ep.t3_timestamp
    ep.to_csv(out/name,index=False)
    return ep
