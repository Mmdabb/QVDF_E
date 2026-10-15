"""Reproduce the selected Arizona detector-141 example and its editable seven-page report."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/frozen/calibration/average_weekday'
EPISODE='state_transition__AZ_I10_W::141__2016-11-01__022'
METHODS=['O','S','R','M','A'];POLS=['CO2','NOx','CO','HC']
COL={'O':'#242B33','S':'#2563EB','R':'#7B3294','M':'#168C69','A':'#E69F00'}
STYLE={'O':'-','S':'--','R':'-','M':'-','A':'--'}
NAME={'O':'Recorded-speed proxy','S':'Observed mean speed','R':'Reconstructed speeds','M':'Two-speed lookup','A':'Two-speed cubic'}


def output_location():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=ROOT/'debug/output/az141_november')
    ap.add_argument('--pdf',action='store_true');ap.add_argument('--pdflatex',default='pdflatex')
    a=ap.parse_args();out=a.output.resolve()
    for p in [ROOT/'data',ROOT/'src',ROOT/'reproduce',ROOT/'tools',ROOT/'debug/case_studies',ROOT/'debug/full_experiment',ROOT/'debug/sensor78',ROOT/'debug/episodes_137']:
        if p==out or out.is_relative_to(p) or p.is_relative_to(out):raise ValueError('Output must be separate from published sources and results')
    marker=out/'.qvdfe-az141-case.json'
    if out.exists() and any(out.iterdir()) and not marker.exists():raise ValueError('Output is nonempty and unowned')
    for sub in ['inputs','results','figures','reports/source']:(out/sub).mkdir(parents=True,exist_ok=True)
    marker.write_text('{"workflow":"az141_november_case"}\n');return a,out


def main():
    args,out=output_location();data=out/'results';figdir=out/'figures'
    files=[SOURCE/'episode_results_v2.csv',SOURCE/'traffic_panel.csv.gz',SOURCE/'cubic_rate_coefficients.csv',SOURCE/'parameter_card.csv',ROOT/'data/inputs/detector78/calculation_inputs.json',ROOT/'data/inputs/detector78/calibration_inputs.json',ROOT/'debug/episodes_137/results/episode_calculations_137.csv']
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    all_ep=pd.read_csv(files[0],parse_dates=['t0','t2','t3']);e=all_ep.set_index('episode_id').loc[EPISODE]
    diagnostic=pd.read_csv(files[-1]);selection=diagnostic[['episode_id','paper_corridor','sensor_uid','date','period','trip_time_error_pct','mean_delay_error_pct','peak_delay_error_pct','duration_error_pct','CO2_M_absolute_error_pct','CO2_S_absolute_error_pct','observed_speed_count_cv','vq_mph','vq_hat_mph','physical_observed_pass']].copy()
    selection['traffic_screen_pass']=(selection.trip_time_error_pct.abs().le(5)&selection.mean_delay_error_pct.abs().le(10)&selection.peak_delay_error_pct.abs().le(10)&selection.duration_error_pct.abs().le(10)&((selection.vq_hat_mph/selection.vq_mph-1).abs().le(.10))&selection.physical_observed_pass)
    selection['CO2_two_speed_minus_mean_APE_pp']=selection.CO2_M_absolute_error_pct-selection.CO2_S_absolute_error_pct
    selection['queue_speed_difference_pct']=100*(selection.vq_hat_mph/selection.vq_mph-1)
    selection['selected_case']=selection.episode_id.eq(EPISODE)
    selection.to_csv(data/'selection_all_137.csv',index=False)
    candidates=selection[selection.traffic_screen_pass].sort_values('CO2_two_speed_minus_mean_APE_pp',ascending=False)
    candidates.to_csv(data/'selection_eligible_4.csv',index=False)
    assert len(candidates)==4 and candidates.iloc[0].episode_id==EPISODE
    selected=candidates.iloc[0]
    panel=pd.read_csv(files[1],parse_dates=['datetime'],low_memory=False)
    profile=panel[panel.sensor_uid.eq(e.sensor_uid)&panel.date.eq(e.date)].sort_values('datetime')
    g=profile[(profile.datetime>=e.t0)&(profile.datetime<e.t3)].copy()
    g['clock_h']=g.datetime.dt.hour+g.datetime.dt.minute/60
    g['clock_time']=g.datetime.dt.strftime('%H:%M');g['d']=g.flow_vph/12;g['H']=g.d*e.L_mi/g.speed_mph
    assert len(g)==40
    all_ep[all_ep.episode_id.eq(EPISODE)].to_csv(out/'inputs/episode_record.csv',index=False)
    profile.to_csv(out/'inputs/released_day_profile.csv',index=False)
    g.to_csv(out/'inputs/episode_5min_observations.csv',index=False)
    par=pd.read_csv(files[3]);par=par[par.corridor.eq(e.corridor)&par.period.eq(e.period)];par.to_csv(out/'inputs/calibrated_parameters.csv',index=False)
    inp=json.loads(files[4].read_text());cfg=json.loads(files[5].read_text());bands=pd.DataFrame(inp['rate_table']);bands.to_csv(out/'inputs/emission_rate_bands.csv',index=False)
    co=pd.read_csv(files[2]).set_index('pollutant');co.to_csv(out/'inputs/cubic_coefficients.csv')
    vehicle=cfg['vehicle'];(out/'inputs/vehicle_parameters.json').write_text(json.dumps(vehicle,indent=2))
    lower=bands.speed_lower_mph.to_numpy();quad=pd.DataFrame(inp['quadrature_384'])
    def index(v):return np.searchsorted(lower,np.asarray(v),side='right')-1
    def rate(v,p):return bands[p+'_g_per_veh_h'].to_numpy()[index(v)]
    def cubic(v,p):return sum(co.loc[p,'c'+str(k)]*np.asarray(v)**k for k in range(4))
    def vsp(v):
        s=np.asarray(v)*.44704
        return (vehicle['rolling_term_a']*s+vehicle['rotating_term_b']*s*s+vehicle['drag_term_c']*s**3)/vehicle['source_mass']
    D=g.d.sum();L=e.L_mi;vf=e.vf_mph;C=e.C_vphpl;Tf=L/vf;x=D/C
    P=max(e.fd*x**e.n,x);peak=Tf*e.fp*P**e.s;mean=e.theta*peak;mu=D/P;omega=C/(e.kj-C/vf);vq=mu/(e.kj-mu/omega)
    H=g.H.sum();Hp=D*(Tf+mean);vm=D*L/H;vp=D*L/Hp;Tq=vf*mean/(vf-vq);Tfree=Tf-vq*mean/(vf-vq)
    u=quad.u.to_numpy();a=e.profile_shape_a
    if e.theta>2/3:h=1-abs(2*u-1)**a;dh=-2*a*np.sign(2*u-1)*abs(2*u-1)**(a-1)
    else:h=(4*u*(1-u))**a;dh=4*a*(1-2*u)*(4*u*(1-u))**(a-1)
    N=D*quad.weight.to_numpy()*(1+peak/P*dh);w=peak*h;T=Tf+w;vr=L/T;tq=vf*w/(vf-vq);tf=Tf-vq*w/(vf-vq)
    q=pd.DataFrame(dict(u=u,quadrature_weight=quad.weight,vehicle_weight=N,delay_h=w,trip_time_h=T,speed_mph=vr,zero_acceleration_vsp=vsp(vr),free_time_h=tf,queue_time_h=tq))
    edges=np.r_[0,np.cumsum(g.d)];nedges=np.r_[0,np.cumsum(N)];edges[-1]=D;nedges[-1]=D
    def rebin(values):return np.diff(np.interp(edges,nedges,np.r_[0,np.cumsum(values)]))
    series=pd.DataFrame(dict(clock_h=g.clock_h.to_numpy(),clock_time=g.clock_time.to_numpy(),count_veh_5min=g.d.to_numpy(),H_O=g.H.to_numpy(),H_S=g.d.to_numpy()*H/D,H_R=rebin(N*T)))
    series['H_M']=series.H_R;series['H_A']=series.H_R
    series['Tfree_mean_h']=rebin(N*tf)/series.count_veh_5min;series['Tqueue_mean_h']=rebin(N*tq)/series.count_veh_5min
    for m in METHODS:
        series['v_'+m]=series.count_veh_5min*L/series['H_'+m]
        series['vsp_at_equivalent_speed_'+m]=vsp(series['v_'+m])
    # Average VSP over operating-state vehicle-hours, not at equivalent speed.
    vsp_numerators={
        'O':g.H.to_numpy()*vsp(g.speed_mph.to_numpy()),
        'S':series.H_S.to_numpy()*vsp(vm),
        'R':rebin(N*T*vsp(vr)),
        'M':rebin(N*(tf*vsp(vf)+tq*vsp(vq))),
    }
    vsp_numerators['A']=vsp_numerators['M'].copy()
    vsp_native={
        'O':float((g.H.to_numpy()*vsp(g.speed_mph.to_numpy())).sum()),
        'S':float(H*vsp(vm)),
        'R':float((N*T*vsp(vr)).sum()),
        'M':float((N*(tf*vsp(vf)+tq*vsp(vq))).sum()),
    }
    vsp_native['A']=vsp_native['M']
    vsp_rows=[];vsp_checks=[]
    for m in METHODS:
        series['vsp_exposure_weighted_'+m]=vsp_numerators[m]/series['H_'+m]
        aligned=float((series['H_'+m]*series['vsp_exposure_weighted_'+m]).sum())
        np.testing.assert_allclose(aligned,vsp_native[m],rtol=1e-11,atol=1e-10)
        vsp_checks.append(dict(method=m,native_vsp_times_vehicle_hours=vsp_native[m],aligned_vsp_times_vehicle_hours=aligned,residual=aligned-vsp_native[m]))
        for i,row in series.iterrows():
            vsp_rows.append(dict(method=m,bin_index=i+1,clock_time=row.clock_time,clock_h=row.clock_h,
                bin_start=str(g.datetime.iloc[i]),bin_end=str(g.datetime.iloc[i]+pd.Timedelta(minutes=5)),
                count_veh_per_lane=row.count_veh_5min,vehicle_hours_per_lane=row['H_'+m],
                equivalent_speed_mph=row['v_'+m],vsp_exposure_weighted_kw_t=row['vsp_exposure_weighted_'+m],
                vsp_at_equivalent_speed_kw_t=row['vsp_at_equivalent_speed_'+m],
                free_state_vsp_kw_t=float(vsp(vf)) if m in ['M','A'] else np.nan,
                queue_state_vsp_kw_t=float(vsp(vq)) if m in ['M','A'] else np.nan))
    pd.DataFrame(vsp_rows).to_csv(data/'vsp_time_series.csv',index=False)
    pd.DataFrame(vsp_checks).to_csv(data/'vsp_exposure_reconciliation.csv',index=False)
    np.testing.assert_allclose(series.vsp_exposure_weighted_M,series.vsp_exposure_weighted_A,rtol=0,atol=0)
    totals=[];decomposition=[];sensitivity=[];occupancy=[];cumulative=[]
    for p in POLS:
        O=(g.H*rate(g.speed_mph,p)).sum();S=H*rate(vm,p);R=(N*T*rate(vr,p)).sum();M=D*(Tfree*rate(vf,p)+Tq*rate(vq,p));A=D*(Tfree*cubic(vf,p)+Tq*cubic(vq,p));Sp=Hp*rate(vp,p)
        values=dict(O=O,S=S,R=R,M=M,A=A)
        q['R_'+p+'_g']=N*T*rate(vr,p);q['M_'+p+'_g']=N*(tf*rate(vf,p)+tq*rate(vq,p));q['A_'+p+'_g']=N*(tf*cubic(vf,p)+tq*cubic(vq,p))
        for m,value in values.items():
            assert np.isclose(value,e[m+'_'+p],rtol=1e-10)
            totals.append(dict(method=m,pollutant=p,emission_g=float(value),vehicle_hours=H if m in ['O','S'] else Hp,effective_rate_g_per_veh_h=value/(H if m in ['O','S'] else Hp),signed_error_pct=100*(value/O-1),absolute_error_pct=100*abs(value/O-1)))
            if m=='O':series[f'E_{m}_{p}_g']=g.H.to_numpy()*rate(g.speed_mph,p)
            elif m=='S':series[f'E_{m}_{p}_g']=series.count_veh_5min*S/D
            else:series[f'E_{m}_{p}_g']=rebin(q[m+'_'+p+'_g'])
            series[f'rate_{m}_{p}_g_h']=series[f'E_{m}_{p}_g']/series['H_'+m];series[f'cum_{m}_{p}_g']=series[f'E_{m}_{p}_g'].cumsum()
            assert np.isclose(series[f'E_{m}_{p}_g'].sum(),value,rtol=1e-11)
            xe=edges/D if m in ['O','S'] else nedges/D
            ye=np.r_[0,np.cumsum(series[f'E_{m}_{p}_g'])] if m in ['O','S'] else np.r_[0,np.cumsum(q[m+'_'+p+'_g'])]
            cumulative.extend(dict(method=m,pollutant=p,vehicle_share=xx,cumulative_g=yy) for xx,yy in zip(xe,ye))
        vals=[O,S,Sp,R,M,A]
        for i,(before,after) in enumerate(zip(vals[:-1],vals[1:])):
            decomposition.append(dict(pollutant=p,step=i+1,from_method=['O','S','S_pred','R','M'][i],to_method=['S','S_pred','R','M','A'][i],from_g=before,to_g=after,delta_g=after-before,delta_pct_O=100*(after-before)/O))
        rf=rate(vf,p);rfbelow=bands.iloc[index(vf)-1][p+'_g_per_veh_h'];sensitivity.append(dict(pollutant=p,vf_mph=vf,previous_rate_boundary_mph=lower[index(vf)],distance_above_boundary_mph=vf-lower[index(vf)],current_free_rate_g_h=rf,previous_band_rate_g_h=rfbelow,original_M_g=M,fixed_times_previous_free_rate_M_g=D*(Tfree*rfbelow+Tq*rate(vq,p)),rate_only_change_g=D*Tfree*(rfbelow-rf)))
    for m in ['O','S','R','M']:
        vs=g.speed_mph.to_numpy() if m=='O' else np.array([vm]) if m=='S' else vr if m=='R' else np.array([vf,vq])
        hours=g.H.to_numpy() if m=='O' else np.array([H]) if m=='S' else N*T if m=='R' else D*np.array([Tfree,Tq])
        for band in range(len(bands)):
            hh=hours[index(vs)==band].sum();occupancy.append(dict(method=m,source_operating_mode=bands.iloc[band].source_operating_mode,speed_lower_mph=lower[band],vehicle_hours=hh,time_share=hh/hours.sum()))
    tot=pd.DataFrame(totals);dc=pd.DataFrame(decomposition);occ=pd.DataFrame(occupancy);sens=pd.DataFrame(sensitivity)
    tot.to_csv(data/'emission_totals.csv',index=False);dc.to_csv(data/'error_decomposition.csv',index=False);occ.to_csv(data/'lookup_band_exposure.csv',index=False);sens.to_csv(data/'free_rate_boundary_sensitivity.csv',index=False)
    series.to_csv(data/'common_time_series.csv',index=False);q.to_csv(data/'reconstructed_integration.csv',index=False);pd.DataFrame(cumulative).to_csv(data/'cumulative_vehicle_share.csv',index=False)
    state=dict(episode_id=EPISODE,bins=len(g),D_veh=D,L_mi=L,vf_mph=vf,C_vphpl=C,Tf_h=Tf,x_h=x,P_observed_h=e.P_h,P_predicted_h=P,peak_delay_observed_h=e.wt2_h,peak_delay_predicted_h=peak,mean_delay_observed_h=H/D-Tf,mean_delay_predicted_h=mean,vq_observed_fd_mph=e.vq_mph,vq_predicted_mph=vq,H_observed_veh_h=H,H_predicted_veh_h=Hp,observed_mean_speed_mph=vm,predicted_mean_speed_mph=vp,free_mean_time_h=Tfree,queue_mean_time_h=Tq,observed_speed_min_mph=g.speed_mph.min(),observed_speed_max_mph=g.speed_mph.max(),calibration_N_source=int(par.N_source.iloc[0]),calibration_scope=e.calibration_scope,physical_observed_pass=bool(e.physical_observed_pass),physical_predicted_pass=bool(e.physical_predicted_pass),observed_lookup_band_count=int(len(np.unique(index(g.speed_mph)))),free_flow_lookup_mode=int(bands.iloc[index(vf)].source_operating_mode),queue_lookup_mode=int(bands.iloc[index(vq)].source_operating_mode))
    (data/'calculated_state.json').write_text(json.dumps(state,indent=2))
    audit=dict(source_sha256=hashes,selected_case=EPISODE,selection_eligible=4,all_20_saved_emission_totals_match=True,all_20_common_clock_totals_conserved=True,all_observed_speeds_one_lookup_band=state['observed_lookup_band_count']==1,
        quadrature_count_relative_error=float(N.sum()/D-1),quadrature_VHT_relative_error=float((N*T).sum()/Hp-1),maximum_speed_identity_error_mph=float(np.max(abs((vf*tf+vq*tq)/(tf+tq)-vr))),minimum_free_time_h=float(tf.min()),minimum_queue_time_h=float(tq.min()),
        all_5_vsp_exposure_totals_conserved=True,maximum_vsp_exposure_residual=float(max(abs(z['residual']) for z in vsp_checks)),vsp_definition='Operating-state VSP weighted by vehicle-hours; equivalent-speed VSP retained separately')
    assert abs(audit['quadrature_count_relative_error'])<1e-10 and abs(audit['quadrature_VHT_relative_error'])<1e-10
    (data/'audit.json').write_text(json.dumps(audit,indent=2))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelcolor':'#17324D','text.color':'#17324D','axes.edgecolor':'#17324D','grid.color':'#E2E8F0','svg.fonttype':'none','pdf.fonttype':42,'figure.facecolor':'white','axes.facecolor':'white'})
    end=e.t3.hour+e.t3.minute/60;clock=series.clock_h.to_numpy();ticks=np.arange(16.,19.01,.5)
    labels=[f'{int(t):02d}:{round((t%1)*60):02d}' for t in ticks]
    def finish(fig,name):
        for ax in fig.axes:ax.grid(linewidth=.6);ax.set_axisbelow(True);ax.spines[['top','right']].set_visible(False)
        fig.tight_layout(rect=[0,0,1,.94] if fig.legends else [0,0,1,1])
        for ext in ['pdf','svg','png']:fig.savefig(figdir/(name+'.'+ext),dpi=220,bbox_inches='tight')
        plt.close(fig)
    def clock_axis(ax):ax.set_xticks(ticks,labels);ax.set_xlim(clock[0],end);ax.set_xlabel('Profile clock time')
    def stepped(ax,field,scale=1):
        for m in METHODS:ax.step(np.r_[clock,end],np.r_[series[field.format(m=m)].to_numpy(),series[field.format(m=m)].iloc[-1]]/scale,where='post',color=COL[m],ls=STYLE[m],lw=2.6 if m=='R' else 1.4 if m=='M' else 1.15,label=m,zorder=3 if m=='A' else 2)
        clock_axis(ax)
    fig,axes=plt.subplots(2,1,figsize=(7,4.9))
    stepped(axes[0],'v_{m}');axes[0].set_ylabel('Equivalent link speed (mph)');axes[0].legend(ncol=5,frameon=False,loc='upper center',fontsize=8)
    axes[1].step(np.r_[clock,end],np.r_[g.d,g.d.iloc[-1]],where='post',color=COL['O']);clock_axis(axes[1]);axes[1].set_ylabel('Vehicles per lane / 5 min')
    finish(fig,'traffic_profiles')
    vg=np.linspace(5,75,1401);curve=pd.DataFrame(dict(speed_mph=vg,zero_acceleration_vsp=vsp(vg),CO2_lookup_g_h=rate(vg,'CO2'),CO2_cubic_g_h=cubic(vg,'CO2')));curve.to_csv(data/'speed_vsp_rate_curves.csv',index=False)
    fig,axes=plt.subplots(3,1,figsize=(7,6.3))
    for m in ['O','S','R','M']:
        z=series['vsp_exposure_weighted_'+m].to_numpy()
        axes[0].step(np.r_[clock,end],np.r_[z,z[-1]],where='post',color=COL[m],ls=STYLE[m],lw=1.6,label='M = A' if m=='M' else m)
    axes[0].set_ylabel('Exposure-weighted VSP (kW/t)');clock_axis(axes[0]);axes[0].legend(frameon=False,ncol=4,fontsize=8,loc='upper center')
    axes[1].plot(vg,rate(vg,'CO2')/1000,color=COL['O'],label='Lookup');axes[1].plot(vg,cubic(vg,'CO2')/1000,color=COL['A'],ls='--',label='Cubic');axes[1].set_ylabel(r'CO$_2$ rate (kg/veh h)');axes[1].set_xlabel('Operating speed (mph)');axes[1].legend(frameon=False,loc='upper center',ncol=2)
    axes[1].axvspan(g.speed_mph.min(),g.speed_mph.max(),color=COL['S'],alpha=.15)
    axes[1].axvline(vq,color=COL['M'],lw=1,ls=':');axes[1].axvline(vf,color=COL['A'],lw=1,ls=':')
    modes=sorted(occ.loc[occ.time_share>1e-8,'source_operating_mode'].unique());xx=np.arange(len(modes))
    for j,m in enumerate(['O','S','R','M']):
        z=occ[occ.method.eq(m)].set_index('source_operating_mode');axes[2].bar(xx+(j-1.5)*.18,[100*z.loc[b,'time_share'] for b in modes],width=.18,color=COL[m],label=m)
    axes[2].set_xticks(xx,[str(int(b)) for b in modes]);axes[2].set_xlabel('Operating-mode lookup band');axes[2].set_ylabel('Vehicle-hour share (%)');axes[2].legend(frameon=False,ncol=4)
    finish(fig,'vsp_and_rate_mapping')
    fig,axes=plt.subplots(2,2,figsize=(7.5,6.2))
    for col,p in enumerate(['CO2','NOx']):
        scale=1000 if p=='CO2' else 1;unit='kg' if p=='CO2' else 'g'
        stepped(axes[0,col],f'rate_{{m}}_{p}_g_h',scale);axes[0,col].set_ylabel(p+' effective rate ('+unit+'/veh h)')
        stepped(axes[1,col],f'E_{{m}}_{p}_g',scale);axes[1,col].set_ylabel(p+' contribution ('+unit+'/bin)')
        for ax in axes[:,col]:ax.tick_params(axis='x',labelrotation=30)
    fig.legend(*axes[0,0].get_legend_handles_labels(),loc='upper center',ncol=5,frameon=False)
    finish(fig,'emission_time_series')
    cum=pd.DataFrame(cumulative);fig,axes=plt.subplots(2,2,figsize=(7.5,6.3))
    for row,p in enumerate(['CO2','NOx']):
        scale=1000 if p=='CO2' else 1;unit='kg' if p=='CO2' else 'g'
        for m in METHODS:
            z=cum[cum.method.eq(m)&cum.pollutant.eq(p)];axes[row,0].plot(z.vehicle_share*100,z.cumulative_g/scale,color=COL[m],ls=STYLE[m],label=m,lw=1.5)
            axes[row,1].plot(np.r_[clock,end],np.r_[0,series[f'cum_{m}_{p}_g']]/scale,color=COL[m],ls=STYLE[m],label=m,lw=1.5)
        axes[row,0].set_xlabel('Cumulative vehicle share (%)');clock_axis(axes[row,1]);axes[row,1].tick_params(axis='x',labelrotation=30)
        for ax in axes[row,:]:ax.set_ylabel(p+' cumulative emission ('+unit+')')
    fig.legend(*axes[0,0].get_legend_handles_labels(),loc='upper center',ncol=5,frameon=False)
    finish(fig,'cumulative_contributions')
    fig,axes=plt.subplots(2,2,figsize=(7.5,5.2))
    descriptions=[r'$S-O$',r'$S_p-S$',r'$R-S_p$',r'$M-R$',r'$A-M$']
    for ax,p in zip(axes.flat,POLS):
        z=dc[dc.pollutant.eq(p)];ax.barh(descriptions,z.delta_pct_O,color=[COL['S'],'#64748B',COL['R'],COL['M'],COL['A']]);ax.axvline(0,color='#17324D',lw=.8);ax.set_title(p);ax.set_xlabel('Signed contribution (% of O)')
    finish(fig,'error_components')

    def fmt(v,n=3):return f'{float(v):,.{n}f}'
    def tex_table(header,rows,align):
        return '\\par\\noindent\\begin{tabular*}{\\linewidth}{@{\\extracolsep{\\fill}}'+align+'@{}}\\toprule\n'+' & '.join(header)+r'\\\midrule'+'\n'+ ('\\\\\\midrule[.3pt]\n'.join(' & '.join(row) for row in rows))+r'\\\bottomrule\end{tabular*}\par'
    resultrows=[];errorrows=[]
    for m in METHODS:
        z=tot[tot.method.eq(m)].set_index('pollutant')
        resultrows.append([m]+[fmt(z.loc[p,'emission_g']/1000 if p=='CO2' else z.loc[p,'emission_g'],3) for p in POLS])
        errorrows.append([m]+['Reference' if m=='O' else fmt(z.loc[p,'absolute_error_pct'],2) for p in POLS])
    resulttable=tex_table(['Method','CO$_2$ (kg)','NO$_x$ (g)','CO (g)','HC (g)'],resultrows,'lrrrr')
    errortable=tex_table(['Method','CO$_2$','NO$_x$','CO','HC'],errorrows,'lrrrr')
    trafficrows=[]
    for label,obs,pred,mult in [('Duration (min)',e.P_h,P,60),('Mean trip time (s)',H/D,Hp/D,3600),('Mean delay (s)',H/D-Tf,mean,3600),('Peak delay (s)',e.wt2_h,peak,3600),('Queue FD speed (mph)',e.vq_mph,vq,1)]:trafficrows.append([label,fmt(obs*mult,2),fmt(pred*mult,2),f'{100*(pred/obs-1):+.2f}'])
    traffictable=tex_table(['Quantity','Observed-derived','Fitted','Difference (\\%)'],trafficrows,'lrrr')
    dcrows=[]
    for p in POLS:dcrows.append([p.replace('CO2','CO$_2$').replace('NOx','NO$_x$')]+[f'{v:+.2f}' for v in dc[dc.pollutant.eq(p)].delta_pct_O])
    dctable=tex_table(['Pollutant','S$-$O','S$_p-$S','R$-$S$_p$','M$-$R','A$-$M'],dcrows,'lrrrrr')
    sCO=sens[sens.pollutant.eq('CO2')].iloc[0];tCO=tot[tot.pollutant.eq('CO2')].set_index('method')
    report= (HERE/'reports/source/formulas_and_preamble.tex').read_text()
    report+=r'''
\newpage\fontsize{10}{13}\selectfont
{\fontsize{19}{23}\selectfont\bfseries\color{navy}Arizona detector 141: selected comparison}\par
{\color{muted}I-10 westbound. Constructed November 2016 average-weekday profile.}\par
\vspace{7pt}\textbf{Why this case was selected}\par
Among the 137 common episodes, four meet a strict diagnostic screen: absolute mean-trip-time error at most 5\%; mean-delay, peak-delay, duration and inferred FD queue-speed errors each at most 10\%; and the observed-derived finite-link check passes. This case has the largest CO$_2$ absolute-error gap between M and S among those four. These criteria select one diagnostic case; they do not estimate an overall method ranking.
\vspace{8pt}TRAFFICTABLE
\notebox{Both observed-derived and fitted finite-link checks pass. Traffic predictions remain close under the stated five error screens, yet the emission estimates differ substantially. The FD queue speed is an inferred operating state; it is not the minimum recorded whole-link speed.}
\vspace{10pt}\textbf{Episode-total emissions per lane}\par
RESULTTABLE
\vspace{10pt}\textbf{Absolute percentage difference from O (\%)}\par
ERRORTABLE
\vspace{8pt}For this single episode, the absolute percentage difference is $100|E_m-E_O|/E_O$. It is not a new pooled WAPE estimate.
\notebox{S uses the reference's observed vehicle-hours, while M uses a slightly smaller fitted exposure. Nevertheless, M is much higher than O. The following pages show how the time allocated to free-flow and queue operating speeds changes the effective emission rate. The reference contains no measured trajectories or exhaust.}

\newpage
{\fontsize{19}{23}\selectfont\bfseries\color{navy}Traffic inputs and speed profiles}\par
{\color{muted}One whole episode: 15:45 inclusive to 19:05 exclusive, 40 five-minute bins.}\par
\vspace{6pt}
INPUTTABLE
\vspace{5pt}The AZ I-10 westbound PM fit uses NSOURCE source episodes. This November profile averages 13 complete weekdays. The archived monthly profile is used directly; its date label identifies the month, not a single observed traffic day. The free-flow and FD card are detector-specific.
\begin{center}\includegraphics[width=\linewidth]{../../figures/traffic_profiles.pdf}\end{center}
\textbf{Equivalent speed for M/A.} The time allocation gives
\[v_i^{\rm eff}=\frac{v_f\bar t_{f,i}+v_q\bar t_{q,i}}{\bar t_{f,i}+\bar t_{q,i}}=\frac{L}{\bar t_{f,i}+\bar t_{q,i}}.\]
R, M and A overlap because they have identical allocated vehicle-hours and distance. Their operating speeds and rates differ. M/A use $v_f=VF$ and $v_q=VQ$ mph internally, rather than the displayed equivalent speed.
\notebox{The common clock is a display allocation: modeled vehicle groups are split into the observed five-minute count groups in cumulative-count order. It preserves every method's total. It does not infer when exhaust was physically released on the roadway.}

\newpage
{\fontsize{19}{23}\selectfont\bfseries\color{navy}VSP profiles over the episode}\par
{\color{muted}Same count-aligned clock as the speed profiles; zero acceleration and level road.}\par
\vspace{4pt}Let $z(v)=\operatorname{VSP}_0(v)$ in kW/t and $a_{ij}$ be the model-node count assigned to observed bin $i$. The plotted VSP is weighted by vehicle-hours:
\[
\bar z_{R,i}=\frac{\sum_j a_{ij}T_j z(v_{R,j})}{H_{R,i}},\qquad
\bar z_{M,i}=\bar z_{A,i}=\frac{\sum_j a_{ij}[t_{f,j}z(v_f)+t_{q,j}z(v_q)]}{H_{R,i}}.
\]
O uses $z(v_i)$; S uses the constant $z(\bar v_{\rm obs})$. M and A overlap because their operating speeds and exposure are identical. A changes only the emission-rate approximation.
The supplied mapping is $z(v)=(0.156461s_v+0.00200193s_v^2+0.000492646s_v^3)/1.4788$, with $s_v=0.44704v$ for speed $v$ in mph.
\begin{center}\includegraphics[width=.95\linewidth]{../../figures/vsp_and_rate_mapping.pdf}\end{center}
\textbf{Top: VSP over time.} Each step spans one observed five-minute bin. This exposure-weighted quantity generally differs from $z(v_i^{\rm eff})$, which is supplied separately in the CSV. It is not an emission rate or a measured trajectory VSP.\par
\textbf{Middle: rate assignment.} Shading marks observed speeds; dotted lines mark $v_q$ (green) and $v_f$ (orange). The lookup and cubic functions map the operating conditions to rates.\par
\textbf{Bottom: total exposure by lookup band.} O and R span several bands; S uses one band. M allocates exposure to modes QMODE and FMODE. A uses those same two speeds with cubic rates.
\notebox{Equal equivalent speed does not imply equal operating-state VSP. R, M and A share fitted vehicle-hours, but M/A can place substantial exposure at free-flow speed while compensating with a slow queue state. The VSP profile is a diagnostic average of those states, not a new rate input. The emission calculations and all 20 episode totals are unchanged.}

\newpage
{\fontsize{19}{23}\selectfont\bfseries\color{navy}Rates and five-minute contributions}\par
{\color{muted}Same observed count in each bin; method-specific travel-time exposure and rates.}\par
\vspace{5pt}Legend: \legendkey{methodO}{O}\quad\legendkey{methodS}{S}\quad\legendkey{methodR}{R}\quad\legendkey{methodM}{M}\quad\legendkey{methodA}{A}
\begin{center}\includegraphics[width=\linewidth]{../../figures/emission_time_series.pdf}\end{center}
\textbf{Top: effective rate.} In each bin, $r^{\rm eff}_{m,i}=E_{m,i}/H_{m,i}$. For R this averages the assigned rates of its reconstructed vehicle groups. For M/A it averages the free-flow and queue rates by their time allocations. It is generally not the lookup at the displayed equivalent speed.
\vspace{8pt}\textbf{Bottom: contribution from that bin's vehicles.} $E_{m,i}=H_{m,i}r^{\rm eff}_{m,i}$. The five-minute duration creates the vehicle count; a vehicle's exposure is its complete-link travel time. Each plotted series sums to the corresponding episode total on page 2.
\notebox{O and S have identical total exposure. Their five-minute contributions differ because S assigns one constant trip time and rate to every counted vehicle. R/M/A share fitted exposure; their remaining differences come from the speeds at which rates are evaluated and from lookup versus cubic approximation.}

\newpage
{\fontsize{19}{23}\selectfont\bfseries\color{navy}How the contributions accumulate}\par
{\color{muted}Vehicle-order view on the left; conservative common-clock allocation on the right.}\par
\vspace{5pt}Legend: \legendkey{methodO}{O}\quad\legendkey{methodS}{S}\quad\legendkey{methodR}{R}\quad\legendkey{methodM}{M}\quad\legendkey{methodA}{A}
\begin{center}\includegraphics[width=\linewidth]{../../figures/cumulative_contributions.pdf}\end{center}
\textbf{Vehicle share.} O follows the observed bin order. R/M/A follow reconstructed entry-group order. S has constant emission per vehicle. All curves terminate at the same count $D$, with their own episode emission total.
\vspace{8pt}\textbf{Clock time.} Each boundary value sums the complete-link emissions assigned to all preceding bins. Connecting lines interpolate bin contributions for display and imply no sub-bin exhaust timing.
\notebox{For observed cumulative counts $B_i$ and modeled cumulative counts $N_j$, the overlap count is
\[n_{ij}=\max\{0,\min(B_i,N_j)-\max(B_{i-1},N_{j-1})\}.\]
Use $H_i=\sum_jn_{ij}T_j$ and $E_i=\sum_jn_{ij}e_j$. Both count and emission totals are conserved. The underlying 384-node integration and all 40 common-clock rows are supplied as CSV files.}

\newpage
{\fontsize{19}{23}\selectfont\bfseries\color{navy}Where the differences enter}\par
{\color{muted}An exact signed accounting sequence, conditional on the chosen order.}\par
Define $E_{S,p}=H_{\rm pred}r_0(DL/H_{\rm pred})$, a single-speed calculation with the fitted exposure shared by R/M/A. Then
\[
E_A-E_O=(E_S-E_O)+(E_{S,p}-E_S)+(E_R-E_{S,p})+(E_M-E_R)+(E_A-E_M).
\]
\begin{center}\includegraphics[width=.96\linewidth]{../../figures/error_components.pdf}\end{center}
\textbf{Signed components as a percentage of O}\par
DCTABLE
\vspace{7pt}The fitted exposure differs from O by HCHANGE\%. $S_p-S$ combines this exposure change with any lookup-rate change caused by the fitted mean speed. $R-S_p$ adds reconstructed trip-speed variation. $M-R$ changes the operating-speed representation at equal fitted vehicle-hours. $A-M$ changes only the rate approximation.
\notebox{The traffic screens pass, so a large travel-time calibration error is not needed to create this discrepancy. M and R have the same fitted vehicle-hours, but evaluate rates at different speed distributions. The large M--R component isolates that representation difference within this accounting sequence. It does not identify the unknown real trajectory emissions.}
\vspace{7pt}\textbf{Audit and source files.} All 20 episode totals reproduce the frozen matched-episode record. The supplied selection table contains all 137 cases, the five traffic error screens, the physical check and the four passing cases. The full-precision inputs, rate-band exposure, common-clock data, error components, editable vector figures and this report source are included with the case. No calibration, episode boundary or published result was replaced.
\end{document}
'''
    inputtable=tex_table(['Input','Value','Input','Value'],[['$D$ (veh/lane)',fmt(D,2),'$L$ (mi)',fmt(L,3)],['$C$ (veh/h/lane)',fmt(C,2),'$v_f$ (mph)',fmt(vf,3)],['$x=D/C$ (h)',fmt(x,4),'$T_f$ (s)',fmt(Tf*3600,2)],['$f_d$; $n$',fmt(e.fd,4)+'; '+fmt(e.n,4),'$f_p$; $s$',fmt(e.fp,4)+'; '+fmt(e.s,4)],[r'$\theta$; $k_j$',fmt(e.theta,4)+'; 220','Speed CV',fmt(selected.observed_speed_count_cv,4)]],'lrlr')
    replacements={'TRAFFICTABLE':traffictable,'RESULTTABLE':resulttable,'ERRORTABLE':errortable,'INPUTTABLE':inputtable,'NSOURCE':str(int(par.N_source.iloc[0])),'DCTABLE':dctable,'BOUNDARYDIST':fmt(sCO.distance_above_boundary_mph,5),'BOUNDARY':fmt(sCO.previous_rate_boundary_mph,5),'RFPREV':fmt(sCO.previous_band_rate_g_h/1000,3),'RF':fmt(sCO.current_free_rate_g_h/1000,3),'RATECHANGE':f'{sCO.rate_only_change_g/1000:+.2f}','HCHANGE':f'{100*(Hp/H-1):+.3f}','VMIN':fmt(g.speed_mph.min(),3),'VMAX':fmt(g.speed_mph.max(),3),'VF':fmt(vf,3),'VQ':fmt(vq,3),'QMODE':str(state['queue_lookup_mode']),'FMODE':str(state['free_flow_lookup_mode'])}
    for key in sorted(replacements,key=len,reverse=True):report=report.replace(key,replacements[key])
    report='\n'.join(line for line in report.splitlines() if not line.startswith(r'\vspace{5pt}Legend:'))+'\n'
    report=report.replace(r'\vspace{8pt}\textbf',r'\par\vspace{8pt}\textbf')
    tex=out/'reports/source/AZ_I10_Detector141_Emission_Diagnostic.tex';tex.write_text(report,encoding='utf-8')
    shutil.copy2(HERE/'reports/source/formulas_and_preamble.tex',out/'reports/source/formulas_and_preamble.tex')
    if args.pdf:
        for _ in range(2):
            result=subprocess.run([args.pdflatex,'-interaction=nonstopmode','-halt-on-error','-no-shell-escape',tex.name],cwd=tex.parent,capture_output=True,text=True)
            if result.returncode:raise RuntimeError(result.stdout[-5000:])
        log=tex.with_suffix('.log').read_text(errors='replace')
        if 'Overfull' in log or 'Missing character:' in log:raise RuntimeError('LaTeX layout warning; inspect generated log')
        shutil.copy2(tex.with_suffix('.pdf'),out/'reports/AZ_I10_Detector141_Emission_Diagnostic.pdf')
    print(json.dumps({'episode':EPISODE,'all_saved_totals_match':True,'candidate_count':4,'outputs':str(out)},indent=2))


if __name__=='__main__':main()
