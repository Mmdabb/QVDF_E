"""Display strict versus free capacity results without recalibrating any model."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from dashboard_layout import render_page, mathml, math_expression, mi, mn, op, row, sub, frac
from parameter_diagnostic_views import grouped_table, CSS

ROOT = Path(__file__).resolve().parents[3]
POLS = ['CO2', 'NOx', 'CO', 'HC']
SCRIPT = """<script>(()=>{
const table=document.getElementById('capacity-comparison-table'),search=document.getElementById('inverse-search'),strategy=document.getElementById('inverse-strategy'),bounds=document.getElementById('inverse-bounds');
function filter(){const q=search.value.trim().toLowerCase(),s=strategy.value,b=bounds.value;let n=0;Array.from(table.tBodies[0].rows).forEach(r=>{r.hidden=!(r.dataset.search.includes(q)&&(!s||r.dataset.strategy===s)&&r.dataset.bounds===b);if(!r.hidden)n++});document.getElementById('inverse-count').textContent=n+' episode–strategy comparisons'}
search.addEventListener('input',filter);strategy.addEventListener('change',filter);bounds.addEventListener('change',filter);
table.querySelectorAll('.inverse-sort').forEach(button=>button.addEventListener('click',()=>{
 const key=button.dataset.key,numeric=button.dataset.numeric==='true',head=button.parentElement,direction=head.getAttribute('aria-sort')==='ascending'?-1:1;
 table.querySelectorAll('.inverse-column-row th').forEach(h=>{h.setAttribute('aria-sort','none');h.querySelector('span').textContent='↕'});head.setAttribute('aria-sort',direction===1?'ascending':'descending');button.querySelector('span').textContent=direction===1?'↑':'↓';
 Array.from(table.tBodies[0].rows).sort((a,b)=>{const x=a.querySelector('[data-key="'+key+'"]').dataset.value,y=b.querySelector('[data-key="'+key+'"]').dataset.value;if(numeric){const xn=x===''?NaN:Number(x),yn=y===''?NaN:Number(y);if(!Number.isFinite(xn))return Number.isFinite(yn)?1:0;if(!Number.isFinite(yn))return -1;return direction*(xn-yn)}return direction*x.localeCompare(y,undefined,{numeric:true})}).forEach(r=>table.tBodies[0].appendChild(r));
}));filter();})();</script>"""


def build(out: Path, source: Path | None = None):
    source = source or ROOT/'debug/capacity_sensitivity'
    data = pd.read_csv(source/'fixed_traffic_comparison.csv')
    traffic = pd.read_csv(out/'traffic_parameters.csv')
    folders = dict(zip(traffic.case_id, traffic.folder))
    keys = ['case_id','episode_id','sensor_uid','corridor','date','period','bounds_profile','strategy']
    strict = data[data.capacity_policy.eq('strict_baseline_capacity')].copy()
    free = data[data.capacity_policy.eq('free_capacity')].copy()
    merged = strict.merge(free, on=keys, validate='one_to_one', suffixes=('_strict','_free'))
    assert len(merged) == 548
    view = merged[keys].copy()
    view['source_bounds_profile'] = view.bounds_profile
    view['bounds_profile'] = view.bounds_profile.map({'primary_omega_5_20':'primary','expanded_omega_3_20':'expanded_lower_wave'})
    assert view.bounds_profile.notna().all()
    for key in ['baseline_C_vphpl','baseline_mu_vphpl','baseline_q_mph']:
        view[key] = merged[key+'_strict']
    status_names = {'exact_root':'Exact CO₂ match','attained_minimum':'Minimum balanced error','attained_closest':'Closest attainable','boundary_limit_approximation':'Rate-boundary limit'}
    for policy in ['strict','free']:
        for key in ['valid','selected_q_mph','selected_kj_veh_mi_lane','selected_omega_mph','selected_C_vphpl','capacity_change_pct']:
            view[policy+'_'+key] = merged[key+'_'+policy]
        view[policy+'_status'] = [status_names.get(str(s), str(s).replace('_',' ')) if valid else 'No feasible bounded pair' for s,valid in zip(merged['solution_status_'+policy],merged['valid_'+policy])]
        residuals = []
        for p in POLS:
            residual = merged['M_'+p+'_g_'+policy]/merged['O_'+p+'_g_'+policy]-1
            view[policy+'_'+p+'_ape_pct'] = 100*residual.abs()
            residuals.append(residual.to_numpy())
        view[policy+'_normalized_rmse_pct'] = 100*np.sqrt(np.mean(np.square(residuals),axis=0))
    view['jointly_feasible'] = view.strict_valid & view.free_valid
    view.to_csv(out/'fd_capacity_comparison.csv',index=False,lineterminator='\n')
    body = '<h1>Fixed versus freely varying capacity</h1><p class="note">Both alternatives retain the same demand, free-flow speed, fitted duration, delay and discharge. Each finds its best emission-target queue speed within the same jam-density and wave-speed bounds. The free-capacity column allows the implied capacity to change.</p>'
    body += '<p>The earlier bounded analysis already allowed a capacity change when needed to reach its optimal speed. Its preference for preserving capacity was a secondary choice among equally good emission solutions. The free-capacity results here reproduce that optimum; the new comparison is against a <strong>strictly fixed capacity</strong>.</p>'
    C0=sub(mi('C'),mn(0));mu0=sub(mi('μ'),mn(0));vf=sub(mi('v'),mi('f'));omega=mi('ω');kj=sub(mi('k'),mi('j'))
    body += '<div class="equations"><div class="equation-card"><h3>Strictly fixed capacity</h3>'
    body += math_expression(row(kj,op('='),frac(C0,vf),op('+'),frac(C0,omega)),'For fixed capacity, jam density equals capacity over free-flow speed plus capacity over wave speed.')
    body += math_expression(row(sub(mi('v'),mi('q')),op('='),frac(mu0,row(frac(C0,vf),op('+'),frac(row(C0,op('−'),mu0),omega)))),'Queue speed at fixed capacity and discharge follows the constrained triangular FD.')
    body += '</div><div class="equation-card"><h3>Capacity may vary</h3>'+mathml('exact_fd_curve')+mathml('capacity_closure')+'<p>Capacity is calculated from each candidate pair, with no requirement that it equal the current capacity.</p></div></div>'
    body += '<details><summary>Emission targets and physical limit</summary>'+mathml('co2_objective')+mathml('balanced_objective')+mathml('normalized_rmse')+mathml('physical_queue_bound')+'</details>'
    body += '<p>Primary bounds: 150–300 veh/mi/lane for jam density and 5–20 mph for the backward-wave magnitude. The expanded bounds lower the latter to 3 mph. Primary fixed capacity is feasible for 136/137 episodes; free capacity is feasible for all 137. Compare pooled errors on the same feasible cases. These are conditional fits to O, the recorded-speed emission reference, not independently validated capacities.</p>'
    body += '<nav class="downloads"><a href="fd_capacity_comparison.csv">Side-by-side results CSV</a><a href="../../../capacity_sensitivity/fixed_traffic_comparison.csv">Full calculation CSV</a><a href="../../../capacity_sensitivity/report.html">Separate capacity sensitivity report</a></nav>'
    body += '<div class="inverse-diagnostics"><div class="inverse-controls"><label for="inverse-search">Find an episode</label><input id="inverse-search" type="search" placeholder="Case, corridor, detector or date"><label for="inverse-strategy">Target</label><select id="inverse-strategy"><option value="">Both targets</option><option value="co2_target">CO₂</option><option value="balanced_four_pollutants">Balanced four pollutants</option></select><label for="inverse-bounds">Bounds</label><select id="inverse-bounds"><option value="primary">Primary: 5–20 mph</option><option value="expanded_lower_wave">Expanded: 3–20 mph</option></select><span id="inverse-count" aria-live="polite"></span></div>'
    groups = [('Episode and current values', [('case_id','Case',None),('strategy','Target',None),('baseline_C_vphpl','Current C<br>veh/h/lane',1),('baseline_mu_vphpl','Fixed discharge μ<br>veh/h/lane',1),('baseline_q_mph','Original v<sub>q</sub><br>mph',3)])]
    for policy,label in [('strict','Strictly fixed capacity'),('free','Freely varying capacity')]:
        columns = [(policy+'_status','Solution',None),(policy+'_selected_q_mph','v<sub>q</sub><br>mph',3),(policy+'_selected_kj_veh_mi_lane','k<sub>j</sub><br>veh/mi/lane',2),(policy+'_selected_omega_mph','ω<br>mph',3),(policy+'_selected_C_vphpl','Capacity<br>veh/h/lane',1)]
        if policy == 'free': columns += [(policy+'_capacity_change_pct','Capacity change<br>%',2)]
        columns += [(policy+'_normalized_rmse_pct','Four-pollutant<br>normalized RMSE %',2)]
        columns += [(policy+'_'+p+'_ape_pct',p+' total<br>APE %',2) for p in POLS]
        groups.append((label,columns))
    body += grouped_table(view,groups,'capacity-comparison-table',folders)+'</div>'
    body += '<p class="muted">Changing capacity while retaining the original fitted traffic is a conditional FD experiment. The separate report propagates capacity changes through D/C, duration and delay, and reports physical feasibility and common-cohort errors. A subsequent calibration would need one consistent FD per detector.</p>'
    css = CSS+'.inverse-table td[data-key$="_status"]{white-space:normal;min-width:155px;max-width:210px}'
    (out/'fd_capacity_comparison.html').write_text(render_page('Capacity comparison',body,'fd_capacity_comparison',extra_css=css,scripts=SCRIPT),encoding='utf-8',newline='\n')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'debug/output/episode_time_series')
    parser.add_argument('--source',type=Path,default=ROOT/'debug/capacity_sensitivity')
    args=parser.parse_args()
    from build_parameter_diagnostics import safe_output, rebase_analysis_links
    output = safe_output(args.output)
    build(output,args.source.resolve())
    rebase_analysis_links(output,args.source.resolve())
