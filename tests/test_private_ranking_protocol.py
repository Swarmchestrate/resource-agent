"""Tests for Trusted Key Generator private offer ranking."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest


pytest.importorskip("mife")
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "ipfe_resource_ranking"))

from private_protocol import (
    TrustedKeyGenerator,
    decrypt_combination_scores,
    encrypt_offer_values,
    import_public_key,
    validate_public_context,
)


def _offer(reliability, energy, bandwidth, price, latency=1):
    return {
        "reliability": reliability,
        "energy": energy,
        "bandwidth": bandwidth,
        "latency": latency,
        "price": price,
    }


def test_distributed_protocol_selects_best_offer_without_plaintext_at_hub():
    tkg = TrustedKeyGenerator()
    material = tkg.issue_job(
        "job-1",
        {"reliability": 1, "energy": 1, "bandwidth": 1, "price": 1},
    )
    public_context = material["public_context"]

    ciphertexts = {
        "offer-a": encrypt_offer_values(
            _offer(0.9, energy=10, bandwidth=100, price=5), public_context
        ),
        "offer-b": encrypt_offer_values(
            _offer(0.7, energy=20, bandwidth=200, price=3), public_context
        ),
    }
    # Everything crossing the RA-to-Hub boundary is JSON-safe ciphertext.
    json.dumps({"context": public_context, "offers": ciphertexts})
    assert "energy" not in ciphertexts["offer-a"]
    assert not import_public_key(public_context["public_key"]).has_private_key()

    batch = tkg.rank_combinations(
        "job-1", ciphertexts, [["offer-a"], ["offer-b"]]
    )
    scores = decrypt_combination_scores(
        public_context, material["functional_key"], batch
    )

    np.testing.assert_array_equal(scores, [60, 60])
    # Reliability + energy favor A; bandwidth + price favor B. Stable argmax
    # selects first candidate when weighted scores tie.
    assert int(np.argmax(scores)) == 0


def test_combination_scores_sum_resources_before_borda_ranking():
    tkg = TrustedKeyGenerator()
    material = tkg.issue_job(
        "job-combinations", {"energy": 2, "bandwidth": 1, "price": 1}
    )
    context = material["public_context"]
    offers = {
        "a1": encrypt_offer_values(_offer(0.9, 5, 100, 2), context),
        "a2": encrypt_offer_values(_offer(0.9, 5, 100, 2), context),
        "b1": encrypt_offer_values(_offer(0.8, 8, 200, 1), context),
        "b2": encrypt_offer_values(_offer(0.8, 8, 200, 1), context),
    }
    batch = tkg.rank_combinations(
        "job-combinations", offers, [["a1", "a2"], ["b1", "b2"]]
    )
    scores = decrypt_combination_scores(
        context, material["functional_key"], batch
    )

    # A gets rank 2 for energy with weight 20. B gets rank 2 for bandwidth
    # and price with weight 10 each, so final scores tie at 60.
    np.testing.assert_array_equal(scores, [60, 60])


def test_tampered_public_context_is_rejected_before_encryption():
    tkg = TrustedKeyGenerator()
    context = tkg.issue_job("job-2", {"energy": 1})["public_context"]
    tampered = dict(context)
    tampered["value_scale"] = context["value_scale"] + 1

    with pytest.raises(ValueError, match="context hash mismatch"):
        validate_public_context(tampered)


def test_wrong_job_batch_is_rejected_by_hub():
    tkg = TrustedKeyGenerator()
    material = tkg.issue_job("job-3", {"energy": 1})
    context = material["public_context"]
    encrypted = {"offer": encrypt_offer_values(_offer(1, 10, 1, 1), context)}
    batch = tkg.rank_combinations("job-3", encrypted, [["offer"]])
    batch["job_id"] = "different-job"

    with pytest.raises(ValueError, match="job_id mismatch"):
        decrypt_combination_scores(context, material["functional_key"], batch)


def test_tkg_overrides_self_reported_reliability():
    tkg = TrustedKeyGenerator()
    material = tkg.issue_job("job-trust", {"reliability": 1})
    context = material["public_context"]
    encrypted = {
        "liar": encrypt_offer_values(_offer(1.0, 1, 1, 1), context),
        "trusted": encrypt_offer_values(_offer(0.0, 1, 1, 1), context),
    }
    batch = tkg.rank_combinations(
        "job-trust",
        encrypted,
        [["liar"], ["trusted"]],
        trusted_values={
            "liar": {"reliability": 0.2},
            "trusted": {"reliability": 0.9},
        },
    )
    scores = decrypt_combination_scores(
        context, material["functional_key"], batch
    )

    np.testing.assert_array_equal(scores, [10, 20])
    assert int(np.argmax(scores)) == 1
