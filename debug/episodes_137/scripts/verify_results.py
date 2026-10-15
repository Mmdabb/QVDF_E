"""Compare regenerated diagnostics with the checked-in reference bundle."""
import json
import math
import pandas as pd
from _paths import REFERENCE, arguments

args = arguments(__doc__)
checked = []
for reference in sorted((REFERENCE / "results").glob("*.csv")):
    actual = args.output / reference.name
    pd.testing.assert_frame_equal(pd.read_csv(reference), pd.read_csv(actual),
                                  check_exact=False, rtol=1e-10, atol=1e-10)
    checked.append(reference.name)
pd.testing.assert_frame_equal(
    pd.read_csv(REFERENCE / "audits/reproduction_checks.csv"),
    pd.read_csv(args.output / "support/reproduction_checks.csv"),
    check_exact=False, rtol=1e-10, atol=1e-10)


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
        assert (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10), location
    else:
        assert a == b, location


compare(json.loads((REFERENCE / "results/summary.json").read_text()),
        json.loads((args.output / "summary.json").read_text()))
for name in ["attribution_review.json", "calibration_review.json", "average_speed_identity_summary.json"]:
    compare(json.loads((REFERENCE / "audits" / name).read_text()),
            json.loads((args.output / "support" / name).read_text()), name)
    checked.append(name)
report = {"status": "pass", "comparison": "Reference tables and detailed JSON diagnostics reproduced",
          "CSV_files": 12, "JSON_files": 4, "rtol": 1e-10, "atol": 1e-10,
          "checked": checked + ["reproduction_checks.csv", "summary.json"]}
(args.output / "support/bundle_reproduction_check.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
