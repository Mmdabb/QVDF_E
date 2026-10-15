"""Independent emission-attribution review; does not modify paper results."""
from pathlib import Path
import hashlib
import json
import math
import sys
import numpy as np
import pandas as pd

from _paths import ROOT, arguments
args = arguments(__doc__)
OUT = args.output
sys.path.insert(0, str(ROOT / 'src'))
from qvdfe.pipeline._engine.emissions import load_moves_rates
from qvdfe.pipeline._engine.two_regime_emissions import exact_rate_for_speed, cubic_rate

SOURCE = ROOT / 'data/frozen/calibration/average_weekday/episode_results_v2.csv'
COMPACT = ROOT / 'data/inputs/detector78/calculation_inputs.json'
ep = pd.read_csv(SOURCE)
ep = ep[ep.matched_ladder_pass.eq(True)].reset_index(drop=True)
assert len(ep) == 137
cfg = json.loads(COMPACT.read_text())
rate_table = pd.DataFrame(cfg['rate_table'])
moves = load_moves_rates(ROOT / 'data/frozen/calibration/emission_input')
co_table = pd.read_csv(ROOT / 'data/frozen/calibration/average_weekday/cubic_rate_coefficients.csv').set_index('pollutant')
POLS = ['CO2', 'NOx', 'CO', 'HC']
def r(v,p):
    return exact_rate_for_speed(moves,np.asarray(v,dtype=float),'NOX' if p=='NOx' else p)
def rcompact(v,p):
    ix = np.searchsorted(rate_table.speed_lower_mph.to_numpy(), np.asarray(v),side='right')-1
    return rate_table[p+'_g_per_veh_h'].to_numpy()[ix]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def scores(y,p):
    y,p=np.asarray(y,float),np.asarray(p,float)
    return {'n':len(y),'total_reference':float(y.sum()),'total_prediction':float(p.sum()),
      'WAPE_pct':float(100*np.abs(p-y).sum()/np.abs(y).sum()),
      'bias_pct':float(100*(p.sum()/y.sum()-1)),
      'R2':float(1-np.sum((p-y)**2)/np.sum((y-y.mean())**2)),
      'median_absolute_percentage_error':float(np.median(100*np.abs(p-y)/y))}
def distribution(v):
    v=np.asarray(v,float);v=v[np.isfinite(v)]
    return {'n':len(v),'min':float(np.min(v)),'q25':float(np.quantile(v,.25)),
      'median':float(np.median(v)),'q75':float(np.quantile(v,.75)),'max':float(np.max(v))}
def corr(a,b):
    return float(np.corrcoef(pd.Series(a).rank(),pd.Series(b).rank())[0,1])
def profile_closure(P,peak,theta):
    if theta>2/3:
        maximum=2*theta/(1-theta)
    else:
        low,high=1.,10000.
        for _ in range(70):
            a=(low+high)/2
            area=math.exp(a*math.log(4)+2*math.lgamma(a+1)-math.lgamma(2*a+2))
            if area>theta:low=a
            else:high=a
        a=(low+high)/2
        if abs(a-1)<1e-9:maximum=4.
        else:
            umax=(1-1/math.sqrt(2*a-1))/2
            maximum=a*4*(1-2*umax)*(4*umax*(1-umax))**(a-1)
    return peak/P*maximum<=1+1e-10

D=ep.D_veh.to_numpy();L=ep.L_mi.to_numpy();Tf=ep.Tf_h.to_numpy()
vf=ep.vf_mph.to_numpy();vq=ep.vq_hat_mph.to_numpy()
wobs=ep.wbar_h.to_numpy();what=ep.wbar_hat_h.to_numpy()
Hobs=D*(Tf+wobs);Hpred=D*(Tf+what)
vobs=D*L/Hobs;vpred=D*L/Hpred
bound=L*(1/vq-1/vf)
Tqpred=vf*what/(vf-vq);Tfpred=Tf-vq*what/(vf-vq)
Tqcorr=vf*wobs/(vf-vq);Tfcorr=Tf-vq*wobs/(vf-vq)
mean_admissible=(wobs>=0)&(Tfcorr>=-1e-10)&(Tqcorr>=-1e-10)&(vq>0)&(vq<vf)
peak_corr=wobs/ep.theta.to_numpy()
profile_geometry=peak_corr<=bound+1e-10
closure=np.array([profile_closure(float(P),float(w),float(theta))
    for P,w,theta in zip(ep.P_hat_h,peak_corr,ep.theta)])
profile_admissible=mean_admissible&profile_geometry&closure
observed_vq=ep.vq_mph.to_numpy()
obsq_valid=(observed_vq>0)&(observed_vq<vf)
obsq_bound=L*(1/observed_vq-1/vf)
obsq_mean_admissible=obsq_valid&(wobs<=obsq_bound+1e-10)

results={'source':SOURCE.relative_to(ROOT).as_posix(),'source_sha256':sha(SOURCE),'n':len(ep),
 'methodology':{
  'target':'Diagnostic differences relative to the five-minute link-speed proxy O, not measured trajectory or exhaust truth.',
  'S_pred':'D*(Tf+wbar_hat)*r0(L/(Tf+wbar_hat)); same predicted count, distance, VHT as M.',
  'M_mean_corrected':'D*(Tf*r0(vf)+wbar_observed*Gamma(vq_hat,vf)); queue speed remains predicted.',
  'A_mean_corrected':'D*(Tf*rc(vf)+wbar_observed*Gamma_c(vq_hat,vf)); queue speed remains predicted.',
  'mean_correction_admissibility':'0<vq_hat<vf and 0<=wbar_observed<=L*(1/vq_hat-1/vf). No clamping; invalid cases excluded from counterfactual scores.',
  'profile_admissibility':'Stricter optional profile: peak_corrected=wbar_observed/theta; peak_corrected<=bound; nonnegative reconstructed arrivals with fixed P_hat/theta.',
  'exact_M_decomposition':'M-O = D*(wbar_hat-wbar_observed)*Gamma_hat + (M_mean_corrected-O). The latter includes rate allocation and queue-speed estimation, not pure emission approximation.',
  'same_time_chord_identity':'M-S_pred = H_pred*[((v_pred-vq)/(vf-vq))*r0(vf) + ((vf-v_pred)/(vf-vq))*r0(vq) - r0(v_pred)].',
  'same_observed_time_chord_identity':'M_mean_corrected-S = H_obs*[linear rate chord through (vq_hat,rq),(vf,rf) at v_obs-r0(v_obs)]. Applicable only to mean-admissible counterfactual.',
  'caution':'Signed accounting differences depend on the specified counterfactual and order. They are not independent causal effects; absolute errors and WAPE components do not add.'},
 'rate_validation':{},'traffic':{},'pollutants':{},'episode_counterfactuals':[]}

results['traffic']={'observed_VHT_sum':float(Hobs.sum()),'predicted_VHT_sum':float(Hpred.sum()),
 'VHT_scores':scores(Hobs,Hpred),'mean_delay_vehicle_hour_scores':scores(D*wobs,D*what),
 'mean_delay_unweighted_scores':scores(wobs,what),
 'mean_correction_admissible_n':int(mean_admissible.sum()),
 'full_corrected_profile_admissible_n':int(profile_admissible.sum()),
 'corrected_profile_geometry_pass_n':int(profile_geometry.sum()),
 'corrected_profile_closure_pass_n':int(closure.sum()),
 'observed_queue_and_mean_admissible_n':int(obsq_mean_admissible.sum()),
 'mean_delay_relative_error_pct':distribution(100*(what/wobs-1)),
 'predicted_free_time_share':distribution(Tfpred/(Tf+what)),
 'observed_mean_speed_equals_saved':bool(np.allclose(vobs,ep.space_mean_speed_mph,rtol=1e-12)),
 'mean_correction_invalid_episodes':ep.loc[~mean_admissible,['episode_id','corridor','period','wbar_h','predicted_bound_h','vq_hat_mph','space_mean_speed_mph']].to_dict('records'),
 'full_profile_correction_invalid_n':int((~profile_admissible).sum())}
episode_extra=[]
for i,row in ep.iterrows():
    episode_extra.append({'episode_id':row.episode_id,'corridor':row.corridor,'period':row.period,
      'H_obs_veh_h':float(Hobs[i]),'H_pred_veh_h':float(Hpred[i]),
      'v_obs_mph':float(vobs[i]),'v_pred_mph':float(vpred[i]),
      'M_mean_corrected_admissible':bool(mean_admissible[i]),
      'M_corrected_profile_admissible':bool(profile_admissible[i]),
      'M_observed_queue_mean_admissible':bool(obsq_mean_admissible[i])})

feature_arrays={'abs_VHT_relative_error':np.abs(Hpred/Hobs-1),
 'abs_mean_delay_relative_error':np.abs(what/wobs-1),
 'abs_peak_delay_relative_error':np.abs(ep.wt2_hat_h/ep.wt2_h-1).to_numpy(),
 'abs_duration_relative_error':np.abs(ep.P_hat_h/ep.P_h-1).to_numpy(),
 'observed_mean_delay_over_Tf':wobs/Tf,
 'observed_peak_delay_over_Tf':ep.wt2_h.to_numpy()/Tf,
 'observed_duration_h':ep.P_h.to_numpy(),
 'predicted_free_time_share':Tfpred/(Tf+what),
 'predicted_queue_speed_mph':vq}

for p in POLS:
    O=ep['O_'+p].to_numpy();S=ep['S_'+p].to_numpy();R=ep['R_'+p].to_numpy()
    M=ep['M_'+p].to_numpy();A=ep['A_'+p].to_numpy()
    rf=r(vf,p);rq=r(vq,p);ro=r(vobs,p);rp=r(vpred,p)
    Spred=Hpred*rp
    gamma=(vf*rq-vq*rf)/(vf-vq)
    Mcorr=D*(Tf*rf+wobs*gamma)
    coefficients=co_table.loc[p,['c0','c1','c2','c3']].to_numpy()
    rfc=cubic_rate(vf,coefficients);rqc=cubic_rate(vq,coefficients)
    gc=(vf*rqc-vq*rfc)/(vf-vq)
    Acorr=D*(Tf*rfc+wobs*gc)
    roq=r(observed_vq,p)
    go=(vf*roq-observed_vq*rf)/(vf-observed_vq)
    Mobsq=D*(Tf*rf+wobs*go)
    allspeeds=np.r_[vf,vq,vobs,vpred]
    compact_error=np.max(np.abs(r(allspeeds,p)-rcompact(allspeeds,p)))
    assert compact_error<1e-8
    assert np.allclose(M,D*(Tf*rf+what*gamma),rtol=1e-11,atol=1e-8)
    assert np.allclose(S,Hobs*ro,rtol=1e-11,atol=1e-8)
    assert np.allclose(A,D*(Tf*rfc+what*gc),rtol=1e-11,atol=1e-8)
    chord=((vpred-vq)*rf+(vf-vpred)*rq)/(vf-vq)
    assert np.allclose(M-Spred,Hpred*(chord-rp),rtol=1e-10,atol=1e-7)
    delay_component=D*(what-wobs)*gamma
    fixed_mean_component=Mcorr-O
    assert np.allclose(M-O,delay_component+fixed_mean_component,rtol=1e-10,atol=1e-7)
    worse=np.abs(M-O)>np.abs(S-O)+1e-10
    worsepred=np.abs(M-O)>np.abs(Spred-O)+1e-10
    errgap=np.abs(M-O)/O-np.abs(S-O)/O
    eq_q_obs=np.isclose(rq,ro,rtol=1e-12,atol=1e-10)
    eq_q_pred=np.isclose(rq,rp,rtol=1e-12,atol=1e-10)
    same_mode=np.isclose(ro,rp,rtol=1e-12,atol=1e-10)
    grouping={}
    for gname,gmask in [('M_worse_than_S',worse),('M_not_worse_than_S',~worse)]:
        grouping[gname]={'n':int(gmask.sum()),'features':{k:distribution(v[gmask]) for k,v in feature_arrays.items()},
          'obs_mean_and_queue_same_rate_n':int((eq_q_obs&gmask).sum()),
          'pred_mean_and_queue_same_rate_n':int((eq_q_pred&gmask).sum()),
          'M_bias_pct':float(100*(M[gmask].sum()/O[gmask].sum()-1)),
          'S_bias_pct':float(100*(S[gmask].sum()/O[gmask].sum()-1))}
    result={'scores_all':{name:scores(O,vals) for name,vals in [('S',S),('S_pred',Spred),('R',R),('M',M),('A',A)]},
      'M_worse_than_S_n':int(worse.sum()),'M_worse_than_S_pred_n':int(worsepred.sum()),
      'A_worse_than_S_n':int((np.abs(A-O)>np.abs(S-O)+1e-10).sum()),
      'A_worse_than_S_pred_n':int((np.abs(A-O)>np.abs(Spred-O)+1e-10).sum()),
      'M_greater_than_S_pred_n':int((M>Spred+1e-10).sum()),
      'M_mean_corrected_vs_S_on_admissible':{
        'n':int(mean_admissible.sum()),'M_worse_than_S_n':int((np.abs(Mcorr-O)[mean_admissible]>np.abs(S-O)[mean_admissible]+1e-10).sum()),
        'M_original':scores(O[mean_admissible],M[mean_admissible]),
        'M_mean_corrected':scores(O[mean_admissible],Mcorr[mean_admissible]),
        'A_original':scores(O[mean_admissible],A[mean_admissible]),
        'A_mean_corrected':scores(O[mean_admissible],Acorr[mean_admissible]),
        'S':scores(O[mean_admissible],S[mean_admissible])},
      'M_mean_and_queue_corrected_on_admissible':{'n':int(obsq_mean_admissible.sum()),
        'M_observed_queue_and_mean':scores(O[obsq_mean_admissible],Mobsq[obsq_mean_admissible]),
        'M_original':scores(O[obsq_mean_admissible],M[obsq_mean_admissible]),
        'S':scores(O[obsq_mean_admissible],S[obsq_mean_admissible])},
      'signed_telescope_total':{'O_to_S':float(np.sum(S-O)),'S_to_S_pred':float(np.sum(Spred-S)),
        'S_pred_to_R':float(np.sum(R-Spred)),'R_to_M':float(np.sum(M-R)),'M_to_A':float(np.sum(A-M))},
      'original_M_error_decomposition_all_algebraic':{
        'delay_component_sum':float(delay_component.sum()),'fixed_mean_component_sum':float(fixed_mean_component.sum()),
        'delay_component_sum_absolute':float(np.abs(delay_component).sum()),
        'fixed_mean_component_sum_absolute':float(np.abs(fixed_mean_component).sum()),
        'opposite_sign_components_n':int((delay_component*fixed_mean_component<0).sum()),
        'warning':'Algebraic identity is valid for all137; the fixed-mean term is not a feasible two-speed counterfactual in inadmissible episodes.'},
      'obs_mean_and_queue_same_rate_n':int(eq_q_obs.sum()),
      'pred_mean_and_queue_same_rate_n':int(eq_q_pred.sum()),
      'observed_to_predicted_mean_changes_rate_bin_n':int((~same_mode).sum()),
      'negative_Gamma_n':int((gamma<0).sum()),
      'M_free_flow_emission_share':distribution(D*Tfpred*rf/M),
      'M_over_S_pred_ratio':distribution(M/Spred),
      'rank_correlations_with_excess_absolute_relative_error_M_minus_S':{k:corr(v,errgap) for k,v in feature_arrays.items()},
      'groups':grouping}
    results['pollutants'][p]=result
    results['rate_validation'][p]={'compact_vs_original_loader_max_abs_rate_difference':float(compact_error),
      'M_reconstruction_max_relative_error':float(np.max(np.abs(D*(Tf*rf+what*gamma)/M-1))),
      'A_reconstruction_max_relative_error':float(np.max(np.abs(D*(Tf*rfc+what*gc)/A-1)))}
    for i in range(len(ep)):
        episode_extra[i][p]={'S_pred':float(Spred[i]),'M_mean_corrected':float(Mcorr[i]) if mean_admissible[i] else None,
          'A_mean_corrected':float(Acorr[i]) if mean_admissible[i] else None,
          'M_observed_queue_and_mean':float(Mobsq[i]) if obsq_mean_admissible[i] else None,
          'M_worse_than_S':bool(worse[i]),'M_worse_than_S_pred':bool(worsepred[i]),
          'mean_delay_component_algebraic':float(delay_component[i]),
          'fixed_observed_mean_component_algebraic':float(fixed_mean_component[i]),
          'cubic_component_A_minus_M':float(A[i]-M[i]),
          'same_time_rate_chord_gap':float(chord[i]-rp[i]),
          'observed_mean_and_queue_same_rate':bool(eq_q_obs[i]),
          'predicted_mean_and_queue_same_rate':bool(eq_q_pred[i]),
          'M_free_flow_emission_share':float(D[i]*Tfpred[i]*rf[i]/M[i])}

results['episode_counterfactuals']=episode_extra
out=OUT/'support/attribution_review.json'
out.write_text(json.dumps(results,indent=2,allow_nan=False))
print(json.dumps({'output':str(out),'traffic':results['traffic'],
 'pollutants':{p:{k:results['pollutants'][p][k] for k in ['scores_all','M_worse_than_S_n','M_worse_than_S_pred_n','M_mean_corrected_vs_S_on_admissible','negative_Gamma_n','obs_mean_and_queue_same_rate_n','pred_mean_and_queue_same_rate_n']} for p in POLS}},indent=2))
