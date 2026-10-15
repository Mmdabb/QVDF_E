"""Expose arithmetic behind the experiment branches outside the 137-episode table.

Frozen observations, fitted parameters and solver choices are inputs. This does
not refit models, redetect episodes or resolve network equilibria.
"""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
FROZEN = ROOT / 'data/frozen'
CAL = FROZEN / 'calibration'
POLS = ['CO2', 'NOx', 'CO', 'HC']
SOURCES = {}
CHECKS = []


def source(path):
    path = Path(path)
    SOURCES[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return path


def csv(path, **kwargs):
    return pd.read_csv(source(path), **kwargs)


def js(path):
    return json.loads(source(path).read_text(encoding='utf-8'))


def check(name, got, expected, rtol=1e-9, atol=1e-8):
    a, b = np.asarray(got, float), np.asarray(expected, float)
    passed = bool(np.allclose(a, b, rtol=rtol, atol=atol, equal_nan=True))
    finite = np.isfinite(a) & np.isfinite(b)
    CHECKS.append(dict(check=name, passed=passed,
                       compared_values=int(a.size),
                       maximum_absolute_difference=float(np.max(np.abs(a[finite]-b[finite]))) if finite.any() else 0.))
    if not passed:
        raise AssertionError(name)


def scores(observed, estimated):
    o, e = np.asarray(observed, float), np.asarray(estimated, float)
    keep = np.isfinite(o) & np.isfinite(e)
    o, e = o[keep], e[keep]
    err = e-o
    sst = np.square(o-o.mean()).sum()
    return dict(N=len(o), observed_sum=float(o.sum()), estimated_sum=float(e.sum()),
                sum_absolute_error=float(abs(err).sum()), sum_squared_error=float(np.square(err).sum()),
                observed_sum_squared_deviation=float(sst),
                WAPE_pct=float(100*abs(err).sum()/abs(o).sum()),
                R2=float(1-np.square(err).sum()/sst), RMSE=float(np.sqrt(np.square(err).mean())),
                bias_pct=float(100*(e.sum()/o.sum()-1)))


def daily_trace(out):
    ep = csv(CAL/'daily_validation/episode_results_v2.csv')
    reference = csv(CAL/'daily_validation/daily_metrics_ci.csv')
    rows = []
    for r in reference.to_dict('records'):
        g = ep[ep.calibration_eligible & (ep.holdout if r['sample']=='AZ later date' else ~ep.holdout)]
        if r['target']=='vq_mph':
            g = g[g.vq_mph.gt(0)&g.vq_mph.lt(g.vf_mph)&g.vq_hat_mph.gt(0)&g.vq_hat_mph.lt(g.vf_mph)]
        z = dict(sample=r['sample'], target=r['target'], prediction=r['prediction'],
                 **scores(g[r['target']],g[r['prediction']]))
        for k in ['N','R2','RMSE','WAPE_pct','bias_pct']:
            check('daily '+r['sample']+' '+r['target']+' '+r['prediction']+' '+k,z[k],r[k])
        for k in ['R2','RMSE','WAPE_pct','bias_pct']:
            z[k+'_saved_CI_low']=r[k+'_lo']; z[k+'_saved_CI_high']=r[k+'_hi']
        z['CI_status']='retained 400-draw calendar-date block interval; not resampled here'
        rows.append(z)
    pd.DataFrame(rows).to_csv(out/'daily_validation_score_arithmetic.csv',index=False)


def period_trace(out):
    ep = csv(CAL/'average_weekday/episode_results_v2.csv',parse_dates=['t0','t3'])
    panel = csv(CAL/'average_weekday/traffic_panel.csv.gz',parse_dates=['datetime'],low_memory=False)
    periods = csv(CAL/'average_weekday/period_results_v2.csv')
    scope = csv(ROOT/'data/reporting/v33/arizona_episode_profile_scope.csv')
    expected = csv(ROOT/'data/reporting/v33/period_emission_metrics.csv')
    bands = csv(ROOT/'data/inputs/detector78/emission_rate_bands.csv')
    cards = csv(CAL/'average_weekday/sensor_parameters.csv').set_index('sensor_uid')
    hour=panel.datetime.dt.hour+panel.datetime.dt.minute/60
    panel['period']=np.select([hour.between(6,10,inclusive='left'),hour.between(10,16,inclusive='left'),hour.between(16,20,inclusive='left')],['AM','MD','PM'],default='NT')
    groups={k:g for k,g in panel.groupby(['sensor_uid','date','period'])}
    episodes={k:g for k,g in ep.groupby(['sensor_uid','date'])}
    allowed=set(zip(scope.sensor_uid,scope.month))
    allocations=[]; rows=[]
    for r in periods.to_dict('records'):
        key=(r['sensor_uid'],r['date'],r['period']); g=groups[key]
        card=cards.loc[r['sensor_uid']]; Tf=card.L_mi/card.vf_mph
        band=int(np.searchsorted(bands.speed_lower_mph,card.vf_mph,side='right')-1)
        included=(r['corridor']!='AZ_I10_W' or (r['sensor_uid'],r['date'][:7]) in allowed)
        total_increment={p:0. for p in POLS}
        for e in episodes.get(key[:2],pd.DataFrame()).to_dict('records'):
            bins=g[(g.datetime>=e['t0'])&(g.datetime<e['t3'])]
            if bins.empty: continue
            overlap=float(bins.flow_vph.sum()/12)
            valid=bool(e['calibration_eligible'] and e['physical_predicted_pass'] and e['profile_closed_pass'] and np.isfinite(e['D_veh']) and e['D_veh']>0)
            for p in POLS:
                inc=e['congestion_'+p]*overlap/e['D_veh'] if valid else np.nan
                if valid: total_increment[p]+=inc
                allocations.append(dict(sensor_uid=key[0],date=key[1],period=key[2],episode_id=e['episode_id'],pollutant=p,
                    overlap_bins=len(bins),overlap_volume_veh=overlap,whole_episode_volume_veh=e['D_veh'],
                    overlap_volume_share=overlap/e['D_veh'] if e['D_veh']>0 else np.nan,
                    whole_episode_congestion_increment_g=e['congestion_'+p],episode_period_eligible=valid,
                    allocated_increment_g=inc,current_reporting_profile=included))
        for p in POLS:
            rf=float(bands.iloc[band][p+'_g_per_veh_h']); base=r['V_veh']*Tf*rf
            calculated=base+total_increment[p] if r['period_model_pass'] else np.nan
            check('period M '+str(key)+' '+p,calculated,r['M_H_'+p])
            rows.append(dict(sensor_uid=key[0],date=key[1],period=key[2],corridor=r['corridor'],pollutant=p,
                current_reporting_profile=included,complete_observations=r['complete_observations'],
                all_episodes_valid=r['all_episodes_valid'],period_model_pass=r['period_model_pass'],
                V_veh=r['V_veh'],D_veh=r['D_veh'],L_mi=card.L_mi,vf_mph=card.vf_mph,Tf_h=Tf,
                free_flow_rate_g_per_veh_h=rf,all_vehicles_free_flow_base_g=base,
                eligible_overlap_increment_sum_g=total_increment[p],M_recomputed_g=calculated,
                M_saved_g=r['M_H_'+p],O_saved_g=r['O_H_'+p],S_saved_g=r['S_H_'+p]))
    pd.DataFrame(allocations).to_csv(out/'period_episode_allocations.csv',index=False)
    components=pd.DataFrame(rows)
    components.to_csv(out/'period_emission_components.csv',index=False)
    current=components[components.current_reporting_profile]
    daytime=[]
    for (sid,date,p),g in current[current.period.isin(['AM','MD','PM'])].groupby(['sensor_uid','date','pollutant']):
        assert set(g.period)=={'AM','MD','PM'}
        row=dict(sensor_uid=sid,date=date,pollutant=p,corridor=g.corridor.iloc[0],
                 all_three_periods_pass=bool(g.period_model_pass.all()))
        for m in ['O','M','S']:
            for _,r in g.iterrows(): row[m+'_'+r.period+'_g']=r[m+'_saved_g']
            # Preserve unavailable totals, unlike a default skip-NaN sum.
            row[m+'_daytime_g']=g[m+'_saved_g'].sum(min_count=3)
        daytime.append(row)
    daytime=pd.DataFrame(daytime); daytime.to_csv(out/'current_daytime_addition.csv',index=False)
    metrics=[]
    for r in expected.to_dict('records'):
        p,m=r['pollutant'],r['method']
        if r['window']=='planning_period':
            g=current[current.period_model_pass&current.pollutant.eq(p)]; obs='O_saved_g'; est=m+'_saved_g'
        else:
            g=daytime[daytime.all_three_periods_pass&daytime.pollutant.eq(p)];obs='O_daytime_g';est=m+'_daytime_g'
        if r['sample']!='All':g=g[g.corridor.eq('AZ_I10_W') if r['sample']=='AZ' else ~g.corridor.eq('AZ_I10_W')]
        z=dict(window=r['window'],sample=r['sample'],pollutant=p,method=m,**scores(g[obs],g[est]))
        for k in ['N','R2','WAPE_pct','bias_pct']:check('current report '+str((r['window'],r['sample'],p,m,k)),z[k],r[k])
        metrics.append(z)
    pd.DataFrame(metrics).to_csv(out/'current_period_score_arithmetic.csv',index=False)


def state(x,ctx,coeff):
    C,vf,L=[ctx[k] for k in ['C_vphpl','vf_mph','L_mi']]
    Tf=L/vf; P=ctx['fd']*x**ctx['n'];mu=C*x/P
    omega=C/(ctx['kj']-C/vf); kq=ctx['kj']-mu/omega;vq=mu/kq
    peak=Tf*ctx['fp']*P**ctx['s'];w=ctx['theta']*peak; beta=ctx['n']*ctx['s']
    result=dict(x_h=x,Tf_h=Tf,P_h=P,mu_vphpl=mu,vq_mph=vq,wbar_h=w,T_h=Tf+w,
                peak_delay_h=peak,finite_link_limit_h=L*(1/vq-1/vf))
    for p,co in coeff.items():
        rf=sum(co[i]*vf**i for i in range(4));rq=sum(co[i]*vq**i for i in range(4))
        gamma=(vf*rq-vq*rf)/(vf-vq)
        gamma_derivative=-co[2]*vf-co[3]*vf*(vf+2*vq)
        dv_dx=(1-ctx['n'])*ctx['kj']/kq*vq/x
        result[p]=dict(free_rate_g_per_veh_h=rf,queue_rate_g_per_veh_h=rq,Gamma_g_per_veh_h=gamma,
                       free_emission_g_per_vehicle=Tf*rf,congestion_increment_g_per_vehicle=w*gamma,
                       full_emission_g_per_vehicle=Tf*rf+w*gamma,
                       full_derivative_per_vehicle=(beta*w/x*gamma+w*gamma_derivative*dv_dx)/C)
    return result


def surrogate_trace(out):
    spec=js(CAL/'surrogate/surrogate_specification.json')
    card=csv(CAL/'surrogate/surrogate_coefficients.csv')
    curves=csv(CAL/'surrogate/surrogate_curves.csv')
    rows=[]
    for r in card[card.status.isin(['fitted','failed_fit_or_positive_cost_check'])].to_dict('records'):
        g=curves[curves.corridor.eq(r['corridor'])&curves.period.eq(r['period'])&curves.pollutant.eq(r['pollutant'])&curves.branch_id.astype(str).eq(str(r['branch_id']))].sort_values('x_h')
        if g.empty:continue
        for pos in sorted(set([0,len(g)//4,len(g)//2,3*len(g)//4,len(g)-1])):
            sample=g.iloc[pos];x=sample.x_h;p=r['pollutant'];z=state(x,r,spec['cubic_coefficients']);v=z[p]
            factor=r['a_e']*(x/r['x_ref_h'])**r['beta_e'];approx=r['e0_g_per_vehicle']*(1+r['sign_reference']*factor)
            signed_k=(v['full_emission_g_per_vehicle']/r['e0_g_per_vehicle']-1)/factor
            check('power full '+str((r['corridor'],r['period'],p,r['branch_id'],pos)),v['full_emission_g_per_vehicle'],sample.e_full_g_per_vehicle)
            check('power approximation '+str((r['corridor'],r['period'],p,r['branch_id'],pos)),approx,sample.e_approx_g_per_vehicle)
            check('power k '+str((r['corridor'],r['period'],p,r['branch_id'],pos)),signed_k,sample.k_signed)
            rows.append(dict(corridor=r['corridor'],period=r['period'],pollutant=p,branch_id=r['branch_id'],fit_status=r['status'],
                reference_sensor_uid=r['reference_sensor_uid'],validation_grid_index=pos,**{k:v for k,v in z.items() if k not in POLS},
                **v,a_e=r['a_e'],beta_e=r['beta_e'],x_ref_h=r['x_ref_h'],sign_reference=r['sign_reference'],
                unsigned_power_factor=factor,approximate_emission_g_per_vehicle=approx,k_signed=signed_k,
                relative_approximation_error=(approx-v['full_emission_g_per_vehicle'])/v['full_emission_g_per_vehicle']))
    pd.DataFrame(rows).to_csv(out/'fixed_parameter_gamma_and_power_samples.csv',index=False)
    card[['corridor','period','pollutant','reference_sensor_uid','branch_id','status','max_total_relative_error','max_scaled_derivative_error']].to_csv(out/'power_branch_status.csv',index=False)


def pigou_trace(out):
    spec=js(CAL/'pigou/pigou_selection.json');ctx=spec['context'];coeff=spec['cubic_coefficients']
    B=spec['background_veh_lane'];N=spec['flexible_veh_lane'];T2=spec['bypass_time_h'];scale=spec['time_emission_scale']
    rows=[];ratios=[];sensitivity=[]
    def costs(y,mode):
        D=B+y;z=state(D/ctx['C_vphpl'],ctx,coeff)
        c={'time':z['T_h']};c2={'time':T2}
        for p in POLS:
            e=z[p]['full_emission_g_per_vehicle']
            if mode=='surrogate':
                r=spec['surrogate_coefficients'][p]
                e=r['e0_g_per_vehicle']*(1+r['sign_reference']*r['a_e']*(z['x_h']/r['x_ref_h'])**r['beta_e'])
            c[p]=e;c2[p]=spec['bypass_emission_g_veh'][p]
        return z,c,c2
    def objective(y,kind,eta,mode):
        _,c,c2=costs(y,mode)
        if kind=='generalized':c1=c['time']+eta*scale*c['CO2'];other=c2['time']+eta*scale*c2['CO2']
        else:c1=c[kind];other=c2[kind]
        return (B+y)*c1+(N-y)*other
    for mode in ['full','surrogate']:
        assignments=csv(CAL/f'pigou/{mode}/assignment_results.csv')
        poa=csv(CAL/f'pigou/{mode}/price_of_anarchy.csv')
        for r in assignments.to_dict('records'):
            y=r['flexible_route1_veh'];z,c,c2=costs(y,mode)
            for p in ['time']+POLS:
                one=(B+y)*c[p];two=(N-y)*c2[p];saved=r['travel_time_veh_h' if p=='time' else p+'_g']
                check('Pigou components '+str((mode,r['assignment'],p)),one+two,saved)
                rows.append(dict(mode=mode,assignment=r['assignment'],eta=r['eta'],quantity=p,unit='vehicle hours' if p=='time' else 'grams',
                    background_veh=B,flexible_veh=N,flexible_route1_veh=y,route1_total_veh=B+y,route2_total_veh=N-y,
                    x_h=z['x_h'],P_h=z['P_h'],vq_mph=z['vq_mph'],
                    route1_per_vehicle=c[p],route2_per_vehicle=c2[p],route1_total=one,route2_total=two,
                    recomputed_network_total=one+two,saved_network_total=saved,
                    generalized_objective_veh_h=objective(y,'generalized',r['eta'],mode) if np.isfinite(r['eta']) else np.nan))
        for r in poa.to_dict('records'):
            kind='generalized' if r['objective'].startswith('generalized') else r['objective']
            eta=float(r['objective'].split('eta')[1]) if kind=='generalized' else 0.
            ue=objective(r['worst_UE_y'],kind,eta,mode);so=objective(r['SO_y'],kind,eta,mode)
            check('Pigou UE '+mode+r['objective'],ue,r['UE_total']);check('Pigou SO '+mode+r['objective'],so,r['SO_total']);check('Pigou PoA '+mode+r['objective'],ue/so,r['PoA'])
            ratios.append(dict(mode=mode,objective=r['objective'],eta=eta,UE_count=r['UE_count'],worst_UE_flexible_route1_veh=r['worst_UE_y'],SO_flexible_route1_veh=r['SO_y'],
                recomputed_UE_total=ue,recomputed_SO_total=so,PoA_recomputed=ue/so,PoA_saved=r['PoA']))
        sens=csv(CAL/f'pigou/{mode}/weight_sensitivity.csv')
        for r in sens.to_dict('records'):
            ue=objective(r['UE_share']*N,'generalized',r['eta'],mode);so=objective(r['SO_share']*N,'generalized',r['eta'],mode)
            check('Pigou eta '+mode+str(r['eta']),ue/so,r['PoA'])
            sensitivity.append(dict(mode=mode,eta=r['eta'],UE_share=r['UE_share'],SO_share=r['SO_share'],emission_weight_h_per_g=r['eta']*scale,
                UE_time_veh_h=r['UE_time_veh_h'],UE_CO2_g=r['UE_CO2_g'],UE_emission_cost_veh_h=r['eta']*scale*r['UE_CO2_g'],
                UE_generalized_total=ue,SO_time_veh_h=r['SO_time_veh_h'],SO_CO2_g=r['SO_CO2_g'],
                SO_emission_cost_veh_h=r['eta']*scale*r['SO_CO2_g'],SO_generalized_total=so,PoA=ue/so))
    pd.DataFrame(rows).to_csv(out/'pigou_route_component_arithmetic.csv',index=False)
    pd.DataFrame(ratios).to_csv(out/'pigou_poa_arithmetic.csv',index=False)
    pd.DataFrame(sensitivity).to_csv(out/'pigou_generalized_cost_arithmetic.csv',index=False)


def cbi_transition_trace(out):
    cbi=csv(CAL/'cbi_comparison_summary.csv')
    cbi['qvdfe_recomputed']=cbi.matched_episodes+cbi.qvdfe_only
    cbi['repository_recomputed']=cbi.matched_episodes+cbi.repository_only
    cbi['bin_iou_recomputed']=cbi.intersection_bins/cbi.union_bins
    check('CBI episode inventory',cbi.qvdfe_recomputed,cbi.qvdfe_episodes)
    check('CBI reference inventory',cbi.repository_recomputed,cbi.repository_episodes)
    check('CBI temporal IoU',cbi.bin_iou_recomputed,cbi.bin_iou)
    cbi.to_csv(out/'cbi_inventory_arithmetic.csv',index=False)
    transitions=csv(FROZEN/'transitions/ks1_vsp_transitions.csv');rows=[]
    for r in transitions.to_dict('records'):
        for p in ['CO2','NOX','CO','HC']:
            two=r[p+'_E_2s_zero_g'];zero=r[p+'_E_ks1_zero_g'];modal=r[p+'_E_ks1_modal_g'];observed=r[p+'_E_meas_modal_g']
            rate=zero-two;load=modal-zero;combined=modal-two
            check('transition load '+str((r['run'],r['vehicle'],r['i1'],p)),load,r[p+'_de_load_g'])
            check('transition combined '+str((r['run'],r['vehicle'],r['i1'],p)),combined,r[p+'_de_combined_g'])
            rows.append(dict(run=r['run'],vehicle=r['vehicle'],direction=r['direction'],i1=r['i1'],i2=r['i2'],pollutant=p,
                complete_record=r['complete_record'],replace_ok=r['replace_ok'],T_s=r['T_s'],v1_mph=r['v1_mph'],v2_mph=r['v2_mph'],
                two_speed_zero_acceleration_g=two,KS1_zero_acceleration_g=zero,KS1_modal_g=modal,measured_motion_modal_g=observed,
                zero_acceleration_speed_correction_g=rate,acceleration_load_correction_g=load,combined_correction_g=combined,
                corrected_two_speed_total_g=two+rate+load,modal_difference_g=modal-observed,
                modal_difference_pct=100*(modal-observed)/observed if observed!=0 else np.nan))
    pd.DataFrame(rows).to_csv(out/'transition_component_arithmetic.csv',index=False)


def plots(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors=['#2563EB','#168C69','#E69F00','#7A5195']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':11,
        'axes.labelsize':10,'axes.edgecolor':'#17324D','axes.labelcolor':'#17324D',
        'text.color':'#17324D','xtick.color':'#17324D','ytick.color':'#17324D',
        'grid.color':'#E2E8F0','figure.facecolor':'white','axes.facecolor':'white',
        'svg.fonttype':'none','savefig.facecolor':'white'})
    figdir=out/'figures';figdir.mkdir(exist_ok=True)
    plotmeta=[]
    def finish(fig,name,title,caption,sources):
        fig.suptitle(title,x=.06,ha='left',fontsize=13,fontweight='bold')
        for ax in fig.axes:
            ax.grid(alpha=.8,linewidth=.6);ax.set_axisbelow(True)
            ax.spines[['top','right']].set_visible(False)
        fig.tight_layout(rect=[0,.075,1,.93],w_pad=2.5)
        fig.text(.06,.025,caption,fontsize=8.5,ha='left',va='bottom')
        fig.savefig(figdir/(name+'.png'),dpi=220)
        fig.savefig(figdir/(name+'.svg'))
        plt.close(fig)
        plotmeta.append(dict(figure=name,caption=caption,sources=sources))
    def parity(ax,x,y,labelx,labely):
        lo=min(np.min(x),np.min(y));hi=max(np.max(x),np.max(y))
        ax.plot([lo,hi],[lo,hi],color='#64748B',lw=1,ls='--',label='Equality')
        ax.set_xlabel(labelx);ax.set_ylabel(labely)

    ep=csv(CAL/'daily_validation/episode_results_v2.csv')
    e=ep[ep.calibration_eligible]
    fig,axes=plt.subplots(1,2,figsize=(10,4.7))
    for hold,label,color in [(False,'Training (924)',colors[0]),(True,'Later dates (174)',colors[2])]:
        g=e[e.holdout.eq(hold)]
        axes[0].scatter(g.P_h,g.P_hat_h,s=11,alpha=.45,color=color,label=label,edgecolors='none')
        axes[1].scatter(g.wt2_h*60,g.wt2_hat_h*60,s=11,alpha=.45,color=color,label=label,edgecolors='none')
    parity(axes[0],e.P_h,e.P_hat_h,'Observed duration (h)','Predicted duration (h)')
    parity(axes[1],e.wt2_h*60,e.wt2_hat_h*60,'Observed peak delay (min)','Predicted peak delay (min)')
    axes[0].legend(frameon=False,fontsize=8.5);axes[0].set_title('(a) Episode duration');axes[1].set_title('(b) Peak link delay')
    finish(fig,'01_daily_validation','Daily traffic validation',
        'Eligible Arizona daily episodes; finite-link failures remain. Emissions are not evaluated on this daily sample.',
        ['data/frozen/calibration/daily_validation/episode_results_v2.csv'])

    p=pd.read_csv(out/'period_emission_components.csv');g=p[p.current_reporting_profile&p.period_model_pass&p.pollutant.eq('CO2')]
    fig,axes=plt.subplots(1,2,figsize=(10,4.7))
    for isaz,label,color in [(True,'Arizona (115)',colors[0]),(False,'PeMS (1,095)',colors[1])]:
        z=g[g.corridor.eq('AZ_I10_W').eq(isaz)]
        axes[0].scatter(z.O_saved_g/1e6,z.M_recomputed_g/1e6,s=14,alpha=.5,color=color,label=label,edgecolors='none')
        axes[1].scatter(z.D_veh/z.V_veh,100*(z.M_recomputed_g/z.O_saved_g-1),s=14,alpha=.5,color=color,edgecolors='none')
    parity(axes[0],g.O_saved_g/1e6,g.M_recomputed_g/1e6,'Observed-speed lookup proxy (million g)','Two-speed estimate (million g)')
    axes[0].set_xscale('log');axes[0].set_yscale('log');axes[0].legend(frameon=False,fontsize=8.5)
    axes[0].set_title('(a) Period CO₂ totals');axes[1].set_title('(b) Error and congested-volume share')
    axes[1].axhline(0,color='#64748B',lw=1,ls='--');axes[1].set_xlabel('Episode-overlap volume / period volume');axes[1].set_ylabel('Two-speed minus proxy (%)')
    finish(fig,'02_period_emissions','Period emission accounting',
        'Current reporting scope: 1,210 admitted planning periods. The comparison reference is a model-assigned proxy.',
        ['period_emission_components.csv'])

    spec=js(CAL/'pigou/pigou_selection.json');ctx=spec['context'];coeff=spec['cubic_coefficients']
    x=np.linspace(spec['x_low_h'],spec['x_high_h'],201);z=state(x,ctx,coeff);plotrows=[]
    fig,axes=plt.subplots(1,2,figsize=(10,4.7))
    for p,color in zip(POLS,colors):
        r=spec['surrogate_coefficients'][p];k=(z[p]['full_emission_g_per_vehicle']/r['e0_g_per_vehicle']-1)/(r['a_e']*(x/r['x_ref_h'])**r['beta_e'])
        axes[0].plot(x,z[p]['Gamma_g_per_veh_h']/z[p]['free_rate_g_per_veh_h'],color=color,label=p,lw=1.8)
        axes[1].plot(x,k,color=color,label=p,lw=1.8)
        for i,xx in enumerate(x):plotrows.append(dict(pollutant=p,x_h=xx,Gamma_over_free_rate=z[p]['Gamma_g_per_veh_h'][i]/z[p]['free_rate_g_per_veh_h'],k_signed=k[i]))
    axes[0].set_title('(a) Gamma relative to the free-flow rate');axes[1].set_title('(b) Signed power correction')
    for ax in axes:ax.set_xlabel('Episode volume / hourly capacity (h)')
    axes[0].set_ylabel('Gamma / free-flow rate');axes[1].set_ylabel('k(x)');axes[1].axhline(1,color='#64748B',lw=1,ls='--')
    axes[0].legend(frameon=False,ncol=2,fontsize=8.5)
    pd.DataFrame(plotrows).to_csv(out/'gamma_plot_values.csv',index=False)
    finish(fig,'03_fixed_parameter_gamma','Fixed-parameter response: AZ I-10 W / MD',
        'One detector FD and one parameter set throughout; cubic-rate branch over the selected Pigou loading interval.',
        ['data/frozen/calibration/pigou/pigou_selection.json','gamma_plot_values.csv'])

    q=pd.read_csv(out/'pigou_generalized_cost_arithmetic.csv')
    fig,axes=plt.subplots(1,2,figsize=(10,4.7))
    for mode,style in [('full','-'),('surrogate','--')]:
        z=q[q['mode'].eq(mode)]
        axes[0].plot(z.eta,z.UE_share,color=colors[0],ls=style,lw=1.8,label='UE, '+mode)
        axes[0].plot(z.eta,z.SO_share,color=colors[1],ls=style,lw=1.8,label='SO, '+mode)
        axes[1].plot(z.eta,z.PoA,color=colors[0] if mode=='full' else colors[2],ls=style,lw=1.8,label=mode.capitalize())
    axes[0].set_title('(a) Flexible demand on route 1');axes[1].set_title('(b) Generalized-cost PoA')
    for ax in axes:ax.set_xlabel('CO₂ routing weight η');ax.legend(frameon=False,fontsize=8)
    axes[0].set_ylabel('Fraction of flexible demand');axes[1].set_ylabel('Worst UE objective / optimal objective')
    finish(fig,'04_pigou','Pigou assignment and inefficiency',
        'Saved equilibrium and optimal flows; all background vehicles included. Full and power-model curves nearly overlap.',
        ['pigou_generalized_cost_arithmetic.csv'])

    t=pd.read_csv(out/'transition_component_arithmetic.csv');g=t[t.replace_ok&t.pollutant.eq('CO2')]
    fig,axes=plt.subplots(1,2,figsize=(10,4.7))
    for direction,label,color in [('deceleration','Deceleration',colors[0]),('acceleration','Acceleration',colors[2])]:
        z=g[g.direction.eq(direction)]
        axes[0].scatter(z.zero_acceleration_speed_correction_g,z.acceleration_load_correction_g,s=13,alpha=.55,color=color,label=label,edgecolors='none')
        axes[1].scatter(z.measured_motion_modal_g,z.KS1_modal_g,s=13,alpha=.55,color=color,edgecolors='none')
    axes[0].axhline(0,color='#64748B',lw=1,ls='--');axes[0].axvline(0,color='#64748B',lw=1,ls='--')
    axes[0].set_xlabel('Smooth-speed correction at zero acceleration (g)');axes[0].set_ylabel('Acceleration-load correction (g)');axes[0].legend(frameon=False,fontsize=8.5)
    parity(axes[1],g.measured_motion_modal_g,g.KS1_modal_g,'Measured-motion assigned emissions (g)','Fitted-transition assigned emissions (g)')
    axes[0].set_title('(a) CO₂ correction components');axes[1].set_title('(b) Modal emission comparison')
    finish(fig,'05_transition','Finite-transition emission calculation',
        '281 replacement-admissible transitions. Both axes use assigned rates; neither represents measured exhaust.',
        ['transition_component_arithmetic.csv'])

    c=csv(CAL/'cbi_episode_matches.csv');inventory=pd.read_csv(out/'cbi_inventory_arithmetic.csv')
    fig,axes=plt.subplots(1,2,figsize=(10,4.9))
    axes[0].scatter(c.P_repository_h,c.P_ours_h,s=14,alpha=.5,color=colors[0],edgecolors='none')
    parity(axes[0],c.P_repository_h,c.P_ours_h,'Reference episode duration (h)','QVDF-E episode duration (h)')
    labels=inventory.corridor.str.replace('_',' ',regex=False)
    axes[1].barh(labels,inventory.bin_iou_recomputed,color=colors[1],height=.7)
    axes[1].set_xlim(0,1.02);axes[1].set_xlabel('Five-minute-bin intersection / union');axes[1].tick_params(axis='y',labelsize=8)
    axes[0].set_title('(a) 263 matched detected episodes');axes[1].set_title('(b) Corridor temporal overlap')
    finish(fig,'06_cbi','CBI episode-definition comparison',
        'Detection comparison precedes emission admission. Matched boundaries are the retained original pairing.',
        ['data/frozen/calibration/cbi_episode_matches.csv','cbi_inventory_arithmetic.csv'])
    (out/'figure_sources.json').write_text(json.dumps(plotmeta,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'debug/output/full_experiment/10_other_experiments')
    args=parser.parse_args();out=args.output.resolve()
    protected=[ROOT/'data',ROOT/'src',ROOT/'reproduce',ROOT/'tools',ROOT/'debug/full_experiment',ROOT/'debug/episodes_137',ROOT/'debug/sensor78']
    for p in protected:
        if out==p or out.is_relative_to(p) or p.is_relative_to(out):raise ValueError('Choose a separate generated-output directory')
    marker=out/'.qvdfe-other-experiment-trace.json'
    if out.exists() and any(out.iterdir()) and not marker.is_file():raise ValueError('Output is nonempty and not owned by this calculation')
    out.mkdir(parents=True,exist_ok=True);marker.write_text('{"workflow":"other_experiment_trace"}\n',encoding='utf-8')
    daily_trace(out);period_trace(out);surrogate_trace(out);pigou_trace(out);cbi_transition_trace(out);plots(out)
    groups={}
    for c in CHECKS:
        key=c['check'].split()[0];g=groups.setdefault(key,dict(checks=0,compared_values=0,all_passed=True,maximum_absolute_difference=0.))
        g['checks']+=1;g['compared_values']+=c['compared_values'];g['all_passed'] &= c['passed']
        if c['maximum_absolute_difference']>g['maximum_absolute_difference']:
            g['maximum_absolute_difference']=c['maximum_absolute_difference'];g['largest_difference_check']=c['check']
    summary={'purpose':'Arithmetic re-evaluation of frozen additional experiment branches; no new calibration or optimizer run',
             'all_checks_passed':all(r['passed'] for r in CHECKS),'check_count':len(CHECKS),
             'checks_by_branch':groups,'source_sha256':SOURCES,
             'output_rows':{p.name:len(pd.read_csv(p)) for p in out.glob('*.csv')}}
    (out/'arithmetic_audit.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['all_checks_passed','check_count','output_rows']},indent=2))


if __name__=='__main__':main()
