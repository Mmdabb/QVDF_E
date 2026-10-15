"""Error measures and offline HTML views for the preserved episode comparisons."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd
from dashboard_layout import mathml, wrap_document

METHODS = ["S", "R", "M", "A"]
POLS = ["CO2", "NOx", "CO", "HC"]
COLORS = dict(S="#2563EB", R="#7B3294", M="#168C69", A="#A46700")


def error_row(meta, group, quantity, method, actual, predicted, unit, pollutant="", scalar=False):
    """Equal-bin comparisons; signed references use the sum of absolute values."""
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    if actual.shape != predicted.shape or not actual.size or not np.isfinite([actual, predicted]).all():
        raise ValueError(f"Invalid comparison: {meta['case_id']} {quantity} {method}")
    residual = predicted - actual
    denominator = float(np.abs(actual).sum())
    absolute_pct = 100 * float(np.abs(residual).sum()) / denominator if denominator > 0 else np.nan
    return dict(case_id=meta["case_id"], episode_id=meta["episode_id"], group=group,
                pollutant=pollutant, quantity=quantity, method=method, reference="O",
                aggregation="episode_scalar" if scalar else "equal_five_minute_bins",
                n_pairs=len(actual), unit=unit,
                reference_value=float(actual[0]) if scalar else np.nan,
                model_value=float(predicted[0]) if scalar else np.nan,
                reference_mean=float(actual.mean()), model_mean=float(predicted.mean()),
                reference_sum=float(actual.sum()), model_sum=float(predicted.sum()),
                denominator_abs_sum=denominator,
                wape_pct=np.nan if scalar else absolute_pct,
                ape_pct=absolute_pct if scalar else np.nan,
                bias_pct=100*float(residual.sum())/denominator if denominator > 0 else np.nan,
                mae=float(np.abs(residual).mean()), rmse=float(np.sqrt(np.mean(residual**2))))


def calculate_metrics(meta, traffic, emissions, target):
    """Keep scalar calibration targets distinct from binned profile comparisons."""
    series = {m: traffic[traffic.method.eq(m)].sort_values("bin_index") for m in ["O"]+METHODS}
    base = series["O"]
    rows = []
    average = {m: meta["D_veh_per_lane"]*meta["L_mi"]/z.vehicle_hours_per_lane.sum()
               for m, z in series.items()}
    for method in METHODS:
        z = series[method]
        np.testing.assert_array_equal(z.bin_index, base.bin_index)
        np.testing.assert_allclose(z.count_veh_per_lane, base.count_veh_per_lane, rtol=0, atol=0)
        if method != "S":
            for quantity, observed, fitted, unit in [
                ("duration", target.P_h, target.P_hat_h, "h"),
                ("minimum_speed", target.vt2_obs_mph, target.vt2_hat_mph, "mph"),
            ]:
                rows.append(error_row(meta, "traffic", quantity, method, [observed], [fitted], unit, scalar=True))
        rows.append(error_row(meta, "traffic", "average_speed", method,
                              [average["O"]], [average[method]], "mph", scalar=True))
        for quantity, column, scale, unit in [
            ("speed_5min", "equivalent_speed_mph", 1, "mph"),
            ("travel_time_5min", "mean_trip_time_h", 60, "min"),
            ("delay_5min", "mean_delay_h", 60, "min"),
            ("vsp_5min", "exposure_weighted_vsp_kw_t", 1, "kW/t"),
        ]:
            rows.append(error_row(meta, "traffic", quantity, method,
                                  base[column].to_numpy()*scale, z[column].to_numpy()*scale, unit))
    np.testing.assert_allclose(base.equivalent_speed_mph.min(), target.vt2_obs_mph, rtol=1e-12)
    np.testing.assert_allclose(meta["L_mi"]/(meta["Tf_h"]+target.wt2_hat_h), target.vt2_hat_mph, rtol=1e-12)
    for pollutant in POLS:
        groups = {m: emissions[emissions.method.eq(m) & emissions.pollutant.eq(pollutant)].sort_values("bin_index")
                  for m in ["O"]+METHODS}
        for method in METHODS:
            for quantity, column, unit in [
                ("effective_rate_5min", "effective_rate_g_veh_h", "g/vehicle-hour"),
                ("emission_5min", "emission_g_per_lane", "g/lane/bin"),
                ("cumulative_emission", "cumulative_emission_g_per_lane", "g/lane"),
            ]:
                rows.append(error_row(meta, "emission", quantity, method,
                                      groups["O"][column].to_numpy(), groups[method][column].to_numpy(), unit, pollutant))
            rows.append(error_row(meta, "emission", "total_emission", method,
                                  [groups["O"].emission_g_per_lane.sum()],
                                  [groups[method].emission_g_per_lane.sum()], "g/lane", pollutant, scalar=True))
    metrics = pd.DataFrame(rows)
    r_metrics = metrics[metrics.group.eq("traffic") & metrics.method.eq("R")].set_index("quantity")
    for quantity in ["duration", "minimum_speed", "average_speed"]:
        meta[quantity+"_ape_pct"] = float(r_metrics.loc[quantity, "ape_pct"])
        meta["observed_"+quantity] = float(r_metrics.loc[quantity, "reference_value"])
        meta["predicted_"+quantity] = float(r_metrics.loc[quantity, "model_value"])
    for quantity in ["speed_5min", "travel_time_5min", "delay_5min", "vsp_5min"]:
        meta[quantity+"_wape_pct"] = float(r_metrics.loc[quantity, "wape_pct"])
    assert len(metrics) == 90
    return metrics


def fmt(value, signed=False):
    if not np.isfinite(value):
        return "—"
    if abs(value) < .005:
        value = 0.
    return f"{value:+.2f}" if signed else f"{value:.2f}"


CSS = """
*{box-sizing:border-box}body{max-width:1700px;margin:28px auto;padding:0 24px;font:16px/1.55 system-ui,sans-serif;color:#17324d;background:#fff}
a{color:#2563eb}h1{font-size:28px;line-height:1.25}h2{font-size:23px;margin-bottom:8px}h3{font-size:17px;margin:0 0 12px}p{margin:10px 0 16px}
code{overflow-wrap:anywhere}section{margin:36px 0 48px}nav{display:flex;flex-wrap:wrap;gap:9px 20px;margin:18px 0}
.note{background:#f1f5f9;border-left:4px solid #168c69;padding:15px 18px}.muted{color:#52657a;font-size:14px}.comparison{display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:26px;align-items:start}
.chart{min-width:0}.chart img{width:100%;height:auto;display:block}.metrics{min-width:0;overflow-x:auto;border:1px solid #cbd5e1;border-radius:8px;background:#f8fafc;padding:17px}.metrics p{font-size:13px;line-height:1.5;margin:12px 0 3px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:9px 8px;border-bottom:1px solid #d8e0e8;text-align:right;vertical-align:top}th:first-child,td:first-child{text-align:left}th{font-size:13px;line-height:1.4;background:#f1f5f9}td{font-size:14px}.metrics table+table{margin-top:16px}
.metrics td,.metrics th{padding:8px 6px}.metrics th:first-child{width:43%}.subhead{font-size:15px;margin:22px 0 6px}.summary{max-width:920px}.summary td,.summary th{text-align:left}
.metrics details{margin-top:16px;font-size:13px}.metrics summary{cursor:pointer;font-weight:600}.table-wrap{overflow:auto;border:1px solid #cbd5e1;border-radius:7px;max-height:76vh}
.catalog{min-width:1460px}.catalog th{position:sticky;top:0;z-index:2}.catalog th:first-child{left:0;z-index:3}.catalog td:first-child{position:sticky;left:0;background:white;z-index:1}.catalog tr:hover td{background:#eff6ff}.catalog .context{text-align:left;white-space:nowrap}
button.sort{border:0;background:none;color:inherit;font:inherit;font-weight:650;cursor:pointer;text-align:inherit;padding:0;width:100%}button.sort:focus-visible{outline:2px solid #2563eb;outline-offset:3px}
input{font:inherit;padding:11px 13px;width:100%;max-width:780px;border:1px solid #94a3b8;border-radius:5px;margin:8px 0 18px}.count{font-size:14px;color:#52657a;margin-left:14px}
@media(max-width:1280px){.comparison{grid-template-columns:minmax(0,1fr)}.metrics{max-width:650px}.chart img{max-width:1100px}body{padding:0 15px}.catalog{min-width:1400px}}
@media print{.comparison{grid-template-columns:minmax(0,1fr) 310px}.metrics{padding:10px}.metrics td,.metrics th{font-size:10px}nav,input,.count{display:none}section{break-inside:avoid}.table-wrap{max-height:none;overflow:visible}}
"""


def doc_start(title):
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{CSS}</style></head><body>\n')


def matrix(metrics, entries):
    heads = ''.join(f'<th scope="col" style="color:{COLORS[m]}">{m}</th>' for m in METHODS)
    rows = []
    for quantity, label, measure in entries:
        values = []
        for method in METHODS:
            value = metrics[metrics.quantity.eq(quantity) & metrics.method.eq(method)][measure]
            values.append('<td>'+fmt(float(value.iloc[0]), signed=measure == "bias_pct")+'</td>' if len(value) else '<td>—</td>')
        rows.append('<tr><th scope="row">'+label+'</th>'+''.join(values)+'</tr>')
    return '<table><thead><tr><th scope="col">Quantity / error (%)</th>'+heads+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>'


def traffic_tables(metrics):
    metrics = metrics[metrics.group.eq("traffic")]
    rows = []
    for quantity, label in [("duration", "Duration P (h)"), ("minimum_speed", "Minimum speed vₜ₂ (mph)"), ("average_speed", "Average speed (mph)")]:
        group = metrics[metrics.quantity.eq(quantity)].set_index('method')
        reference = float(group.iloc[0].reference_value)
        for field, measure in [('model_value', 'Value'), ('ape_pct', 'APE %')]:
            cells = [fmt(reference) if field == 'model_value' else '—']
            cells += [fmt(float(group.loc[m, field])) if m in group.index else '—' for m in METHODS]
            rows.append('<tr><th scope="row">'+label+'</th><td>'+measure+'</td>'+''.join('<td>'+v+'</td>' for v in cells)+'</tr>')
    for quantity, label in [("speed_5min", "5-min speed"), ("travel_time_5min", "5-min travel time"), ("delay_5min", "5-min delay"), ("vsp_5min", "5-min operating VSP")]:
        group = metrics[metrics.quantity.eq(quantity)].set_index('method')
        cells = ['—']+[fmt(float(group.loc[m, 'wape_pct'])) for m in METHODS]
        rows.append('<tr><th scope="row">'+label+'</th><td>WAPE %</td>'+''.join('<td>'+v+'</td>' for v in cells)+'</tr>')
    heads = '<th scope="col">O</th>'+''.join(f'<th scope="col" style="color:{COLORS[m]}">{m}</th>' for m in METHODS)
    result = '<aside class="metrics" aria-label="Traffic error measures"><h3>Traffic values and errors</h3><p>Fitted episode quantities: R = M = A. Values use the units shown; APE and WAPE are percentages.</p><div class="metric-scroll"><table><thead><tr><th scope="col">Quantity</th><th scope="col">Measure</th>'+heads+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    result += '<p>R/M/A share speed, travel time and delay; M/A share VSP. VSP compares operating-state exposure averages, not VSP evaluated at equivalent speed.</p><p>Average speed = total distance / total vehicle-hours. S matches the observed episode average by construction. The fitted minimum speed is the calibrated peak target, before five-minute averaging.</p><p>Free/queue times and distances have no independent observed-state reference, so no error is assigned to those panels.</p>'
    result += '<details><summary>Metric definitions</summary>'+mathml('wape')+mathml('ape')+mathml('delay')+'<p>Here y<sub>m,i</sub> is the method estimate and y<sub>O,i</sub> the reference in bin i. No additional count weighting is applied. Signed observed delays are retained; a zero denominator is undefined (—). Full MAE, RMSE and signed bias are in the CSV.</p></details></aside>'
    return result


def emission_tables(metrics, pollutant):
    rows = metrics[metrics.group.eq("emission") & metrics.pollutant.eq(pollutant)]
    return ('<aside class="metrics" aria-label="'+pollutant+' error measures"><h3>'+pollutant+' errors against O</h3>'
            + matrix(rows, [("effective_rate_5min", "5-min rate WAPE", "wape_pct"),
                            ("emission_5min", "5-min emission WAPE", "wape_pct"),
                            ("cumulative_emission", "Cumulative path WAPE", "wape_pct"),
                            ("total_emission", "Episode total APE", "ape_pct"),
                            ("total_emission", "Episode total bias", "bias_pct")])
            + '<p>Positive bias means overestimation. Rate and bin-emission WAPE use equal five-minute bins.</p><p>Cumulative-path WAPE uses bin-end cumulative values. It is identical for the time and vehicle axes, which display the same cumulative series; it is not a set of independent emission errors.</p><p>Episode-total APE compares the final sums. It can be smaller than bin-emission WAPE because positive and negative errors can cancel.</p><p>O is the observed-speed calculation reference, not measured tailpipe emissions.</p></aside>')


def page_html(meta, metrics, pollutant=None):
    title = f"{meta['case_id']} · {meta['corridor']} · {meta['date']} · {meta['period']}"
    text = doc_start(title)+'<p><a href="../../index.html">← All episodes</a></p><h1>'+html.escape(title)+'</h1><p><code>'+html.escape(meta['episode_id'])+'</code></p>'
    text += '<p class="note">Common-clock diagnostic: model vehicle groups are assigned to recorded five-minute bins by cumulative-count overlap. The fitted duration may differ from the observed duration. These are comparisons with the observed-speed calculation O, not measured vehicle trajectories. Counts, vehicle-hours and emissions are per lane.</p>'
    text += '<dl class="episode-cards">'+''.join(f'<div><dt>{label}</dt><dd>{value}</dd></div>' for label,value in [('Observed duration',f'{meta["observed_duration_h"]:.3f} h'),('Fitted duration',f'{meta["predicted_duration_h"]:.3f} h'),('Volume',f'{meta["D_veh_per_lane"]:.1f} veh/lane'),('Length',f'{meta["L_mi"]:.3f} mi')])+'</dl>'
    text += '<nav><a href="traffic_timeseries.csv">Traffic CSV</a><a href="emissions_timeseries.csv">Emissions CSV</a><a href="error_metrics.csv">Error metrics CSV</a><a href="node_to_bin_allocation.csv">Count allocation CSV</a></nav>'
    text += '<p class="muted">O: recorded-speed lookup reference · S: single observed average speed · R: reconstructed speed + lookup · M: two speeds + lookup · A: two speeds + cubic rates.</p>'
    if pollutant is None:
        text += '<section><h2>Traffic and operating conditions</h2><div class="comparison"><div class="chart"><a href="traffic_profiles.svg">Editable SVG / full-size figure</a><img src="traffic_profiles.png" alt="Traffic, time-dependent VSP, and two-speed time and distance allocation"></div>'+traffic_tables(metrics)+'</div></section>'
    else:
        assert pollutant in POLS
        p = pollutant
        text += f'<section><h2>{p}: rates, emissions and accumulation</h2><div class="comparison"><div class="chart"><a href="emissions_{p}.svg">Editable SVG / full-size figure</a><img loading="lazy" src="emissions_{p}.png" alt="{p} rate, five-minute emission and cumulative comparisons"></div>'+emission_tables(metrics, p)+'</div></section>'
        text += '<details><summary>Evaluation equations</summary>'+mathml('wape')+mathml('ape')+'<p>Use the same five-minute bins for profile WAPE, and the final episode sum for total APE.</p></details>'
    text += '<style>.episode-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.episode-cards div{border:1px solid #cbd5e1;border-radius:6px;padding:12px 16px;background:#f8fafc}.episode-cards dt{font-size:13px;color:#52657a}.episode-cards dd{margin:4px 0 0;font-size:20px;font-weight:650}.comparison{grid-template-columns:minmax(0,1fr) 500px}.metric-scroll{overflow:auto}.metrics th,.metrics td{min-width:48px}.metrics th:first-child{min-width:125px}.metrics .math-display{font-size:16px}@media(max-width:1500px){.comparison{grid-template-columns:minmax(0,1fr)}.metrics{max-width:850px}}</style>'
    return wrap_document(text+'</body></html>\n', 'episode_'+(pollutant or 'traffic'), prefix='../../', episode={'case_id':meta['case_id'],'title':title})


def index_html(records):
    columns = [("case_id", "Case", False), ("corridor", "Direction", False),
               ("sensor_uid", "Detector/link", False), ("date", "Profile date", False), ("period", "Period", False),
               ("observed_duration_h", "Observed P<br>(h)", True), ("predicted_duration_h", "Fitted P<br>(h)", True),
               ("D_veh_per_lane", "Vehicles<br>/ lane", True),
               ("duration_ape_pct", "P<br>APE %", True), ("minimum_speed_ape_pct", "vₜ₂<br>APE %", True),
               ("speed_5min_wape_pct", "5-min speed<br>WAPE %", True),
               ("average_speed_ape_pct", "Average speed<br>APE %", True),
               ("travel_time_5min_wape_pct", "5-min travel time<br>WAPE %", True),
               ("delay_5min_wape_pct", "5-min delay<br>WAPE %", True)]
    header = ''.join(f'<th scope="col" aria-sort="none"><button class="sort" data-index="{i}" data-numeric="{str(numeric).lower()}">{label} <span aria-hidden="true">↕</span></button></th>' for i, (_, label, numeric) in enumerate(columns))
    rows = []
    for r in records:
        cells = []
        for key, _, numeric in columns:
            value = r[key]
            display = fmt(float(value)) if numeric else html.escape(str(value))
            if key == "case_id":
                display = f'<a href="{html.escape(r["folder"])}/index.html">{display}</a>'
            cells.append(f'<td data-value="{html.escape(str(value))}"'+(' class="context"' if not numeric else '')+'>'+display+'</td>')
        rows.append('<tr>'+''.join(cells)+'</tr>')
    text = doc_start("137 episode time-series comparisons")+'<h1>137 episode time-series comparisons</h1>'
    text += '<p class="note">The six error columns compare the common fitted traffic quantities (R = M = A) with the observed reference. P is episode duration; vₜ₂ is minimum whole-link speed, not the FD queue speed. Open a case for five-method figures and error tables beside each figure group.</p>'
    text += '<p>Scalar duration, minimum speed and episode average speed use <strong>APE</strong>. Five-minute speed, travel time and delay use <strong>WAPE</strong> over matching bins, without additional vehicle-count weighting. Average speed = total distance / total vehicle-hours. Click any column heading to sort.</p>'
    text += '<details><summary>Definitions and interpretation</summary>'+mathml('wape')+mathml('ape')+mathml('average_speed')+mathml('delay')+'<p>Here y<sub>m,i</sub> is the method estimate and y<sub>O,i</sub> the reference in bin i. Observed negative bin delays are retained and the denominator sums absolute values. Undefined percentages display —.</p><p>Model groups are aligned to the observed clock by cumulative vehicle count. Fitted duration remains separate. O uses recorded point speed as a link-speed proxy; these are not measured trajectory errors. Profile dates identify average profiles; Arizona dates label months. Detailed CSVs include signed bias, MAE and RMSE.</p></details>'
    text += '<nav><a href="traffic_parameters.html">Traffic, QVDF and FD parameters / inverse analysis →</a><a href="README.md">Equations and interpretation</a><a href="episode_index.csv">Episode index CSV</a><a href="all_error_metrics.csv">All error metrics CSV</a><a href="all_traffic_timeseries.csv.gz">All traffic CSV (gzip)</a><a href="all_emissions_timeseries.csv.gz">All emissions CSV (gzip)</a></nav>'
    text += '<label for="search">Find an episode</label><br><input id="search" type="search" placeholder="Corridor, detector, date, period or case ID"><span class="count" id="count">137 episodes</span><div class="table-wrap"><table class="catalog"><thead><tr>'+header+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    text += '''<script>
const body=document.querySelector("tbody"), rows=Array.from(body.rows);
document.getElementById("search").addEventListener("input",e=>{
 const q=e.target.value.trim().toLowerCase();let count=0;
 rows.forEach(r=>{r.hidden=!r.textContent.toLowerCase().includes(q);if(!r.hidden)count++});
 document.getElementById("count").textContent=count+" episodes";
});
document.querySelectorAll("button.sort").forEach(button=>button.addEventListener("click",()=>{
 const col=Number(button.dataset.index),numeric=button.dataset.numeric==="true",head=button.parentElement;
 const direction=head.getAttribute("aria-sort")==="ascending"?-1:1;
 document.querySelectorAll("thead th").forEach(h=>{h.setAttribute("aria-sort","none");h.querySelector("span").textContent="↕"});
 head.setAttribute("aria-sort",direction===1?"ascending":"descending");button.querySelector("span").textContent=direction===1?"↑":"↓";
 rows.sort((a,b)=>{const x=a.cells[col].dataset.value,y=b.cells[col].dataset.value;
  if(numeric){const xn=Number(x),yn=Number(y);if(!Number.isFinite(xn))return Number.isFinite(yn)?1:0;if(!Number.isFinite(yn))return -1;return direction*(xn-yn)}
  return direction*x.localeCompare(y,undefined,{numeric:true});
 }).forEach(r=>body.appendChild(r));
}));
</script></body></html>\n'''
    return wrap_document(text, 'index')
