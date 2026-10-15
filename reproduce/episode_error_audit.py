"""Read-only diagnostic reproduction of the retained 137-episode comparison."""
from pathlib import Path
import argparse,hashlib,json,math
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output',type=Path,default=ROOT/'reproduce/output/episode_error_audit')
args=ap.parse_args()
OUT=args.output.resolve()
for protected in [ROOT/'data',ROOT/'src',ROOT/'reproduce',ROOT/'tools']:
    if OUT == protected or protected.is_relative_to(OUT):
        raise ValueError('Choose a separate output directory')
if OUT.is_relative_to(ROOT/'data') or OUT.is_relative_to(ROOT/'src') or OUT.is_relative_to(ROOT/'tools'):
    raise ValueError('Output cannot overwrite data or source files')
if OUT.is_relative_to(ROOT/'reproduce') and not OUT.is_relative_to(ROOT/'reproduce/output'):
    raise ValueError('Within reproduce/, output must be under reproduce/output/')
marker=OUT/'.qvdfe-episode-audit.json'
if OUT.exists() and any(OUT.iterdir()) and not marker.is_file():
    raise ValueError('Output is not owned by this analysis; choose an empty directory')
(OUT/'support').mkdir(parents=True,exist_ok=True)
marker.write_text('{"workflow":"episode_error_audit"}\n')
SRC=ROOT/'data/frozen/calibration/average_weekday' 
pols=['CO2','NOx','CO','HC']
data=json.loads((ROOT/'data/inputs/detector78/calculation_inputs.json').read_text())
lower=np.array([r['speed_lower_mph'] for r in data['rate_table']])
rates={p:np.array([r[p+'_g_per_veh_h'] for r in data['rate_table']]) for p in pols}
u=np.array([r['u'] for r in data['quadrature_384']]);gl=np.array([r['weight'] for r in data['quadrature_384']])
co=pd.read_csv(SRC/'cubic_rate_coefficients.csv').set_index('pollutant')
def rate(v,p): return rates[p][np.searchsorted(lower,np.asarray(v),side='right')-1]
def cubic(v,p): return sum(co.loc[p,'c'+str(k)]*np.asarray(v)**k for k in range(4))
def score(o,e):
 o,e=np.asarray(o),np.asarray(e)
 return dict(N=len(o),WAPE_pct=100*np.abs(e-o).sum()/np.abs(o).sum(),bias_pct=100*(e.sum()/o.sum()-1),RMSE=float(np.sqrt(np.mean((e-o)**2))),R2=float(1-np.square(e-o).sum()/np.square(o-o.mean()).sum()))
ep=pd.read_csv(SRC/'episode_results_v2.csv',parse_dates=['t0','t2','t3'])
ep=ep.loc[ep.matched_ladder_pass.eq(True)].copy()
assert len(ep)==137
panel=pd.read_csv(SRC/'traffic_panel.csv.gz',parse_dates=['datetime'],low_memory=False)
panel['date']=panel.datetime.dt.strftime('%Y-%m-%d')
groups={k:g for k,g in panel.groupby(['sensor_uid','date'])}
rows=[];long=[];checks=[]
basecols=['episode_id','sensor_uid','date','paper_corridor','corridor','direction','period','dataset','calibration_scope','calibration_split','t0','t2','t3','D_veh','L_mi','C_vphpl','vf_mph','kj','x_h','P_h','P_hat_h','Tf_h','wt2_h','wt2_hat_h','wbar_h','wbar_hat_h','vq_mph','vq_hat_mph','fd','n','fp','s','theta','theta_observed','physical_observed_pass','profile_family','profile_shape_a']
for _,r in ep.iterrows():
 g=groups[(r.sensor_uid,r.date)]
 g=g[(g.datetime>=r.t0)&(g.datetime<r.t3)].sort_values('datetime')
 v=g.speed_mph.to_numpy(float);d=g.flow_vph.to_numpy(float)/12
 assert len(g)==round(r.P_h*12) and np.all(v>0) and np.all(d>=0)
 D=d.sum();L=r.L_mi;Tf=L/r.vf_mph;H=float(np.sum(d*L/v));Hp=D*(Tf+r.wbar_hat_h)
 wobs=H/D-Tf;vobs=D*L/H;vp=D*L/Hp
 meanv=float(np.average(v,weights=d));sd=float(np.sqrt(np.average((v-meanv)**2,weights=d)))
 a=r.profile_shape_a
 if r.theta>2/3:
  h=1-np.abs(2*u-1)**a;der=-2*a*np.sign(2*u-1)*np.abs(2*u-1)**(a-1);dermax=2*a
 else:
  h=(4*u*(1-u))**a;der=4*a*(1-2*u)*(4*u*(1-u))**(a-1)
  um=(1-1/np.sqrt(2*a-1))/2 if a>1+1e-9 else 0
  dermax=4*a*(1-2*um)*(4*um*(1-um))**(a-1) if a>1+1e-9 else 4
 Nj=D*gl*(1+r.wt2_hat_h/r.P_hat_h*der);tj=Tf+r.wt2_hat_h*h;vr=L/tj
 Tq=r.vf_mph*r.wbar_hat_h/(r.vf_mph-r.vq_hat_mph)
 Tfree=Tf-r.vq_hat_mph*r.wbar_hat_h/(r.vf_mph-r.vq_hat_mph)
 Tqobs=r.vf_mph*wobs/(r.vf_mph-r.vq_hat_mph)
 Tfreeobs=Tf-r.vq_hat_mph*wobs/(r.vf_mph-r.vq_hat_mph)
 bound=L/r.vq_hat_mph-Tf
 peakcf=wobs/r.theta
 mean_admissible=Tfreeobs>=0 and Tqobs>=0
 profile_admissible=mean_admissible and peakcf<=bound+1e-10 and peakcf/r.P_hat_h*dermax<=1+1e-10
 z={k:r[k] for k in basecols}
 z.update(bin_count=len(g),H_observed_veh_h=H,H_predicted_veh_h=Hp,H_reconstructed_quadrature_veh_h=float(np.sum(Nj*tj)),H_quadrature_minus_analytical_veh_h=float(np.sum(Nj*tj))-Hp,
   mean_trip_observed_min=H/D*60,mean_trip_predicted_min=Hp/D*60,mean_delay_observed_min=wobs*60,mean_delay_predicted_min=r.wbar_hat_h*60,
   mean_delay_error_pct=100*(r.wbar_hat_h/wobs-1),mean_delay_abs_error_min=abs(r.wbar_hat_h-wobs)*60,
   trip_time_error_pct=100*(Hp/H-1),trip_time_abs_error_pct=100*abs(Hp/H-1),
   peak_delay_error_pct=100*(r.wt2_hat_h/r.wt2_h-1),duration_error_pct=100*(r.P_hat_h/r.P_h-1),
   mean_speed_observed_mph=vobs,mean_speed_predicted_mph=vp,observed_speed_count_mean_mph=meanv,observed_speed_count_sd_mph=sd,observed_speed_count_cv=sd/meanv,
   observed_speed_min_mph=float(v.min()),observed_speed_max_mph=float(v.max()),observed_speed_range_mph=float(v.max()-v.min()),
   mean_delay_over_free_time=wobs/Tf,peak_delay_over_free_time=r.wt2_h/Tf,min_speed_over_free_speed=float(v.min()/r.vf_mph),
   predicted_free_time_min=Tfree*60,predicted_queue_time_min=Tq*60,predicted_free_VHT_share=Tfree/(Tf+r.wbar_hat_h),
   observed_delay_counterfactual_free_time_min=Tfreeobs*60,observed_delay_counterfactual_queue_time_min=Tqobs*60,
   observed_delay_counterfactual_mean_admissible=bool(mean_admissible),observed_delay_counterfactual_full_profile_admissible=bool(profile_admissible),
   lookup_band_mean_observed=int(np.searchsorted(lower,vobs,side='right')),lookup_band_mean_predicted=int(np.searchsorted(lower,vp,side='right')),
   mean_speed_crosses_rate_band=bool(np.searchsorted(lower,vobs,side='right')!=np.searchsorted(lower,vp,side='right')),
   flag_flat_profile_cv_le_010=bool(sd/meanv<=.10),flag_shallow_mean_delay_ratio_le_025=bool(wobs/Tf<=.25),flag_short_duration_le_1h=bool(r.P_h<=1),flag_large_trip_time_error_gt_10pct=bool(abs(Hp/H-1)>.10),flag_small_mean_delay_le_10s=bool(wobs*3600<=10))
 conditional_peak=Tf*r.fp*r.P_h**r.s
 z.update(conditional_peak_delay_h=conditional_peak,
   mean_delay_component_theta_h=(r.theta-r.theta_observed)*r.wt2_h,
   mean_delay_component_severity_h=r.theta*(conditional_peak-r.wt2_h),
   mean_delay_component_duration_h=r.theta*(r.wt2_hat_h-conditional_peak),
   total_vehicle_delay_observed_veh_h=D*wobs,total_vehicle_delay_predicted_veh_h=D*r.wbar_hat_h)
 assert abs(sum(z['mean_delay_component_'+k+'_h'] for k in ['theta','severity','duration'])-(r.wbar_hat_h-wobs))<1e-10
 errmax=0
 for name,got,expected in [('D',D,r.D_veh),('Tf',Tf,r.Tf_h),('wbar',wobs,r.wbar_h),('peak',L/v.min()-Tf,r.wt2_h),('mean_speed',vobs,r.space_mean_speed_mph),('P_hat',max(r.fd*r.x_h**r.n,r.x_h),r.P_hat_h),('peak_hat',Tf*r.fp*r.P_hat_h**r.s,r.wt2_hat_h)]:
  checks.append(dict(episode_id=r.episode_id,quantity=name,recomputed=got,saved=expected,absolute_difference=got-expected,relative_difference=(got-expected)/expected))
 for p in pols:
  O=float(r['O_'+p]);S=float(r['S_'+p]);R=float(r['R_'+p]);M=float(r['M_'+p]);A=float(r['A_'+p])
  rf=float(rate(r.vf_mph,p));rq=float(rate(r.vq_hat_mph,p));ro=float(rate(vobs,p));rp=float(rate(vp,p))
  gamma=(r.vf_mph*rq-r.vq_hat_mph*rf)/(r.vf_mph-r.vq_hat_mph)
  Ef=D*Tfree*rf;Eq=D*Tq*rq;Sp=Hp*rp
  Mcf=D*(Tf*rf+wobs*gamma)
  computed={'O':float(np.sum(d*L/v*rate(v,p))),'S':H*ro,'R':float(np.sum(Nj*tj*rate(vr,p))),'M':Ef+Eq,'A':D*(Tfree*cubic(r.vf_mph,p)+Tq*cubic(r.vq_hat_mph,p))}
  for m,got in computed.items():
   expected=float(r[m+'_'+p]);errmax=max(errmax,abs(got-expected)/abs(expected));checks.append(dict(episode_id=r.episode_id,quantity=m+'_'+p,recomputed=got,saved=expected,absolute_difference=got-expected,relative_difference=(got-expected)/expected))
  components=[S-O,Sp-S,R-Sp,M-R,A-M]
  steps=['observed_mean_rate','fitted_mean_delay_speed','reconstructed_speed_distribution','two_speed_allocation','cubic_rates']
  hh=(Hp-H)*(rp+ro)/2;rr=(rp-ro)*(Hp+H)/2
  assert abs(sum(components)-(A-O))<1e-7 and abs(hh+rr-(Sp-S))<1e-7
  ll={k:z[k] for k in ['episode_id','sensor_uid','date','paper_corridor','corridor','period']}
  ll.update(pollutant=p,O_g=O,S_g=S,S_pred_g=Sp,R_g=R,M_g=M,A_g=A,
   M_free_g=Ef,M_queue_g=Eq,M_free_emission_share=Ef/M,
   lookup_rate_observed_mean=ro,lookup_rate_predicted_mean=rp,lookup_rate_free=rf,lookup_rate_queue=rq,lookup_rate_free_queue_ratio=rf/rq,
   observed_effective_rate=O/H,predicted_M_effective_rate=M/Hp,rate_M_over_observed=(M/Hp)/(O/H),
   observed_bin_rate_time_cv=float(np.sqrt(np.average((rate(v,p)-O/H)**2,weights=d*L/v))/(O/H)),
   gamma_lookup=gamma,M_observed_delay_g=Mcf,M_observed_delay_mean_admissible=bool(mean_admissible),M_observed_delay_full_profile_admissible=bool(profile_admissible),
   predicted_chord_rate=(vp-r.vq_hat_mph)/(r.vf_mph-r.vq_hat_mph)*rf+(r.vf_mph-vp)/(r.vf_mph-r.vq_hat_mph)*rq,
   M_minus_S_pred_g=M-Sp,
   M_fixed_state_delay_component_g=M-Mcf,M_observed_delay_representation_residual_g=Mcf-O,
   fitted_mean_vehicle_hours_component_g=hh,fitted_mean_speed_rate_component_g=rr,
   M_vs_O_vehicle_hours_component_g=(Hp-H)*((M/Hp)+(O/H))/2,
   M_vs_O_effective_rate_component_g=((M/Hp)-(O/H))*(Hp+H)/2)
  for m,value in [('S',S),('S_pred',Sp),('R',R),('M',M),('A',A),('M_observed_delay',Mcf)]:
   ll[m+'_signed_error_pct']=100*(value/O-1);ll[m+'_absolute_error_pct']=100*abs(value/O-1)
  for m in ['M','A']:
   for s in ['S','S_pred']:
    diff=ll[m+'_absolute_error_pct']-ll[s+'_absolute_error_pct'];ll[m+'_minus_'+s+'_APE_pp']=diff;ll[m+'_worse_than_'+s]=bool(diff>1e-9)
  for step,c in zip(steps,components):ll[step+'_component_g']=c;ll[step+'_component_pct_O']=100*c/O
  ll['largest_M_accounting_component']=steps[int(np.argmax(np.abs(components[:4])))];ll['largest_A_accounting_component']=steps[int(np.argmax(np.abs(components)))];
  z.update({p+'_'+k:vv for k,vv in ll.items() if k not in ['episode_id','sensor_uid','date','paper_corridor','corridor','period','pollutant']});long.append(ll)
 z['maximum_emission_reproduction_relative_error']=errmax
 rows.append(z)
wide=pd.DataFrame(rows);long=pd.DataFrame(long);checks=pd.DataFrame(checks)
assert checks.relative_difference.abs().max()<1e-9
assert not wide.episode_id.duplicated().any()
OUT.mkdir(parents=True,exist_ok=True)
wide.to_csv(OUT/'episode_calculations_137.csv',index=False)
long.to_csv(OUT/'episode_pollutant_calculations_548.csv',index=False)
checks.to_csv(OUT/'support/reproduction_checks.csv',index=False)
metrics=[]
for sample,g in [('All 137',wide),('Arizona monthly',wide[wide.paper_corridor.eq('AZ_I10')]),('California released',wide[~wide.paper_corridor.eq('AZ_I10')])]:
 for p in pols:
  for m in ['S','S_pred','R','M','A']:
   metrics.append(dict(sample=sample,pollutant=p,method=m,**score(g[p+'_O_g'],g[p+'_'+m+'_g'])))
pd.DataFrame(metrics).to_csv(OUT/'comparison_metrics.csv',index=False)
traffic=[]
for y,pr,unit in [('P_h','P_hat_h','h'),('wt2_h','wt2_hat_h','h'),('wt2_h','conditional_peak_delay_h','h'),('wbar_h','wbar_hat_h','h'),('total_vehicle_delay_observed_veh_h','total_vehicle_delay_predicted_veh_h','veh h'),('H_observed_veh_h','H_predicted_veh_h','veh h'),('mean_speed_observed_mph','mean_speed_predicted_mph','mph')]:traffic.append(dict(observed=y,predicted=pr,unit=unit,**score(wide[y],wide[pr])))
pd.DataFrame(traffic).to_csv(OUT/'traffic_error_metrics.csv',index=False)
flags=['flag_flat_profile_cv_le_010','flag_shallow_mean_delay_ratio_le_025','flag_short_duration_le_1h','flag_large_trip_time_error_gt_10pct','mean_speed_crosses_rate_band','flag_small_mean_delay_le_10s']
group_rows=[]
for p in pols:
 for flag in flags:
  for value,g in wide.groupby(flag):
   group_rows.append(dict(pollutant=p,criterion=flag,flag_value=value,N=len(g),M_worse_than_S_count=int(g[p+'_M_worse_than_S'].sum()),M_worse_than_S_share=float(g[p+'_M_worse_than_S'].mean()),median_M_minus_S_APE_pp=float(g[p+'_M_minus_S_APE_pp'].median()),S_WAPE_pct=score(g[p+'_O_g'],g[p+'_S_g'])['WAPE_pct'],M_WAPE_pct=score(g[p+'_O_g'],g[p+'_M_g'])['WAPE_pct']))
pd.DataFrame(group_rows).to_csv(OUT/'diagnostic_groups.csv',index=False)
features=['trip_time_abs_error_pct','mean_delay_abs_error_min','observed_speed_count_cv','mean_delay_over_free_time','P_h','x_h','L_mi','predicted_free_VHT_share','vq_hat_mph']
corr=[]
for p in pols:
 y=wide[p+'_M_minus_S_APE_pp']
 for f in features:
  corr.append(dict(pollutant=p,feature=f,spearman=float(wide[f].rank().corr(y.rank())),pearson=float(wide[f].corr(y))))
pd.DataFrame(corr).to_csv(OUT/'diagnostic_correlations.csv',index=False)
corridor=[]
for name,g in wide.groupby('paper_corridor'):
 corridor.append(dict(corridor=name,N=len(g),M_worse_CO2=int(g.CO2_M_worse_than_S.sum()),M_worse_NOx=int(g.NOx_M_worse_than_S.sum()),S_CO2_WAPE=score(g.CO2_O_g,g.CO2_S_g)['WAPE_pct'],M_CO2_WAPE=score(g.CO2_O_g,g.CO2_M_g)['WAPE_pct'],trip_time_WAPE=score(g.H_observed_veh_h,g.H_predicted_veh_h)['WAPE_pct'],median_speed_CV=float(g.observed_speed_count_cv.median())))
pd.DataFrame(corridor).to_csv(OUT/'corridor_diagnostics.csv',index=False)
summary={'N_episodes':len(wide),'N_profile_blocks':wide[['sensor_uid','date']].drop_duplicates().shape[0],'N_bins':int(wide.bin_count.sum()),'sample_by_corridor':wide.paper_corridor.value_counts().to_dict(),'max_reproduction_relative_error':float(checks.relative_difference.abs().max()),'traffic_metrics':traffic,'emission_metrics':metrics[:20],
 'threshold_definitions':{'flat':'count-weighted speed CV <= 0.10','shallow':'observed mean delay/free time <= 0.25','short':'observed episode duration <=1h','large_trip_time_error':'absolute predicted total travel-time error >10%','small_absolute_delay':'observed mean delay <=10 seconds'},
 'flags':{f:int(wide[f].sum()) for f in flags},'counterfactual_mean_admissible':int(wide.observed_delay_counterfactual_mean_admissible.sum()),'counterfactual_full_profile_admissible':int(wide.observed_delay_counterfactual_full_profile_admissible.sum()),
 'source_sha256':{name:hashlib.sha256((SRC/name).read_bytes()).hexdigest() for name in ['episode_results_v2.csv','traffic_panel.csv.gz','cubic_rate_coefficients.csv']},'pollutants':{}}
for p in pols:
 g=long[long.pollutant.eq(p)];o=g.O_g.sum()
 summary['pollutants'][p]={'M_worse_than_S':int(g.M_worse_than_S.sum()),'A_worse_than_S':int(g.A_worse_than_S.sum()),'M_worse_than_S_pred':int(g.M_worse_than_S_pred.sum()),'A_worse_than_S_pred':int(g.A_worse_than_S_pred.sum()),
  'total_O_g':float(o),'M_signed_error_pct':float(100*(g.M_g.sum()/o-1)),
  'sum_signed_components_pct_O':{step:float(100*g[step+'_component_g'].sum()/o) for step in steps},
  'absolute_components_normalized_by_O_pct':{step:float(100*g[step+'_component_g'].abs().sum()/o) for step in steps},
  'M_VHT_component_pct_O':float(100*g.M_vs_O_vehicle_hours_component_g.sum()/o),'M_effective_rate_component_pct_O':float(100*g.M_vs_O_effective_rate_component_g.sum()/o),
  'M_observed_delay_all_algebraic':score(g.O_g,g.M_observed_delay_g),
  'M_observed_delay_valid_mean':score(g.loc[g.M_observed_delay_mean_admissible,'O_g'],g.loc[g.M_observed_delay_mean_admissible,'M_observed_delay_g']),
  'largest_M_component_counts':g.largest_M_accounting_component.value_counts().to_dict(),
  'M_free_emission_share_pooled':float(g.M_free_g.sum()/g.M_g.sum()),
  'observed_effective_rate_pooled':float(g.O_g.sum()/wide.H_observed_veh_h.sum()),'M_effective_rate_pooled':float(g.M_g.sum()/wide.H_predicted_veh_h.sum())}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
# A short review table is the entry point; the wide table retains every calculation.
reviewcols=['episode_id','paper_corridor','direction','period','date','t0','t3','D_veh','L_mi','P_h','P_hat_h','mean_delay_observed_min','mean_delay_predicted_min','mean_delay_error_pct','trip_time_error_pct','peak_delay_error_pct','observed_speed_count_cv','mean_delay_over_free_time','mean_speed_observed_mph','mean_speed_predicted_mph','vf_mph','vq_hat_mph']
review=wide[reviewcols].copy()
for p in pols:
 for k in ['S_absolute_error_pct','M_absolute_error_pct','M_worse_than_S','A_worse_than_S']:
  review[p+'_'+k]=wide[p+'_'+k]
review['CO2_M_minus_S_APE_pp']=wide.CO2_M_minus_S_APE_pp
review['CO2_largest_accounting_component']=wide.CO2_largest_M_accounting_component
review['CO2_diagnostic_labels']=['; '.join(([('accurate mean delay' if abs(r.mean_delay_error_pct)<=10 else 'mean-delay error above 10%')]+(['flat recorded speeds'] if r.flag_flat_profile_cv_le_010 else [])+(['short episode'] if r.flag_short_duration_le_1h else [])+(['mean-speed lookup band changes'] if r.mean_speed_crosses_rate_band else []))) for _,r in wide.iterrows()]
review=review.sort_values('CO2_M_minus_S_APE_pp',ascending=False)
review.insert(0,'CO2_gap_rank',np.arange(1,len(review)+1))
review.to_csv(OUT/'episode_review_137.csv',index=False)
cfmetrics=[]
for maskname,mask in [('mean_admissible_133',wide.observed_delay_counterfactual_mean_admissible),('full_profile_admissible_110',wide.observed_delay_counterfactual_full_profile_admissible),('mean_delay_error_within_10pct',wide.mean_delay_error_pct.abs()<=10)]:
 g=wide[mask]
 for p in pols:
  for m in ['S','S_pred','M','M_observed_delay']:
   cfmetrics.append(dict(sample=maskname,pollutant=p,method=m,**score(g[p+'_O_g'],g[p+'_'+m+'_g'])))
pd.DataFrame(cfmetrics).to_csv(OUT/'counterfactual_metrics.csv',index=False)
# A compact explanation accompanies every exported column rather than requiring source-code knowledge.
desc={
 'episode_id':'Stable episode identifier from the retained paper experiment.',
 'wbar_h':'Observed count-weighted mean link delay: sum[d*(L/v - L/vf)] / D (h).',
 'wt2_h':'Observed peak link delay: L/min(recorded speed) - L/vf (h).',
 'wbar_hat_h':'Predicted mean delay = theta * predicted peak delay (h).',
 'wt2_hat_h':'Predicted peak delay = Tf * fp * P_hat^s (h).',
 'P_hat_h':'Predicted episode duration = max(fd * (D/C)^n, D/C) (h).',
 'vq_hat_mph':'Predicted queued operating speed from mu=D/P_hat and the calibrated triangular flow-density relation.',
 'observed_speed_count_cv':'Count-weighted SD of recorded 5-min speeds / count-weighted arithmetic mean speed.',
 'mean_delay_over_free_time':'Observed mean delay / free-flow link time. Descriptive congestion severity.',
 'predicted_free_VHT_share':'Predicted free-flow state time / predicted total link time.',
 'conditional_peak_delay_h':'Tf*fp*P_observed^s: peak-delay prediction substituting observed duration only.',
 'mean_delay_component_theta_h':'(fitted theta - observed theta) * observed peak delay; signed path component in hours/vehicle.',
 'mean_delay_component_severity_h':'fitted theta * (conditional peak delay - observed peak delay); signed path component in hours/vehicle.',
 'mean_delay_component_duration_h':'fitted theta * (predicted peak delay - conditional peak delay); signed path component in hours/vehicle.',
 'mean_speed_crosses_rate_band':'Observed and predicted episode mean speeds fall in different lookup-rate bands.',
 'observed_delay_counterfactual_mean_admissible':'Replacing predicted mean delay by observed mean delay keeps mean free/queue times nonnegative. Not a full-trajectory guarantee.',
 'observed_delay_counterfactual_full_profile_admissible':'Same fitted shape and duration, with peak rescaled to observed mean delay, meets finite-link and nonnegative-arrival constraints.',
}
suffixes={
 'O_g':'Reference: sum over recorded bins of d * L/v * lookup(v), grams.',
 'S_g':'Observed mean-speed method: H_obs * lookup(D*L/H_obs), grams.',
 'S_pred_g':'Predicted-mean diagnostic: H_pred * lookup(D*L/H_pred), grams; same fitted travel time as two-speed.',
 'R_g':'Reconstructed whole-trip speed integration using 384-node quadrature, grams.',
 'M_g':'Two operating speeds with lookup rates, grams.',
 'A_g':'Two operating speeds with cubic rates, grams.',
 'M_observed_delay_g':'Algebraic counterfactual holding predicted vf/vq rates fixed and replacing only mean delay by observed mean delay. Read admissibility flags.',
 'M_fixed_state_delay_component_g':'M - M_observed_delay = D*(w_pred-w_obs)*Gamma; conditional on fixed queue speed and rates.',
 'M_observed_delay_representation_residual_g':'M_observed_delay - O; not a uniquely identified physical approximation error.',
 'predicted_chord_rate':'Linear interpolation of rates at fitted queue speed and free-flow speed, evaluated at predicted mean speed (g/veh h); exactly M/H_pred.',
 'M_minus_S_pred_g':'Difference at identical fitted vehicle-hours, count and distance; equals H_pred*(predicted_chord_rate-lookup_rate_predicted_mean).',
 'M_vs_O_vehicle_hours_component_g':'Exact symmetric product split: (H_pred-H_obs)*(r_M_eff+r_O_eff)/2.',
 'M_vs_O_effective_rate_component_g':'Exact symmetric product split: (r_M_eff-r_O_eff)*(H_pred+H_obs)/2; includes speed/rate representation and interacting calibration effects.',
 'observed_mean_rate_component_g':'S-O.',
 'fitted_mean_delay_speed_component_g':'S_pred-S.',
 'reconstructed_speed_distribution_component_g':'R-S_pred.',
 'two_speed_allocation_component_g':'M-R; travel times held equal up to quadrature precision.',
 'cubic_rates_component_g':'A-M.',
 'largest_M_accounting_component':'Largest absolute signed contribution among S-O, S_pred-S, R-S_pred, M-R. Ordered accounting, not causal label.',
 'largest_A_accounting_component':'Largest absolute signed contribution among the five successive differences. Ordered accounting, not causal label.'}
dictionary=[]
for c in wide.columns:
 definition=desc.get(c,'')
 for p in pols:
  if c.startswith(p+'_'):
   sf=c[len(p)+1:];definition=suffixes.get(sf,'')
   if sf.endswith('_worse_than_S'):definition='True if this method has larger episode absolute error than observed single-speed S; strict tolerance 1e-9 percentage points.'
   elif sf.endswith('_worse_than_S_pred'):definition='True if this method has larger episode absolute error than predicted single-speed S_pred.'
   elif sf.endswith('_signed_error_pct'):definition='100 * (method emission / O - 1).'
   elif sf.endswith('_absolute_error_pct'):definition='100 * abs(method emission / O - 1); episode APE, not pooled WAPE.'
   elif sf.endswith('_APE_pp'):definition='First method APE minus comparison method APE, percentage points; positive means first method is worse.'
   elif sf.endswith('_component_pct_O'):definition='Corresponding signed component in grams / O *100. Components add with signs, not after taking absolute values.'
   if definition:definition=p+': '+definition
 if not definition:
  if c.startswith('flag_'):definition='Descriptive threshold stated in the column name; not an exclusion rule or proof of causality.'
  else:definition=c.replace('_',' ')+'. Units/operation follow the column name; original traffic fields retain their archived meaning.'
 dictionary.append(dict(column=c,definition=definition))
pd.DataFrame(dictionary).to_csv(OUT/'column_definitions.csv',index=False)
print(json.dumps({'episodes':len(wide),'columns':len(wide.columns),'bins':int(wide.bin_count.sum()),'max_reproduction_relative_error':summary['max_reproduction_relative_error'],'counts':{p:{k:summary['pollutants'][p][k] for k in ['M_worse_than_S','A_worse_than_S','M_worse_than_S_pred']} for p in pols}},indent=2))
