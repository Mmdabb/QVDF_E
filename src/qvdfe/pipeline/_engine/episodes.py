from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .cbi_state_transition import (
    StateTransitionConfig,
    _post_process_episodes,
    detect_state_transition,
    identify_discharge_window,
)

from .config import PERIODS
from .boundary_recovery import StateTransitionConfig as BoundaryConfig, _resolve_t0_boundary, _resolve_t3_boundary


LOGGER = logging.getLogger("qvdfe_cbi")


def period_for_timestamp(ts) -> str:
    ts = pd.Timestamp(ts)
    hour = ts.hour + ts.minute / 60.0
    for label, (start, end) in PERIODS.items():
        if start < end and start <= hour < end:
            return label
        if start > end and (hour >= start or hour < end):
            return label
    return "NT"


def span_periods(t0, t3, interval_min: float = 5.0) -> str:
    stamps = pd.date_range(pd.Timestamp(t0), pd.Timestamp(t3), freq=f"{int(interval_min)}min")
    labels = []
    for stamp in stamps:
        label = period_for_timestamp(stamp)
        if label not in labels:
            labels.append(label)
    return ";".join(labels)


def _base_frame(group: pd.DataFrame, speed_col: str = 'speed_mph') -> pd.DataFrame:
    frame = group.sort_values("datetime").reset_index(drop=True).copy()
    frame['datetime'] = pd.to_datetime(frame['datetime'])
    if frame.datetime.duplicated().any():
        raise ValueError('Duplicate five-minute timestamps in detector input')
    # Missing timestamps must occupy their elapsed intervals, not shorten P.
    timeline = pd.date_range(frame.datetime.min(), frame.datetime.max(), freq='5min')
    frame = frame.set_index('datetime').reindex(timeline).rename_axis('datetime').reset_index()
    for col in ['sensor_uid', 'corridor_freeflow_speed_mph', 'fd_capacity_vphpl']:
        frame[col] = frame[col].ffill().bfill()
    return pd.DataFrame({
        "entity_id": frame["sensor_uid"].astype(str),
        "timestamp": pd.to_datetime(frame["datetime"]),
        "date": pd.to_datetime(frame["datetime"]).dt.date.astype(str),
        "time_of_day": pd.to_datetime(frame["datetime"]).dt.strftime("%H:%M:%S"),
        "speed_mph": pd.to_numeric(frame[speed_col], errors="coerce"),
        "corridor_freeflow_speed_mph": pd.to_numeric(frame["corridor_freeflow_speed_mph"], errors="coerce"),
        "flow": pd.to_numeric(frame["flow_vph"], errors="coerce"),
        "per_lane_hourly_capacity": pd.to_numeric(frame["fd_capacity_vphpl"], errors="coerce"),
        "aggregation_mode": "daily",
        "speed_mph_pre_qc": pd.to_numeric(frame["speed_mph"], errors="coerce"),
        'speed_qc_flagged': frame['qc_pass'].eq(0) if 'qc_pass' in frame else False,
    })


def _config(vf: float, vc: float, min_duration: float, merge_gap: float,
            detection_smoothing: bool = True) -> StateTransitionConfig:
    return StateTransitionConfig(
        source_speed_col="speed_mph",
        min_duration_min=min_duration,
        merge_gap_min=merge_gap,
        min_discharge_duration_min=30.0,
        min_discharge_positive_dq_share=0.60,
        allow_net_increasing_discharge=True,
        min_discharge_speed_gain_mph=0.0,
        require_congested_speed_for_discharge=True,
        enable_measured_outlier_flags=False,
        enable_mad_outlier_flags=False,
        use_stage0_corridor_freeflow=True,
        free_threshold_ratio=0.85,
        congested_threshold_ratio=float(np.clip(vc / max(vf, 1e-6), 0.35, 0.95)),
        breakdown_drop_mph=10.0,
        breakdown_window_intervals=2,
        recovery_rise_mph=10.0,
        max_noncongested_gap_intervals=3,
        allow_rolling_mean_extension=True,
        rolling_mean_extension_intervals=6,
        rolling_mean_extension_ratio=1.0,
        use_detection_smoothing=detection_smoothing,
        detection_smoothing_method="savgol",
        detection_smoothing_window_intervals=5,
        detection_smoothing_polyorder=2,
    )


def _deepest_bounds(frame: pd.DataFrame, vc: float) -> list[tuple[int, int]]:
    speed = frame["speed_mph"].to_numpy(dtype=float)
    if not np.isfinite(speed).any():
        return []
    t2 = int(np.nanargmin(speed))
    if not np.isfinite(speed[t2]) or speed[t2] >= vc:
        return []

    def boundary(indices):
        above = nan_gap = 0
        last_inside = t2
        for idx in indices:
            value = speed[idx]
            if np.isfinite(value):
                nan_gap = 0
                if value > vc:
                    above += 1
                    if above >= 2:
                        return last_inside
                else:
                    above = 0
                    last_inside = idx
            else:
                above = 0
                nan_gap += 1
                if nan_gap >= 3:
                    return last_inside
        return last_inside

    return [(boundary(range(t2, -1, -1)), boundary(range(t2, len(speed))))]


def _episode_from_bounds(
    frame: pd.DataFrame,
    start: int,
    end: int,
    vf: float,
    vc: float,
    detector: str,
    min_duration_min: float,
) -> dict | None:
    interval = 5.0
    if end < start or (end - start + 1) * interval < min_duration_min:
        return None
    speed = frame["speed_mph"].to_numpy(dtype=float)
    flow = frame["flow"].to_numpy(dtype=float)
    segment = speed[start:end + 1]
    if not np.isfinite(segment).any():
        return None
    t2 = start + int(np.nanargmin(segment))
    # Preserve the original minimum while recovering only episode boundaries.
    boundary_cfg = BoundaryConfig()
    b0 = _resolve_t0_boundary(frame, t0_idx=start, congested_threshold=vc,
                             freeflow_speed_mph=vf, config=boundary_cfg)
    b3 = _resolve_t3_boundary(frame, t2_idx=t2, t3_idx=end, congested_threshold=vc,
                             freeflow_speed_mph=vf, config=boundary_cfg)
    start, end = int(b0.pop("t0_idx")), int(b3.pop("t3_idx"))
    speed = speed.copy()
    speed[start], speed[end] = b0["t0_boundary_speed_mph"], b3["t3_boundary_speed_mph"]
    segment = speed[start:end + 1]
    discharge = identify_discharge_window(
        speed, flow, t2, end, vc, interval,
        _config(vf, vc, min_duration_min, 15.0),
    )
    timestamps = pd.to_datetime(frame["timestamp"])
    capacity = float(np.nanmedian(frame["per_lane_hourly_capacity"]))
    demand = float(np.nansum(flow[start:end + 1] * interval / 60.0))
    duration = float((end - start + 1) * interval)
    valid = bool(
        duration >= min_duration_min and np.nanmin(segment) < vc
        and discharge["discharge_window_valid"] and np.isfinite(discharge["mu_obs_vphpl"])
        and np.isfinite(speed[start]) and np.isfinite(speed[end])
    )
    return {
        "detector": detector,
        "sensor_uid": str(frame["entity_id"].iloc[0]),
        "date": str(frame["date"].iloc[0]),
        "t0_timestamp": timestamps.iloc[start],
        "t2_timestamp": timestamps.iloc[t2],
        "t3_timestamp": timestamps.iloc[end] + pd.Timedelta(minutes=interval),
        "t3_last_sample_timestamp": timestamps.iloc[end],
        **b0, **b3,
        "t0_index": int(start),
        "t2_index": int(t2),
        "t3_index": int(end),
        "time_period_tag": span_periods(timestamps.iloc[start], timestamps.iloc[end]),
        "calibration_period": period_for_timestamp(timestamps.iloc[t2]),
        "duration_min": duration,
        "min_speed_mph": float(speed[t2]),
        "mean_speed_mph": float(np.nanmean(segment)),
        "freeflow_speed_mph": vf,
        "threshold_used": vc,
        "episode_demand": demand,
        "per_lane_hourly_capacity": capacity,
        "demand_capacity_ratio": demand / capacity if capacity > 0 else np.nan,
        "mu_obs_vphpl": discharge["mu_obs_vphpl"],
        "discharge_duration_min": discharge["discharge_duration_min"],
        "discharge_positive_dq_share": discharge["discharge_positive_dq_share"],
        "discharge_net_dq": discharge["discharge_net_dq"],
        "discharge_speed_gain_mph": discharge["discharge_speed_gain_mph"],
        "is_valid_for_mu": valid,
        'n_episode_missing_speeds': int((~np.isfinite(frame['speed_mph'].iloc[start:end+1])).sum()),
        'n_episode_flagged_speeds': int(frame['speed_qc_flagged'].iloc[start:end+1].sum()) if 'speed_qc_flagged' in frame else 0,
        "_start_idx": int(start),
        "_end_idx": int(end),
    }


def run_detectors(
    qc: pd.DataFrame,
    detectors: tuple[str, ...],
    min_duration_min: float = 30.0,
    merge_gap_min: float = 15.0,
    speed_col: str = 'speed_mph',
    detection_smoothing: bool = True,
) -> pd.DataFrame:
    work = qc.copy()
    work["datetime"] = pd.to_datetime(work["datetime"])
    work = work[work["datetime"].dt.dayofweek < 5].copy()
    rows = []
    for (sid, date), group in work.groupby(["sensor_uid", work["datetime"].dt.date], sort=False):
        frame = _base_frame(group, speed_col=speed_col)
        vf = float(np.nanmedian(frame["corridor_freeflow_speed_mph"]))
        vc = float(np.nanmedian(pd.to_numeric(group["fd_vc_mph"], errors="coerce")))
        if not (np.isfinite(vf) and np.isfinite(vc) and vf > vc > 0):
            continue
        if "state_transition" in detectors:
            cfg = _config(vf, vc, min_duration_min, merge_gap_min, detection_smoothing)
            state_rows = detect_state_transition(frame, cfg)
            for item in state_rows:
                row = _episode_from_bounds(
                    frame, int(item["_start_idx"]), int(item["_end_idx"]),
                    vf, vc, "state_transition", min_duration_min,
                )
                if row:
                    rows.append(row)
        if "deepest_queue" in detectors:
            for start, end in _deepest_bounds(frame, vc):
                row = _episode_from_bounds(
                    frame, start, end, vf, vc, "deepest_queue", min_duration_min,
                )
                if row:
                    rows.append(row)
    episodes = pd.DataFrame(rows)
    if episodes.empty:
        return episodes
    episodes['detection_speed_column'] = speed_col
    episodes['detection_smoothing'] = detection_smoothing
    sensor_meta = work.groupby("sensor_uid", as_index=False).agg(
        corridor=("corridor", "first"),
        direction=("direction", "first"),
        road_order=("road_order", "first"),
        length_mi=("length_mi", "first"),
        flow_synthetic=("flow_synthetic", "first"),
        source_format=("source_format", "first"),
    )
    episodes = episodes.merge(sensor_meta, on="sensor_uid", how="left")
    episodes["episode_id"] = [
        f"{d}__{s}__{date}__{i:03d}"
        for i, (d, s, date) in enumerate(zip(episodes.detector, episodes.sensor_uid, episodes.date), start=1)
    ]
    return episodes.sort_values(["detector", "sensor_uid", "date", "t0_timestamp"]).reset_index(drop=True)
