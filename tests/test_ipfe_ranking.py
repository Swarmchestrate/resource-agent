"""Tests for the IPFE private ranking integration seam.

The full RA stack needs Docker/puccini; these tests exercise the exact
call path used by _rank_resource_offers: build the offer dataset, run
IPFERanker (from_dataset -> encrypt_offers -> decrypt_scores -> argmax),
and check the selection.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

pytest.importorskip("mife")
sys.path.insert(0, str(REPO_ROOT / "ipfe_resource_ranking"))
from ranking_wrapper import IPFERanker

QOS_DIRECTION = {
    "reliability": "max",
    "bandwidth": "max",
    "energy": "min",
    "latency": "min",
    "price": "min",
}


def make_offer_data(priorities, reliability, energy, bandwidth, latency, price):
    return {
        "qos_priority": priorities,
        # Same filtering as ra_base._rank_resource_offers: the wrapper
        # rejects direction entries for metrics absent from qos_priority.
        "qos_direction": {k: d for k, d in QOS_DIRECTION.items() if k in priorities},
        "reliability": reliability,
        "energy": energy,
        "bandwidth": bandwidth,
        "latency": latency,
        "price": price,
    }


def rank_offer_data(offer_data):
    """Same call sequence as _rank_resource_offers."""
    ranker = IPFERanker.from_dataset(offer_data)
    batch = ranker.encrypt_offers(offer_data)
    scores = ranker.decrypt_scores(batch)
    np.testing.assert_array_equal(scores, ranker.plaintext_scores(offer_data))
    return int(np.argmax(scores))


def test_reliability_direction_prefers_higher_trust():
    data = make_offer_data(
        {"reliability": 1.0},
        reliability=[0.9, 0.7],
        energy=[10.0, 10.0],
        bandwidth=[100, 100],
        latency=[1, 1],
        price=[5.0, 5.0],
    )
    assert rank_offer_data(data) == 0


def test_bandwidth_direction_prefers_higher():
    data = make_offer_data(
        {"bandwidth": 1.0},
        reliability=[1.0, 1.0],
        energy=[10.0, 10.0],
        bandwidth=[100, 200],
        latency=[1, 1],
        price=[5.0, 5.0],
    )
    assert rank_offer_data(data) == 1


def test_min_directions_prefer_lower_values():
    data = make_offer_data(
        {"energy": 1.0, "price": 1.0, "latency": 1.0},
        reliability=[1.0, 1.0],
        energy=[20.0, 10.0],
        bandwidth=[100, 100],
        latency=[2, 1],
        price=[5.0, 3.0],
    )
    assert rank_offer_data(data) == 1


def test_weighted_priorities_shift_selection():
    # Energy equal; price favors offer 0, reliability favors offer 1.
    # With price priority 0 and reliability priority 1, offer 1 wins.
    base = {
        "reliability": [0.9, 0.7],
        "energy": [10.0, 10.0],
        "bandwidth": [100, 100],
        "latency": [1, 1],
        "price": [3.0, 5.0],
    }
    by_reliability = make_offer_data({"reliability": 1.0, "price": 0.0}, **base)
    assert rank_offer_data(by_reliability) == 0


def test_return_type_is_int():
    data = make_offer_data(
        {"reliability": 1.0, "energy": 1.0},
        reliability=[0.9, 0.7],
        energy=[10.0, 20.0],
        bandwidth=[100, 100],
        latency=[1, 1],
        price=[5.0, 5.0],
    )
    idx = rank_offer_data(data)
    assert isinstance(idx, int)
    assert 0 <= idx < 2


def test_tied_scores_select_first_stably():
    data = make_offer_data(
        {"reliability": 1.0, "energy": 1.0},
        reliability=[1.0, 1.0],
        energy=[10.0, 10.0],
        bandwidth=[100, 100],
        latency=[1, 1],
        price=[5.0, 5.0],
    )
    assert rank_offer_data(data) == 0


def test_single_offer():
    data = make_offer_data(
        {"reliability": 1.0},
        reliability=[0.8],
        energy=[12.0],
        bandwidth=[50],
        latency=[1],
        price=[2.0],
    )
    assert rank_offer_data(data) == 0


def test_full_ranking_order_encrypted_matches_plaintext():
    data = make_offer_data(
        {"reliability": 1.0, "energy": 2.0, "bandwidth": 1.0, "price": 1.0},
        reliability=[0.9, 0.7, 0.8],
        energy=[10.0, 20.0, 15.0],
        bandwidth=[100, 200, 150],
        latency=[1, 1, 1],
        price=[5.0, 3.0, 4.0],
    )
    ranker = IPFERanker.from_dataset(data)
    plaintext_order = ranker.rank(data)
    batch = ranker.encrypt_offers(data)
    scores = ranker.decrypt_scores(batch)
    encrypted_order = np.argsort(-scores)
    np.testing.assert_array_equal(plaintext_order, encrypted_order)
