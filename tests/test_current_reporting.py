"""The reporting sample is explicit and cannot create supported partial windows."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'reproduce'))
from current_reporting import checked_periods, daytime_totals, pooled_metrics


def inputs():
    source = ROOT / 'data/frozen/calibration/average_weekday/period_results_v2.csv'
    scope = ROOT / 'data/reporting/v33/arizona_episode_profile_scope.csv'
    return pd.read_csv(source, low_memory=False), pd.read_csv(scope)


def test_current_reporting_matches_reviewed_v33_values():
    original, scope = inputs()
    periods = checked_periods(original, scope)
    day = daytime_totals(periods)
    assert len(scope) == 41
    assert len(day) == 388
    assert int(day.period_model_pass.sum()) == 225
    expected = pd.read_csv(ROOT / 'data/reporting/v33/period_emission_metrics.csv')
    pd.testing.assert_frame_equal(pooled_metrics(periods, day), expected,
                                  check_exact=False, rtol=1e-9, atol=1e-12)


def test_incomplete_or_duplicate_daytime_period_is_not_silently_supported():
    original, scope = inputs()
    periods = checked_periods(original, scope)
    am_index = periods[periods.period.eq('AM')].index[0]
    with pytest.raises(ValueError, match='all three periods'):
        daytime_totals(periods.drop(index=am_index))
    with pytest.raises(ValueError, match='duplicate'):
        daytime_totals(pd.concat([periods, periods.loc[[am_index]]]))


def test_unknown_profile_scope_fails_instead_of_silently_dropping_it():
    original, scope = inputs()
    scope.loc[0, 'sensor_uid'] = 'AZ_I10_W::not-a-detector'
    with pytest.raises(ValueError, match='absent'):
        checked_periods(original, scope)
