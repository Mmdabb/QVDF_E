"""Loaders for the frozen data used by the tutorials, examples and reproduction scripts."""
import json

import numpy as np
import pandas as pd

from .paths import frozen_dir

POLLUTANTS = ['CO2', 'NOx', 'CO', 'HC']


def load_rates(path=None, *, representation='cubic', vehicle_type=1):
    """Load an explicitly selected zero-acceleration emission-rate representation.

    ``representation='lookup'`` returns callable rates for the empirical two-speed
    result M. ``representation='cubic'`` returns coefficient dictionaries for the
    smooth approximation A and its analytical derivatives. The cubic default is
    retained for compatibility; new empirical calculations should request lookup.
    ``path`` is an input directory for lookup, or a coefficient CSV for cubic.
    These are two representations of the same archived MOVES-derived table, not
    different traffic calibrations or new MOVES runs.
    """
    if representation == 'lookup':
        return load_lookup_rates(path, vehicle_type=vehicle_type)
    if representation == 'cubic':
        return load_cubic_rates(path)
    raise ValueError("representation must be 'lookup' or 'cubic'")


def load_cubic_rates(path=None):
    """Cubic zero-acceleration rates fitted to the archived MOVES-derived passenger-car table.

    Returns {pollutant: {'coef': array(c0..c3), 'vmin': mph, 'vmax': mph}}; r in g/(veh h), v in mph.
    This representation produces A, not the empirical lookup result M.
    The original MOVES run (version, year, settings) was not recorded; results start from this derived table.
    """
    p = path or frozen_dir() / 'calibration' / 'cubic_rate_coefficients.csv'
    df = pd.read_csv(p)
    return {r.pollutant: {'coef': np.array([r.c0, r.c1, r.c2, r.c3], float), 'vmin': float(r.speed_min_mph),
                          'vmax': float(r.speed_max_mph)} for r in df.itertuples()}


def load_lookup_rates(path=None, *, vehicle_type=1):
    """Return {pollutant: callable(speed_mph)} for the empirical lookup result M.

    Rates have units g/(vehicle h). Vehicle age weights are normalized, rates are
    selected by zero-acceleration VSP/operating-mode bins, and no interpolation is
    applied. Pass these callables directly to ``gamma`` or ``episode_total``.
    The default uses the same already-public passenger-car input tables as the experiment pipeline.
    """
    from .rates import lookup_rates
    p = path if path is not None else frozen_dir() / 'calibration' / 'emission_input'
    return lookup_rates(p, vehicle_type=vehicle_type)


def load_reference_state():
    """Detector-78 reference state of Appendix F (saved full-precision values)."""
    return json.loads((frozen_dir() / 'calibration' / 'audit' / 'table3_reference_state.json').read_text(encoding='utf-8'))


def load_cards():
    """Average-weekday QVDF parameter cards with the FD of a representative detector per corridor
    (detector 78 for Arizona). Columns as in parameter_card.csv plus C, vf, L, kj, omega, sensor."""
    A = frozen_dir() / 'calibration' / 'average_weekday'
    pc = pd.read_csv(A / 'parameter_card.csv')
    sp = pd.read_csv(A / 'sensor_parameters.csv')
    out = []
    for row in pc.to_dict('records'):
        s = sp[sp.corridor == row['corridor']]
        if row['corridor'] == 'AZ_I10_W':
            s = s[s.sensor.astype(str) == '78']
        if len(s):
            s0 = s.iloc[0]
            row.update(C=s0.C_vphpl, vf=s0.vf_mph, L=s0.L_mi, kj=s0.kj, omega=s0.omega_mph, sensor=str(s0.sensor))
        out.append(row)
    return pd.DataFrame(out)


def load_episodes(kind='average_weekday'):
    """Episode results (kind 'average_weekday' or 'daily_validation') with boolean flags parsed."""
    df = pd.read_csv(frozen_dir() / 'calibration' / kind / 'episode_results_v2.csv', low_memory=False)
    for c in df.columns:
        if df[c].dtype == object and set(df[c].dropna().astype(str).str.lower().unique()) <= {'true', 'false'}:
            df[c] = df[c].astype(str).str.lower().eq('true')
    return df
