"""Exact lookup and cubic emission-rate kernels used by v19."""
from __future__ import annotations
from typing import Callable
import numpy as np
from .emissions import MovesRates, compute_vsp, get_op_mode_bin

def _array(value) -> np.ndarray:
    return np.asarray(value, dtype=float)


def _safe_ratio(numerator, denominator) -> np.ndarray:
    num = _array(numerator)
    den = _array(denominator)
    return np.divide(
        num,
        den,
        out=np.full(np.broadcast_shapes(num.shape, den.shape), np.nan, dtype=float),
        where=np.isfinite(den) & (np.abs(den) > 1e-12),
    )


def cubic_rate(speed_mph, coefficients) -> np.ndarray:
    """Evaluate ``r(v)=c0+c1*v+c2*v^2+c3*v^3`` in g/vehicle-hour."""
    c0, c1, c2, c3 = _array(coefficients)
    speed = _array(speed_mph)
    return c0 + c1 * speed + c2 * speed**2 + c3 * speed**3


def gamma_from_rate(
    queue_speed_mph,
    reference_speed_mph,
    rate_function: Callable[[np.ndarray], np.ndarray],
) -> np.ndarray:
    """Evaluate the exact Lawson--Lu delay-to-emission quotient."""
    vq = _array(queue_speed_mph)
    vr = _array(reference_speed_mph)
    rq = _array(rate_function(vq))
    rr = _array(rate_function(vr))
    denominator = vr - vq
    numerator = vr * rq - vq * rr
    return np.divide(
        numerator,
        denominator,
        out=np.full_like(np.broadcast_arrays(vq, vr)[0], np.nan, dtype=float),
        where=np.isfinite(denominator) & (np.abs(denominator) > 1e-8),
    )


def gamma_from_cubic(queue_speed_mph, reference_speed_mph, coefficients) -> np.ndarray:
    """Evaluate Equation (gamma) after the cubic speed-rate approximation."""
    c0, _c1, c2, c3 = _array(coefficients)
    vq = _array(queue_speed_mph)
    vr = _array(reference_speed_mph)
    return c0 - (c2 * vr + c3 * vr**2) * vq - c3 * vr * vq**2


def exact_rate_for_speed(moves: MovesRates, speed_mph, pollutant: str) -> np.ndarray:
    """Return the exact age-weighted zero-acceleration MOVES lookup rate."""
    speed = _array(speed_mph)
    flat = speed.ravel()
    vsp = compute_vsp(flat, moves.vehicle_params)
    modes = [get_op_mode_bin(float(v), float(p)) for v, p in zip(flat, vsp)]
    return moves.rate_for_modes(modes, pollutant).reshape(speed.shape)
