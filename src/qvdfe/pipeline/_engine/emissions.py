"""MOVES operating-mode emission benchmark for reconstructed QVDFE profiles.

The equations and input-file interpretation are intentionally aligned with the
previous QVDFE paper package.  Acceleration is held at zero because the source
traffic products contain five-minute mean speeds rather than trajectories.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

import numpy as np
import pandas as pd


LOGGER = logging.getLogger("qvdfe_cbi")
MPH_TO_MPS = 0.44704
MIN_SPEED_MPH = 1.0
POLLUTANTS = {
    "CO2": "meanBaseRate_CO2_(g/hr)",
    "NOX": "meanBaseRate_NOX_(g/hr)",
    "CO": "meanBaseRate_CO_(g/hr)",
    "HC": "meanBaseRate_HC_(g/hr)",
}


def compute_vsp(speed_mph, vehicle_params: dict, acceleration_mps2: float = 0.0) -> np.ndarray:
    v = np.asarray(speed_mph, dtype=float) * MPH_TO_MPS
    mass = max(float(vehicle_params["source_mass"]), 1e-12)
    return (
        float(vehicle_params["rolling_term_a"]) * v
        + float(vehicle_params["rotating_term_b"]) * v**2
        + float(vehicle_params["drag_term_c"]) * v**3
        + mass * v * float(acceleration_mps2)
    ) / mass


def get_op_mode_bin(speed_mph: float, vsp: float) -> int | None:
    if not np.isfinite(speed_mph) or not np.isfinite(vsp):
        return None
    if speed_mph <= 0:
        return 1
    if speed_mph < 25:
        for threshold, mode in [(0, 11), (3, 12), (6, 13), (9, 14), (12, 15)]:
            if vsp < threshold:
                return mode
        return 16
    if speed_mph < 50:
        for threshold, mode in [(0, 21), (3, 22), (6, 23), (9, 24), (12, 25), (18, 27), (24, 28), (30, 29)]:
            if vsp < threshold:
                return mode
        return 30
    for threshold, mode in [(6, 33), (12, 35), (18, 37), (24, 38), (30, 39)]:
        if vsp < threshold:
            return mode
    return 40


@dataclass
class MovesRates:
    vehicle_params: dict
    rates: pd.DataFrame

    def rate_for_modes(self, modes, pollutant: str) -> np.ndarray:
        lookup = self.rates.set_index("OpModeID")[f"ER_{pollutant}"].to_dict()
        return np.asarray([lookup.get(int(x), np.nan) if pd.notna(x) else np.nan for x in modes], dtype=float)


def load_moves_rates(input_dir: Path, vehicle_type: int = 1) -> MovesRates:
    input_dir = Path(input_dir)
    vehicles = pd.read_csv(input_dir / "input_vehicle_type.csv")
    raw = pd.read_csv(input_dir / "input_vehicle_emission_rate.csv")
    selected = vehicles.loc[vehicles["vehicle_type"].eq(vehicle_type)]
    if selected.empty:
        raise ValueError(f"MOVES vehicle_type={vehicle_type} is absent")
    params = selected.iloc[0].to_dict()
    weights = pd.DataFrame(
        [
            {"age": int(c.rsplit("_", 1)[-1]), "age_weight": float(params[c])}
            for c in vehicles.columns
            if c.startswith("percentage_of_age_")
        ]
    )
    weights["age_weight"] /= weights["age_weight"].sum()
    merged = raw.loc[raw["vehicle_type"].eq(vehicle_type)].merge(weights, on="age", how="inner")
    rows: list[dict] = []
    for mode, group in merged.groupby("OpModeID"):
        row = {"OpModeID": int(mode)}
        for pollutant, column in POLLUTANTS.items():
            row[f"ER_{pollutant}"] = float((group[column] * group["age_weight"]).sum())
        rows.append(row)
    return MovesRates(params, pd.DataFrame(rows).sort_values("OpModeID").reset_index(drop=True))


def fit_cubic_surrogates(moves: MovesRates) -> pd.DataFrame:
    speeds = np.linspace(5.0, 75.0, 701)
    vsp = compute_vsp(speeds, moves.vehicle_params)
    modes = [get_op_mode_bin(v, p) for v, p in zip(speeds, vsp)]
    rows = []
    for pollutant in POLLUTANTS:
        rates = moves.rate_for_modes(modes, pollutant)
        good = np.isfinite(rates)
        descending = np.polyfit(speeds[good], rates[good], 3)
        pred = np.polyval(descending, speeds[good])
        ss_tot = np.sum((rates[good] - rates[good].mean()) ** 2)
        rows.append(
            {
                "pollutant": pollutant,
                "speed_min_mph": 5.0,
                "speed_max_mph": 75.0,
                "c0": descending[3],
                "c1": descending[2],
                "c2": descending[1],
                "c3": descending[0],
                "rate_r2": 1.0 - np.sum((rates[good] - pred) ** 2) / ss_tot if ss_tot else np.nan,
                "rate_rmse_gph": float(np.sqrt(np.mean((rates[good] - pred) ** 2))),
                "negative_grid_share": float(np.mean(pred < 0)),
            }
        )
    return pd.DataFrame(rows)


def build_rate_speed_curve(moves: MovesRates) -> pd.DataFrame:
    """Return the exact zero-acceleration MOVES lookup over a dense speed grid."""
    speed = np.linspace(1.0, 80.0, 791)
    vsp = compute_vsp(speed, moves.vehicle_params)
    modes = pd.array([get_op_mode_bin(v, p) for v, p in zip(speed, vsp)], dtype="Int64")
    out = pd.DataFrame({"speed_mph": speed, "VSP": vsp, "OpModeID": modes})
    for pollutant in POLLUTANTS:
        out[f"ER_{pollutant}_gph"] = moves.rate_for_modes(modes, pollutant)
    return out
