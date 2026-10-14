"""Editable v33 Figure 2 and fixed-parameter Gamma curves.

Frozen inputs; no traffic fit or empirical result is recalculated here.
Run with NumPy, pandas, scipy, Matplotlib and Times New Roman installed.
Every plotted mark is a vector object. CSV exports give every curve coordinate.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from _paths import FROZEN, OUT as REPRO_OUT
import json, hashlib
import numpy as np
import pandas as pd
from scipy.optimize import brentq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.collections import LineCollection
from matplotlib.text import Text
import polish_style as P

HERE=Path(__file__).resolve().parent
DATA=FROZEN/'presentation/us06'
OUT=REPRO_OUT/'figs'
QA=REPRO_OUT/'qa'
CALIBRATION=FROZEN/'calibration'
OUT.mkdir(exist_ok=True); QA.mkdir(exist_ok=True)
P.apply()

def clean(ax):
    ax.set_facecolor(P.WHITE)
    ax.spines[['top','right']].set_visible(False)
    ax.grid(False)

def save(fig,stem):
    fig.canvas.draw(); renderer=fig.canvas.get_renderer()
    texts=[];seen=set();outside=set()
    for ax in fig.axes:
        for axis in (ax.xaxis,ax.yaxis):
            lo,hi=sorted(axis.get_view_interval())
            for tick in list(axis.get_major_ticks())+list(axis.get_minor_ticks()):
                if not lo-1e-10<=tick.get_loc()<=hi+1e-10:
                    outside.update((id(tick.label1),id(tick.label2)))
    for item in fig.findobj(match=Text):
        if id(item) in seen or id(item) in outside or not item.get_visible() or not item.get_text().strip():continue
        seen.add(id(item));b=Text.get_window_extent(item,renderer)
        if b.width<=0 or b.height<=0:continue
        texts.append({'text':item.get_text(),'bbox_px':list(b.extents)})
    hits=[]
    for i,a in enumerate(texts):
        x0,y0,x1,y1=a['bbox_px']
        for b in texts[i+1:]:
            u0,v0,u1,v1=b['bbox_px'];dx=min(x1,u1)-max(x0,u0);dy=min(y1,v1)-max(y0,v0)
            if dx>.5 and dy>.5:hits.append([a['text'],b['text'],dx,dy])
    W,H=fig.bbox.width,fig.bbox.height
    clipped=[t for t in texts if t['bbox_px'][0]<0 or t['bbox_px'][1]<0 or t['bbox_px'][2]>W or t['bbox_px'][3]>H]
    for ext in ['pdf','svg','png']:fig.savefig(OUT/f'{stem}.{ext}',dpi=600,facecolor='white')
    fig.savefig(QA/f'{stem}_preview.png',dpi=170,facecolor='white')
    (QA/f'{stem}_layout.json').write_text(json.dumps({'text_intersections':hits,'clipped_text':clipped},indent=2))
    plt.close(fig)
    return {'text_intersections':len(hits),'clipped_text':len(clipped)}

def fig2():
    import us06_comparison as supplied
    data,curve,threshold=supplied.prepare(DATA, rate_dir=CALIBRATION/'emission_input',
        coefficient_file=CALIBRATION/'cubic_rate_coefficients.csv')
    # The supplied script changes global style at import. Reapply manuscript style.
    P.apply()
    stats=supplied.summarize(data,threshold)
    released=pd.read_csv(DATA/'US06_emission_rate_comparison_by_second.csv')
    for col in ['time_s','speed_mph','CO2_kgph','CO2_zero_accel_kgph','delta_full_minus_zero_kgph','dt_s']:
        assert np.allclose(data[col],released[col],atol=1e-8,rtol=1e-9),col
    released_stats=pd.read_csv(DATA/'US06_driving_mode_summary.csv')
    assert np.allclose(stats.total_full_minus_zero_g,released_stats.total_full_minus_zero_g,atol=1e-8)
    xx,yy,cubic_x,cubic_y=supplied.make_curves(data,curve,CALIBRATION/'emission_input')
    fig=plt.figure(figsize=(7.07,6.4))
    gs=fig.add_gridspec(3,2,left=.09,right=.975,top=.955,bottom=.075,
        height_ratios=[1.05,1.45,1.00],hspace=.62,wspace=.32)
    a=fig.add_subplot(gs[0,:]);b=fig.add_subplot(gs[1,0]);c=fig.add_subplot(gs[1,1]);d=fig.add_subplot(gs[2,:])
    # Reserve a separate strip between panel (a)'s axis label and the two-row
    # shared legend; do not rely on automatic padding around long labels.
    a.set_position([.09,.79,.885,.16]);b.set_position([.09,.38,.38,.25])
    c.set_position([.595,.38,.38,.25]);d.set_position([.115,.075,.86,.175])
    # Preserve panel (a)'s trace, classification, labels and color semantics.
    v=data.speed_mph.to_numpy();acc=data.acceleration_mph_per_s.to_numpy()
    braking=data.OpModeID.eq(0).to_numpy()
    typ=np.where(v<1,0,np.where(braking,1,np.where(acc>.5,2,3)))
    colors=np.array([P.MID,P.INK,P.ACCENT,P.LIGHT])
    labels=['Idle','Braking','Acceleration','Other running']
    pts=np.c_[data.time_s,v];seg=np.stack([pts[:-1],pts[1:]],axis=1)
    a.add_collection(LineCollection(seg,colors=colors[typ[1:]],linewidths=1.25))
    a.set(xlim=(0,600),ylim=(0,105),xlabel='Test time (s)',ylabel='Speed (mph)')
    a.set_title('(a) EPA US06 prescribed driving cycle',loc='left')
    a.legend(handles=[Line2D([],[],color=co,label=la,lw=1.6) for co,la in zip(colors,labels)],
        loc='upper left',ncol=4,fontsize=7.3,columnspacing=1.8)
    phase_style={'Accelerating':(P.ACCENT,'o'),'Cruising':(P.MID,'o'),'Decelerating':(P.INK,'o')}
    for phase,(color,marker) in phase_style.items():
        sel=data[data.driving_phase.eq(phase)]
        norm=sel[sel.OpModeID.ne(0)];br=sel[sel.OpModeID.eq(0)]
        for ax,column in [(b,'CO2_kgph'),(c,'delta_full_minus_zero_kgph')]:
            ax.scatter(norm.speed_mph,norm[column],s=11,marker=marker,facecolors=color,edgecolors='white',linewidths=.2,alpha=.67,zorder=3)
            ax.scatter(br.speed_mph,br[column],s=13,marker='D',facecolors='none',edgecolors=color,linewidths=.6,zorder=4)
    b.plot(xx,yy,color=P.INK,lw=1.15,label='Zero-acceleration lookup',zorder=2)
    b.plot(cubic_x,cubic_y,color=P.MID,lw=1.3,ls='--',label='Speed-only cubic',zorder=3)
    c.axhline(0,color=P.MID,lw=.7)
    b.set(xlim=(0,82),ylim=(0,55),xlabel='Speed (mph)',ylabel=r'CO$_2$ rate (kg/h)')
    c.set(xlim=(0,82),ylim=(-27,45),xlabel='Speed (mph)',ylabel=r'Rate difference (kg/h)')
    b.set_title('(b) Operating-mode and speed-only rates',fontsize=8.5,loc='left')
    c.set_title('(c) Operating-mode minus zero acceleration',fontsize=8.5,loc='left')
    for ax in (b,c):ax.set_xticks([0,20,40,60,80])
    handles=[Line2D([],[],marker='o',linestyle='none',color=co,label=ph,markersize=3.7) for ph,(co,_) in phase_style.items()]
    handles += [Line2D([],[],marker='D',linestyle='none',color=P.INK,markerfacecolor='none',label='Braking mode',markersize=3.7),
        Line2D([],[],color=P.INK,lw=1.15,label='Zero-acceleration lookup'),
        Line2D([],[],color=P.MID,lw=1.3,ls='--',label='Speed-only cubic')]
    fig.legend(handles=handles,loc='center',bbox_to_anchor=(.54,.697),ncol=3,columnspacing=1.3,
        handletextpad=.45,labelspacing=.6,fontsize=7.2)
    phases=['Accelerating','Cruising','Decelerating','Idle']
    values=stats.set_index('driving_phase').loc[phases,'total_full_minus_zero_g'].tolist();values.append(sum(values))
    bar_colors=[P.ACCENT,P.MID,P.INK,P.LIGHT,P.DARK]
    y=np.arange(5)
    d.barh(y,values,height=.55,color=bar_colors)
    total=float((data.CO2_kgph*data.dt_s).sum()/3.6)
    for i,value in enumerate(values):
        label=f'{value:+.1f} g ({value/total*100:+.1f}%)' if abs(value)<1 else f'{value:+.0f} g ({value/total*100:+.1f}%)'
        d.text(value+12 if value>=0 else value-12,i,label,va='center',ha='left' if value>=0 else 'right',fontsize=7.5)
    d.set_yticks(y,labels=['Acceleration','Cruising','Deceleration','Idling','Net difference']);d.invert_yaxis()
    pos=d.get_position();d.set_position([.115,pos.y0,.86,pos.height])
    d.set(xlim=(-580,910),xlabel=r'CO$_2$ difference over 600 s (g)');d.set_xticks([-400,-200,0,200,400,600,800])
    d.axvline(0,color=P.MID,lw=.65)
    d.set_title('(d) Contribution by driving phase',loc='left')
    for ax in (a,b,c,d):clean(ax)
    layout=save(fig,'fig1_emission_rate')
    data.to_csv(OUT/'fig2_plotted_seconds.csv',index=False);stats.to_csv(OUT/'fig2_phase_totals.csv',index=False)
    pd.DataFrame({'speed_mph':xx,'zero_acceleration_kgph':yy}).to_csv(OUT/'fig2_lookup_curve.csv',index=False)
    return {'supplied_csv_reproduced':True,'lookup_entries_verified':701,'cycle_intervals':600,
        'full_total_g':total,'zero_acceleration_total_g':float((data.CO2_zero_accel_kgph*data.dt_s).sum()/3.6),
        'difference_g':sum(values[:4]),'layout':layout,'phase_threshold_mph_per_s':.5,
        'panel_a_preserved':'601 supplied US06 speeds and original idle/braking/acceleration/other-running rule',
        'panel_bc_idle':'Idling excluded from scatter as in supplied compact; included in panel d totals',
        'rates_are_model_estimates_not_exhaust_measurements':True}

def gamma_behavior():
    ref=json.loads((CALIBRATION/'audit/table3_reference_state.json').read_text());par=ref['traffic_parameters']
    vf,C,omega,kj=[ref[k] for k in ['vf_mph','C_vphpl','omega_mph','kj_veh_mi_lane']]
    fd,n,fp,s=[par[k] for k in ['fd','n','fp','s']]
    low=.4681022684444174;source_hi=5.885911238721851
    def Pofx(x):return np.maximum(fd*np.asarray(x)**n,x)
    def vqx(x):return C*np.asarray(x)/(kj*Pofx(x)-C*np.asarray(x)/omega)
    def allowance(x):return vf/vqx(x)-1-fp*Pofx(x)**s
    hi=brentq(allowance,1,source_hi)
    x=np.linspace(low,hi,450); v=np.linspace(5,vf,500)
    assert np.all(allowance(x)>-1e-9)
    assert np.all((vqx(x)>=5)&(vqx(x)<vf))
    fig,axes=plt.subplots(1,2,figsize=(7.07,2.95))
    fig.subplots_adjust(left=.09,right=.98,top=.88,bottom=.27,wspace=.29)
    styles=[(P.ACCENT,'-'),(P.INK,'--'),(P.MID,'-'),(P.DARK,':')]
    rows=[];check={}
    for co,(col,ls) in zip(ref['rates'],styles):
        pol=co['pollutant'];c0,c1,c2,c3=[co[k] for k in ['c0','c1','c2','c3']]
        rate=lambda z:c0+c1*z+c2*z*z+c3*z*z*z
        gamma=lambda z:c0-c2*vf*z-c3*vf*z*(vf+z)
        label={'CO2':r'CO$_2$','NOx':r'NO$_x$'}.get(pol,pol)
        # Direct formula verifies cubic simplification except the removable limit.
        direct=(vf*rate(v[:-1])-v[:-1]*rate(vf))/(vf-v[:-1])
        assert np.allclose(direct,gamma(v[:-1]),rtol=1e-9,atol=1e-8)
        assert np.isclose(gamma(vf),rate(vf)-vf*(c1+2*c2*vf+3*c3*vf**2))
        axes[0].plot(v,gamma(v)/rate(vf),color=col,ls=ls,lw=1.5,label=label)
        axes[1].plot(x,gamma(vqx(x))/rate(vf),color=col,ls=ls,lw=1.5,label=label)
        for z,y in zip(v,gamma(v)):rows.append({'panel':'speed','pollutant':pol,'vq_mph':z,'x_h':np.nan,'Gamma_g_vehicle_h':y,'Gamma_over_rf':y/rate(vf)})
        for xx,z,y in zip(x,vqx(x),gamma(vqx(x))):rows.append({'panel':'demand','pollutant':pol,'vq_mph':z,'x_h':xx,'Gamma_g_vehicle_h':y,'Gamma_over_rf':y/rate(vf)})
        check[pol]={'rf_g_vehicle_h':rate(vf),'Gamma_free_flow_limit':gamma(vf),'x_curve_range':[float(gamma(vqx(x)).min()),float(gamma(vqx(x)).max())]}
    for ax in axes:
        ax.axhline(0,color=P.LIGHT,lw=.8,zorder=0);clean(ax)
        ax.set_ylabel(r'Normalized delay-emission factor $\Gamma/r(v_f)$')
    axes[0].set(xlim=(5,vf),ylim=(-.85,.65),xlabel=r'Queue speed $v_q$ (mph)')
    axes[1].set(xlim=(low,hi),ylim=(-.35,.55),xlabel=r'Capacity-equivalent demand $x=D/C$ (h)')
    axes[0].set_title('(a) Queue-speed dependence',loc='left');axes[1].set_title('(b) Demand dependence',loc='left')
    h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='lower center',bbox_to_anchor=(.54,.018),ncol=4,columnspacing=2.3)
    layout=save(fig,'fig_gamma_behavior');pd.DataFrame(rows).to_csv(OUT/'fig_gamma_behavior_values.csv',index=False)
    return {'parameters':ref,'normalization':'Gamma/r(vf), independently for each pollutant; positive constant preserves all signs',
        'speed_panel_domain_mph':[5,vf],'speed_panel_is_coefficient_function_not_episode_admissibility':True,
        'demand_panel_domain_h':[low,hi],'source_calibration_x_range_h':[low,source_hi],
        'upper_domain_reason':'Peak finite-link delay equality fp P^s = vf/vq - 1; no extrapolation beyond observed calibration demand range',
        'fixed_state_between_all_points':True,'cubic_identity_and_vf_limit_verified':True,'pollutants':check,'layout':layout}

if __name__=='__main__':
    report={'figure2':fig2(),'gamma':gamma_behavior()}
    inputs = list(DATA.glob('*.csv')) + [CALIBRATION/'cubic_rate_coefficients.csv', CALIBRATION/'audit/table3_reference_state.json'] + list((CALIBRATION/'emission_input').glob('*.csv'))
    report['input_sha256']={p.relative_to(FROZEN).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    (QA/'figure_generation_checks.json').write_text(json.dumps(report,indent=2))
    print('Current manuscript figures and checks written to',OUT)
