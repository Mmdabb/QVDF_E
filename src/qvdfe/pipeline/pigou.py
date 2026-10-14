"""Compare signed-power QVDFE compression with the full model in a Pigou network.

The baseline and every affected background vehicle remain in all objectives.
Only a connected empirically supported and physically admitted interval is used.
"""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

from ._engine.pigou_solver import PigouNetwork
from .surrogate import POLS, scalar, state, valid, rate



def choose_specification(source, data, corridor, period):
    spec = json.loads((source/'surrogate_specification.json').read_text())
    ctx = next(c for c in spec['contexts'] if c['corridor']==corridor and c['period']==period)
    cards = pd.read_csv(source/'surrogate_coefficients.csv')
    cards = cards[cards.corridor.eq(corridor)&cards.period.eq(period)&cards.status.eq('fitted')]
    ep = pd.read_csv(data/'episode_results_v2.csv')
    ep = ep[ep.calibration_eligible & ~ep.holdout & ep.corridor.eq(corridor)]
    if ctx['calibration_scope']=='corridor_period': ep=ep[ep.period.eq(period)]
    # Contract verified from existing episode outputs: D_over_C_h is the volume/capacity loading.
    xcolumn = 'D_over_C_h' if 'D_over_C_h' in ep.columns else 'x_h'
    if xcolumn not in ep: raise ValueError('Episode loading column unavailable')
    observed = ep[xcolumn].to_numpy(float)
    observed = observed[np.isfinite(observed)&(observed>0)]
    candidates=[]
    for interval in ctx['admitted_intervals']:
        breaks=sorted(set([interval[0],interval[1]]+cards.x_low_h.tolist()+cards.x_high_h.tolist()))
        for lo,hi in zip(breaks[:-1],breaks[1:]):
            if hi <= lo*(1+1e-4):continue
            selected={}
            for p in POLS:
                found=cards[cards.pollutant.eq(p)&(cards.x_low_h<=lo*(1+1e-9))&(cards.x_high_h>=hi*(1-1e-9))]
                if len(found):selected[p]=found.iloc[0].to_dict()
            if len(selected)!=4:continue
            support=observed[(observed>lo)&(observed<hi)]
            if len(support)<5:continue
            candidates.append((len(support),lo,hi,support,selected))
    if not candidates:raise ValueError('No common fitted four-pollutant interval with five supported episodes')
    # Select by empirical support, never by the resulting network inefficiency.
    _,lo,hi,support,selected=max(candidates,key=lambda a:(a[0],a[2]-a[1]))
    low,reference,high=np.quantile(support,[.1,.5,.9])
    if high<=low*(1+1e-4):raise ValueError('Insufficient conditional loading variation')
    out=dict(corridor=corridor,period=period,reference_sensor_uid=ctx['reference_sensor_uid'],
             x_low_h=float(low),x_high_h=float(high),x_reference_h=float(reference),
             selected_branch_ids={p:r['branch_id'] for p,r in selected.items()},
             selection='Largest common constant-sign admitted interval by episode count; its empirical 10th/50th/90th loading percentiles set background/reference/maximum',
             episodes_in_common_interval=len(support),episodes_in_network_interval=int(np.sum((observed>=low)&(observed<=high))),
             calibration_scope=ctx['calibration_scope'],context=ctx,
             surrogate_coefficients=selected,cubic_coefficients=spec['cubic_coefficients'],
             source_data=data.name,surrogate_source=source.name)
    return out


class EmissionNetwork(PigouNetwork):
    def __init__(self,spec,mode):
        self.spec,self.mode=spec,mode
        self.ctx=spec['context'];self.params=self.ctx.copy()
        self.C,self.vf,self.L=[self.ctx[k] for k in ['C_vphpl','vf_mph','L_mi']]
        self.Tf=self.L/self.vf
        self.B=self.C*spec['x_low_h'];self.N=self.C*(spec['x_high_h']-spec['x_low_h'])
        self.coeff={p:np.asarray(c) for p,c in spec['cubic_coefficients'].items()}
        self.approx=spec['surrogate_coefficients']
        self.x_ref=spec['x_reference_h'];self.v2=self.vf
        self.T2=float(state(self.x_ref,self.ctx,self.coeff)['T'])
        self.L2=self.v2*self.T2
        self.e2={p:float(self.T2*rate(self.v2,c)) for p,c in self.coeff.items()}
        self.emission_scale=self.T2/self.e2['CO2']

    def state(self,f):
        D=self.B+np.asarray(f,float)
        z=state(D/self.C,self.ctx,self.coeff)
        z['D']=D
        if self.mode=='surrogate':
            for p,row in self.approx.items():
                increment=row['e0_g_per_vehicle']*row['sign_reference']*row['a_e']*(z['x']/row['x_ref_h'])**row['beta_e']
                z['e_'+p]=row['e0_g_per_vehicle']+increment
                z['de_'+p]=row['beta_e']*increment/D
        return z


def solve(network,out):
    out.mkdir(parents=True,exist_ok=True)
    f=np.linspace(0,network.N,20001);z=network.state(f)
    assert valid(z['x'],network.ctx,network.coeff).all()
    assert all(np.all(z['e_'+p]>0) for p in POLS)
    curves=pd.DataFrame({k:np.broadcast_to(v,f.shape) for k,v in z.items()})
    curves.insert(0,'flexible_route1_share',f/network.N)
    for kind in ['time']+POLS:
        curves['network_'+kind]=network.objective(f,kind)
        curves['marginal_'+kind]=network.derivative(f,kind)
    curves.to_csv(out/'network_curves.csv',index=False)
    outcomes=[];ratios=[];sensitivity=[];checks=[];optima={}
    for kind in ['time']+POLS:
        ue=network.equilibria(kind);fs,js=network.optimum(kind)
        worst=max(ue,key=lambda q:network.objective(q,kind))
        optima[kind]=(fs,js)
        ratios.append(dict(objective=kind,UE_count=len(ue),worst_UE_y=worst,SO_y=fs,
                           UE_total=float(network.objective(worst,kind)),SO_total=js,PoA=float(network.objective(worst,kind))/js))
        for j,q in enumerate(ue):outcomes.append(network.outcome(kind+'_UE'+('' if len(ue)==1 else f'_{j+1}'),q))
        outcomes.append(network.outcome(kind+'_SO',fs))
    for eta in sorted(set(np.linspace(0,4,81).tolist()+[.25,1.,4.])):
        ue=network.equilibria('generalized',eta);fs,js=network.optimum('generalized',eta)
        worst=max(ue,key=lambda q:network.objective(q,'generalized',eta))
        row=dict(eta=eta,UE_count=len(ue),UE_share=worst/network.N,SO_share=fs/network.N,
                 PoA=float(network.objective(worst,'generalized',eta))/js)
        for name,q in [('UE',worst),('SO',fs)]:
            row[name+'_time_veh_h']=float(network.objective(q,'time'))
            for p in POLS:
                row[name+'_'+p+'_g']=float(network.objective(q,p))
                row[name+'_'+p+'_inefficiency']=float(network.objective(q,p))/optima[p][1]
        sensitivity.append(row)
        if eta in [0.,.25,1.,4.]:
            outcomes.extend([network.outcome(f'generalized_UE_eta{eta:g}',worst,eta),network.outcome(f'generalized_SO_eta{eta:g}',fs,eta)])
            ratios.append(dict(objective=f'generalized_eta{eta:g}',UE_count=len(ue),worst_UE_y=worst,SO_y=fs,
                               UE_total=float(network.objective(worst,'generalized',eta)),SO_total=js,PoA=float(network.objective(worst,'generalized',eta))/js))
    for kind,eta in [('time',0.)]+[(p,0.) for p in POLS]+[('generalized',e) for e in [0.,.25,1.,4.]]:
        fs,js=network.optimum(kind,eta);fine_f,fine_j=network.optimum(kind,eta,20001)
        glob=differential_evolution(lambda q:network.objective(q[0],kind,eta),[(0,network.N)],seed=190922,tol=1e-11,polish=True)
        gap=abs(float(glob.fun)-js)/max(1.,abs(js))
        assert gap<1e-8
        assert abs(fine_j-js)/max(1.,abs(js))<1e-10
        assert network.equilibria(kind,eta)==network.equilibria(kind,eta,20001)
        points=np.linspace(.01,.99,51)*network.N;step=network.N*1e-5
        analytic=network.derivative(points,kind,eta)
        numeric=(network.objective(points+step,kind,eta)-network.objective(points-step,kind,eta))/(2*step)
        error=float(np.max(np.abs(analytic-numeric)/np.maximum(1.,np.abs(analytic))))
        assert error<1e-7,(kind,eta,error)
        c1,_,c2=network.costs(f,kind,eta);assert np.all(c1>0) and c2>0
        residuals=[]
        for q in network.equilibria(kind,eta):
            g=float(network.private_gap(q,kind,eta))
            residual=max(0.,-g) if q==0 else max(0.,g) if q==network.N else abs(g)
            assert residual<1e-8*max(1,abs(c2));residuals.append(residual)
        checks.append(dict(objective=kind,eta=eta,global_optimizer_relative_gap=gap,derivative_scaled_error=error,
                           maximum_Wardrop_residual=max(residuals),doubled_grid_same_equilibria=True,doubled_grid_same_optimum=True))
    table=pd.DataFrame(outcomes)
    for p in POLS:table[p+'_inefficiency']=table[p+'_g']/optima[p][1]
    table.to_csv(out/'assignment_results.csv',index=False)
    pd.DataFrame(ratios).to_csv(out/'price_of_anarchy.csv',index=False)
    pd.DataFrame(sensitivity).to_csv(out/'weight_sensitivity.csv',index=False)
    audit=dict(status='PASS',mode=network.mode,all_20001_states_admissible=True,
               minimum_P_minus_x_h=float(np.min(z['P']-z['x'])),minimum_peak_delay_margin_h=float(np.min(z['max_delay']-z['peak_delay'])),
               minimum_arrival_ratio=float(np.min(z['arrival_margin'])),queue_speed_range_mph=[float(np.min(z['vq'])),float(np.max(z['vq']))],
               all_total_emissions_positive=True,all_background_emissions_included=True,solver_checks=checks)
    (out/'audit.json').write_text(json.dumps(audit,indent=2))
    return table,pd.DataFrame(ratios),audit


def run(source,data,out,corridor,period):
    out.mkdir(parents=True,exist_ok=True)
    spec=choose_specification(source,data,corridor,period)
    full=EmissionNetwork(spec,'full');surrogate=EmissionNetwork(spec,'surrogate')
    spec.update(background_veh_lane=full.B,flexible_veh_lane=full.N,bypass_time_h=full.T2,bypass_length_mi=full.L2,
                bypass_speed_mph=full.v2,bypass_emission_g_veh=full.e2,time_emission_scale=full.emission_scale,
                source_hashes={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in [source/'surrogate_coefficients.csv',source/'surrogate_specification.json']})
    (out/'pigou_selection.json').write_text(json.dumps(spec,indent=2,default=scalar))
    results={};audits={}
    for mode,network in [('surrogate',surrogate),('full',full)]:results[mode]=solve(network,out/mode);audits[mode]=results[mode][2]
    comparisons=[]
    for row in results['surrogate'][0].to_dict('records'):
        f=row['flexible_route1_veh'];name=row['assignment']
        fullsame=full.outcome(name,f,row['eta'])
        fullown=results['full'][0].set_index('assignment').loc[name]
        one=dict(assignment=name,surrogate_share=f/full.N,full_model_share=float(fullown.flexible_route1_share))
        one['absolute_share_difference']=abs(one['surrogate_share']-one['full_model_share'])
        for col in ['travel_time_veh_h']+[p+'_g' for p in POLS]:
            one['surrogate_'+col]=row[col];one['full_at_surrogate_'+col]=fullsame[col];one['full_at_own_'+col]=fullown[col]
            one['same_assignment_relative_error_'+col]=(row[col]-fullsame[col])/fullsame[col]
        comparisons.append(one)
    pd.DataFrame(comparisons).to_csv(out/'full_surrogate_comparison.csv',index=False)
    poa=results['surrogate'][1].merge(results['full'][1],on='objective',suffixes=('_surrogate','_full'))
    poa['absolute_PoA_difference']=abs(poa.PoA_surrogate-poa.PoA_full)
    poa.to_csv(out/'full_surrogate_poa.csv',index=False)
    curve_path=source/'surrogate_curves.csv';curves=pd.read_csv(curve_path)
    curves['selected_for_main']=curves.corridor.eq(corridor)&curves.period.eq(period)
    curves['within_pigou_domain']=curves.selected_for_main&curves.x_h.between(spec['x_low_h'],spec['x_high_h'])
    curves.to_csv(out/'selected_surrogate_curves.csv',index=False)
    audit=dict(status='PASS',selected_context=f'{corridor}/{period}',reference_sensor_uid=spec['reference_sensor_uid'],
               network_interval_h=[spec['x_low_h'],spec['x_high_h']],maximum_PoA_difference=float(poa.absolute_PoA_difference.max()),
               maximum_assignment_share_difference=float(pd.DataFrame(comparisons).absolute_share_difference.max()),
               derivative_checks_pass=True,full_and_surrogate_compared=True)
    (out/'comparison_audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit,indent=2))
