"""Compare regenerated diagnostics with the checked-in reference bundle."""
import json
import math
import numpy as np
import pandas as pd
from _paths import REFERENCE, arguments

MODEL_RTOL = MODEL_ATOL = 1e-10
RESIDUAL_ULPS = 8


def verify_reproduction_checks(reference, actual):
    """Check quantities normally, and cancellation residuals on their source scale.

    ``absolute_difference`` is the historical name for the *signed* residual.
    Its own magnitude is not an appropriate scale for cross-platform roundoff:
    subtracting two million-gram totals can change it by one ULP of either total.
    Both source tables must still reproduce the quantities and their residual
    arithmetic. Callers use round-trip CSV parsing to preserve stored floats.
    """
    residuals = ["absolute_difference", "relative_difference"]
    pd.testing.assert_frame_equal(
        reference.drop(columns=residuals), actual.drop(columns=residuals),
        check_exact=False, rtol=MODEL_RTOL, atol=MODEL_ATOL)
    arithmetic_ulp_max = 0.0
    for label, frame in [("reference", reference), ("regenerated", actual)]:
        numbers = frame[["recomputed", "saved", *residuals]].to_numpy(float)
        assert np.isfinite(numbers).all(), f"{label}: nonfinite audit quantities"
        assert (frame.saved != 0).all(), f"{label}: relative residual requires nonzero saved value"
        np.testing.assert_allclose(frame.recomputed, frame.saved,
                                   rtol=MODEL_RTOL, atol=MODEL_ATOL,
                                   err_msg=f"{label}: recomputed versus saved quantities")
        scale = np.maximum(abs(frame.recomputed), abs(frame.saved))
        ulp = np.spacing(scale)
        delta = frame.recomputed - frame.saved
        arithmetic_error = abs(frame.absolute_difference - delta)
        assert (arithmetic_error <= RESIDUAL_ULPS * ulp).all(), (
            f"{label}: signed residual does not equal recomputed minus saved")
        arithmetic_ulp_max = max(arithmetic_ulp_max, float((arithmetic_error / ulp).max()))
        # Check division separately; a corrupted relative residual cannot hide
        # behind the cancellation allowance for recomputed - saved.
        relative = frame.absolute_difference / frame.saved
        relative_ulp = np.spacing(np.maximum(abs(relative), abs(frame.relative_difference)))
        assert (abs(frame.relative_difference - relative) <= RESIDUAL_ULPS * relative_ulp).all(), (
            f"{label}: relative residual does not equal signed residual / saved")

    scale = np.maximum.reduce([abs(frame[column]).to_numpy() for frame in (reference, actual)
                               for column in ("recomputed", "saved")])
    ulp = np.spacing(scale)
    tolerance = RESIDUAL_ULPS * ulp
    residual_change = abs(reference.absolute_difference - actual.absolute_difference).to_numpy()
    assert (residual_change <= tolerance).all(), (
        "Cross-platform signed residual changed by more than 8 ULPs of its source quantities")
    # Normalize with the same source scale, rather than relaxing every result
    # column's absolute tolerance to accommodate large emission totals.
    normalized_change = abs(reference.relative_difference - actual.relative_difference).to_numpy()
    saved_scale = np.minimum(abs(reference.saved), abs(actual.saved)).to_numpy()
    assert (normalized_change <= tolerance / saved_scale).all(), (
        "Cross-platform relative residual changed beyond its source-scale allowance")
    return {
        "rows": len(reference),
        "CSV_float_parser": "round_trip",
        "residual_definition": "signed: recomputed - saved; relative: signed / saved",
        "residual_tolerance": "8 * spacing(max(abs(recomputed), abs(saved))) across both tables",
        "residual_ULPs": RESIDUAL_ULPS,
        "source_scale_min": float(scale.min()),
        "source_scale_max": float(scale.max()),
        "source_scaled_absolute_tolerance_min": float(tolerance.min()),
        "source_scaled_absolute_tolerance_max": float(tolerance.max()),
        "maximum_residual_arithmetic_error_ULPs": arithmetic_ulp_max,
        "maximum_cross_platform_residual_change_ULPs": float((residual_change / ulp).max()),
    }


def compare(a, b, location=""):
    if isinstance(a, dict):
        assert a.keys() == b.keys(), location
        for key in a:
            compare(a[key], b[key], location + "/" + key)
    elif isinstance(a, list):
        assert len(a) == len(b), location
        for i, (x, y) in enumerate(zip(a, b)):
            compare(x, y, location + "/" + str(i))
    elif isinstance(a, float):
        assert (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=MODEL_RTOL, abs_tol=MODEL_ATOL), location
    else:
        assert a == b, location


def main():
    args = arguments(__doc__)
    checked = []
    for reference in sorted((REFERENCE / "results").glob("*.csv")):
        actual = args.output / reference.name
        pd.testing.assert_frame_equal(pd.read_csv(reference), pd.read_csv(actual),
                                      check_exact=False, rtol=MODEL_RTOL, atol=MODEL_ATOL)
        checked.append(reference.name)
    residual_check = verify_reproduction_checks(
        pd.read_csv(REFERENCE / "audits/reproduction_checks.csv", float_precision="round_trip"),
        pd.read_csv(args.output / "support/reproduction_checks.csv", float_precision="round_trip"))
    compare(json.loads((REFERENCE / "results/summary.json").read_text()),
            json.loads((args.output / "summary.json").read_text()))
    for name in ["attribution_review.json", "calibration_review.json", "average_speed_identity_summary.json"]:
        compare(json.loads((REFERENCE / "audits" / name).read_text()),
                json.loads((args.output / "support" / name).read_text()), name)
        checked.append(name)
    report = {"status": "pass", "comparison": "Reference tables and detailed JSON diagnostics reproduced",
              "CSV_files": 12, "JSON_files": 4, "rtol": MODEL_RTOL, "atol": MODEL_ATOL,
              "residual_check": residual_check,
              "checked": checked + ["reproduction_checks.csv", "summary.json"]}
    (args.output / "support/bundle_reproduction_check.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
