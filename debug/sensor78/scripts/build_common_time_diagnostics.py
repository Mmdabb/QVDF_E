"""Conservative five-minute attribution and signed emission-error diagnostics."""
from pathlib import Path
import json, math, shutil
import numpy as np
import pandas as pd

from debug_support import locations, load_inputs
HERE, ROOT, OUT = locations()
_, cfg, expected = load_inputs(ROOT)
state=json.loads((OUT/'calculation_inputs_and_state.json').read_text())
z=pd.read_csv(OUT/'observed_episode_profile.csv'); q=pd.read_csv(OUT/'reconstructed_integration.csv')
tot=pd.read_csv(OUT/'emission_totals.csv'); pols=['CO2','NOx','CO','HC']; methods=['O','S','R','M','A']
rate_table={int(r['OpModeID']):r for r in expected['lookup_rates']}
def mode(v):
    s=v*.44704; c=cfg['vehicle']; vsp=(c['rolling_term_a']*s+c['rotating_term_b']*s*s+c['drag_term_c']*s**3)/c['source_mass']
    if v<=0:return 1
    pairs=([(0,11),(3,12),(6,13),(9,14),(12,15)] if v<25 else [(0,21),(3,22),(6,23),(9,24),(12,25),(18,27),(24,28),(30,29)] if v<50 else [(6,33),(12,35),(18,37),(24,38),(30,39)])
    for threshold,m in pairs:
        if vsp<threshold:return m
    return 16 if v<25 else 30 if v<50 else 40
def rate(v,p):return rate_table[mode(float(v))][p]
D=state['D'];L=state['L'];vf=state['vf'];vq=state['vq'];Ho=state['H_obs'];Hp=state['H_pred']
edges=np.r_[0,z.d.cumsum().to_numpy()]; nedge=np.r_[0,q.vehicle_weight.cumsum().to_numpy()]
assert abs(nedge[-1]-D)<1e-8
nedge[-1]=D;edges[-1]=D
def rebin(values):return np.diff(np.interp(edges,nedge,np.r_[0,np.cumsum(values)]))
series=pd.DataFrame({'clock_h':z.clock_h,'clock_time':z.clock_time,'count_veh_5min':z.d,'cum_count_start':edges[:-1],'cum_count_end':edges[1:]})
series['H_O']=z.H;series['H_S']=z.d*Ho/D;series['H_R']=rebin(q.vehicle_weight*q.trip_time_h)
series['H_M']=series.H_R;series['H_A']=series.H_R
w=q.trip_time_h-state['Tf_h'];tq=vf*w/(vf-vq);tf=state['Tf_h']-vq*w/(vf-vq)
series['Tfree_mean_h']=rebin(q.vehicle_weight*tf)/z.d
series['Tqueue_mean_h']=rebin(q.vehicle_weight*tq)/z.d
for m in methods:series[f'v_{m}']=z.d*L/series[f'H_{m}']
assert np.allclose(series.v_R,L/(series.Tfree_mean_h+series.Tqueue_mean_h),rtol=1e-12)
decomp=[]; diag=[]
for p in pols:
    e=tot[tot.pollutant.eq(p)].set_index('method').emission_g.to_dict()
    sp=Hp*rate(D*L/Hp,p)
    vals=[e['O'],e['S'],sp,e['R'],e['M'],e['A']]
    labels=['Observed mean-rate aggregation','Fitted mean delay and speed','Reconstructed trip-speed variation','Two operating-speed allocation','Cubic rate approximation']
    dif=np.diff(vals)
    for k,(label,delta) in enumerate(zip(labels,dif)):
        decomp.append({'pollutant':p,'stage':k+1,'component':label,'from_g':vals[k],'to_g':vals[k+1],'delta_g':delta,'delta_pct_of_O':100*delta/e['O']})
    for m in methods:
        if m=='O':series[f'E_{m}_{p}_g']=z[f'O_{p}_g']
        elif m=='S':series[f'E_{m}_{p}_g']=z.d*e['S']/D
        else:series[f'E_{m}_{p}_g']=rebin(q[f'{m}_{p}_g'])
        series[f'rate_{m}_{p}_g_h']=series[f'E_{m}_{p}_g']/series[f'H_{m}']
        series[f'cum_{m}_{p}_g']=series[f'E_{m}_{p}_g'].cumsum()
        assert math.isclose(series[f'E_{m}_{p}_g'].sum(),e[m],rel_tol=1e-12)
        hm=Ho if m in ['O','S'] else Hp
        diag.append({'pollutant':p,'method':m,'total_g':e[m],'H':hm,'effective_rate':e[m]/hm,'S_pred_g':sp,'signed_error_pct':100*(e[m]/e['O']-1)})
series.to_csv(OUT/'common_time_series.csv',index=False)
pd.DataFrame(decomp).to_csv(OUT/'error_decomposition.csv',index=False)
pd.DataFrame(diag).to_csv(OUT/'method_diagnostics.csv',index=False)
# Sparse node-to-bin overlap is an independent conservation check.
overlap=np.maximum(0,np.minimum(edges[1:,None],nedge[None,1:])-np.maximum(edges[:-1,None],nedge[None,:-1]))
assert np.allclose(overlap.sum(axis=1),z.d,rtol=1e-12)
assert np.allclose(overlap@q.trip_time_h,series.H_R,rtol=1e-12)

# Reuse the vector-axis functions without executing the previous builder.
script=(HERE/'build_detector78_appendix.py').read_text()
start=script.index("COL={'O'");end=script.index('W=250;Hpanel=174')
exec(script[start:end],globals())
styles={'O':'','S':'dashed','R':'line width=2.1pt','M':'line width=1.1pt','A':'dashed,line width=.8pt'}
xt=[(v,f'{v:02d}:00') for v in range(15,20)]
def timeseries(field,scale=1):
    ans=[]
    for m in methods:
        xx,yy=step(series.clock_h,series[field.format(m=m)]/scale,19.5)
        ans.append((xx,yy,COL[m],styles[m]))
    return ans
body=[]
body.append(axis(0,354,509,170,(14.75,19.5),(0,70),xt,[(v,str(v)) for v in [0,20,40,60]],'(a) Equivalent whole-link speed: all five approaches','Detector clock time','Speed (mph)',timeseries('v_{m}')))
body.append(axis(0,177,509,170,(14.75,19.5),(0,22),xt,[(v,str(v)) for v in [0,5,10,15,20]],'(b) Five-minute effective CO$_2$ emission rate','Detector clock time','Rate (kg/veh h)',timeseries('rate_{m}_CO2_g_h',1000)))
body.append(axis(0,0,509,170,(14.75,19.5),(0,55),xt,[(v,str(v)) for v in [0,10,20,30,40,50]],'(c) CO$_2$ assigned to the counted vehicles in each five-minute bin','Detector clock time','Emission (kg/lane/bin)',timeseries('E_{m}_CO2_g',1000)))
(OUT/'common_clock_profiles.tex').write_text(tikz(body,509,524))
body=[]
for row,p in enumerate(['CO2','NOx']):
    scale=1000 if p=='CO2' else 1;Y=260 if row==0 else 0
    for col,axisname in enumerate(['share','clock']):
        lines=[]
        for m in methods:
            if axisname=='share':
                if m=='O':xx=np.r_[0,z.d.cumsum()/D]; yy=np.r_[0,z[f'O_{p}_g'].cumsum()]/scale
                elif m=='S':xx=[0,1];yy=[0,tot[(tot.method==m)&(tot.pollutant==p)].emission_g.iloc[0]/scale]
                else:xx=nedge/D;yy=np.r_[0,q[f'{m}_{p}_g'].cumsum()]/scale
            else:
                xx=np.r_[series.clock_h.to_numpy(),19.5];yy=np.r_[0,series[f'cum_{m}_{p}_g']]/scale
            lines.append((xx,yy,COL[m],styles[m]))
        idx='abcd'[row*2+col];name='CO$_2$' if p=='CO2' else 'NO$_x$'
        body.append(axis(col*259,Y,250,240,(0,1) if axisname=='share' else (14.75,19.5),(0,2200),[(v,str(round(v*100))) for v in [0,.25,.5,.75,1]] if axisname=='share' else xt,[(v,f'{v:,}') for v in [0,500,1000,1500,2000]],f'({idx}) {name}: '+('by vehicle share' if axisname=='share' else 'by clock time'),'Cumulative vehicle share (\\%)' if axisname=='share' else 'Detector clock time','Cumulative '+('kg' if p=='CO2' else 'g')+'/lane',lines))
(OUT/'common_cumulative.tex').write_text(tikz(body,509,500))
dc=pd.DataFrame(decomp);dco=dc[dc.pollutant.eq('CO2')]
rows='\n'.join(f'{r.stage}. {r.component} & {r.delta_g/1000:+,.2f} & {r.delta_pct_of_O:+.2f} \\\\' for r in dco.itertuples())
allrows=[]
for p in pols:
    ds=dc[dc.pollutant.eq(p)];allrows.append(p.replace('CO2','CO$_2$').replace('NOx','NO$_x$')+' & '+' & '.join(f'{v:+.2f}' for v in ds.delta_pct_of_O)+' \\\\')
Sp=diag[0]['S_pred_g']
pages=r'''
\newpage
{\fontsize{18}{21}\selectfont\bfseries\color{navy}All five methods on the same clock}\par
{\color{muted}Detector 78. The modeled groups are aligned to the recorded cumulative vehicle counts.}\par
\legendkey{methodO}{O: recorded}\quad\legendkey{methodS}{S: mean speed}\quad\legendkey{methodR}{R: reconstructed}\quad\legendkey{methodM}{M: two-speed}\quad\legendkey{methodA}{A: cubic}
\begin{center}\resizebox{\linewidth}{!}{\input{detector78/common_clock_profiles.tex}}\end{center}
\textbf{Speed overlap is expected.} R, M and A have identical bin vehicle-hours and distance;
their equivalent speeds coincide. For M/A, $v_i^{eff}=L/(\bar T_{{free},i}+\bar T_{q,i})$.
The colors distinguish emission calculations, not three different equivalent-speed predictions.
\notebox{For every method, $v_i^{eff}=d_iL/H_i$, $r_i^{eff}=E_i/H_i$ and $E_i=H_i r_i^{eff}$.
R's effective rate is the time-weighted rate of its reconstructed groups, not the lookup at its bin-average speed.
The displayed emissions are complete-link emissions assigned to vehicles counted in each bin;
they are not emissions physically released during that clock interval. The alignment preserves all previous totals.}

\newpage
{\fontsize{18}{21}\selectfont\bfseries\color{navy}Cumulative emissions: vehicle share and time}\par
{\color{muted}The left panels retain the vehicle-order view; the right panels use the common five-minute clock.}\par
\legendkey{methodO}{O: recorded}\quad\legendkey{methodS}{S: mean speed}\quad\legendkey{methodR}{R: reconstructed}\quad\legendkey{methodM}{M: two-speed}\quad\legendkey{methodA}{A: cubic}
\begin{center}\resizebox{\linewidth}{!}{\input{detector78/common_cumulative.tex}}\end{center}
\textbf{Left: cumulative counted-vehicle share.} O follows observed bin order. R, M and A follow modeled group order.
S uses a constant emission per vehicle. The same reconstructed group delays supply M/A's free/queue allocation.
\textbf{Right: detector clock time.} Each boundary is the sum of all preceding five-minute emission contributions.
Within-bin lines interpolate the bin contribution for display; no sub-bin release timing is inferred.
Every endpoint equals the corresponding total on page 3.
\notebox{\textbf{Alignment rule.} Split each positive quadrature vehicle weight across observed bins in cumulative-count order.
For node $j$ and bin $i$, the overlap count is
\[
n_{ij}=\max\{0,\min(B_i,N_j)-\max(B_{i-1},N_{j-1})\},
\]
where $B_i$ and $N_j$ are cumulative observed-bin and modeled-node counts.
Use $H_i=\sum_j n_{ij}T_j$ and $E_i=\sum_j n_{ij}e_j$.
Thus all five methods use exactly the same bin count $d_i$ while keeping their original episode totals.
This is a transparent display attribution, not an independently reconstructed queue clock.}

\newpage
{\fontsize{18}{21}\selectfont\bfseries\color{navy}Where the emission differences enter}\par
{\color{muted}An exact signed decomposition for detector 78, conditional on the stated sequence.}
\vspace{8pt}
Define a single-speed calculation using the same fitted mean travel time as R/M/A:
\[
E_{S,pred}=H_{pred}r_0(DL/H_{pred}).
\]
Here $H_{obs}=211.434$ and $H_{pred}=197.040$ veh h/lane, a $-6.81$\% change.
Mean trip time changes from 2.649 to 2.469 min and mean speed from 23.557 to 25.278 mph.
The latter crosses a lookup-rate boundary; the fitted-mean CO$_2$ total is SPVALUE kg/lane.
For step 2, an exact symmetric split is
\[
\Delta E_H=(H_p-H_o)(r_p+r_o)/2,\qquad
\Delta E_r=(r_p-r_o)(H_p+H_o)/2.
\]
Here $r_o=r_0(DL/H_o)$ and $r_p=r_0(DL/H_p)$.
For CO$_2$, the vehicle-hours term is $-106.42$ kg and the mean-speed/rate term is $+188.43$ kg,
giving a net $+82.01$ kg. These are mathematical components of the fitted-mean comparison.

\vspace{8pt}\textbf{Sequential CO$_2$ contributions}\par
\renewcommand{\arraystretch}{1.45}\setlength{\tabcolsep}{6pt}
\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lrr@{}}\toprule
Change & CO$_2$ difference (kg/lane) & \% of O\\\midrule
DECOMPROWS
\bottomrule\end{tabular*}

\vspace{8pt}\textbf{What each step measures}
\begin{enumerate}\setlength{\itemsep}{3pt}
\item $E_S-E_O$: replace the recorded speed distribution with one observed mean speed, keeping observed vehicle-hours.
\item $E_{S,pred}-E_S$: change to fitted mean delay and its implied mean speed, using the same one-speed rule.
This combines the exposure change and the induced lookup-rate change.
\item $E_R-E_{S,pred}$: introduce reconstructed variation among whole-link trip speeds at the same fitted vehicle-hours.
\item $E_M-E_R$: replace each group's whole-trip speed with free/queue operating speeds, preserving time and distance.
\item $E_A-E_M$: replace the two lookup rates with cubic rates; time allocation is unchanged.
\end{enumerate}

\notebox{\textbf{Which terms belong to each result?}
S uses step 1. R uses steps 1--3. M uses steps 1--4. A uses steps 1--5.
Their signed sums equal $E_m-E_O$ exactly. For example,
\[
E_M-E_O=(E_S-E_O)+(E_{S,pred}-E_S)+(E_R-E_{S,pred})+(E_M-E_R).
\]
Positive and negative components can cancel. Absolute errors or WAPE values do not add this way.
This decomposition is order-dependent accounting, not proof of independent causal effects.}

\vspace{9pt}\textbf{Components for all pollutants (percentage points relative to O)}\par
\renewcommand{\arraystretch}{1.4}
\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lrrrrr@{}}\toprule
Pollutant & Step 1 & Step 2 & Step 3 & Step 4 & Step 5\\\midrule
ALLROWS
\bottomrule\end{tabular*}
\par\smallskip
\textbf{Interpretation.} A lower total error can result from cancellation between calibration and emission-representation errors.
The current reference itself assumes constant-speed whole-link trips; these components explain discrepancies relative to that reference,
not discrepancies from measured tailpipe emissions. The 137-episode analysis will assess these patterns across episodes separately.
'''
pages=pages.replace('DECOMPROWS',rows).replace('ALLROWS','\n'.join(allrows)).replace('SPVALUE',f'{Sp/1000:,.2f}')
(OUT/'common_time_pages.tex').write_text(pages)
(OUT/'common_time_validation.json').write_text(json.dumps({'bins':57,'all_20_totals_preserved':True,'same_bin_counts':True,'shared_R_M_A_speed':True,'max_bin_count_error':float(np.max(abs(overlap.sum(axis=1)-z.d))),'H_error_pct':100*(Hp/Ho-1)},indent=2))
print(dc.to_string(index=False));print('Wrote common-clock data and PDF pages.')
