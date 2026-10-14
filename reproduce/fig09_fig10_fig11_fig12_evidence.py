# Reproduction entry; reads the frozen inputs through qvdfe.paths and writes to reproduce/output.
"""Figs. 9-12 from the complete, audited episode tables.

No raster artwork or hand-positioned empirical data are used.  The figure audit
records each mask and source checksum so omitted states remain inspectable.
"""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent / 'lib'))  # reproduce/lib
from _paths import ROOT as _ROOT, FROZEN as _FROZEN, OUT as _OUT  # noqa: E402
from pathlib import Path
import argparse
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from figure_style import style, panel, save_figure, BLUE, ORANGE, TEAL, PURPLE, INK, GRAY, MUTED, GRID, LIGHT, WHITE
from figure_style import clean, identity, QA

HERE = Path(__file__).resolve().parent
ROOT = _ROOT
DEST = _OUT / 'figs'
POLS = ['CO2', 'NOx', 'CO', 'HC']
POL_LABELS = {'CO2': r'CO$_2$', 'NOx': r'NO$_x$', 'CO': 'CO', 'HC': 'HC'}


def bool_column(frame, column):
    values = frame[column]
    if values.dtype == bool:
        return values.fillna(False)
    return values.astype(str).str.lower().isin(['true', '1'])


def finite(frame, columns):
    return np.isfinite(frame[columns].to_numpy(float)).all(axis=1)


def groups(frame):
    az = frame.corridor.eq('AZ_I10_W')
    return [(az, INK, 'o', 'AZ average weekdays'),
            (~az, TEAL, 's', 'PeMS average weekdays')]


def source_audit(data):
    source = data / 'episode_results_v2.csv'
    return {'source': str(source.relative_to(ROOT)), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'track': 'average_weekday', 'points_are_actual_episode_rows': True,
            'representative_median_curve': False}


def write_audit(stem, report):
    (QA / f'{stem}_data_audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


def paired_points(ax, frame, x, y):
    for mask, color, marker, label in groups(frame):
        ax.scatter(frame.loc[mask, x], frame.loc[mask, y], s=18, marker=marker,
                   facecolors='none', edgecolors=color, linewidths=.7, alpha=.62, label=label)
    identity(ax, frame[x], frame[y])


def fig5(data):
    frame = pd.read_csv(data / 'episode_results_v2.csv')
    mask = (bool_column(frame, 'calibration_eligible') &
            bool_column(frame, 'physical_predicted_pass') &
            bool_column(frame, 'cubic_domain_pass') & finite(frame, ['x_h']))
    figure, axes = plt.subplots(2, 2, figsize=(7.07, 5.25))
    figure.subplots_adjust(left=.11, right=.98, top=.94, bottom=.14, wspace=.32, hspace=.45)
    counts = {}
    for axis, pollutant, letter in zip(axes.flat, POLS, 'abcd'):
        column = f'Gamma_cubic_{pollutant}'
        selected = frame.loc[mask & finite(frame, [column])].copy()
        if selected.empty:
            raise ValueError(f'No finite admissible average-weekday Gamma points for {pollutant}')
        scale = 1000. if pollutant == 'CO2' else 1.
        unit = 'kg/(veh h)' if pollutant == 'CO2' else 'g/(veh h)'
        for group, color, marker, label in groups(selected):
            axis.scatter(selected.loc[group, 'x_h'], selected.loc[group, column]/scale,
                         s=22, marker=marker, facecolors='none', edgecolors=color,
                         linewidths=.75, alpha=.68, label=label)
        axis.axhline(0, color=MUTED, lw=.8, ls='--', zorder=1)
        axis.set(xlabel=r'Cumulative demand $x=D/C$ (h)',
                 ylabel=rf'$\Gamma$ ({unit})')
        panel(axis, letter, POL_LABELS[pollutant])
        clean(axis)
        counts[pollutant] = {'plotted': len(selected), 'negative': int((selected[column] < 0).sum()),
                             'positive': int((selected[column] > 0).sum()),
                             'x_range_h': [float(selected.x_h.min()), float(selected.x_h.max())],
                             'gamma_range_g_per_veh_h': [float(selected[column].min()), float(selected[column].max())]}
    handles, labels = axes.flat[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc='lower center', bbox_to_anchor=(.55, .015), ncol=2, frameon=False)
    paths = save_figure(figure, 'fig5_gamma_progression', DEST)
    report = source_audit(data)
    report.update({'mask': 'calibration_eligible & physical_predicted_pass & cubic_domain_pass & finite(x, Gamma)',
                   'gamma_definition': 'Cubic emission coefficient at fitted-duration FD queue speed vq_hat_mph',
                   'negative_interpretation': 'Queued distance-specific emission is below its free-flow value; total emission need not be negative.',
                   'pollutants': counts, 'files': paths})
    write_audit('fig5_gamma_progression', report)


def fig8(data):
    frame = pd.read_csv(data / 'episode_results_v2.csv')
    base = bool_column(frame, 'calibration_eligible') & finite(frame, ['x_h', 'P_h', 'P_hat_h'])
    episodes = frame.loc[base].copy()
    if episodes.empty:
        raise ValueError('No calibrated average-weekday episodes for Figure 8')
    speed_pairs = episodes.loc[finite(episodes, ['vt2_obs_mph', 'vt2_hat_mph'])].copy()
    if 'figure8_pair_vq_pass' in frame:
        vq_mask = base & bool_column(frame, 'figure8_pair_vq_pass')
    else:
        # A finite FD queue state requires positive sub-capacity service and
        # a positive speed below vf.  The finite-link delay bound is NOT used
        # here; the comparison must retain its diagnostically relevant failures.
        vq_mask = (base & finite(frame, ['vq_mph', 'vq_hat_mph', 'vf_mph']) &
                   frame.vq_mph.gt(0) & frame.vq_mph.lt(frame.vf_mph) &
                   frame.vq_hat_mph.gt(0) & frame.vq_hat_mph.lt(frame.vf_mph))
    vq = frame.loc[vq_mask].copy()
    discharge = episodes.loc[finite(episodes, ['mu_vphpl', 'mu_hat_vphpl'])].copy()
    figure, axes = plt.subplots(2, 3, figsize=(7.07, 6.20))
    figure.subplots_adjust(left=.085, right=.98, top=.94, bottom=.19, wspace=.49, hspace=.47)
    a, b, c, d, e, f = axes.flat
    a.scatter(episodes.x_h, episodes.P_h, s=12, color=BLUE, alpha=.52, label='Observed duration')
    a.scatter(episodes.x_h, episodes.P_hat_h, s=17, marker='o', facecolors='none', edgecolors=ORANGE, alpha=.65,
              linewidths=.7, label='Fitted duration')
    max_x = float(episodes.x_h.max())
    a.plot([0, max_x], [0, max_x], color=MUTED, linestyle='--', lw=.8)
    a.set(xlabel=r'$x=D/C$ (h)', ylabel='Duration (h)')
    panel(a, 'a', 'Duration and demand')
    paired_points(b, episodes, 'P_h', 'P_hat_h')
    b.set(xlabel='Observed duration (h)', ylabel='Fitted duration (h)')
    panel(b, 'b', 'Duration prediction')
    paired_points(c, speed_pairs, 'vt2_obs_mph', 'vt2_hat_mph')
    c.set(xlabel=r'Observed $v_{t_2}$ (mph)', ylabel=r'Fitted $v_{t_2}$ (mph)')
    panel(c, 'c', 'Minimum link speed')
    d.scatter(vq.x_h, vq.vq_mph, s=13, color=BLUE, alpha=.55)
    d.scatter(vq.x_h, vq.vq_hat_mph, s=18, marker='o', facecolors='none', edgecolors=ORANGE, alpha=.7, linewidths=.7)
    d.set(xlabel=r'$x=D/C$ (h)', ylabel=r'FD queue speed $v_q$ (mph)')
    panel(d, 'd', 'Queue speed and demand')
    paired_points(e, vq, 'vq_mph', 'vq_hat_mph')
    e.set(xlabel=r'$v_q(D/P_{obs})$ (mph)', ylabel=r'$v_q(D/\widehat P)$ (mph)')
    panel(e, 'e', 'Queue-speed comparison')
    discharge['mu_obs_thousand']=discharge.mu_vphpl/1000
    discharge['mu_fit_thousand']=discharge.mu_hat_vphpl/1000
    paired_points(f, discharge, 'mu_obs_thousand', 'mu_fit_thousand')
    f.set(xlabel=r'$D/P_{obs}$ ($10^3$ veh/h/lane)', ylabel=r'$D/\widehat P$ ($10^3$ veh/h/lane)')
    panel(f, 'f', 'Mean discharge rate')
    for axis in axes.flat:
        clean(axis)
        axis.set_box_aspect(1)
    cohort_handles, cohort_labels = b.get_legend_handles_labels()
    figure.legend(cohort_handles, cohort_labels, loc='lower center', bbox_to_anchor=(.54,.018),
                  ncol=2, frameon=False)
    handles, labels = a.get_legend_handles_labels()
    labels = ['From observed episode', 'From fitted duration']
    figure.legend(handles, labels, loc='lower center', bbox_to_anchor=(.54,.080), ncol=2,
                  title='Panels (a) and (d)', title_fontsize=7.5, frameon=False)
    paths = save_figure(figure, 'fig8_calibration', DEST)
    report = source_audit(data)
    report.update({'calibrated_eligible': len(episodes), 'minimum_speed_pairs': len(speed_pairs),
                   'valid_fd_queue_speed_pairs': len(vq), 'discharge_pairs': len(discharge),
                   'excluded_invalid_fd_queue_state_pairs': int(base.sum()-len(vq)),
                   'queue_speed_is_directly_observed': False, 'finite_link_admissibility_filter': False,
                   'geometry_failures_retained_in_vq_plot': int((~bool_column(vq, 'physical_predicted_pass')).sum()),
                   'vq_mask': 'calibration eligible, finite observed/fitted FD speeds, 0<vq<vf for both states',
                   'panel_map': {'a':'duration against demand','b':'duration pairs','c':'minimum whole-link speed pairs',
                                 'd':'FD queue speeds against demand','e':'FD queue-speed pairs','f':'mean discharge-rate pairs'},
                   'files': paths})
    write_audit('fig8_calibration', report)


def fig9(data):
    frame=pd.read_csv(data/'episode_results_v2.csv')
    selected=frame.loc[bool_column(frame,'matched_ladder_pass')]
    figure,axes=plt.subplots(2,2,figsize=(7.07,5.6))
    figure.subplots_adjust(left=.105,right=.98,top=.94,bottom=.15,wspace=.31,hspace=.43)
    for axis,pollutant,letter in zip(axes.flat,POLS,'abcd'):
        scale=1000 if pollutant=='CO2' else 1
        unit='kg/lane' if pollutant=='CO2' else 'g/lane'
        axis.scatter(selected['O_'+pollutant]/scale,selected['M_'+pollutant]/scale,
            s=13,color=BLUE,alpha=.55,label='Two-speed model $M$')
        axis.scatter(selected['O_'+pollutant]/scale,selected['S_'+pollutant]/scale,
            s=17,marker='o',facecolors='none',edgecolors=INK,alpha=.62,lw=.65,
            label='Single episode-speed $S$')
        identity(axis,selected['O_'+pollutant]/scale,
            np.r_[selected['M_'+pollutant]/scale,selected['S_'+pollutant]/scale])
        clean(axis)
        axis.set(xlabel=f'Recorded-speed calculation $O$ ({unit})',ylabel=f'Comparison estimate ({unit})')
        panel(axis,letter,POL_LABELS[pollutant])
    handles,labels=axes.flat[0].get_legend_handles_labels()
    figure.legend(handles,labels,loc='lower center',bbox_to_anchor=(.54,.015),ncol=2,frameon=False)
    paths=save_figure(figure,'fig9_emission_comparison',DEST)
    report=source_audit(data)
    report.update({'mask':'matched_ladder_pass','matched_episodes':len(selected),
                   'comparisons':['M vs O','S vs O'],'pollutants':POLS,
                   'observed_speed_emission_calculation_is_tailpipe_measurement':False,'files':paths})
    write_audit('fig9_emission_comparison',report)


def fig10(surrogate_data, parameter_data):
    source=surrogate_data/'figure10_reference_states.csv'
    card=pd.read_csv(source)
    card=card.loc[bool_column(card,'valid')].copy()
    support_source=parameter_data/'parameter_card_full.csv'
    support=pd.read_csv(support_source)
    card=card.merge(support[['corridor','period','N_source']],on=['corridor','period'],how='left',validate='many_to_one')
    if card.N_source.isna().any():
        raise ValueError('Missing calibration support for an elasticity reference')
    card['small_sample']=card.N_source.lt(15)
    card.to_csv(QA/'elasticity_reference_support.csv',index=False)
    figure,axes=plt.subplots(2,2,figsize=(7.07,5.2))
    figure.subplots_adjust(left=.11,right=.98,top=.94,bottom=.17,wspace=.32,hspace=.44)
    counts={}
    for axis,pollutant,letter in zip(axes.flat,POLS,'abcd'):
        points=card.loc[card.pollutant.eq(pollutant)&finite(card,['beta','beta_plus_epsilon'])].copy()
        if points.empty:
            raise ValueError(f'No valid actual-detector references for {pollutant}')
        negative=points.congestion_g_per_vehicle.lt(0)
        # Sign uses shape; hollow/filled is reserved exclusively for fit support.
        for sign,marker in [(False,'o'),(True,'^')]:
            for small in [False,True]:
                chosen=points.loc[negative.eq(sign)&points.small_sample.eq(small)]
                axis.scatter(chosen.beta,chosen.beta_plus_epsilon,s=28 if marker=='o' else 32,
                    marker=marker,facecolors=WHITE if small else BLUE,
                    edgecolors=BLUE,linewidths=.85,alpha=.9,zorder=4 if small else 3)
        lo=min(0,float(points.beta.min()))
        hi=max(.1,float(points.beta.max())*1.08)
        axis.plot([lo,hi],[lo,hi],ls='--',color=MUTED,lw=.85)
        axis.axhline(0,color=MUTED,lw=.6)
        if pollutant in ['CO2','NOx']:
            axis.set_yscale('symlog',linthresh=2,linscale=1)
            low=min(-.5,float(points.beta_plus_epsilon.min())*1.2)
            high=max(hi,float(points.beta_plus_epsilon.max())*1.2,2.2)
            axis.set_ylim(low,high)
            ticks=[v for v in [-100,-30,-10,-2,-1,0,1,2,5,10,30,100] if low<=v<=high]
            axis.set_yticks(ticks);axis.set_yticklabels([str(v) for v in ticks])
        axis.set(xlim=(lo,hi),xlabel=r'Mean-delay elasticity $\beta=ns$',
                 ylabel=r'Increment elasticity $\beta+\varepsilon_{\Gamma,x}$')
        panel(axis,letter,POL_LABELS[pollutant]);clean(axis)
        counts[pollutant]={'plotted_rows':len(points),'negative_increment':int(negative.sum()),
                          'positive_increment':int((~negative).sum()),
                          'N_source_below_15':int(points.small_sample.sum()),
                          'unique_coordinates':len(points[['beta','beta_plus_epsilon']].drop_duplicates())}
    handles=[Line2D([],[],linestyle='none',marker='o',color=INK,label=r'$\Delta e>0$'),
             Line2D([],[],linestyle='none',marker='^',color=INK,label=r'$\Delta e<0$'),
             Line2D([],[],linestyle='none',marker='o',color=BLUE,label=r'$N_{source}\geq15$'),
             Line2D([],[],linestyle='none',marker='o',markerfacecolor=WHITE,color=BLUE,label=r'$N_{source}<15$')]
    figure.legend(handles=handles,loc='lower center',bbox_to_anchor=(.54,.025),ncol=4,frameon=False,
        columnspacing=1.4)
    paths=save_figure(figure,'fig10_emission_elasticity',DEST)
    write_audit('fig10_emission_elasticity',{'source':str(source.relative_to(ROOT)),
                'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'support_source':str(support_source.relative_to(ROOT)),
                'support_sha256':hashlib.sha256(support_source.read_bytes()).hexdigest(),
                'support_definition':'N_source effective calibration fit episodes including fallback',
                'small_sample_cards':card.loc[card.small_sample,['corridor','period','N_source']].drop_duplicates().to_dict('records'),
                'reference_detector_is_actual':True,'legacy_median_reference_used':False,
                'bootstrap_intervals_shown':False,'counts':counts,'files':paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=_FROZEN / 'calibration/average_weekday')
    parser.add_argument('--surrogate-data', type=Path, default=_FROZEN / 'calibration/surrogate')
    parser.add_argument('--only', choices=['all','gamma','calibration','emissions','elasticity'], default='all')
    args = parser.parse_args()
    style()
    jobs = {'gamma': fig5, 'calibration': fig8, 'emissions': fig9}
    for name, function in jobs.items():
        if args.only in ('all', name):
            function(args.data)
            print(f'Generated {name} from {args.data}', flush=True)
    if args.only in ('all','elasticity'):
        fig10(args.surrogate_data,args.data)
        print(f'Generated elasticity references from {args.surrogate_data}',flush=True)


if __name__ == '__main__':
    main()
