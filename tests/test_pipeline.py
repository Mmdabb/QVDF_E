"""Regression checks against frozen empirical results, not only synthetic formulas."""
from pathlib import Path
import json
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest

from qvdfe.pipeline._engine import model, calibration
from qvdfe.pipeline._engine.emissions import MovesRates
from qvdfe.pipeline._engine.two_regime_emissions import exact_rate_for_speed, gamma_from_rate
from qvdfe.pipeline.cli import manifest_sources, protect_output

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/frozen/calibration"


@pytest.mark.parametrize("track", ["daily_validation", "average_weekday"])
def test_observed_qc_and_fitted_predictions_reproduce_frozen_cards(track):
    original = pd.read_csv(DATA / track / "episode_results_v2.csv")
    parameters = pd.read_csv(DATA / track / "parameter_card.csv")
    qc = calibration.add_outlier_flags(original)
    np.testing.assert_array_equal(qc.calibration_eligible, original.calibration_eligible)
    np.testing.assert_array_equal(qc.outlier_votes, original.outlier_votes)
    raw = original.drop(columns=["calibration_scope", *model.PARAMS], errors="ignore")
    result = model.predictions(raw, parameters)
    for column in ["P_hat_h", "wt2_hat_h", "wt2_conditional_hat_h", "vt2_hat_mph", "mu_hat_vphpl", "vq_hat_mph"]:
        np.testing.assert_allclose(result[column], original[column], rtol=1e-10, atol=1e-10, equal_nan=True)
    np.testing.assert_array_equal(result.physical_predicted_pass, original.physical_predicted_pass)


def test_daily_training_outliers_do_not_depend_on_heldout_rows():
    episodes = pd.read_csv(DATA / "daily_validation/episode_results_v2.csv")
    original = calibration.add_outlier_flags(episodes)
    changed = episodes.copy()
    changed.loc[changed.holdout, ["x_h", "P_h", "wt2_h", "mu_obs_vphpl"]] *= 100
    rerun = calibration.add_outlier_flags(changed)
    np.testing.assert_array_equal(original.loc[~original.holdout, "outlier_votes"],
                                  rerun.loc[~rerun.holdout, "outlier_votes"])


def test_direct_lookup_keeps_operating_bins_and_negative_gamma():
    moves = MovesRates(
        {"source_mass": 1, "rolling_term_a": 0, "rotating_term_b": 0, "drag_term_c": 0},
        pd.DataFrame({"OpModeID": [12, 22, 33], "ER_CO2": [1., 5., 12.]}),
    )
    np.testing.assert_array_equal(exact_rate_for_speed(moves, [10., 20., 30., 60.], "CO2"), [1., 1., 5., 12.])
    gamma = gamma_from_rate(10., 60., lambda speed: exact_rate_for_speed(moves, speed, "CO2"))
    assert float(gamma) == pytest.approx(-1.2)


def test_closed_profile_rejects_negative_endpoint_arrivals():
    # The limiting parabola has its maximum recovery slope at an endpoint.
    # A finite interior grid alone can miss this small infeasibility.
    *_, admitted, minimum_arrival = model.profile_grid(1., .25001, 2 / 3)
    assert not admitted
    assert minimum_arrival == pytest.approx(-0.00004, abs=1e-10)


def test_output_guard_protects_inputs_and_frozen_data():
    with pytest.raises(ValueError):
        protect_output(ROOT / "data/frozen/calibration", [])
    with pytest.raises(ValueError):
        protect_output(ROOT / "build/source/nested", [ROOT / "build/source"])
    with pytest.raises(ValueError):
        protect_output(ROOT / "build", [ROOT / "build/source"])
    protect_output(ROOT / "build/new-result", [ROOT / "build/source"])


def test_output_guard_protects_manifested_files_outside_baseline():
    manifest = [{"path": "build/owned-result/raw-observations.csv", "sha256": "unused-in-path-resolution"}]
    with patch.object(Path, "read_text", return_value=json.dumps(manifest)):
        sources = manifest_sources(ROOT, ROOT / "external-baseline")
    with pytest.raises(ValueError):
        protect_output(ROOT / "build/owned-result", sources)
    protect_output(ROOT / "build/another-result", sources)
