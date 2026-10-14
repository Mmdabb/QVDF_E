"""Traffic states on the triangular fundamental diagram (paper Section 2.1, Eqs. 1-2)."""
import numpy as np


def fd_triangular(C, vf, kj=220.0):
    """Critical density and backward wave speed of the triangular FD.

    C capacity (veh/h/lane), vf free-flow speed (mph), kj jam density (veh/mi/lane; 220 is the paper's value).
    Returns (kc in veh/mi/lane, omega in mph) with C = vf*kc = omega*(kj - kc).
    """
    kc = C / vf
    if np.any(np.asarray(kc) >= np.asarray(kj)):
        raise ValueError(f'critical density C/vf must be below the jam density')
    return kc, C / (kj - kc)


def queue_speed(mu, C, vf, kj=220.0):
    """Speed of queued vehicles discharged at service rate mu (Eq. 2). Accepts arrays.

    The queue sits on the congested branch at (kq, mu): kq = kj - mu/omega, vq = mu/kq. Requires 0 < mu <= C (at mu = C
    the queue speed equals vf). Returns (vq in mph, kq in veh/mi/lane, omega in mph). Matches the empirical pipeline queue-speed calculation.
    """
    mu_arr = np.asarray(mu, float)
    if np.any(mu_arr <= 0) or np.any(mu_arr > np.asarray(C, float) * (1 + 1e-12)):
        raise ValueError('the service rate must satisfy 0 < mu <= C')
    _, omega = fd_triangular(C, vf, kj)
    kq = kj - mu_arr / omega
    return np.divide(mu_arr, kq), kq, omega
