"""Explore bounded triangular-FD pairs at the preserved fitted discharge rate.

This is an episode diagnostic. It does not refit traffic parameters or replace
the frozen experiment. The density/wave-speed box is an explicit exploratory
assumption, not an empirically validated universal range.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
K_MIN, K_MAX = 150.0, 300.0  # veh / mi / lane
W_MIN, W_MAX = 5.0, 20.0  # positive backward-wave magnitude, mph
TOL = 1e-10


def safe_output(path: Path) -> Path:
    out = path.resolve()
    working = (ROOT / "debug/output").resolve()
    root = ROOT.resolve()
    if root.is_relative_to(out) or (out.is_relative_to(root) and not out.is_relative_to(working)):
        raise ValueError("Use debug/output/ or a separate working folder outside canonical files.")
    marker = out / ".qvdfe-fd-parameter-sensitivity.json"
    allowed = [marker, out / '.episode-time-series-trace.json', out / '.inverse-queue-speed-trace.json']
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not any(m.is_file() for m in allowed))):
        raise ValueError("Choose an empty directory or one owned by this generator.")
    out.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"owner":"qvdfe-fd-parameter-sensitivity"}\n', encoding="utf-8")
    return out


def implied_capacity(vf: float, kj: float, omega: float) -> float:
    return vf * omega * kj / (vf + omega)


def queue_speed(mu: float, kj: float, omega: float) -> float:
    denominator = kj - mu / omega
    return mu / denominator if denominator > 0 else np.nan


def exact_wave_interval(mu: float, q: float, wave_min: float = W_MIN) -> tuple[float, float] | None:
    """Closed wave-speed interval with k_j = mu/q + mu/omega in the box."""
    if not np.isfinite(mu) or not np.isfinite(q) or mu <= 0 or q <= 0:
        return None
    density = mu / q
    if K_MAX <= density:
        return None
    lower = max(wave_min, mu / (K_MAX - density))
    upper = W_MAX
    if K_MIN > density:
        upper = min(upper, mu / (K_MIN - density))
    if lower > upper + TOL:
        return None
    if lower > upper:  # collapse a floating-point endpoint discrepancy
        lower = upper
    return float(lower), float(upper)


def attainable_queue_interval(mu: float, vf: float, q_physical_max: float, wave_min: float = W_MIN) -> tuple[float, float] | None:
    """Image of the bounded FD rectangle, intersected with finite-link validity."""
    if not all(np.isfinite([mu, vf, q_physical_max])) or min(mu, vf, q_physical_max) <= 0:
        return None
    max_denominator = K_MAX - mu / W_MAX
    if max_denominator <= 0:
        return None
    q_lower = mu / max_denominator
    min_denominator = K_MIN - mu / wave_min
    q_upper = mu / min_denominator if min_denominator > 0 else np.inf
    q_upper = min(q_upper, q_physical_max, np.nextafter(vf, 0.0))
    if q_lower > q_upper + TOL:
        return None
    if q_lower > q_upper:
        q_lower = q_upper
    return float(q_lower), float(q_upper)


def choose_pair(mu: float, vf: float, capacity: float, q: float, baseline_omega: float, wave_min: float = W_MIN) -> dict | None:
    """Keep q exact; preserve capacity if feasible, otherwise minimize its change.

    Along the exact-q curve, C*(omega) is monotone increasing for q < vf.
    Endpoint comparison plus the analytic capacity-preserving root therefore
    solves the absolute capacity-change objective without a grid search.
    """
    interval = exact_wave_interval(mu, q, wave_min)
    if interval is None or q >= vf:
        return None
    lo, hi = interval
    options = [lo, hi]
    denominator = mu / q - capacity / vf
    root = (capacity - mu) / denominator if denominator != 0 else np.nan
    if np.isfinite(root) and lo - TOL <= root <= hi + TOL:
        options.append(float(np.clip(root, lo, hi)))
    if np.isfinite(baseline_omega):
        options.append(float(np.clip(baseline_omega, lo, hi)))

    def score(w):
        k = mu / q + mu / w
        c = implied_capacity(vf, k, w)
        tie = abs(w - baseline_omega) if np.isfinite(baseline_omega) else w
        return abs(c - capacity), tie

    omega = min(options, key=score)
    kj = mu / q + mu / omega
    c = implied_capacity(vf, kj, omega)
    q_check = queue_speed(mu, kj, omega)
    assert K_MIN - TOL <= kj <= K_MAX + TOL
    assert wave_min - TOL <= omega <= W_MAX + TOL
    np.testing.assert_allclose(q_check, q, rtol=1e-11, atol=1e-11)
    assert c >= mu - TOL
    return dict(
        selected_omega_mph=float(omega), selected_kj_veh_mi_lane=float(kj),
        selected_implied_capacity_vphpl=float(c), selected_queue_speed_mph=float(q_check),
        capacity_change_vphpl=float(c - capacity), capacity_change_pct=float(100 * (c / capacity - 1)),
        baseline_capacity_preserved=bool(np.isclose(c, capacity, rtol=1e-10, atol=1e-8)),
        selected_exact_q_wave_min_mph=lo, selected_exact_q_wave_max_mph=hi,
        selected_exact_q_kj_at_wave_min=mu / q + mu / lo,
        selected_exact_q_kj_at_wave_max=mu / q + mu / hi,
        selected_exact_q_capacity_min_vphpl=implied_capacity(vf, mu / q + mu / lo, lo),
        selected_exact_q_capacity_max_vphpl=implied_capacity(vf, mu / q + mu / hi, hi),
        margin_kj_above_min=kj - K_MIN, margin_kj_below_max=K_MAX - kj,
        margin_omega_above_min=omega - wave_min, margin_omega_below_max=W_MAX - omega,
        selected_mu_over_capacity=mu / c,
    )


def basic_tests() -> dict:
    """Independent analytic cases, interval edges, and a dense capacity check."""
    mu, vf, q = 1000.0, 60.0, 10.0
    np.testing.assert_allclose(exact_wave_interval(mu, q), [5.0, 20.0])
    baseline = 60 * 10 * 200 / 70
    p = choose_pair(mu, vf, baseline, q, 10.0)
    np.testing.assert_allclose([p['selected_omega_mph'], p['selected_kj_veh_mi_lane']], [10.0, 200.0])
    assert p['baseline_capacity_preserved']
    low = choose_pair(mu, vf, 1200.0, q, 10.0)
    np.testing.assert_allclose([low['selected_omega_mph'], low['selected_kj_veh_mi_lane']], [5.0, 300.0])
    high = choose_pair(mu, vf, 2600.0, q, 10.0)
    np.testing.assert_allclose([high['selected_omega_mph'], high['selected_kj_veh_mi_lane']], [20.0, 150.0])
    np.testing.assert_allclose(exact_wave_interval(2000.0, 10.0), [20.0, 20.0])
    assert exact_wave_interval(2000.0, 5.0) is None
    assert attainable_queue_interval(2000.0, 60.0, 8.0) is None
    assert attainable_queue_interval(7000.0, 60.0, 50.0) is None
    np.testing.assert_allclose(attainable_queue_interval(1000.0, 60.0, 40.0), [4.0, 40.0])
    grid = np.linspace(5.0, 20.0, 10001)
    capacities = vf * mu * (grid / q + 1) / (vf + grid)
    for capacity in [1200.0, baseline, 2000.0, 2600.0]:
        pair = choose_pair(mu, vf, capacity, q, 10.0)
        assert abs(pair['capacity_change_vphpl']) <= np.min(abs(capacities-capacity)) + 1e-8
    return {"analytic_capacity_preservation": True, "capacity_boundaries": True,
            "singleton_interval": True, "infeasible_target_and_box": True,
            "attainable_interval": True, "dense_capacity_objective_check": True}


def stable_pair(pair, frozen, desired_q, qmax, wave_min, rates, inverse):
    """Preserve the lookup side when FD arithmetic lands one ulp away from q.

    The selected emissions are always evaluated at the reconstructed FD speed.
    This small representable-neighbor search only resolves floating-point edge
    cases; it is not an extra optimization or a relaxation of the bounds.
    """
    expected = inverse.emissions_at_speed(frozen, desired_q, rates)
    mu, vf, capacity = frozen.mu_hat_vphpl, frozen.vf_mph, frozen.C_vphpl

    def candidate(k, w):
        if not (K_MIN <= k <= K_MAX and wave_min <= w <= W_MAX):
            return None
        q = queue_speed(mu, k, w)
        if not (0 < q <= qmax and q < vf):
            return None
        emissions = inverse.emissions_at_speed(frozen, q, rates)
        if not np.allclose(emissions, expected, rtol=1e-9, atol=1e-8):
            return None
        c = implied_capacity(vf, k, w)
        return (abs(q-desired_q), abs(c-capacity), k, w, q, c, emissions)

    k0, w0 = pair['selected_kj_veh_mi_lane'], pair['selected_omega_mph']
    found = candidate(k0, w0)
    adjusted = found is None
    if found is None:
        def neighbors(value):
            lower, upper = value, value
            values = [value]
            for _ in range(4):
                lower = np.nextafter(lower, -np.inf)
                upper = np.nextafter(upper, np.inf)
                values.extend([lower, upper])
            return values
        choices = [candidate(k,w) for k in neighbors(k0) for w in neighbors(w0)]
        choices = [c for c in choices if c is not None]
        if not choices:
            raise AssertionError('No bounded floating-point FD pair preserves the target lookup side')
        found = min(choices, key=lambda c:c[:2])
    _, _, k, w, q, c, emissions = found
    np.testing.assert_allclose(q, desired_q, rtol=1e-11, atol=1e-11)
    pair.update(selected_kj_veh_mi_lane=float(k), selected_omega_mph=float(w),
                selected_queue_speed_mph=float(q), selected_implied_capacity_vphpl=float(c),
                capacity_change_vphpl=float(c-capacity), capacity_change_pct=float(100*(c/capacity-1)),
                baseline_capacity_preserved=bool(np.isclose(c,capacity,rtol=1e-10,atol=1e-8)),
                margin_kj_above_min=float(k-K_MIN), margin_kj_below_max=float(K_MAX-k),
                margin_omega_above_min=float(w-wave_min), margin_omega_below_max=float(W_MAX-w),
                selected_mu_over_capacity=float(mu/c), floating_boundary_adjustment=adjusted,
                desired_minus_reconstructed_q_mph=float(desired_q-q))
    return pair, emissions


def summarize(frame, grouping):
    rows=[]
    for key, g in frame.groupby(grouping, dropna=False, sort=True):
        key=key if isinstance(key,tuple) else (key,)
        selected=g.q_selected_mph.notna()
        changed=g.loc[selected,'capacity_change_pct'].abs()
        row=dict(zip(grouping,key))
        row.update(rows=len(g), episodes=g.episode_id.nunique(),
                   exact_target_feasible=int(g.exact_target_feasible.sum()),
                   exact_target_feasible_pct=float(100*g.exact_target_feasible.mean()),
                   bounded_reoptimized=int(g.bounded_objective_reoptimized.sum()),
                   no_physical_fd_pair=int((~selected).sum()),
                   selected_capacity_preserved=int(g.baseline_capacity_preserved.fillna(False).sum()),
                   exact_target_and_capacity_preserved=int((g.exact_target_feasible&g.baseline_capacity_preserved.fillna(False)).sum()),
                   original_fitted_pair_within_bounds=int(g.original_fitted_pair_within_bounds.sum()),
                   median_abs_capacity_change_pct=float(changed.median()) if len(changed) else np.nan,
                   maximum_abs_capacity_change_pct=float(changed.max()) if len(changed) else np.nan,
                   selected_capacity_change_above_10pct=int((changed>10).sum()),
                   median_selected_CO2_ape_pct=float(g.loc[selected,'selected_CO2_ape_pct'].median()) if selected.any() else np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


def build(out: Path, inverse_path: Path | None = None):
    """Write bounded FD diagnostics after the inverse table has been generated."""
    out=safe_output(out)
    inverse_path=Path(inverse_path) if inverse_path is not None else out/'inverse_queue_speed.csv'
    if not inverse_path.is_file():
        raise FileNotFoundError(f'Generate the inverse diagnostic first: {inverse_path}')
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    import build_inverse_queue_speed as inverse
    tests=basic_tests()
    source=ROOT/'data/frozen/calibration/average_weekday/episode_results_v2.csv'
    frozen=pd.read_csv(source)
    frozen=frozen[frozen.matched_ladder_pass]
    frozen_rows={r.episode_id:r for r in frozen.itertuples(index=False)}
    targets=pd.read_csv(inverse_path)
    assert len(targets)==274 and targets.episode_id.nunique()==137
    assert set(targets.strategy)=={'co2_target','balanced_four_pollutants'}
    assert not targets.duplicated(['episode_id','strategy']).any()
    rates=inverse.canonical_rates()
    metadata_path=out/'traffic_parameters.csv'
    metadata={}
    if metadata_path.is_file():
        meta=pd.read_csv(metadata_path)
        for r in meta.itertuples(index=False):
            metadata[r.episode_id]=dict(metadata_capacity_vphpl=getattr(r,'metadata_capacity_vphpl',np.nan),
                                        metadata_capacity_available=bool(getattr(r,'metadata_capacity_available',False)))
    all_rows=[]
    for bounds_name,wave_min in [('primary',5.0),('expanded_lower_wave',3.0)]:
        for t in targets.itertuples(index=False):
            f=frozen_rows[t.episode_id]
            mu,vf,C,qtarget,qmax=(float(t.baseline_mu_vphpl),float(t.vf_mph),float(t.baseline_C_vphpl),float(t.q_inverse_mph),float(t.q_physical_max_mph))
            np.testing.assert_allclose(mu,f.D_veh/f.P_hat_h,rtol=1e-10,atol=1e-10)
            np.testing.assert_allclose(qmax,f.L_mi/(f.Tf_h+f.wt2_hat_h),rtol=1e-10,atol=1e-10)
            observed=np.array([getattr(f,'O_'+p) for p in inverse.POLS])
            original=np.array([getattr(f,'M_'+p) for p in inverse.POLS])
            achievable=attainable_queue_interval(mu,vf,qmax,wave_min)
            interval=exact_wave_interval(mu,qtarget,wave_min) if 0<qtarget<=qmax else None
            exact=interval is not None
            r={k:getattr(t,k) for k in ['case_id','episode_id','corridor','sensor_uid','date','period','strategy']}
            r.update(bounds_profile=bounds_name, density_lower_veh_mi_lane=K_MIN,density_upper_veh_mi_lane=K_MAX,
                     wave_lower_mph=wave_min,wave_upper_mph=W_MAX,q_target_mph=qtarget,q_fitted_mph=float(t.q_fitted_mph),
                     q_physical_max_mph=qmax,vf_mph=vf,baseline_mu_vphpl=mu,baseline_C_vphpl=C,
                     baseline_kj_veh_mi_lane=float(t.baseline_kj_veh_mi_lane),baseline_omega_mph=float(t.baseline_omega_mph),
                     baseline_P_h=float(t.baseline_P_h),D_veh_per_lane=float(f.D_veh),
                     inverse_solution_status=t.solution_status,inverse_target_objective=float(t.objective_value),
                     inverse_target_objective_infimum=float(t.objective_infimum),exact_target_feasible=bool(exact),
                     target_wave_min_mph=interval[0] if exact else np.nan,target_wave_max_mph=interval[1] if exact else np.nan,
                     attainable_q_min_mph=achievable[0] if achievable else np.nan,
                     attainable_q_max_mph=achievable[1] if achievable else np.nan,
                     original_fitted_pair_within_bounds=bool(K_MIN<=t.baseline_kj_veh_mi_lane<=K_MAX and wave_min<=t.baseline_omega_mph<=W_MAX),
                     bounded_objective_reoptimized=False,baseline_capacity_preserved=False,
                     q_selected_mph=np.nan,q_target_residual_mph=np.nan,capacity_change_pct=np.nan,
                     fd_status='no_physical_fd_pair',selected_CO2_ape_pct=np.nan,
                     frozen_delay_duration_and_discharge_preserved=True,
                     changed_fd_capacity_not_used_in_qvdf_calibration=True)
            r.update(metadata.get(t.episode_id,dict(metadata_capacity_vphpl=np.nan,metadata_capacity_available=False)))
            if exact:
                assert achievable is not None
                desired=qtarget
                selection=dict(solution_status=t.solution_status,objective_value=t.objective_value,
                               objective_infimum=t.objective_infimum,limit_attained=t.limit_attained,
                               selected_limit_mph=t.selected_limit_mph,selected_limit_side=t.selected_limit_side)
            elif achievable is not None:
                selection=inverse.solve_restricted_interval(f,t.strategy,*achievable,rates=rates)
                desired=float(selection['q_inverse_mph'])
                r['bounded_objective_reoptimized']=True
            else:
                for j,p in enumerate(inverse.POLS):
                    r['O_'+p+'_g']=observed[j]
                    r['original_M_'+p+'_g']=original[j]
                    r['selected_M_'+p+'_g']=np.nan
                    r['selected_'+p+'_error_pct']=np.nan
                    r['selected_'+p+'_ape_pct']=np.nan
                all_rows.append(r)
                continue
            pair=choose_pair(mu,vf,C,desired,float(t.baseline_omega_mph),wave_min)
            assert pair is not None
            pair,emissions=stable_pair(pair,f,desired,qmax,wave_min,rates,inverse)
            r.update(pair)
            q=pair['selected_queue_speed_mph']
            r.update(q_selected_mph=q,q_target_residual_mph=q-qtarget,
                     selected_solution_status=selection['solution_status'],
                     selected_objective_infimum=float(selection['objective_infimum']),
                     selected_limit_attained=bool(selection['limit_attained']),
                     selected_limit_mph=float(selection['selected_limit_mph']),
                     selected_limit_side=selection['selected_limit_side'],
                     selected_peak_free_time_h=f.Tf_h-q*f.wt2_hat_h/(vf-q),
                     margin_q_below_physical_max_mph=qmax-q,
                     selected_duration_closure_residual_veh=float(mu*f.P_hat_h-f.D_veh))
            rel=emissions/observed-1
            objective=float(abs(rel[0])) if t.strategy=='co2_target' else float(np.mean(rel**2))
            np.testing.assert_allclose(objective,selection['objective_value'],rtol=1e-7,atol=1e-10)
            assert r['selected_peak_free_time_h']>=-1e-10
            r['selected_objective_value']=objective
            r['selected_balanced_objective']=float(np.mean(rel**2))
            r['selected_CO2_matches_proxy']=bool(abs(rel[0])<=1e-10)
            r['fd_status']=('exact_target_' if exact else 'bounded_objective_')+('capacity_preserved' if r['baseline_capacity_preserved'] else 'capacity_changed')
            if r['metadata_capacity_available'] and np.isfinite(r['metadata_capacity_vphpl']) and r['metadata_capacity_vphpl']>0:
                r['selected_capacity_minus_metadata_pct']=100*(r['selected_implied_capacity_vphpl']/r['metadata_capacity_vphpl']-1)
            else:
                r['selected_capacity_minus_metadata_pct']=np.nan
            for j,p in enumerate(inverse.POLS):
                r['O_'+p+'_g']=float(observed[j]);r['original_M_'+p+'_g']=float(original[j])
                r['selected_M_'+p+'_g']=float(emissions[j]);r['selected_'+p+'_error_pct']=float(100*rel[j])
                r['selected_'+p+'_ape_pct']=float(100*abs(rel[j]))
            all_rows.append(r)
    full=pd.DataFrame(all_rows)
    primary=full[full.bounds_profile.eq('primary')].copy()
    expanded=full[full.bounds_profile.eq('expanded_lower_wave')].copy()
    assert len(primary)==len(expanded)==274
    primary.to_csv(out/'fd_parameter_sensitivity.csv',index=False)
    expanded.to_csv(out/'fd_parameter_sensitivity_expanded.csv',index=False)
    summary=summarize(full,['bounds_profile','strategy','corridor'])
    summary.to_csv(out/'fd_sensitivity_summary.csv',index=False)
    bound_summary=summarize(full,['bounds_profile','strategy'])
    bound_summary.to_csv(out/'fd_bound_sensitivity_summary.csv',index=False)
    sources=[dict(title='Laval and Daganzo (2006), Lane-changing in traffic streams',
                  url='https://www.sciencedirect.com/science/article/pii/S019126150500055X',
                  example='Section 3 numerical experiments use jam density 150 veh/mi/lane and congested wave speed -15 mph.',
                  access_note='Verified from the publisher-indexed section snippet; full open returned HTTP 403.'),
             dict(title='GDOT FHWA-GA-19-1414 (2019), Travel-time Optimization on I-285',
                  url='https://rosap.ntl.bts.gov/view/dot/40155/dot_40155_DS1.pdf',
                  example='Table 5 (printed p.54; PDF p.64) reports density 150 veh/km and wave speed 20 km/h, equivalent to 241.402 veh/mi and 12.427 mph.',
                  access_note='The table labels density veh/km without explicitly appending /lane; no universal bound or lane-basis validation is inferred.')]
    assumptions=dict(primary=dict(kj_min=K_MIN,kj_max=K_MAX,omega_min=5.0,omega_max=W_MAX),
                     expanded_lower_wave=dict(kj_min=K_MIN,kj_max=K_MAX,omega_min=3.0,omega_max=W_MAX),
                     density_unit='veh/mi/lane',omega_unit='mph, positive magnitude of a backward wave',
                     interpretation='Exploratory sensitivity bounds. Literature examples motivate scale only; they do not validate every pair in either box.',
                     pair_policy='Hold current D/P_hat fixed. Preserve an attainable inverse target q; choose the pair with minimum absolute capacity change. If q is outside the FD-attainable physical interval, reoptimize the same emission objective over that interval before choosing the capacity-closest pair.',
                     capacity_warning='A changed implied FD capacity is reported but never fed back into frozen QVDF loading, duration, or delay calibration.',
                     inverse_warning='Matching the inverse target speed does not imply exact emission matching: some inverse objectives have residual error or an unattained one-sided infimum.',
                     numerical_tolerance=TOL,floating_boundary_policy='At most four representable neighbors per direction in kj and omega preserve the correct lookup side; exported emissions always use the reconstructed FD speed.',sources=sources)
    (out/'fd_parameter_bounds.json').write_text(json.dumps(assumptions,indent=2)+'\n',encoding='utf-8')
    present=full.q_selected_mph.notna()
    hashes={'inverse_queue_speed.csv':hashlib.sha256(inverse_path.read_bytes()).hexdigest(),
            source.relative_to(ROOT).as_posix():hashlib.sha256(source.read_bytes()).hexdigest()}
    if metadata_path.is_file():hashes['traffic_parameters.csv']=hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    verification=dict(all_checks_passed=True,analytic_tests=tests,primary_rows=len(primary),expanded_rows=len(expanded),
                      episodes=targets.episode_id.nunique(),strategies=sorted(targets.strategy.unique()),
                      selected_pairs=int(present.sum()),no_physical_pair=int((~present).sum()),
                      maximum_duration_closure_residual_veh=float(full.loc[present,'selected_duration_closure_residual_veh'].abs().max()),
                      maximum_fd_target_rounding_residual_mph=float(full.loc[present,'desired_minus_reconstructed_q_mph'].abs().max()),
                      floating_lookup_boundary_adjustments=int(full.loc[present,'floating_boundary_adjustment'].sum()),
                      minimum_peak_free_time_h=float(full.loc[present,'selected_peak_free_time_h'].min()),
                      capacity_minimization='Analytic monotone objective; independent dense-grid synthetic tests pass.',
                      calibration_modified=False,emission_reference='Observed-speed lookup proxy, not measured trajectory or exhaust emissions.',
                      input_sha256=hashes)
    (out/'fd_sensitivity_verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
    lines=['# Bounded FD sensitivity: diagnostic interpretation','',
           'The two bounds are exploratory assumptions. These calculations hold fitted discharge, duration and delay fixed; they are not a new calibration.', '']
    for _,z in bound_summary.iterrows():
        lines.append(f"- {z.bounds_profile}, {z.strategy}: {int(z.exact_target_feasible)}/137 inverse speeds are exactly attainable; {int(z.exact_target_and_capacity_preserved)} also preserve baseline capacity. {int(z.bounded_reoptimized)} require the emission objective to be reoptimized within the bounds; {int(z.no_physical_fd_pair)} have no physical bounded pair.")
    primary_summary=bound_summary[bound_summary.bounds_profile.eq('primary')].set_index('strategy')
    if len(primary_summary)==2:
        c=primary_summary.loc['co2_target'];b=primary_summary.loc['balanced_four_pollutants']
        lines.extend(['',f"Most target speeds fit the exploratory box, but only {int(c.exact_target_and_capacity_preserved)} CO2-target cases and {int(b.exact_target_and_capacity_preserved)} balanced cases preserve the original capacity. The largest absolute capacity change is {c.maximum_abs_capacity_change_pct:.1f}% for the CO2 target versus {b.maximum_abs_capacity_change_pct:.1f}% for the balanced objective. Feasible FD values therefore do not by themselves establish a defensible permanent correction."])
    lines.extend(['','Use the primary-versus-expanded comparison to assess sensitivity to the lower wave-speed bound. Compare capacity changes, the retained traffic fit and pollutant-specific residuals before considering a new FD. If the proposal changes implied capacity, a subsequent corridor-level joint calibration and validation is needed before altering the production FD. Per-episode inverse pairs are explanatory diagnostics, not recommended per-episode parameters.',''])
    (out/'fd_sensitivity_recommendation.md').write_text('\n'.join(lines),encoding='utf-8')
    return verification


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'debug/output/fd_parameter_sensitivity')
    parser.add_argument('--inverse-path',type=Path,default=None)
    args=parser.parse_args()
    print(json.dumps(build(args.output,args.inverse_path),indent=2))
