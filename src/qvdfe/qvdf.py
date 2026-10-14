"""Demand-dependent service and emission response (paper Section 4, Eqs. 13-20)."""
import numpy as np

from .states import queue_speed
from .emission import gamma_cubic, cubic_rate


def qvdf(x, fd, n, fp, s, theta):
    """Calibrated QVDF. x = D/C (h). Returns (P in h, fp P^s, theta fp P^s); multiply the last two by Tf for the
    peak and mean delay in hours. P = max(fd x^n, x) (Eq. 13). Same as v15_model.qvdf."""
    x = np.asarray(x, float)
    P = np.maximum(fd * x ** n, x)
    return P, fp * P ** s, theta * fp * P ** s


def response(card, x, coef, kj=None):
    """Response of one calibrated card at loading x (h) for one pollutant's cubic rate ``coef``.

    ``card`` needs fd, n, fp, s, theta, C (veh/h/lane), vf (mph), L (mi) and optionally kj (veh/mi/lane, default 220).
    Follows v15_model.cost_values: mu = C x / P, vq from the FD, peak delay Tf fp P^s, mean delay Tf theta fp P^s,
    Gamma at vq, beta = n s, eps_Gamma = x Gamma'(x)/Gamma (defined only where Gamma != 0),
    increment elasticity beta + eps_Gamma, emission increment wbar Gamma (g/veh), marginal emission
    dE/dD = e + x e'(x) (g per added vehicle, capacity and calibration held fixed). Scalars only.
    ``valid`` checks the admissible power branch: fd x^n > x, 5 <= vq < vf <= 75 mph (the rate table's range) and
    the peak delay within the finite-link allowance (Eq. 9). It does not check the nonnegative-arrival condition of
    the reconstructed profile (``qvdfe.delay_profile`` reports analytic lambda_min for that), observation QC,
    outliers or positive totals. Use ``qvdfe.screen_episode`` for the complete v19 matched-comparison mask.
    This limited response flag is the same check as v19 cost_values.valid. Derivatives returned with valid=False
    must not be interpreted on the capacity branch; the derivative formulas assume the power branch.
    """
    if x <= 0:
        raise ValueError('loading x = D/C must be positive')
    fd, n, fp, s, theta = (float(card[k]) for k in ('fd', 'n', 'fp', 's', 'theta'))
    C, vf, L = float(card['C']), float(card['vf']), float(card['L'])
    kj = float(kj if kj is not None else card.get('kj', 220.0) or 220.0)
    P, severity, _ = qvdf(x, fd, n, fp, s, theta)
    P = float(P)
    mu = C * x / P
    vq, kq, _ = queue_speed(mu, C, vf, kj)
    vq, kq = float(vq), float(kq)
    Tf = L / vf
    peak = Tf * float(severity)
    wbar = Tf * theta * fp * P ** s
    bound = L * (1 / vq - 1 / vf)
    power = fd * x ** n > x * (1 + 1e-10)
    valid = bool(power and 5 <= vq < vf <= 75 and peak <= bound + 1e-10)
    G = float(gamma_cubic(vq, vf, coef))
    _, _, c2, c3 = np.asarray(coef, float)
    dG_dvq = -c2 * vf - c3 * vf * (vf + 2 * vq)
    direct = (1 - n) * kj / kq * vq * dG_dvq          # x dGamma/dx through vq(x)
    beta = n * s
    eps = direct / G if abs(G) > 1e-9 else float('nan')
    e = float(cubic_rate(vf, coef)) * Tf + wbar * G
    return {'valid': valid, 'P': P, 'mu': mu, 'vq': vq, 'kq': kq, 'Tf': Tf, 'peak_delay': peak, 'mean_delay': wbar,
            'allowance': bound, 'Gamma': G, 'beta': beta, 'eps_Gamma': eps, 'increment_elasticity': beta + eps,
            'increment_g': wbar * G, 'e_g': e, 'marginal_g': e + wbar * (beta * G + direct),
            'external_g': wbar * (beta * G + direct)}
