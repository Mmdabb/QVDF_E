"""Standalone Stage 2 state-transition congestion episode detector.

This module keeps only the state-transition approach from the Stage 2 sandbox.
It reads Stage 1 QC output, detects congestion episodes, writes CSV summaries,
and optionally plots episode overlays for visual review.
"""

from __future__ import annotations

import json
import logging
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .cbi_paths import project_path, project_root_from_cwd


EPISODE_COLUMNS = [
    "method",
    "aggregation_mode",
    "entity_id",
    "date",
    "time_period_tag",
    "calibration_period",
    "regime_label",
    "is_valid_for_mu",
    "t0",
    "t2",
    "t3",
    "t0_timestamp",
    "t2_timestamp",
    "t3_timestamp",
    "duration_min",
    "duration_mad_zscore",
    "severe_congestion_duration_min",
    "min_speed_mph",
    "mean_speed_mph",
    "freeflow_speed_mph",
    "freeflow_source",
    "threshold_used",
    "speed_drop_mph",
    "severity",
    "episode_demand",
    "discharge_start_idx",
    "discharge_end_idx",
    "discharge_duration_min",
    "mu_obs_vphpl",
    "discharge_positive_dq_share",
    "discharge_net_dq",
    "discharge_speed_gain_mph",
    "discharge_trend_ok",
    "discharge_speed_recovery_ok",
    "per_lane_hourly_capacity",
    "demand_capacity_ratio",
    "demand_capacity_ratio_mad_zscore",
    "num_intervals",
    "measured_outlier_flag",
    "measured_outlier_reasons",
    "notes",
]


TIME_PERIODS = {
    "AM": (5, 9),
    "MD": (9, 15),
    "PM": (15, 19),
    "NT": (19, 5),
}


@dataclass
class StateTransitionConfig:
    """Configuration for standalone state-transition episode detection."""

    stage1_dir: str = "cbi_outputs/stage1_qc"
    output_folder: str = "cbi_outputs/stage2_state_transition"
    source_speed_col: str = "speed_mph_clean_repaired"
    source_flow_col: str = "flow"
    source_capacity_col: str = "per_lane_hourly_capacity"
    source_corridor_freeflow_col: str = "corridor_freeflow_speed_mph"
    source_sensor_col: str = "sensor_uid"
    source_datetime_col: str = "datetime"
    use_qc_pass_repaired_only: bool = False
    qc_pass_repaired_col: str = "qc_pass_repaired"
    use_multiday_average: bool = False

    min_duration_min: float = 15.0
    merge_gap_min: float = 10.0
    default_interval_minutes: float = 5.0
    freeflow_percentile: float = 85.0
    freeflow_min_mph: float = 35.0
    freeflow_max_mph: float = 85.0
    use_stage0_corridor_freeflow: bool = True
    default_per_lane_capacity_vphpl: float = 2000.0

    uncongested_max_duration_min: float = 30.0
    mild_max_duration_min: float = 60.0
    recurring_min_duration_min: float = 60.0
    severe_min_duration_min: float = 120.0
    severe_min_speed_ratio: float = 0.50
    mild_speed_ratio_lo: float = 0.70
    event_z_threshold: float = 2.5

    min_discharge_duration_min: float = 30.0
    min_discharge_positive_dq_share: float = 0.60
    allow_net_increasing_discharge: bool = True
    min_discharge_speed_gain_mph: float = 0.0
    require_congested_speed_for_discharge: bool = True

    enable_measured_outlier_flags: bool = True
    outlier_doc_high_threshold: float = 1.0
    outlier_doc_low_threshold: float = 0.5
    outlier_doc_low_high_duration_min: float = 60.0
    outlier_mu_capacity_ratio_high: float = 1.05
    outlier_mu_starved_doc_threshold: float = 1.5
    outlier_mu_starved_capacity_ratio: float = 0.30
    outlier_vt2_min_mph: float = 5.0
    enable_mad_outlier_flags: bool = True
    duration_mad_z_threshold: float = 3.5
    demand_capacity_ratio_mad_z_threshold: float = 3.5
    min_valid_episodes_for_global_mad_outlier_detection: int = 10

    free_threshold_ratio: float = 0.85
    congested_threshold_ratio: float = 0.70
    breakdown_drop_mph: float = 10.0
    breakdown_window_intervals: int = 2
    recovery_rise_mph: float = 8.0
    exit_confirm_intervals: int = 2
    max_noncongested_gap_intervals: int = 2
    allow_rolling_mean_extension: bool = True
    rolling_mean_extension_intervals: int = 6
    rolling_mean_extension_ratio: float = 1.0
    use_detection_smoothing: bool = True
    detection_smoothing_method: str = "savgol"
    detection_smoothing_window_intervals: int = 5
    detection_smoothing_polyorder: int = 2
    plot_detection_smoothed_speed: bool = True

    very_short_episode_minutes: float = 15.0
    max_figures: int = 50
    sample_sensor_count: int | None = None
    sample_days_per_sensor: int | None = None


def _configure_logging(out_dir: Path) -> logging.Logger:
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    file_handler = logging.FileHandler(out_dir / "warnings.log", mode="w", encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    logger.addHandler(console_handler)
    return logger


def _safe_id(value) -> str:
    return str(value).replace(":", "_").replace("/", "_").replace("\\", "_").replace(" ", "_")


def _period_for_hour(hour: int) -> str:
    for tag, (start_hour, end_hour) in TIME_PERIODS.items():
        if start_hour < end_hour:
            if start_hour <= hour < end_hour:
                return tag
        elif hour >= start_hour or hour < end_hour:
            return tag
    return "NT"


def episode_time_period_tag(t0_timestamp, t3_timestamp, interval_minutes: float = 5.0) -> str:
    """Return semicolon-separated period tags touched by an episode interval."""
    t0 = pd.Timestamp(t0_timestamp)
    t3 = pd.Timestamp(t3_timestamp)
    if pd.isna(t0) or pd.isna(t3):
        return ""
    if t3 < t0:
        t3 = t3 + pd.Timedelta(days=1)

    step = pd.Timedelta(minutes=max(float(interval_minutes), 1e-6))
    tags = []
    current = t0
    while current <= t3:
        tag = _period_for_hour(int(current.hour))
        if not tags or tags[-1] != tag:
            tags.append(tag)
        current = current + step

    end_tag = _period_for_hour(int(t3.hour))
    if not tags or tags[-1] != end_tag:
        tags.append(end_tag)
    return ";".join(tags)


def _read_stage1_output(stage1_dir: Path) -> pd.DataFrame:
    long_parquet = stage1_dir / "stage1_qc_long.parquet"
    if long_parquet.exists():
        return pd.read_parquet(long_parquet)

    long_csv = stage1_dir / "stage1_qc_long.csv"
    if long_csv.exists():
        return pd.read_csv(long_csv)

    per_sensor = stage1_dir / "per_sensor"
    if not per_sensor.exists():
        raise FileNotFoundError(f"Stage 1 output not found at {stage1_dir}")

    pieces = []
    for path in sorted(per_sensor.glob("*.parquet")):
        try:
            pieces.append(pd.read_parquet(path))
        except Exception as exc:
            warnings.warn(f"Skipping parquet {path}: {exc}", stacklevel=2)
    for path in sorted(per_sensor.glob("*.csv")):
        pieces.append(pd.read_csv(path))
    if not pieces:
        raise FileNotFoundError(f"No Stage 1 per-sensor files found under {per_sensor}")
    return pd.concat(pieces, ignore_index=True)


def load_experiment_input(config: StateTransitionConfig, project_root: Path | None = None) -> pd.DataFrame:
    """Read Stage 1 output and keep Monday-Friday observations."""
    project_root = project_root_from_cwd() if project_root is None else Path(project_root)
    df = _read_stage1_output(project_path(config.stage1_dir, project_root))
    required = [config.source_sensor_col, config.source_speed_col]
    if config.use_multiday_average:
        if "minute_of_day" in df.columns:
            required.append("minute_of_day")
        elif config.source_datetime_col in df.columns:
            required.append(config.source_datetime_col)
        else:
            required.append("minute_of_day")
    else:
        required.append(config.source_datetime_col)
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Stage 1 input is missing required columns: {missing}")

    df = df.copy()
    if config.use_qc_pass_repaired_only:
        if config.qc_pass_repaired_col not in df.columns:
            raise ValueError(
                f"Stage 1 input is missing required QC column: {config.qc_pass_repaired_col}"
            )
        qc_pass = pd.to_numeric(df[config.qc_pass_repaired_col], errors="coerce").fillna(0)
        df = df[qc_pass == 1].copy()

    df["entity_id"] = df[config.source_sensor_col].astype(str)
    df["speed_mph"] = pd.to_numeric(df[config.source_speed_col], errors="coerce")
    if config.source_flow_col in df.columns:
        df["flow"] = pd.to_numeric(df[config.source_flow_col], errors="coerce")
    else:
        df["flow"] = np.nan
    if config.source_capacity_col in df.columns:
        capacity = pd.to_numeric(df[config.source_capacity_col], errors="coerce")
    else:
        capacity = pd.Series(float(config.default_per_lane_capacity_vphpl), index=df.index)
    df["per_lane_hourly_capacity"] = capacity
    if config.source_corridor_freeflow_col in df.columns:
        df["corridor_freeflow_speed_mph"] = pd.to_numeric(
            df[config.source_corridor_freeflow_col],
            errors="coerce",
        )
    else:
        df["corridor_freeflow_speed_mph"] = np.nan
    if config.use_multiday_average:
        if "minute_of_day" in df.columns:
            minute = pd.to_numeric(df["minute_of_day"], errors="coerce")
            df = df[minute.notna()].copy()
            minute = minute.loc[df.index].astype(int)
            df["timestamp"] = pd.Timestamp("2000-01-03") + pd.to_timedelta(minute, unit="m")
            df["time_of_day"] = df.get("time_of_day", df["timestamp"].dt.strftime("%H:%M:%S"))
            df["time_of_day"] = df["time_of_day"].fillna(df["timestamp"].dt.strftime("%H:%M:%S")).astype(str)
        else:
            df[config.source_datetime_col] = pd.to_datetime(df[config.source_datetime_col], errors="coerce")
            df = df.dropna(subset=[config.source_datetime_col]).copy()
            df["timestamp"] = df[config.source_datetime_col]
            df["time_of_day"] = df["timestamp"].dt.strftime("%H:%M:%S")
        df["date"] = ""
        df["aggregation_mode"] = "multiday_average"
    else:
        df[config.source_datetime_col] = pd.to_datetime(df[config.source_datetime_col], errors="coerce")
        df = df.dropna(subset=[config.source_datetime_col])
        df = df[df[config.source_datetime_col].dt.weekday < 5].copy()
        df["timestamp"] = df[config.source_datetime_col]
        df["date"] = df["timestamp"].dt.date.astype(str)
        df["time_of_day"] = df["timestamp"].dt.strftime("%H:%M:%S")
        df["aggregation_mode"] = "daily"
    return df


def make_entity_frames(df: pd.DataFrame, config: StateTransitionConfig) -> list[pd.DataFrame]:
    """Create sorted one-entity dataframes for daily or weekday-average mode."""
    frames = []
    if config.use_multiday_average:
        keep = [
            "entity_id",
            "timestamp",
            "date",
            "time_of_day",
            "speed_mph",
            "corridor_freeflow_speed_mph",
            "flow",
            "per_lane_hourly_capacity",
            "aggregation_mode",
        ]
        for _, grp in df[keep].groupby("entity_id", sort=False):
            frames.append(grp.sort_values("timestamp").reset_index(drop=True))
    else:
        keep = [
            "entity_id",
            "timestamp",
            "date",
            "time_of_day",
            "speed_mph",
            "corridor_freeflow_speed_mph",
            "flow",
            "per_lane_hourly_capacity",
            "aggregation_mode",
        ]
        for _, grp in df[keep].groupby(["entity_id", "date"], sort=False):
            frames.append(grp.sort_values("timestamp").reset_index(drop=True))
    return frames


def estimate_interval_minutes(entity_df: pd.DataFrame, default: float = 5.0) -> float:
    diffs = entity_df["timestamp"].sort_values().diff().dropna().dt.total_seconds() / 60.0
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    return float(diffs.median()) if len(diffs) else float(default)


def detection_speed_series(entity_df: pd.DataFrame, config: StateTransitionConfig) -> np.ndarray:
    """Return the speed series used only for detection/state classification."""
    raw = entity_df["speed_mph"].to_numpy(dtype=float)
    if not config.use_detection_smoothing:
        return raw.copy()

    speed = raw.copy()
    s = pd.Series(speed)
    filled = s.interpolate(limit_direction="both").to_numpy(dtype=float)
    if np.isfinite(filled).sum() < 3:
        return raw.copy()

    method = str(config.detection_smoothing_method).lower()
    if method == "rolling_mean":
        window = max(1, int(config.detection_smoothing_window_intervals))
        smoothed = (
            pd.Series(filled)
            .rolling(window=window, center=True, min_periods=1)
            .mean()
            .to_numpy(dtype=float)
        )
    elif method == "savgol":
        from scipy.signal import savgol_filter

        window = max(3, int(config.detection_smoothing_window_intervals))
        if window % 2 == 0:
            window += 1

        n = len(filled)
        if window > n:
            window = n if n % 2 == 1 else n - 1

        polyorder = max(1, int(config.detection_smoothing_polyorder))
        if window <= polyorder:
            window = polyorder + 2
            if window % 2 == 0:
                window += 1

        if window > n or window < 3:
            return raw.copy()

        polyorder = min(polyorder, window - 1)
        smoothed = savgol_filter(filled, window_length=window, polyorder=polyorder, mode="interp")
    else:
        raise ValueError(f"Unknown detection_smoothing_method: {config.detection_smoothing_method}")

    smoothed = np.asarray(smoothed, dtype=float)
    smoothed[~np.isfinite(raw)] = np.nan
    return smoothed


def estimate_freeflow_speed(
    entity_df: pd.DataFrame,
    config: StateTransitionConfig,
    speed_override=None,
) -> float:
    if config.use_stage0_corridor_freeflow and "corridor_freeflow_speed_mph" in entity_df.columns:
        freeflow = pd.to_numeric(entity_df["corridor_freeflow_speed_mph"], errors="coerce").to_numpy(dtype=float)
        freeflow = freeflow[np.isfinite(freeflow) & (freeflow > 0)]
        if len(freeflow):
            return float(np.clip(np.nanmedian(freeflow), config.freeflow_min_mph, config.freeflow_max_mph))

    speed = np.asarray(speed_override, dtype=float) if speed_override is not None else entity_df["speed_mph"].to_numpy(dtype=float)
    valid = speed[np.isfinite(speed)]
    if len(valid) == 0:
        return float("nan")
    freeflow = float(np.nanpercentile(valid, config.freeflow_percentile))
    return float(np.clip(freeflow, config.freeflow_min_mph, config.freeflow_max_mph))


def freeflow_source_for_entity(entity_df: pd.DataFrame, config: StateTransitionConfig) -> str:
    if config.use_stage0_corridor_freeflow and "corridor_freeflow_speed_mph" in entity_df.columns:
        freeflow = pd.to_numeric(entity_df["corridor_freeflow_speed_mph"], errors="coerce").to_numpy(dtype=float)
        freeflow = freeflow[np.isfinite(freeflow) & (freeflow > 0)]
        if len(freeflow):
            return "stage0_corridor"
    return "percentile_fallback"


def congested_threshold_from_freeflow(
    freeflow_speed_mph: float,
    config: StateTransitionConfig,
) -> float:
    return float(config.congested_threshold_ratio * freeflow_speed_mph)


def classify_regime(
    duration_min: float,
    min_speed_mph: float,
    congested_threshold: float,
    z_score: float = 0.0,
    config: StateTransitionConfig | None = None,
) -> str:
    """Classify a detected episode into a calibration-prep traffic regime."""
    config = config or StateTransitionConfig()
    if not (np.isfinite(duration_min) and np.isfinite(min_speed_mph) and np.isfinite(congested_threshold)):
        return "uncongested"
    if duration_min < config.uncongested_max_duration_min or min_speed_mph >= congested_threshold:
        return "uncongested"
    if abs(float(z_score)) > config.event_z_threshold:
        return "event"
    if (
        duration_min >= config.severe_min_duration_min
        and min_speed_mph < config.severe_min_speed_ratio * congested_threshold
    ):
        return "severe"
    if duration_min >= config.recurring_min_duration_min:
        return "recurring"
    if (
        duration_min < config.mild_max_duration_min
        and config.mild_speed_ratio_lo * congested_threshold <= min_speed_mph < congested_threshold
    ):
        return "mild"
    return "mild"


def identify_discharge_window(
    speed: np.ndarray,
    flow: np.ndarray,
    t2_idx: int,
    t3_idx: int,
    congested_threshold: float,
    interval_minutes: float,
    config: StateTransitionConfig,
) -> dict:
    """Find a robust discharge window from after t2 through t3."""
    invalid = {
        "discharge_start_idx": np.nan,
        "discharge_end_idx": np.nan,
        "discharge_duration_min": 0.0,
        "mu_obs_vphpl": np.nan,
        "discharge_positive_dq_share": np.nan,
        "discharge_net_dq": np.nan,
        "discharge_speed_gain_mph": np.nan,
        "discharge_trend_ok": False,
        "discharge_speed_recovery_ok": False,
        "discharge_window_valid": False,
    }
    start = int(t2_idx) + 1
    end = int(t3_idx)
    if end < start or start < 0:
        return invalid

    speed = np.asarray(speed, dtype=float)
    flow = np.asarray(flow, dtype=float)
    candidate_idx = np.arange(start, min(end, len(speed) - 1) + 1)
    if candidate_idx.size == 0:
        return invalid

    finite_speed = np.isfinite(speed[candidate_idx])
    if config.require_congested_speed_for_discharge:
        keep = finite_speed & (speed[candidate_idx] < congested_threshold)
    else:
        keep = finite_speed
    kept_idx = candidate_idx[keep]
    if kept_idx.size == 0:
        return invalid

    duration = float(kept_idx.size * interval_minutes)
    flow_candidate = flow[kept_idx] if len(flow) else np.array([], dtype=float)
    finite_flow = flow_candidate[np.isfinite(flow_candidate)]
    mu_obs = float(np.nanmedian(flow_candidate)) if finite_flow.size else np.nan

    if finite_flow.size >= 2:
        dq = np.diff(finite_flow)
        finite_dq = dq[np.isfinite(dq)]
        positive_share = (
            float(np.mean(finite_dq >= 0.0)) if finite_dq.size else np.nan
        )
        net_dq = float(finite_flow[-1] - finite_flow[0])
    else:
        positive_share = np.nan
        net_dq = np.nan

    t2_safe = 0 <= int(t2_idx) < len(speed)
    t3_safe = 0 <= int(t3_idx) < len(speed)
    speed_start = speed[int(t2_idx)] if t2_safe else np.nan
    speed_end = speed[int(t3_idx)] if t3_safe else np.nan
    speed_gain = float(speed_end - speed_start) if np.isfinite(speed_start) and np.isfinite(speed_end) else np.nan

    duration_ok = duration >= config.min_discharge_duration_min
    speed_ok = kept_idx.size > 0
    trend_ok = (
        np.isfinite(positive_share)
        and positive_share >= config.min_discharge_positive_dq_share
    ) or (
        config.allow_net_increasing_discharge
        and np.isfinite(net_dq)
        and net_dq >= 0.0
    )
    speed_recovery_ok = bool(
        np.isfinite(speed_gain)
        and speed_gain >= config.min_discharge_speed_gain_mph
    )
    valid = bool(duration_ok and speed_ok and trend_ok and speed_recovery_ok and np.isfinite(mu_obs))
    return {
        "discharge_start_idx": int(kept_idx[0]),
        "discharge_end_idx": int(kept_idx[-1]),
        "discharge_duration_min": duration,
        "mu_obs_vphpl": mu_obs,
        "discharge_positive_dq_share": positive_share,
        "discharge_net_dq": net_dq,
        "discharge_speed_gain_mph": speed_gain,
        "discharge_trend_ok": bool(trend_ok),
        "discharge_speed_recovery_ok": speed_recovery_ok,
        "discharge_window_valid": valid,
    }


def score_measured_outlier_flags(row: pd.Series, config: StateTransitionConfig) -> tuple[bool, str]:
    """Return measured-data outlier flag and semicolon-separated reason codes."""
    reasons = []
    dc = row.get("demand_capacity_ratio", np.nan)
    duration = row.get("duration_min", np.nan)
    mu = row.get("mu_obs_vphpl", np.nan)
    cap = row.get("per_lane_hourly_capacity", np.nan)
    min_speed = row.get("min_speed_mph", np.nan)
    threshold = row.get("threshold_used", np.nan)

    if np.isfinite(dc) and np.isfinite(duration):
        if dc > config.outlier_doc_high_threshold and duration < 15.0:
            reasons.append("doc_high_P_zero")
        if dc < config.outlier_doc_low_threshold and duration > config.outlier_doc_low_high_duration_min:
            reasons.append("doc_low_P_high")
    if np.isfinite(mu) and np.isfinite(cap):
        if mu > config.outlier_mu_capacity_ratio_high * cap:
            reasons.append("mu_above_capacity")
        if (
            np.isfinite(dc)
            and dc > config.outlier_mu_starved_doc_threshold
            and mu < config.outlier_mu_starved_capacity_ratio * cap
        ):
            reasons.append("mu_starved")
    if np.isfinite(min_speed) and np.isfinite(threshold):
        if min_speed >= threshold:
            reasons.append("vt2_above_threshold")
        if min_speed < config.outlier_vt2_min_mph:
            reasons.append("vt2_too_low")
    return bool(reasons), ";".join(reasons)


def _robust_mad_zscore(values: pd.Series, reference_values: pd.Series) -> pd.Series:
    reference = pd.to_numeric(reference_values, errors="coerce").dropna()
    if len(reference) == 0:
        return pd.Series(np.nan, index=values.index)
    median = reference.median()
    mad = (reference - median).abs().median()
    if not np.isfinite(mad) or mad <= 0:
        return pd.Series(np.nan, index=values.index)
    values = pd.to_numeric(values, errors="coerce")
    return (values - median) / (1.4826 * mad)


def _append_reason(existing: str, reason: str) -> str:
    reasons = [part for part in str(existing or "").split(";") if part]
    if reason not in reasons:
        reasons.append(reason)
    return ";".join(reasons)


def _apply_mad_outlier_flags(episodes: pd.DataFrame, config: StateTransitionConfig) -> pd.DataFrame:
    out = episodes.copy()
    out["duration_mad_zscore"] = np.nan
    out["demand_capacity_ratio_mad_zscore"] = np.nan

    if not config.enable_mad_outlier_flags or out.empty:
        return out

    valid_for_mu = out["is_valid_for_mu"].fillna(False).astype(bool)
    min_reference = int(config.min_valid_episodes_for_global_mad_outlier_detection)

    duration = pd.to_numeric(out["duration_min"], errors="coerce")
    duration_reference = duration[valid_for_mu & duration.notna()]
    if len(duration_reference) >= min_reference:
        out["duration_mad_zscore"] = _robust_mad_zscore(duration, duration_reference)
        duration_outlier = out["duration_mad_zscore"] > config.duration_mad_z_threshold
        out.loc[duration_outlier.fillna(False), "measured_outlier_reasons"] = out.loc[
            duration_outlier.fillna(False), "measured_outlier_reasons"
        ].apply(lambda reasons: _append_reason(reasons, "duration_mad_outlier"))

    dcr = pd.to_numeric(out["demand_capacity_ratio"], errors="coerce")
    dcr_reference = dcr[valid_for_mu & dcr.notna()]
    if len(dcr_reference) >= min_reference:
        out["demand_capacity_ratio_mad_zscore"] = _robust_mad_zscore(dcr, dcr_reference)
        dcr_outlier = (
            out["demand_capacity_ratio_mad_zscore"]
            > config.demand_capacity_ratio_mad_z_threshold
        )
        out.loc[dcr_outlier.fillna(False), "measured_outlier_reasons"] = out.loc[
            dcr_outlier.fillna(False), "measured_outlier_reasons"
        ].apply(lambda reasons: _append_reason(reasons, "demand_capacity_ratio_mad_outlier"))

    out["measured_outlier_flag"] = out["measured_outlier_reasons"].fillna("").astype(str) != ""
    return out


def _apply_event_regime_override(episodes: pd.DataFrame, config: StateTransitionConfig) -> pd.DataFrame:
    out = episodes.copy()
    if out.empty or "duration_min" not in out.columns:
        return out
    for _, grp in out.groupby("entity_id", sort=False):
        if len(grp) < 5:
            continue
        duration = pd.to_numeric(grp["duration_min"], errors="coerce")
        median = float(duration.median())
        mad = float((duration - median).abs().median() * 1.4826)
        if not np.isfinite(mad) or mad <= 0:
            continue
        z = (duration - median) / mad
        mask = (
            z.abs() > config.event_z_threshold
        ) & out.loc[grp.index, "regime_label"].isin(["severe", "recurring"])
        out.loc[grp.index[mask.to_numpy()], "regime_label"] = "event"
    return out


def _post_process_episodes(episodes: pd.DataFrame, config: StateTransitionConfig) -> pd.DataFrame:
    out = _apply_event_regime_override(episodes, config)
    if out.empty:
        for col in [
            "regime_label",
            "is_valid_for_mu",
            "duration_mad_zscore",
            "demand_capacity_ratio_mad_zscore",
            "measured_outlier_flag",
            "measured_outlier_reasons",
        ]:
            if col not in out.columns:
                out[col] = []
        return out

    if config.enable_measured_outlier_flags:
        scored = out.apply(lambda row: score_measured_outlier_flags(row, config), axis=1)
        out["measured_outlier_flag"] = [flag for flag, _ in scored]
        out["measured_outlier_reasons"] = [reasons for _, reasons in scored]
    else:
        out["measured_outlier_flag"] = False
        out["measured_outlier_reasons"] = ""

    out = _apply_mad_outlier_flags(out, config)
    return out


def merge_episode_bounds(bounds: list[tuple[int, int]], gap_intervals: int) -> list[tuple[int, int]]:
    if not bounds:
        return []
    bounds = sorted(bounds)
    merged = [bounds[0]]
    for start, end in bounds[1:]:
        last_start, last_end = merged[-1]
        if start - last_end - 1 <= gap_intervals:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _group_key(entity_df: pd.DataFrame) -> tuple[str, str, str]:
    return (
        str(entity_df["aggregation_mode"].iloc[0]),
        str(entity_df["entity_id"].iloc[0]),
        str(entity_df["date"].iloc[0]),
    )


def _episode_from_bounds(
    entity_df: pd.DataFrame,
    start: int,
    end: int,
    threshold_used: float,
    freeflow_speed_mph: float,
    interval_minutes: float,
    config: StateTransitionConfig,
    notes: str,
) -> dict | None:
    n = len(entity_df)
    start = max(0, int(start))
    end = min(n - 1, int(end))
    if end < start or n == 0:
        return None

    speed = entity_df["speed_mph"].to_numpy(dtype=float)
    segment = speed[start:end + 1]
    if not np.isfinite(segment).any():
        return None

    t2_idx = start + int(np.nanargmin(segment))
    timestamps = entity_df["timestamp"].reset_index(drop=True)
    min_speed = float(np.nanmin(segment))
    duration = (end - start + 1) * interval_minutes
    severity = float(np.nansum(np.maximum(0.0, threshold_used - segment)) * interval_minutes)
    states, _, _, _ = classify_state_transition_states(entity_df, config)
    severe_indices = np.flatnonzero(states[start:end + 1] == "severe_congestion")
    if len(severe_indices) == 0:
        severe_duration = 0.0
    else:
        severe_duration = float((severe_indices[-1] - severe_indices[0] + 1) * interval_minutes)

    flow = entity_df["flow"].to_numpy(dtype=float) if "flow" in entity_df.columns else np.full(n, np.nan)
    flow_segment = flow[start:end + 1]
    episode_demand = (
        np.nan
        if np.isnan(flow_segment).all()
        else float(np.nansum(flow_segment * interval_minutes / 60.0))
    )
    discharge = identify_discharge_window(
        speed=speed,
        flow=flow,
        t2_idx=t2_idx,
        t3_idx=end,
        congested_threshold=threshold_used,
        interval_minutes=interval_minutes,
        config=config,
    )
    capacity = (
        entity_df["per_lane_hourly_capacity"].to_numpy(dtype=float)
        if "per_lane_hourly_capacity" in entity_df.columns
        else np.full(n, np.nan)
    )
    capacity_segment = capacity[start:end + 1]
    per_lane_hourly_capacity = (
        np.nan
        if np.isnan(capacity_segment).all()
        else float(np.nanmedian(capacity_segment))
    )
    demand_capacity_ratio = (
        np.nan
        if not np.isfinite(episode_demand)
        or not np.isfinite(per_lane_hourly_capacity)
        or per_lane_hourly_capacity <= 0
        else float(episode_demand / per_lane_hourly_capacity)
    )
    regime_label = classify_regime(
        duration_min=duration,
        min_speed_mph=min_speed,
        congested_threshold=threshold_used,
        z_score=0.0,
        config=config,
    )
    is_valid_for_mu = bool(
        duration >= config.uncongested_max_duration_min
        and min_speed < threshold_used
        and discharge["discharge_window_valid"]
        and np.isfinite(discharge["mu_obs_vphpl"])
    )
    return {
        "method": "state_transition",
        "aggregation_mode": str(entity_df["aggregation_mode"].iloc[0]),
        "entity_id": str(entity_df["entity_id"].iloc[0]),
        "date": str(entity_df["date"].iloc[0]),
        "time_period_tag": episode_time_period_tag(timestamps.iloc[start], timestamps.iloc[end], interval_minutes),
        "calibration_period": _period_for_hour(int(timestamps.iloc[t2_idx].hour)),
        "regime_label": regime_label,
        "is_valid_for_mu": is_valid_for_mu,
        "t0": str(entity_df["time_of_day"].iloc[start]),
        "t2": str(entity_df["time_of_day"].iloc[t2_idx]),
        "t3": str(entity_df["time_of_day"].iloc[end]),
        "t0_timestamp": str(timestamps.iloc[start]),
        "t2_timestamp": str(timestamps.iloc[t2_idx]),
        "t3_timestamp": str(timestamps.iloc[end]),
        "duration_min": float(duration),
        "duration_mad_zscore": np.nan,
        "severe_congestion_duration_min": float(severe_duration),
        "min_speed_mph": min_speed,
        "mean_speed_mph": float(np.nanmean(segment)),
        "freeflow_speed_mph": float(freeflow_speed_mph),
        "freeflow_source": freeflow_source_for_entity(entity_df, config),
        "threshold_used": float(threshold_used),
        "speed_drop_mph": float(freeflow_speed_mph - min_speed),
        "severity": severity,
        "episode_demand": episode_demand,
        "discharge_start_idx": discharge["discharge_start_idx"],
        "discharge_end_idx": discharge["discharge_end_idx"],
        "discharge_duration_min": discharge["discharge_duration_min"],
        "mu_obs_vphpl": discharge["mu_obs_vphpl"],
        "discharge_positive_dq_share": discharge["discharge_positive_dq_share"],
        "discharge_net_dq": discharge["discharge_net_dq"],
        "discharge_speed_gain_mph": discharge["discharge_speed_gain_mph"],
        "discharge_trend_ok": discharge["discharge_trend_ok"],
        "discharge_speed_recovery_ok": discharge["discharge_speed_recovery_ok"],
        "per_lane_hourly_capacity": per_lane_hourly_capacity,
        "demand_capacity_ratio": demand_capacity_ratio,
        "demand_capacity_ratio_mad_zscore": np.nan,
        "num_intervals": int(end - start + 1),
        "measured_outlier_flag": False,
        "measured_outlier_reasons": "",
        "notes": notes,
        "_start_idx": start,
        "_end_idx": end,
        "_group_key": _group_key(entity_df),
    }


def _episodes_from_bounds(
    entity_df: pd.DataFrame,
    bounds: list[tuple[int, int]],
    threshold_used: float,
    freeflow_speed_mph: float,
    interval_minutes: float,
    config: StateTransitionConfig,
    notes: str,
) -> list[dict]:
    gap_intervals = int(round(config.merge_gap_min / max(interval_minutes, 1e-6)))
    min_intervals = int(np.ceil(config.min_duration_min / max(interval_minutes, 1e-6)))
    episodes = []
    for start, end in merge_episode_bounds(bounds, gap_intervals):
        if end - start + 1 < min_intervals:
            continue
        episode = _episode_from_bounds(
            entity_df,
            start,
            end,
            threshold_used,
            freeflow_speed_mph,
            interval_minutes,
            config,
            notes,
        )
        if episode:
            episodes.append(episode)
    return episodes


def classify_state_transition_states(
    entity_df: pd.DataFrame,
    config: StateTransitionConfig,
) -> tuple[np.ndarray, float, float, float]:
    """Classify each interval as free, normal, breakdown, congested, severe_congestion, or recovery."""
    speed = detection_speed_series(entity_df, config)
    freeflow = estimate_freeflow_speed(entity_df, config, speed_override=speed)
    congested_threshold = config.congested_threshold_ratio * freeflow
    severe_congested_threshold = 0.5 * congested_threshold
    free_threshold = config.free_threshold_ratio * freeflow
    window = max(1, int(config.breakdown_window_intervals))

    states = np.full(len(speed), "normal", dtype=object)
    states[speed >= free_threshold] = "free"
    states[speed <= congested_threshold] = "congested"
    states[speed <= severe_congested_threshold] = "severe_congestion"

    for i in range(window, len(speed)):
        if np.isfinite(speed[i]) and np.isfinite(speed[i - window]):
            if (
                speed[i - window] - speed[i] >= config.breakdown_drop_mph
                and speed[i] > congested_threshold
            ):
                states[i] = "breakdown"
            elif speed[i] - speed[i - window] >= config.recovery_rise_mph and speed[i] > congested_threshold:
                states[i] = "recovery"

    for i in range(len(speed) - 1):
        if (
            np.isfinite(speed[i])
            and np.isfinite(speed[i + 1])
            and speed[i] > congested_threshold
            and speed[i + 1] <= congested_threshold
        ):
            states[i] = "breakdown"

    return states, freeflow, congested_threshold, free_threshold


def _next_speed_below_threshold(speed: np.ndarray, idx: int, threshold: float) -> bool:
    next_idx = idx + 1
    return next_idx < len(speed) and np.isfinite(speed[next_idx]) and speed[next_idx] < threshold


def _is_exit_inactive(state: str, speed_value: float, free_threshold: float) -> bool:
    return (
        state not in ("breakdown", "congested", "severe_congestion", "recovery")
        and np.isfinite(speed_value)
        and speed_value > free_threshold
    )


def _allow_rolling_mean_extension(
    speed: np.ndarray,
    start: int,
    current_idx: int,
    congested_threshold: float,
    config: StateTransitionConfig,
) -> bool:
    if not config.allow_rolling_mean_extension:
        return False

    lookback = max(1, int(config.rolling_mean_extension_intervals))
    recent_start = max(start, current_idx - lookback + 1)
    recent = speed[recent_start:current_idx + 1]
    recent = recent[np.isfinite(recent)]
    if len(recent) == 0:
        return False

    recent_mean = float(np.mean(recent))
    return recent_mean <= config.rolling_mean_extension_ratio * congested_threshold


def detect_state_transition(entity_df: pd.DataFrame, config: StateTransitionConfig) -> list[dict]:
    """Detect congestion episodes using traffic-state transitions."""
    speed_detection = detection_speed_series(entity_df, config)
    interval = estimate_interval_minutes(entity_df, config.default_interval_minutes)
    states, freeflow, congested_threshold, free_threshold = classify_state_transition_states(entity_df, config)

    bounds = []
    in_episode = False
    seen_entry_signal = False
    start = 0
    last_active = 0
    last_supported_active = 0
    free_confirm = 0
    noncongested_gap = 0
    for i, state in enumerate(states):
        core_active = state in ("breakdown", "congested", "severe_congestion", "recovery")
        if not in_episode:
            if state in ("breakdown", "congested", "severe_congestion"):
                seen_entry_signal = True
            if seen_entry_signal and _next_speed_below_threshold(speed_detection, i, congested_threshold):
                in_episode = True
                start = i
                last_active = i
                last_supported_active = i
                free_confirm = 0
                noncongested_gap = 0
                seen_entry_signal = False
            continue

        if in_episode:
            if core_active:
                last_active = i
                last_supported_active = i
                free_confirm = 0
                noncongested_gap = 0
                continue

            noncongested_gap += 1
            if noncongested_gap <= config.max_noncongested_gap_intervals:
                last_supported_active = i
                continue
            if _allow_rolling_mean_extension(speed_detection, start, i, congested_threshold, config):
                last_supported_active = i
                continue

            exit_start = max(start, i - noncongested_gap + 1)
            end = min(max(start, exit_start), len(speed_detection) - 1)
            bounds.append((start, end))
            in_episode = False
            if state in ("breakdown", "congested", "severe_congestion"):
                seen_entry_signal = True
            else:
                seen_entry_signal = False
            last_active = 0
            last_supported_active = 0
            free_confirm = 0
            noncongested_gap = 0

    if in_episode:
        end = last_supported_active
        bounds.append((start, end))

    notes = (
        f"free_ratio={config.free_threshold_ratio};"
        f"congested_ratio={config.congested_threshold_ratio};"
        "severe_congestion_threshold=0.5*congested_threshold;"
        f"breakdown_drop_mph={config.breakdown_drop_mph};"
        "breakdown_requires_speed_above_congested_threshold=True;"
        "breakdown_includes_point_immediately_before_congestion=True;"
        f"recovery_rise_mph={config.recovery_rise_mph};"
        f"max_noncongested_gap_intervals={config.max_noncongested_gap_intervals};"
        f"allow_rolling_mean_extension={config.allow_rolling_mean_extension};"
        f"rolling_mean_extension_intervals={config.rolling_mean_extension_intervals};"
        f"rolling_mean_extension_ratio={config.rolling_mean_extension_ratio};"
        f"use_detection_smoothing={config.use_detection_smoothing};"
        f"detection_smoothing_method={config.detection_smoothing_method};"
        f"detection_smoothing_window_intervals={config.detection_smoothing_window_intervals};"
        f"detection_smoothing_polyorder={config.detection_smoothing_polyorder};"
        f"use_stage0_corridor_freeflow={config.use_stage0_corridor_freeflow};"
        f"source_corridor_freeflow_col={config.source_corridor_freeflow_col};"
        "freeflow_source=stage0_corridor_or_percentile_fallback;"
        f"mad_outlier_detection={config.enable_mad_outlier_flags};"
        f"duration_mad_z_threshold={config.duration_mad_z_threshold};"
        f"demand_capacity_ratio_mad_z_threshold={config.demand_capacity_ratio_mad_z_threshold};"
        f"min_valid_episodes_for_global_mad_outlier_detection={config.min_valid_episodes_for_global_mad_outlier_detection};"
        "global_mad_reference=is_valid_for_mu_episodes;"
        "boundary_rule=next_below_congested_start;"
        "t3_rule=explicit_state_machine_exit;"
        "normal_exit_t3_rule=first_interval_of_confirmed_noncore_exit_sequence;"
        "end_of_series_t3_rule=last_supported_active_no_backward_trim;"
        "endpoint_rule=no_backward_threshold_scan"
    )
    return _episodes_from_bounds(
        entity_df,
        bounds,
        congested_threshold,
        freeflow,
        interval,
        config,
        notes,
    )


def run_detector(entity_frames: list[pd.DataFrame], config: StateTransitionConfig) -> pd.DataFrame:
    episodes = []
    for entity_df in entity_frames:
        episodes.extend(detect_state_transition(entity_df, config))
    out = pd.DataFrame(episodes)
    if out.empty:
        return pd.DataFrame(columns=EPISODE_COLUMNS + ["_start_idx", "_end_idx", "_group_key"])
    out = _post_process_episodes(out, config)
    return out[EPISODE_COLUMNS + ["_start_idx", "_end_idx", "_group_key"]].copy()


def detector_summary(
    episodes: pd.DataFrame,
    entity_frames: list[pd.DataFrame],
    config: StateTransitionConfig,
    outlier_episodes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = [
        "method",
        "n_episodes",
        "mean_duration_min",
        "median_duration_min",
        "total_congested_minutes",
        "share_observed_time_congested",
        "mean_min_speed_mph",
        "mean_severity",
        "n_very_short_episodes",
        "n_valid_for_mu",
        "valid_for_mu_share",
        "regime_distribution",
        "n_measured_outliers",
        "measured_outlier_share",
        "n_duration_mad_outliers",
        "n_demand_capacity_ratio_mad_outliers",
    ]
    if episodes.empty:
        return pd.DataFrame(columns=columns)

    total_intervals = sum(len(frame) for frame in entity_frames)
    total_minutes = float(episodes["duration_min"].sum())
    valid_for_mu = episodes["is_valid_for_mu"].fillna(False).astype(bool)
    outlier_source = episodes if outlier_episodes is None else outlier_episodes
    measured_outliers = outlier_source["measured_outlier_flag"].fillna(False).astype(bool)
    outlier_reasons = outlier_source["measured_outlier_reasons"].fillna("").astype(str)
    return pd.DataFrame([{
        "method": "state_transition",
        "n_episodes": int(len(episodes)),
        "mean_duration_min": float(episodes["duration_min"].mean()),
        "median_duration_min": float(episodes["duration_min"].median()),
        "total_congested_minutes": total_minutes,
        "share_observed_time_congested": total_minutes / max(total_intervals * config.default_interval_minutes, 1.0),
        "mean_min_speed_mph": float(episodes["min_speed_mph"].mean()),
        "mean_severity": float(episodes["severity"].mean()),
        "n_very_short_episodes": int((episodes["duration_min"] < config.very_short_episode_minutes).sum()),
        "n_valid_for_mu": int(valid_for_mu.sum()),
        "valid_for_mu_share": float(valid_for_mu.mean()),
        "regime_distribution": json.dumps(episodes["regime_label"].value_counts().to_dict(), sort_keys=True),
        "n_measured_outliers": int(measured_outliers.sum()),
        "measured_outlier_share": float(measured_outliers.mean()),
        "n_duration_mad_outliers": int(outlier_reasons.str.contains("duration_mad_outlier", regex=False).sum()),
        "n_demand_capacity_ratio_mad_outliers": int(
            outlier_reasons.str.contains("demand_capacity_ratio_mad_outlier", regex=False).sum()
        ),
    }], columns=columns)


def _selected_plot_groups(entity_frames: list[pd.DataFrame], config: StateTransitionConfig) -> set[tuple[str, str, str]]:
    if config.sample_sensor_count is None and config.sample_days_per_sensor is None:
        return {_group_key(frame) for frame in entity_frames}

    selected = set()
    by_entity: dict[str, list[pd.DataFrame]] = {}
    for frame in entity_frames:
        by_entity.setdefault(str(frame["entity_id"].iloc[0]), []).append(frame)
    sensor_count = config.sample_sensor_count if config.sample_sensor_count is not None else len(by_entity)
    for entity in sorted(by_entity)[:max(0, int(sensor_count))]:
        frames = by_entity[entity]
        day_count = config.sample_days_per_sensor if config.sample_days_per_sensor is not None else len(frames)
        for frame in frames[:max(0, int(day_count))]:
            selected.add(_group_key(frame))
    return selected


def plot_state_transition_samples(
    episodes: pd.DataFrame,
    entity_frames: list[pd.DataFrame],
    config: StateTransitionConfig,
    out_dir: Path,
    logger: logging.Logger,
) -> set[tuple[str, str, str]]:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        logger.warning("matplotlib unavailable; skipped figures (%s)", exc)
        return set()
    if episodes.empty:
        logger.info("No episodes detected; skipped figure generation.")
        return set()

    fig_dir = out_dir / "figures" / "state_transition"
    fig_dir.mkdir(parents=True, exist_ok=True)
    for old_png in fig_dir.glob("*.png"):
        old_png.unlink()

    max_figures = max(0, int(config.max_figures))
    frame_lookup = {_group_key(frame): frame for frame in entity_frames}
    selected_keys = _selected_plot_groups(entity_frames, config)
    candidate_count = episodes["_group_key"].isin(selected_keys).groupby(episodes["_group_key"]).any().sum()

    plotted = 0
    plotted_keys: set[tuple[str, str, str]] = set()
    for key, eps in episodes.groupby("_group_key", sort=False):
        if key not in selected_keys or plotted >= max_figures:
            continue
        frame = frame_lookup.get(key)
        if frame is None:
            continue

        speed = frame["speed_mph"].to_numpy(dtype=float)
        speed_detection = detection_speed_series(frame, config)
        states, _, _, _ = classify_state_transition_states(frame, config)
        x = np.arange(len(speed))
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(
            x,
            speed,
            color="black",
            linewidth=1.2,
            marker="o",
            markersize=3,
            markerfacecolor="black",
            markeredgecolor="black",
            label="raw/repaired speed",
        )
        if config.use_detection_smoothing and config.plot_detection_smoothed_speed:
            ax.plot(
                x,
                speed_detection,
                color="tab:blue",
                linewidth=2.0,
                linestyle="--",
                alpha=0.85,
                label="detection smoothed speed",
            )
        state_styles = {
            "breakdown": "tab:orange",
            "congested": "tab:red",
            "severe_congestion": "purple",
            "recovery": "tab:green",
        }
        for state, color in state_styles.items():
            mask = states == state
            if mask.any():
                ax.scatter(
                    x[mask],
                    speed[mask],
                    s=28,
                    color=color,
                    edgecolors="black",
                    linewidths=0.35,
                    zorder=4,
                    label=state,
                )
        ax.axhline(
            congested_threshold_from_freeflow(estimate_freeflow_speed(frame, config), config),
            color="tab:red",
            linestyle="--",
            linewidth=1,
            label=f"congested threshold ({config.congested_threshold_ratio:.2f} x freeflow)",
        )
        for _, ep in eps.iterrows():
            start = int(ep["_start_idx"])
            end = int(ep["_end_idx"])
            t2 = int(np.nanargmin(speed[start:end + 1])) + start if end >= start else start
            ax.axvspan(start, end, color="tab:red", alpha=0.18)
            ax.axvline(start, color="tab:orange", linestyle="--", linewidth=1, label="t0")
            ax.axvline(t2, color="tab:purple", linestyle=":", linewidth=1.5, label="t2")
            ax.axvline(end, color="tab:green", linestyle="--", linewidth=1, label="t3")

        date = str(frame["date"].iloc[0]) or "weekday_average"
        entity = str(frame["entity_id"].iloc[0])
        ax.set_title(f"state_transition - {entity} / {date}")
        ax.set_ylabel("Speed (mph)")
        ax.set_xlabel("Interval")
        handles, labels = ax.get_legend_handles_labels()
        unique = dict(zip(labels, handles))
        ax.legend(unique.values(), unique.keys(), loc="best", fontsize=8)
        fig.tight_layout()
        fig.savefig(fig_dir / f"{_safe_id(entity)}_{_safe_id(date)}.png", dpi=140)
        plt.close(fig)
        plotted += 1
        plotted_keys.add(key)

    logger.info("Figures saved for state_transition: %s of %s eligible groups", plotted, candidate_count)
    return plotted_keys


def plot_valid_episode_windows(
    episodes: pd.DataFrame,
    entity_frames: list[pd.DataFrame],
    plotted_keys: set[tuple[str, str, str]],
    out_dir: Path,
    logger: logging.Logger,
) -> None:
    """Plot valid episode windows only for groups already plotted in state_transition."""
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        logger.warning("matplotlib unavailable; skipped valid episode window figures (%s)", exc)
        return

    fig_dir = out_dir / "figures" / "state_transition_valid_episode_windows"
    fig_dir.mkdir(parents=True, exist_ok=True)
    for old_png in fig_dir.glob("*.png"):
        old_png.unlink()

    if episodes.empty or not plotted_keys:
        logger.info("No plotted valid episode groups; skipped valid episode window figures.")
        return

    eligible = episodes[episodes["_group_key"].isin(plotted_keys)].copy()
    if eligible.empty:
        logger.info("No valid episodes within plotted state_transition groups; skipped valid episode window figures.")
        return

    frame_lookup = {_group_key(frame): frame for frame in entity_frames}
    plotted = 0
    for sequence, (_, ep) in enumerate(eligible.iterrows(), start=1):
        frame = frame_lookup.get(ep.get("_group_key"))
        if frame is None:
            continue

        start = max(0, int(ep["_start_idx"]))
        end = min(len(frame) - 1, int(ep["_end_idx"]))
        if end < start:
            continue

        segment = frame.iloc[start:end + 1].copy().reset_index(drop=True)
        timestamps = pd.to_datetime(segment["timestamp"], errors="coerce")
        if timestamps.isna().all():
            logger.warning("Skipped valid episode window for %s: missing timestamps.", ep.get("entity_id"))
            continue

        speed = segment["speed_mph"].to_numpy(dtype=float)
        x = timestamps
        t2_offset = int(np.nanargmin(speed)) if np.isfinite(speed).any() else 0
        if pd.notna(ep.get("t2_timestamp")):
            t2_timestamp = pd.to_datetime(ep.get("t2_timestamp"), errors="coerce")
            if pd.notna(t2_timestamp):
                matches = np.flatnonzero(timestamps == t2_timestamp)
                if len(matches):
                    t2_offset = int(matches[0])
        t2_offset = min(max(0, t2_offset), len(segment) - 1)

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(
            x,
            speed,
            color="black",
            linewidth=1.4,
            marker="o",
            markersize=3,
            markerfacecolor="black",
            markeredgecolor="black",
            label="raw/repaired speed",
        )
        threshold = pd.to_numeric(pd.Series([ep.get("threshold_used")]), errors="coerce").iloc[0]
        if np.isfinite(threshold):
            ax.axhline(threshold, color="tab:red", linestyle="--", linewidth=1, label="congested threshold")
        ax.axvline(x.iloc[0], color="tab:orange", linestyle="--", linewidth=1, label="t0")
        ax.axvline(x.iloc[t2_offset], color="tab:purple", linestyle=":", linewidth=1.5, label="t2")
        ax.axvline(x.iloc[-1], color="tab:green", linestyle="--", linewidth=1, label="t3")

        hour_ticks = []
        hour_labels = []
        seen_hours = set()
        for ts in timestamps:
            if pd.isna(ts):
                continue
            hour = int(ts.hour)
            if hour in seen_hours:
                continue
            seen_hours.add(hour)
            hour_ticks.append(ts)
            hour_labels.append(str(hour))
        if hour_ticks:
            ax.set_xticks(hour_ticks)
            ax.set_xticklabels(hour_labels)

        entity = str(ep.get("entity_id", "entity"))
        date = str(ep.get("date", "")) or "weekday_average"
        ax.set_title(f"valid episode - {entity} / {date} / {ep.get('t0')} to {ep.get('t3')}")
        ax.set_ylabel("Speed (mph)")
        ax.set_xlabel("Time of day")
        handles, labels = ax.get_legend_handles_labels()
        unique = dict(zip(labels, handles))
        ax.legend(unique.values(), unique.keys(), loc="best", fontsize=8)
        fig.tight_layout()
        filename = (
            f"{sequence:04d}_{_safe_id(entity)}_{_safe_id(date)}_"
            f"{_safe_id(ep.get('t0'))}_{_safe_id(ep.get('t3'))}.png"
        )
        fig.savefig(fig_dir / filename, dpi=140)
        plt.close(fig)
        plotted += 1

    logger.info("Valid episode window figures saved: %s", plotted)


def plot_episode_diagnostics(
    episodes: pd.DataFrame,
    out_dir: Path,
    logger: logging.Logger,
) -> None:
    """Plot episode-level distributions and relationship diagnostics."""
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        logger.warning("matplotlib unavailable; skipped episode diagnostics (%s)", exc)
        return
    if episodes.empty:
        logger.info("No episodes detected; skipped episode diagnostic figures.")
        return

    public = episodes.drop(columns=["_start_idx", "_end_idx", "_group_key"], errors="ignore").copy()
    public["speed_reduction_ratio"] = (
        (public["threshold_used"] - public["min_speed_mph"]) / public["threshold_used"]
    ).replace([np.inf, -np.inf], np.nan)
    t0 = pd.to_datetime(public.get("t0_timestamp"), errors="coerce")
    t2 = pd.to_datetime(public.get("t2_timestamp"), errors="coerce")
    t2_minus_t0_min = (t2 - t0).dt.total_seconds() / 60.0
    duration = pd.to_numeric(public.get("duration_min"), errors="coerce")
    public["time_to_min_speed_ratio"] = (t2_minus_t0_min / duration).replace([np.inf, -np.inf], np.nan)

    dist_specs = [
        ("min_speed_mph", "Minimum speed (mph)", "distribution_min_speed_mph.png"),
        ("mean_speed_mph", "Mean speed (mph)", "distribution_mean_speed_mph.png"),
        ("duration_min", "Congestion duration (min)", "distribution_congestion_duration_min.png"),
        (
            "time_to_min_speed_ratio",
            "(t2 - t0) / congestion duration",
            "distribution_time_to_min_speed_ratio.png",
        ),
        (
            "severe_congestion_duration_min",
            "Severe congestion duration (min)",
            "distribution_severe_congestion_duration_min.png",
        ),
        ("discharge_duration_min", "Discharge duration (min)", "distribution_discharge_duration_min.png"),
        ("mu_obs_vphpl", "Observed discharge flow (vphpl)", "distribution_mu_obs_vphpl.png"),
        ("demand_capacity_ratio", "Demand / capacity", "distribution_demand_capacity_ratio.png"),
    ]
    category_specs = [
        ("regime_label", "Regime label", "distribution_regime_label.png"),
        ("measured_outlier_flag", "Measured outlier flag", "distribution_measured_outlier_flag.png"),
    ]
    relationship_specs = [
        (
            "demand_capacity_ratio",
            "duration_min",
            "Demand / capacity",
            "Congestion duration (min)",
            "relationship_duration_vs_demand_capacity.png",
        ),
        (
            "demand_capacity_ratio",
            "min_speed_mph",
            "Demand / capacity",
            "Minimum speed (mph)",
            "relationship_min_speed_vs_demand_capacity.png",
        ),
        (
            "demand_capacity_ratio",
            "mean_speed_mph",
            "Demand / capacity",
            "Mean speed (mph)",
            "relationship_mean_speed_vs_demand_capacity.png",
        ),
        (
            "duration_min",
            "speed_reduction_ratio",
            "Congestion duration (min)",
            "(threshold - min speed) / threshold",
            "relationship_speed_reduction_vs_duration.png",
        ),
    ]

    dist_dir = out_dir / "figures" / "episode_distributions"
    rel_dir = out_dir / "figures" / "episode_relationships"
    dist_dir.mkdir(parents=True, exist_ok=True)
    rel_dir.mkdir(parents=True, exist_ok=True)
    for folder in (dist_dir, rel_dir):
        for old_png in folder.glob("*.png"):
            old_png.unlink()

    dist_count = 0
    for col, xlabel, filename in dist_specs:
        values = pd.to_numeric(public.get(col), errors="coerce").dropna()
        if values.empty:
            logger.warning("Skipped distribution for %s: no finite values.", col)
            continue
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(values, bins=min(40, max(10, int(np.sqrt(len(values))))), color="steelblue", edgecolor="white")
        ax.set_title(f"Distribution of {xlabel}")
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Episode count")
        fig.tight_layout()
        fig.savefig(dist_dir / filename, dpi=140)
        plt.close(fig)
        dist_count += 1

    for col, xlabel, filename in category_specs:
        if col not in public.columns:
            continue
        counts = public[col].fillna("").astype(str).value_counts()
        if counts.empty:
            continue
        fig, ax = plt.subplots(figsize=(7, 4))
        counts.plot(kind="bar", ax=ax, color="steelblue")
        ax.set_title(f"Distribution of {xlabel}")
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Episode count")
        ax.tick_params(axis="x", rotation=30)
        fig.tight_layout()
        fig.savefig(dist_dir / filename, dpi=140)
        plt.close(fig)
        dist_count += 1

    rel_count = 0
    for x_col, y_col, xlabel, ylabel, filename in relationship_specs:
        x = pd.to_numeric(public.get(x_col), errors="coerce")
        y = pd.to_numeric(public.get(y_col), errors="coerce")
        mask = x.notna() & y.notna()
        if not mask.any():
            logger.warning("Skipped relationship %s vs %s: no finite pairs.", y_col, x_col)
            continue
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.scatter(x[mask], y[mask], s=18, alpha=0.65, color="tab:blue", edgecolors="none")
        ax.set_title(f"{ylabel} vs {xlabel}")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(True, linewidth=0.4, alpha=0.35)
        fig.tight_layout()
        fig.savefig(rel_dir / filename, dpi=140)
        plt.close(fig)
        rel_count += 1

    logger.info("Episode distribution figures saved: %s", dist_count)
    logger.info("Episode relationship figures saved: %s", rel_count)


def _valid_episode_mask(episodes: pd.DataFrame) -> pd.Series:
    if episodes.empty:
        return pd.Series(dtype=bool)
    valid_for_mu = episodes.get("is_valid_for_mu", pd.Series(False, index=episodes.index))
    measured_outlier = episodes.get("measured_outlier_flag", pd.Series(False, index=episodes.index))
    return valid_for_mu.fillna(False).astype(bool) & ~measured_outlier.fillna(False).astype(bool)


def build_episode_time_series(episodes: pd.DataFrame, entity_frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Extract Stage 1 time-series intervals from t0 through t3 for valid episodes."""
    columns = [
        "episode_id",
        "episode_sequence",
        "method",
        "aggregation_mode",
        "entity_id",
        "date",
        "t0",
        "t2",
        "t3",
        "interval_index",
        "interval_from_t0",
        "timestamp",
        "time_of_day",
        "speed_mph",
        "flow",
        "per_lane_hourly_capacity",
        "corridor_freeflow_speed_mph",
    ]
    if episodes.empty:
        return pd.DataFrame(columns=columns)

    frame_lookup = {_group_key(frame): frame for frame in entity_frames}
    pieces = []
    for sequence, (_, episode) in enumerate(episodes.iterrows(), start=1):
        key = episode.get("_group_key")
        frame = frame_lookup.get(key)
        if frame is None:
            continue

        start = max(0, int(episode["_start_idx"]))
        end = min(len(frame) - 1, int(episode["_end_idx"]))
        if end < start:
            continue

        segment = frame.iloc[start:end + 1].copy().reset_index(drop=True)
        episode_id = (
            f"{episode['aggregation_mode']}__{_safe_id(episode['entity_id'])}__"
            f"{_safe_id(episode['date'] or 'weekday_average')}__"
            f"{_safe_id(episode['t0'])}__{_safe_id(episode['t3'])}"
        )
        segment.insert(0, "episode_id", episode_id)
        segment.insert(1, "episode_sequence", sequence)
        segment.insert(2, "method", episode["method"])
        segment.insert(3, "interval_index", np.arange(start, end + 1, dtype=int))
        segment.insert(4, "interval_from_t0", np.arange(0, end - start + 1, dtype=int))
        for col in ["t0", "t2", "t3"]:
            segment[col] = episode[col]
        pieces.append(segment)

    if not pieces:
        return pd.DataFrame(columns=columns)

    out = pd.concat(pieces, ignore_index=True)
    for col in columns:
        if col not in out.columns:
            out[col] = np.nan
    return out[columns]


def write_outputs(
    config: StateTransitionConfig,
    episodes: pd.DataFrame,
    summary: pd.DataFrame,
    out_dir: Path,
    entity_frames: list[pd.DataFrame],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(__name__)
    valid_mask = _valid_episode_mask(episodes)
    valid_episodes = episodes.loc[valid_mask].copy() if not episodes.empty else episodes.copy()
    invalid_episodes = episodes.loc[~valid_mask].copy() if not episodes.empty else episodes.copy()
    valid_public = valid_episodes.drop(columns=["_start_idx", "_end_idx", "_group_key"], errors="ignore")
    invalid_public = invalid_episodes.drop(columns=["_start_idx", "_end_idx", "_group_key"], errors="ignore")
    episode_time_series = build_episode_time_series(valid_episodes, entity_frames)

    with open(out_dir / "config_used.json", "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2, default=str)
    valid_public.to_csv(out_dir / "state_transition_episodes.csv", index=False)
    invalid_public.to_csv(out_dir / "state_transition_invalid_episodes.csv", index=False)
    episode_time_series.to_csv(out_dir / "state_transition_episodes_td.csv", index=False)
    summary.to_csv(out_dir / "state_transition_summary.csv", index=False)
    stale_reliability = out_dir / "entity_reliability.csv"
    if stale_reliability.exists():
        stale_reliability.unlink()
    with open(out_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write("Standalone Stage 2 state-transition detector outputs\n")
        f.write("These are diagnostic experiments, not final calibrated Stage 2 results.\n\n")
        f.write(f"Outputs saved at: {out_dir}\n")
        f.write("Main files:\n")
        f.write("- config_used.json\n")
        f.write("- state_transition_episodes.csv (valid for mu and not measured outliers)\n")
        f.write("- state_transition_invalid_episodes.csv\n")
        f.write("- state_transition_episodes_td.csv\n")
        f.write("- state_transition_summary.csv\n")
        f.write("- figures/state_transition/*.png\n")
        f.write("- figures/state_transition_valid_episode_windows/*.png\n")
        f.write("- figures/episode_distributions/*.png\n")
        f.write("- figures/episode_relationships/*.png\n")
        f.write("\nNew calibration-prep episode fields include regime_label, is_valid_for_mu,\n")
        f.write("discharge window fields, mu_obs_vphpl, and measured outlier flags.\n")

    logger.info("Wrote config_used.json")
    logger.info("Wrote state_transition_episodes.csv rows=%s", len(valid_public))
    logger.info("Wrote state_transition_invalid_episodes.csv rows=%s", len(invalid_public))
    logger.info("Wrote state_transition_episodes_td.csv rows=%s", len(episode_time_series))
    logger.info("Wrote state_transition_summary.csv rows=%s", len(summary))
    logger.info("Wrote README.txt and warnings.log")


def _log_config(logger: logging.Logger, config: StateTransitionConfig, out_dir: Path) -> None:
    mode = "multiday average profile" if config.use_multiday_average else "sensor-day"
    logger.info("Input Stage 1 folder: %s", config.stage1_dir)
    logger.info("Output folder: %s", out_dir)
    logger.info("Aggregation mode: %s", mode)
    logger.info("Speed field: %s", config.source_speed_col)
    logger.info(
        "QC filter: %s",
        f"{config.qc_pass_repaired_col} == 1" if config.use_qc_pass_repaired_only else "all points",
    )
    logger.info("Minimum episode duration: %.1f min", config.min_duration_min)
    logger.info(
        "Thresholds: free_ratio=%.3f congested_ratio=%.3f freeflow_percentile=%.1f",
        config.free_threshold_ratio,
        config.congested_threshold_ratio,
        config.freeflow_percentile,
    )
    logger.info(
        "Free-flow source: use_stage0_corridor_freeflow=%s source_col=%s percentile_fallback=%.1f",
        config.use_stage0_corridor_freeflow,
        config.source_corridor_freeflow_col,
        config.freeflow_percentile,
    )
    logger.info(
        "Transition params: breakdown_drop=%.1f mph window=%s recovery_rise=%.1f mph exit_confirm=%s max_noncongested_gap=%s",
        config.breakdown_drop_mph,
        config.breakdown_window_intervals,
        config.recovery_rise_mph,
        config.exit_confirm_intervals,
        config.max_noncongested_gap_intervals,
    )
    logger.info(
        "Rolling extension: enabled=%s intervals=%s ratio=%.3f",
        config.allow_rolling_mean_extension,
        config.rolling_mean_extension_intervals,
        config.rolling_mean_extension_ratio,
    )
    logger.info(
        "Detection smoothing: enabled=%s method=%s window=%s polyorder=%s plot=%s",
        config.use_detection_smoothing,
        config.detection_smoothing_method,
        config.detection_smoothing_window_intervals,
        config.detection_smoothing_polyorder,
        config.plot_detection_smoothed_speed,
    )
    logger.info(
        "Discharge validity: min_duration=%.1f min positive_dq_share=%.2f allow_net_increasing=%s min_speed_gain=%.1f require_congested_speed=%s",
        config.min_discharge_duration_min,
        config.min_discharge_positive_dq_share,
        config.allow_net_increasing_discharge,
        config.min_discharge_speed_gain_mph,
        config.require_congested_speed_for_discharge,
    )
    logger.info("Measured outlier flags enabled: %s", config.enable_measured_outlier_flags)
    logger.info(
        "MAD outlier flags: enabled=%s duration_z=%.2f demand_capacity_ratio_z=%.2f min_reference=%s",
        config.enable_mad_outlier_flags,
        config.duration_mad_z_threshold,
        config.demand_capacity_ratio_mad_z_threshold,
        config.min_valid_episodes_for_global_mad_outlier_detection,
    )


def _log_input_summary(logger: logging.Logger, df: pd.DataFrame, frames: list[pd.DataFrame]) -> None:
    logger.info(
        "Weekday input: rows=%s, finite_speed=%s, entities=%s, dates=%s",
        f"{len(df):,}",
        f"{int(df['speed_mph'].notna().sum()):,}",
        df["entity_id"].nunique(),
        df["date"].nunique(),
    )
    logger.info("Weekday time range: %s to %s", df["timestamp"].min(), df["timestamp"].max())
    logger.info("Detection entity frames prepared: %s", f"{len(frames):,}")


def _log_detector_summary(logger: logging.Logger, summary: pd.DataFrame) -> None:
    if summary.empty:
        logger.info("State-transition summary: no episodes detected.")
        return
    row = summary.iloc[0]
    logger.info(
        "State-transition summary: episodes=%s, median_duration=%.1f min, congested_share=%.3f, mean_min_speed=%.1f mph",
        int(row["n_episodes"]),
        float(row["median_duration_min"]),
        float(row["share_observed_time_congested"]),
        float(row["mean_min_speed_mph"]),
    )


def run_state_transition(config: StateTransitionConfig | None = None) -> dict:
    """Run the standalone state-transition detector and write artifacts."""
    config = config or StateTransitionConfig()
    project_root = project_root_from_cwd()
    out_dir = project_path(config.output_folder, project_root)
    logger = _configure_logging(out_dir)

    logger.info("=" * 72)
    logger.info("Standalone Stage 2 state-transition detector start")
    logger.info("These are diagnostic experiments, not final calibrated Stage 2 results.")
    _log_config(logger, config, out_dir)

    df = load_experiment_input(config, project_root=project_root)
    entity_frames = make_entity_frames(df, config)
    _log_input_summary(logger, df, entity_frames)

    logger.info("Detector start: state_transition")
    episodes = run_detector(entity_frames, config)
    logger.info("Detector end: state_transition episodes=%s", len(episodes))

    valid_episodes = episodes.loc[_valid_episode_mask(episodes)].copy()
    summary = detector_summary(valid_episodes, entity_frames, config, outlier_episodes=episodes)
    _log_detector_summary(logger, summary)
    logger.info("Generating figures...")
    plotted_state_transition_keys = plot_state_transition_samples(episodes, entity_frames, config, out_dir, logger)
    plot_valid_episode_windows(valid_episodes, entity_frames, plotted_state_transition_keys, out_dir, logger)
    plot_episode_diagnostics(valid_episodes, out_dir, logger)
    logger.info("Writing output artifacts...")
    write_outputs(config, episodes, summary, out_dir, entity_frames)

    message = (
        "\nStandalone Stage 2 state-transition detector complete.\n"
        "These are diagnostic experiments, not final calibrated Stage 2 results.\n"
        f"Total episodes detected: {len(episodes)}\n"
        f"Valid episodes written: {len(valid_episodes)}\n"
        f"Outputs saved at: {out_dir}\n"
    )
    print(message)
    logger.info("Standalone state-transition detector end: output=%s", out_dir)
    logger.info("=" * 72)
    return {
        "out_dir": str(out_dir),
        "n_episodes": int(len(episodes)),
        "episodes": episodes,
        "summary": summary,
        "config": config,
    }


def main() -> int:
    common = dict(
        source_speed_col="speed_mph_clean_repaired",
        # Change this if Stage 1 uses a different flow/volume column name.
        source_flow_col="flow_vph",
        # Change this if Stage 1 uses a different per-lane hourly capacity column name.
        # If unavailable, per-lane capacity defaults to 2000 vphpl.
        source_capacity_col="per_lane_hourly_capacity",
        source_corridor_freeflow_col="corridor_freeflow_speed_mph",
        use_stage0_corridor_freeflow=True,
        default_per_lane_capacity_vphpl=2000.0,
        uncongested_max_duration_min=30.0,
        mild_max_duration_min=60.0,
        recurring_min_duration_min=60.0,
        severe_min_duration_min=120.0,
        severe_min_speed_ratio=0.50,
        mild_speed_ratio_lo=0.70,
        event_z_threshold=2.5,
        min_discharge_duration_min=30.0,
        min_discharge_positive_dq_share=0.60,
        allow_net_increasing_discharge=True,
        min_discharge_speed_gain_mph=0.0,
        require_congested_speed_for_discharge=True,
        enable_measured_outlier_flags=True,
        outlier_doc_high_threshold=1.0,
        outlier_doc_low_threshold=0.5,
        outlier_doc_low_high_duration_min=60.0,
        outlier_mu_capacity_ratio_high=1.05,
        outlier_mu_starved_doc_threshold=1.5,
        outlier_mu_starved_capacity_ratio=0.30,
        outlier_vt2_min_mph=5.0,
        enable_mad_outlier_flags=True,
        duration_mad_z_threshold=3.5,
        demand_capacity_ratio_mad_z_threshold=3.5,
        min_valid_episodes_for_global_mad_outlier_detection=10,
        use_qc_pass_repaired_only=True,
        qc_pass_repaired_col="qc_pass_repaired",
        min_duration_min=30.0,
        merge_gap_min=15.0,
        freeflow_percentile=95.0,
        free_threshold_ratio=0.85,
        congested_threshold_ratio=0.70,
        breakdown_drop_mph=10.0,
        breakdown_window_intervals=2,
        recovery_rise_mph=10.0,
        exit_confirm_intervals=2,
        max_noncongested_gap_intervals=3,
        allow_rolling_mean_extension=True,
        rolling_mean_extension_intervals=6,
        rolling_mean_extension_ratio=1.0,
        use_detection_smoothing=True,
        detection_smoothing_method="savgol",
        detection_smoothing_window_intervals=5,
        detection_smoothing_polyorder=2,
        plot_detection_smoothed_speed=True,
        max_figures=100,
        sample_sensor_count=None,
        sample_days_per_sensor=None,
    )
    daily_config = StateTransitionConfig(
        stage1_dir="cbi_outputs/stage1_qc/raw",
        output_folder="cbi_outputs/stage2_state_transition/daily",
        source_datetime_col="datetime",
        use_multiday_average=False,
        **common,
    )
    multiday_config = StateTransitionConfig(
        stage1_dir="cbi_outputs/stage1_qc/multiday_average",
        output_folder="cbi_outputs/stage2_state_transition/multiday_average",
        source_datetime_col="minute_of_day",
        use_multiday_average=True,
        **common,
    )
    run_state_transition(daily_config)
    run_state_transition(multiday_config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
