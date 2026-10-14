"""Regression against the unchanged empirical v19 results and screening boundaries."""
import numpy as np
import pytest

import qvdfe


@pytest.fixture(scope='module')
def lookup():
    return qvdfe.load_lookup_rates()


@pytest.mark.parametrize('pollutant', qvdfe.POLLUTANTS)
def test_lookup_reproduces_all_frozen_M_totals(pollutant, lookup):
    episodes = qvdfe.load_episodes()
    matched = episodes[episodes.matched_ladder_pass]
    assert len(matched) == 137
    calculated = [qvdfe.episode_total(r.D_veh, r.wbar_hat_h, r.L_mi, r.vf_mph,
                                     r.vq_hat_mph, lookup[pollutant]) for r in matched.itertuples()]
    np.testing.assert_allclose(calculated, matched[f'M_{pollutant}'], rtol=1e-10, atol=1e-9)
    # M and A are intentionally different rate representations on the same episodes.
    assert not np.allclose(calculated, matched[f'A_{pollutant}'], rtol=1e-4)


def test_explicit_rate_selection_preserves_default_and_array_shapes(lookup):
    default, cubic = qvdfe.load_rates(), qvdfe.load_cubic_rates()
    selected = qvdfe.load_rates(representation='lookup')
    for p in qvdfe.POLLUTANTS:
        np.testing.assert_array_equal(default[p]['coef'], cubic[p]['coef'])
        speeds = np.array([[5.0, 25.0], [50.0, 75.0]])
        np.testing.assert_array_equal(lookup[p](speeds), selected[p](speeds))
        assert lookup[p](speeds).shape == speeds.shape
        assert lookup[p](60.0).shape == ()
        assert np.isnan(lookup[p](np.nan))
    with pytest.raises(ValueError, match='representation'):
        qvdfe.load_rates(representation='unknown')


def test_complete_screen_reproduces_each_frozen_matched_flag():
    episodes = qvdfe.load_episodes()
    results = [qvdfe.screen_episode(row) for row in episodes.to_dict('records')]
    assert [r['matched_ladder_pass'] for r in results] == episodes.matched_ladder_pass.tolist()
    assert len(episodes) == 325
    assert sum(r['matched_ladder_pass'] for r in results) == 137
    for source, result in zip(episodes.to_dict('records'), results):
        if source['matched_ladder_pass']:
            assert np.isclose(result['arrival_min_relative'], source['arrival_min_relative'], atol=1e-12)


def test_traffic_validation_rows_do_not_imply_matched_emission_eligibility():
    # Daily data validate traffic fits; only average-weekday data have emissions.
    daily = qvdfe.load_episodes('daily_validation')
    assert 'M_CO2' not in daily.columns
    results = [qvdfe.screen_episode(row) for row in daily.to_dict('records')]
    assert not any(r['matched_ladder_pass'] for r in results)


def test_parabola_endpoint_negative_arrival_is_not_missed():
    profile = qvdfe.delay_profile(1.0, 0.25001, 2 / 3, 1500.0)
    assert np.isclose(profile['lam'][-1] / 1500, -0.00004, atol=1e-12)
    assert np.isclose(profile['lambda_min'] / 1500, -0.00004, atol=1e-12)
    assert not profile['profile_closed_pass']
    boundary = qvdfe.delay_profile(1.0, 0.25, 2 / 3, 1500.0)
    assert boundary['profile_closed_pass']
    assert np.isclose(boundary['lambda_min'], 0, atol=1e-12)


def test_analytic_arrival_check_does_not_depend_on_plotting_grid():
    # For h=[4u(1-u)]^2 the derivative extrema lie between a three-point grid.
    profile = qvdfe.delay_profile(1.0, 0.34, 8 / 15, 1500.0, n_grid=3)
    assert profile['lambda_min_sampled'] > 0
    assert profile['lambda_min'] < 0
    assert not profile['profile_closed_pass']
    expected = 1 - 0.34 * 16 / (3 * np.sqrt(3))
    assert np.isclose(profile['lambda_min'] / 1500, expected, atol=1e-12)


def test_screen_requires_qc_profile_and_all_totals_but_not_positive_gamma():
    row = dict(P_hat_h=1, wt2_hat_h=0.1, theta=2 / 3, D_veh=1000,
               L_mi=10, vf_mph=60, vq_hat_mph=10, calibration_eligible=True)
    row.update({f'{m}_{p}': 1.0 for m in ('O', 'R', 'M', 'A', 'S') for p in qvdfe.POLLUTANTS})
    row.update(Gamma_CO2=-1, congestion_CO2=-0.1)
    assert qvdfe.screen_episode(row)['matched_ladder_pass']
    assert not qvdfe.screen_episode({**row, 'calibration_eligible': 'False'})['matched_ladder_pass']
    assert not qvdfe.screen_episode({**row, 'M_CO2': float('nan')})['matched_ladder_pass']
    assert not qvdfe.screen_episode({**row, 'S_HC': 0})['matched_ladder_pass']
    arrival_failure = qvdfe.screen_episode({**row, 'wt2_hat_h': 0.25001})
    assert arrival_failure['physical_predicted_pass']
    assert not arrival_failure['profile_closed_pass']
    assert not arrival_failure['matched_ladder_pass']
    assert not qvdfe.screen_episode({})['matched_ladder_pass']
