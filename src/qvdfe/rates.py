"""The QVDF-E age-weighted, zero-acceleration MOVES-derived lookup rate.

The archived input tables are the starting point; this module does not run MOVES
or infer its original version/year/settings. Speeds are in mph and rates are in
g/(vehicle h). Operating-mode boundaries deliberately match the QVDF-E experiment workflow.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


def _op_mode(speed, vsp):
    if not np.isfinite(speed) or not np.isfinite(vsp):
        return None
    if speed <= 0:
        return 1
    if speed < 25:
        bins = [(0, 11), (3, 12), (6, 13), (9, 14), (12, 15)]
        last = 16
    elif speed < 50:
        bins = [(0, 21), (3, 22), (6, 23), (9, 24), (12, 25), (18, 27), (24, 28), (30, 29)]
        last = 30
    else:
        bins = [(6, 33), (12, 35), (18, 37), (24, 38), (30, 39)]
        last = 40
    return next((mode for threshold, mode in bins if vsp < threshold), last)


@dataclass(frozen=True)
class LookupRate:
    """Callable scalar/array lookup with no smoothing, interpolation or rate clipping."""
    vehicle_params: dict
    mode_rates: dict
    pollutant: str

    def __call__(self, speed_mph):
        speed = np.asarray(speed_mph, dtype=float)
        flat = speed.ravel()
        v = flat * 0.44704
        p = self.vehicle_params
        mass = max(float(p['source_mass']), 1e-12)
        vsp = (float(p['rolling_term_a']) * v + float(p['rotating_term_b']) * v ** 2
               + float(p['drag_term_c']) * v ** 3) / mass
        values = [self.mode_rates.get(_op_mode(s, z), np.nan) for s, z in zip(flat, vsp)]
        return np.asarray(values, dtype=float).reshape(speed.shape)


def lookup_rates(input_dir, *, vehicle_type=1):
    """Load the original normalized vehicle-age mixture and operating-mode rates."""
    input_dir = Path(input_dir)
    vehicles = pd.read_csv(input_dir / 'input_vehicle_type.csv')
    raw = pd.read_csv(input_dir / 'input_vehicle_emission_rate.csv')
    selected = vehicles.loc[vehicles.vehicle_type.eq(vehicle_type)]
    if selected.empty:
        raise ValueError(f'MOVES vehicle_type={vehicle_type} is absent')
    params = selected.iloc[0].to_dict()
    weights = pd.DataFrame([
        {'age': int(c.rsplit('_', 1)[-1]), 'age_weight': float(params[c])}
        for c in vehicles.columns if c.startswith('percentage_of_age_')
    ])
    if weights.empty or not np.isfinite(weights.age_weight).all() or (weights.age_weight < 0).any():
        raise ValueError('vehicle age weights must be finite and nonnegative')
    weight_sum = weights.age_weight.sum()
    if weight_sum <= 0:
        raise ValueError('vehicle age weights must have a positive sum')
    weights['age_weight'] /= weight_sum
    merged = raw.loc[raw.vehicle_type.eq(vehicle_type)].merge(weights, on='age', how='inner')
    if merged.empty:
        raise ValueError(f'no emission rates for vehicle_type={vehicle_type} and its age mixture')
    out = {}
    for pollutant, source_name in [('CO2', 'CO2'), ('NOx', 'NOX'), ('CO', 'CO'), ('HC', 'HC')]:
        column = f'meanBaseRate_{source_name}_(g/hr)'
        mode_rates = {int(mode): float((g[column] * g.age_weight).sum())
                      for mode, g in merged.groupby('OpModeID')}
        out[pollutant] = LookupRate(params, mode_rates, pollutant)
    return out
