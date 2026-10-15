"""Expose preserved traffic targets, QVDF parameters and FD provenance for 137 cases.

Only joins and diagnostic arithmetic are performed; no scientific model is refitted.
The HTML is intended to sit beside the existing step-11 index.html on publication.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dashboard_layout import mathml, wrap_document

ROOT = Path(__file__).resolve().parents[3]
STEP = ROOT / "debug/full_experiment/steps/11_episode_time_series"
FROZEN = ROOT / "data/frozen/calibration/average_weekday"
PARAMS = ["fd", "n", "fp", "s", "theta", "alpha", "beta"]


def safe_output(path):
    out = Path(path).resolve()
    root, working = ROOT.resolve(), (ROOT / "debug/output").resolve()
    if root.is_relative_to(out) or (out.is_relative_to(root) and not out.is_relative_to(working)):
        raise ValueError("Use debug/output/ or an empty external working directory; reference files are protected.")
    marker = out / ".traffic-parameter-page.json"
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not marker.is_file())):
        raise ValueError("Output must be empty or owned by this generator.")
    out.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"owner":"qvdfe-traffic-parameter-page"}\n', encoding="utf-8")
    return out


def ape(observed, fitted):
    return 100 * np.abs(fitted-observed) / np.abs(observed).where(np.abs(observed)>0)


def fmt(value, decimals=2):
    if pd.isna(value):
        return "—"
    if isinstance(value, (bool, np.bool_)):
        return "Yes" if value else "No"
    if isinstance(value, (int, float, np.number)):
        return f"{value:.{decimals}f}"
    return str(value)


GROUPS = [
    ("id", "Episode identifiers", True),
    ("inputs", "Traffic inputs", False),
    ("qvdf", "QVDF: duration and speed", True),
    ("delay", "QVDF: delay", False),
    ("coefficients", "QVDF coefficients", False),
    ("fd", "FD and queue states", True),
    ("fd_support", "FD fit and metadata provenance", False),
]
# key, displayed label (HTML), numeric, decimals
COLUMNS = {
    "id": [("case_id", "Case", False, 0), ("corridor", "Corridor / direction", False, 0),
           ("sensor_uid", "Detector / link", False, 0), ("date", "Profile date", False, 0),
           ("period", "Period", False, 0)],
    "inputs": [("D_veh", "Episode D<br>veh/lane", True, 1), ("x_h", "D/C<br>h", True, 3),
               ("L_mi", "Length L<br>mi", True, 3), ("lanes", "Lanes", True, 0),
               ("vco_mph", "Detection threshold (0.7 v<sub>f</sub>)<br>mph", True, 2),
               ("Tf_min", "Free-flow time<br>min", True, 3),
               ("observed_vehicle_hours_per_lane", "Observed exposure<br>veh·h/lane", True, 2),
               ("predicted_vehicle_hours_per_lane", "Fitted exposure<br>veh·h/lane", True, 2)],
    "qvdf": [("P_h", "P observed<br>h", True, 3), ("P_hat_h", "P fitted<br>h", True, 3),
             ("duration_ape_pct", "P APE<br>%", True, 2),
             ("vt2_obs_mph", "Min. speed observed<br>mph", True, 2),
             ("vt2_hat_mph", "Min. speed fitted<br>mph", True, 2),
             ("minimum_speed_ape_pct", "Min. speed APE<br>%", True, 2),
             ("average_speed_observed_mph", "Average speed observed<br>mph", True, 2),
             ("average_speed_fitted_mph", "Average speed fitted<br>mph", True, 2),
             ("average_speed_ape_pct", "Average speed APE<br>%", True, 2)],
    "delay": [("peak_delay_observed_min", "Peak delay observed<br>min", True, 3),
              ("peak_delay_fitted_min", "Peak delay fitted<br>min", True, 3),
              ("peak_delay_ape_pct", "Peak delay APE<br>%", True, 2),
              ("mean_delay_observed_min", "Mean delay observed<br>min", True, 3),
              ("mean_delay_fitted_min", "Mean delay fitted<br>min", True, 3),
              ("mean_delay_ape_pct", "Mean delay APE<br>%", True, 2),
              ("theta_observed", "Observed mean / peak", True, 4)],
    "coefficients": [("fd", "f<sub>d</sub><br>h<sup>1−n</sup>", True, 4), ("n", "n", True, 4),
                     ("fp", "f<sub>p</sub><br>h<sup>−s</sup>", True, 4), ("s", "s", True, 4),
                     ("theta", "θ", True, 4), ("alpha", "α<br>h<sup>−β</sup>", True, 4),
                     ("beta", "β", True, 4), ("calibration_scope", "Fit scope", False, 0),
                     ("N_train", "Period cases", True, 0), ("N_source", "Fit-source cases", True, 0)],
    "fd": [("C_vphpl", "Capacity used C<br>veh/h/lane", True, 1),
           ("metadata_capacity_vphpl", "Network metadata C<br>veh/h/lane", True, 1),
           ("vf_mph", "Free speed v<sub>f</sub><br>mph", True, 2),
           ("kj", "Jam density k<sub>j</sub><br>veh/mi/lane", True, 0),
           ("kc", "Triangle k<sub>c</sub><br>veh/mi/lane", True, 2),
           ("omega_mph", "Backward-wave magnitude ω<br>mph", True, 3),
           ("mu_vphpl", "Episode D/P<br>veh/h/lane", True, 1),
           ("mu_hat_vphpl", "Fitted D/P̂<br>veh/h/lane", True, 1),
           ("discharge_ape_pct", "Episode-mean flow APE<br>%", True, 2),
           ("vq_mph", "FD-inferred v<sub>q</sub> from D/P<br>mph", True, 2),
           ("vq_hat_mph", "Fitted v̂<sub>q</sub><br>mph", True, 2),
           ("vq_ape_pct", "FD-state v<sub>q</sub> APE<br>%", True, 2),
           ("observed_fd_domain_status", "Observed FD domain", False, 0)],
    "fd_support": [("capacity_source", "Capacity source", False, 0),
                   ("fd_fit_accepted", "S3 fit accepted", False, 0),
                   ("fd_fallback_reason", "Fallback reason", False, 0),
                   ("fd_fit_scope", "FD fit support", False, 0),
                   ("fd_n_fit_pairs", "FD fit pairs", True, 0),
                   ("old_C_vphpl", "Pre-S3 profile q99.5 capacity<br>veh/h/lane", True, 1),
                   ("s3_m", "S3 m", True, 4),
                   ("s3_kc_vpmpl", "S3 k<sub>c</sub><br>veh/mi/lane", True, 2),
                   ("s3_vc_mph", "S3 v<sub>c</sub><br>mph", True, 2),
                   ("fd_flow_r2", "FD flow R²", True, 3),
                   ("fd_speed_r2", "FD speed R²", True, 3),
                   ("network_capacity_vph", "Network metadata total C<br>veh/h", True, 1),
                   ("mu_obs_vphpl", "CBI recovery-window flow<br>veh/h/lane", True, 1),
                   ("is_valid_for_mu", "Recovery-window QC valid", False, 0),
                   ("physical_observed_pass", "Observed finite-link check", False, 0)],
}


def build_html(frame):
    css = """
*{box-sizing:border-box}body{max-width:1800px;margin:28px auto;padding:0 24px;color:#17324d;background:white;font:15px/1.5 system-ui,sans-serif}a{color:#2563eb}h1{font-size:28px;line-height:1.25}h2{font-size:21px}p{margin:10px 0 16px}.note{background:#f1f5f9;border-left:4px solid #168c69;padding:14px 18px}.warning{background:#fff7e5;border-left-color:#c58b12}.muted{color:#52657a;font-size:13px}nav{display:flex;flex-wrap:wrap;gap:12px 22px;margin:18px 0}.controls{padding:14px;border:1px solid #cbd5e1;border-radius:7px;margin:20px 0}.checks{display:flex;flex-wrap:wrap;gap:10px 18px;margin:10px 0}.checks label{white-space:nowrap}input[type=search]{font:inherit;padding:10px;width:100%;max-width:690px;border:1px solid #94a3b8;border-radius:4px}button{cursor:pointer;font:inherit}button.action{padding:5px 10px;background:white;border:1px solid #94a3b8;border-radius:4px;margin:5px 8px 5px 0}button:focus-visible,input:focus-visible{outline:2px solid #2563eb;outline-offset:2px}.count{padding-left:14px;color:#52657a}.scroll{overflow:auto;max-height:74vh;border:1px solid #aebdcd;border-radius:6px}table{border-collapse:separate;border-spacing:0;width:max-content;min-width:100%;font-variant-numeric:tabular-nums}th,td{border-bottom:1px solid #d8e0e8;padding:9px 10px;text-align:right;vertical-align:top;min-width:115px;max-width:220px}td{font-size:13px}thead th{position:sticky;z-index:4;background:#f1f5f9;font-size:12px}.group-row th{top:0;height:36px;padding:8px 10px;text-align:left;white-space:nowrap;background:#dfe8f1;border-left:3px solid #9baec1}.column-row th{top:36px;height:72px}.group-start{border-left:3px solid #9baec1}.text{text-align:left;white-space:nowrap}.sticky-case{position:sticky;left:0;min-width:66px;width:66px;max-width:66px;background:white;z-index:3}.sticky-corridor{position:sticky;left:66px;min-width:125px;width:125px;max-width:125px;background:white;z-index:3}thead .sticky-case,thead .sticky-corridor{z-index:6;background:#eaf0f6}.g-inputs,.g-delay,.g-fd_support{background:#fafcfe}.g-qvdf,.g-coefficients,.g-fd{background:#f4f8fb}tbody tr:hover td{background:#edf5ff}.bad{color:#9a4310;font-weight:600}.sort{border:0;padding:0;background:transparent;color:inherit;font:inherit;font-weight:650;text-align:inherit;width:100%}[hidden]{display:none!important}details{margin:14px 0}summary{cursor:pointer;font-weight:600}.equations{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px 28px}.equations div{border:1px solid #d8e0e8;border-radius:5px;padding:12px 15px}.equations h3{margin:0 0 8px;font-size:16px}.equations p{margin:5px 0}code{overflow-wrap:anywhere}@media(max-width:700px){body{padding:0 12px}.count{display:block;padding:7px 0}.scroll{max-height:70vh}}@media print{.controls{display:none}.scroll{max-height:none;overflow:visible}thead th,.sticky-case,.sticky-corridor{position:static}}
"""
    esc = html.escape
    text = '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Traffic parameters and QVDF comparisons — 137 episodes</title><style>'+css+'</style></head><body>'
    text += '<p><a href="index.html">← All episode comparisons</a></p><h1>Traffic inputs, QVDF comparisons and fundamental diagrams</h1>'
    text += '<p class="note">The same 137 retained average-profile episodes, with the preserved calibration and inputs. Observed means <strong>calculated from the recorded traffic profile</strong>; fitted means the QVDF prediction. Queue speeds in this table are inferred through the triangular FD, not directly measured queue speeds.</p>'
    invalid = int((~frame.observed_fd_domain_valid).sum())
    text += f'<p class="note warning">{invalid} observed episode-mean flows lie outside the strictly congested FD domain (0 &lt; D/P &lt; C). Their algebraic queue-speed values are retained and flagged. A queue-speed percentage error is not reported for those states. The fitted states pass this domain check. Network metadata capacity is available for 117 PeMS cases; it is unavailable for 20 Arizona cases.</p>'
    text += '<nav class="downloads"><a href="traffic_parameters.csv">Download all inputs and comparisons (CSV)</a><a href="traffic_parameter_sources.csv">Source-file inventory</a><a href="traffic_parameter_verification.json">Verification and provenance</a><a href="#equations">Equations and interpretation</a></nav>'
    text += '<div class="controls"><label for="search"><strong>Find an episode</strong></label><br><input id="search" type="search" placeholder="Corridor, detector, profile date, period or case"><span id="count" class="count" aria-live="polite">137 episodes</span><div class="checks" aria-label="Visible column groups">'
    for key,label,default in GROUPS:
        if key != 'id':
            text += f'<label><input class="group-toggle" type="checkbox" data-group="{key}"'+(' checked' if default else '')+f'> {label}</label>'
    text += '</div><button class="action" id="summary-view">Summary view</button><button class="action" id="all-view">Show all columns</button><span class="muted">Identifiers stay visible. Scroll horizontally for additional groups; click a column to sort.</span></div>'
    text += '<div class="scroll" tabindex="0" aria-label="Scrollable traffic parameter table"><table id="traffic-parameter-table"><thead><tr class="group-row">'
    for key,label,default in GROUPS:
        text += f'<th data-group="{key}" colspan="{len(COLUMNS[key])}" scope="colgroup"'+('' if default else ' hidden')+'>'+label+'</th>'
    text += '</tr><tr class="column-row">'
    for key,_,default in GROUPS:
        for j,(field,label,numeric,decimals) in enumerate(COLUMNS[key]):
            classes=['g-'+key]+(['group-start'] if j==0 else [])+(['text'] if not numeric else [])
            if field=='case_id':classes+=['sticky-case']
            if field=='corridor':classes+=['sticky-corridor']
            text += f'<th data-group="{key}" class="{" ".join(classes)}" scope="col" aria-sort="none"'+('' if default else ' hidden')+f'><button class="sort" data-key="{field}" data-numeric="{str(numeric).lower()}">{label} <span aria-hidden="true">↕</span></button></th>'
    text += '</tr></thead><tbody>'
    for r in frame.to_dict('records'):
        search=' '.join(str(r[k]) for k in ['case_id','corridor','sensor_uid','date','period']).lower()
        text += '<tr data-search="'+esc(search)+'">'
        for key,_,default in GROUPS:
            for j,(field,label,numeric,decimals) in enumerate(COLUMNS[key]):
                value=r[field];display=esc(fmt(value,decimals));raw='' if pd.isna(value) else str(value)
                classes=['g-'+key]+(['group-start'] if j==0 else [])+(['text'] if not numeric else [])
                if field=='case_id':
                    classes+=['sticky-case'];display=f'<a href="{esc(r["folder"])}/index.html">{display}</a>'
                if field=='corridor':classes+=['sticky-corridor']
                if field in ['vq_mph','observed_fd_domain_status'] and not r['observed_fd_domain_valid']:classes+=['bad']
                text += f'<td data-group="{key}" data-key="{field}" data-value="{esc(raw)}" class="{" ".join(classes)}"'+('' if default else ' hidden')+'>'+display+'</td>'
        text += '</tr>'
    text += '</tbody></table></div>'
    text += '<section id="equations"><h2>Equations and interpretation</h2><div class="equations">'
    text += '<div class="equation-card"><h3>Observed traffic</h3>'+''.join(mathml(k) for k in ['demand','interval','demand_capacity','free_time','duration','observed_peak','observed_mean','average_speed'])+'<p>Flow q<sub>i</sub> is in vehicles/h/lane. D is in vehicles/lane; x and all times in the equations are hours. H<sub>i</sub> is five-minute vehicle-hours per lane: bin count multiplied by the whole-link travel time L/v<sub>i</sub>. Recorded point speeds are whole-link speed proxies. Delay is not clipped at zero.</p></div>'
    text += '<div class="equation-card"><h3>QVDF predictions</h3>'+''.join(mathml(k) for k in ['predicted_duration','predicted_peak','predicted_mean','predicted_min_speed','predicted_average_speed','alpha','beta','power_delay'])+'<p>A hat denotes a fitted quantity. The final reduced delay equation applies on the power branch. The calibration coefficients are shown in the optional QVDF-coefficients column group.</p></div>'
    text += '<div class="equation-card"><h3>Triangular FD and queue state</h3>'+''.join(mathml(k) for k in ['critical_density','wave','mu_observed','mu_fitted','queue_density','queue_speed'])+'<p>ω is the positive magnitude of the backward wave; its signed propagation speed is −ω. Use fitted μ for the fitted queue state. Jam density k<sub>j</sub> = 220 veh/mi/lane is an assumed closure constant. Neither queue-state speed is an independently measured target.</p></div>'
    text += '<div class="equation-card"><h3>Capacity, S3 and comparison limits</h3><p>C is the accepted detector S3 capacity, or the preserved profile 99.5th-percentile fallback. PeMS network metadata capacity divided by its lane count is a separate comparator.</p><p>S3 k<sub>c</sub> and v<sub>c</sub> describe the empirical S3 fit and differ from the triangular critical density. Pre-S3 capacity is a profile estimate, not network metadata.</p>'+mathml('ape')+'<p>Here y<sub>m</sub> is fitted and y<sub>O</sub> is observed. A zero reference denominator is undefined (—). The separate CBI recovery-window flow is not the episode mean flow used in the queue-state calculation; its QC flag is included only for provenance.</p></div></div>'
    text += '<p class="muted">Parameter fits are by corridor, direction and period, with the saved corridor-wide fallback when period support is insufficient. Fit-source counts refer to the calibration cohort, not just these 137 retained emission cases. Profile dates identify average profiles; Arizona dates label months. These comparisons use fitted sample results, not an out-of-sample validation set.</p></section>'
    text += '''<script>
const parameterTable=document.getElementById("traffic-parameter-table"),tableBody=parameterTable.querySelector("tbody"),rows=Array.from(tableBody.rows),toggles=Array.from(document.querySelectorAll(".group-toggle"));
function applyGroups(){toggles.forEach(t=>parameterTable.querySelectorAll('[data-group="'+t.dataset.group+'"]').forEach(e=>e.hidden=!t.checked))}
toggles.forEach(t=>t.addEventListener("change",applyGroups));
document.getElementById("all-view").addEventListener("click",()=>{toggles.forEach(t=>t.checked=true);applyGroups()});
document.getElementById("summary-view").addEventListener("click",()=>{toggles.forEach(t=>t.checked=["qvdf","fd"].includes(t.dataset.group));applyGroups()});
document.getElementById("search").addEventListener("input",e=>{const q=e.target.value.trim().toLowerCase();let count=0;rows.forEach(r=>{r.hidden=!r.dataset.search.includes(q);if(!r.hidden)count++});document.getElementById("count").textContent=count+" episodes"});
parameterTable.querySelectorAll("button.sort").forEach(button=>button.addEventListener("click",()=>{
 const key=button.dataset.key,numeric=button.dataset.numeric==="true",head=button.parentElement,direction=head.getAttribute("aria-sort")==="ascending"?-1:1;
 parameterTable.querySelectorAll(".column-row th").forEach(h=>{h.setAttribute("aria-sort","none");h.querySelector("span").textContent="↕"});head.setAttribute("aria-sort",direction===1?"ascending":"descending");button.querySelector("span").textContent=direction===1?"↑":"↓";
 rows.sort((a,b)=>{const x=a.querySelector('[data-key="'+key+'"]').dataset.value,y=b.querySelector('[data-key="'+key+'"]').dataset.value;
  if(numeric){const xn=x===""?NaN:Number(x),yn=y===""?NaN:Number(y);if(!Number.isFinite(xn))return Number.isFinite(yn)?1:0;if(!Number.isFinite(yn))return -1;return direction*(xn-yn)}
  if(x==="")return y===""?0:1;if(y==="")return -1;return direction*x.localeCompare(y,undefined,{numeric:true});
 }).forEach(r=>tableBody.appendChild(r));
}));
</script></body></html>\n'''
    # Apply the shared offline shell after the page-specific CSS and controls.
    text = text.replace('.equations div{', '.equations>.equation-card{')
    return wrap_document(text, 'traffic_parameters')


def build(out: Path):
    """Write into a directory already approved/owned by the calling generator."""
    out=Path(out)
    if not out.is_dir():
        raise ValueError("Caller must create and approve the output directory before build(out).")
    paths={
        'episode_index':STEP/'episode_index.csv',
        'episode_results':FROZEN/'episode_results_v2.csv',
        'sensor_parameters':FROZEN/'sensor_parameters.csv',
        'detector_fd_calibration':FROZEN/'detector_fd_calibration.csv',
        'qvdf_parameters':FROZEN/'parameter_card_full.csv',
        'pems_network_metadata':ROOT/'data/inputs/empirical/source_files/pems/pems_link_meta.csv',
    }
    frames={key:pd.read_csv(path) for key,path in paths.items()}
    index=frames['episode_index'];ep=frames['episode_results'];sensor=frames['sensor_parameters'];fd=frames['detector_fd_calibration'];parameters=frames['qvdf_parameters'];metadata=frames['pems_network_metadata']
    selected=ep[ep.matched_ladder_pass]
    assert len(index)==len(selected)==137 and set(index.episode_id)==set(selected.episode_id)
    keep=['case_id','folder','episode_id','observed_vehicle_hours_per_lane','predicted_vehicle_hours_per_lane']
    episode_fields=['episode_id','sensor_uid','sensor','corridor','paper_corridor','dataset','date','period','profile_kind','month','t0','t2','t3','P_h','D_veh','x_h','C_vphpl','vf_mph','vco_mph','L_mi','lanes','Tf_h','wt2_h','wbar_h','theta_observed','vt2_obs_mph','mu_vphpl','mu_obs_vphpl','is_valid_for_mu','kj','omega_mph','vq_mph','kq','observed_bound_h','physical_observed_pass','metadata_capacity_flag','calibration_eligible','calibration_scope']+PARAMS+['P_hat_h','wt2_hat_h','wbar_hat_h','wt2_conditional_hat_h','vt2_hat_mph','mu_hat_vphpl','k_mu','vq_hat_mph','kq_hat','predicted_bound_h','lower_branch','near_capacity','physical_predicted_pass','calibration_split','space_mean_speed_mph','profile_family','profile_shape_a']
    result=index[keep].merge(selected[episode_fields],on='episode_id',validate='one_to_one',sort=False)
    for field in ['C_vphpl','vf_mph','L_mi','lanes','kj','omega_mph']:
        lookup=result.sensor_uid.map(sensor.set_index('sensor_uid')[field])
        np.testing.assert_allclose(result[field],lookup,rtol=1e-12,atol=1e-12)
    sensor_fields=['sensor_uid','kc','capacity_source','vf_source','length_source','s3_m','s3_kc_vpmpl','s3_vc_mph','fd_fit_accepted','fd_fallback_reason']
    result=result.merge(sensor[sensor_fields],on='sensor_uid',validate='many_to_one',sort=False)
    fd_fields=['sensor_uid','old_C_vphpl','old_vf_mph','n_fit_pairs','n_free_branch','n_congested_branch','fit_scope','flow_r2','speed_r2','flow_rmse','speed_rmse','recorded_flow_above_fitted_C_share','candidate_capacity_vphpl','candidate_vf_mph','candidate_kc_vpmpl','candidate_s3_m']
    rename={c:'fd_'+c for c in fd_fields if c not in ['sensor_uid','old_C_vphpl','old_vf_mph']}
    result=result.merge(fd[fd_fields].rename(columns=rename),on='sensor_uid',validate='many_to_one',sort=False)
    parameter_fields=['corridor','period','N_train','N_source','x_min_h','x_max_h','x_median_h','bootstrap_replicates','parameter_CI_scope']+[p+suf for p in PARAMS for suf in ['_lo','_hi']]
    result=result.merge(parameters[parameter_fields],on=['corridor','period'],validate='many_to_one',sort=False).copy()
    result['link_id']=result.sensor.astype(str)
    md=metadata.rename(columns={'lanes':'metadata_lanes','detector_id':'metadata_detector_id','length_mi':'metadata_length_mi','daily_p995_flow_vph':'metadata_daily_p995_flow_vph','daily_p95_speed_mph':'metadata_daily_p95_speed_mph'})
    result=result.merge(md,on=['corridor','link_id'],how='left',validate='many_to_one',sort=False).copy()
    has_metadata=result.network_capacity_vph.notna()
    assert has_metadata.sum()==117 and result.loc[~has_metadata,'corridor'].eq('AZ_I10_W').all()
    np.testing.assert_array_equal(result.loc[has_metadata,'lanes'],result.loc[has_metadata,'metadata_lanes'])
    result['metadata_capacity_vphpl']=result.network_capacity_vph/result.metadata_lanes
    result['metadata_capacity_available']=has_metadata
    result['metadata_capacity_source']=np.where(has_metadata,'released PeMS network metadata','unavailable in supplied Arizona input files')
    result['capacity_difference_from_metadata_pct']=100*(result.C_vphpl/result.metadata_capacity_vphpl-1)
    result['Tf_min']=60*result.Tf_h
    result['peak_delay_observed_min']=60*result.wt2_h;result['peak_delay_fitted_min']=60*result.wt2_hat_h
    result['mean_delay_observed_min']=60*result.wbar_h;result['mean_delay_fitted_min']=60*result.wbar_hat_h
    result['average_speed_observed_mph']=result.D_veh*result.L_mi/result.observed_vehicle_hours_per_lane
    result['average_speed_fitted_mph']=result.L_mi/(result.Tf_h+result.wbar_hat_h)
    for name,obs,fit in [('duration','P_h','P_hat_h'),('peak_delay','wt2_h','wt2_hat_h'),('mean_delay','wbar_h','wbar_hat_h'),('minimum_speed','vt2_obs_mph','vt2_hat_mph'),('average_speed','average_speed_observed_mph','average_speed_fitted_mph'),('discharge','mu_vphpl','mu_hat_vphpl')]:
        result[name+'_ape_pct']=ape(result[obs],result[fit])
        result[name+'_signed_error']=result[fit]-result[obs]
    result['observed_fd_domain_valid']=(result.mu_vphpl.gt(0)&result.mu_vphpl.lt(result.C_vphpl)&result.kq.gt(0)&result.vq_mph.gt(0)&result.vq_mph.lt(result.vf_mph))
    result['fitted_fd_domain_valid']=(result.mu_hat_vphpl.gt(0)&result.mu_hat_vphpl.lt(result.C_vphpl)&result.kq_hat.gt(0)&result.vq_hat_mph.gt(0)&result.vq_hat_mph.lt(result.vf_mph))
    result['observed_fd_domain_status']=np.where(result.observed_fd_domain_valid,'Within congested domain','Outside congested domain')
    result['vq_algebraic_ape_pct']=ape(result.vq_mph,result.vq_hat_mph)
    result['vq_ape_pct']=result.vq_algebraic_ape_pct.where(result.observed_fd_domain_valid & result.fitted_fd_domain_valid)
    checks={
        'x_equals_D_over_C':(result.x_h,result.D_veh/result.C_vphpl),
        'detection_threshold':(result.vco_mph,.7*result.vf_mph),
        'observed_mu_equals_D_over_P':(result.mu_vphpl,result.D_veh/result.P_h),
        'fitted_mu_equals_D_over_P_hat':(result.mu_hat_vphpl,result.D_veh/result.P_hat_h),
        'triangle_critical_density':(result.kc,result.C_vphpl/result.vf_mph),
        'triangle_wave_magnitude':(result.omega_mph,result.C_vphpl/(result.kj-result.kc)),
        'observed_inferred_vq':(result.vq_mph,result.mu_vphpl/(result.kj-result.mu_vphpl/result.omega_mph)),
        'fitted_vq':(result.vq_hat_mph,result.mu_hat_vphpl/(result.kj-result.mu_hat_vphpl/result.omega_mph)),
        'predicted_duration':(result.P_hat_h,np.maximum(result.fd*result.x_h**result.n,result.x_h)),
        'predicted_peak_delay':(result.wt2_hat_h,result.Tf_h*result.fp*result.P_hat_h**result.s),
        'predicted_mean_delay':(result.wbar_hat_h,result.theta*result.wt2_hat_h),
        'predicted_minimum_speed':(result.vt2_hat_mph,result.L_mi/(result.Tf_h+result.wt2_hat_h)),
        'observed_average_speed':(result.average_speed_observed_mph,result.space_mean_speed_mph),
        'predicted_average_speed':(result.average_speed_fitted_mph,result.D_veh*result.L_mi/result.predicted_vehicle_hours_per_lane),
        'alpha':(result.alpha,result.theta*result.fp*result.fd**result.s),
        'beta':(result.beta,result.n*result.s),
    }
    for name,(actual,expected) in checks.items():
        # The aligned node exposure uses quadrature; the QVDF mean delay is analytic.
        tolerance=1e-9 if name=='predicted_average_speed' else 1e-10
        np.testing.assert_allclose(actual,expected,rtol=tolerance,atol=1e-10,err_msg=name)
    assert result.fitted_fd_domain_valid.all()
    # Keep traffic inputs/targets, parameter intervals and joined provenance beyond visible columns.
    result.to_csv(out/'traffic_parameters.csv',index=False,lineterminator='\n')
    (out/'traffic_parameters.html').write_text(build_html(result),encoding='utf-8')
    sources=[]
    for key,path in paths.items():
        sources.append(dict(source_key=key,path=path.relative_to(ROOT).as_posix(),rows=len(frames[key]),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    pd.DataFrame(sources).to_csv(out/'traffic_parameter_sources.csv',index=False,lineterminator='\n')
    audit=dict(episodes=len(result),sensors=int(result.sensor_uid.nunique()),metadata_capacity_episodes=int(has_metadata.sum()),metadata_capacity_missing=int((~has_metadata).sum()),observed_fd_domain_valid=int(result.observed_fd_domain_valid.sum()),observed_fd_domain_invalid=int((~result.observed_fd_domain_valid).sum()),observed_finite_link_pass=int(result.physical_observed_pass.sum()),fitted_fd_domain_valid=int(result.fitted_fd_domain_valid.sum()),fd_fit_accepted_episodes=int(result.fd_fit_accepted.sum()),equation_checks=len(checks),all_checks_passed=True,source_hashes={r['path']:r['sha256'] for r in sources},interpretation={'observed_queue_speed':'FD-inferred from episode mean flow D/P; not directly measured','recovery_discharge':'mu_obs_vphpl is a separate recovery-window diagnostic, not the queue-state discharge','metadata_capacity':'PeMS network total divided by metadata lane count; unavailable for supplied Arizona files','undefined_queue_speed_APE':'Suppressed when either state falls outside the strict congested FD domain; raw algebraic difference remains in vq_algebraic_ape_pct','inverse_analysis':'Not performed; reserved section only'})
    (out/'traffic_parameter_verification.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k not in ['source_hashes','interpretation']},indent=2))
    return audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'debug/output/traffic_parameters')
    args=parser.parse_args()
    build(safe_output(args.output))


if __name__=='__main__':main()
