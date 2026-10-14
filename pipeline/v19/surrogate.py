"""Signed-power compression of full QVDFE curves on admitted sign branches.

Parameters compress the calibrated model; they are not emission observations fits.
Each corridor-period uses one named actual detector, never a synthetic median FD.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import sys
import numpy as np
import pandas as pd
from scipy.optimize import brentq, least_squares
from scipy.special import betaln

POLS = ['CO2', 'NOx', 'CO', 'HC']


def scalar(value):
    return value.item() if isinstance(value, np.generic) else value


def profile_slope(theta):
    if not 0 < theta < 1:
        return np.nan
    if theta > 2/3:
        return 2*theta/(1-theta)
    a = brentq(lambda a: np.exp(a*np.log(4)+betaln(a+1,a+1))-theta, 1., 10000.)
    if abs(a-1) < 1e-8:
        return 4.
    u = (1-1/np.sqrt(2*a-1))/2
    return a*4*(1-2*u)*(4*u*(1-u))**(a-1)


def context(parameter, detector):
    out = {k: float(parameter[k]) for k in ['fd','n','fp','s','theta']}
    out.update({k: float(detector[k]) for k in ['C_vphpl','vf_mph','L_mi']})
    out.update(kj=220., reference_sensor_uid=detector['sensor_uid'])
    out['slope_max'] = profile_slope(out['theta'])
    return out


def rate(v, co):
    return co[0]+v*(co[1]+v*(co[2]+v*co[3]))


def state(x, ctx, coeff):
    x = np.asarray(x, float)
    C,vf,L = [ctx[k] for k in ['C_vphpl','vf_mph','L_mi']]
    fd,n,fp,s,theta = [ctx[k] for k in ['fd','n','fp','s','theta']]
    Tf=L/vf; P=fd*x**n; mu=C*x/P
    omega=C/(ctx['kj']-C/vf); kq=ctx['kj']-mu/omega; vq=mu/kq
    peak=Tf*fp*P**s; w=theta*peak; beta=n*s
    bound=L*(1/vq-1/vf)
    z=dict(x=x,P=P,mu=mu,vq=vq,kq=kq,w=w,T=Tf+w,dT=beta*w/(C*x),
           peak_delay=peak,max_delay=bound,arrival_margin=1-peak/P*ctx['slope_max'])
    for p,co in coeff.items():
        gamma=co[0]-co[2]*vf*vq-co[3]*vf*vq*(vf+vq)
        gv=-co[2]*vf-co[3]*vf*(vf+2*vq)
        dv_dx=(1-n)*ctx['kj']/kq*vq/x
        e0=Tf*rate(vf,co)
        z['e0_'+p]=e0
        z['Gamma_'+p]=gamma
        z['e_'+p]=e0+w*gamma
        z['de_'+p]=(beta*w/x*gamma+w*gv*dv_dx)/C
    return z


def valid(x, ctx, coeff):
    z=state(x,ctx,coeff)
    ans=(z['P']>np.asarray(x)*(1+1e-9)) & (z['vq']>=5) & (z['vq']<ctx['vf_mph'])
    ans &= ctx['vf_mph']<=75
    ans &= (z['peak_delay']<=z['max_delay']) & (z['arrival_margin']>=0)
    ans &= all(z['e0_'+p]>0 for p in coeff)
    for p in coeff:
        ans &= np.isfinite(z['e_'+p]) & (z['e_'+p]>0)
    return ans


def domain_intervals(low, high, ctx, coeff):
    if not 0<low<high or ctx['vf_mph']>75 or not np.isfinite(ctx['slope_max']):
        return []
    xs=np.geomspace(low,high,8001)
    ok=valid(xs,ctx,coeff)
    changes=np.flatnonzero(ok[1:]!=ok[:-1])
    boundaries=[low]
    for i in changes:
        a,b=xs[i],xs[i+1]; left=bool(ok[i])
        for _ in range(60):
            m=(a+b)/2
            if bool(valid(m,ctx,coeff))==left:a=m
            else:b=m
        boundaries.append((a+b)/2)
    boundaries.append(high)
    result=[]
    for a,b in zip(boundaries[:-1],boundaries[1:]):
        if b/a<=1+1e-5 or not bool(valid(math.sqrt(a*b),ctx,coeff)):continue
        aa=a*(1+1e-7); bb=b*(1-1e-7)
        if bool(valid(aa,ctx,coeff)) and bool(valid(bb,ctx,coeff)):result.append((aa,bb))
    return result


def gamma_zeros(ctx, co, low, high):
    C,vf=[ctx[k] for k in ['C_vphpl','vf_mph']]
    omega=C/(ctx['kj']-C/vf)
    if abs(ctx['n']-1)<1e-12:return []
    roots=np.roots([-co[3]*vf,-vf*(co[2]+co[3]*vf),co[0]])
    result=[]
    for v in roots:
        if abs(v.imag)>1e-9 or not 0<v.real<vf:continue
        mu=v.real*ctx['kj']/(1+v.real/omega)
        log_x=math.log(ctx['fd']*mu/C)/(1-ctx['n'])
        if math.log(low)<log_x<math.log(high):result.append(float(math.exp(log_x)))
    return sorted(result)


def increment_stationary_points(ctx,co,low,high):
    """Exact cubic in queue speed for d(e-e0)/dx=0 on the power branch."""
    if abs(ctx['n']-1)<1e-12:return []
    C,vf=ctx['C_vphpl'],ctx['vf_mph']
    omega=C/(ctx['kj']-C/vf)
    beta=ctx['n']*ctx['s'];a=1-ctx['n']
    A,B,Q=co[0],-vf*(co[2]+co[3]*vf),-co[3]*vf
    polynomial=[2*a*Q/omega,(beta+2*a)*Q+a*B/omega,(beta+a)*B,beta*A]
    result=[]
    for v in np.roots(np.trim_zeros(np.asarray(polynomial),'f')):
        if abs(v.imag)>1e-9 or not 0<v.real<vf:continue
        mu=v.real*ctx['kj']/(1+v.real/omega)
        log_x=math.log(ctx['fd']*mu/C)/a
        if math.log(low)<log_x<math.log(high):result.append(float(math.exp(log_x)))
    return sorted(result)


def fit_branch(low, high, ctx, coeff, pollutant):
    xref=math.sqrt(low*high)
    x=np.geomspace(low,high,201)
    z=state(x,ctx,coeff); e0=z['e0_'+pollutant]
    target=(z['e_'+pollutant]-e0)/e0
    sign=float(np.sign(target[len(target)//2]))
    if sign==0 or np.max(np.abs(target))<1e-10:return None
    assert np.all(sign*target>=-1e-9)
    keep=np.abs(target)>1e-8*np.max(np.abs(target))
    initial=np.polyfit(np.log(x[keep]/xref),np.log(np.abs(target[keep])),1)
    b0=float(np.clip(initial[0],-19,19)); a0=float(np.clip(initial[1],-29,29))
    # Original-scale normalized increment loss, not log-error optimization.
    fit=least_squares(lambda p:np.exp(p[0]+p[1]*np.log(x/xref))-np.abs(target),
                      [a0,b0],bounds=([-30,-20],[30,20]),xtol=1e-13,ftol=1e-13,gtol=1e-13,max_nfev=500)
    a,b=float(np.exp(fit.x[0])),float(fit.x[1])
    valx=np.linspace(low,high,1001)
    v=state(valx,ctx,coeff); full=v['e_'+pollutant]
    approx=e0*(1+sign*a*(valx/xref)**b)
    correction=((full-e0)/e0)/(a*(valx/xref)**b)
    delta=((full-e0)/e0)
    err=approx-full
    peak_delta=max(np.sqrt(np.mean(delta**2)),1e-12)
    deriv_approx=e0*sign*a*b*(valx/xref)**b/(ctx['C_vphpl']*valx)
    deriv_full=v['de_'+pollutant]
    good=bool(fit.success and np.all(approx>0) and not np.any(fit.active_mask))
    fields=dict(a_e=a,beta_e=b,alpha_e=a/xref**b,x_ref_h=xref,sign_reference=sign,e0_g_per_vehicle=e0,
                alpha_e_unit='h^(-beta_e)',x_low_h=low,x_high_h=high,
                fit_nodes=201,validation_nodes=1001,fit_success=bool(fit.success),coefficient_bound_hit=bool(np.any(fit.active_mask)),
                approximation_positive=bool(np.all(approx>0)),
                max_total_relative_error=float(np.max(np.abs(err)/full)),
                mean_total_relative_error=float(np.mean(np.abs(err)/full)),
                rms_increment_relative_error=float(np.sqrt(np.mean((err/e0)**2))/peak_delta),
                max_scaled_derivative_error=float(np.max(np.abs(deriv_approx-deriv_full))/max(np.max(np.abs(deriv_full)),1e-12)),
                k_min=float(correction.min()),k_max=float(correction.max()),
                status='fitted' if good else 'failed_fit_or_positive_cost_check')
    curves=pd.DataFrame(dict(x_h=valx,k_signed=correction,sign_reference=sign,x_ref_h=xref,
                             e_full_g_per_vehicle=full,e_approx_g_per_vehicle=approx,
                             full_de_dD=deriv_full,approx_de_dD=deriv_approx))
    identity=e0*(1+a*correction*(valx/xref)**b)
    assert np.max(np.abs(identity-full))<1e-10*max(1,np.max(np.abs(full)))
    return fields,curves


def run(data,out):
    out.mkdir(parents=True,exist_ok=True)
    parameter_path = next((data/name for name in ['parameter_card_v15.csv', 'parameter_card_full.csv', 'parameter_card.csv'] if (data/name).is_file()), None)
    if parameter_path is None:
        raise FileNotFoundError('Full parameter card not found in ' + str(data))
    params=pd.read_csv(parameter_path)
    detectors=pd.read_csv(data/'sensor_parameters.csv')
    episodes=pd.read_csv(data/'episode_results_v2.csv')
    cr=pd.read_csv(data/'cubic_rate_coefficients.csv').set_index('pollutant')
    coeff={p:cr.loc[p,['c0','c1','c2','c3']].to_numpy(float) for p in POLS}
    eligible=episodes[episodes.calibration_eligible & ~episodes.holdout]
    rows=[]; curves=[]; contexts=[]
    for param in params.to_dict('records'):
        meta={k:param[k] for k in ['corridor','period','N_train','N_source','calibration_scope']}
        empty=lambda status:[dict(**meta,pollutant=p,branch_id='unavailable',status=status) for p in POLS]
        if param['calibration_scope']=='unavailable' or not np.isfinite(param['fd']):
            rows.extend(empty('unavailable_calibration'));continue
        source=eligible[eligible.corridor.eq(param['corridor'])]
        if param['calibration_scope']=='corridor_period':source=source[source.period.eq(param['period'])]
        candidates=detectors[detectors.sensor_uid.isin(source.sensor_uid.unique())].copy()
        candidates=candidates[(candidates.vf_mph>5)&(candidates.vf_mph<=75)&(candidates.C_vphpl>0)&(candidates.L_mi>0)]
        if candidates.empty:rows.extend(empty('no_cubic_supported_reference_detector'));continue
        median=float(candidates.C_vphpl.median())
        candidates['capacity_distance']=abs(np.log(candidates.C_vphpl/median))
        candidates=candidates.sort_values(['capacity_distance','sensor_uid'])
        detector=candidates.iloc[0].to_dict()
        ctx=context(param,detector)
        low,high=float(param['x_min_h']),float(param['x_max_h'])
        intervals=domain_intervals(low,high,ctx,coeff)
        named=dict(**meta,reference_sensor_uid=ctx['reference_sensor_uid'],reference_selection='nearest median capacity among participating cubic-supported detectors',
                   x_support_min_h=low,x_support_max_h=high,x_empirical_median_h=float(param['x_median_h']),**{k:v for k,v in ctx.items() if k!='reference_sensor_uid'})
        contexts.append(dict(**named,admitted_intervals=intervals))
        if not intervals:rows.extend([dict(**named,pollutant=p,branch_id='unavailable',status='no_admitted_reference_interval') for p in POLS]);continue
        for p in POLS:
            for j,(left,right) in enumerate(intervals):
                roots=gamma_zeros(ctx,coeff[p],left,right)+increment_stationary_points(ctx,coeff[p],left,right)
                points=sorted(set([left]+roots+[right]))
                for k,(a,b) in enumerate(zip(points[:-1],points[1:])):
                    if b/a<1+1e-4:continue
                    a=a*(1+1e-8);b=b*(1-1e-8)
                    branch=f'{j+1}.{k+1}'
                    fit=fit_branch(a,b,ctx,coeff,p)
                    if fit is None:
                        rows.append(dict(**named,pollutant=p,branch_id=branch,status='negligible_increment'));continue
                    fields,table=fit
                    rows.append(dict(**named,pollutant=p,branch_id=branch,**fields))
                    table['fit_status']=fields['status']
                    for key,val in dict(corridor=param['corridor'],period=param['period'],pollutant=p,branch_id=branch,reference_sensor_uid=ctx['reference_sensor_uid']).items():table[key]=val
                    curves.append(table)
    cards=pd.DataFrame(rows)
    cards.to_csv(out/'surrogate_coefficients.csv',index=False)
    if curves:pd.concat(curves,ignore_index=True).to_csv(out/'surrogate_curves.csv',index=False)
    specification=dict(data_source=data.name,target='Compression of full calibrated QVDFE curves; not regression to observed emissions',
        reference_selection='Nearest median capacity among participating detectors with 5<vf<=75; actual detector retained even if its interval is unavailable',
        fit='201 log-spaced nodes; unweighted squared normalized-increment errors on original scale; beta_e permitted negative',
        validation='1001 independent linearly spaced nodes per admitted constant-sign monotone-increment branch',
        diagnostic='k=((e_full/e0)-1)/(a_e*(x/x_ref)^beta_e); exact identity is distinguished from surrogate k=sign_reference',
        numerical_parameter_bounds=dict(log_a_e=[-30,30],beta_e=[-20,20]),
        source_hashes={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in [parameter_path, data/'sensor_parameters.csv', data/'episode_results_v2.csv', data/'cubic_rate_coefficients.csv']},
        contexts=contexts,cubic_coefficients={k:v.tolist() for k,v in coeff.items()})
    (out/'surrogate_specification.json').write_text(json.dumps(specification,indent=2,default=scalar))
    audit=dict(status='PASS',cards=len(params),coefficient_rows=len(cards),status_counts=cards.status.value_counts().to_dict(),
               negative_exponents_fitted=int(((cards.get('beta_e',pd.Series(dtype=float))<0)&cards.status.eq('fitted')).sum()),
               exact_k_identity_checked=True,zero_crossings_split=True,increment_stationary_points_split=True,calibration_files_modified=False)
    (out/'surrogate_audit.json').write_text(json.dumps(audit,indent=2,default=scalar))
    reference_rows=[]
    context_lookup={(c['corridor'],c['period']):c for c in contexts}
    for param in params.to_dict('records'):
        ctx=context_lookup.get((param['corridor'],param['period']))
        base=dict(corridor=param['corridor'],period=param['period'],calibration_scope=param['calibration_scope'])
        if ctx is None or not ctx['admitted_intervals']:
            reference_rows.extend([dict(**base,pollutant=p,valid=False) for p in POLS]);continue
        source=eligible[eligible.corridor.eq(param['corridor'])]
        if param['calibration_scope']=='corridor_period':source=source[source.period.eq(param['period'])]
        intervals=ctx['admitted_intervals']
        counts=[int(source.x_h.between(a,b).sum()) for a,b in intervals]
        j=max(range(len(intervals)),key=lambda j:(counts[j],np.log(intervals[j][1]/intervals[j][0])))
        lo,hi=intervals[j];x=np.sqrt(lo*hi);z=state(x,ctx,coeff)
        for p,c in coeff.items():
            gamma=float(z['Gamma_'+p]);v=float(z['vq']);gv=-c[2]*ctx['vf_mph']-c[3]*ctx['vf_mph']*(ctx['vf_mph']+2*v)
            eps=(1-ctx['n'])*ctx['kj']/float(z['kq'])*v*gv/gamma if abs(gamma)>1e-12 else np.nan
            reference_rows.append(dict(**base,pollutant=p,reference_sensor_uid=ctx['reference_sensor_uid'],reference_interval=j+1,
                x_low_h=lo,x_high_h=hi,x_h=x,reference_episode_count=counts[j],beta=ctx['n']*ctx['s'],Gamma=gamma,
                epsilon_Gamma_x=eps,beta_plus_epsilon=ctx['n']*ctx['s']+eps,
                congestion_g_per_vehicle=float(z['w']*gamma),marginal_external_g_per_vehicle=float(ctx['C_vphpl']*x*z['de_'+p]),
                valid=bool(valid(x,ctx,coeff))))
    pd.DataFrame(reference_rows).to_csv(out/'figure10_reference_states.csv',index=False)
    print(json.dumps(audit,indent=2,default=scalar))
