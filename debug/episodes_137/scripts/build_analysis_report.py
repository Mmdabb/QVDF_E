"""Typeset the retained-episode audit; omit the withdrawn average-error table."""
from pathlib import Path
import json,subprocess,shutil
import numpy as np
import pandas as pd
from pypdf import PdfReader
from _paths import ROOT, REFERENCE, arguments
args=arguments(__doc__, report=True)
OUT=args.results.resolve();SUP=REFERENCE/'reports/source'
REPORTS=args.output/'reports';REPORTS.mkdir(parents=True,exist_ok=True)
TMP=args.output/'build';TMP.mkdir(parents=True,exist_ok=True)
summary=json.loads((OUT/'summary.json').read_text())
wide=pd.read_csv(OUT/'episode_calculations_137.csv')
metrics=pd.read_csv(OUT/'comparison_metrics.csv')
traffic=pd.read_csv(OUT/'traffic_error_metrics.csv')
groups=pd.read_csv(OUT/'diagnostic_groups.csv')
cf=pd.read_csv(OUT/'counterfactual_metrics.csv')
pols=['CO2','NOx','CO','HC'];labels={'CO2':r'$\mathrm{CO}_2$','NOx':r'$\mathrm{NO}_x$','CO':r'$\mathrm{CO}$','HC':r'$\mathrm{HC}$'}
def metric(p,m,key='WAPE_pct'):return float(metrics[(metrics.pollutant==p)&(metrics.method==m)&metrics['sample'].eq('All 137')].iloc[0][key])
def cfval(p,m):return float(cf[(cf.pollutant==p)&(cf.method==m)&cf['sample'].eq('mean_admissible_133')].iloc[0].WAPE_pct)
def rows_tex(rows):return '\n'.join(' & '.join(str(x) for x in row)+r' \\' for row in rows)
def tab(spec,heads,rows):
 env='tabularx' if 'X' in spec else 'tabular*'
 begin=(r'\begin{tabularx}{\linewidth}{'+spec+'}') if env=='tabularx' else (r'\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}'+spec+'@{}}')
 return '\n'.join([r'\begin{center}\small',begin,r'\toprule',rows_tex([[r'\textbf{'+x+'}' for x in heads]]),r'\midrule',rows_tex(rows),r'\bottomrule',r'\end{'+env+r'}\end{center}'])
parts={}
parts['WAPE']=tab('lrrrrr',['Pollutant',r'$S$',r'$S_{\mathrm p}$',r'$R$',r'$M$',r'$A$'],[[labels[p]]+[f'{metric(p,m):.2f}' for m in ['S','S_pred','R','M','A']] for p in pols])
parts['COUNTS']=tab('lrrr',['Pollutant',r'$M$ worse than $S$',r'$A$ worse than $S$',r'$M$ worse than $S_{\mathrm p}$'],[[labels[p],str(summary['pollutants'][p]['M_worse_than_S'])+'/137',str(summary['pollutants'][p]['A_worse_than_S'])+'/137',str(summary['pollutants'][p]['M_worse_than_S_pred'])+'/137'] for p in pols])
tr=[]
specs=[('P_h','P_hat_h','Episode duration','Estimated duration is comparatively accurate.'),('wt2_h','wt2_hat_h','Peak delay','Both targets use the same free-flow baseline.'),('wt2_h','conditional_peak_delay_h','Peak delay with observed duration','Replacing predicted duration changes little.'),('wbar_h','wbar_hat_h','Mean delay per episode','Scores the per-vehicle mean-delay targets.'),('total_vehicle_delay_observed_veh_h','total_vehicle_delay_predicted_veh_h','Total vehicle delay','Multiplies mean delay by the episode count.'),('H_observed_veh_h','H_predicted_veh_h','Total vehicle-hours',r'Includes free-flow time; total bias is $-1.85\%$.')]
for ob,pr,label,meaning in specs:tr.append([label,f'{traffic[(traffic.observed==ob)&(traffic.predicted==pr)].iloc[0].WAPE_pct:.2f}',meaning])
parts['TRAFFIC']=tab(r'>{\raggedright\arraybackslash}p{4.8cm}rX',['Traffic quantity',r'WAPE (\%)','Interpretation'],tr)
parts['CF']=tab('lrr',['Pollutant',r'Original $M$ WAPE (\%)',r'Corrected $M$ WAPE (\%)'],[[labels[p],f'{cfval(p,"M"):.2f}',f'{cfval(p,"M_observed_delay"):.2f}'] for p in pols])
steps=['observed_mean_rate','fitted_mean_delay_speed','reconstructed_speed_distribution','two_speed_allocation','cubic_rates']
names=[r'Observed mean-rate aggregation: $E_S-E_O$',r'Fitted mean time and speed: $E_{\Sp}-E_S$',r'Reconstructed speed variation: $E_R-E_{\Sp}$',r'Two-speed allocation: $E_M-E_R$',r'Cubic rate approximation: $E_A-E_M$']
rows=[[name]+[f"{summary['pollutants'][p]['sum_signed_components_pct_O'][step]:+.2f}" for p in pols] for name,step in zip(names,steps)]
rows.append([r'Sum: total bias of $A$']+[f'{metric(p,"A","bias_pct"):+.2f}' for p in pols])
parts['STEPS']=tab('Xrrrr',['Signed contribution (pp)']+[labels[p] for p in pols],rows)
parts['PRODUCT']=tab('Xrrrr',['Signed contribution (pp)']+[labels[p] for p in pols],[[r'Vehicle-hours component']+[f"{summary['pollutants'][p]['M_VHT_component_pct_O']:+.2f}" for p in pols],[r'Effective-rate component']+[f"{summary['pollutants'][p]['M_effective_rate_component_pct_O']:+.2f}" for p in pols]])
rows=[]
for flag,value,label in [('flag_flat_profile_cv_le_010',True,r'Flat recorded speeds: CV $\leq0.10$'),('flag_flat_profile_cv_le_010',False,r'More variable speeds: CV $>0.10$'),('flag_short_duration_le_1h',True,r'Short episodes: $P\leq1$ h'),('flag_short_duration_le_1h',False,r'Longer episodes: $P>1$ h')]:
 r=groups[(groups.pollutant=='CO2')&(groups.criterion==flag)&groups.flag_value.eq(value)].iloc[0];rows.append([label,str(int(r.N)),f'{int(r.M_worse_than_S_count)}/{int(r.N)}',f'{r.S_WAPE_pct:.2f} / {r.M_WAPE_pct:.2f}'])
parts['PROFILES']=tab('Xrrr',['Condition','$N$',r'$M$ worse than $S$',r'$S$ / $M$ WAPE (\%)'],rows)
e=wide[wide.sensor_uid.str.contains('L5N-028')&wide.period.eq('AM')].iloc[0]
inputs=json.loads((ROOT/'data/inputs/detector78/calculation_inputs.json').read_text())
breaks=np.array([r['speed_lower_mph'] for r in inputs['rate_table']]);rates=np.array([r['CO2_g_per_veh_h'] for r in inputs['rate_table']])/1000
vgrid=np.sort(np.r_[20,75,breaks[(breaks>20)&(breaks<75)]-1e-7,breaks[(breaks>20)&(breaks<75)]])
xy=lambda v,r:f'({(v-20)/55*13.4:.6f},{r/24*4.5:.6f})'
plot=[r'\begin{center}\begin{tikzpicture}[x=1cm,y=1cm,font=\small]',r'\path[use as bounding box] (-0.9,-0.9) rectangle (14.4,5.9);']
for y in [0,5,10,15,20]:plot.extend([r'\draw[rulegray,line width=.3pt] '+xy(20,y)+' -- '+xy(75,y)+';',r'\node[left,text=muted] at '+xy(20,y)+' {'+str(y)+'};'])
for x in [20,30,40,50,60,70]:plot.append(r'\node[below=5pt,text=muted] at '+xy(x,0)+' {'+str(x)+'};')
plot.extend([r'\draw[navy] (0,0)--(13.4,0);',r'\draw[navy] (0,0)--(0,4.5);',r'\node[anchor=west,font=\small\bfseries] at (0,5.45) {CO$_2$ rate (kg/(vehicle\,h))};',r'\node at (6.7,-0.75) {Speed (mph)};',r'\draw[teal,line width=1.3pt] plot coordinates {'+' '.join(xy(v,rates[np.searchsorted(breaks,v,side='right')-1]) for v in vgrid)+'};'])
vq,vf,vp=e.vq_hat_mph,e.vf_mph,e.mean_speed_predicted_mph;rq,rf,rm,rs=e.CO2_lookup_rate_queue/1000,e.CO2_lookup_rate_free/1000,e.CO2_predicted_chord_rate/1000,e.CO2_lookup_rate_predicted_mean/1000
plot.extend([r'\draw[rust,line width=1.4pt] '+xy(vq,rq)+' -- '+xy(vf,rf)+';',r'\draw[navy,dashed] '+xy(vp,rs)+' -- '+xy(vp,rm)+';'])
for v,r,c in [(vq,rq,'rust'),(vf,rf,'rust'),(vp,rm,'rust'),(vp,rs,'teal')]:plot.append(r'\filldraw[fill='+c+',draw=white,line width=.6pt] '+xy(v,r)+r' circle (2.4pt);')
plot.extend([r'\node[anchor=south east,text=rust] at '+xy(vp-1,rm+3.1)+r' {$r_M^{\eff}=13.19$};',r'\draw[rust,line width=.5pt] '+xy(vp-.6,rm+2.8)+' -- '+xy(vp,rm+.6)+';',r'\node[anchor=north west,text=teal] at '+xy(vp+1,rs-.4)+r' {$r_0(\widehat{\bar v})=9.73$};',r'\node[anchor=south west] at '+xy(vq,rq+.7)+r' {$\widehat v_q=26.01$};',r'\node[anchor=south east] at '+xy(vf,rf+.7)+r' {$v_f=68.50$};',r'\draw[teal,line width=1.3pt] (6.6,5.5)--(7.2,5.5);',r'\node[anchor=west,text=teal] at (7.3,5.5) {Lookup};',r'\draw[rust,line width=1.4pt] (9.6,5.5)--(10.2,5.5);',r'\node[anchor=west,text=rust] at (10.3,5.5) {Two-speed chord};',r'\end{tikzpicture}\end{center}'])
parts['FIGURE']='\n'.join(plot)
text=(SUP/'analysis_report_template.tex').read_text(encoding='utf-8')
for k,v in parts.items():text=text.replace('@@'+k+'@@',v)
assert '@@' not in text
tex=REPORTS/'QVDFE_137_Episode_Error_Analysis.tex';tex.write_text(text,encoding='utf-8')
exe=args.pdflatex
for run in range(2):
 result=subprocess.run([exe,'-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-output-directory='+str(TMP),str(tex)],capture_output=True,text=True)
 (TMP/f'compile_{run+1}.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
 if result.returncode:raise RuntimeError((result.stdout+result.stderr)[-5000:])
pdf=TMP/(tex.stem+'.pdf');log=(TMP/(tex.stem+'.log')).read_text(encoding='utf-8',errors='replace')
warnings=[s for s in log.splitlines() if any(t in s for t in ['Overfull','Underfull','Missing character','LaTeX Warning'])]
print('Pages:',len(PdfReader(pdf).pages));print('Warnings:',warnings)
if any(t in log for t in ['Overfull','Missing character']):raise RuntimeError('Repair typesetting warnings before export.')
target=REPORTS/'QVDFE_137_Episode_Error_Analysis.pdf';shutil.copy2(pdf,target)
(args.output/'support/readability_revision_audit.json').write_text(json.dumps({'pages':len(PdfReader(pdf).pages),'layout_warnings':warnings,'equations':'native LaTeX vector text','average_error_table_included':False,'existing_WAPE_results_preserved':True},indent=2))
print(target)
