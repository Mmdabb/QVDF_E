"""Readable offline views of emission-target and FD sensitivity calculations."""
from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd

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
                suffix = '−' if side == 'left' else '+' if side == 'right' else '*'
                display += f'<sup title="One-sided rate-boundary limit; use full-precision CSV for calculation">{suffix}</sup>'
            cell_classes = classes + (' bad' if key == 'capacity_change_pct' and abs(value) > 10 else '')
            text += f'<td class="{cell_classes}" data-key="{key}" data-value="{esc(raw)}">{display}</td>'
        text += '</tr>'
    return text+'</tbody></table></div>'


CSS = """
.inverse-diagnostics{margin:40px 0}.inverse-diagnostics section{margin:34px 0}.inverse-diagnostics .inverse-controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;border:1px solid #cbd5e1;border-radius:6px;padding:14px;margin:18px 0}
.inverse-diagnostics select{font:inherit;padding:8px;border:1px solid #94a3b8;border-radius:4px;background:white}.inverse-diagnostics input[type=search]{max-width:520px}
.inverse-scroll{max-height:66vh}.inverse-table .inverse-group-row th{top:0;height:36px;text-align:left;border-left:3px solid #9baec1;white-space:nowrap}
.inverse-table .inverse-column-row th{top:36px;height:76px}.inverse-table th,.inverse-table td{min-width:104px;max-width:250px}.inverse-table td{white-space:nowrap}
.inverse-table .inverse-case{position:sticky;left:0;min-width:70px;max-width:70px;background:#fff;z-index:3}.inverse-table thead .inverse-case{z-index:6;background:#eaf0f6}
.inverse-table td[data-key=fd_status],.inverse-table td[data-key=solution_status]{white-space:normal;min-width:150px;max-width:200px}
.inverse-tone-0{background:#fff}.inverse-tone-1{background:#f2f7fb}.inverse-tone-2{background:#f0f7f4}.inverse-group-row .inverse-tone-0{background:#dfe8f1}.inverse-group-row .inverse-tone-1{background:#dceaf4}.inverse-group-row .inverse-tone-2{background:#dfeee7}
.inverse-sort{border:0;background:none;color:inherit;font:inherit;font-weight:650;text-align:inherit;cursor:pointer;padding:0;width:100%}.inverse-controls label{font-weight:600}.inverse-card-list{display:flex;flex-wrap:wrap;gap:14px}.inverse-card{border:1px solid #cbd5e1;padding:12px 16px;border-radius:6px;min-width:230px;background:#f8fafc}.inverse-card strong{display:block;font-size:20px}.inverse-diagnostics .compact-table{width:auto;min-width:0;max-width:100%}.inverse-diagnostics .compact-table th{position:static}.inverse-diagnostics .compact-table td,.inverse-diagnostics .compact-table th{min-width:90px;white-space:normal}
"""


SCRIPT = """
<script>(()=>{
const root=document.getElementById('inverse-diagnostics'),tables=Array.from(root.querySelectorAll('.inverse-table'));
const search=document.getElementById('inverse-search'),strategy=document.getElementById('inverse-strategy'),bounds=document.getElementById('inverse-bounds');
function filter(){const q=search.value.trim().toLowerCase(),s=strategy.value,b=bounds.value;let n=0;
 tables.forEach((table,j)=>Array.from(table.tBodies[0].rows).forEach(row=>{row.hidden=!(row.dataset.search.includes(q)&&(!s||row.dataset.strategy===s)&&(!row.dataset.bounds||row.dataset.bounds===b));if(j===0&&!row.hidden)n++}));
 document.getElementById('inverse-count').textContent=n+' episode–strategy results';
}
search.addEventListener('input',filter);strategy.addEventListener('change',filter);bounds.addEventListener('change',filter);
const topSearch=document.getElementById('search');if(topSearch)topSearch.addEventListener('input',()=>{search.value=topSearch.value;filter()});
tables.forEach(table=>table.querySelectorAll('.inverse-sort').forEach(button=>button.addEventListener('click',()=>{
 const key=button.dataset.key,numeric=button.dataset.numeric==='true',head=button.parentElement,direction=head.getAttribute('aria-sort')==='ascending'?-1:1;
 table.querySelectorAll('.inverse-column-row th').forEach(h=>{h.setAttribute('aria-sort','none');h.querySelector('span').textContent='↕'});
 head.setAttribute('aria-sort',direction===1?'ascending':'descending');button.querySelector('span').textContent=direction===1?'↑':'↓';
 Array.from(table.tBodies[0].rows).sort((a,b)=>{const x=a.querySelector('[data-key="'+key+'"]').dataset.value,y=b.querySelector('[data-key="'+key+'"]').dataset.value;
  if(numeric){const xn=x===''?NaN:Number(x),yn=y===''?NaN:Number(y);if(!Number.isFinite(xn))return Number.isFinite(yn)?1:0;if(!Number.isFinite(yn))return -1;return direction*(xn-yn)}
  return direction*x.localeCompare(y,undefined,{numeric:true});
 }).forEach(row=>table.tBodies[0].appendChild(row));
})));
filter();
})();</script>
"""


def inverse_sections(out: Path):
    traffic = pd.read_csv(out/'traffic_parameters.csv')
    inverse = pd.read_csv(out/'inverse_queue_speed.csv')
    fd = pd.concat([pd.read_csv(out/'fd_parameter_sensitivity.csv'), pd.read_csv(out/'fd_parameter_sensitivity_expanded.csv')], ignore_index=True)
    folders = dict(zip(traffic.case_id, traffic.folder))
    for p in POLS:
        inverse['original_'+p+'_ape_pct'] = 100*abs(inverse['original_M_'+p+'_g']/inverse['O_'+p+'_g']-1)
    inverse['original_normalized_rmse_pct'] = 100*np.sqrt(inverse.original_balanced_objective)
    inverse['normalized_rmse_pct'] = 100*np.sqrt(inverse.balanced_objective)
    identity = ('Case and strategy', [('case_id','Case',None), ('strategy','Target strategy',None)])
    text = '<style>'+CSS+'</style><div class="inverse-diagnostics" id="inverse-diagnostics"><section id="inverse-emissions"><h2>Queue speed required to match the reference emissions</h2>'
    text += '<p class="note">Each strategy selects <strong>one common queue speed for all four pollutants</strong>. CO₂ target matches CO₂ where physically attainable; Balanced four minimizes the mean squared relative error across CO₂, NOₓ, CO and HC, with equal weight ¼. Both are conditional diagnostics using O as the recorded-speed emission reference.</p>'
    exact = int((inverse.strategy.eq('co2_target') & inverse.solution_status.eq('exact_root')).sum())
    text += f'<div class="inverse-card-list"><div class="inverse-card"><strong>{exact} / 137</strong>episodes admit an exact CO₂ match</div><div class="inverse-card"><strong>2 strategies × 137 episodes</strong>same queue speed used for all pollutants</div><div class="inverse-card"><strong>Traffic predictions held fixed</strong>D, L, v<sub>f</sub>, mean and peak delay</div></div>'
    text += '<details open><summary>Emission objective and physical constraint</summary><div class="equations"><div><h3>Two-speed emission total M</h3><p>t̄<sub>q</sub>(q) = v<sub>f</sub>w̄̂ / (v<sub>f</sub> − q).</p><p>t̄<sub>f</sub>(q) = T<sub>f</sub> − q w̄̂ / (v<sub>f</sub> − q).</p><p>M<sub>p</sub>(q) = D [t̄<sub>f</sub>(q) r<sub>p</sub>(v<sub>f</sub>) + t̄<sub>q</sub>(q) r<sub>p</sub>(q)].</p><p>q denotes the candidate queue speed v<sub>q</sub> here, not traffic flow. The original speed→VSP→mode lookup supplies r<sub>p</sub>.</p></div><div><h3>Two diagnostic targets</h3><p>CO₂: minimize |M<sub>CO₂</sub>(q)/O<sub>CO₂</sub> − 1|.</p><p>Balanced: minimize J(q) = ¼ Σ<sub>p</sub>[M<sub>p</sub>(q)/O<sub>p</sub> − 1]².</p><p>Normalized RMSE = 100 √J (shown below). This is a balance across pollutants within one episode.</p><p>0 &lt; q ≤ L/(T<sub>f</sub> + ŵ<sub>peak</sub>) ensures nonnegative free-state time even at the peak delay.</p></div></div></details>'
    text += '<p>Every lookup interval is solved separately. Rate jumps are retained; a jump crossing is never counted as a root. When multiple solutions tie, the one nearest the current fitted queue speed is selected. A <strong>rate-boundary limit</strong> is approached from one side and may have a nonzero residual. Superscript − or + identifies that side; use full-precision CSV values to reproduce the calculation.</p>'
    text += '<nav><a href="inverse_queue_speed.csv">Both strategies and all backward calculations (CSV)</a><a href="inverse_queue_speed_roots.csv">All pollutant roots</a><a href="inverse_queue_speed_candidates.csv">Candidate ledger</a><a href="inverse_queue_speed_equations.json">Assumptions and tolerances</a></nav>'
    text += '<div class="inverse-controls"><label for="inverse-search">Find an episode</label><input id="inverse-search" type="search" placeholder="Case, corridor, detector or date"><label for="inverse-strategy">Strategy</label><select id="inverse-strategy"><option value="">Both strategies</option><option value="co2_target">CO₂ target</option><option value="balanced_four_pollutants">Balanced four pollutants</option></select><label for="inverse-bounds">FD bounds</label><select id="inverse-bounds"><option value="primary">Primary: 5–20 mph</option><option value="expanded_lower_wave">Expanded: 3–20 mph</option></select><span id="inverse-count" aria-live="polite"></span></div>'
    groups = [identity, ('Queue speed and solution', [('q_fitted_mph','Fitted v<sub>q</sub><br>mph',3), ('q_inverse_mph','Emission-target v<sub>q</sub><br>mph',3), ('q_physical_max_mph','Physical maximum<br>mph',3), ('solution_status','Solution status',None), ('CO2_root_count','CO₂ root count',0)]),
              ('Four-pollutant balance', [('original_normalized_rmse_pct','Original normalized<br>RMSE %',2), ('normalized_rmse_pct','Target normalized<br>RMSE %',2)])]
    groups += [(p+' total error', [('original_'+p+'_ape_pct','Original APE<br>%',2), ('inverse_'+p+'_ape_pct','Target APE<br>%',2), ('inverse_'+p+'_bias_pct','Target bias<br>%',2)]) for p in POLS]
    text += grouped_table(inverse, groups, 'inverse-emission-table', folders)
    text += '</section><section id="backward-fd"><h2>Three backward FD calculations</h2><p>ω is the positive backward-wave-speed magnitude (the γ in your question). Each calculation changes one quantity and holds the other two at their current values. μ₀ = D/P̂ is the fitted episode discharge.</p>'
    text += '<div class="equations"><div><h3>1. Recover discharge</h3><p>μ* = k<sub>j0</sub> q ω₀ / (ω₀ + q).</p><p>Hold k<sub>j0</sub>, ω₀ fixed. The implied duration is P* = D/μ*. This generally differs from P̂; capacity stays fixed.</p></div><div><h3>2. Recover wave speed</h3><p>ω* = μ₀ q / (k<sub>j0</sub> q − μ₀).</p><p>Hold μ₀, k<sub>j0</sub> fixed. A finite positive solution exists only when k<sub>j0</sub> q &gt; μ₀.</p></div><div><h3>3. Recover jam density</h3><p>k<sub>j</sub>* = μ₀/q + μ₀/ω₀.</p><p>Hold μ₀, ω₀ fixed. The new wave/density pair implies C* = v<sub>f</sub>ω*k<sub>j</sub>*/(v<sub>f</sub> + ω*), using whichever quantity changes.</p></div></div>'
    groups = [identity,
              ('Current FD inputs', [('baseline_mu_vphpl','μ₀<br>veh/h/lane',1), ('baseline_omega_mph','ω₀<br>mph',3), ('baseline_kj_veh_mi_lane','k<sub>j0</sub><br>veh/mi/lane',2)]),
              ('1 · Hold ω and kⱼ', [('mu_case_mu_vphpl','Recovered μ<br>veh/h/lane',1), ('mu_case_mu_change_pct','μ change<br>%',2), ('baseline_P_h','Original P̂<br>h',3), ('mu_case_implied_P_h','Implied D/μ*<br>h',3)]),
              ('2 · Hold μ and kⱼ', [('omega_case_omega_mph','Recovered ω<br>mph',3), ('omega_case_feasible','Positive finite<br>solution',None), ('omega_case_capacity_vphpl','Implied C<br>veh/h/lane',1), ('omega_case_capacity_change_pct','C change<br>%',2)]),
              ('3 · Hold μ and ω', [('kj_case_kj_veh_mi_lane','Recovered k<sub>j</sub><br>veh/mi/lane',2), ('kj_case_capacity_vphpl','Implied C<br>veh/h/lane',1), ('kj_case_capacity_change_pct','C change<br>%',2)])]
    text += grouped_table(inverse, groups, 'inverse-fd-table', folders)
    text += '<p class="muted">A recovered μ that changes D/μ does not satisfy the original duration closure. A changed FD capacity changes D/C, so adopting it would require a new check of the QVDF predictions. These rows isolate the implications of each change; no fitted parameter or archived result is replaced.</p></section>'
    text += bounded_section(out, fd, identity, folders)
    return text+'</div>'+SCRIPT


def bounded_section(out, frame, identity, folders):
    text = '<section id="fd-sensitivity"><h2>Bounded combinations of jam density and backward-wave speed</h2>'
    text += '<p class="note">Primary exploratory box: <strong>150 ≤ k<sub>j</sub> ≤ 300 veh/mi/lane</strong> and <strong>5 ≤ ω ≤ 20 mph</strong>. A second run lowers the wave-speed bound to 3 mph because some existing fitted wave speeds lie below 5 mph. These are explicit sensitivity assumptions, not universal limits or traffic-validated parameter estimates.</p>'
    text += '<div class="equations"><div><h3>Keep the current discharge</h3><p>For target q and fixed μ₀, exact pairs satisfy k<sub>j</sub>(ω) = μ₀/q + μ₀/ω.</p><p>The allowable ω interval is the intersection of this relation with the stated parameter box and physical speed bound.</p></div><div><h3>Choose a candidate pair</h3><p>First preserve the existing capacity wherever an exact target pair permits it. Otherwise select the pair with the closest implied capacity within the feasible interval.</p><p>If the target speed cannot be attained within the box, optimize the same emission objective over the attainable speeds. The achieved speed and remaining errors stay visible.</p></div></div>'
    text += '<p>Published examples provide context for the sensitivity box: <a href="https://www.sciencedirect.com/science/article/abs/pii/S019126150500055X">Laval and Daganzo</a> use 150 veh/mi/lane and a 15 mph backward-wave magnitude; the <a href="https://rosap.ntl.bts.gov/view/dot/40155/dot_40155_DS1.pdf">GDOT I-285 study, Table 5</a> reports 150 veh/km and 20 km/h. Neither establishes the limits of this exploratory box.</p>'
    text += '<nav><a href="fd_parameter_sensitivity.csv">Primary bounded combinations (CSV)</a><a href="fd_parameter_sensitivity_expanded.csv">Expanded 3–20 mph run (CSV)</a><a href="fd_bound_sensitivity_summary.csv">Sensitivity summary</a><a href="fd_sensitivity_verification.json">Bounds, sources and verification</a></nav>'
    text += '<p>Use the strategy and FD-bounds controls above to compare the rows. “Target reachable” means the inverse speed is attainable; it does not guarantee an exact emission match. Capacity changes above 10% are highlighted as a review aid, not an acceptance threshold.</p>'
    summary = pd.read_csv(out/'fd_bound_sensitivity_summary.csv')
    text += '<div class="scroll"><table class="compact-table"><thead><tr><th scope="col">Wave-speed bounds</th><th scope="col">Strategy</th><th scope="col">Target speed reachable</th><th scope="col">Target and original capacity preserved</th><th scope="col">Reoptimized within box</th><th scope="col">Capacity change &gt;10%</th></tr></thead><tbody>'
    for r in summary.to_dict('records'):
        bound_label = '5–20 mph' if r['bounds_profile'] == 'primary' else '3–20 mph'
        text += f'<tr><td>{bound_label}</td><td>{STRATEGIES[r["strategy"]]}</td><td>{r["exact_target_feasible"]}/137</td><td>{r["exact_target_and_capacity_preserved"]}/137</td><td>{r["bounded_reoptimized"]}</td><td>{r["selected_capacity_change_above_10pct"]}/137</td></tr>'
    text += '</tbody></table></div>'
    groups = [identity,
              ('Target and feasibility', [('q_target_mph','Target v<sub>q</sub><br>mph',3), ('q_selected_mph','Bounded v<sub>q</sub><br>mph',3), ('exact_target_feasible','Target reachable<br>within box',None), ('fd_status','Selection status',None)]),
              ('Bounded FD pair · current μ held fixed', [('selected_kj_veh_mi_lane','Candidate k<sub>j</sub><br>veh/mi/lane',2), ('selected_omega_mph','Candidate ω<br>mph',3), ('target_wave_min_mph','Target ω lower<br>mph',3), ('target_wave_max_mph','Target ω upper<br>mph',3)]),
              ('Capacity consistency', [('baseline_C_vphpl','Existing C<br>veh/h/lane',1), ('selected_implied_capacity_vphpl','Candidate C<br>veh/h/lane',1), ('capacity_change_pct','Capacity change<br>%',2), ('baseline_capacity_preserved','Existing capacity<br>preserved',None)])]
    if 'metadata_capacity_vphpl' in frame:
        groups[-1][1].append(('metadata_capacity_vphpl','Metadata C<br>veh/h/lane',1))
    groups += [('Resulting total-emission errors', [('selected_'+p+'_ape_pct',p+' APE<br>%',2) for p in POLS])]
    text += grouped_table(frame, groups, 'bounded-fd-table', folders)
    text += '<p><strong>Suggested starting point:</strong> review the balanced four-pollutant candidates that preserve the existing capacity. They balance the emission residuals while keeping μ and D/C unchanged. This is a screening priority, not a replacement calibration.</p><p class="muted">Candidate pairs are episode-level diagnostics. Repeated episodes from the same detector must ultimately be checked with a consistent detector FD. A pair requiring a capacity change also requires re-evaluating the traffic calibration before adoption.</p></section>'
    return text


def attach_views(out: Path):
    path = out/'traffic_parameters.html'
    text = path.read_text(encoding='utf-8')
    marker = '<!-- INVERSE_DIAGNOSTICS -->'
    assert text.count(marker) == 1
    path.write_text(text.replace(marker, inverse_sections(out)),encoding='utf-8',newline='\n')
