"""Column contracts for the refreshed CBI package."""

from __future__ import annotations

from typing import Final


TIMESERIES_COLUMNS: Final = [
    "sensor_uid",
    "datetime",
    "speed_mph",
    "corridor_freeflow_speed_mph",
    "flow_vph",
    "density_vpm",
    "has_volume",
    "flow_synthetic",
    "source_format",
    "lanes",
    "length_mi",
    "road_order",
    "direction",
    "corridor",
]


STAGE1_QC_COLUMNS: Final = [
    "speed_mph_raw",
    "qc_hard_range",
    "qc_hampel",
    "hampel_replacement",
    "qc_jump",
    "qc_spatial_lag",
    "qc_pass",
    "speed_mph_clean",
    "speed_mph_clean_repaired",
    "qc_repaired_flag",
    "qc_repair_method",
    "qc_pass_repaired",
    "stage1_dataset_kind",
]


STAGE1_FLAG_COLUMNS: Final = [
    "qc_hard_range",
    "qc_hampel",
    "qc_jump",
    "qc_spatial_lag",
]


S3_PRIOR_PRESETS: Final = {
    "cbi_default": {
        "vf_mph": 70.0,
        "k_critical_vpm": 45.0,
        "s3_m": 4.0,
        "lane_capacity_vphpl": 2200.0,
        "provenance": "CBI legacy default - urban Phoenix",
    },
    "urban_freeway": {
        "vf_mph": 65.0,
        "k_critical_vpm": 50.0,
        "s3_m": 4.0,
        "lane_capacity_vphpl": 2200.0,
        "provenance": "Generic urban interstate prior",
    },
    "rural_freeway": {
        "vf_mph": 75.0,
        "k_critical_vpm": 32.0,
        "s3_m": 4.0,
        "lane_capacity_vphpl": 1900.0,
        "provenance": "Generic rural interstate prior",
    },
    "az_tmc_i17": {
        "vf_mph": 75.0,
        "k_critical_vpm": 32.0,
        "s3_m": 4.0,
        "lane_capacity_vphpl": 1900.0,
        "provenance": "AZ INRIX I-17 placeholder prior",
    },
    "ca_pems_freeway": {
        "vf_mph": 65.0,
        "k_critical_vpm": 50.0,
        "s3_m": 4.0,
        "lane_capacity_vphpl": 2200.0,
        "provenance": "California PeMS urban freeway prior",
    },
    "arterial": {
        "vf_mph": 45.0,
        "k_critical_vpm": 35.0,
        "s3_m": 4.0,
        "lane_capacity_vphpl": 1500.0,
        "provenance": "Signalized arterial prior",
    },
}


DEFAULT_S3_PARAMS: Final = {
    k: v for k, v in S3_PRIOR_PRESETS["cbi_default"].items()
    if k != "provenance"
}


def resolve_s3_prior(prior) -> dict:
    """Resolve an S3 prior preset name, parameter dict, or ``None``."""
    if prior is None:
        prior = "cbi_default"
    if isinstance(prior, str):
        if prior not in S3_PRIOR_PRESETS:
            raise ValueError(
                f"Unknown S3 prior preset: {prior!r}. "
                f"Choose from {sorted(S3_PRIOR_PRESETS)} or pass a dict."
            )
        return dict(S3_PRIOR_PRESETS[prior])
    if isinstance(prior, dict):
        out = dict(S3_PRIOR_PRESETS["cbi_default"])
        out.update(prior)
        out.setdefault("provenance", "user-supplied dict")
        return out
    raise TypeError(f"s3_prior must be str | dict | None, got {type(prior).__name__}")
