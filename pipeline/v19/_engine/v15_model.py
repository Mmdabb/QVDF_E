"""Cumulative-volume QVDF experiment, with explicit failed-state accounting.

No rolling-hour demand, split-episode target, recovery-discharge predictor, or
synthetic traffic is used. California records are average profiles, not days.
"""
from pathlib import Path
import json, logging
from functools import lru_cache
import numpy as np
import pandas as pd
from scipy.optimize import least_squares, brentq
from scipy.special import betaln
from numpy.polynomial.legendre import leggauss
from .emissions import load_moves_rates, fit_cubic_surrogates
from .two_regime_emissions import exact_rate_for_speed, gamma_from_rate, gamma_from_cubic, cubic_rate
from .v15_data import DT, PERIODS, period_of

LOG=logging.getLogger('qvdfe_cbi')
POLS=['CO2','NOx','CO','HC']
PARAMS=['fd','n','fp','s','theta','alpha','beta']

def rate(moves,v,p):
    return exact_rate_for_speed(moves,np.asarray(v,dtype=float),'NOX' if p=='NOx' else p)

def scores(y,p):
    y=np.asarray(y,float);p=np.asarray(p,float);ok=np.isfinite(y)&np.isfinite(p)
    y=y[ok];p=p[ok]
    return dict(N=len(y),R2=1-np.sum((p-y)**2)/np.sum((y-y.mean())**2) if len(y)>1 and np.std(y)>0 else np.nan,
        RMSE=np.sqrt(np.mean((p-y)**2)) if len(y) else np.nan,
        bias_pct=100*(p.sum()/y.sum()-1) if len(y) and y.sum()!=0 else np.nan,
        WAPE_pct=100*np.abs(p-y).sum()/np.abs(y).sum() if len(y) and np.abs(y).sum()>0 else np.nan)

def qvdf(x,fd,n,fp,s,theta):
    x=np.asarray(x,float);P=np.maximum(fd*x**n,x)
    return P,fp*P**s,theta*fp*P**s

def queue_speed(mu,C,vf,kj=220.):
    omega=C/(kj-C/vf);kq=kj-mu/omega
    return np.divide(mu,kq),kq,omega

@lru_cache(maxsize=512)
def profile_shape(theta):
    """Symmetric closed profile h(u)=[4u(1-u)]^a with integral theta."""
    if not 0<theta<1:return np.nan
    return brentq(lambda a:np.exp(a*np.log(4)+betaln(a+1,a+1))-theta,.00001,10000)

@lru_cache(maxsize=4)
def quadrature(nodes):
    z,w=leggauss(nodes)
    return (z+1)/2,w/2

def profile_grid(P,peak,theta,nodes=384):
    u,w=quadrature(nodes)
    # Both families have bounded endpoint slopes and meet at the parabola.
    # Using fractional powers of u at high theta would manufacture infinite
    # recovery slopes and reject broad average-day queues by construction.
    if theta>2/3:
        a=theta/(1-theta);h=1-np.abs(2*u-1)**a
        derivative=-2*a*np.sign(2*u-1)*np.abs(2*u-1)**(a-1)
        maximum=2*a
    else:
        a=profile_shape(theta);h=(4*u*(1-u))**a
        derivative=a*4*(1-2*u)*(4*u*(1-u))**(a-1)
        if abs(a-1)<1e-9:maximum=4.
        else:
            umax=(1-1/np.sqrt(2*a-1))/2
            maximum=a*4*(1-2*umax)*(4*umax*(1-umax))**(a-1)
    lam_factor=1+peak/P*derivative
    admissible=np.isfinite(maximum) and peak/P*maximum<=1+1e-10
    return u,w,h,lam_factor,a,admissible,float(1-peak/P*maximum)

def observed_targets(ep,panel,cards):
    groups={k:g.sort_values('datetime') for k,g in panel.groupby(['sensor_uid','date'])}
    records=[];metadata=cards.set_index('sensor_uid')
    for r in ep.to_dict('records'):
        g=groups[(r['sensor_uid'],r['date'])]
        z=g[(g.datetime>=r['t0'])&(g.datetime<r['t3'])]
        v=z.speed_mph.to_numpy(float);q=z.flow_vph.to_numpy(float)
        expected=round(r['P_h']/DT)
        complete=len(z)==expected and np.isfinite(v).all() and np.isfinite(q).all()
        valid=complete and (v>0).all() and (v<=90).all() and (q>=0).all()
        D=float(np.sum(q)*DT) if np.isfinite(q).all() else np.nan
        r['D_veh']=D;r['x_h']=D/r['C_vphpl'];r['mu_vphpl']=D/r['P_h']
        r['Tf_h']=r['L_mi']/r['vf_mph']
        r['wt2_h']=r['L_mi']/np.min(v)-r['Tf_h'] if valid else np.nan
        r['wbar_h']=np.sum(q*(r['L_mi']/v-r['Tf_h']))/np.sum(q) if valid and D>0 else np.nan
        r['theta_observed']=r['wbar_h']/r['wt2_h'] if r['wt2_h']>0 else np.nan
        r['vt2_obs_mph']=np.min(v) if valid else r['vt2_obs_mph']
        r['kj']=float(metadata.loc[r['sensor_uid'],'kj'])
        r['vq_mph'],r['kq'],r['omega_mph']=queue_speed(r['mu_vphpl'],r['C_vphpl'],r['vf_mph'],r['kj'])
        r['observed_bound_h']=r['L_mi']*(1/r['vq_mph']-1/r['vf_mph'])
        r['physical_observed_pass']=bool(valid and 0<r['vq_mph']<r['vf_mph'] and r['wt2_h']<=r['observed_bound_h']+1e-10)
        # A detector-day boundary is a censored observation, not a newly split
        # target claimed to be a whole closed queue.
        r['day_boundary_censored']=r['t0'].hour==0 and r['t0'].minute==0 or r['t3'].date()>r['t0'].date()
        r['incomplete_episode']=not complete
        r['invalid_observed_speed_or_flow']=not valid
        r['metadata_capacity_flag']=bool(metadata.loc[r['sensor_uid'],'metadata_capacity_flag'])
        r['qc_hard_fail']=bool(not valid or D<=0 or r['wt2_h']<=0 or not 0<r['theta_observed']<1
            or r['day_boundary_censored'] or r['metadata_capacity_flag'])
        r['qc_reason']=';'.join(k for k in ['incomplete_episode','invalid_observed_speed_or_flow','day_boundary_censored','metadata_capacity_flag'] if r[k])
        records.append(r)
    return pd.DataFrame(records)

def robust_line(x,y):
    X=np.column_stack([np.ones(len(x)),x]);b=np.linalg.lstsq(X,y,rcond=None)[0]
    for _ in range(15):
        e=y-X@b;scale=max(1.4826*np.median(np.abs(e-np.median(e))),.03)
        w=np.minimum(1,1.35*scale/np.maximum(abs(e),1e-12))
        new=np.linalg.lstsq(X*np.sqrt(w[:,None]),y*np.sqrt(w),rcond=None)[0]
        if np.max(np.abs(new-b))<1e-8:break
        b=new
    return b

def add_outlier_flags(ep):
    ep=ep.copy();ep['outlier_votes']=0
    relationships=[('x_h','P_h'),('P_h','wt2_h'),('x_h','mu_obs_vphpl')]
    for corridor,g in ep.groupby('corridor'):
        train=g[~g.holdout & ~g.qc_hard_fail]
        if len(train)<8:continue
        for x,y in relationships:
            z=train[(train[x]>0)&(train[y]>0)&np.isfinite(train[y])]
            if len(z)<8:continue
            b=robust_line(np.log(z[x].to_numpy()),np.log(z[y].to_numpy()))
            resid=np.log(z[y])-(b[0]+b[1]*np.log(z[x]));center=np.median(resid)
            scale=max(1.4826*np.median(np.abs(resid-center)),.10)
            target=np.log(g[y].where(g[y]>0))-(b[0]+b[1]*np.log(g[x].where(g[x]>0)))
            flag=(np.abs(target-center)>3.5*scale).fillna(False)
            ep.loc[g.index,'outlier_votes']+=flag.astype(int)
        center=np.median(np.log(train.P_h));scale=max(1.4826*np.median(np.abs(np.log(train.P_h)-center)),.2)
        ep.loc[g.index,'outlier_votes']+=(np.abs(np.log(g.P_h)-center)>3.5*scale).astype(int)
    ep['qc_outlier_fail']=ep.outlier_votes.ge(2)
    ep['calibration_eligible']=~(ep.qc_hard_fail|ep.qc_outlier_fail)
    return ep

def fit_parameters(g):
    x=g.x_h.to_numpy();p=g.P_h.to_numpy();severity=(g.wt2_h/g.Tf_h).to_numpy()
    lx=np.log(x);lp=np.log(p)
    initial=robust_line(lx,lp);initial=np.clip(initial,[-6,.15],[6,4])
    fit=least_squares(lambda b:np.maximum(b[0]+b[1]*lx,lx)-lp,initial,bounds=([-6,.15],[6,4]),loss='soft_l1',f_scale=.2,max_nfev=80)
    b=robust_line(lp,np.log(severity));s=float(np.clip(b[1],.05,6))
    # Reestimate the intercept when a slope bound is active.
    fp=float(np.exp(np.median(np.log(severity)-s*lp)))
    theta=float(np.median(g.theta_observed));fd=float(np.exp(fit.x[0]));n=float(fit.x[1])
    return dict(fd=fd,n=n,fp=fp,s=s,theta=theta,alpha=theta*fp*fd**s,beta=n*s)

def calibrate(ep,cards,out,bootstrap):
    train=ep[ep.calibration_eligible&~ep.holdout];rows=[];draws=[];rng=np.random.default_rng(15020910)
    for corridor in cards.corridor.unique():
        for period in PERIODS:
            local=train[train.corridor.eq(corridor)&train.period.eq(period)]
            source=local;scope='corridor_period'
            if len(source)<8:
                source=train[train.corridor.eq(corridor)];scope='corridor_all_periods'
            row=dict(corridor=corridor,period=period,N_train=len(local),N_source=len(source),calibration_scope=scope)
            if len(source)<8:
                row.update({k:np.nan for k in PARAMS});row['calibration_scope']='unavailable';rows.append(row);continue
            params=fit_parameters(source);row.update(params)
            row.update(x_min_h=source.x_h.min(),x_max_h=source.x_h.max(),x_median_h=source.x_h.median(),
                lower_branch_share=float(np.mean(params['fd']*source.x_h**params['n']<=source.x_h)),
                fd_unit='h^(1-n)',fp_unit='h^(-s)',alpha_unit='h^(-beta)',
                bootstrap_unit='sensor-day' if corridor=='AZ_I10_W' else 'released link profile')
            units=source.groupby(['sensor_uid','date'],sort=False).indices
            blocks=list(units.values());nblocks=len(blocks);bs=[]
            for i in range(bootstrap):
                ix=np.concatenate([blocks[j] for j in rng.integers(0,nblocks,nblocks)])
                b=fit_parameters(source.iloc[ix]);b.update(corridor=corridor,period=period,draw=i)
                bs.append(b);draws.append(b)
            bdf=pd.DataFrame(bs)
            for k in PARAMS:
                row[k+'_lo'],row[k+'_hi']=np.quantile(bdf[k],[.025,.975])
            rows.append(row)
        LOG.info('Calibrated %s with %s bootstrap replicates per supported period',corridor,bootstrap)
    result=pd.DataFrame(rows);result.to_csv(out/'parameter_card_v15.csv',index=False)
    draws=pd.DataFrame(draws);draws.to_csv(out/'parameter_bootstrap.csv.gz',index=False)
    return result,draws

def predictions(ep,parameters):
    ep=ep.merge(parameters[['corridor','period','calibration_scope']+PARAMS],on=['corridor','period'],validate='many_to_one')
    ep['P_hat_h'],severity,wmean=qvdf(ep.x_h,ep.fd,ep.n,ep.fp,ep.s,ep.theta)
    ep['wt2_hat_h']=ep.Tf_h*severity;ep['wbar_hat_h']=ep.Tf_h*wmean
    ep['wt2_conditional_hat_h']=ep.Tf_h*ep.fp*ep.P_h**ep.s
    ep['vt2_hat_mph']=ep.vf_mph/(1+severity)
    ep['mu_hat_vphpl']=ep.D_veh/ep.P_hat_h
    ep['k_mu']=ep.x_h/ep.P_hat_h
    ep['vq_hat_mph'],ep['kq_hat'],_=queue_speed(ep.mu_hat_vphpl,ep.C_vphpl,ep.vf_mph,ep.kj)
    ep['predicted_bound_h']=ep.L_mi*(1/ep.vq_hat_mph-1/ep.vf_mph)
    ep['lower_branch']=ep.fd*ep.x_h**ep.n<=ep.x_h*(1+1e-10)
    ep['near_capacity']=ep.k_mu.gt(.95)
    ep['physical_predicted_pass']=(ep.vq_hat_mph.gt(0)&ep.vq_hat_mph.lt(ep.vf_mph*(1-1e-10))
        &ep.wt2_hat_h.le(ep.predicted_bound_h+1e-10))
    ep['physical_pass']=ep.physical_observed_pass
    ep['physical_failure_reason']=np.select([ep.lower_branch,~ep.vq_hat_mph.between(0,ep.vf_mph,inclusive='neither'),
        ep.wt2_hat_h.gt(ep.predicted_bound_h)],['capacity_branch_with_positive_delay','invalid_queue_speed','queue_exceeds_link'],default='')
    ep['calibration_split']=np.where(ep.holdout,'later_date',np.where(ep.corridor.eq('AZ_I10_W'),'training','released_profile_fit'))
    return ep

def emission_ladder(ep,panel,moves,coeff):
    groups={k:g.sort_values('datetime') for k,g in panel.groupby(['sensor_uid','date'])}
    records=[]
    for r in ep.to_dict('records'):
        g=groups[(r['sensor_uid'],r['date'])];g=g[(g.datetime>=r['t0'])&(g.datetime<r['t3'])]
        v=g.speed_mph.to_numpy();q=g.flow_vph.to_numpy();D=r['D_veh'];L=r['L_mi'];vf=r['vf_mph'];Tf=r['Tf_h']
        observable=not r['invalid_observed_speed_or_flow'] and D>0
        valid=r['physical_predicted_pass'] and r['calibration_eligible']
        r['profile_closed_pass']=False;r['arrival_min_relative']=np.nan;r['conservation_error_veh']=np.nan
        r['theta_quadrature_error']=np.nan;r['profile_shape_a']=np.nan
        if valid:
            u,w,h,lam,a,closed,minlam=profile_grid(r['P_hat_h'],r['wt2_hat_h'],r['theta'])
            r['profile_shape_a']=a;r['profile_closed_pass']=closed;r['arrival_min_relative']=minlam
            r['profile_family']='flat_top_power' if r['theta']>2/3 else 'beta_power'
            r['conservation_error_veh']=D*(np.sum(w*lam)-1)
            r['theta_quadrature_error']=np.sum(w*lam*h)-r['theta']
            vr=L/(Tf+r['wt2_hat_h']*h)
            weights=D*w*lam
        meanv=np.sum(q)/np.sum(q/v) if observable else np.nan
        r['space_mean_speed_mph']=meanv
        domain=valid and 5<=r['vq_hat_mph']<vf<=75
        r['cubic_domain_pass']=domain
        for p in POLS:
            co=coeff[p];rf=float(rate(moves,vf,p));rfc=float(cubic_rate(vf,co))
            r['O_'+p]=float(np.sum(q*DT*L/v*rate(moves,v,p))) if observable else np.nan
            r['S_'+p]=float(D*L/meanv*rate(moves,meanv,p)) if observable else np.nan
            r['R_'+p]=float(np.sum(weights*L/vr*rate(moves,vr,p))) if valid and closed else np.nan
            # Keep signed Gamma and signed congestion increments. M itself must
            # be positive for log ratios; no zero truncation or sign repair.
            gamma=float(gamma_from_rate(r['vq_hat_mph'],vf,lambda a:rate(moves,a,p))) if valid else np.nan
            gammac=float(gamma_from_cubic(r['vq_hat_mph'],vf,co)) if domain else np.nan
            r['Gamma_'+p]=gamma;r['Gamma_cubic_'+p]=gammac
            r['congestion_'+p]=D*r['wbar_hat_h']*gamma
            r['M_'+p]=D*Tf*rf+r['congestion_'+p]
            r['A_'+p]=D*(Tf*rfc+r['wbar_hat_h']*gammac)
            r['congestion_share_'+p]=r['congestion_'+p]/r['M_'+p] if r['M_'+p]>0 else np.nan
        r['matched_ladder_pass']=bool(valid and r['profile_closed_pass'] and domain and all(np.isfinite(r[k+'_'+p]) and r[k+'_'+p]>0 for p in POLS for k in ['O','R','M','A','S']))
        records.append(r)
    return pd.DataFrame(records)

def period_table(ep,panel,moves,average=False):
    panel=panel.copy();panel['period']=[period_of(x) for x in panel.datetime.dt.hour+panel.datetime.dt.minute/60]
    daily_ep={k:g for k,g in ep.groupby(['sensor_uid','date'])};rows=[]
    for (sid,date,period),g in panel.groupby(['sensor_uid','date','period'],sort=False):
        r=g.iloc[0];q=g.flow_vph.to_numpy();v=g.speed_mph.to_numpy();H=PERIODS[period][1]-PERIODS[period][0]
        complete=len(g)==round(H/DT) and np.isfinite(q).all() and np.isfinite(v).all() and (v>0).all() and (v<=90).all() and (q>=0).all()
        V=np.sum(q)*DT if np.isfinite(q).all() else np.nan;D=0.;increments={p:0. for p in POLS};all_valid=True
        occupied=np.zeros(len(g),bool)
        for e in daily_ep.get((sid,date),pd.DataFrame()).to_dict('records'):
            mask=((g.datetime>=e['t0'])&(g.datetime<e['t3'])).to_numpy()
            assert not (occupied&mask).any(),'Overlapping episode volumes in period accounting'
            occupied|=mask;overlap=np.sum(q[mask])*DT
            if mask.any():
                D+=overlap
                if not e['calibration_eligible'] or not e['physical_predicted_pass'] or not e['profile_closed_pass'] or not np.isfinite(e['D_veh']) or e['D_veh']<=0:
                    all_valid=False
                else:
                    for p in POLS:increments[p]+=e['congestion_'+p]*overlap/e['D_veh']
        row=dict(sensor_uid=sid,corridor=r.corridor,sensor=sid.split('::')[-1],date='AVG' if average else date,
            period=period,H_h=H,flow_source='measured',holdout=bool(r.holdout),is_average_day=average,
            V_veh=V,D_veh=D,QDF=D/V if V>0 else np.nan,complete_observations=complete,
            all_episodes_valid=all_valid,period_model_pass=complete and all_valid,dataset=r.dataset)
        meanv=V/np.sum(q*DT/v) if complete and V>0 else np.nan
        for p in POLS:
            rf=float(rate(moves,r.vf_mph,p));base=V*r.L_mi/r.vf_mph*rf
            row['O_H_'+p]=float(np.sum(q*DT*r.L_mi/v*rate(moves,v,p))) if complete else np.nan
            row['S_H_'+p]=float(V*r.L_mi/meanv*rate(moves,meanv,p)) if complete and V>0 else np.nan
            row['M_H_'+p]=base+increments[p] if complete and all_valid else np.nan
        rows.append(row)
    result=pd.DataFrame(rows)
    assert not result.duplicated(['sensor_uid','date','period','is_average_day']).any()
    return result

def cost_values(params,x,C,vf,L,co,kj=220.):
    fd,n,fp,s,theta=[params[k] for k in ['fd','n','fp','s','theta']]
    P,severity,_=qvdf(x,fd,n,fp,s,theta);mu=C*x/P;vq,kq,_=queue_speed(mu,C,vf,kj)
    peak=L/vf*severity;bound=L*(1/vq-1/vf)
    power=fd*x**n>x*(1+1e-10)
    if not power or not 5<=vq<vf<=75 or peak>bound+1e-10:return dict(valid=False,vq=vq)
    gamma=float(gamma_from_cubic(vq,vf,co));c0,c1,c2,c3=co
    deriv=-c2*vf-c3*vf*(vf+2*vq)
    direct=(1-n)*kj/kq*vq*deriv;beta=n*s
    eps=direct/gamma if abs(gamma)>1e-9 else np.nan
    wbar=L/vf*theta*fp*P**s
    return dict(valid=True,vq=vq,Gamma=gamma,epsilon_Gamma_x=eps,beta_plus_epsilon=beta+eps,
        congestion_g_per_vehicle=wbar*gamma,toll_g_per_vehicle=wbar*(beta*gamma+direct))

def cost_tables(parameters,draws,cards,ep,coeff,out):
    rows=[];curves=[];pigou=[]
    for r in parameters.to_dict('records'):
        if not np.isfinite(r['beta']):
            for p in POLS:
                rows.append(dict(corridor=r['corridor'],period=r['period'],pollutant=p,valid=False,
                    calibration_scope='unavailable',valid_bootstrap_share=np.nan))
            pigou.append(dict(corridor=r['corridor'],period=r['period'],beta=np.nan))
            continue
        C,vf,L=cards[cards.corridor.eq(r['corridor'])][['C_vphpl','vf_mph','L_mi']].median()
        x=r['x_median_h'];b=draws[draws.corridor.eq(r['corridor'])&draws.period.eq(r['period'])]
        beta=b.beta.to_numpy();poa=1/(1-beta*(beta+1)**(-(beta+1)/beta));ystar=(beta+1)**(-1/beta)
        point=1/(1-r['beta']*(r['beta']+1)**(-(r['beta']+1)/r['beta']))
        pigou.append(dict(corridor=r['corridor'],period=r['period'],beta=r['beta'],beta_lo=r['beta_lo'],beta_hi=r['beta_hi'],
            PoA=point,PoA_lo=np.quantile(poa,.025),PoA_hi=np.quantile(poa,.975),
            optimal_variable_link_share=(r['beta']+1)**(-1/r['beta']),share_lo=np.quantile(ystar,.025),share_hi=np.quantile(ystar,.975)))
        for p in POLS:
            val=cost_values(r,x,C,vf,L,coeff[p]);values=[cost_values(z,x,C,vf,L,coeff[p]) for z in b.to_dict('records')]
            valid=pd.DataFrame([z for z in values if z['valid']]);row=dict(corridor=r['corridor'],period=r['period'],pollutant=p,
                x_h=x,C_vphpl=C,vf_mph=vf,L_mi=L,beta=r['beta'],beta_lo=r['beta_lo'],beta_hi=r['beta_hi'],
                valid_bootstrap_share=len(valid)/len(b),calibration_scope=r['calibration_scope'],**val)
            for k in ['epsilon_Gamma_x','beta_plus_epsilon','toll_g_per_vehicle']:
                if val['valid'] and len(valid)>=100:
                    row[k+'_lo'],row[k+'_hi']=np.nanquantile(valid[k],[.025,.975])
            rows.append(row)
            for xx in np.linspace(r['x_min_h'],r['x_max_h'],161):
                z=cost_values(r,xx,C,vf,L,coeff[p]);curves.append(dict(corridor=r['corridor'],period=r['period'],pollutant=p,x_h=xx,**z))
    pd.DataFrame(rows).to_csv(out/'marginal_emission_card.csv',index=False)
    pd.DataFrame(curves).to_csv(out/'marginal_emission_curves.csv',index=False)
    pd.DataFrame(pigou).to_csv(out/'pigou_results.csv',index=False)
