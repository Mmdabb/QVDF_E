"""Recompute the workbook example and create editable vector figure sources.

No paper experiment is rerun or changed. All plotted data are exported alongside
the figures. Run with Python 3, NumPy and pandas; outputs go to debug/output/sensor78.
"""
from pathlib import Path
import json, math, hashlib, shutil
import numpy as np
import pandas as pd

from debug_support import locations, load_inputs
HERE, ROOT, DEST = locations()
raw, cfg, expected = load_inputs(ROOT)
DEST.mkdir(parents=True, exist_ok=True)
source = pd.DataFrame(raw['raw_rows'], columns=raw['raw_columns'])
source['dt'] = pd.to_datetime(source['date']+' '+source['clock_time'])
source['valid'] = (source.dt.dt.weekday < 5) & source.speed_mph.between(0,90,inclusive='right') & source.volume_veh_5min.ge(0)
days = source.groupby('date').agg(n=('dt','size'), unique=('dt','nunique'), valid=('valid','all'))
retained = days.index[(days.n==288)&(days.unique==288)&days.valid]
source = source[source.date.isin(retained)].copy()
source['volume_over_speed'] = source.volume_veh_5min/source.speed_mph
profile = source.groupby('clock_time').agg(d=('volume_veh_5min','mean'), sum_d=('volume_veh_5min','sum'), sum_dv=('volume_over_speed','sum')).reset_index()
profile['v'] = profile.sum_d/profile.sum_dv
profile['clock_h'] = profile.clock_time.map(lambda s: sum(float(z)*k for z,k in zip(s.split(':'),[1,1/60,1/3600])))
refprofile = pd.DataFrame(expected['profile_rows'])
assert len(retained)==16 and np.allclose(profile.v,refprofile.speed_mph,rtol=1e-12)
assert np.allclose(profile.d,refprofile.volume_veh_5min,rtol=1e-12)
z = profile[profile.clock_h.ge(14.75)&profile.clock_h.lt(19.5)].copy()
assert len(z)==57
card=cfg['tracks']['average_weekday']['sensor_card']; par=cfg['tracks']['average_weekday']['calibration_by_period'][0]
D=z.d.sum(); L=card['L_mi']; vf=card['vf_mph']; C=card['C_vphpl']; Tf=L/vf
x=D/C; P=max(par['fd']*x**par['n'],x); peak=Tf*par['fp']*P**par['s']; mean=par['theta']*peak
mu=D/P; omega=C/(220-C/vf); vq=mu/(220-mu/omega)
Tq=vf*mean/(vf-vq); Tfree=Tf-vq*mean/(vf-vq)
z['H']=z.d*L/z.v; H=z.H.sum(); Hp=D*(Tf+mean); vm=D*L/H
rates={r['OpModeID']:r for r in expected['lookup_rates']}
coeff={r['pollutant']:np.array([r[f'c{i}'] for i in range(4)]) for r in cfg['cubic_coefficients']}
def mode(v):
    v=float(v); ms=v*.44704; veh=cfg['vehicle']
    vsp=(veh['rolling_term_a']*ms+veh['rotating_term_b']*ms**2+veh['drag_term_c']*ms**3)/veh['source_mass']
    if v<=0:return 1
    pairs=[(0,11),(3,12),(6,13),(9,14),(12,15)] if v<25 else ([(0,21),(3,22),(6,23),(9,24),(12,25),(18,27),(24,28),(30,29)] if v<50 else [(6,33),(12,35),(18,37),(24,38),(30,39)])
    for threshold,m in pairs:
        if vsp<threshold:return m
    return 16 if v<25 else 30 if v<50 else 40
def rate(v,p):
    a=np.asarray(v,dtype=float)
    return np.array([rates[mode(k)][p] for k in a.ravel()]).reshape(a.shape)
def cubic(v,p):return np.polynomial.polynomial.polyval(np.asarray(v),coeff[p])
lo,hi=1.,10000.
for _ in range(60):
    a=(lo+hi)/2; area=math.exp(a*math.log(4)+2*math.lgamma(a+1)-math.lgamma(2*a+2))
    if area>par['theta']:lo=a
    else:hi=a
a=(lo+hi)/2
def shape(u):
    u=np.asarray(u)
    h=(4*u*(1-u))**a
    dh=4*a*(1-2*u)*(4*u*(1-u))**(a-1)
    return h,dh
quad=pd.DataFrame(cfg['gauss_legendre_384']); uq=quad.u.to_numpy(); h,dh=shape(uq)
N=D*quad.weight.to_numpy()*(1+peak/P*dh); T=Tf+peak*h; vr=L/T
assert abs(N.sum()/D-1)<1e-12 and abs(np.sum(N*T)/Hp-1)<1e-12
grid=np.linspace(0,1,1001); hg,dhg=shape(grid); vg=L/(Tf+peak*hg)
rec=pd.DataFrame({'entry_elapsed_h':grid*P,'speed_mph':vg,'lambda_veh_h_lane':mu*(1+peak/P*dhg)})
qdata=pd.DataFrame({'u':uq,'entry_elapsed_h':uq*P,'vehicle_weight':N,'trip_time_h':T,'speed_mph':vr})
trip_duration=(Tf+mean)*60; free_half=Tfree*60/2
trip_t=np.array([0,free_half,free_half,free_half+Tq*60,free_half+Tq*60,trip_duration])
trip_v=np.array([vf,vf,vq,vq,vf,vf])
trip=pd.DataFrame({'elapsed_trip_min':trip_t,'speed_M_A_mph':trip_v})
summary=[]
for p in ['CO2','NOx','CO','HC']:
    ro=rate(z.v,p); rq=rate(vr,p)
    z[f'rate_{p}_g_h']=ro;z[f'O_{p}_g']=z.H*ro
    rec[f'rate_{p}_g_h']=rate(vg,p)
    qdata[f'R_{p}_g']=N*T*rq
    # A within-episode extension of the same mean two-speed calculation:
    # assign each R group its own delay, preserving the aggregate M/A totals.
    group_Tq=vf*peak*h/(vf-vq);group_Tfree=Tf-vq*peak*h/(vf-vq)
    qdata[f'M_{p}_g']=N*(group_Tfree*rate(vf,p)+group_Tq*rate(vq,p))
    qdata[f'A_{p}_g']=N*(group_Tfree*cubic(vf,p)+group_Tq*cubic(vq,p))
    trip[f'M_rate_{p}_g_h']=rate(trip_v,p);trip[f'A_rate_{p}_g_h']=cubic(trip_v,p)
    vals={'O':float(np.sum(z.H*ro)),'S':float(H*rate(vm,p)),'R':float(np.sum(N*T*rq)),
          'M':float(D*(Tfree*rate(vf,p)+Tq*rate(vq,p))),
          'A':float(D*(Tfree*cubic(vf,p)+Tq*cubic(vq,p)))}
    keys={'O':'E_bin_g','S':'E_avg_g','R':'E_rec_g','M':'E_2s_g','A':'E_2s_cubic_g'}
    for m,v in vals.items():
        assert math.isclose(v,expected['emissions'][p][keys[m]],rel_tol=1e-10),(p,m,v)
        if m in ['M','A']:assert math.isclose(qdata[f'{m}_{p}_g'].sum(),v,rel_tol=1e-10)
        summary.append({'method':m,'pollutant':p,'emission_g':v,'signed_error_pct':100*(v/vals['O']-1),'absolute_error_pct':100*abs(v/vals['O']-1)})
summary=pd.DataFrame(summary)
z.to_csv(DEST/'observed_episode_profile.csv',index=False)
rec.to_csv(DEST/'reconstructed_entry_profile.csv',index=False)
qdata.to_csv(DEST/'reconstructed_integration.csv',index=False)
trip.to_csv(DEST/'two_speed_trip_profile.csv',index=False)
summary.to_csv(DEST/'emission_totals.csv',index=False)
pd.DataFrame({'clock_h':profile.clock_h,'speed_mph':profile.v,'count_veh_5min':profile.d}).to_csv(DEST/'average_weekday_profile.csv',index=False)
state={'sensor':78,'retained_days':list(retained),'bins':57,'start_h':14.75,'end_h':19.5,'D':D,'L':L,'C':C,'vf':vf,'Tf_h':Tf,'x_h':x,'P_obs_h':4.75,'P_pred_h':P,'peak_h':peak,'mean_delay_h':mean,'mu':mu,'vq':vq,'Tfree_h':Tfree,'Tq_h':Tq,'H_obs':H,'H_pred':Hp,'v_mean':vm,'shape_a':a,'pred_mean_speed':D*L/Hp,'rates':expected['emissions']}
(DEST/'calculation_inputs_and_state.json').write_text(json.dumps(state,indent=2))

# TikZ curves are vector objects, with common axes, palette and background.
COL={'O':'methodO','S':'methodS','R':'methodR','M':'methodM','A':'methodA'}
def line_coords(x,y):return ' '.join(f'({xx:.3f},{yy:.3f})' for xx,yy in zip(x,y))
def axis(X,Y,W,H,xlim,ylim,xticks,yticks,title,xlabel,ylabel,series,marks=None):
    left=X+40;bottom=Y+29;pw=W-51;ph=H-58
    tx=lambda v:left+(np.asarray(v)-xlim[0])/(xlim[1]-xlim[0])*pw
    ty=lambda v:bottom+(np.asarray(v)-ylim[0])/(ylim[1]-ylim[0])*ph
    out=[f'\\node[anchor=west,font=\\small\\bfseries,text=navy] at ({X+5},{Y+H-9}) {{{title}}};']
    for value,label in yticks:
        yy=float(ty(value));out += [f'\\draw[rulegray,line width=.25pt] ({left},{yy:.3f}) -- ({left+pw},{yy:.3f});',f'\\node[anchor=east,font=\\scriptsize] at ({left-4},{yy:.3f}) {{{label}}};']
    for value,label in xticks:
        xx=float(tx(value));out += [f'\\draw[black,line width=.35pt] ({xx:.3f},{bottom}) -- ({xx:.3f},{bottom-3});',f'\\node[anchor=north,font=\\scriptsize] at ({xx:.3f},{bottom-4}) {{{label}}};']
    out += [f'\\draw[black,line width=.45pt] ({left},{bottom+ph}) -- ({left},{bottom}) -- ({left+pw},{bottom});',f'\\node[anchor=north,font=\\scriptsize] at ({left+pw/2},{Y+10}) {{{xlabel}}};',f'\\node[rotate=90,font=\\scriptsize] at ({X+7},{bottom+ph/2}) {{{ylabel}}};','\\begin{scope}',f'\\clip ({left},{bottom}) rectangle ({left+pw},{bottom+ph});']
    for xs,ys,color,style in series:
        out.append(f'\\draw[{color},line width=1.05pt,{style}] plot coordinates {{{line_coords(tx(xs),ty(ys))}}};')
    if marks:
        for xx,yy,label,color,anchor in marks:
            xp,yp=float(tx(xx)),float(ty(yy))
            out += [f'\\fill[{color}] ({xp:.3f},{yp:.3f}) circle (2pt);',f'\\node[anchor={anchor},font=\\scriptsize,text={color},fill=white,inner sep=1pt] at ({xp:.3f},{yp+5:.3f}) {{{label}}};']
    out+=['\\end{scope}']
    return '\n'.join(out)
def step(x,y,end):
    x=np.asarray(x);y=np.asarray(y);return np.repeat(np.r_[x,end],2)[1:-1],np.repeat(y,2)
def tikz(body,w,h):return '\\begin{tikzpicture}[x=1pt,y=1pt]\n'+f'\\useasboundingbox (0,0) rectangle ({w},{h});\n'+'\n'.join(body)+'\n\\end{tikzpicture}\n'
W=250;Hpanel=174;body=[]
xo,yo=step(z.clock_h,z.v,19.5);xr,yr=step(z.clock_h,z.rate_CO2_g_h/1000,19.5)
xtclock=[(15,'15:00'),(16,'16:00'),(17,'17:00'),(18,'18:00'),(19,'19:00')]
ytv=[(v,str(v)) for v in [0,20,40,60]];ytr=[(v,str(v)) for v in [0,5,10,15,20]]
body.append(axis(0,366,W,Hpanel,(14.75,19.5),(0,70),xtclock,ytv,'(a) O and S: detector-clock speeds','Clock time','Speed (mph)',[(xo,yo,COL['O'],''),([14.75,19.5],[vm,vm],COL['S'],'dashed')]))
body.append(axis(259,366,W,Hpanel,(14.75,19.5),(0,22),xtclock,ytr,'(b) O and S: rates at these speeds','Clock time','CO$_2$ rate (kg/veh h)',[(xr,yr,COL['O'],''),([14.75,19.5],[float(rate(vm,'CO2'))/1000]*2,COL['S'],'dashed')]))
xtentry=[(v,str(v)) for v in [0,1,2,3,4]]
body.append(axis(0,183,W,Hpanel,(0,P),(0,70),xtentry,ytv,'(c) R: trip-average speed by entry','Elapsed entry time (h)','Speed (mph)',[(rec.entry_elapsed_h,rec.speed_mph,COL['R'],'')]))
body.append(axis(259,183,W,Hpanel,(0,P),(0,22),xtentry,ytr,'(d) R: rate at each trip-average speed','Elapsed entry time (h)','CO$_2$ rate (kg/veh h)',[(rec.entry_elapsed_h,rec.rate_CO2_g_h/1000,COL['R'],'')]))
xttrip=[(v,f'{v:g}') for v in [0,.5,1,1.5,2,2.5]]
body.append(axis(0,0,W,Hpanel,(0,2.55),(0,70),xttrip,ytv,'(e) M and A: same two operating speeds','Elapsed time within one trip (min)','Speed (mph)',[(trip_t,trip_v,COL['M'],''),(trip_t,trip_v,COL['A'],'dashed')]))
body.append(axis(259,0,W,Hpanel,(0,2.55),(0,22),xttrip,ytr,'(f) M and A: lookup versus cubic rates','Elapsed time within one trip (min)','CO$_2$ rate (kg/veh h)',[(trip_t,trip.M_rate_CO2_g_h/1000,COL['M'],''),(trip_t,trip.A_rate_CO2_g_h/1000,COL['A'],'dashed')]))
(DEST/'speed_rate_profiles.tex').write_text(tikz(body,509,540))

# Rate curves and cumulative totals. Cumulative share is a vehicle-order index,
# not a shared clock or instantaneous on-road emissions process.
vgrid=np.linspace(5,75,1401);curve=pd.DataFrame({'speed_mph':vgrid})
body=[]
for col,p in enumerate(['CO2','NOx']):
    scale=1000 if p=='CO2' else 1
    rr=rate(vgrid,p)/scale;cc=cubic(vgrid,p)/scale
    curve[f'lookup_{p}']=rr;curve[f'cubic_{p}']=cc
    ymax=30 if p=='CO2' else 50
    yt=[(v,str(v)) for v in ([0,10,20,30] if p=='CO2' else [0,10,20,30,40,50])]
    marks=[(vq,float(rate(vq,p))/scale,'$v_q$',COL['M'],'south east'),(vm,float(rate(vm,p))/scale,'$\\bar v$',COL['S'],'south west'),(vf,float(rate(vf,p))/scale,'$v_f$',COL['M'],'south')]
    body.append(axis(col*259,275,W,210,(5,75),(0,ymax),[(v,str(v)) for v in [10,25,40,55,70]],yt,f'({"a" if col==0 else "b"}) {"CO$_2$" if col==0 else "NO$_x$"}: speed-to-rate mapping','Speed (mph)','Rate ('+('kg' if p=='CO2' else 'g')+'/veh h)',[(vgrid,rr,COL['O'],''),(vgrid,cc,COL['A'],'dashed')],marks))
    cxo=np.r_[0,np.cumsum(z.d)/D];cyo=np.r_[0,np.cumsum(z[f'O_{p}_g'])]/1000
    cxr=np.r_[0,np.cumsum(N)/D];cyr=np.r_[0,np.cumsum(qdata[f'R_{p}_g'])]/1000
    # kg for CO2; grams for NOx.
    if p=='NOx':cyo*=1000;cyr*=1000
    outputs=summary[summary.pollutant.eq(p)].set_index('method').emission_g
    scale=1000 if p=='CO2' else 1
    sy=[(cxo,cyo,COL['O'],''),(cxr,cyr,COL['R'],'')]
    sy.append(([0,1],[0,outputs['S']/scale],COL['S'],'dashed'))
    for m in ['M','A']:
        cym=np.r_[0,np.cumsum(qdata[f'{m}_{p}_g'])]/scale
        sy.append((cxr,cym,COL[m],'dashed' if m=='A' else ''))
        assert math.isclose(cym[-1],outputs[m]/scale,rel_tol=1e-10)
        pd.DataFrame({'vehicle_share':cxr,f'{m}_emission_g':cym*scale}).to_csv(DEST/f'cumulative_{m}_{p}.csv',index=False)
    ymax=2200;yt=[(v,f'{v:,}') for v in [0,500,1000,1500,2000]]
    body.append(axis(col*259,0,W,235,(0,1),(0,ymax),[(v,f'{int(v*100)}') for v in [0,.25,.5,.75,1]],yt,f'({"c" if col==0 else "d"}) {"CO$_2$" if col==0 else "NO$_x$"}: cumulative contribution','Cumulative counted-vehicle share (\\%)','Cumulative emission ('+('kg' if p=='CO2' else 'g')+'/lane)',sy))
    # Every plotted cumulative endpoint must equal its method's verified total.
    assert math.isclose(cyo[-1],outputs['O']/scale,rel_tol=1e-12)
    assert math.isclose(cyr[-1],outputs['R']/scale,rel_tol=1e-12)
    pd.DataFrame({'vehicle_share':cxo,'O_emission_g':np.r_[0,np.cumsum(z[f'O_{p}_g'])]}).to_csv(DEST/f'cumulative_O_{p}.csv',index=False)
    pd.DataFrame({'vehicle_share':cxr,'R_emission_g':np.r_[0,np.cumsum(qdata[f'R_{p}_g'])]}).to_csv(DEST/f'cumulative_R_{p}.csv',index=False)
curve.to_csv(DEST/'rate_curves.csv',index=False)
(DEST/'rate_and_cumulative_profiles.tex').write_text(tikz(body,509,485))

def fmt(v,n=3):return f'{float(v):,.{n}f}'
co=summary[summary.pollutant.eq('CO2')].set_index('method')
names={'O':'Recorded speeds','S':'Episode mean speed','R':'Reconstructed speeds','M':'Two-speed lookup','A':'Two-speed cubic'}
rows=[]
for m in ['O','S','R','M','A']:
    g=summary[summary.method.eq(m)].set_index('pollutant')
    err='Reference' if m=='O' else f'{g.loc["CO2","signed_error_pct"]:+.2f}'
    rows.append(f'{m}: {names[m]} & {fmt(g.loc["CO2","emission_g"]/1000,2)} & {fmt(g.loc["NOx","emission_g"],2)} & {fmt(g.loc["CO","emission_g"],2)} & {fmt(g.loc["HC","emission_g"],2)} & {err} \\\\')
numeric=r'''
\newpage
\fontsize{10}{12}\selectfont
{\fontsize{19}{22}\selectfont\bfseries\color{navy}Detector 78: worked link example}\par
{\color{muted}Arizona I-10 westbound, January 2016 average weekday.}

\notebox{\textbf{Scope.} This is the standalone workbook example from the supplied sensor-78 data:
16 complete weekdays, 57 bins from 14:45 inclusive to 19:30 exclusive. The window is fixed for explanation,
not newly detected. These inputs differ from the archived paper sample; the case is not one of the
137 observations summarized on page 2. Supplied counts are assumed already per lane (multiplier 1).}

\vspace{7pt}\textbf{Inputs and fitted traffic quantities}\par
\renewcommand{\arraystretch}{1.35}\setlength{\tabcolsep}{6pt}
\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lrlr@{}}\toprule
Input & Value & Calculated quantity & Value\\\midrule
Link length $L$ & 1.040 mi & Demand $D$ & DVALUE veh/lane\\
Free-flow speed $v_f$ & VFVALUE mph & $D/C$ & XVALUE h\\
Capacity $C$ & CVALUE veh/h/lane & Predicted duration $\widehat P$ & PVALUE h\\
Jam density $k_j$ & 220 veh/mi/lane & Queue speed $\widehat v_q$ & VQVALUE mph\\
Observed duration & 4.750 h & Predicted mean delay & MEANVALUE min\\
Observed vehicle-hours & HOVALUE veh h/lane & Predicted vehicle-hours & HPVALUE veh h/lane\\
Observed mean speed & VMVALUE mph & Predicted mean trip speed & VPVALUE mph\\\bottomrule
\end{tabular*}
\par\smallskip
{\small Calibration: $f_d=1.693177$, $n=0.833031$, $f_p=0.308070$, $s=1.635098$, $\theta=0.434829$ (PM).
The reconstructed shape exponent is $a=AVALUE$.}

\vspace{9pt}\textbf{How the CO$_2$ totals are obtained}
\begin{align*}
E_O &= \sum_{i=1}^{57}d_i(L/v_i)r_0(v_i)/1000 = OVALUE\ \text{kg/lane},\\
E_S &= HOVALUE\times SRATE /1000 = SVALUE\ \text{kg/lane},\\
E_R &= \sum_{j=1}^{384}N_j[T_f+w(u_j)]r_0(v_R(u_j))/1000
      = RVALUE\ \text{kg/lane},\\
E_M &= DVALUE[TFREE\times FRATE+TQUEUE\times QRATE]/1000
      = MVALUE\ \text{kg/lane},\\
E_A &= DVALUE[TFREE\times FCRATE+TQUEUE\times QCRATE]/1000
      = AVALUEEM\ \text{kg/lane}.
\end{align*}
The numerical rates are in g/(veh h), times in hours; dividing by 1,000 converts grams to kg.
For O the displayed result is converted to kg after summation. For R, $N_j$ are quadrature vehicle weights.
Unrounded values are used in the calculations; the substitutions above are rounded.

\notebox{\textbf{The speed/rate distinction in this case.}
The observed mean speed is VMVALUE mph and the inferred queue speed is VQVALUE mph;
both select the same CO$_2$ lookup rate, SRATE g/(veh h).
Free-flow speed selects FRATE g/(veh h).
M assigns FREEPCT\% of its vehicle-hours to free flow, which contributes FREEEM\% of its CO$_2$ total.
Its mean trip consists of FREEMIN min at free flow and QUEUEMIN min at queue speed.}

\vspace{8pt}\textbf{Episode emission totals and CO$_2$ discrepancy}\par
\renewcommand{\arraystretch}{1.4}\setlength{\tabcolsep}{4pt}
\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lrrrrr@{}}\toprule
Calculation & CO$_2$ (kg) & NO$_x$ (g) & CO (g) & HC (g) & CO$_2$ error (\%)\\\midrule
TABLEROWS
\bottomrule\end{tabular*}
\par\smallskip{\small Totals are per lane. Signed error is $100(E_m/E_O-1)$;
its absolute value is the one-episode WAPE. R has the smallest CO$_2$ discrepancy here.
M's absolute discrepancy (14.01\%) is smaller than S's (15.95\%), unlike the pooled ordering on page 2.}
\vfill
{\small\color{muted}Source: Sensor78\_Emission\_Calculations.xlsx and its embedded January input profile and calibrated parameters.
Recorded source travel times are not used: link times are recalculated as $L/v$. All emissions use passenger-car rates with zero acceleration and level road.}
'''
vals={'DVALUE':fmt(D,2),'VFVALUE':fmt(vf,3),'XVALUE':fmt(x,3),'CVALUE':fmt(C,3),'PVALUE':fmt(P,3),'VQVALUE':fmt(vq,3),'MEANVALUE':fmt(mean*60,3),'HOVALUE':fmt(H,3),'HPVALUE':fmt(Hp,3),'VMVALUE':fmt(vm,3),'VPVALUE':fmt(D*L/Hp,3),'AVALUE':fmt(a,6),'SRATE':fmt(rate(vm,'CO2'),3),'TFREE':fmt(Tfree,8),'TQUEUE':fmt(Tq,8),'FRATE':fmt(rate(vf,'CO2'),3),'QRATE':fmt(rate(vq,'CO2'),3),'FCRATE':fmt(cubic(vf,'CO2'),3),'QCRATE':fmt(cubic(vq,'CO2'),3),'FREEPCT':fmt(100*Tfree/(Tfree+Tq),1),'FREEEM':fmt(100*Tfree*rate(vf,'CO2')/(Tfree*rate(vf,'CO2')+Tq*rate(vq,'CO2')),1),'FREEMIN':fmt(Tfree*60,3),'QUEUEMIN':fmt(Tq*60,3),'TABLEROWS':'\n'.join(rows)}
for m,k in [('O','OVALUE'),('S','SVALUE'),('R','RVALUE'),('M','MVALUE'),('A','AVALUEEM')]:vals[k]=fmt(co.loc[m,'emission_g']/1000,2)
for k in sorted(vals,key=len,reverse=True):numeric=numeric.replace(k,vals[k])
(DEST/'worked_calculations.tex').write_text(numeric)

figpages=r'''
\newpage
{\fontsize{19}{22}\selectfont\bfseries\color{navy}Speed and emission-rate profiles}\par
{\color{muted}Detector 78 worked example. The three rows have different time meanings.}\par
\vspace{5pt}
\legendkey{methodO}{O: recorded}\quad\legendkey{methodS}{S: mean speed}\quad\legendkey{methodR}{R: reconstructed}\quad\legendkey{methodM}{M: two-speed}\quad\legendkey{methodA}{A: cubic}
\par\vspace{8pt}\begin{center}\resizebox{\linewidth}{!}{\input{detector78/speed_rate_profiles.tex}}\end{center}
\textbf{How to read the panels.}
(a,b) O uses the recorded five-minute link-speed proxies; S holds their harmonic mean constant.
(c,d) R assigns a whole-link average speed to each entering group over its fitted 4.449 h duration.
This is not a vehicle's within-trip speed history. (e,f) M and A share a 2.469 min mean trip and identical speeds;
only the rate function changes. Free-flow time is split equally before and after the queue for illustration.
This ordering is not identified by the method and does not change its total; instantaneous transitions add no acceleration emissions.

\notebox{\textbf{A rate curve is not an episode emission total.}
O's rate must be weighted by $d_iL/v_i$; R's by each group's count and trip time;
M and A by free/queue time and total demand. The area under (b) or (d) over the displayed horizontal axis
alone is not the episode total. The cumulative contributions on the next page include the required weights.}

\newpage
{\fontsize{19}{22}\selectfont\bfseries\color{navy}From speed choice to emission totals}\par
{\color{muted}Detector 78: lookup sensitivity and correctly weighted cumulative contributions.}\par
\vspace{5pt}
\legendkey{methodO}{O: recorded}\quad\legendkey{methodS}{S: mean speed}\quad\legendkey{methodR}{R: reconstructed}\quad\legendkey{methodM}{M: two-speed}\quad\legendkey{methodA}{A: cubic}
\par\vspace{8pt}\begin{center}\resizebox{\linewidth}{!}{\input{detector78/rate_and_cumulative_profiles.tex}}\end{center}
\textbf{Rate curves (a,b).} Black is the zero-acceleration lookup; orange dashed is its cubic approximation.
Markers identify the queue speed (13.611 mph), observed mean speed (23.557 mph) and free-flow speed (64.161 mph).
The queue and observed mean speeds select the same lookup rate for both pollutants. The free-flow rate is much higher.

\textbf{Cumulative curves (c,d).} The horizontal coordinate is the cumulative share of counted vehicles,
not clock time. O accumulates each bin's complete-link emission in chronological order;
R accumulates reconstructed group emissions in entry order using its vehicle weights.
M and A use the same group delays $w(u)$ to allocate each group's free/queue time; this illustrative
extension preserves their analytical episode totals exactly. S assigns the same emission to every vehicle,
so its cumulative curve is straight.
For O, straight segments within a five-minute group distribute that group's total uniformly over its vehicle share.
Every endpoint equals its episode total on page 3.

\notebox{\textbf{What this example shows.} R is closest to O for CO$_2$ and NO$_x$ in this case.
S does not win every episode. M's higher free-flow rate can offset its lower total vehicle-hours relative to O.
These plots explain the calculations; none supplies independent vehicle trajectories or measured emissions.}
'''
(DEST/'figure_pages.tex').write_text(figpages)

validation={'retained_days':len(retained),'episode_bins':len(z),'all_20_emission_totals_match_workbook':True,'max_profile_speed_difference':float(np.max(abs(profile.v-refprofile.speed_mph))),'source_workbook_sha256':expected['source_sha256'],'observed_vht':H,'predicted_vht':Hp,'plot_axes':'Clock time for O/S; reconstructed entry time for R; within-trip time for M/A; vehicle-share index for cumulative curves','no_full_experiment_rerun':True}
(DEST/'validation.json').write_text(json.dumps(validation,indent=2))
print(json.dumps(validation,indent=2));print(summary.to_string(index=False))
