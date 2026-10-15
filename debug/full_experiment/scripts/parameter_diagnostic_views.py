"""Readable offline views of emission-target and FD sensitivity calculations."""
from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd

from dashboard_layout import mathml, render_page

POLS = ["CO2", "NOx", "CO", "HC"]
STRATEGIES = {"co2_target": "CO₂ target", "balanced_four_pollutants": "Balanced four"}
STATUS = {"exact_root": "Exact CO₂ match", "attained_closest": "Closest attainable",
          "attained_minimum": "Minimum balanced error", "boundary_limit_approximation": "Rate-boundary limit"}


def fmt(value, digits=2):
    if pd.isna(value):
        return "—"
    if isinstance(value, (bool, np.bool_)):
        return "Yes" if value else "No"
    if isinstance(value, (float, int, np.number)):
        if not np.isfinite(value):
            return "—"
        if abs(value) >= 1e7 or (0 < abs(value) < 10**(-digits-1)):
            return f"{value:.3g}"
        if abs(value) < .5*10**-digits:
            value = 0.
        return f"{value:,.{digits}f}"
    return str(value)


def grouped_table(frame, groups, identifier, folders):
    esc = html.escape
    text = f'<div class="scroll inverse-scroll" tabindex="0"><table class="inverse-table" id="{identifier}"><thead><tr class="inverse-group-row">'
    for j, (label, columns) in enumerate(groups):
        text += f'<th colspan="{len(columns)}" scope="colgroup" class="inverse-tone-{j%3}">{label}</th>'
    text += '</tr><tr class="inverse-column-row">'
    flat = []
    for g, (_, columns) in enumerate(groups):
        for i, (key, label, digits) in enumerate(columns):
            classes = f'inverse-tone-{g%3}'+(' group-start' if i == 0 else '')+(' inverse-case' if key == "case_id" else '')
            text += f'<th class="{classes}" scope="col" aria-sort="none"><button class="inverse-sort" data-key="{key}" data-numeric="{str(digits is not None).lower()}">{label} <span aria-hidden="true">↕</span></button></th>'
            flat.append((key, digits, classes))
    text += '</tr></thead><tbody>'
    for r in frame.to_dict('records'):
        search = ' '.join(str(r.get(k, '')) for k in ['case_id', 'corridor', 'sensor_uid', 'date', 'period']).lower()
        text += f'<tr data-strategy="{esc(r["strategy"])}" data-search="{esc(search)}" data-bounds="{esc(str(r.get("bounds_profile", "")))}">'
        for key, digits, classes in flat:
            value = r[key]
            raw = '' if pd.isna(value) else str(value)
            display = STRATEGIES.get(value, value) if key == 'strategy' else STATUS.get(value, value) if key == 'solution_status' else value
            if key == 'fd_status' and isinstance(display, str):
                display = display.replace('_', ' ').capitalize()
            display = esc(fmt(display, 2 if digits is None else digits))
            if key == 'case_id':
                display = f'<a href="{esc(folders[value])}/index.html">{display}</a>'
            if key == 'q_inverse_mph' and not r['limit_attained']:
                side = str(r.get('selected_limit_side', ''))
                suffix = '−' if side in ('left', 'below') else '+' if side in ('right', 'above') else '*'
                display += f'<sup title="One-sided rate-boundary limit; use full-precision CSV for calculation">{suffix}</sup>'
            cell_classes = classes + (' bad' if key == 'capacity_change_pct' and abs(value) > 10 else '')
            text += f'<td class="{cell_classes}" data-key="{key}" data-value="{esc(raw)}">{display}</td>'
        text += '</tr>'
    return text+'</tbody></table></div>'


CSS = """
.inverse-diagnostics{margin:0}.inverse-diagnostics section{margin:26px 0}.inverse-diagnostics .inverse-controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;border:1px solid #cbd5e1;border-radius:6px;padding:14px;margin:18px 0}
.inverse-diagnostics select{font:inherit;padding:8px;border:1px solid #94a3b8;border-radius:4px;background:white}.inverse-diagnostics input[type=search]{max-width:520px}
.inverse-diagnostics input[type=search]{font:inherit;padding:9px;border:1px solid #94a3b8;border-radius:4px;width:100%;max-width:420px}.inverse-table{width:max-content;min-width:100%}.inverse-table thead th{position:sticky;z-index:4}.inverse-diagnostics :focus-visible{outline:2px solid #2563eb;outline-offset:2px}
.inverse-scroll{max-height:66vh}.inverse-table .inverse-group-row th{top:0;height:36px;text-align:left;border-left:3px solid #9baec1;white-space:nowrap}
.inverse-table .inverse-column-row th{top:36px;height:76px}.inverse-table th,.inverse-table td{min-width:104px;max-width:250px}.inverse-table td{white-space:nowrap}
.inverse-table .inverse-case{position:sticky;left:0;min-width:70px;max-width:70px;background:#fff;z-index:3}.inverse-table thead .inverse-case{z-index:6;background:#eaf0f6}
.inverse-table td[data-key=fd_status],.inverse-table td[data-key=solution_status]{white-space:normal;min-width:150px;max-width:200px}
.inverse-tone-0{background:#fff}.inverse-tone-1{background:#f2f7fb}.inverse-tone-2{background:#f0f7f4}.inverse-group-row .inverse-tone-0{background:#dfe8f1}.inverse-group-row .inverse-tone-1{background:#dceaf4}.inverse-group-row .inverse-tone-2{background:#dfeee7}
.inverse-sort{border:0;background:none;color:inherit;font:inherit;font-weight:650;text-align:inherit;cursor:pointer;padding:0;width:100%}.inverse-controls label{font-weight:600}.inverse-card-list{display:flex;flex-wrap:wrap;gap:14px}.inverse-card{border:1px solid #cbd5e1;padding:12px 16px;border-radius:6px;min-width:230px;background:#f8fafc}.inverse-card strong{display:block;font-size:20px}.inverse-diagnostics .compact-table{width:100%;min-width:680px;max-width:100%}.inverse-diagnostics .compact-table th{position:static;text-align:left}.inverse-diagnostics .compact-table td,.inverse-diagnostics .compact-table th{min-width:90px;white-space:normal}.inverse-diagnostics .compact-table td:first-child,.inverse-diagnostics .compact-table td:nth-child(2){text-align:left}.inverse-diagnostics .compact-table tr:nth-child(2n) td{background:#f4f8fb}
@media print{.inverse-controls{display:none}.inverse-scroll{max-height:none}.inverse-table thead th,.inverse-table .inverse-case{position:static}}
"""


SCRIPT = """
<script>(()=>{
const root=document.getElementById('inverse-diagnostics'),tables=Array.from(root.querySelectorAll('.inverse-table'));
const search=document.getElementById('inverse-search'),strategy=document.getElementById('inverse-strategy'),bounds=document.getElementById('inverse-bounds');
function filter(){const q=search.value.trim().toLowerCase(),s=strategy.value,b=bounds?bounds.value:'';let n=0;
 tables.forEach((table,j)=>Array.from(table.tBodies[0].rows).forEach(row=>{row.hidden=!(row.dataset.search.includes(q)&&(!s||row.dataset.strategy===s)&&(!row.dataset.bounds||row.dataset.bounds===b));if(j===0&&!row.hidden)n++}));
 document.getElementById('inverse-count').textContent=n+' episode–strategy results';
}
search.addEventListener('input',filter);strategy.addEventListener('change',filter);if(bounds)bounds.addEventListener('change',filter);
tables.forEach(table=>table.querySelectorAll('.inverse-sort').forEach(button=>button.addEventListener('click',()=>{
 const key=button.dataset.key,numeric=button.dataset.numeric==='true',head=button.parentElement,direction=head.getAttribute('aria-sort')==='ascending'?-1:1;
 table.querySelectorAll('.inverse-column-row th').forEach(h=>{h.setAttribute('aria-sort','none');h.querySelector('span').textContent='↕'});
 head.setAttribute('aria-sort',direction===1?'ascending':'descending');button.querySelector('span').textContent=direction===1?'↑':'↓';
 Array.from(table.tBodies[0].rows).sort((a,b)=>{const x=a.querySelector('[data-key="'+key+'"]').dataset.value,y=b.querySelector('[data-key="'+key+'"]').dataset.value;
  if(numeric){const xn=x===''?NaN:Number(x),yn=y===''?NaN:Number(y);if(!Number.isFinite(xn))return Number.isFinite(yn)?1:0;if(!Number.isFinite(yn))return -1;return direction*(xn-yn)}
  if(x==='')return y===''?0:1;if(y==='')return -1;return direction*x.localeCompare(y,undefined,{numeric:true});
 }).forEach(row=>table.tBodies[0].appendChild(row));
})));
filter();
})();</script>
"""



def controls(bounds=False):
    result = '<div class="inverse-controls"><label for="inverse-search">Find an episode</label><input id="inverse-search" type="search" placeholder="Case, corridor, detector or date"><label for="inverse-strategy">Strategy</label><select id="inverse-strategy"><option value="">Both strategies</option><option value="co2_target">CO₂ target</option><option value="balanced_four_pollutants">Balanced four pollutants</option></select>'
    if bounds:
        result += '<label for="inverse-bounds">Wave-speed bounds</label><select id="inverse-bounds"><option value="primary">Primary: 5–20 mph</option><option value="expanded_lower_wave">Expanded: 3–20 mph</option></select>'
    return result+'<span id="inverse-count" aria-live="polite"></span></div>'


def card(title, equations, explanation):
    return '<div class="equation-card"><h3>'+title+'</h3>'+''.join(mathml(k) for k in equations)+'<p>'+explanation+'</p></div>'


def downloads(links):
    return '<nav class="downloads">'+''.join('<a href="'+html.escape(path,quote=True)+'">'+label+'</a>' for path,label in links)+'</nav>'


def page(title, body, active, use_controls=True):
    return render_page(title+' — QVDF-E diagnostics','<div class="inverse-diagnostics" id="inverse-diagnostics"><h1>'+title+'</h1>'+body+'</div>',active,extra_css=CSS,scripts=SCRIPT if use_controls else '')


def inverse_emissions_page(inverse, identity, folders):
    body = '<p class="note">Each strategy selects <strong>one common queue speed for all four pollutants</strong>. CO₂ target matches CO₂ where physically attainable. Balanced four minimizes the mean squared relative error across CO₂, NOₓ, CO and HC with equal weight. Both use O, the recorded-speed emission reference, conditional on the preserved traffic predictions.</p>'
    exact = int((inverse.strategy.eq('co2_target') & inverse.solution_status.eq('exact_root')).sum())
    body += f'<div class="inverse-card-list"><div class="inverse-card"><strong>{exact} / 137</strong>episodes admit an exact CO₂ match</div><div class="inverse-card"><strong>137 episodes × 2 strategies</strong>one queue speed for all four pollutants</div><div class="inverse-card"><strong>Traffic predictions held fixed</strong>demand, length, free speed, mean and peak delay</div></div>'
    body += downloads([('inverse_queue_speed.csv','All inverse results (CSV)'),('inverse_queue_speed_roots.csv','All pollutant roots'),('inverse_queue_speed_candidates.csv','Candidate ledger'),('inverse_queue_speed_equations.json','Assumptions and tolerances')])
    body += '<details open><summary>Equations, units and physical constraint</summary><div class="equations">'
    body += card('Two-speed emission total',['queue_time','free_state_time','two_speed_emission'],'Here q is the candidate queue speed, in mph, rather than traffic flow. State times are hours per vehicle, D is vehicles per lane, and rₚ is grams per vehicle-hour. Mₚ and Oₚ are episode grams per lane. The original speed → VSP → mode lookup supplies the rate; no interpolation smooths its jumps.')
    body += card('Two diagnostic targets',['co2_objective','balanced_objective','normalized_rmse'],'CO₂ uses the smallest absolute relative CO₂ residual. Balanced four minimizes J across the four pollutants within each episode. The displayed normalized RMSE summarizes this four-pollutant balance, not pooled error across episodes.')
    body += card('Physical speed bound',['physical_queue_bound'],'The bound ensures nonnegative free-state time at the fitted peak delay. D, L, free-flow speed, and fitted mean and peak delay stay fixed. These are conditional inverse calculations, not traffic measurements or a refitted QVDF.')
    body += '</div></details><p>Every constant-rate interval is solved separately. A rate-jump crossing is never counted as a root. Ties select the queue speed nearest the current fitted value. A <strong>rate-boundary limit</strong> may only be approached; superscript − or + indicates the approach side. Display rounding can hide the small offset, so use the full-precision CSV for calculation.</p>'
    groups = [identity, ('Queue speed and solution', [('q_fitted_mph','Fitted v<sub>q</sub><br>mph',3), ('q_inverse_mph','Emission-target v<sub>q</sub><br>mph',3), ('q_physical_max_mph','Physical maximum<br>mph',3), ('solution_status','Solution status',None), ('CO2_root_count','CO₂ root count',0)]),
              ('Four-pollutant balance', [('original_normalized_rmse_pct','Original normalized<br>RMSE %',2), ('normalized_rmse_pct','Target normalized<br>RMSE %',2)])]
    groups += [(p+' total error', [('original_'+p+'_ape_pct','Original APE<br>%',2), ('inverse_'+p+'_ape_pct','Target APE<br>%',2), ('inverse_'+p+'_bias_pct','Target bias<br>%',2)]) for p in POLS]
    body += controls()+grouped_table(inverse,groups,'inverse-emission-table',folders)
    body += '<p class="muted">APE is the absolute episode-total error; bias is signed. All results refer to the same fitted sample of 137 episodes. O is an observed-speed calculation, not independently measured emissions.</p>'
    return page('Emission-target queue speed',body,'inverse_emissions')


def inverse_fd_page(inverse, identity, folders):
    body = '<p class="note">For each emission-target queue speed, change <strong>one FD quantity at a time</strong> and hold the other two at their saved values. The current fitted discharge μ₀ is episode demand divided by fitted duration. ω denotes the positive backward-wave-speed magnitude.</p>'
    body += downloads([('inverse_queue_speed.csv','Backward calculations and inverse targets (CSV)'),('inverse_emissions.html','Inspect emission-target queue speeds')])
    body += '<details open><summary>Three calculations and their implications</summary><div class="equations">'
    body += card('1 · Recover discharge',['recover_mu','recover_duration'],'Hold jam density and wave-speed magnitude fixed. Discharge is vehicles/h/lane. Its implied duration generally differs from the original fitted duration, although the FD capacity stays fixed.')
    body += card('2 · Recover wave speed',['recover_wave'],'Hold fitted discharge and jam density fixed. A finite positive wave-speed magnitude exists only when kⱼ₀q is greater than μ₀. Nonpositive or singular solutions are explicitly marked infeasible.')
    body += card('3 · Recover jam density',['recover_density','capacity_closure'],'Hold fitted discharge and wave speed fixed. Jam density is vehicles/mi/lane. The closure equation uses the recovered quantity and the other quantity unchanged; it also evaluates capacity in the wave-speed case.')
    body += '</div></details><p>Speeds are mph and durations are hours. The emission-target speed is defined on the <a href="inverse_emissions.html">inverse-emissions page</a>. Adopting a changed capacity would change the demand-to-capacity ratio and require rechecking the QVDF predictions. These calculations expose consequences; they do not replace any archived result.</p>'
    groups = [identity,
              ('Current FD inputs', [('baseline_mu_vphpl','μ₀<br>veh/h/lane',1), ('baseline_omega_mph','ω₀<br>mph',3), ('baseline_kj_veh_mi_lane','k<sub>j0</sub><br>veh/mi/lane',2)]),
              ('1 · Hold ω and kⱼ', [('mu_case_mu_vphpl','Recovered μ<br>veh/h/lane',1), ('mu_case_mu_change_pct','μ change<br>%',2), ('baseline_P_h','Original fitted P<br>h',3), ('mu_case_implied_P_h','Implied duration<br>h',3)]),
              ('2 · Hold μ and kⱼ', [('omega_case_omega_mph','Recovered ω<br>mph',3), ('omega_case_feasible','Positive finite<br>solution',None), ('omega_case_capacity_vphpl','Implied C<br>veh/h/lane',1), ('omega_case_capacity_change_pct','C change<br>%',2)]),
              ('3 · Hold μ and ω', [('kj_case_kj_veh_mi_lane','Recovered k<sub>j</sub><br>veh/mi/lane',2), ('kj_case_capacity_vphpl','Implied C<br>veh/h/lane',1), ('kj_case_capacity_change_pct','C change<br>%',2)])]
    body += controls()+grouped_table(inverse,groups,'inverse-fd-table',folders)
    return page('Three backward FD calculations',body,'inverse_fd')


def bounds_explanation():
    return '<p class="note">Both exploratory boxes use jam density between <strong>150 and 300 veh/mi/lane</strong>. The primary wave-speed range is <strong>5–20 mph</strong>; the expanded range is <strong>3–20 mph</strong>, because some saved fitted wave speeds fall below 5 mph. These are sensitivity assumptions, not universal limits or traffic-validated estimates.</p>'


def bounded_page(frame, identity, folders):
    body = bounds_explanation()
    body += downloads([('fd_parameter_sensitivity.csv','Primary combinations (CSV)'),('fd_parameter_sensitivity_expanded.csv','Expanded combinations (CSV)'),('fd_summary.html','Compare both bounds in the summary'),('fd_sensitivity_verification.json','Bounds, sources and verification')])
    body += '<details open><summary>Pair selection and capacity consistency</summary><div class="equations">'
    body += card('Hold fitted discharge fixed',['exact_fd_curve'],'Each target queue speed defines a density–wave-speed curve. Intersect this curve with the stated parameter box and the physical speed bound. The lower and upper target-ω columns report the resulting interval when it exists.')
    body += card('Preserve capacity when possible',['capacity_closure','capacity_selection'],'Among pairs that attain the selected speed, first preserve the current capacity if possible; otherwise minimize its absolute change. If the inverse target is outside the box, reoptimize the same emission objective over the attainable speeds, then select the closest-capacity pair.')
    body += '</div></details><p>“Target reachable” means the inverse queue speed is attainable within the box; it does not guarantee an exact emission match. Capacity changes above 10% are highlighted for review, not treated as an acceptance threshold. Select the primary or expanded bounds below; each view has 137 episodes × 2 strategies.</p>'
    groups = [identity,
              ('Target and feasibility', [('q_target_mph','Target v<sub>q</sub><br>mph',3), ('q_selected_mph','Bounded v<sub>q</sub><br>mph',3), ('exact_target_feasible','Target reachable<br>within box',None), ('fd_status','Selection status',None)]),
              ('Bounded FD pair · fitted μ held fixed', [('selected_kj_veh_mi_lane','Candidate k<sub>j</sub><br>veh/mi/lane',2), ('selected_omega_mph','Candidate ω<br>mph',3), ('target_wave_min_mph','Target ω lower<br>mph',3), ('target_wave_max_mph','Target ω upper<br>mph',3)]),
              ('Capacity consistency', [('baseline_C_vphpl','Existing C<br>veh/h/lane',1), ('selected_implied_capacity_vphpl','Candidate C<br>veh/h/lane',1), ('capacity_change_pct','Capacity change<br>%',2), ('baseline_capacity_preserved','Existing capacity<br>preserved',None)])]
    if 'metadata_capacity_vphpl' in frame:
        groups[-1][1].append(('metadata_capacity_vphpl','Metadata C<br>veh/h/lane',1))
    groups += [('Resulting total-emission errors', [('selected_'+p+'_ape_pct',p+' APE<br>%',2) for p in POLS])]
    body += controls(bounds=True)+grouped_table(frame,groups,'bounded-fd-table',folders)
    body += '<p class="muted">These are episode-level diagnostic pairs. Repeated episodes from one detector ultimately require a consistent detector FD. Changed capacity requires a new traffic-calibration check. Network metadata capacity, where available, is only a separate comparator.</p>'
    return page('Bounded density and wave-speed pairs',body,'fd_sensitivity')


def summary_page(summary):
    body = bounds_explanation()
    body += '<p>Each row summarizes <strong>137 episodes</strong> for one strategy and one bound choice. A reachable queue-speed target can still have residual emission error. “Target and original capacity preserved” is a stricter condition than reachability alone.</p>'
    body += downloads([('fd_bound_sensitivity_summary.csv','Summary (CSV)'),('fd_sensitivity.html','Inspect episode-level pairs'),('fd_sensitivity_verification.json','Verification and assumptions')])
    body += '<div class="scroll" tabindex="0" aria-label="FD sensitivity summary"><table class="compact-table" id="fd-summary-table"><thead><tr><th scope="col">Wave-speed bounds</th><th scope="col">Target strategy</th><th scope="col">Target speed reachable</th><th scope="col">Target and original capacity preserved</th><th scope="col">Reoptimized within box</th><th scope="col">Capacity change &gt;10%</th></tr></thead><tbody>'
    for r in summary.to_dict('records'):
        label='5–20 mph' if r['bounds_profile']=='primary' else '3–20 mph'
        body += f'<tr><td>{label}</td><td>{STRATEGIES[r["strategy"]]}</td><td>{r["exact_target_feasible"]} / 137</td><td>{r["exact_target_and_capacity_preserved"]} / 137</td><td>{r["bounded_reoptimized"]} / 137</td><td>{r["selected_capacity_change_above_10pct"]} / 137</td></tr>'
    body += '</tbody></table></div><h2>How to interpret the comparison</h2><p>Balanced four minimizes equal-weight squared relative errors, so large-magnitude CO₂ totals do not dominate by unit scale. CO₂ target gives priority only to CO₂. The bounds restrict physically admissible density–wave-speed combinations while holding fitted discharge fixed.</p>'
    body += '<div class="equations">'+card('Balanced four-pollutant objective',['balanced_objective','normalized_rmse'],'The four-pollutant normalized RMSE applies within each episode. It is distinct from WAPE pooled across episodes.')+card('Capacity check',['exact_fd_curve','capacity_closure'],'Targets that preserve the existing capacity keep the current demand-to-capacity ratio unchanged. This is a diagnostic screening priority, not evidence of an improved traffic calibration.')+'</div>'
    body += '<h2>Context for the exploratory bounds</h2><p><a href="https://www.sciencedirect.com/science/article/abs/pii/S019126150500055X">Laval and Daganzo</a> use an example jam density of 150 veh/mi/lane and a 15 mph backward-wave magnitude. The <a href="https://rosap.ntl.bts.gov/view/dot/40155/dot_40155_DS1.pdf">GDOT I-285 study, Table 5</a> reports 150 veh/km and 20 km/h. Neither example establishes universal limits for the sensitivity box used here.</p>'
    return page('FD sensitivity summary',body,'fd_summary',use_controls=False)


def attach_views(out: Path):
    """Write one offline page per diagnostic table, without changing any CSV."""
    out=Path(out)
    traffic=pd.read_csv(out/'traffic_parameters.csv')
    inverse=pd.read_csv(out/'inverse_queue_speed.csv')
    fd=pd.concat([pd.read_csv(out/'fd_parameter_sensitivity.csv'),pd.read_csv(out/'fd_parameter_sensitivity_expanded.csv')],ignore_index=True)
    summary=pd.read_csv(out/'fd_bound_sensitivity_summary.csv')
    folders=dict(zip(traffic.case_id,traffic.folder))
    for p in POLS:
        inverse['original_'+p+'_ape_pct']=100*abs(inverse['original_M_'+p+'_g']/inverse['O_'+p+'_g']-1)
    inverse['original_normalized_rmse_pct']=100*np.sqrt(inverse.original_balanced_objective)
    inverse['normalized_rmse_pct']=100*np.sqrt(inverse.balanced_objective)
    identity=('Case and strategy',[('case_id','Case',None),('strategy','Target strategy',None)])
    documents={
        'inverse_emissions.html':inverse_emissions_page(inverse,identity,folders),
        'inverse_fd.html':inverse_fd_page(inverse,identity,folders),
        'fd_sensitivity.html':bounded_page(fd,identity,folders),
        'fd_summary.html':summary_page(summary),
    }
    for name,document in documents.items():
        (out/name).write_text(document,encoding='utf-8',newline='\n')
    return list(documents)
