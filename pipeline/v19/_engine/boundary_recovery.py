"""Boundary recovery ported from CBI-TAPLite commit 1ce571f80e34.

Only boundary recovery is imported; sampling and detectors remain QVDFE's.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Literal
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class StateTransitionConfig:
    boundary_speed_max_mph: float = 90.0
    boundary_speed_max_factor: float = 1.25
    t0_onset_search_intervals: int = 2
    t3_recovery_search_intervals: int = 2
    allow_pre_qc_t0_speed_fallback: bool = True
    allow_pre_qc_t3_speed_fallback: bool = True
    min_discharge_speed_gain_mph: float = 0.0

def _is_physical_boundary_speed(
    value: float,
    config: StateTransitionConfig,
    freeflow_speed_mph: float,
) -> bool:
    upper = float(config.boundary_speed_max_mph)
    if np.isfinite(freeflow_speed_mph) and freeflow_speed_mph > 0.0:
        upper = min(
            upper,
            float(config.boundary_speed_max_factor)
            * float(freeflow_speed_mph),
        )
    return bool(
        np.isfinite(value)
        and 0.0 <= float(value) <= upper
    )


def _directional_speed_fallback(
    clean_speed: np.ndarray,
    pre_qc_speed: np.ndarray,
    *,
    boundary_idx: int,
    direction: Literal["backward", "forward"],
    search_intervals: int,
    freeflow_speed_mph: float,
    config: StateTransitionConfig,
    allow_pre_qc_fallback: bool,
    search_candidate_is_valid: Callable[[float, int], bool] | None = None,
    pre_qc_candidate_is_valid: Callable[[float, int], bool] | None = None,
) -> dict[str, object]:
    """Recover one speed without assigning any episode-boundary meaning.

    The original cleaned value is retained when physical.  Otherwise the
    helper searches cleaned values in the requested direction and finally may
    use the pre-QC value at the original index.  It reports a candidate index,
    but the caller alone decides whether that index changes a T0, T3, or any
    future boundary.
    """

    clean = np.asarray(clean_speed, dtype=float)
    pre_qc = np.asarray(pre_qc_speed, dtype=float)
    if not len(clean):
        raise ValueError("clean_speed must contain at least one value")
    if len(pre_qc) != len(clean):
        raise ValueError("clean_speed and pre_qc_speed must have equal length")
    if direction not in {"backward", "forward"}:
        raise ValueError("direction must be 'backward' or 'forward'")

    original_idx = min(max(int(boundary_idx), 0), len(clean) - 1)
    original_post_qc = clean[original_idx]
    original_pre_qc = pre_qc[original_idx]

    if _is_physical_boundary_speed(
        original_post_qc, config, freeflow_speed_mph
    ):
        return {
            "resolved_idx": original_idx,
            "speed_mph": float(original_post_qc),
            "source": "post_qc",
            "shift_intervals": 0,
            "original_speed_post_qc_mph": float(original_post_qc),
            "original_speed_pre_qc_mph": (
                float(original_pre_qc)
                if np.isfinite(original_pre_qc)
                else np.nan
            ),
        }

    step = -1 if direction == "backward" else 1
    max_search = max(0, int(search_intervals))
    for offset in range(1, max_search + 1):
        candidate_idx = original_idx + step * offset
        if candidate_idx < 0 or candidate_idx >= len(clean):
            break
        candidate_speed = clean[candidate_idx]
        if not _is_physical_boundary_speed(
            candidate_speed, config, freeflow_speed_mph
        ):
            continue
        if (
            search_candidate_is_valid is not None
            and not search_candidate_is_valid(
                float(candidate_speed), candidate_idx
            )
        ):
            continue
        return {
            "resolved_idx": candidate_idx,
            "speed_mph": float(candidate_speed),
            "source": "shifted_post_qc",
            "shift_intervals": candidate_idx - original_idx,
            "original_speed_post_qc_mph": np.nan,
            "original_speed_pre_qc_mph": (
                float(original_pre_qc)
                if np.isfinite(original_pre_qc)
                else np.nan
            ),
        }

    if (
        allow_pre_qc_fallback
        and _is_physical_boundary_speed(
            original_pre_qc, config, freeflow_speed_mph
        )
        and (
            pre_qc_candidate_is_valid is None
            or pre_qc_candidate_is_valid(
                float(original_pre_qc), original_idx
            )
        )
    ):
        return {
            "resolved_idx": original_idx,
            "speed_mph": float(original_pre_qc),
            "source": "pre_qc_fallback",
            "shift_intervals": 0,
            "original_speed_post_qc_mph": np.nan,
            "original_speed_pre_qc_mph": float(original_pre_qc),
        }

    return {
        "resolved_idx": original_idx,
        "speed_mph": np.nan,
        "source": "missing",
        "shift_intervals": 0,
        "original_speed_post_qc_mph": np.nan,
        "original_speed_pre_qc_mph": (
            float(original_pre_qc)
            if np.isfinite(original_pre_qc)
            else np.nan
        ),
    }


def _speed_arrays(entity_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    clean = pd.to_numeric(
        entity_df["speed_mph"], errors="coerce"
    ).to_numpy(dtype=float)
    pre_qc_column = (
        entity_df["speed_mph_pre_qc"]
        if "speed_mph_pre_qc" in entity_df
        else entity_df["speed_mph"]
    )
    pre_qc = pd.to_numeric(
        pre_qc_column, errors="coerce"
    ).to_numpy(dtype=float)
    return clean, pre_qc


def _resolve_t0_boundary(
    entity_df: pd.DataFrame,
    *,
    t0_idx: int,
    congested_threshold: float,
    freeflow_speed_mph: float,
    config: StateTransitionConfig,
) -> dict[str, object]:
    """Resolve the onset speed and let this T0 section move T0 backward."""

    clean, pre_qc = _speed_arrays(entity_df)
    fallback = _directional_speed_fallback(
        clean,
        pre_qc,
        boundary_idx=t0_idx,
        direction="backward",
        search_intervals=config.t0_onset_search_intervals,
        freeflow_speed_mph=freeflow_speed_mph,
        config=config,
        allow_pre_qc_fallback=config.allow_pre_qc_t0_speed_fallback,
        search_candidate_is_valid=lambda value, _index: (
            value >= congested_threshold
        ),
    )
    return {
        "t0_idx": fallback["resolved_idx"],
        "t0_boundary_speed_mph": fallback["speed_mph"],
        "t0_boundary_speed_source": fallback["source"],
        "t0_boundary_shift_intervals": fallback["shift_intervals"],
        "original_t0_speed_post_qc_mph": fallback[
            "original_speed_post_qc_mph"
        ],
        "original_t0_speed_pre_qc_mph": fallback[
            "original_speed_pre_qc_mph"
        ],
    }


def _resolve_t3_boundary(
    entity_df: pd.DataFrame,
    *,
    t2_idx: int,
    t3_idx: int,
    congested_threshold: float,
    freeflow_speed_mph: float,
    config: StateTransitionConfig,
) -> dict[str, object]:
    """Resolve the recovery speed and let this T3 section move T3 forward."""

    clean, pre_qc = _speed_arrays(entity_df)
    t2_speed = (
        clean[int(t2_idx)]
        if 0 <= int(t2_idx) < len(clean)
        else np.nan
    )

    def recovered(value: float, _index: int) -> bool:
        return bool(
            np.isfinite(t2_speed)
            and value >= congested_threshold
            and value - t2_speed >= config.min_discharge_speed_gain_mph
        )

    def usable_delta_v(value: float, _index: int) -> bool:
        return bool(
            np.isfinite(t2_speed)
            and value - t2_speed >= config.min_discharge_speed_gain_mph
        )

    fallback = _directional_speed_fallback(
        clean,
        pre_qc,
        boundary_idx=t3_idx,
        direction="forward",
        search_intervals=config.t3_recovery_search_intervals,
        freeflow_speed_mph=freeflow_speed_mph,
        config=config,
        allow_pre_qc_fallback=config.allow_pre_qc_t3_speed_fallback,
        search_candidate_is_valid=recovered,
        pre_qc_candidate_is_valid=usable_delta_v,
    )
    return {
        "t3_idx": fallback["resolved_idx"],
        "t3_boundary_speed_mph": fallback["speed_mph"],
        "t3_boundary_speed_source": fallback["source"],
        "t3_boundary_shift_intervals": fallback["shift_intervals"],
        "original_t3_speed_post_qc_mph": fallback[
            "original_speed_post_qc_mph"
        ],
        "original_t3_speed_pre_qc_mph": fallback[
            "original_speed_pre_qc_mph"
        ],
    }
