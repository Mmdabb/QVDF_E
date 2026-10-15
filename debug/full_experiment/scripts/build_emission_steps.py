"""Expose the frozen experiment's traffic, VSP, rate and emission arithmetic.

No traffic calibration or sample selection is changed. Generated files are
separate from the committed reference package. Large node tables use gzip CSV.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import io
import json
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import wasserstein_distance

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from qvdfe.pipeline._engine.emissions import load_moves_rates, compute_vsp, get_op_mode_bin
from qvdfe.pipeline._engine.model import profile_grid, queue_speed

POLS = ['CO2', 'NOx', 'CO', 'HC']
METHODS = ['O', 'S', 'R', 'M', 'A']
COLORS = dict(O='#242B33', S='#2563EB', R='#7B3294', M='#168C69', A='#E69F00')
SOURCE = ROOT / 'data/frozen/calibration/average_weekday'
STEP_NAMES = ['05_physical_admission', '06_rate_construction', '07_observed_and_single_speed',
              '08_reconstruction_and_two_speed', '09_totals_and_comparison']


def output_path():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'debug/output/full_experiment/emissions')
    args = parser.parse_args()
    out = args.output.resolve()
    root, working = ROOT.resolve(), (ROOT / 'debug/output').resolve()
    if root.is_relative_to(out) or (out.is_relative_to(root) and not out.is_relative_to(working)):
        parser.error('Use debug/output/ or a separate working directory, outside reference/source folders.')
    marker = out / '.emission-step-trace.json'
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not marker.is_file())):
        parser.error('Choose an empty directory or one already owned by this calculation trace.')
    out.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"workflow":"emission_step_trace"}\n', encoding='utf-8')
    return out


def save_csv(frame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.gz':
        with path.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding='utf-8', newline='') as text:
                frame.to_csv(text, index=False, lineterminator='\n')
    else:
        frame.to_csv(path, index=False, lineterminator='\n')


def vsp_terms(speed, params):
    v = np.asarray(speed, float) * .44704
    mass = float(params['source_mass'])
    a = float(params['rolling_term_a']) * v / mass
    b = float(params['rotating_term_b']) * v**2 / mass
    c = float(params['drag_term_c']) * v**3 / mass
    return dict(speed_mps=v, rolling_vsp_kw_t=a, rotating_vsp_kw_t=b,
                drag_vsp_kw_t=c, vsp_kw_t=a+b+c)


def mode_for(v, vsp):
    return np.array([get_op_mode_bin(float(a), float(b)) for a, b in zip(np.atleast_1d(v), np.atleast_1d(vsp))])


def chart_style():
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titlesize': 11,
                         'axes.labelsize': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.labelcolor': '#17324D', 'text.color': '#17324D', 'axes.edgecolor': '#94A3B8',
                         'axes.facecolor': 'white', 'figure.facecolor': 'white', 'savefig.facecolor': 'white',
                         'grid.color': '#E2E8F0', 'grid.linewidth': .6, 'svg.fonttype': 'none',
                         'svg.hashsalt': 'qvdfe-step-diagnostics'})


def save_fig(fig, path):
    for ax in fig.axes:
        ax.grid(alpha=.65)
        ax.set_axisbelow(True)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix('.png'), dpi=180, bbox_inches='tight')
    fig.savefig(path.with_suffix('.svg'), bbox_inches='tight', metadata={'Date': None})
    plt.close(fig)


def main():
    out = output_path()
    folders = {int(n[:2]): out / 'steps' / n for n in STEP_NAMES}
    for path in folders.values():
        path.mkdir(parents=True, exist_ok=True)
    ep = pd.read_csv(SOURCE / 'episode_results_v2.csv', parse_dates=['t0', 't2', 't3'])
    retained = ep[ep.matched_ladder_pass.eq(True)].copy()
    assert len(ep) == 325 and len(retained) == 137
    panel = pd.read_csv(SOURCE / 'traffic_panel.csv.gz', parse_dates=['datetime'], low_memory=False)
    panel['date'] = panel.datetime.dt.strftime('%Y-%m-%d')
    groups = {key: g.sort_values('datetime') for key, g in panel.groupby(['sensor_uid', 'date'])}
    moves = load_moves_rates(ROOT / 'data/frozen/calibration/emission_input')
    params = moves.vehicle_params
    co = pd.read_csv(SOURCE / 'cubic_rate_coefficients.csv').set_index('pollutant')
    rate_by_mode = moves.rates.set_index('OpModeID')

    def lookup(mode, pol):
        name = 'NOX' if pol == 'NOx' else pol
        return np.array([rate_by_mode.loc[int(m), 'ER_' + name] for m in np.atleast_1d(mode)])

    def cubic(v, pol):
        return sum(co.loc[pol, 'c'+str(k)] * np.asarray(v)**k for k in range(4))

    # Step 5: expose the finite-link bound and every admission decision.
    admission = ep[['episode_id', 'paper_corridor', 'corridor', 'period', 'calibration_eligible',
                    'calibration_scope', 'D_veh', 'L_mi', 'C_vphpl', 'vf_mph', 'kj', 'x_h',
                    'fd', 'n', 'fp', 's', 'theta', 'P_hat_h', 'wt2_hat_h', 'wbar_hat_h',
                    'physical_observed_pass', 'physical_predicted_pass', 'physical_failure_reason',
                    'profile_closed_pass', 'cubic_domain_pass', 'matched_ladder_pass']].copy()
    admission['power_duration_h'] = ep.fd * ep.x_h**ep.n
    admission['P_recomputed_h'] = np.maximum(admission.power_duration_h, ep.x_h)
    admission['Tf_h'] = ep.L_mi / ep.vf_mph
    admission['peak_recomputed_h'] = admission.Tf_h * ep.fp * admission.P_recomputed_h**ep.s
    admission['mu_recomputed_vphpl'] = ep.D_veh / admission.P_recomputed_h
    vq, kq, omega = queue_speed(admission.mu_recomputed_vphpl, ep.C_vphpl, ep.vf_mph, ep.kj)
    admission['omega_mph'] = omega
    admission['kq_recomputed_veh_mi_lane'] = kq
    admission['vq_recomputed_mph'] = vq
    admission['maximum_compatible_delay_h'] = ep.L_mi / vq - admission.Tf_h
    admission['delay_margin_s'] = 3600 * (admission.maximum_compatible_delay_h-admission.peak_recomputed_h)
    with np.errstate(divide='ignore', invalid='ignore'):
        admission['peak_queue_time_h'] = ep.vf_mph * admission.peak_recomputed_h / (ep.vf_mph-vq)
        admission['peak_free_time_h'] = admission.Tf_h - vq * admission.peak_recomputed_h / (ep.vf_mph-vq)
    admission['supported_fit'] = ep.fd.notna()
    admission['all_20_totals_finite_positive'] = np.isfinite(ep[[f'{m}_{p}' for m in METHODS for p in POLS]]).all(axis=1) & ep[[f'{m}_{p}' for m in METHODS for p in POLS]].gt(0).all(axis=1)
    for calculated, archived in [('P_recomputed_h', 'P_hat_h'), ('peak_recomputed_h', 'wt2_hat_h'), ('vq_recomputed_mph', 'vq_hat_mph')]:
        np.testing.assert_allclose(admission[calculated], ep[archived], rtol=1e-10, atol=1e-10, equal_nan=True)
    assert (admission.calibration_eligible & admission.physical_predicted_pass & admission.profile_closed_pass & admission.cubic_domain_pass & admission.all_20_totals_finite_positive).equals(ep.matched_ladder_pass)
    save_csv(admission, folders[5] / 'physical_admission_325.csv')

    # Step 6: rate construction from the original age mixture, before any method uses it.
    raw_rates = pd.read_csv(ROOT / 'data/frozen/calibration/emission_input/input_vehicle_emission_rate.csv')
    age = pd.DataFrame([dict(age=int(k.rsplit('_', 1)[1]), supplied_weight=float(v)) for k, v in params.items() if k.startswith('percentage_of_age_')])
    age['normalized_weight'] = age.supplied_weight / age.supplied_weight.sum()
    save_csv(age, folders[6] / 'vehicle_age_weights.csv')
    mixed = raw_rates[raw_rates.vehicle_type.eq(1)].merge(age, on='age', validate='many_to_one')
    age_rows = []
    for p in POLS:
        source_col = f'meanBaseRate_{"NOX" if p=="NOx" else p}_(g/hr)'
        z = mixed[['OpModeID', 'age', 'normalized_weight']].copy()
        z['pollutant'] = p
        z['input_rate_g_veh_h'] = mixed[source_col]
        z['weighted_contribution_g_veh_h'] = mixed[source_col] * mixed.normalized_weight
        age_rows.append(z)
        sums = z.groupby('OpModeID').weighted_contribution_g_veh_h.sum()
        np.testing.assert_allclose(sums, lookup(sums.index, p), rtol=1e-12, atol=1e-12)
    save_csv(pd.concat(age_rows, ignore_index=True), folders[6] / 'age_rate_contributions.csv')
    save_csv(moves.rates, folders[6] / 'age_weighted_operating_mode_rates.csv')
    save_csv(pd.DataFrame([{'quantity': k, 'value': params[k]} for k in ['vehicle_type', 'source_mass', 'rolling_term_a', 'rotating_term_b', 'drag_term_c']] +
                         [dict(quantity='mph_to_mps', value=.44704), dict(quantity='acceleration_mps2', value=0), dict(quantity='road_grade', value=0)]), folders[6] / 'vsp_input_parameters.csv')
    speed = np.linspace(5, 75, 701)
    road = pd.DataFrame({'speed_mph': speed, **vsp_terms(speed, params)})
    road['OpModeID'] = mode_for(speed, road.vsp_kw_t)
    save_csv(road, folders[6] / 'speed_to_vsp_grid.csv')
    curve = []
    for p in POLS:
        z = road[['speed_mph', 'vsp_kw_t', 'OpModeID']].copy()
        z['pollutant'] = p
        z['lookup_rate_g_veh_h'] = lookup(z.OpModeID, p)
        for k in range(4):
            z[f'cubic_term_{k}_g_veh_h'] = co.loc[p, 'c'+str(k)] * speed**k
        z['cubic_rate_g_veh_h'] = cubic(speed, p)
        z['cubic_minus_lookup_g_veh_h'] = z.cubic_rate_g_veh_h-z.lookup_rate_g_veh_h
        curve.append(z)
    curves = pd.concat(curve, ignore_index=True)
    save_csv(curves, folders[6] / 'lookup_and_cubic_grid.csv')
    save_csv(co.reset_index(), folders[6] / 'cubic_coefficients.csv')

    observed, singles, obs_lookup, single_lookup, obs_emission, single_emission = [], [], [], [], [], []
    nodes, node_lookups, states, state_rates, node_emissions = [], [], [], [], []
    totals, identities, vsp_summary, mode_exposure, comparisons = [], [], [], [], []
    histogram_parts = {m: [] for m in METHODS}
    hist_edges = np.linspace(0, 32, 129)
    for r in retained.itertuples(index=False):
        g = groups[(r.sensor_uid, r.date)]
        g = g[(g.datetime >= r.t0) & (g.datetime < r.t3)]
        v, d = g.speed_mph.to_numpy(float), g.flow_vph.to_numpy(float)/12
        D, L, vf, vq = d.sum(), r.L_mi, r.vf_mph, r.vq_hat_mph
        Tf, peak, mean_delay = L/vf, r.wt2_hat_h, r.wbar_hat_h
        trips, Hbins = L/v, d*L/v
        H = Hbins.sum(); Hp = D*(Tf+mean_delay); vm = D*L/H
        ids = {'episode_id': r.episode_id, 'paper_corridor': r.paper_corridor}
        terms = vsp_terms(v, params); om = mode_for(v, terms['vsp_kw_t'])
        single_terms = vsp_terms(np.array([vm]), params); sm = mode_for([vm], single_terms['vsp_kw_t'])
        u, gl, h, lam, shape, closed, minlam = profile_grid(r.P_hat_h, peak, r.theta)
        assert closed and len(u) == 384
        N, w, tau = D*gl*lam, peak*h, Tf+peak*h
        vr = L/tau
        nq = vf*w/(vf-vq); nf = Tf-vq*w/(vf-vq)
        tqueue = vf*mean_delay/(vf-vq); tfree = Tf-vq*mean_delay/(vf-vq)
        rt = vsp_terms(vr, params); rm = mode_for(vr, rt['vsp_kw_t'])
        st = vsp_terms(np.array([vf, vq]), params); st_modes = mode_for([vf, vq], st['vsp_kw_t'])
        observed.append(pd.DataFrame({**ids, 'bin_index': np.arange(1,len(g)+1), 'datetime': g.datetime.to_numpy(),
                        'flow_vphpl': g.flow_vph.to_numpy(), 'count_veh': d, 'speed_mph': v, **terms,
                        'trip_time_h': trips, 'vehicle_hours': Hbins}))
        singles.append(dict(**ids, D_veh=D, sum_vehicle_hours=H, L_mi=L, mean_trip_time_h=H/D,
                            speed_mph=vm, **{k:float(val[0]) for k,val in single_terms.items()}))
        nodes.append(pd.DataFrame({**ids, 'node_index': np.arange(1,385), 'u': u, 'quadrature_weight': gl,
                     'shape_h': h, 'arrival_factor': lam, 'vehicle_weight': N, 'delay_h': w,
                     'trip_time_h': tau, 'vehicle_hours': N*tau, 'speed_mph': vr, **rt,
                     'free_time_h': nf, 'queue_time_h': nq, 'distance_mi': vf*nf+vq*nq}))
        states.append(pd.DataFrame({**ids, 'state': ['free', 'queue'], 'speed_mph': [vf,vq], **st,
                                   'mean_time_h': [tfree,tqueue], 'vehicle_hours': [D*tfree,D*tqueue]}))
        Hdist = {'O': Hbins, 'S': np.array([H]), 'R': N*tau,
                 'M': D*np.array([tfree,tqueue]), 'A': D*np.array([tfree,tqueue])}
        Vdist = {'O': terms['vsp_kw_t'], 'S': single_terms['vsp_kw_t'], 'R': rt['vsp_kw_t'],
                 'M': st['vsp_kw_t'], 'A': st['vsp_kw_t']}
        modes = {'O': om, 'S': sm, 'R': rm, 'M': st_modes, 'A': st_modes}
        mean_o = float(np.average(Vdist['O'], weights=Hdist['O']))
        all_modes = sorted(rate_by_mode.index)
        shares_o = np.array([Hbins[om==mode].sum()/H for mode in all_modes])
        for m in METHODS:
            vals, exposure = Vdist[m], Hdist[m]
            mean = float(np.average(vals, weights=exposure))
            shares = np.array([exposure[modes[m]==mode].sum()/exposure.sum() for mode in all_modes])
            vsp_summary.append(dict(**ids, method=m, vehicle_hours=exposure.sum(), mean_vsp_kw_t=mean,
                vsp_of_equivalent_speed_kw_t=float(compute_vsp([D*L/exposure.sum()], params)[0]),
                mean_vsp_minus_O_kw_t=mean-mean_o,
                wasserstein_vsp_distance_kw_t=float(wasserstein_distance(Vdist['O'], vals, u_weights=Hdist['O'], v_weights=exposure)),
                operating_mode_total_variation=.5*np.abs(shares-shares_o).sum()))
            for mode, share in zip(all_modes, shares):
                mode_exposure.append(dict(**ids, method=m, OpModeID=int(mode), vehicle_hours=share*exposure.sum(), share=share))
            histogram_parts[m].append(np.histogram(vals, bins=hist_edges, weights=exposure)[0])
        identities.append(dict(**ids, D_veh=D, observed_bins=len(g), quadrature_nodes=len(u),
             profile_shape_a=shape, profile_family='flat_top_power' if r.theta>2/3 else 'beta_power',
             theta=r.theta, predicted_duration_h=r.P_hat_h, peak_delay_h=peak,
             vehicle_conservation_error_veh=N.sum()-D, mean_delay_quadrature_error_h=np.sum(N*w)/D-mean_delay,
             distance_identity_max_abs_mi=float(np.max(abs(vf*nf+vq*nq-L))),
             time_identity_max_abs_h=float(np.max(abs(nf+nq-tau))),
             average_speed_identity_max_abs_mph=float(np.max(abs((vf*nf+vq*nq)/(nf+nq)-vr))),
             minimum_node_free_time_s=float(nf.min()*3600), minimum_arrival_factor=minlam))
        for p in POLS:
            ro, rs, rr = lookup(om,p), float(lookup(sm,p)[0]), lookup(rm,p)
            rf,rq = lookup(st_modes,p); af,aq = cubic(np.array([vf,vq]),p)
            obs_lookup.append(pd.DataFrame({**ids, 'bin_index': np.arange(1,len(g)+1), 'pollutant': p,
                       'speed_mph': v, 'vsp_kw_t': terms['vsp_kw_t'], 'OpModeID': om, 'lookup_rate_g_veh_h': ro}))
            single_lookup.append(dict(**ids, pollutant=p, speed_mph=vm, vsp_kw_t=float(single_terms['vsp_kw_t'][0]),
                                      OpModeID=int(sm[0]), lookup_rate_g_veh_h=rs))
            obs_emission.append(pd.DataFrame({**ids, 'bin_index': np.arange(1,len(g)+1), 'pollutant': p,
                                  'count_veh':d, 'trip_time_h':trips, 'vehicle_hours':Hbins,
                                  'rate_g_veh_h':ro, 'emission_g':Hbins*ro}))
            single_emission.append(dict(**ids, pollutant=p, D_veh=D, mean_trip_time_h=H/D,
                                        vehicle_hours=H, rate_g_veh_h=rs, emission_g=H*rs))
            node_lookups.append(pd.DataFrame({**ids,'node_index':np.arange(1,385),'pollutant':p,
                         'vsp_kw_t':rt['vsp_kw_t'],'speed_mph':vr,'OpModeID':rm,'lookup_rate_g_veh_h':rr}))
            for si, state in enumerate(['free','queue']):
                sv=[vf,vq][si]
                state_rates.append(dict(**ids, pollutant=p, state=state, speed_mph=sv, vsp_kw_t=st['vsp_kw_t'][si],
                       OpModeID=int(st_modes[si]), lookup_rate_g_veh_h=[rf,rq][si],
                       cubic_c0=co.loc[p,'c0'],cubic_c1v=co.loc[p,'c1']*sv,cubic_c2v2=co.loc[p,'c2']*sv**2,
                       cubic_c3v3=co.loc[p,'c3']*sv**3,cubic_rate_g_veh_h=[af,aq][si]))
            node_emissions.append(pd.DataFrame({**ids,'node_index':np.arange(1,385),'pollutant':p,
                 'vehicle_weight':N,'R_trip_time_h':tau,'R_lookup_rate_g_veh_h':rr,'R_g':N*tau*rr,
                 'free_time_h':nf,'queue_time_h':nq,'M_free_g':N*nf*rf,'M_queue_g':N*nq*rq,
                 'A_free_g':N*nf*af,'A_queue_g':N*nq*aq}))
            gamma=(vf*rq-vq*rf)/(vf-vq); gammac=(vf*aq-vq*af)/(vf-vq)
            values=dict(O=float(np.sum(Hbins*ro)),S=H*rs,R=float(np.sum(N*tau*rr)),
                        M=D*(tfree*rf+tqueue*rq),A=D*(tfree*af+tqueue*aq))
            vp = D*L/Hp; vp_vsp = compute_vsp([vp],params); vp_mode=mode_for([vp],vp_vsp)
            vp_rate=float(lookup(vp_mode,p)[0]); sp=Hp*vp_rate
            z=dict(**ids,pollutant=p,D_veh=D,H_observed_veh_h=H,H_predicted_veh_h=Hp,
                   mean_free_time_h=tfree,mean_queue_time_h=tqueue,free_lookup_rate_g_veh_h=rf,queue_lookup_rate_g_veh_h=rq,
                   free_cubic_rate_g_veh_h=af,queue_cubic_rate_g_veh_h=aq,Gamma_lookup_g_veh_h=gamma,
                   Gamma_cubic_g_veh_h=gammac,baseline_lookup_g=D*Tf*rf,delay_increment_lookup_g=D*mean_delay*gamma,
                   baseline_cubic_g=D*Tf*af,delay_increment_cubic_g=D*mean_delay*gammac,
                   M_free_g=D*tfree*rf,M_queue_g=D*tqueue*rq,A_free_g=D*tfree*af,A_queue_g=D*tqueue*aq,
                   S_pred_speed_mph=vp,S_pred_vsp_kw_t=float(vp_vsp[0]),S_pred_OpModeID=int(vp_mode[0]),
                   S_pred_rate_g_veh_h=vp_rate,S_pred_g=sp,
                   M_node_minus_analytic_g=float(np.sum(N*(nf*rf+nq*rq))-values['M']),
                   A_node_minus_analytic_g=float(np.sum(N*(nf*af+nq*aq))-values['A']),
                   **{m+'_g':e for m,e in values.items()})
            z.update(S_minus_O_g=values['S']-values['O'],S_pred_minus_S_g=sp-values['S'],
                     R_minus_S_pred_g=values['R']-sp,M_minus_R_g=values['M']-values['R'],A_minus_M_g=values['A']-values['M'])
            for m in METHODS:
                saved=float(getattr(r,m+'_'+p))
                comparisons.append(dict(**ids,pollutant=p,method=m,recomputed_g=values[m],archived_g=saved,
                                        difference_g=values[m]-saved,relative_difference=(values[m]-saved)/saved))
                np.testing.assert_allclose(values[m],saved,rtol=1e-9,atol=1e-8)
                z[m+'_signed_error_pct']=100*(values[m]/values['O']-1)
                z[m+'_absolute_error_pct']=100*abs(values[m]/values['O']-1)
            totals.append(z)
    outputs = {
      (7,'observed_speed_vsp.csv'):pd.concat(observed,ignore_index=True),
      (7,'single_speed_vsp.csv'):pd.DataFrame(singles),
      (7,'observed_rate_lookup.csv'):pd.concat(obs_lookup,ignore_index=True),
      (7,'single_speed_rate_lookup.csv'):pd.DataFrame(single_lookup),
      (7,'observed_emission_terms.csv'):pd.concat(obs_emission,ignore_index=True),
      (7,'single_speed_emission_terms.csv'):pd.DataFrame(single_emission),
      (8,'reconstructed_speed_vsp.csv.gz'):pd.concat(nodes,ignore_index=True),
      (8,'two_speed_state_vsp.csv'):pd.concat(states,ignore_index=True),
      (8,'reconstructed_rate_lookup.csv.gz'):pd.concat(node_lookups,ignore_index=True),
      (8,'two_speed_lookup_and_cubic_rates.csv'):pd.DataFrame(state_rates),
      (8,'node_emission_terms.csv.gz'):pd.concat(node_emissions,ignore_index=True),
      (8,'profile_conservation_checks.csv'):pd.DataFrame(identities),
      (8,'vsp_agreement_by_episode_method.csv'):pd.DataFrame(vsp_summary),
      (8,'operating_mode_exposure_by_episode.csv'):pd.DataFrame(mode_exposure),
      (9,'episode_pollutant_calculation_steps.csv'):pd.DataFrame(totals),
      (9,'archived_result_reconciliation.csv'):pd.DataFrame(comparisons),
    }
    total=pd.DataFrame(totals); metric_rows=[]
    for sample, mask in [('All 137',np.ones(len(total),bool)),('Arizona I-10',total.paper_corridor.eq('AZ_I10')),('California PeMS',total.paper_corridor.ne('AZ_I10'))]:
        for p in POLS:
            z=total[mask & total.pollutant.eq(p)]; o=z.O_g.to_numpy(); denom=np.abs(o).sum(); sst=np.sum((o-o.mean())**2)
            for m in ['S','S_pred','R','M','A']:
                pred=z[m+'_g'].to_numpy();err=pred-o
                metric_rows.append(dict(sample=sample,pollutant=p,method=m,N=len(z),sum_reference_g=o.sum(),sum_method_g=pred.sum(),
                   sum_abs_error_g=np.abs(err).sum(),sum_signed_error_g=err.sum(),sum_squared_error_g2=np.sum(err**2),
                   reference_sum_squared_deviation_g2=sst,WAPE_pct=100*np.abs(err).sum()/denom,
                   bias_pct=100*err.sum()/o.sum(),RMSE_g=np.sqrt(np.mean(err**2)),R2=1-np.sum(err**2)/sst))
    metrics=pd.DataFrame(metric_rows); outputs[(9,'pooled_metric_calculation_steps.csv')]=metrics
    hist_rows=[]
    for m in METHODS:
        counts=np.sum(histogram_parts[m],axis=0)
        for j,value in enumerate(counts):
            hist_rows.append(dict(method=m,vsp_lower_kw_t=hist_edges[j],vsp_upper_kw_t=hist_edges[j+1],vehicle_hours=value,
                                  exposure_share=value/counts.sum(),cumulative_share=counts[:j+1].sum()/counts.sum()))
    outputs[(8,'pooled_vsp_exposure_distribution.csv')]=pd.DataFrame(hist_rows)
    for (step,name),frame in outputs.items(): save_csv(frame,folders[step]/name)
    # Small preview of the long node tables, with the complete CSVs available compressed.
    for key in [(8,'reconstructed_speed_vsp.csv.gz'),(8,'reconstructed_rate_lookup.csv.gz'),(8,'node_emission_terms.csv.gz')]:
        save_csv(outputs[key].head(24),folders[8]/(key[1].replace('.csv.gz','_preview.csv')))
    matched_metrics=metrics[metrics['sample'].eq('All 137')]
    archived=pd.read_csv(ROOT/'debug/episodes_137/results/comparison_metrics.csv')
    archived=archived[archived['sample'].eq('All 137')]
    merged=matched_metrics.merge(archived,on=['sample','pollutant','method','N'],suffixes=('_new','_saved'),validate='one_to_one')
    for key in ['WAPE_pct','bias_pct','R2']:
        np.testing.assert_allclose(merged[key+'_new'],merged[key+'_saved'],rtol=1e-9,atol=1e-8)
    assert len(merged)==20
    chart_style()
    # Admission chart separates calibration support from the stronger finite-link condition.
    fig,axs=plt.subplots(1,2,figsize=(11,4.3),layout='constrained')
    eligible=admission[admission.calibration_eligible & admission.supported_fit]
    for passed,label,color in [(False,'Excluded by finite-link check','#D47A40'),(True,'Retained comparison',COLORS['M'])]:
        z=eligible[eligible.physical_predicted_pass.eq(passed)]
        axs[0].scatter(z.maximum_compatible_delay_h*60,z.peak_recomputed_h*60,s=15,alpha=.75,color=color,label=f'{label} (n={len(z)})')
    lim=max(eligible.maximum_compatible_delay_h.max(),eligible.peak_recomputed_h.max())*60
    axs[0].plot([0,lim],[0,lim],color='#64748B',ls='--',lw=1)
    axs[0].set(xlabel='Maximum compatible delay (min)',ylabel='Predicted peak delay (min)',title='Queue must fit within the link')
    axs[0].legend(fontsize=8)
    r=admission[admission.matched_ladder_pass]
    axs[1].hist(r.peak_free_time_h*3600,bins=20,color=COLORS['M'],alpha=.8)
    axs[1].set(xlabel='Free-flow time at peak delay (s)',ylabel='Episodes',title='Nonnegative time allocation: 137 episodes')
    save_fig(fig,folders[5]/'diagnostic_physical_admission')
    fig,axs=plt.subplots(2,3,figsize=(12,7.5),layout='constrained')
    axs[0,0].plot(road.speed_mph,road.vsp_kw_t,color=COLORS['S'])
    axs[0,0].set(xlabel='Operating speed (mph)',ylabel='VSP (kW/t)',title='Zero-acceleration VSP')
    axs[0,1].step(road.vsp_kw_t,road.OpModeID,where='post',color=COLORS['M'])
    axs[0,1].set(xlabel='VSP (kW/t)',ylabel='Operating-mode ID',title='Joint speed/VSP classification')
    for ax,p in zip([axs[0,2],*axs[1]],POLS):
        z=curves[curves.pollutant.eq(p)]
        ax.plot(z.vsp_kw_t,z.lookup_rate_g_veh_h,label='Lookup',color=COLORS['M'])
        ax.plot(z.vsp_kw_t,z.cubic_rate_g_veh_h,label='Cubic',color=COLORS['A'],ls='--')
        ax.set(xlabel='VSP (kW/t)',ylabel='Rate (g/vehicle-hour)',title=p)
    axs[0,2].legend(fontsize=8)
    save_fig(fig,folders[6]/'diagnostic_vsp_and_rates')
    fig,axs=plt.subplots(1,2,figsize=(11,4.2),layout='constrained')
    bv=outputs[(7,'observed_speed_vsp.csv')]
    axs[0].hist(bv.vsp_kw_t,bins=30,weights=bv.vehicle_hours,color=COLORS['O'],alpha=.8)
    axs[0].set(xlabel='Recorded-speed VSP (kW/t)',ylabel='Vehicle-hours',title='Reference exposure across 4,800 bins')
    vs=pd.DataFrame(vsp_summary);o=vs[vs.method.eq('O')].set_index('episode_id');s=vs[vs.method.eq('S')].set_index('episode_id').loc[o.index]
    axs[1].scatter(o.mean_vsp_kw_t,s.mean_vsp_kw_t,color=COLORS['S'],s=18,alpha=.8)
    lim=max(o.mean_vsp_kw_t.max(),s.mean_vsp_kw_t.max());axs[1].plot([0,lim],[0,lim],ls='--',color='#64748B',lw=1)
    axs[1].set(xlabel='O exposure-weighted VSP (kW/t)',ylabel='S VSP at mean speed (kW/t)',title='Averaging speed changes VSP')
    save_fig(fig,folders[7]/'diagnostic_observed_and_mean_vsp')
    fig,axs=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    hd=pd.DataFrame(hist_rows)
    for m in ['O','S','R','M']:
        z=hd[hd.method.eq(m)]
        axs[0].step(z.vsp_upper_kw_t,z.cumulative_share,where='post',color=COLORS[m],label=m)
    axs[0].set(xlabel='VSP (kW/t)',ylabel='Cumulative vehicle-hour share',title='Operating-state VSP distributions (A = M)')
    axs[0].set_xlim(0, float(hd.loc[hd.vehicle_hours.gt(0), 'vsp_upper_kw_t'].max())*1.04)
    axs[0].legend(ncol=2)
    for i,m in enumerate(['S','R','M']):
        vals=vs[vs.method.eq(m)].wasserstein_vsp_distance_kw_t
        axs[1].scatter(np.full(len(vals),i)+np.linspace(-.15,.15,len(vals)),vals,s=10,alpha=.5,color=COLORS[m])
        axs[1].plot([i-.2,i+.2],[vals.median()]*2,color='#17324D',lw=2)
    axs[1].set(xticks=[0,1,2],xticklabels=['S','R','M = A'],ylabel='VSP distribution distance to O (kW/t)',title='Episode-level VSP differences')
    save_fig(fig,folders[8]/'diagnostic_vsp_distributions')
    fig,axs=plt.subplots(1,2,figsize=(11,4.4),layout='constrained')
    for j,m in enumerate(['S','R','M','A']):
        vals=[float(matched_metrics[(matched_metrics.method.eq(m))&(matched_metrics.pollutant.eq(p))].WAPE_pct.iloc[0]) for p in POLS]
        axs[0].bar(np.arange(4)+(j-1.5)*.18,vals,.18,color=COLORS[m],label=m)
    axs[0].set(xticks=np.arange(4),xticklabels=POLS,ylabel='Episode WAPE (%)',title='Same 137-episode comparison')
    axs[0].legend(ncol=2,fontsize=9)
    z=total[total.pollutant.eq('CO2')]
    for m in ['S','R','M','A']:
        axs[1].scatter(z.O_g/1000,z[m+'_g']/1000,s=12,alpha=.55,color=COLORS[m],label=m)
    lim=max(z.O_g.max(),z[['S_g','R_g','M_g','A_g']].max().max())/1000
    axs[1].plot([0,lim],[0,lim],ls='--',color='#64748B',lw=1)
    axs[1].set(xlabel='O reference CO2 (kg/episode)',ylabel='Estimated CO2 (kg/episode)',title='Episode totals on the same demand')
    save_fig(fig,folders[9]/'diagnostic_emission_comparison')
    audit={'scope':'Recomputed arithmetic from frozen parameters and unchanged matched sample; no calibration rerun.',
           'all_average_episode_records':len(ep),'matched_episodes':len(retained),'observed_bins':len(bv),
           'reconstruction_nodes':len(outputs[(8,'reconstructed_speed_vsp.csv.gz')]),'node_pollutant_records':len(outputs[(8,'node_emission_terms.csv.gz')]),
           'reconciled_method_totals':len(comparisons),'maximum_relative_total_difference':float(pd.DataFrame(comparisons).relative_difference.abs().max()),
           'matched_pooled_metrics_checked':len(merged),'rate_age_weight_checks_passed':True,'all_checks_passed':True,
           'vsp_interpretation':'Differences to the recorded-speed zero-acceleration proxy, not measured trajectory VSP errors.',
           'inputs':{str(p.relative_to(ROOT).as_posix()):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE/'episode_results_v2.csv',SOURCE/'traffic_panel.csv.gz',SOURCE/'cubic_rate_coefficients.csv',ROOT/'data/frozen/calibration/emission_input/input_vehicle_type.csv',ROOT/'data/frozen/calibration/emission_input/input_vehicle_emission_rate.csv']}}
    (out/'emission_trace_audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(audit,indent=2))


if __name__=='__main__':
    main()
