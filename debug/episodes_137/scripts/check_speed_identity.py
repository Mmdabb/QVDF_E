"""Recompute FD/QVDF inputs and audit the two-speed average-speed identity."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

from _paths import ROOT, arguments
args = arguments(__doc__)
OUT = args.output
SOURCE = ROOT / 'data/frozen/calibration/average_weekday/episode_results_v2.csv'
ep = pd.read_csv(SOURCE)
ep = ep.loc[ep.matched_ladder_pass.eq(True)].copy()
assert len(ep) == 137
u, _ = np.polynomial.legendre.leggauss(384)
u = np.sort(np.r_[0., .5, 1., (u + 1.) / 2.])
rows = []
for r in ep.itertuples():
    L, vf, C, kj, D = r.L_mi, r.vf_mph, r.C_vphpl, r.kj, r.D_veh
    x = D / C
    P = max(r.fd * x ** r.n, x)
    mu = D / P
    omega = C / (kj - C / vf)
    kq = kj - mu / omega
    vq = mu / kq
    Tf = L / vf
    peak = Tf * r.fp * P ** r.s
    wbar = r.theta * peak
    a = r.profile_shape_a
    h = 1 - np.abs(2*u-1)**a if r.theta > 2/3 else (4*u*(1-u))**a
    w = peak * h
    tq = vf * w / (vf-vq)
    tf = Tf - vq * w / (vf-vq)
    lhs = (vf*tf + vq*tq) / (tf+tq)
    rhs = L / (Tf+w)
    bound = L * (1/vq-1/vf)
    bound_fd = L * kj * (1/mu-1/C)
    tq_mean = vf * wbar / (vf-vq)
    tf_mean = Tf - vq * wbar / (vf-vq)
    tf_peak = Tf - vq * peak / (vf-vq)
    rows.append({
        'episode_id':r.episode_id,'sensor_uid':r.sensor_uid,'date':r.date,
        'corridor':r.corridor,'period':r.period,'D_veh':D,'L_mi':L,
        'vf_mph':vf,'capacity_vphpl':C,'jam_density_veh_per_mi_lane':kj,
        'P_recomputed_h':P,'mu_recomputed_vphpl':mu,'vq_recomputed_mph':vq,
        'vq_saved_mph':r.vq_hat_mph,'vq_recomputation_abs_difference_mph':abs(vq-r.vq_hat_mph),
        'free_flow_travel_time_h':Tf,'peak_delay_recomputed_h':peak,
        'peak_delay_saved_h':r.wt2_hat_h,'mean_delay_recomputed_h':wbar,
        'delay_allowance_h':bound,'delay_allowance_from_mu_h':bound_fd,
        'peak_delay_allowance_ratio':peak/bound,'peak_delay_margin_h':bound-peak,
        'peak_free_state_time_h':tf_peak,'mean_free_state_time_h':tf_mean,
        'mean_queue_state_time_h':tq_mean,
        'mean_speed_two_state_mph':(vf*tf_mean+vq*tq_mean)/(tf_mean+tq_mean),
        'mean_speed_delay_formula_mph':L/(Tf+wbar),
        'profile_min_average_speed_mph':float(rhs.min()),
        'profile_max_average_speed_mph':float(rhs.max()),
        'profile_max_identity_abs_error_mph':float(np.max(np.abs(lhs-rhs))),
        'profile_max_distance_abs_error_mi':float(np.max(np.abs(vf*tf+vq*tq-L))),
        'profile_max_time_abs_error_h':float(np.max(np.abs(tf+tq-(Tf+w)))),
        'profile_min_free_state_time_h':float(tf.min()),
        'profile_min_queue_state_time_h':float(tq.min()),
        'fd_state_pass':bool(0 < mu < C and 0 < vq < vf),
        'continuous_finite_link_pass':bool(0 <= peak <= bound + 1e-10),
        'profile_identity_pass':bool(np.allclose(lhs,rhs,rtol=1e-12,atol=1e-12)),
        'profile_nonnegative_times_pass':bool(np.all(tf >= -1e-10) and np.all(tq >= -1e-10)),
        'profile_average_speed_between_states_pass':bool(np.all(rhs >= vq-1e-10) and np.all(rhs <= vf+1e-10)),
    })
result = pd.DataFrame(rows)
result.to_csv(OUT/'average_speed_identity_check_137.csv',index=False)
summary = {
    'source':SOURCE.relative_to(ROOT).as_posix(),
    'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'episodes':len(result),'profile_points_per_episode':len(u),
    'profile_points_total':len(result)*len(u),
    'profile_points':'384 Gauss-Legendre locations plus both endpoints and the peak',
    'recomputed_inputs':'x=D/C; P=max(fd*x**n,x); mu=D/P; omega=C/(kj-C/vf); vq=mu/(kj-mu/omega); peak=(L/vf)*fp*P**s; w(t)=peak*h(t/P)',
    'time_split':'tq=vf*w/(vf-vq); tf=L/vf-vq*w/(vf-vq)',
    'meaning':'Checks a model identity and finite-link compatibility, not agreement with measured vehicle trajectories. The speed on both sides is whole-link traversal speed.',
    'pass_counts':{c:int(result[c].sum()) for c in result if c.endswith('_pass')},
    'max_speed_identity_error_mph':float(result.profile_max_identity_abs_error_mph.max()),
    'max_distance_error_mi':float(result.profile_max_distance_abs_error_mi.max()),
    'max_total_time_error_h':float(result.profile_max_time_abs_error_h.max()),
    'max_FD_speed_recomputation_error_mph':float(result.vq_recomputation_abs_difference_mph.max()),
    'max_QVDF_peak_recomputation_error_h':float((result.peak_delay_recomputed_h-result.peak_delay_saved_h).abs().max()),
    'max_bound_identity_error_h':float((result.delay_allowance_h-result.delay_allowance_from_mu_h).abs().max()),
    'largest_peak_delay_allowance_ratio':float(result.peak_delay_allowance_ratio.max()),
    'smallest_peak_free_state_time_seconds':float(result.peak_free_state_time_h.min()*3600),
}
assert all(v == 137 for v in summary['pass_counts'].values())
(OUT/'support/average_speed_identity_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
