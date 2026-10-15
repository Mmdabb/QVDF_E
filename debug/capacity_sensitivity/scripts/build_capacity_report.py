"""Render the separate capacity report from the audited numerical CSV exports."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
POLS = ['CO2','NOx','CO','HC']
LABELS = ['CO₂','NOₓ','CO','HC']
BLUE, TEAL, AMBER, INK, GRID = '#2563EB','#168C69','#E69F00','#17324D','#E2E8F0'


def finish(fig, out, stem):
    for suffix in ('svg','png'):
        fig.savefig(out/'figures'/f'{stem}.{suffix}',dpi=180,facecolor='white',bbox_inches='tight')
    plt.close(fig)


def figures(out, fixed, sweep, episodes, detector):
    (out/'figures').mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.labelcolor':INK,'text.color':INK,
                         'xtick.color':INK,'ytick.color':INK,'axes.edgecolor':GRID,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.titleweight':'bold','svg.fonttype':'none'})
    fig, axs = plt.subplots(1,2,figsize=(11.4,4.6),layout='constrained',sharey=True)
    for ax,strategy,title in zip(axs,['co2_target','balanced_four_pollutants'],['CO₂ objective','Four-pollutant objective']):
        z=fixed[(fixed.bounds_profile=='primary_omega_5_20')&(fixed.strategy==strategy)&(fixed.cohort=='paired_strict_free')]
        for offset,policy,method,label,color in [(-.25,'strict_baseline_capacity','baseline_M','Preserved model','#67768A'),
                                                (0.,'strict_baseline_capacity','M','Capacity fixed',BLUE),
                                                (.25,'free_capacity','M','Capacity free',TEAL)]:
            values=z[(z.capacity_policy==policy)&(z.method==method)].set_index('pollutant').reindex(POLS).WAPE_pct
            ax.bar(np.arange(4)+offset,values,width=.23,color=color,label=label,zorder=3)
        ax.set_xticks(np.arange(4),LABELS);ax.set_title(title,pad=12);ax.grid(axis='y',color=GRID,zorder=0)
        ax.set_ylim(bottom=0);ax.set_xlabel('Same 136 episodes; primary FD bounds')
    axs[0].set_ylabel('Episode-total emission WAPE (%)')
    handles,labels=axs[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncols=3,frameon=False)
    finish(fig,out,'fixed_capacity_comparison')

    fig,axs=plt.subplots(2,2,figsize=(11.4,8.3),layout='constrained')
    xs=np.array([1,1.1,1.25,1.5,2.])
    N=int(sweep[(sweep.cohort=='common_capacity_increases')&(sweep.scenario=='multiplier_1')].N.max())
    for ax,quantity,title in [(axs[0,0],'CO2','CO₂ emission error'),(axs[0,1],'mean_delay','Mean-delay error')]:
        for policy,label,color,marker in [('frozen_coefficients','Coefficients unchanged',BLUE,'o'),('fd_rescaled','Duration coefficient rescaled',TEAL,'s')]:
            z=sweep[(sweep.cohort=='common_capacity_increases')&(sweep.quantity==quantity)&(sweep.method=='sensitivity')&(sweep.coefficient_policy==policy)].set_index('scenario')
            ax.plot(xs,[z.loc[f'multiplier_{x:g}','WAPE_pct'] for x in xs],color=color,marker=marker,label=label,lw=2)
        ax.set_title(title+f' · same {N} episodes',pad=10);ax.set_xlabel('Capacity multiplier');ax.set_ylabel('WAPE (%)');ax.grid(color=GRID)
        ax.set_xticks(xs)
    ax=axs[1,0];allxs=np.array([.8,1,1.1,1.25,1.5,2.])
    for policy,label,color,marker in [('frozen_coefficients','Coefficients unchanged',BLUE,'o'),('fd_rescaled','Duration coefficient rescaled',TEAL,'s')]:
        g=episodes[episodes.coefficient_policy==policy].groupby('scenario').valid.sum()
        ax.plot(allxs,[g.loc[f'multiplier_{x:g}'] for x in allxs],color=color,marker=marker,lw=2,label=label)
    ax.set_title('Retained physical and closed cases',pad=10);ax.set_xlabel('Capacity multiplier');ax.set_ylabel('Valid cases out of 137');ax.set_ylim(0,145);ax.grid(color=GRID);ax.set_xticks(allxs)
    ax=axs[1,1];z=detector[detector.represented_in_137]
    ax.scatter(z.profile_q995_vphpl,z.C_vphpl,color=BLUE,alpha=.72,s=24,edgecolors='white',linewidths=.4)
    lo=min(z.profile_q995_vphpl.min(),z.C_vphpl.min())*.9;hi=max(z.profile_q995_vphpl.max(),z.C_vphpl.max())*1.05
    ax.plot([lo,hi],[lo,hi],color=INK,ls='--',lw=1,label='Equal capacity and profile q99.5')
    ax.set_xlim(lo,hi);ax.set_ylim(lo,hi);ax.set_title('104 detectors represented in the sample',pad=10)
    ax.set_xlabel('Positive-profile flow q99.5 (veh/h/lane)');ax.set_ylabel('Used capacity (veh/h/lane)');ax.grid(color=GRID);ax.legend(fontsize=8,loc='upper left',frameon=False)
    handles,labels=axs[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncols=2,frameon=False)
    finish(fig,out,'capacity_sweep_and_sources')


def equation(contents):
    return '<div class="equation"><math xmlns="http://www.w3.org/1998/Math/MathML" display="block">'+contents+'</math></div>'


def sub(a,b):
    return f'<msub><mi>{a}</mi><mi>{b}</mi></msub>'


def build(out):
    out=Path(out).resolve()
    if not (out/'.capacity-sensitivity.json').is_file():
        raise ValueError('Build numerical outputs in an owned working directory first.')
    fixed=pd.read_csv(out/'fixed_traffic_metrics.csv');sweep=pd.read_csv(out/'capacity_sweep_metrics.csv')
    episodes=pd.read_csv(out/'capacity_sweep.csv');detector=pd.read_csv(out/'detector_capacity_audit.csv')
    summary=json.loads((out/'analysis_summary.json').read_text())
    figures(out,fixed,sweep,episodes,detector)
    paired=fixed[(fixed.bounds_profile=='primary_omega_5_20')&(fixed.cohort=='paired_strict_free')]
    rows=[]
    for title,strategy,policy,method in [
            ('Preserved two-speed model','co2_target','strict_baseline_capacity','baseline_M'),
            ('CO₂ objective · capacity fixed','co2_target','strict_baseline_capacity','M'),
            ('CO₂ objective · capacity free','co2_target','free_capacity','M'),
            ('Four-pollutant objective · capacity fixed','balanced_four_pollutants','strict_baseline_capacity','M'),
            ('Four-pollutant objective · capacity free','balanced_four_pollutants','free_capacity','M')]:
        z=paired[(paired.strategy==strategy)&(paired.capacity_policy==policy)&(paired.method==method)].set_index('pollutant')
        rows.append('<tr><th scope="row">'+title+'</th><td>'+str(int(z.N.iloc[0]))+'</td>'+''.join(f'<td>{z.loc[p,"WAPE_pct"]:.2f}%</td>' for p in POLS)+'</tr>')
    table='<div class="scroll"><table><caption>Episode-total emission WAPE against the point-speed proxy O; identical 136-episode cohort</caption><thead><tr><th>Calculation</th><th>N</th>'+''.join('<th>'+p+'</th>' for p in LABELS)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    # One summary table focuses on the traffic/emission tradeoff. The fixed/free
    # comparison is already shown in the first figure and the separate dashboard.
    rows=[]
    for policy,label in [('frozen_coefficients','Coefficients unchanged'),('fd_rescaled','Duration coefficient rescaled')]:
        for multiplier in (1.,1.1,1.25,1.5,2.):
            scenario=f'multiplier_{multiplier:g}'
            z=sweep[(sweep.cohort=='common_capacity_increases')&(sweep.coefficient_policy==policy)&(sweep.scenario==scenario)&(sweep.method=='sensitivity')].set_index('quantity')
            valid=int(episodes.loc[(episodes.coefficient_policy==policy)&(episodes.scenario==scenario),'valid'].sum())
            rows.append(f'<tr><th scope="row">{label}</th><td>{multiplier:g}×</td><td>{valid}/137</td>'+''.join(f'<td>{z.loc[p,"WAPE_pct"]:.2f}%</td>' for p in ['CO2','duration','mean_delay'])+'</tr>')
    sweep_table='<div class="scroll"><table><caption>Capacity increases: all error columns use the same 104 episodes; valid-count column refers to all 137</caption><thead><tr><th>Calculation</th><th>C multiplier</th><th>Valid cases</th><th>CO₂ WAPE</th><th>Duration WAPE</th><th>Mean-delay WAPE</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    m=sub;frac=lambda a,b:'<mfrac><mrow>'+a+'</mrow><mrow>'+b+'</mrow></mfrac>'
    fixed_formula=equation(m('k','j')+'<mo>=</mo>'+frac('<mi>μ</mi>',m('v','q'))+'<mo>+</mo>'+frac('<mi>μ</mi>','<mi>ω</mi>')+'<mo>,</mo><mspace width="1em"/>'+m('C','FD')+'<mo>=</mo>'+frac(m('v','f')+'<mi>ω</mi>'+m('k','j'),m('v','f')+'<mo>+</mo><mi>ω</mi>'))
    sweep_formula=equation('<msup><mi>x</mi><mo>′</mo></msup><mo>=</mo>'+frac('<mi>D</mi>','<msup><mi>C</mi><mo>′</mo></msup>')+'<mo>,</mo><mspace width="1em"/><msup><mi>P</mi><mo>′</mo></msup><mo>=</mo><mi>max</mi><mo>(</mo>'+m('f','d')+'<msup><mrow><mo>(</mo><msup><mi>x</mi><mo>′</mo></msup><mo>)</mo></mrow><mi>n</mi></msup><mo>,</mo><msup><mi>x</mi><mo>′</mo></msup><mo>)</mo>')
    delay_formula=equation('<msup>'+m('w','peak')+'<mo>′</mo></msup><mo>=</mo>'+m('T','f')+m('f','p')+'<msup><mrow><mo>(</mo><msup><mi>P</mi><mo>′</mo></msup><mo>)</mo></mrow><mi>s</mi></msup><mo>,</mo><mspace width="1em"/><msup><mover><mi>w</mi><mo>¯</mo></mover><mo>′</mo></msup><mo>=</mo><mi>θ</mi><msup>'+m('w','peak')+'<mo>′</mo></msup><mo>,</mo><mspace width="1em"/><msup><mi>μ</mi><mo>′</mo></msup><mo>=</mo>'+frac('<mi>D</mi>','<msup><mi>P</mi><mo>′</mo></msup>'))
    gauge_formula=equation('<msup>'+m('f','d')+'<mo>′</mo></msup><mo>=</mo>'+m('f','d')+'<msup><mrow><mo>(</mo>'+frac('<msup><mi>C</mi><mo>′</mo></msup>','<mi>C</mi>')+'<mo>)</mo></mrow><mi>n</mi></msup>')
    css='''body{font:16px/1.58 system-ui,sans-serif;color:#17324D;background:#fff;max-width:1080px;margin:32px auto;padding:0 24px}h1{font-size:30px;line-height:1.2;max-width:800px}h2{font-size:23px;margin-top:36px;border-top:1px solid #E2E8F0;padding-top:22px}h3{font-size:18px}p{max-width:960px}a{color:#2563EB}nav{display:flex;gap:10px 20px;flex-wrap:wrap;margin:22px 0}.note{background:#F0F7FF;border-left:4px solid #2563EB;padding:16px 20px}.caution{background:#FFF7E5;border-left-color:#E69F00}.muted,figcaption{font-size:14px;color:#536579}figure{margin:22px 0}figure img{display:block;width:100%;height:auto}figcaption{padding-top:8px}.equation{padding:8px 14px;overflow-x:auto;background:#F7FAFC;margin:10px 0;font-size:19px}table{border-collapse:collapse;width:100%;font-size:14px}caption{text-align:left;font-weight:600;padding:10px 0}th,td{padding:11px 12px;border-bottom:1px solid #D5DFEA;text-align:right}th:first-child{text-align:left}thead{background:#EAF1F8}tbody th{font-weight:500}tbody tr:nth-child(even){background:#F8FAFC}.scroll{overflow-x:auto}.downloads{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:8px}li{margin:8px 0}@media print{body{font-size:11pt;margin:0;max-width:none}nav{display:none}h2,figure,table{break-inside:avoid}h2{break-after:avoid}}'''
    text='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Capacity sensitivity — QVDF-E</title><style>'+css+'</style></head><body>'
    text+='<p class="muted">QVDF-E · exploratory diagnostics · preserved 137-episode sample</p><h1>Does freeing capacity improve the emission comparison?</h1>'
    text+='<p class="note"><strong>Yes, as a conditional fit to the same emission proxy.</strong> Allowing capacity to change improves the optimized two-speed emission comparison relative to strictly preserving capacity. The earlier bounded-FD analysis already allowed this change; its free-capacity objective is reproduced here, rather than presented as a new improvement.</p>'
    text+='<nav><a href="#fixed">Fixed traffic comparison</a><a href="#sweep">Capacity through the traffic model</a><a href="#sources">Capacity source audit</a><a href="#next">What to check before rerunning</a><a href="#files">Data and calculations</a></nav>'
    text+='<section id="fixed"><h2>1. Change the FD allocation while preserving traffic predictions</h2><p>Demand, free-flow speed, episode duration, delay and discharge μ = D/P remain fixed. Each episode uses one queue-state speed v<sub>q</sub> (mph) for all four pollutants. The strict case requires C<sub>FD</sub> = C; the free case lets C<sub>FD</sub> vary. Both search the same exploratory bounds: k<sub>j</sub> = 150–300 veh/mi/lane and positive backward-wave magnitude ω = 5–20 mph.</p>'+fixed_formula
    text+='<p>The CO₂ objective minimizes absolute relative CO₂ error. The four-pollutant objective minimizes the mean of the four squared relative errors, with equal pollutant weights. These are conditional fits to the same observations, not out-of-sample predictions. The reported WAPE is calculated from each episode’s total emission, then pooled across episodes.</p><p>On the same 136 feasible episodes, the CO₂ objective reduces CO₂ WAPE from 22.39% in the preserved model to 16.07% with fixed capacity and 11.55% with free capacity. The four-pollutant objective gives CO₂ WAPE of 16.96% and 12.89%, respectively.</p>'
    text+='<p>The primary fixed-capacity case is feasible for 136 of 137 episodes; the free case is feasible for all 137. Episode ep101 (D12 I-5 S, L5S-264; C = 792.87 veh/h/lane) has no admissible fixed-capacity pair within the primary bounds. Expanding the lower wave-speed bound to 3 mph makes both cases feasible for all 137. All failures and both bounds are retained in the CSVs.</p>'
    text+='<figure><img src="figures/fixed_capacity_comparison.svg" alt="Grouped bars compare preserved, fixed-capacity and free-capacity emission WAPE for each pollutant and objective."><figcaption>Primary bounds; the same 136 jointly feasible episodes in every bar. O is the emission proxy calculated from recorded point speeds, not measured vehicle-trajectory emissions. Lower bars describe a better conditional match to that proxy.</figcaption></figure></section>'
    text+='<section id="sweep"><h2>2. A larger capacity also changes the QVDF traffic calculation</h2><p>In a separate calculation, replace C by C′ while holding free-flow speed, jam density k<sub>j</sub> = 220, the selected episodes and fitted coefficients fixed. Capacity multipliers are 0.8, 1, 1.1, 1.25, 1.5 and 2; released metadata capacity is another scenario where available. The entire calculation is propagated:</p>'+sweep_formula+delay_formula
    prime=lambda symbol:'<msup>'+symbol+'<mo>′</mo></msup>'
    Cp,wp,mup=prime('<mi>C</mi>'),prime('<mi>ω</mi>'),prime('<mi>μ</mi>')
    text+='<p>The triangular FD is then recomputed:</p>'+equation(wp+'<mo>=</mo>'+frac(Cp,m('k','j')+'<mo>−</mo>'+frac(Cp,m('v','f')))+'<mo>,</mo><mspace width="1em"/>'+prime(m('v','q'))+'<mo>=</mo>'+frac(mup,m('k','j')+'<mo>−</mo>'+frac(mup,wp)))
    text+='<p>New two-state times and lookup rates produce the new emission totals. Every row retains domain, finite-link and nonnegative-arrival checks. An invalid result is left undefined and counted; it is never replaced by zero.</p>'
    text+='<p class="note caution"><strong>An apparent emission gain can come with worse traffic predictions.</strong> On the same 104 episodes valid for every capacity increase, doubling C with unchanged coefficients lowers CO₂ WAPE from 25.16% to 13.31%, but raises mean-delay WAPE from 28.05% to 53.64% and duration WAPE from 6.13% to 48.92%. It also makes 33 of the original 137 cases fail finite-link geometry. This is not evidence that doubling capacity is a better calibrated model.</p>'
    text+='<h3>Separate control: rescale the duration coefficient</h3><p>A uniform capacity change can be absorbed by the duration power-law coefficient:</p>'+gauge_formula
    text+='<p>On the power branch this preserves P, peak delay, mean delay and μ exactly, while the FD queue speed still changes. Across the same 104 episodes, doubling capacity under this control raises CO₂ WAPE to 39.56%, with unchanged traffic errors. All 137 cases remain valid for capacity increases in this control. It is an algebraic reparameterization, not a full recalibration. Detector-specific metadata ratios require different rescaling within a fitting group; those rows are labelled as individual algebraic controls, not a valid common parameter card.</p>'
    text+=sweep_table
    text+='<figure><img src="figures/capacity_sweep_and_sources.svg" alt="Capacity sensitivity plots show CO2 error, mean-delay error, valid case counts, and used capacity versus profile flow percentile."><figcaption>Top: the same 104 episodes valid for every multiplier ≥ 1 under both coefficient policies. Bottom left: validity across all 137 original cases, including the 0.8 decrease. Bottom right: 104 distinct detectors, one point per detector. The intersection across all multipliers including 0.8 has only six episodes and is exported separately; it is not used for the higher-capacity conclusions.</figcaption></figure></section>'
    text+='<section id="sources"><h2>3. Are the existing capacities too low?</h2><p>The 137 episodes represent 104 detectors. Their median used capacity is <strong>1,219.42 veh/h/lane</strong>; the median ratio to the detector’s positive-profile flow q99.5 is <strong>0.947</strong>. A median <strong>8.16%</strong> of valid profile flow readings exceeds the fitted capacity. Seventy-four of these detectors use accepted S3 fits; the others use the preserved fallback. These diagnostics justify checking the FD fit and its observation support.</p>'
    text+='<p>Released metadata is available for 100 of these detectors and gives 2,000 veh/h/lane for every one. The median fitted-to-metadata ratio is 0.610. Because this metadata comparator is constant across detectors, it should not be treated as an independently estimated capacity for each site. Arizona metadata capacity is unavailable. The profile q99.5 is also descriptive, not an independent capacity measurement.</p>'
    text+='<p>The broader inventory contains 352 detectors, including 248 outside the retained emission sample. Twenty-three capacities exceed the inherited 500–3,500 acceptance range; the largest is 7,857 veh/h/lane. Those 23 have one or two declared lanes and are absent from the retained 137 episodes. Their lane/count mapping, units, fallback and fit support warrant a source audit as well. A low-capacity-only correction would miss these anomalies.</p></section>'
    text+='<section id="next"><h2>4. What would justify a full recalibration and rerun?</h2><ol><li><strong>Check traffic inputs first:</strong> lane counts, total versus per-lane flow, five-minute conversion and profile averaging; resolve the extreme fallback capacities and inspect free/congested branch coverage.</li><li><strong>Refit FD parameters against traffic evidence:</strong> assess both branches, residual patterns and held-out daily data where available. Compare the same observations with the current fit. Do not select FD parameters solely to match the emission proxy.</li><li><strong>Then propagate the accepted change:</strong> repeat the affected FD, episode detection/QC, QVDF calibration and emission stages, retaining the full sample accounting. Report traffic errors together with emission errors and compare common cohorts.</li></ol><p>The current evidence supports a focused FD/source audit before a full rerun. It does not establish that every low fitted capacity is wrong, nor that raising capacity will improve a recalibrated model. Emission fitting identifies a queue speed; many jam-density/wave-speed pairs produce that speed, so these data alone do not identify a unique physical FD.</p></section>'
    text+='<section id="files"><h2>Data and calculations</h2><div class="downloads">'
    for name,label in [('fixed_traffic_comparison.csv','All fixed/free episode calculations'),('fixed_traffic_metrics.csv','Pooled fixed/free comparisons'),('capacity_sweep.csv','Every capacity scenario and validity flag'),('capacity_sweep_metrics.csv','Same-cohort sweep metrics'),('detector_capacity_audit.csv','Detector capacity source audit'),('detector_capacity_summary.csv','Capacity summaries by corridor'),('analysis_summary.json','Assumptions and sample accounting'),('verification.json','Numerical verification and input hashes')]:
        text+='<a href="'+name+'">'+html.escape(label)+'</a>'
    text+='</div><p class="muted">No production calibration, observed input, episode selection or published result table was changed. Editable function-based SVG figures and their generators accompany this report.</p></section></body></html>\n'
    (out/'report.html').write_text(text,encoding='utf-8')
    (out/'README.md').write_text('''# Capacity sensitivity diagnostics

Open [the separate report](report.html) for the interpretation. This is an exploratory analysis of the preserved 137-episode sample, not a recalibrated experiment.

- `fixed_traffic_comparison.csv`: two bounds × two objectives × fixed/free capacity × 137 episodes; invalid rows remain present.
- `capacity_sweep.csv`: six capacity multipliers plus metadata, with unchanged coefficients or an algebraic duration-coefficient rescaling. All 1,918 candidate rows remain present.
- `*_metrics.csv`: pooled episode-total metrics with explicit cohort and baseline-on-the-same-rows comparisons. For increases, use `common_capacity_increases` (104 episodes); the intersection including the 0.8 decrease contains only six.
- `detector_capacity_audit.csv`: one row for every 352 detector cards, including those outside the 137-episode sample.
- `figures/`: editable SVG and preview PNG plots. Values come directly from the CSVs.
- `verification.json`: equation checks and source hashes. The independent `verify_analysis.py` checks the equations, lookup rates, objective minima, validity flags, cohort summaries and source data without importing the analysis generator.

The previous bounded FD analysis already allowed capacity changes. The free-capacity optimum here reproduces it; the new comparison is with a strictly fixed-capacity alternative. The optimization uses the observed point-speed emission proxy O, not measured vehicle emissions.

From the repository root, regenerate into a separate working directory:

```text
python debug/capacity_sensitivity/scripts/build_capacity_sensitivity.py
python debug/capacity_sensitivity/scripts/build_capacity_report.py
```

Outputs default to `debug/output/capacity_sensitivity`. Reference data and production model files are never replaced.

Verify the published results in `debug/capacity_sensitivity`:

```text
python debug/capacity_sensitivity/verify_analysis.py
```

Verify newly regenerated results in the working directory:

```text
python debug/capacity_sensitivity/verify_analysis.py --directory debug/output/capacity_sensitivity
```
''',encoding='utf-8')
    print(json.dumps({'report':str(out/'report.html'),'figures':2,'summary_tables':1,'native_MathML_equations':5},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'debug/output/capacity_sensitivity')
    build(parser.parse_args().output)
