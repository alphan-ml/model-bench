"""Paired bootstrap over the 3,080-message test set, joined by id across
models. Task 2 of the decision pack (see README.md's "The Decision").

"Paired" means every resample draws the SAME set of message ids for every
model being compared -- so a pairwise difference's confidence interval
reflects genuine per-message disagreement between two models, not
independent sampling noise from two separate bootstraps. This is the
standard paired-bootstrap construction for comparing classifiers on a
shared test set.

No model or network call happens here: the inputs are plain
correct/incorrect (0/1) arrays already computed from outputs/*.jsonl (and,
if Task 1 succeeded, from the classifier baseline's own predictions).
"""

from __future__ import annotations

import numpy as np

N_RESAMPLES = 1000
SEED = 26
CI_LOW_PCT = 2.5
CI_HIGH_PCT = 97.5


def _ci(point: float, samples: np.ndarray) -> dict:
    return {
        "point": float(point),
        "ci_lo": float(np.percentile(samples, CI_LOW_PCT)),
        "ci_hi": float(np.percentile(samples, CI_HIGH_PCT)),
    }


def paired_bootstrap(
    correct_by_model: dict[str, list[bool]],
    n_resamples: int = N_RESAMPLES,
    seed: int = SEED,
) -> dict:
    """correct_by_model: {model_key: [bool, ...]} -- every list the SAME
    length N and aligned to the same row ordering (e.g. sorted by id), so
    index i means the same message in every model's list.

    Returns each model's fine-accuracy point estimate (the plain, observed
    accuracy -- not a bootstrap-resampled mean) with a 95% percentile
    bootstrap interval, and the same for every unordered pairwise
    difference (model_a - model_b), computed from the SAME resample
    indices across models so the comparison is paired.
    """
    model_keys = list(correct_by_model.keys())
    if not model_keys:
        raise ValueError("correct_by_model must not be empty")

    n = len(correct_by_model[model_keys[0]])
    for key, values in correct_by_model.items():
        if len(values) != n:
            raise ValueError(
                f"{key!r} has {len(values)} rows, expected {n} (paired join across models)"
            )
    if n == 0:
        raise ValueError("correct_by_model arrays must not be empty")

    arrays = {key: np.asarray(values, dtype=float) for key, values in correct_by_model.items()}
    point_acc = {key: float(arr.mean()) for key, arr in arrays.items()}

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_resamples, n))  # same resample indices for every model

    acc_samples = {key: arr[idx].mean(axis=1) for key, arr in arrays.items()}

    accuracy_fine_ci = {key: _ci(point_acc[key], acc_samples[key]) for key in model_keys}

    pairwise_diff_ci = {}
    for i, a in enumerate(model_keys):
        for b in model_keys[i + 1 :]:
            diff_point = point_acc[a] - point_acc[b]
            diff_samples = acc_samples[a] - acc_samples[b]
            pairwise_diff_ci[f"{a}_minus_{b}"] = _ci(diff_point, diff_samples)

    return {
        "n_resamples": n_resamples,
        "seed": seed,
        "n_messages": n,
        "accuracy_fine_ci": accuracy_fine_ci,
        "pairwise_diff_ci": pairwise_diff_ci,
    }
