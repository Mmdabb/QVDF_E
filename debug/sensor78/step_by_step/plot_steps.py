"""Object-based diagnostic plots for the detector-78 calculation ledger."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

COLORS={"O":"#242B33","S":"#2563EB","R":"#7B3294","M":"#168C69","A":"#E69F00"}
STYLES={"O":"-","S":"--","R":"-","M":"-.","A":":"}
STEPS=("01_raw_day_screening","02_average_weekday","03_selected_window","04_traffic_calculation","05_emission_rates","06_method_calculations","07_common_clock","08_totals_and_errors")


def make_figures(out):
    out=Path(out)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.titlesize":11,"axes.labelsize":10,"axes.spines.top":False,"axes.spines.right":False,"axes.facecolor":"white","figure.facecolor":"white","savefig.facecolor":"white","grid.alpha":.18,"svg.fonttype":"none","svg.hashsalt":"qvdfe-sensor78-steps"})
    def read(step,name):return pd.read_csv(out/STEPS[step-1]/name)
    def finish(fig,step,title):
        fig.suptitle(title,fontsize=14,fontweight="bold")
        for ax in fig.axes:ax.grid(axis="y",alpha=.18)
        fig.savefig(out/STEPS[step-1]/"diagnostic.png",dpi=180)
        fig.savefig(out/STEPS[step-1]/"diagnostic.svg",metadata={"Date":None})
        plt.close(fig)
    def clocks(ax):
        ax.set_xticks(np.arange(15,20));ax.set_xticklabels([f"{i}:00" for i in range(15,20)])
        ax.set_xlim(14.75,19.5)
    d=read(1,"day_decisions.csv")
    fig,ax=plt.subplots(figsize=(9,6.8),layout="constrained")
    yy=np.arange(len(d));color=np.where(d.retained_day,"#2B8C62","#B5BBC3")
    ax.barh(yy,d.row_count,color=color)
    ax.axvline(288,color="#222222",ls="--",lw=1,label="288 required")
    ax.set_yticks(yy);ax.set_yticklabels(d.date);ax.invert_yaxis();ax.set_xlim(0,324)
    for i,r in enumerate(d.itertuples()):ax.text(r.row_count+3,i,f"{r.row_count}",va="center",fontsize=8)
    ax.set_xlabel("Distinct five-minute records in supplied day");ax.set_title("16 complete weekdays retained; five incomplete dates excluded",pad=12)
    ax.legend(loc="lower left",frameon=False)
    finish(fig,1,"Step 1 | Day completeness")

    p=read(2,"average_weekday_arithmetic.csv")
    fig,axs=plt.subplots(2,1,figsize=(9,5.6),sharex=True,layout="constrained")
    axs[0].plot(p.clock_h,p.speed_mph,color=COLORS["O"],lw=1.6)
    axs[1].plot(p.clock_h,p.count_veh_5min,color=COLORS["S"],lw=1.6)
    for ax in axs:ax.axvspan(14.75,19.5,color="#E38B2C",alpha=.13,label="Selected 14:45–19:30 window");ax.set_xlim(0,24)
    axs[0].set_ylabel("Harmonic speed (mph)");axs[0].legend(loc="lower left",frameon=False)
    axs[1].set_ylabel("Mean count (veh/lane/bin)");axs[1].set_xlabel("Time of day");axs[1].set_xticks(np.arange(0,25,3));axs[1].set_xticklabels([f"{i:02}:00" for i in range(0,25,3)])
    finish(fig,2,"Step 2 | Average weekday from 16 complete days")

    z=read(3,"selected_window_arithmetic.csv")
    fig,axs=plt.subplots(3,1,figsize=(9,7.2),sharex=True,layout="constrained")
    for ax,field,label,color in zip(axs,["speed_mph","trip_time_h","vehicle_hours"],["Speed (mph)","Link travel time (min/veh)","Contribution (veh h/lane)"],[COLORS["O"],COLORS["R"],COLORS["S"]]):
        values=z[field]*(60 if field=="trip_time_h" else 1)
        ax.step(np.r_[z.clock_h,19.5],np.r_[values,values.iloc[-1]],where="post",color=color,lw=1.6);ax.set_ylabel(label);clocks(ax)
    axs[-1].set_xlabel("Start of observed five-minute bin")
    finish(fig,3,"Step 3 | Speed → link travel time → vehicle-hours")

    q=read(4,"quadrature_traffic_arithmetic.csv");state=read(4,"traffic_arithmetic.csv").set_index("key").value
    fig,axs=plt.subplots(2,2,figsize=(10,6.8),layout="constrained")
    axs[0,0].plot(q.u,q.delay_h*60,color=COLORS["R"],label="Fitted delay")
    axs[0,0].axhline(state.delay_allowance*60,color="#888888",ls="--",label="Finite-link allowance")
    axs[0,0].set_ylabel("Delay (min/veh)");axs[0,0].legend(frameon=False,fontsize=8,loc="lower center")
    axs[0,1].plot(q.u,q.arrival_factor,color=COLORS["R"]);axs[0,1].axhline(1,color="#888888",ls="--");axs[0,1].set_ylabel("Arrival-rate multiplier")
    axs[1,0].plot(q.u,q.free_time_h*60,color=COLORS["S"],label="Free-flow time")
    axs[1,0].plot(q.u,q.queue_time_h*60,color=COLORS["M"],label="Queue time")
    axs[1,0].set_ylabel("Time allocation (min/veh)");axs[1,0].legend(frameon=False,fontsize=8)
    axs[1,1].plot(q.u,q.speed_mph,color=COLORS["R"],label="Whole-link trip speed")
    ips=read(4,"input_parameters.csv").set_index("key").value
    axs[1,1].axhline(ips.free_speed_mph,color=COLORS["S"],ls="--",label="Free speed")
    axs[1,1].axhline(state.vq,color=COLORS["M"],ls="-.",label="Queue speed")
    axs[1,1].set_ylabel("Speed (mph)");axs[1,1].legend(frameon=False,fontsize=8,loc="center")
    for ax in axs.ravel():ax.set_xlabel("Normalized entry position u");ax.set_xlim(0,1)
    finish(fig,4,"Step 4 | Fitted delay, arrivals and time allocation")

    vehicle=read(5,"vehicle_vsp_inputs.csv").set_index("key").value
    v=np.linspace(.001,75,1501);ms=.44704*v
    zv=(vehicle.rolling_term_a*ms+vehicle.rotating_term_b*ms**2+vehicle.drag_term_c*ms**3)/vehicle.source_mass
    bands=read(5,"positive_speed_rate_bands.csv");bands=bands[bands.pollutant.eq("CO2")].sort_values("speed_lower_mph")
    ids=np.searchsorted(bands.speed_lower_mph,v,side="right")-1
    rr=bands.rate_g_veh_h.to_numpy()[ids]/1000
    sr=read(5,"state_rate_arithmetic.csv");sr=sr[sr.pollutant.eq("CO2")]
    fig,axs=plt.subplots(1,2,figsize=(10,4.8),layout="constrained")
    axs[0].plot(v,zv,color="#666666",lw=1.5);axs[0].set_xlabel("Operating speed (mph)");axs[0].set_ylabel("VSP (kW/tonne)")
    axs[1].plot(zv,rr,color="#666666",lw=1.6);axs[1].set_xlabel("VSP (kW/tonne)");axs[1].set_ylabel("CO₂ lookup rate (kg/veh h)")
    names={"free_speed":("M/A: free state",COLORS["M"]),"queue_speed":("M/A: queue state",COLORS["A"]),"observed_mean_speed":("S: observed mean",COLORS["S"]),"predicted_mean_speed":("Fitted mean",COLORS["R"])}
    for r in sr.itertuples():
        label,color=names[r.state]
        axs[0].scatter(r.speed_mph,r.vsp_kw_tonne,color=color,s=42,label=label,zorder=3)
        axs[1].scatter(r.vsp_kw_tonne,r.lookup_rate_g_veh_h/1000,color=color,s=42,zorder=3)
    axs[0].legend(frameon=False,fontsize=8,loc="upper left")
    axs[0].set_title("Steady speed and level road");axs[1].set_title("Different VSP can select the same rate band")
    finish(fig,5,"Step 5 | VSP calculation and discrete emission-rate selection")

    totals=read(8,"method_totals.csv")
    fig,axs=plt.subplots(2,2,figsize=(9,6.7),layout="constrained")
    for ax,p in zip(axs.ravel(),("CO2","NOx","CO","HC")):
        rows=totals[totals.pollutant.eq(p)].set_index("method").loc[list(COLORS)]
        ax.bar(list(COLORS),rows.signed_error_pct,color=list(COLORS.values()))
        ax.axhline(0,color="#777777",lw=.8);ax.set_title(p.replace("CO2","CO₂").replace("NOx","NOₓ"));ax.set_ylabel("Difference from O (%)")
        for i,r in enumerate(rows.itertuples()):ax.annotate(f"{r.signed_error_pct:+.1f}",(i,r.signed_error_pct),ha="center",va="bottom" if r.signed_error_pct>=0 else "top",xytext=(0,3 if r.signed_error_pct>=0 else -3),textcoords="offset points",fontsize=8)
        lo=min(rows.signed_error_pct.min(),0);hi=max(rows.signed_error_pct.max(),0);pad=max(3,(hi-lo)*.22);ax.set_ylim(lo-pad,hi+pad)
    finish(fig,6,"Step 6 | Five-method episode results relative to the O proxy")

    common=read(7,"common_clock_calculations.csv");vc=read(7,"common_clock_vsp.csv")
    fig,axs=plt.subplots(4,1,figsize=(10,10.5),sharex=True,layout="constrained")
    for m,color in COLORS.items():
        rows=common[common.pollutant.eq("CO2")&common.method.eq(m)];vrows=vc[vc.method.eq(m)]
        for ax,yy in zip(axs,[rows.effective_speed_mph,vrows.exposure_weighted_vsp_kw_tonne,rows.effective_rate_g_veh_h/1000,rows.emission_g/1000]):
            ax.step(np.r_[rows.clock_h,19.5],np.r_[yy,yy.iloc[-1]],where="post",color=color,ls=STYLES[m],lw=1.4 if m!="R" else 2.0,label=m)
    for ax,ylabel in zip(axs,["Equivalent speed (mph)","Time-weighted VSP (kW/t)","Effective CO₂ rate (kg/veh h)","CO₂ contribution (kg/lane/bin)"]):ax.set_ylabel(ylabel);clocks(ax)
    axs[0].legend(ncol=5,frameon=False,loc="lower left",fontsize=9)
    axs[0].set_title("R/M/A equivalent speeds coincide; M/A VSP also coincides",fontsize=10)
    axs[-1].set_xlabel("Observed five-minute bin (count-preserving trip attribution)")
    finish(fig,7,"Step 7 | Speed, operating VSP, effective rate and assigned emissions")

    dc=read(8,"signed_error_components.csv")
    fig,axs=plt.subplots(2,2,figsize=(11,7),layout="constrained")
    stage_colors=[COLORS["S"],"#999999",COLORS["R"],COLORS["M"],COLORS["A"]]
    labels=["O→S","S→S_pred","S_pred→R","R→M","M→A"]
    for ax,p in zip(axs.ravel(),("CO2","NOx","CO","HC")):
        rows=dc[dc.pollutant.eq(p)];y=rows.delta_pct_of_O.to_numpy()
        ax.bar(np.arange(5),y,color=stage_colors);ax.axhline(0,color="#777777",lw=.8)
        ax.set_xticks(np.arange(5));ax.set_xticklabels(labels,rotation=20,ha="right",fontsize=8)
        ax.set_ylabel("Signed contribution (% of O)");ax.set_title(p.replace("CO2","CO₂").replace("NOx","NOₓ"))
        for i,val in enumerate(y):ax.annotate(f"{val:+.1f}",(i,val),ha="center",va="bottom" if val>=0 else "top",xytext=(0,3 if val>=0 else -3),textcoords="offset points",fontsize=8)
        low=min(y.min(),0);high=max(y.max(),0);pad=max(3,(high-low)*.22);ax.set_ylim(low-pad,high+pad)
    finish(fig,8,"Step 8 | Signed differences along the calculation sequence")
