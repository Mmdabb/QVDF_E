"""QVDFE core functions: bottleneck episodes, two-speed emissions, demand-dependent response, finite transitions.

One implementation of each formula of Abbasi and Zhou (2026), shared by the tutorials, the examples and the
paper-reproduction scripts. Units are stated in every docstring: speeds in mph, times in hours unless a name
ends in ``_s`` (seconds) or ``_min`` (minutes), flows in veh/h/lane, densities in veh/mi/lane, emission rates in
g/(veh h) and emissions in g. Accelerations are in m/s^2.
"""
from .paths import repo_root, data_dir, frozen_dir
from .states import fd_triangular, queue_speed
from .episode import closed_queue, NewellQueue, profile_shape, delay_profile, profile_min_arrival_ratio
from .emission import (cubic_rate, cubic_rate_second_derivative, gamma, gamma_cubic, link_emission,
                       episode_total, vmt_vht_form, finite_link_allowance, finite_link_ok, subset_total)
from .qvdf import qvdf, response
from .transitions import (kernel, kernel_prime, transition_time_s, speed_only_correction, transition_band,
                          cohort_shares)
from .data import load_rates, load_cubic_rates, load_lookup_rates, load_cards, load_episodes, load_reference_state, POLLUTANTS
from .screening import screen_episode
from . import report

PAPER = 'Abbasi, M., Zhou, X. (2026). From Bottleneck Episodes to Travel and Emission Costs: A Cross-Resolution Framework with Empirical Evaluation.'
__version__ = "1.0.1"

__all__ = ['repo_root', 'data_dir', 'frozen_dir', 'fd_triangular', 'queue_speed', 'closed_queue', 'NewellQueue',
           'profile_shape', 'delay_profile', 'profile_min_arrival_ratio', 'screen_episode',
           'cubic_rate', 'cubic_rate_second_derivative', 'gamma', 'gamma_cubic',
           'link_emission', 'episode_total', 'vmt_vht_form', 'finite_link_allowance', 'finite_link_ok', 'subset_total',
           'qvdf', 'response', 'kernel', 'kernel_prime', 'transition_time_s', 'speed_only_correction',
           'transition_band', 'cohort_shares', 'load_rates', 'load_cubic_rates', 'load_lookup_rates',
           'load_cards', 'load_episodes', 'load_reference_state',
           'POLLUTANTS', 'report', 'PAPER', '__version__']
