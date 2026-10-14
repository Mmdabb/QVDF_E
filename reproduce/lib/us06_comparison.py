#!/usr/bin/env python3
"""Publication-figure comparisons for EPA US06 model-assigned CO2 emission rates.

Inputs: the uploaded US06 operating states; age-weighted operating-mode emission
rates and passenger-car age distribution; zero-acceleration lookup and cubic data.

The *effect* below is a model counterfactual at the same observed speed, not
measured tailpipe emissions or a physical causal attribution.

The cubic is only plotted/evaluated on its calibrated 5--75 mph speed domain.
The discrete zero-acceleration lookup is reconstructed using MOVES-style
VSP thresholds and the actual age-weighted operating-mode table. It reproduces
all 701 entries in the supplied 5--75 mph plotted lookup file. Its extensions
to speeds outside that domain use the same underlying VSP/mode table rather
than cubic extrapolation.

For a 600-second US06 cycle sampled at t=0,1,...,600, integrate records with
t=1,...,600 as one-second rate assignments. (Dropping the initial record has
no effect on modeled acceleration differences in this data.)
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator

def find_single(data_dir, pattern):
    matches = sorted(data_dir.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f'Expected one file matching {pattern}, found {matches}')
    return matches[0]


def prepare(data_dir:Path, cruise_threshold:float=0.5, *, rate_dir=None, coefficient_file=None):
    rate_dir = data_dir if rate_dir is None else Path(rate_dir)
    coefficient_file = data_dir / "cubic_rate_coefficients.csv" if coefficient_file is None else Path(coefficient_file)
    data = pd.read_csv(data_dir / 'us06_operating_states.csv')
    curve = pd.read_csv(data_dir / 'figS_rates_plotted_values.csv')
    veh = pd.read_csv(find_single(rate_dir,'input_vehicle_type*.csv'))
    rate_input = pd.read_csv(find_single(rate_dir,'input_vehicle_emission_rate*.csv'))
    coeff = pd.read_csv(coefficient_file)
    vp = veh.loc[veh.vehicle_type.eq(1)].iloc[0]  # passenger car
    w = np.array([vp[f'percentage_of_age_{i}'] for i in range(31)],float)
    w /= w.sum()
    co2_col = 'meanBaseRate_CO2_(g/hr)'
    mat = rate_input.loc[rate_input.vehicle_type.eq(1)].pivot(
        index='age',columns='OpModeID',values=co2_col).sort_index()
    rates_kgph = mat.mul(w,axis=0).sum(axis=0)/1000

    v_mps = data.speed_mph.to_numpy(dtype=float)*0.44704
    a_mps2 = data.acceleration_mph_per_s.to_numpy(dtype=float)*0.44704
    A, B, C, M = (float(vp[x]) for x in
                  ['rolling_term_a','rotating_term_b','drag_term_c','source_mass'])
    vsp_at_zero = (A*v_mps+B*v_mps**2+C*v_mps**3)/M
    reconstructed_vsp = vsp_at_zero+v_mps*a_mps2
    assert np.allclose(reconstructed_vsp,data.VSP_kW_per_t,atol=1e-9)
    assert np.allclose(data.CO2_kgph.to_numpy(),
                       data.OpModeID.map(rates_kgph).to_numpy(),atol=1e-8)

    def opmode_without_acceleration(speed_mph,vsp_zero):
        # For the speeds in this cycle, vsp_zero is nonnegative for v>0.
        # MOVES-style modes and VSP cutoffs (kW/t) for the specified vehicle.
        if speed_mph < 1:
            return 1
        if speed_mph < 25:
            if vsp_zero < 0: return 11
            if vsp_zero < 3: return 12
            if vsp_zero < 6: return 13
            if vsp_zero < 9: return 14
            if vsp_zero < 12:return 15
            return 16
        if speed_mph < 50:
            if vsp_zero < 0:return 21
            if vsp_zero < 3:return 22
            if vsp_zero < 6:return 23
            if vsp_zero < 9:return 24
            if vsp_zero < 12:return 25
            if vsp_zero < 18:return 27
            if vsp_zero < 24:return 28
            if vsp_zero < 30:return 29
            return 30
        if vsp_zero < 6:return 33
        if vsp_zero < 12:return 35
        if vsp_zero < 18:return 37
        if vsp_zero < 24:return 38
        if vsp_zero < 30:return 39
        return 40

    reconstructed_curve_v = curve.speed_mph.to_numpy()*0.44704
    reconstructed_curve_vsp = (A*reconstructed_curve_v
                               + B*reconstructed_curve_v**2
                               + C*reconstructed_curve_v**3)/M
    reconstructed_curve_modes = np.array([
        opmode_without_acceleration(v,vs)
        for v,vs in zip(curve.speed_mph,reconstructed_curve_vsp)])
    if not np.array_equal(reconstructed_curve_modes,curve.OpModeID.to_numpy()):
        raise ValueError('Zero-acceleration mode table did not match plotted lookup')
    reconstructed_curve_rates = np.array([rates_kgph[m] for m in reconstructed_curve_modes])
    assert np.allclose(reconstructed_curve_rates,curve.CO2_lookup_gph/1000,atol=1e-8)

    cz=coeff.loc[coeff.pollutant.eq('CO2')].iloc[0]
    def cubic_rate(v):
        return (cz.c0 +cz.c1*v+cz.c2*v**2+cz.c3*v**3)/1000
    assert np.allclose(cubic_rate(curve.speed_mph.to_numpy()),
                       curve.CO2_cubic_gph.to_numpy()/1000,atol=1e-8)

    data['zero_accel_VSP_kW_per_t']=vsp_at_zero
    data['zero_accel_OpModeID']=[
        opmode_without_acceleration(v,vs)
        for v,vs in zip(data.speed_mph.to_numpy(),vsp_at_zero)]
    data['CO2_zero_accel_kgph']=data.zero_accel_OpModeID.map(rates_kgph)
    data['delta_full_minus_zero_kgph']=data.CO2_kgph-data.CO2_zero_accel_kgph
    mask=data.speed_mph.between(cz.speed_min_mph,cz.speed_max_mph)
    data['in_cubic_domain_5to75mph']=mask
    data['CO2_cubic_kgph']=np.where(mask,cubic_rate(data.speed_mph),np.nan)
    data['delta_full_minus_cubic_kgph']=data.CO2_kgph-data.CO2_cubic_kgph
    a=data.acceleration_mph_per_s.to_numpy()
    sp=data.speed_mph.to_numpy()
    data['driving_phase']=np.select(
        [sp<1, a>cruise_threshold,a< -cruise_threshold],
        ['Idle','Accelerating','Decelerating'],default='Cruising')
    # Each observation t=1..600 represents a 1-second interval; t=0 is
    # the initial condition rather than an extra (601st) second of driving.
    data['dt_s']=np.where(data.time_s.gt(0),1.0,0.0)
    return data,curve,cruise_threshold


def summarize(data,threshold):
    rows=[]
    for phase in ['Accelerating','Cruising','Decelerating','Idle']:
        df=data.loc[data.driving_phase.eq(phase)]
        dfc=df.loc[df.in_cubic_domain_5to75mph]
        dt=df.dt_s.to_numpy()
        total_delta_g=(df.delta_full_minus_zero_kgph*df.dt_s).sum()/3.6
        rows.append({
            'driving_phase':phase,
            'n_seconds':int(df.dt_s.sum()),
            'n_records':len(df),
            'n_seconds_5to75mph':int(dfc.dt_s.sum()),
            'mean_full_kgph':df.CO2_kgph.mean(),
            'mean_zero_accel_kgph':df.CO2_zero_accel_kgph.mean(),
            'mean_full_minus_zero_kgph':df.delta_full_minus_zero_kgph.mean(),
            'median_full_minus_zero_kgph':df.delta_full_minus_zero_kgph.median(),
            'MAE_full_minus_zero_kgph':df.delta_full_minus_zero_kgph.abs().mean(),
            'total_full_g':(df.CO2_kgph*df.dt_s).sum()/3.6,
            'total_zero_accel_g':(df.CO2_zero_accel_kgph*df.dt_s).sum()/3.6,
            'total_full_minus_zero_g':total_delta_g,
            'mean_full_minus_cubic_5to75_kgph':dfc.delta_full_minus_cubic_kgph.mean(),
            'total_full_minus_cubic_5to75_g':(dfc.delta_full_minus_cubic_kgph*dfc.dt_s).sum()/3.6,
        })
    out=pd.DataFrame(rows)
    duration=data.loc[data.time_s.gt(0)]
    print('*** VERIFIED LOOKUP: all 701 speed/rate entries match ***')
    print('*** TRIP TOTALS FOR 600 ONE-SECOND INTERVALS ***')
    for col in ['CO2_kgph','CO2_zero_accel_kgph','delta_full_minus_zero_kgph']:
        print(f'{col:36s}',f'{(duration[col]*duration.dt_s).sum()/3.6:.4f} g')
    print('*** BY PHASE ***')
    print(out.to_string(index=False,float_format=lambda x:f'{x:.3f}'))
    print('*** CUBIC DOMAIN 5..75 mph:', int(duration.in_cubic_domain_5to75mph.sum()),'/ 600 intervals ***')
    return out


def style_axes(ax, ylabel=None, xlabel=None, ybounds=None):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y',color=COLORS['grid'],linewidth=0.7,zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlim(0,82)
    ax.set_xticks([0,20,40,60,80])
    if ybounds:ax.set_ylim(*ybounds)
    if ylabel:ax.set_ylabel(ylabel,labelpad=7)
    if xlabel:ax.set_xlabel(xlabel,labelpad=7)
    ax.tick_params(length=3.5, width=0.8)


def make_curves(data,curve,data_dir):
    # The original discrete plotted lookup is used where provided (5--75 mph).
    # For other speeds, create piecewise-constant steps by the known zero-acc
    # states at reference speeds. Verified at 701 table locations 5--75 mph.
    rate_dict=dict(zip(data.zero_accel_OpModeID,data.CO2_zero_accel_kgph))
    # For the plotted 0--82 range, the zero-a operating-mode transitions are:
    #    1 below 1 mph; 12 to 25; 22,23,24 up to 50; 35,37,38 above 50.
    # boundary determination for high-speed 37 -> 38 solves vsp0=18.
    vp=pd.read_csv(find_single(data_dir,'input_vehicle_type*.csv')).query('vehicle_type==1').iloc[0]
    A, B, C, M=[vp[x] for x in ['rolling_term_a','rotating_term_b','drag_term_c','source_mass']]
    def vsp0(mph):
        u=np.asarray(mph)*0.44704
        return (A*u+B*u*u+C*u**3)/M
    x=np.arange(0,82.001,0.005)
    V=vsp0(x)
    op=np.select([x<1,x<25,x<50,x<50], [1,12,22,24],default=38)
    # 25-50 mode groups; >=50 groups for this calibrated speed range.
    op=np.where((x>=25)&(x<50),np.where(V<3,22,np.where(V<6,23,24)),op)
    op=np.where(x>=50,np.where(V<12,35,np.where(V<18,37,38)),op)
    yy=np.array([rate_dict[int(m)] for m in op])
    return x,yy,curve.speed_mph.to_numpy(),curve.CO2_cubic_gph.to_numpy()/1000


def scatter_phase(ax,d,phase,col='left'):
    c=COLORS[phase]
    if phase=='Decelerating':
        normal=d.loc[d.OpModeID.ne(0)]
        brake=d.loc[d.OpModeID.eq(0)]
        yname='CO2_kgph' if col=='left' else 'delta_full_minus_zero_kgph'
        ax.scatter(normal.speed_mph,normal[yname],s=21,alpha=.76,c=c,
                   edgecolors='white',linewidth=.25,zorder=4,rasterized=True)
        ax.scatter(brake.speed_mph,brake[yname],s=28,alpha=.93,
                   marker='D',facecolors='none',edgecolors=c,linewidth=.8,
                   zorder=5,rasterized=True)
    else:
        yname='CO2_kgph' if col=='left' else 'delta_full_minus_zero_kgph'
        ax.scatter(d.speed_mph,d[yname],s=21,alpha=.79,c=c,
                   edgecolors='white',linewidth=.28,zorder=4,rasterized=True)


def panel_label(ax,label):
    ax.text(0.0,1.04,label,transform=ax.transAxes,fontsize=10.9,
            fontweight='bold',va='bottom',ha='left',color=COLORS['Net'])
