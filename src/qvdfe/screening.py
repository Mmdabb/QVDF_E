"""Explicit admission checks for the v19 matched episode-emission comparison."""
import numpy as np

from .data import POLLUTANTS
from .episode import profile_min_arrival_ratio


def screen_episode(row):
    """Recompute the complete downstream matched mask for one v19-format episode.

    ``row`` is a mapping/Series with P_hat_h, wt2_hat_h, theta, D_veh, L_mi,
    vf_mph and vq_hat_mph, the upstream calibration_eligible flag, and positive
    totals O_*, R_*, M_*, A_*, S_* for all four pollutants. No field is inferred
    from another pass flag. Missing fields fail closed.

    calibration_eligible must already include measurement QC and the selected
    outlier policy; this helper does not detect episodes or rerun those checks.
    Model admission requires finite inputs, 0 < vq < vf, the peak finite-link
    allowance, nonnegative reconstructed arrivals and 5 <= vq < vf <= 75 mph.
    The matched comparison additionally needs all 20 finite positive totals.
    Negative Gamma or congestion increments are retained. Component checks are
    reported independently; matched_ladder_pass combines all of them.
    """
    def number(key):
        try:
            return float(row.get(key, np.nan))
        except (TypeError, ValueError):
            return float('nan')

    P, peak, theta, D, L, vf, vq = (number(k) for k in (
        'P_hat_h', 'wt2_hat_h', 'theta', 'D_veh', 'L_mi', 'vf_mph', 'vq_hat_mph'))
    eligible = str(row.get('calibration_eligible', False)).strip().lower() in ('true', '1')
    finite = bool(np.isfinite([P, peak, theta, D, L, vf, vq]).all()
                  and P > 0 and peak >= 0 and D > 0 and L > 0 and vf > 0 and 0 < theta < 1)
    physical = bool(finite and 0 < vq < vf * (1 - 1e-10)
                    and peak <= L * (1 / vq - 1 / vf) + 1e-10)
    minimum = profile_min_arrival_ratio(P, peak, theta) if finite else float('nan')
    profile = bool(np.isfinite(minimum) and minimum >= -1e-10)
    domain = bool(finite and 5 <= vq < vf <= 75)
    values = [number(f'{method}_{p}') for method in ('O', 'R', 'M', 'A', 'S') for p in POLLUTANTS]
    positive = bool(np.isfinite(values).all() and np.all(np.asarray(values) > 0))
    flags = dict(calibration_eligible=eligible, model_inputs_pass=finite,
                 physical_predicted_pass=physical, profile_closed_pass=profile,
                 cubic_domain_pass=domain, positive_totals_pass=positive)
    return {**flags, 'arrival_min_relative': minimum, 'matched_ladder_pass': all(flags.values()),
            'failure_reasons': [key for key, passed in flags.items() if not passed]}
