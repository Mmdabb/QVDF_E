"""Read-only independent checks of traffic parameters and inverse FD diagnostics.

No diagnostic generator or inverse-solver function is imported. Rate mixtures
are rebuilt from the frozen inputs; interval boundaries come from polynomial
roots and both sides of every discontinuity are checked independently.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
POLS=['CO2','NOx','CO','HC']
STEP=ROOT/'debug/full_experiment/steps/11_episode_time_series'
CHECKS=0


def check(condition,message):
    global CHECKS
    CHECKS+=1
    if not bool(condition):raise AssertionError(message)


def close(actual,expected,message,rtol=1e-9,atol=1e-8):
    global CHECKS
    CHECKS+=1
    np.testing.assert_allclose(actual,expected,rtol=rtol,atol=atol,equal_nan=True,err_msg=message)


class IndependentRates:
    def __init__(self):
        directory=ROOT/'data/frozen/calibration/emission_input'
        vehicles=pd.read_csv(directory/'input_vehicle_type.csv')
        raw=pd.read_csv(directory/'input_vehicle_emission_rate.csv')
        v=vehicles.loc[vehicles.vehicle_type.eq(1)].iloc[0]
        self.a,self.b,self.c,self.mass=[float(v[k]) for k in ['rolling_term_a','rotating_term_b','drag_term_c','source_mass']]
        weights={int(k.split('_')[-1]):float(v[k]) for k in vehicles if k.startswith('percentage_of_age_')}
        total=sum(weights.values());weights={k:w/total for k,w in weights.items()}
        self.rates={}
        for mode,g in raw[raw.vehicle_type.eq(1)].groupby('OpModeID'):
            self.rates[int(mode)]=np.array([sum(float(row['meanBaseRate_'+name+'_(g/hr)'])*weights.get(int(row['age']),0.) for row in g.to_dict('records')) for name in ['CO2','NOX','CO','HC']])

    def vsp(self,q):
        v=np.asarray(q)*.44704
        return (self.a*v+self.b*v**2+self.c*v**3)/self.mass

    def mode(self,q):
        if q<=0:return 1
        if q<25:edges,modes=[0,3,6,9,12],[11,12,13,14,15,16]
        elif q<50:edges,modes=[0,3,6,9,12,18,24,30],[21,22,23,24,25,27,28,29,30]
        else:edges,modes=[6,12,18,24,30],[33,35,37,38,39,40]
        return modes[int(np.searchsorted(edges,float(self.vsp(q)),side='right'))]

    def __call__(self,q):return self.rates[self.mode(q)]

    def intervals(self,upper,lower=0.):
        cuts={float(lower),float(upper)}
        for lo,hi,thresholds in [(0.,25.,[0,3,6,9,12]),(25.,50.,[0,3,6,9,12,18,24,30]),(50.,max(100.,upper+1),[6,12,18,24,30])]:
            if lower<lo<upper:cuts.add(lo)
            for threshold in thresholds:
                polynomial=[self.c*.44704**3,self.b*.44704**2,self.a*.44704,-self.mass*threshold]
                for root in np.roots(np.trim_zeros(polynomial,'f')):
                    if abs(root.imag)>1e-8:continue
                    q=float(root.real)
                    if not lo<q<hi or not lower<q<upper:continue
                    # Locate the canonical representable boundary without the solver's bisection.
                    for _ in range(1000):
                        if self.vsp(q)>=threshold:break
                        q=float(np.nextafter(q,np.inf))
                    for _ in range(1000):
                        previous=float(np.nextafter(q,0.))
                        if self.vsp(previous)<threshold:break
                        q=previous
                    check(self.vsp(q)>=threshold and self.vsp(np.nextafter(q,0.))<threshold,'independent VSP threshold')
                    if lower<q<upper:cuts.add(q)
        edges=sorted(cuts)
        return [(a,b,self.mode((a+b)/2)) for a,b in zip(edges[:-1],edges[1:])]


def emission(row,q,rates):
    vf,L,D,mean=float(row.vf_mph),float(row.L_mi),float(row.D_veh),float(row.wbar_hat_h)
    tf=L/vf-q*mean/(vf-q);tq=vf*mean/(vf-q)
    return D*(tf*rates(vf)+tq*rates(q))


def global_objectives(row,rates,lower=0.,upper=None):
    """Independent exhaustive continuous-band analysis, including jump limits."""
    vf,D,mean=float(row.vf_mph),float(row.D_veh),float(row.wbar_hat_h)
    Tf=float(row.L_mi)/vf
    if upper is None:upper=float(row.L_mi)/(Tf+float(row.wt2_hat_h))
    observed=np.array([row['O_'+p] for p in POLS]);free=rates(vf)
    constant=D*(Tf+mean)*free
    co2=[];balanced=[];roots=[]
    intervals=rates.intervals(upper,lower)
    if not intervals:intervals=[(lower,upper,rates.mode(lower))]
    for lo,hi,mode in intervals:
        gradient=D*vf*mean*(rates.rates[mode]-free)
        a=constant/observed-1;b=gradient/observed
        # Minimize the convex squared residual in z over its closed interval.
        zlo,zhi=1/(vf-lo),1/(vf-hi)
        zstar=float(np.linalg.lstsq(b[:,None],-a,rcond=None)[0][0]) if np.any(b) else zlo
        zstar=np.clip(zstar,zlo,zhi)
        balanced.extend([float(np.mean((a+b*z)**2)) for z in [zlo,zhi,zstar]])
        co2.extend([abs(float(a[0]+b[0]*z)) for z in [zlo,zhi]])
        for j,p in enumerate(POLS):
            if gradient[j]==0:continue
            target=observed[j]-constant[j]
            if target==0:continue
            q=vf-gradient[j]/target
            # Membership uses the actual independent lookup, not the output ledger.
            if q>0 and lower<=q<=upper and lo<=q<=hi and rates.mode(q)==mode:
                residual=emission(row,q,rates)[j]/observed[j]-1
                if abs(residual)<1e-9:
                    roots.append((p,float(q)))
                    if p=='CO2':co2.append(0.)
    # The physical upper endpoint can belong to a new band of zero width.
    for q in [lower,upper]:
        if q>0:
            residual=emission(row,q,rates)/observed-1
            co2.append(abs(float(residual[0])));balanced.append(float(np.mean(residual**2)))
    return min(co2),min(balanced),roots,intervals


def verify_traffic(directory,source):
    t=pd.read_csv(directory/'traffic_parameters.csv')
    check(len(t)==137 and not t.episode_id.duplicated().any(),'137 traffic rows')
    ep=source.set_index('episode_id').loc[t.episode_id]
    sensors=pd.read_csv(ROOT/'data/frozen/calibration/average_weekday/sensor_parameters.csv').set_index('sensor_uid')
    for field in ['D_veh','P_h','P_hat_h','C_vphpl','vf_mph','vco_mph','kj','wt2_h','wt2_hat_h','wbar_h','wbar_hat_h','mu_vphpl','mu_obs_vphpl','vq_mph','vq_hat_mph','fd','n','fp','s','theta','alpha','beta']:
        close(t[field],ep[field],'traffic source '+field)
    close(t.vco_mph,.7*t.vf_mph,'detection threshold is 0.7 vf')
    close(t.average_speed_observed_mph,t.D_veh*t.L_mi/t.observed_vehicle_hours_per_lane,'observed space-mean speed')
    close(t.average_speed_fitted_mph,t.L_mi/(t.Tf_h+t.wbar_hat_h),'fitted mean speed')
    for name,observed,fitted in [('duration','P_h','P_hat_h'),('peak_delay','wt2_h','wt2_hat_h'),('mean_delay','wbar_h','wbar_hat_h'),('minimum_speed','vt2_obs_mph','vt2_hat_mph'),('average_speed','average_speed_observed_mph','average_speed_fitted_mph'),('discharge','mu_vphpl','mu_hat_vphpl')]:
        close(t[name+'_ape_pct'],100*np.abs(t[fitted]-t[observed])/np.abs(t[observed]),'traffic APE '+name)
    for field in ['C_vphpl','vf_mph','kj','kc','omega_mph','s3_kc_vpmpl','s3_m']:
        close(t[field],sensors.loc[t.sensor_uid,field],'detector source '+field)
    metadata=pd.read_csv(ROOT/'data/inputs/empirical/source_files/pems/pems_link_meta.csv').set_index(['corridor','link_id'])
    available=0
    for r in t.itertuples(index=False):
        key=(r.corridor,str(r.sensor))
        if key in metadata.index:
            m=metadata.loc[key];available+=1
            close(r.metadata_capacity_vphpl,m.network_capacity_vph/m.lanes,'metadata per-lane capacity')
        else:check(pd.isna(r.metadata_capacity_vphpl) and r.corridor=='AZ_I10_W','missing Arizona metadata')
    check(available==117,'metadata coverage')
    good=(t.mu_vphpl>0)&(t.mu_vphpl<t.C_vphpl)&(t.vq_mph>0)&(t.vq_mph<t.vf_mph)&(t.kq>0)
    check(np.array_equal(good,t.observed_fd_domain_valid),'observed FD flags')
    check(t.loc[~good,'vq_ape_pct'].isna().all(),'invalid FD-state APE is undefined')
    return {'rows':len(t),'metadata_available':available,'observed_FD_domain_invalid':int((~good).sum())}


def verify_inverse(directory,source,rates):
    summary=pd.read_csv(directory/'inverse_queue_speed.csv')
    roots=pd.read_csv(directory/'inverse_queue_speed_roots.csv')
    candidates=pd.read_csv(directory/'inverse_queue_speed_candidates.csv')
    intervals=pd.read_csv(directory/'inverse_queue_speed_intervals.csv')
    check(len(summary)==274 and not summary.duplicated(['episode_id','strategy']).any(),'274 inverse rows')
    check(set(summary.strategy)=={'co2_target','balanced_four_pollutants'},'two common-speed objectives')
    optima={};expected_root_count=0;max_objective_gap=0.
    for row in source.itertuples(index=False):
        r=pd.Series(row._asdict());oid=r.episode_id
        copt,bopt,expected_roots,bands=global_objectives(r,rates)
        optima[oid]=(copt,bopt)
        saved=roots[roots.episode_id.eq(oid)]
        for p,q in expected_roots:
            check(np.any(saved.pollutant.eq(p)&np.isclose(saved.q_root_mph,q,rtol=1e-8,atol=1e-7)),f'missing independent {p} root {oid}')
            expected_root_count+=1
        ledger=intervals[intervals.episode_id.eq(oid)&intervals.pollutant.eq('CO2')]
        for lo,hi,mode in bands:
            match=ledger[np.isclose(ledger.lower_mph,lo,atol=1e-10,rtol=0)&np.isclose(ledger.upper_mph,hi,atol=1e-10,rtol=0)]
            check(len(match)==1 and int(match.operating_mode.iloc[0])==mode,'independent interval coverage')
    source=source.set_index('episode_id')
    for r in roots.itertuples(index=False):
        s=source.loc[r.episode_id];q=r.q_root_mph
        check(q>r.lower_mph or (r.lower_closed and q==r.lower_mph),'root lower membership')
        check(q<r.upper_mph or (r.upper_closed and q==r.upper_mph),'root upper membership')
        check(rates.mode(q)==r.operating_mode,'root actual lookup mode')
        j=POLS.index(r.pollutant)
        close(emission(s,q,rates)[j],s['O_'+r.pollutant],'root actual emission',rtol=1e-9)
    for r in candidates.itertuples(index=False):
        s=source.loc[r.episode_id]
        check(rates.mode(r.q_candidate_mph)==r.operating_mode,'candidate actual lookup mode')
        actual=emission(s,r.q_candidate_mph,rates)
        close(actual,[getattr(r,p+'_emission_g') for p in POLS],'candidate emission')
    for r in summary.itertuples(index=False):
        s=source.loc[r.episode_id];q=r.q_inverse_mph
        D,L,vf,mu,omega,kj,C=s.D_veh,s.L_mi,s.vf_mph,s.mu_hat_vphpl,s.omega_mph,s.kj,s.C_vphpl
        Tf=L/vf;upper=L/(Tf+s.wt2_hat_h)
        check(0<q<=upper+1e-12,'physical peak-delay bound')
        close(r.q_physical_max_mph,upper,'reported physical bound')
        actual=emission(s,q,rates);observed=np.array([s['O_'+p] for p in POLS]);relative=actual/observed-1
        close(actual,[getattr(r,'inverse_M_'+p+'_g') for p in POLS],'selected emission')
        objective=abs(relative[0]) if r.strategy=='co2_target' else float(np.mean(relative**2))
        optimum=optima[r.episode_id][0 if r.strategy=='co2_target' else 1]
        close(r.objective_value,objective,'selected objective',atol=1e-10)
        close(r.objective_infimum,optimum,'global independent interval optimum',rtol=1e-8,atol=1e-10)
        check(objective>=optimum-1e-10 and objective<=optimum+1e-8,'actual vs global limiting optimum')
        max_objective_gap=max(max_objective_gap,abs(objective-optimum))
        close(r.mean_free_time_h+r.mean_queue_time_h,Tf+s.wbar_hat_h,'inverse time identity')
        close(vf*r.mean_free_time_h+q*r.mean_queue_time_h,L,'inverse distance identity')
        check(r.peak_free_time_h>=-1e-12,'peak free time nonnegative')
        mu_new=kj*q*omega/(omega+q)
        close(r.mu_case_mu_vphpl,mu_new,'inverse mu')
        close(r.mu_case_implied_P_h,D/mu_new,'inverse mu implied duration')
        close(r.mu_case_capacity_vphpl,C,'fixed-FD capacity')
        close(r.mu_case_original_duration_closure_residual_veh,mu_new*s.P_hat_h-D,'duration closure residual')
        denominator=kj*q-mu
        check(bool(r.omega_case_feasible)==(denominator>0),'positive omega feasibility')
        if denominator>0:
            wave=mu*q/denominator
            close(r.omega_case_omega_mph,wave,'inverse wave')
            close(r.omega_case_capacity_vphpl,kj*vf*wave/(vf+wave),'wave-case capacity closure')
        else:check(pd.isna(r.omega_case_omega_mph) and pd.isna(r.omega_case_capacity_vphpl),'nonpositive wave infeasible fields')
        jam=mu/q+mu/omega
        close(r.kj_case_kj_veh_mi_lane,jam,'inverse jam density')
        close(r.kj_case_capacity_vphpl,jam*vf*omega/(vf+omega),'jam-case capacity closure')
    return {'rows':len(summary),'roots':len(roots),'independently_recovered_roots':expected_root_count,'candidates':len(candidates),'maximum_actual_minus_global_objective':max_objective_gap,'infeasible_positive_omega':int((~summary.omega_case_feasible).sum())}


def verify_bounded(directory,inverse_directory,source,rates):
    targets=pd.read_csv(inverse_directory/'inverse_queue_speed.csv').set_index(['episode_id','strategy'])
    source=source.set_index('episode_id')
    totals={};maximum_gap=0.;maximum_capacity_error=0.
    for filename,label,wmin in [('fd_parameter_sensitivity.csv','primary',5.),('fd_parameter_sensitivity_expanded.csv','expanded_lower_wave',3.)]:
        frame=pd.read_csv(directory/filename)
        check(len(frame)==274 and not frame.duplicated(['episode_id','strategy']).any(),'bounded row completeness '+label)
        exact_count=0;selected_count=0
        for r in frame.itertuples(index=False):
            s=source.loc[r.episode_id];target=targets.loc[(r.episode_id,r.strategy)]
            mu,vf,C=float(s.mu_hat_vphpl),float(s.vf_mph),float(s.C_vphpl)
            qmax=float(s.L_mi)/(float(s.Tf_h)+float(s.wt2_hat_h))
            close([r.density_lower_veh_mi_lane,r.density_upper_veh_mi_lane,r.wave_lower_mph,r.wave_upper_mph],[150.,300.,wmin,20.],'declared bounds')
            close(r.q_target_mph,target.q_inverse_mph,'bounded target comes from inverse')
            close(r.baseline_mu_vphpl,mu,'bounded fixed discharge')
            lower=mu/(300.-mu/20.) if 300.-mu/20.>0 else np.inf
            denominator=150.-mu/wmin
            upper=min(mu/denominator if denominator>0 else np.inf,qmax,np.nextafter(vf,0.))
            possible=lower<=upper+1e-10
            if not possible:
                check(pd.isna(r.q_selected_mph) and r.fd_status=='no_physical_fd_pair','infeasible FD box flagged')
                continue
            selected_count+=1
            close([r.attainable_q_min_mph,r.attainable_q_max_mph],[lower,upper],'attainable speed interval')
            feasible=lower-1e-10<=target.q_inverse_mph<=upper+1e-10
            check(bool(r.exact_target_feasible)==feasible,'original inverse target feasibility')
            exact_count+=feasible
            check(bool(r.bounded_objective_reoptimized)==(not feasible),'bounded reoptimization flag')
            k,w=float(r.selected_kj_veh_mi_lane),float(r.selected_omega_mph)
            check(150.-1e-10<=k<=300.+1e-10 and wmin-1e-10<=w<=20.+1e-10,'selected density/wave bounds')
            q=mu/(k-mu/w)
            close(q,r.q_selected_mph,'FD-reconstructed speed')
            check(0<q<=qmax+1e-10 and q<vf,'bounded physical peak-delay speed')
            capacity=vf*w*k/(vf+w)
            close(capacity,r.selected_implied_capacity_vphpl,'bounded capacity closure')
            close(mu*s.P_hat_h,s.D_veh,'bounded duration closure')
            check(capacity>=mu-1e-10,'bounded discharge does not exceed capacity')
            # Evaluate the reconstructed q itself: an ulp across a rate jump matters.
            actual=emission(s,q,rates)
            close(actual,[getattr(r,'selected_M_'+p+'_g') for p in POLS],'FD-reconstructed speed emissions',rtol=1e-8)
            observed=np.array([s['O_'+p] for p in POLS]);relative=actual/observed-1
            actual_objective=abs(float(relative[0])) if r.strategy=='co2_target' else float(np.mean(relative**2))
            close(actual_objective,r.selected_objective_value,'bounded selected objective',atol=1e-9)
            co2,balance,_,_=global_objectives(s,rates,lower,upper)
            optimum=co2 if r.strategy=='co2_target' else balance
            close(r.selected_objective_infimum,optimum,'bounded exhaustive interval optimum',rtol=1e-8,atol=1e-9)
            check(actual_objective>=optimum-1e-9 and actual_objective<=optimum+1e-8,'bounded actual objective globally optimal')
            maximum_gap=max(maximum_gap,abs(actual_objective-optimum))
            density=mu/q
            wlo=max(wmin,mu/(300.-density))
            whi=min(20.,mu/(150.-density)) if density<150. else 20.
            cmin=vf*mu*(wlo/q+1)/(vf+wlo)
            cmax=vf*mu*(whi/q+1)/(vf+whi)
            desired_capacity=np.clip(C,cmin,cmax)
            close(capacity,desired_capacity,'minimum capacity change at selected q',rtol=1e-9,atol=1e-7)
            maximum_capacity_error=max(maximum_capacity_error,abs(capacity-desired_capacity))
            check(bool(r.baseline_capacity_preserved)==bool(np.isclose(capacity,C,rtol=1e-10,atol=1e-8)),'capacity-preservation flag')
        totals[label]={'rows':len(frame),'selected_pairs':selected_count,'exact_inverse_target_feasible':int(exact_count)}
    totals.update(maximum_actual_minus_global_objective=maximum_gap,maximum_capacity_minimization_residual=maximum_capacity_error)
    return totals


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=STEP)
    parser.add_argument('--traffic-directory',type=Path)
    parser.add_argument('--bounded-directory',type=Path)
    parser.add_argument('--skip-bounded',action='store_true',help='Temporary partial audit before bounded diagnostics are generated.')
    args=parser.parse_args()
    source=pd.read_csv(ROOT/'data/frozen/calibration/average_weekday/episode_results_v2.csv')
    source=source[source.matched_ladder_pass].sort_values('episode_id')
    result={'traffic':verify_traffic(args.traffic_directory or args.directory,source),'inverse':verify_inverse(args.directory,source,IndependentRates())}
    if not args.skip_bounded:
        result['bounded']=verify_bounded(args.bounded_directory or args.directory,args.directory,source,IndependentRates())
    result.update(checks=CHECKS,all_checks_passed=True,bounded_check_skipped=args.skip_bounded)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
