"""Inverse queue-speed diagnostics for the preserved 137 emission episodes.

Two common-speed strategies are evaluated: match CO2, and minimize the equally
weighted mean squared relative error across all four pollutants. No calibration
or observed input is changed. The exact piecewise lookup, rather than a speed
grid or interpolation across rate jumps, determines the candidates.
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
SOURCE = ROOT / "data/frozen/calibration/average_weekday/episode_results_v2.csv"
RATE_DIR = ROOT / "data/frozen/calibration/emission_input"
POLS = ("CO2", "NOx", "CO", "HC")
MARKERS = (".inverse-queue-speed-trace.json", ".episode-time-series-trace.json")
POSITIVE_LIMIT_SPEED_MPH = 1e-8
BOUNDARY_INTERIOR_OFFSET_MPH = 1e-8
EMISSION_RTOL = 1e-10
EMISSION_ATOL_G = 1e-8


def safe_location(path: Path) -> Path:
    out = path.resolve()
    root, work = ROOT.resolve(), (ROOT / "debug/output").resolve()
    if root.is_relative_to(out) or (out.is_relative_to(root) and not out.is_relative_to(work)):
        raise ValueError("Output must be in debug/output or a separate working directory.")
    return out


def prepare_output(path: Path) -> Path:
    out = safe_location(path)
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not any((out/m).is_file() for m in MARKERS))):
        raise ValueError("Output is nonempty and is not owned by this diagnostic or the episode generator.")
    out.mkdir(parents=True, exist_ok=True)
    (out/MARKERS[0]).write_text('{"owner":"qvdfe-inverse-queue-speed"}\n', encoding="utf-8")
    return out


def vsp(speed, vehicle):
    s = np.asarray(speed, float)*0.44704
    return (vehicle["rolling_term_a"]*s+vehicle["rotating_term_b"]*s**2
            + vehicle["drag_term_c"]*s**3)/vehicle["source_mass"]


def first_float_at_vsp(threshold, lo, hi, vehicle):
    """First floating-point speed meeting the canonical >= VSP threshold."""
    assert float(vsp(lo, vehicle)) < threshold <= float(vsp(hi, vehicle))
    for _ in range(200):
        if np.nextafter(lo, hi) >= hi:
            break
        mid = lo+(hi-lo)/2
        if mid == lo or mid == hi:
            break
        if float(vsp(mid, vehicle)) >= threshold:
            hi = mid
        else:
            lo = mid
    assert float(vsp(hi, vehicle)) >= threshold
    assert float(vsp(np.nextafter(hi, 0.), vehicle)) < threshold
    return float(hi)


def lookup_intervals(qmax, vehicle, mode_function, qmin=0.):
    """Actual positive-speed lookup intervals, including a closed physical end."""
    assert 0 <= qmin <= qmax
    if qmin == qmax:
        return [dict(lower=qmin, upper=qmax, lower_closed=True, upper_closed=True,
                     mode=int(mode_function(qmin, float(vsp(qmin, vehicle)))))]
    cuts = {float(qmin), float(qmax)}
    for lo, hi, thresholds in [(0., 25., (0, 3, 6, 9, 12)),
                               (25., 50., (0, 3, 6, 9, 12, 18, 24, 30)),
                               (50., max(100., qmax+1), (6, 12, 18, 24, 30))]:
        if qmin < lo < qmax:
            cuts.add(lo)
        for threshold in thresholds:
            if float(vsp(lo, vehicle)) < threshold < float(vsp(hi, vehicle)):
                boundary = first_float_at_vsp(threshold, lo, hi, vehicle)
                if qmin < boundary < qmax:
                    cuts.add(boundary)
    cuts = sorted(cuts)
    intervals = []
    for lo, hi in zip(cuts[:-1], cuts[1:]):
        middle = lo+(hi-lo)/2
        mode = int(mode_function(middle, float(vsp(middle, vehicle))))
        upper_closed = hi == qmax and mode_function(hi, float(vsp(hi, vehicle))) == mode
        intervals.append(dict(lower=lo, upper=hi, lower_closed=lo > 0,
                              upper_closed=upper_closed, mode=mode))
    # If qmax itself is a mode boundary, its new-mode point belongs to the domain.
    if not intervals[-1]["upper_closed"]:
        mode = int(mode_function(qmax, float(vsp(qmax, vehicle))))
        intervals.append(dict(lower=qmax, upper=qmax, lower_closed=True,
                              upper_closed=True, mode=mode))
    return intervals


def in_interval(q, interval):
    return ((q >= interval["lower"] if interval["lower_closed"] else q > interval["lower"])
            and (q <= interval["upper"] if interval["upper_closed"] else q < interval["upper"]))


def below_boundary(upper, lower):
    """Stable interior representative; one-ulp points can round across CSV jumps."""
    return float(upper-min(BOUNDARY_INTERIOR_OFFSET_MPH, (upper-lower)/2))


def clamp_physical_roundoff(q, physical_max):
    """Allow CSV roundoff only, never a material relaxation of the physical bound."""
    if q > physical_max and q-physical_max <= 8*np.spacing(physical_max):
        return physical_max
    return q


def canonical_rates():
    """Load the maintained age-weighted lookup, for use by companion diagnostics."""
    if str(ROOT/"src") not in sys.path:
        sys.path.insert(0, str(ROOT/"src"))
    from qvdfe.rates import lookup_rates
    return lookup_rates(RATE_DIR, vehicle_type=1)


def emissions_at_speed(row, q, rates=None):
    """Return M(q) in grams in POLS order, using a frozen episode row.

    The row may be a pandas Series or named tuple. This is the same fixed-delay
    conditional calculation as the main inverse diagnostic, not a traffic refit.
    """
    if rates is None:
        rates = canonical_rates()
    D, L, vf = float(row.D_veh), float(row.L_mi), float(row.vf_mph)
    mean, peak = float(row.wbar_hat_h), float(row.wt2_hat_h)
    Tf = L/vf
    qmax = L/(Tf+peak)
    q = clamp_physical_roundoff(q, qmax)
    if not 0 < q <= qmax:
        raise ValueError("Queue speed lies outside the peak-delay physical domain")
    tq = vf*mean/(vf-q); tf = Tf-q*mean/(vf-q)
    return np.asarray([D*(tf*float(rates[p](vf))+tq*float(rates[p](q))) for p in POLS])


def solve_restricted_interval(row, strategy, lower_q, upper_q, rates=None):
    """Solve either objective over a closed positive-speed subinterval.

    Intended for the bounded-FD sensitivity analysis. Rate jumps are handled
    exactly as in the unrestricted analysis. The returned residuals are for the
    actual selected speed; an unattained left-limit objective is separate.
    This function writes no files and does not change the frozen episode.
    """
    if strategy not in ("co2_target", "balanced_four_pollutants"):
        raise ValueError("Unknown inverse-emission strategy")
    if rates is None:
        rates = canonical_rates()
    from qvdfe.rates import _op_mode
    D, L, vf = float(row.D_veh), float(row.L_mi), float(row.vf_mph)
    Tf, mean = L/vf, float(row.wbar_hat_h)
    physical_max = L/(Tf+float(row.wt2_hat_h))
    upper_q = clamp_physical_roundoff(upper_q, physical_max)
    lower_q = clamp_physical_roundoff(lower_q, physical_max)
    if not 0 < lower_q <= upper_q <= physical_max:
        raise ValueError("Require 0 < lower_q <= upper_q <= physical queue-speed maximum")
    vehicle = rates["CO2"].vehicle_params
    qfit = float(row.vq_hat_mph)
    observed = np.asarray([getattr(row, "O_"+p) for p in POLS])
    rf = np.asarray([float(rates[p](vf)) for p in POLS])
    A = D*(Tf+mean)*rf
    a = A/observed-1
    candidate_rows, exact_roots = [], []
    intervals = lookup_intervals(upper_q, vehicle, _op_mode, qmin=lower_q)

    def add(q, interval, kind, limit_q=None, side="", attained=True, exact=False):
        assert in_interval(q, interval) and 0 < q <= physical_max
        assert _op_mode(q, float(vsp(q, vehicle))) == interval["mode"]
        E = emissions_at_speed(row, q, rates)
        rj = np.asarray([rates[p].mode_rates[interval["mode"]] for p in POLS])
        B = D*vf*mean*(rj-rf)
        qlim = q if limit_q is None else limit_q
        Elim = A+B/(vf-qlim)
        delta, delta_limit = E/observed-1, Elim/observed-1
        result = dict(q_inverse_mph=float(q), candidate_type=kind,
            selected_limit_mph=float(qlim), selected_limit_side=side, limit_attained=attained,
            operating_mode=interval["mode"], distance_from_fitted_mph=abs(q-qfit),
            co2_absolute_relative_error=float(abs(delta[0])),
            co2_limit_absolute_relative_error=float(abs(delta_limit[0])),
            balanced_objective=float(np.mean(delta**2)),
            balanced_limit_objective=float(np.mean(delta_limit**2)),
            inverse_emissions_g={p: float(v) for p, v in zip(POLS, E)})
        candidate_rows.append(result)
        if exact:
            np.testing.assert_allclose(E[0], observed[0], rtol=EMISSION_RTOL, atol=EMISSION_ATOL_G)
            exact_roots.append(result)

    for interval in intervals:
        lo, hi = interval["lower"], interval["upper"]
        add(lo, interval, "closed_lower_endpoint")
        if hi != lo:
            highq = hi if interval["upper_closed"] else below_boundary(hi, lo)
            add(highq, interval, "closed_upper_endpoint" if interval["upper_closed"] else "left_jump_limit",
                limit_q=hi, side="" if interval["upper_closed"] else "below", attained=interval["upper_closed"])
        if in_interval(qfit, interval):
            add(qfit, interval, "current_fitted_speed")
        rj = np.asarray([rates[p].mode_rates[interval["mode"]] for p in POLS])
        B = D*vf*mean*(rj-rf); b = B/observed
        if B[0] != 0 and observed[0] != A[0]:
            qroot = vf-B[0]/(observed[0]-A[0])
            if np.isfinite(qroot) and in_interval(qroot, interval):
                add(float(qroot), interval, "CO2_algebraic_root", exact=True)
        elif B[0] == 0 and abs(observed[0]-A[0]) <= max(EMISSION_ATOL_G, EMISSION_RTOL*observed[0]):
            qroot = max(lo, min(qfit, hi))
            if not interval["upper_closed"] and qroot == hi:
                qroot = below_boundary(hi, lo)
            add(float(qroot), interval, "CO2_flat_exact_interval", exact=True)
        den = float(b@b)
        if den:
            zstar = -float(a@b)/den
            if zstar > 0:
                qstar = vf-1/zstar
                if in_interval(qstar, interval):
                    add(float(qstar), interval, "balanced_stationary_point")
        else:
            qstar = max(lo, min(qfit, hi))
            if not interval["upper_closed"] and qstar == hi:
                qstar = below_boundary(hi, lo)
            add(float(qstar), interval, "balanced_flat_interval")
    objective = "co2_absolute_relative_error" if strategy == "co2_target" else "balanced_objective"
    limit_objective = "co2_limit_absolute_relative_error" if strategy == "co2_target" else "balanced_limit_objective"
    if strategy == "co2_target" and exact_roots:
        selected = min(exact_roots, key=lambda r: (r["distance_from_fitted_mph"], r["q_inverse_mph"]))
        status, infimum = "exact_root", 0.
    else:
        best = min(c[limit_objective] for c in candidate_rows)
        tolerance = 64*np.finfo(float).eps*max(1., abs(best))
        tied = [c for c in candidate_rows if c[limit_objective] <= best+tolerance]
        selected = min(tied, key=lambda r: (r["distance_from_fitted_mph"], r["q_inverse_mph"]))
        status = ("attained_closest" if strategy == "co2_target" else "attained_minimum") if selected["limit_attained"] else "boundary_limit_approximation"
        infimum = best
    result = dict(selected)
    result.update(strategy=strategy, solution_status=status, objective_value=selected[objective],
                  objective_infimum=infimum, selection_objective=objective, CO2_root_count=len(exact_roots),
                  lower_q_mph=float(lower_q), upper_q_mph=float(upper_q), candidate_count=len(candidate_rows),
                  observed_emissions_g={p: float(v) for p, v in zip(POLS, observed)})
    return result


def build(out: Path):
    """Write diagnostic CSVs/JSON into an existing, explicitly owned output folder."""
    out = safe_location(out)
    if not out.is_dir() or not any((out/m).is_file() for m in MARKERS):
        raise ValueError("build(out) requires an existing owned output directory.")
    sys.path.insert(0, str(ROOT/"src"))
    from qvdfe.rates import lookup_rates, _op_mode

    rates = lookup_rates(RATE_DIR, vehicle_type=1)
    vehicle = rates["CO2"].vehicle_params
    ep = pd.read_csv(SOURCE)
    ep = ep.loc[ep.matched_ladder_pass].sort_values("episode_id")
    assert len(ep) == 137
    summaries, candidates, roots, interval_rows = [], [], [], []
    max_original_relative_error = 0.
    max_root_relative_error = 0.
    max_time_residual = 0.
    max_distance_residual = 0.
    max_mu_inverse_residual = 0.

    for ordinal, row in enumerate(ep.itertuples(index=False), 1):
        identity = dict(case_id=f"ep{ordinal:03d}", episode_id=row.episode_id,
                        corridor=row.corridor, sensor_uid=row.sensor_uid, date=row.date, period=row.period)
        D, L, vf = float(row.D_veh), float(row.L_mi), float(row.vf_mph)
        Tf, mean, peak = L/vf, float(row.wbar_hat_h), float(row.wt2_hat_h)
        qfit = float(row.vq_hat_mph)
        qmax = L/(Tf+peak)
        observed = np.array([getattr(row, "O_"+p) for p in POLS])
        original = np.array([getattr(row, "M_"+p) for p in POLS])
        rf = np.array([float(rates[p](vf)) for p in POLS])
        assert D > 0 and 0 < mean <= peak and 0 < qfit <= qmax < vf
        assert np.isfinite(observed).all() and (observed > 0).all()
        np.testing.assert_allclose(qmax, row.vt2_hat_mph, rtol=1e-10, atol=1e-10)
        A = D*(Tf+mean)*rf
        a = A/observed-1

        def evaluate(q):
            assert 0 < q <= qmax
            tq = vf*mean/(vf-q)
            tf = Tf-q*mean/(vf-q)
            rq = np.array([float(rates[p](q)) for p in POLS])
            return D*(tf*rf+tq*rq)

        actual_original = evaluate(qfit)
        np.testing.assert_allclose(actual_original, original, rtol=1e-9, atol=1e-8)
        max_original_relative_error = max(max_original_relative_error, float(np.max(abs(actual_original/original-1))))
        intervals = lookup_intervals(qmax, vehicle, _op_mode)
        local_candidates, local_roots = [], []
        next_id = 0

        def add_candidate(q, interval, interval_no, kind, *, limit_q=None, side="", attained=True):
            nonlocal next_id
            assert 0 < q <= qmax and in_interval(q, interval)
            actual_mode = _op_mode(q, float(vsp(q, vehicle)))
            assert actual_mode == interval["mode"], (q, actual_mode, interval)
            rj = np.array([rates[p].mode_rates[interval["mode"]] for p in POLS])
            B = D*vf*mean*(rj-rf)
            actual = evaluate(q)
            boundary = q if limit_q is None else limit_q
            limiting = A+B/(vf-boundary)
            relative = actual/observed-1
            limit_relative = limiting/observed-1
            candidate_id = f"{identity['case_id']}_c{next_id:03d}"
            next_id += 1
            record = dict(**identity, candidate_id=candidate_id, interval_index=interval_no,
                candidate_type=kind, operating_mode=interval["mode"], q_candidate_mph=q,
                q_limit_mph=boundary, limit_side=side, limit_attained=attained,
                lower_mph=interval["lower"], upper_mph=interval["upper"],
                lower_closed=interval["lower_closed"], upper_closed=interval["upper_closed"],
                distance_from_fitted_mph=abs(q-qfit),
                co2_absolute_relative_error=abs(relative[0]),
                co2_limit_absolute_relative_error=abs(limit_relative[0]),
                balanced_objective=float(np.mean(relative**2)),
                balanced_limit_objective=float(np.mean(limit_relative**2)))
            for j, p in enumerate(POLS):
                record[p+"_emission_g"] = actual[j]
                record[p+"_limit_emission_g"] = limiting[j]
                record[p+"_bias_pct"] = 100*relative[j]
            local_candidates.append(record)
            return record

        for interval_no, interval in enumerate(intervals, 1):
            lo, hi = interval["lower"], interval["upper"]
            rj = np.array([rates[p].mode_rates[interval["mode"]] for p in POLS])
            B = D*vf*mean*(rj-rf)
            b = B/observed
            for j, p in enumerate(POLS):
                interval_rows.append(dict(**identity, interval_index=interval_no, pollutant=p,
                    operating_mode=interval["mode"], lower_mph=lo, upper_mph=hi,
                    lower_closed=interval["lower_closed"], upper_closed=interval["upper_closed"],
                    free_rate_g_veh_h=rf[j], queue_rate_g_veh_h=rj[j], A_g=A[j], B_g_mph=B[j],
                    normalized_a=a[j], normalized_b_mph=b[j],
                    lower_limit_emission_g=A[j]+B[j]/(vf-lo),
                    upper_limit_emission_g=A[j]+B[j]/(vf-hi)))
            if lo == hi:
                add_candidate(lo, interval, interval_no, "closed_physical_endpoint")
            else:
                lowq = lo if interval["lower_closed"] else min(POSITIVE_LIMIT_SPEED_MPH, hi/2)
                add_candidate(lowq, interval, interval_no,
                              "closed_lower_endpoint" if interval["lower_closed"] else "positive_zero_limit",
                              limit_q=lo, side="" if interval["lower_closed"] else "above",
                              attained=interval["lower_closed"])
                highq = hi if interval["upper_closed"] else below_boundary(hi, lo)
                add_candidate(highq, interval, interval_no,
                              "closed_physical_endpoint" if interval["upper_closed"] else "left_jump_limit",
                              limit_q=hi, side="" if interval["upper_closed"] else "below",
                              attained=interval["upper_closed"])
            if in_interval(qfit, interval):
                add_candidate(qfit, interval, interval_no, "current_fitted_speed")

            # All roots are algebraic within a constant-rate interval. A root
            # on an excluded jump side is never accepted by a residual test.
            for j, p in enumerate(POLS):
                target_delta = observed[j]-A[j]
                if B[j] == 0:
                    if abs(target_delta) > max(EMISSION_ATOL_G, EMISSION_RTOL*observed[j]):
                        continue
                    qroot = max(lo, min(qfit, hi))
                    if not interval["lower_closed"] and qroot == lo:
                        qroot = min(POSITIVE_LIMIT_SPEED_MPH, hi/2)
                    if not interval["upper_closed"] and qroot == hi:
                        qroot = below_boundary(hi, lo)
                    kind = "flat_exact_interval"
                elif target_delta != 0:
                    qroot = vf-B[j]/target_delta
                    kind = "algebraic_root"
                else:
                    continue
                if not np.isfinite(qroot) or not in_interval(qroot, interval) or qroot <= 0:
                    continue
                eroot = evaluate(qroot)[j]
                if abs(eroot-observed[j]) > max(EMISSION_ATOL_G, EMISSION_RTOL*observed[j]):
                    raise AssertionError("An algebraic root fails the canonical emission lookup")
                record = add_candidate(float(qroot), interval, interval_no, p+"_"+kind)
                root = dict(**identity, pollutant=p, root_type=kind,
                    candidate_id=record["candidate_id"], interval_index=interval_no,
                    q_root_mph=qroot, operating_mode=interval["mode"],
                    root_emission_g=eroot, target_emission_g=observed[j],
                    residual_g=eroot-observed[j],
                    lower_mph=lo, upper_mph=hi, lower_closed=interval["lower_closed"],
                    upper_closed=interval["upper_closed"], distance_from_fitted_mph=abs(qroot-qfit))
                local_roots.append(root)
                max_root_relative_error = max(max_root_relative_error, abs(eroot/observed[j]-1))

            # With z=1/(vf-q), J=mean((a+b*z)^2) is a convex quadratic.
            # Endpoints have already been added with their proper one-sided limits.
            denominator = float(b@b)
            if denominator:
                zstar = -float(a@b)/denominator
                if zstar > 0:
                    qstar = vf-1/zstar
                    if in_interval(qstar, interval) and qstar > 0:
                        add_candidate(float(qstar), interval, interval_no, "balanced_stationary_point")
            else:
                qstar = max(lo, min(qfit, hi))
                if qstar == lo and not interval["lower_closed"]:
                    qstar = min(POSITIVE_LIMIT_SPEED_MPH, hi/2)
                if qstar == hi and not interval["upper_closed"]:
                    qstar = below_boundary(hi, lo)
                add_candidate(float(qstar), interval, interval_no, "balanced_flat_interval")

        co2roots = [r for r in local_roots if r["pollutant"] == "CO2"]
        candidate_map = {c["candidate_id"]: c for c in local_candidates}
        for strategy in ("co2_target", "balanced_four_pollutants"):
            objective = "co2_absolute_relative_error" if strategy == "co2_target" else "balanced_objective"
            limit_objective = "co2_limit_absolute_relative_error" if strategy == "co2_target" else "balanced_limit_objective"
            if strategy == "co2_target" and co2roots:
                chosen_root = min(co2roots, key=lambda r: (r["distance_from_fitted_mph"], r["q_root_mph"]))
                chosen = candidate_map[chosen_root["candidate_id"]]
                status = "exact_root" if chosen_root["root_type"] == "algebraic_root" else "exact_flat_interval"
                infimum = 0.
            else:
                # Flat-band ties must prefer proximity to the existing fitted
                # state. Within 64 floating-point ulps, differences are numerical.
                best = min(c[limit_objective] for c in local_candidates)
                tie_tol = 64*np.finfo(float).eps*max(1., abs(best))
                tied = [c for c in local_candidates if c[limit_objective] <= best+tie_tol]
                chosen = min(tied, key=lambda c: (c["distance_from_fitted_mph"], c["q_candidate_mph"]))
                infimum = best
                status = "attained_closest" if chosen["limit_attained"] else "boundary_limit_approximation"
                if strategy == "balanced_four_pollutants":
                    status = "attained_minimum" if chosen["limit_attained"] else "boundary_limit_approximation"
            qnew = float(chosen["q_candidate_mph"])
            new = evaluate(qnew)
            tq = vf*mean/(vf-qnew); tf = Tf-qnew*mean/(vf-qnew)
            peakfree = Tf-qnew*peak/(vf-qnew)
            assert tf >= -1e-12 and peakfree >= -1e-12
            max_time_residual = max(max_time_residual, abs(tf+tq-Tf-mean))
            max_distance_residual = max(max_distance_residual, abs(vf*tf+qnew*tq-L))
            C, kj = float(row.C_vphpl), float(row.kj)
            omega = C/(kj-C/vf)
            mu = D/float(row.P_hat_h)
            mu_inverse = kj*qnew*omega/(omega+qnew)
            implied_P = D/mu_inverse
            omega_denominator = kj*qnew-mu
            omega_feasible = omega_denominator > 0
            omega_inverse = mu*qnew/omega_denominator if omega_feasible else np.nan
            C_omega = kj*vf*omega_inverse/(vf+omega_inverse) if omega_feasible else np.nan
            kj_inverse = mu/qnew+mu/omega
            C_kj = kj_inverse*vf*omega/(vf+omega)
            check_q = mu_inverse/(kj-mu_inverse/omega)
            max_mu_inverse_residual = max(max_mu_inverse_residual, abs(check_q-qnew))
            np.testing.assert_allclose(check_q, qnew, rtol=1e-10, atol=1e-10)
            if omega_feasible:
                np.testing.assert_allclose(mu/(kj-mu/omega_inverse), qnew, rtol=1e-10, atol=1e-10)
            np.testing.assert_allclose(mu/(kj_inverse-mu/omega), qnew, rtol=1e-10, atol=1e-10)
            summary = dict(**identity, strategy=strategy, D_veh_per_lane=D, L_mi=L, vf_mph=vf,
                Tf_h=Tf, mean_delay_h=mean, peak_delay_h=peak,
                q_fitted_mph=qfit, q_physical_max_mph=qmax, q_inverse_mph=qnew,
                q_change_mph=qnew-qfit, q_change_pct=100*(qnew/qfit-1),
                selected_candidate_id=chosen["candidate_id"], selected_candidate_type=chosen["candidate_type"],
                solution_status=status, selected_operating_mode=chosen["operating_mode"],
                selected_limit_mph=chosen["q_limit_mph"], selected_limit_side=chosen["limit_side"],
                limit_attained=chosen["limit_attained"], CO2_root_count=len(co2roots),
                selection_objective=objective, objective_value=chosen[objective], objective_infimum=infimum,
                balanced_objective=float(np.mean((new/observed-1)**2)),
                original_balanced_objective=float(np.mean((original/observed-1)**2)),
                mean_free_time_h=tf, mean_queue_time_h=tq, peak_free_time_h=peakfree,
                baseline_mu_vphpl=mu, baseline_omega_mph=omega, baseline_kj_veh_mi_lane=kj,
                baseline_C_vphpl=C, baseline_P_h=float(row.P_hat_h),
                mu_case_mu_vphpl=mu_inverse, mu_case_implied_P_h=implied_P,
                mu_case_mu_change_pct=100*(mu_inverse/mu-1),
                mu_case_P_change_pct=100*(implied_P/float(row.P_hat_h)-1),
                mu_case_capacity_vphpl=C,
                mu_case_original_duration_closure_residual_veh=mu_inverse*float(row.P_hat_h)-D,
                omega_case_feasible=omega_feasible, omega_case_denominator_vphpl=omega_denominator,
                omega_case_omega_mph=omega_inverse, omega_case_capacity_vphpl=C_omega,
                omega_case_change_pct=100*(omega_inverse/omega-1) if omega_feasible else np.nan,
                omega_case_capacity_change_pct=100*(C_omega/C-1) if omega_feasible else np.nan,
                kj_case_kj_veh_mi_lane=kj_inverse, kj_case_capacity_vphpl=C_kj,
                kj_case_change_pct=100*(kj_inverse/kj-1), kj_case_capacity_change_pct=100*(C_kj/C-1),
                original_duration_closure_preserved=bool(np.isclose(mu_inverse, mu, rtol=1e-10, atol=1e-10)))
            for j, p in enumerate(POLS):
                summary["O_"+p+"_g"] = observed[j]
                summary["original_M_"+p+"_g"] = original[j]
                summary["inverse_M_"+p+"_g"] = new[j]
                summary["inverse_"+p+"_bias_pct"] = 100*(new[j]/observed[j]-1)
                summary["inverse_"+p+"_ape_pct"] = 100*abs(new[j]/observed[j]-1)
            summaries.append(summary)
        candidates.extend(local_candidates); roots.extend(local_roots)

    summary = pd.DataFrame(summaries)
    assert len(summary) == 274 and not summary.duplicated(["episode_id", "strategy"]).any()
    # A global optimum must be at least as good as the current fitted candidate.
    for strategy, frame in summary.groupby("strategy"):
        baseline = abs(frame.original_M_CO2_g/frame.O_CO2_g-1) if strategy == "co2_target" else frame.original_balanced_objective
        assert np.all(frame.objective_value.to_numpy() <= baseline.to_numpy()+1e-10)
    summary.to_csv(out/"inverse_queue_speed.csv", index=False, lineterminator="\n")
    pd.DataFrame(roots).to_csv(out/"inverse_queue_speed_roots.csv", index=False, lineterminator="\n")
    pd.DataFrame(candidates).to_csv(out/"inverse_queue_speed_candidates.csv", index=False, lineterminator="\n")
    pd.DataFrame(interval_rows).to_csv(out/"inverse_queue_speed_intervals.csv", index=False, lineterminator="\n")
    equations = dict(
        purpose="Conditional inverse diagnostic against O, not new calibration or measured-emission validation.",
        held_fixed=["D", "L", "vf", "Tf", "mean fitted delay", "peak fitted delay", "delay profile", "observed O totals"],
        physical_domain="0 < q <= L/(Tf+wpeak) = calibrated minimum whole-link speed; peak free time must be nonnegative.",
        time_allocation="tq=vf*wbar/(vf-q); tf=Tf-q*wbar/(vf-q). tf+tq=Tf+wbar; vf*tf+q*tq=L.",
        emission="M_p(q)=D[tf*r_p(vf)+tq*r_p(q)]. Actual age-weighted passenger-car zero-acceleration lookup.",
        interval_form="For constant r_j: M_p=A_p+B_p/(vf-q); A_p=D(Tf+wbar)r_f,p; B_p=D*vf*wbar(r_j,p-r_f,p).",
        exact_root="q=vf-B_p/(O_p-A_p), only in its actual lookup interval. B=0 gives a flat band; open endpoints never count as roots.",
        co2_selection="Nearest fitted q among all exact CO2 roots. Otherwise minimize absolute CO2 error over all interval endpoints/limits.",
        balanced_objective="J(q)=(1/4)*sum_p[(M_p(q)-O_p)/O_p]^2, p=CO2,NOx,CO,HC. One common q for all four pollutants.",
        balanced_solver="Set z=1/(vf-q), a_p=A_p/O_p-1, b_p=B_p/O_p. Within each band z*=-sum(a*b)/sum(b*b). Check feasible stationary point and both endpoint limits; no grid regression.",
        ties="At equal objective within 64 floating-point ulps of max(1,objective), choose nearest fitted q, then smaller q.",
        open_endpoints="A discontinuous half-open domain may have an unattained infimum. The selected boundary approximation has its actual error reported separately from the objective infimum.",
        zero_limit_approximation_mph=POSITIVE_LIMIT_SPEED_MPH,
        jump_left_approximation="A point 1e-8 mph below the threshold (or half the interval width if smaller), to preserve the band through ordinary CSV/Excel parsing. The theoretical left limit is recorded separately.",
        boundary_interior_offset_mph=BOUNDARY_INTERIOR_OFFSET_MPH,
        physical_bound_roundtrip_tolerance="At most 8 floating-point ulps, clamped to the physical bound by the reusable emission helper.",
        root_relative_tolerance=EMISSION_RTOL, root_absolute_tolerance_g=EMISSION_ATOL_G,
        lookup_boundaries="Threshold speeds are bracketed to adjacent floating-point values satisfying the canonical strict VSP comparisons; boundary ownership is validated against the actual mode function.",
        omega_definition="Backward congestion-wave speed magnitude omega=C/(kj-C/vf), in mph; not the emission Gamma factor.",
        inverse_mu="mu*=kj*q*omega/(omega+q), holding omega,kj. Capacity unchanged; P*=D/mu*. Original P closure generally breaks.",
        inverse_omega="omega*=mu*q/(kj*q-mu), holding current mu=D/P_hat,kj. Requires kj*q>mu; otherwise no positive finite omega. Implied capacity changes.",
        inverse_kj="kj*=mu/q+mu/omega, holding current mu=D/P_hat,omega. Implied capacity changes.",
        capacity="C*=kj*vf*omega/(vf+omega), with the varied parameter substituted for each diagnostic case.",
        warning="FD inverses are mutually exclusive conditional diagnostics. Replacing mu, omega, kj or C in the calibrated workflow would require a consistent traffic refit; this analysis does not do that.",
        joint_bounded_FD_selection="Not performed by this solver; separate sensitivity analysis.")
    (out/"inverse_queue_speed_equations.json").write_text(json.dumps(equations, indent=2)+"\n", encoding="utf-8")
    files = [SOURCE, RATE_DIR/"input_vehicle_type.csv", RATE_DIR/"input_vehicle_emission_rate.csv", ROOT/"src/qvdfe/rates.py"]
    audit = dict(episodes=137, summary_rows=len(summary), roots=len(roots), candidates=len(candidates),
        interval_pollutant_rows=len(interval_rows),
        source_sha256={f.relative_to(ROOT).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
        status_counts={s: g.solution_status.value_counts().to_dict() for s, g in summary.groupby("strategy")},
        infeasible_positive_omega_by_strategy=summary.groupby("strategy").omega_case_feasible.apply(lambda z: int((~z).sum())).to_dict(),
        max_original_M_relative_error=max_original_relative_error, max_exact_root_relative_error=max_root_relative_error,
        max_time_identity_error_h=max_time_residual, max_distance_identity_error_mi=max_distance_residual,
        max_mu_inverse_speed_error_mph=max_mu_inverse_residual,
        all_original_totals_verified=True, all_root_memberships_verified=True,
        all_selected_speeds_within_physical_bound=True, both_objectives_no_worse_than_current=True,
        backward_FD_results_are_conditional_diagnostics=True, calibration_changed=False)
    (out/"inverse_queue_speed_verification.json").write_text(json.dumps(audit, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(audit, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"debug/output/inverse_queue_speed")
    build(prepare_output(parser.parse_args().output))
