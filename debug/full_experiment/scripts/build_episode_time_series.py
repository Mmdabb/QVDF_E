"""Count-conserving five-minute comparison for every retained emission episode.

Uses the published intermediate tables from steps 07–09, not a new calibration.
The common observation clock is a diagnostic alignment, not recovered trajectories.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import io
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from episode_dashboard import calculate_metrics, index_html, page_html

ROOT = Path(__file__).resolve().parents[3]
STEPS = ROOT / "debug/full_experiment/steps"
METHODS = ["O", "S", "R", "M", "A"]
POLS = ["CO2", "NOx", "CO", "HC"]
COLORS = dict(O="#242B33", S="#2563EB", R="#7B3294", M="#168C69", A="#E69F00")


def safe_output(path: Path) -> Path:
    out = path.resolve()
    root, working = ROOT.resolve(), (ROOT / "debug/output").resolve()
    if root.is_relative_to(out) or (out.is_relative_to(root) and not out.is_relative_to(working)):
        raise ValueError("Use debug/output/ or a separate working folder, outside reference/source folders.")
    marker = out / ".episode-time-series-trace.json"
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not marker.is_file())):
        raise ValueError("Choose an empty directory or one owned by this generator.")
    out.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"owner":"qvdfe-episode-time-series-trace"}\n', encoding="utf-8")
    return out


def save_csv(frame: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                frame.to_csv(text, index=False, lineterminator="\n")
    else:
        frame.to_csv(path, index=False, lineterminator="\n")


def vsp(speed, params):
    v = np.asarray(speed, float) * params["mph_to_mps"]
    return (params["rolling_term_a"]*v + params["rotating_term_b"]*v*v + params["drag_term_c"]*v*v*v)/params["source_mass"]


def load(name):
    return pd.read_csv(STEPS / name, low_memory=False)


def page_markdown(meta):
    text=f"# {meta['case_id']}: {meta['corridor']}, {meta['date']}, {meta['period']}\n\n"
    text+="[All episodes](../../EPISODES.md) · [Calculation guide](../../README.md) · [Interactive local page](index.html)\n\n"
    text+=f"Original ID: `{meta['episode_id']}`. Observed duration {meta['observed_duration_h']:.3f} h; predicted duration {meta['predicted_duration_h']:.3f} h; {meta['D_veh_per_lane']:.1f} vehicles/lane.\n\n"
    text+="Model vehicle groups are aligned to recorded five-minute bins by cumulative count. This preserves totals and is a diagnostic comparison, not measured trajectories. R/M/A share travel time, delay and equivalent speed; M/A share operating-state VSP.\n\n"
    text+="[Traffic CSV](traffic_timeseries.csv) · [All-pollutant emission CSV](emissions_timeseries.csv) · [Error metrics CSV](error_metrics.csv) · [Allocation CSV](node_to_bin_allocation.csv)\n\n"
    text+="The local HTML dashboard has a separate traffic page and one page per pollutant, each with one results table beside its figure. Use the collapsible sidebar to navigate. Scalar episode targets use APE; five-minute profiles use WAPE against O. Full bias, MAE and RMSE are in the error metrics CSV.\n\n"
    text+="## Traffic\n\n![Traffic and operating-state profiles](traffic_profiles.png)\n\n[Editable SVG](traffic_profiles.svg)\n\n"
    for p in POLS:text+=f"## {p}\n\n![{p} rate, bin emissions and cumulative emissions](emissions_{p}.png)\n\n[Editable SVG](emissions_{p}.svg)\n\n"
    return text.rstrip()+"\n"


def plot_case(args):
    folder, meta = args
    folder=Path(folder)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"axes.titlesize":10,"axes.labelsize":9,"axes.spines.top":False,"axes.spines.right":False,"axes.labelcolor":"#17324D","text.color":"#17324D","axes.edgecolor":"#94A3B8","grid.color":"#E2E8F0","grid.linewidth":.6,"axes.facecolor":"white","figure.facecolor":"white","savefig.facecolor":"white","svg.fonttype":"none","svg.hashsalt":"qvdfe-episode-time-series"})
    traffic=pd.read_csv(folder/"traffic_timeseries.csv",parse_dates=["bin_start","bin_end"])
    emissions=pd.read_csv(folder/"emissions_timeseries.csv",parse_dates=["bin_start","bin_end"])
    ts={m:traffic[traffic.method.eq(m)].sort_values("bin_index") for m in METHODS}
    base=ts["O"]
    starts=mdates.date2num(base.bin_start); edges=np.r_[starts,mdates.date2num(base.bin_end.iloc[-1])]
    n_edges=np.r_[0.,base.cumulative_count_veh_per_lane.to_numpy()]
    label=f"{meta['case_id']} · {meta['corridor']} · {meta['date']} · {meta['period']}"
    subtitle=f"Count-aligned observation clock | observed P={meta['observed_duration_h']:.2f} h; model P={meta['predicted_duration_h']:.2f} h"

    def clock_axis(ax):
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3,maxticks=6))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.set_xlim(edges[0],edges[-1]);ax.set_xlabel("Observed clock time (bin edges)")

    def save(fig,name):
        for ax in fig.axes:ax.grid(alpha=.7);ax.set_axisbelow(True)
        fig.savefig(folder/(name+".png"),dpi=145,bbox_inches="tight")
        fig.savefig(folder/(name+".svg"),bbox_inches="tight",metadata={"Date":None})
        plt.close(fig)

    fig,axes=plt.subplots(3,2,figsize=(10.8,9.0),layout="constrained")
    for ax,column,scale,title,ylabel in [(axes[0,0],"equivalent_speed_mph",1,"Whole-link equivalent speed","Speed (mph)"),(axes[0,1],"mean_trip_time_h",60,"Mean travel time per vehicle","Travel time (min)"),(axes[1,0],"mean_delay_h",60,"Mean delay per vehicle","Delay (min)")]:
        for method in ["O","S","R"]:
            ax.stairs(ts[method][column]*scale,edges,baseline=None,color=COLORS[method],linestyle="--" if method=="S" else "-",linewidth=1.85 if method=="R" else 1.65,label="R = M = A" if method=="R" else method)
        ax.set_title(title,loc="left");ax.set_ylabel(ylabel);clock_axis(ax)
    axes[0,0].axhline(meta["vf_mph"],color="#64748B",linestyle="--",linewidth=1,label="$v_f$")
    axes[0,0].axhline(meta["vq_hat_mph"],color=COLORS["M"],linestyle=":",linewidth=1.1,label=r"$\hat v_q$")
    axes[0,0].legend(loc="best",fontsize=8,ncol=2,framealpha=.9)
    axes[1,0].axhline(0,color="#94A3B8",linewidth=.7)
    ax=axes[1,1]
    for method in ["O","S","R","M"]:ax.stairs(ts[method].exposure_weighted_vsp_kw_t,edges,baseline=None,color=COLORS[method],linestyle="--" if method=="S" else "-",linewidth=1.5,label="M = A" if method=="M" else method)
    ax.set_title("VSP weighted by operating-state exposure",loc="left");ax.set_ylabel("VSP (kW/t)");clock_axis(ax);ax.legend(fontsize=8,ncol=2,framealpha=.9)
    m=ts["M"]
    ax=axes[2,0]
    for column,color,line in [("mean_free_time_h",COLORS["S"],"Free time $t_f$"),("mean_queue_time_h",COLORS["M"],"Queue time $t_q$")]:ax.stairs(m[column]*60,edges,baseline=None,color=color,linewidth=1.7,label=line)
    ax.set_title("Two-speed time allocation (M = A)",loc="left");ax.set_ylabel("Time per vehicle (min)");clock_axis(ax);ax.legend(fontsize=8,framealpha=.9)
    ax=axes[2,1]
    ax.stairs(m.free_distance_mi,edges,baseline=None,color=COLORS["S"],linewidth=1.7,label="$v_f t_f$")
    ax.stairs(m.queue_distance_mi,edges,baseline=None,color=COLORS["M"],linewidth=1.7,label=r"$\hat v_q t_q$")
    ax.axhline(meta["L_mi"],color="#64748B",linestyle="--",linewidth=1,label="Total link length")
    ax.set_title("Two-speed distance allocation (M = A)",loc="left");ax.set_ylabel("Distance per vehicle (mi)");clock_axis(ax);ax.legend(fontsize=8,framealpha=.9)
    fig.suptitle(label+"\n"+subtitle,fontsize=11,fontweight="bold")
    save(fig,"traffic_profiles")
    for p in POLS:
        fig,axes=plt.subplots(2,2,figsize=(10.8,6.8),layout="constrained")
        for method in METHODS:
            z=emissions[emissions.method.eq(method)&emissions.pollutant.eq(p)].sort_values("bin_index")
            color=COLORS[method]
            style="--" if method in ["S","A"] else "-"
            axes[0,0].stairs(z.effective_rate_g_veh_h,edges,baseline=None,color=color,linestyle=style,linewidth=1.7 if method=="R" else 1.4)
            axes[0,1].stairs(z.emission_g_per_lane,edges,baseline=None,color=color,linestyle=style,linewidth=1.7 if method=="R" else 1.4)
            cum=np.r_[0.,z.cumulative_emission_g_per_lane.to_numpy()]
            axes[1,0].plot(edges,cum,color=color,linestyle=style,linewidth=1.7 if method=="R" else 1.5)
            axes[1,1].plot(n_edges,cum,color=color,linestyle=style,linewidth=1.7 if method=="R" else 1.5)
        titles=["Effective emission rate","Assigned emission per five-minute bin","Cumulative emissions versus observed time","Same cumulative emissions versus vehicles"]
        for ax,title in zip(axes.flat,titles):ax.set_title(title,loc="left")
        axes[0,0].set_ylabel("Rate (g/vehicle-hour)");axes[0,1].set_ylabel("Emission (g/lane/bin)")
        axes[1,0].set_ylabel("Cumulative emission (g/lane)");axes[1,1].set_ylabel("Cumulative emission (g/lane)")
        for ax in [axes[0,0],axes[0,1],axes[1,0]]:clock_axis(ax)
        axes[1,1].set_xlabel("Cumulative vehicles per lane");axes[1,1].set_xlim(0,n_edges[-1])
        fig.legend(handles=[Line2D([0],[0],color=COLORS[m],linestyle="--" if m in ["S","A"] else "-",label=m,linewidth=2) for m in METHODS],loc="outside lower center",ncol=5,frameon=False)
        fig.suptitle(label+f" · {p}\n"+subtitle,fontsize=11,fontweight="bold")
        save(fig,"emissions_"+p)
    return meta["case_id"]


def verify_figures(out):
    from PIL import Image
    import xml.etree.ElementTree as ET
    catalog=pd.read_csv(out/"episode_index.csv")
    count=0
    for row in catalog.to_dict("records"):
        folder=out/row["folder"]
        for name in ["traffic_profiles"]+["emissions_"+p for p in POLS]:
            with Image.open(folder/(name+".png")) as im:im.verify()
            if not ET.parse(folder/(name+".svg")).getroot().tag.endswith("svg"):
                raise ValueError("Invalid SVG: "+str(folder/name))
            count+=2
    assert len(catalog)==137 and count==1370
    audit=json.loads((out/"verification.json").read_text())
    audit.update(figures_generated=True,figure_panels=685,figure_files=count,figure_files_verified=True)
    (out/"verification.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    print(f"Verified {count} figure files in {len(catalog)} episodes.",flush=True)


def render_plots(out, workers, start=1, end=None):
    if workers<1:raise ValueError("--workers must be positive")
    audit=json.loads((out/"verification.json").read_text())
    if not audit.get("all_checks_passed") or audit.get("episodes")!=137:
        raise ValueError("Plotting requires a verified complete 137-episode calculation")
    catalog=pd.read_csv(out/"episode_index.csv")
    end=len(catalog) if end is None else end
    if not 1<=start<=end<=len(catalog):raise ValueError("Plot range must be within 1..137, inclusive")
    jobs=[(str(out/r["folder"]),r) for r in catalog.iloc[start-1:end].to_dict("records")]
    if workers==1:
        for job in jobs:print("Plotted "+plot_case(job),flush=True)
    else:
        try:
            pool=ProcessPoolExecutor(max_workers=workers)
        except PermissionError:
            print("Parallel plotting unavailable; using one process.",flush=True)
            for job in jobs:print("Plotted "+plot_case(job),flush=True)
        else:
            with pool:
                for i,case in enumerate(pool.map(plot_case,jobs),1):
                    if i%10==0 or i==len(jobs):print(f"Plotted {i}/{len(jobs)} episodes ({case})",flush=True)
    if start==1 and end==len(catalog):verify_figures(out)
    else:print(f"Finished cases {start}–{end}; full-package status unchanged. Run --verify-figures after all ranges finish.",flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"debug/output/episode_time_series")
    parser.add_argument("--capacity-source",type=Path,default=None,help="Reviewed or regenerated capacity sensitivity directory for its comparison page")
    parser.add_argument("--skip-figures",action="store_true",help="Reproduce all CSVs and numerical checks, without plotting (for CI)")
    parser.add_argument("--plots-only",action="store_true",help="Regenerate figures from an already verified output folder, leaving calculation CSVs unchanged")
    parser.add_argument("--plot-start",type=int,default=1,help="First case to plot, inclusive one-based index; use with --plots-only for disjoint parallel batches")
    parser.add_argument("--plot-end",type=int,help="Last case to plot, inclusive one-based index")
    parser.add_argument("--verify-figures",action="store_true",help="Verify all 685 PNG/SVG pairs and update figure-completion status; no numerical regeneration")
    parser.add_argument("--workers",type=int,default=2,help="Concurrent plotting processes; default 2")
    args=parser.parse_args();out=safe_output(args.output)
    (out/"README.md").write_text((STEPS/"11_episode_time_series/README.md").read_text(encoding="utf-8"),encoding="utf-8")
    if args.verify_figures:
        verify_figures(out)
        return
    if args.plots_only:
        if args.skip_figures:parser.error("--plots-only and --skip-figures are mutually exclusive")
        render_plots(out,args.workers,args.plot_start,args.plot_end)
        return
    observed=load("07_observed_and_single_speed/observed_speed_vsp.csv")
    observed_emission=load("07_observed_and_single_speed/observed_emission_terms.csv")
    single=load("07_observed_and_single_speed/single_speed_vsp.csv")
    single_emission=load("07_observed_and_single_speed/single_speed_emission_terms.csv")
    nodes=load("08_reconstruction_and_two_speed/reconstructed_speed_vsp.csv.gz")
    node_emission=load("08_reconstruction_and_two_speed/node_emission_terms.csv.gz")
    states=load("08_reconstruction_and_two_speed/two_speed_state_vsp.csv")
    totals=load("09_totals_and_comparison/episode_pollutant_calculation_steps.csv")
    source=ROOT/"data/frozen/calibration/average_weekday/episode_results_v2.csv"
    ep=pd.read_csv(source);ep=ep[ep.matched_ladder_pass].sort_values("episode_id")
    assert len(ep)==137 and observed.episode_id.nunique()==137
    parameters=load("06_rate_construction/vsp_input_parameters.csv")
    params=dict(zip(parameters.quantity,parameters.value))
    sources=["07_observed_and_single_speed/observed_speed_vsp.csv","07_observed_and_single_speed/observed_emission_terms.csv","07_observed_and_single_speed/single_speed_vsp.csv","07_observed_and_single_speed/single_speed_emission_terms.csv","08_reconstruction_and_two_speed/reconstructed_speed_vsp.csv.gz","08_reconstruction_and_two_speed/node_emission_terms.csv.gz","08_reconstruction_and_two_speed/two_speed_state_vsp.csv","09_totals_and_comparison/episode_pollutant_calculation_steps.csv","06_rate_construction/vsp_input_parameters.csv"]
    grouped=[{k:g for k,g in frame.groupby("episode_id",sort=False)} for frame in [observed,observed_emission,single,single_emission,nodes,node_emission,states,totals]]
    all_traffic=[];all_emissions=[];all_checks=[];all_metrics=[];index=[];jobs=[]
    for position,r in enumerate(ep.itertuples(index=False),1):
        oid=r.episode_id; obs,oe,ss,se,nd,ne,st,tt=[groups[oid].copy() for groups in grouped]
        obs=obs.sort_values("bin_index");nd=nd.sort_values("node_index")
        count=obs.count_veh.to_numpy();N=nd.vehicle_weight.to_numpy();D=count.sum();L=float(r.L_mi);vf=float(r.vf_mph);vq=float(r.vq_hat_mph);Tf=L/vf
        assert (count>0).all() and (N>0).all()
        edges=np.r_[0.,np.cumsum(count)];nedges=np.r_[0.,np.cumsum(N)];edges[-1]=D;nedges[-1]=D
        overlap=np.maximum(0.,np.minimum(edges[1:,None],nedges[None,1:])-np.maximum(edges[:-1,None],nedges[None,:-1]))
        T=nd.trip_time_h.to_numpy();tf=nd.free_time_h.to_numpy();tq=nd.queue_time_h.to_numpy()
        Hobs=obs.vehicle_hours.to_numpy();Hmodel=overlap@T
        Hsingle=count*float(ss.sum_vehicle_hours.iloc[0])/D
        trip_model=Hmodel/count;w_model=overlap@nd.delay_h.to_numpy()/count
        fmean=overlap@tf/count;qmean=overlap@tq/count
        state=st.set_index("state");zf=float(state.loc["free","vsp_kw_t"]);zq=float(state.loc["queue","vsp_kw_t"])
        zmodel=(overlap@(T*nd.vsp_kw_t.to_numpy()))/Hmodel
        ztwo=(overlap@(tf*zf+tq*zq))/Hmodel
        case_id=f"ep{position:03d}"
        sensor=re.sub(r"[^A-Za-z0-9_-]","_",str(r.sensor_uid).split("::")[-1])
        name=f"{case_id}_{r.corridor}_{sensor}_{str(r.date).replace('-','')}"
        folder=out/"episodes"/name;folder.mkdir(parents=True,exist_ok=True)
        dates=pd.to_datetime(obs.datetime)
        common=dict(case_id=case_id,episode_id=oid,bin_index=obs.bin_index.to_numpy(),bin_start=dates.to_numpy(),bin_end=(dates+pd.Timedelta(minutes=5)).to_numpy(),elapsed_start_h=(dates-pd.Timestamp(r.t0)).dt.total_seconds().to_numpy()/3600,elapsed_end_h=(dates+pd.Timedelta(minutes=5)-pd.Timestamp(r.t0)).dt.total_seconds().to_numpy()/3600,count_veh_per_lane=count,cumulative_count_veh_per_lane=edges[1:])
        traffic=[];emission=[]
        for method in METHODS:
            H=Hobs if method=="O" else Hsingle if method=="S" else Hmodel
            speed=count*L/H;trip=H/count;delay=trip-Tf
            z=obs.vsp_kw_t.to_numpy() if method=="O" else np.full(len(obs),float(ss.vsp_kw_t.iloc[0])) if method=="S" else zmodel if method=="R" else ztwo
            hasstates=method in ["M","A"]
            tr=pd.DataFrame({**common,"method":method,"L_mi":L,"vf_mph":vf,"vq_hat_mph":vq,"Tf_h":Tf,"observed_duration_h":r.P_h,"predicted_duration_h":r.P_hat_h,"vehicle_hours_per_lane":H,"mean_trip_time_h":trip,"mean_delay_h":delay,"equivalent_speed_mph":speed,"exposure_weighted_vsp_kw_t":z,"vsp_at_equivalent_speed_kw_t":vsp(speed,params),"two_speed_state_times_used":hasstates,"mean_free_time_h":fmean if hasstates else np.nan,"mean_queue_time_h":qmean if hasstates else np.nan,"free_distance_mi":vf*fmean if hasstates else np.nan,"queue_distance_mi":vq*qmean if hasstates else np.nan,"two_speed_time_weighted_speed_mph":(vf*fmean+vq*qmean)/(fmean+qmean) if hasstates else np.nan})
            traffic.append(tr)
            for p in POLS:
                if method=="O":
                    E=oe[oe.pollutant.eq(p)].sort_values("bin_index").emission_g.to_numpy();native=float(E.sum())
                    Efree=Equeue=np.full(len(obs),np.nan)
                elif method=="S":
                    native=float(se.loc[se.pollutant.eq(p),"emission_g"].iloc[0]);E=count*native/D
                    Efree=Equeue=np.full(len(obs),np.nan)
                else:
                    values=ne[ne.pollutant.eq(p)].sort_values("node_index")
                    if method=="R":en=values.R_g.to_numpy();Efree=Equeue=np.full(len(obs),np.nan)
                    else:
                        en=values[method+"_free_g"].to_numpy()+values[method+"_queue_g"].to_numpy()
                        Efree=overlap@(values[method+"_free_g"].to_numpy()/N);Equeue=overlap@(values[method+"_queue_g"].to_numpy()/N)
                    native=float(en.sum());E=overlap@(en/N)
                archived=float(tt.loc[tt.pollutant.eq(p),method+"_g"].iloc[0])
                np.testing.assert_allclose(E.sum(),native,rtol=1e-10,atol=1e-8)
                np.testing.assert_allclose(E.sum(),archived,rtol=1e-9,atol=1e-8)
                emission.append(pd.DataFrame({**common,"method":method,"pollutant":p,"vehicle_hours_per_lane":H,"effective_rate_g_veh_h":E/H,"emission_g_per_lane":E,"free_state_emission_g_per_lane":Efree,"queue_state_emission_g_per_lane":Equeue,"cumulative_emission_g_per_lane":np.cumsum(E)}))
                all_checks.append(dict(case_id=case_id,episode_id=oid,method=method,pollutant=p,aligned_total_g=float(E.sum()),native_discrete_total_g=native,archived_episode_total_g=archived,aligned_minus_native_g=float(E.sum()-native),aligned_minus_archived_g=float(E.sum()-archived),relative_difference_from_archived=float((E.sum()-archived)/archived)))
        traffic=pd.concat(traffic,ignore_index=True);emission=pd.concat(emission,ignore_index=True)
        np.testing.assert_allclose(overlap.sum(axis=1),count,rtol=1e-10,atol=1e-9)
        np.testing.assert_allclose(overlap.sum(axis=0),N,rtol=1e-10,atol=1e-9)
        np.testing.assert_allclose(vf*fmean+vq*qmean,L,rtol=1e-10,atol=1e-10)
        np.testing.assert_allclose(fmean+qmean,trip_model,rtol=1e-10,atol=1e-12)
        np.testing.assert_allclose(Tf+w_model,trip_model,rtol=1e-10,atol=1e-12)
        np.testing.assert_allclose(Hmodel.sum(),D*(Tf+r.wbar_hat_h),rtol=1e-9,atol=1e-9)
        np.testing.assert_allclose(np.sum(Hmodel*zmodel),np.sum(N*T*nd.vsp_kw_t),rtol=1e-10,atol=1e-9)
        np.testing.assert_allclose(np.sum(Hmodel*ztwo),np.sum(N*(tf*zf+tq*zq)),rtol=1e-10,atol=1e-9)
        save_csv(traffic,folder/"traffic_timeseries.csv");save_csv(emission,folder/"emissions_timeseries.csv")
        ij=np.argwhere(overlap>0)
        save_csv(pd.DataFrame({"bin_index":ij[:,0]+1,"node_index":ij[:,1]+1,"overlap_count_veh_per_lane":overlap[ij[:,0],ij[:,1]],"fraction_of_node":overlap[ij[:,0],ij[:,1]]/N[ij[:,1]]}),folder/"node_to_bin_allocation.csv")
        record=dict(case_id=case_id,folder=f"episodes/{name}",episode_id=oid,corridor=r.corridor,paper_corridor=r.paper_corridor,sensor_uid=r.sensor_uid,date=r.date,period=r.period,bin_start=str(dates.iloc[0]),bin_end=str(dates.iloc[-1]+pd.Timedelta(minutes=5)),observed_bins=len(obs),model_nodes=len(nd),observed_duration_h=float(r.P_h),predicted_duration_h=float(r.P_hat_h),D_veh_per_lane=float(D),L_mi=L,vf_mph=vf,vq_hat_mph=vq,Tf_h=Tf,observed_vehicle_hours_per_lane=float(Hobs.sum()),predicted_vehicle_hours_per_lane=float(Hmodel.sum()),minimum_aligned_free_time_s=float(fmean.min()*3600),maximum_count_residual_veh=float(np.max(abs(overlap.sum(axis=1)-count))),maximum_distance_residual_mi=float(np.max(abs(vf*fmean+vq*qmean-L))),maximum_time_residual_h=float(np.max(abs(fmean+qmean-trip_model))),maximum_average_speed_residual_mph=float(np.max(abs((vf*fmean+vq*qmean)/(fmean+qmean)-L/trip_model))))
        metrics=calculate_metrics(record,traffic,emission,r)
        save_csv(metrics,folder/"error_metrics.csv");all_metrics.append(metrics)
        index.append(record);(folder/"index.html").write_text(page_html(record,metrics),encoding="utf-8")
        for pollutant in POLS:
            (folder/f"emissions_{pollutant}.html").write_text(page_html(record,metrics,pollutant),encoding="utf-8")
        (folder/"README.md").write_text(page_markdown(record),encoding="utf-8")
        all_traffic.append(traffic);all_emissions.append(emission);jobs.append((str(folder),record))
    save_csv(pd.concat(all_traffic,ignore_index=True),out/"all_traffic_timeseries.csv.gz")
    save_csv(pd.concat(all_emissions,ignore_index=True),out/"all_emissions_timeseries.csv.gz")
    save_csv(pd.concat(all_metrics,ignore_index=True),out/"all_error_metrics.csv")
    checks=pd.DataFrame(all_checks);catalog=pd.DataFrame(index)
    save_csv(checks,out/"total_reconciliation.csv");save_csv(catalog,out/"episode_index.csv")
    audit=dict(episodes=len(catalog),observed_bins=int(catalog.observed_bins.sum()),traffic_rows=sum(len(f) for f in all_traffic),emission_rows=sum(len(f) for f in all_emissions),method_pollutant_totals=len(checks),max_relative_difference_from_archived=float(checks.relative_difference_from_archived.abs().max()),max_aligned_minus_native_g=float(checks.aligned_minus_native_g.abs().max()),max_count_residual_veh=float(catalog.maximum_count_residual_veh.max()),max_distance_residual_mi=float(catalog.maximum_distance_residual_mi.max()),max_time_residual_h=float(catalog.maximum_time_residual_h.max()),max_average_speed_residual_mph=float(catalog.maximum_average_speed_residual_mph.max()),all_checks_passed=True,alignment="Cumulative-count overlap onto observed five-minute bin starts/ends; model duration retained as metadata, not forced equal.",figures_generated=False,input_sha256={str((STEPS/name).relative_to(ROOT)).replace('\\','/'):hashlib.sha256((STEPS/name).read_bytes()).hexdigest() for name in sources})
    audit["input_sha256"][str(source.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(source.read_bytes()).hexdigest()
    audit["error_metric_rows"]=sum(len(f) for f in all_metrics)
    audit["error_metric_reference"]="O; equal-bin WAPE with sum(abs(O)) denominator; episode-scalar APE; L/vf delay baseline"
    (out/"verification.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    (out/"index.html").write_text(index_html(index),encoding="utf-8")
    md="# All 137 episode comparisons\n\nSelect a case to view its figures and calculation CSVs directly in GitHub. For filtering, open [the HTML browser](index.html) locally. See the [calculation guide](README.md) for equations and alignment assumptions. Durations are hours; counts are vehicles per lane.\n\n| Case | Direction | Detector/link | Date | Period | Observed P | Predicted P | Vehicles |\n|---|---|---|---|---|---:|---:|---:|\n"
    for r in index:md+=f"| [{r['case_id']}]({r['folder']}/README.md) | {r['corridor']} | {r['sensor_uid']} | {r['date']} | {r['period']} | {r['observed_duration_h']:.2f} | {r['predicted_duration_h']:.2f} | {r['D_veh_per_lane']:.1f} |\n"
    (out/"EPISODES.md").write_text(md,encoding="utf-8")
    from build_parameter_diagnostics import build as build_parameter_diagnostics
    build_parameter_diagnostics(out,args.capacity_source)
    print(json.dumps(audit,indent=2),flush=True)
    if not args.skip_figures:render_plots(out,args.workers,args.plot_start,args.plot_end)


if __name__=="__main__":main()
