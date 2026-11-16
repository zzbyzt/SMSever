"""Strict input checks and FULL-only orchestration around the exact frozen core.

The numerical functions in _frozen_core.py are an unmodified byte copy.
The loop below is the FULL arm of its forward() function; no panel arm is run.
"""

from . import _frozen_core as core
import numpy as np


def _nonnegative_matrix(value, name):
    a = np.asarray(value, dtype=float)
    if a.ndim != 2 or min(a.shape) < 1:
        raise ValueError(f"{name} must be a nonempty 2-D matrix")
    if not np.all(np.isfinite(a)) or np.any(a < 0):
        raise ValueError(f"{name} must contain finite nonnegative values")
    return a


def predict(F, reference_count_sums, Y, column_type, *, n_types=None):
    """Return full-axis RNA fractions without reading files or target truth.

    Parameters
    ----------
    F : array (genes, reference profiles)
        Each column is a donor-by-type normalized RNA profile, summing to 1.
    reference_count_sums : array with the same shape as F
        Raw summed counts per reference donor-by-type profile.
    Y : array (genes, bulk samples)
        Untransformed bulk counts on exactly the same ordered gene axis.
    column_type : integer array (reference profiles,)
        Zero-based, contiguous type IDs; at least one profile for every type.
    n_types : optional int
        Expected number of output types, normally supplied by the type labels.

    Notes
    -----
    The supplied columns must represent distinct donors within each type.
    Direct array use cannot verify that provenance; the NPZ loader checks it
    when donor_labels are present. Unsupported single-donor variance remains
    zero numerically and is explicitly reported, matching the frozen method.
    No RNA-to-cell conversion, thresholding, or UNKNOWN component is applied.
    """
    F = _nonnegative_matrix(F, "F")
    counts = _nonnegative_matrix(reference_count_sums, "reference_count_sums")
    Y = _nonnegative_matrix(Y, "Y")
    if F.shape != counts.shape:
        raise ValueError("F and reference_count_sums must have the same shape")
    if Y.shape[0] != F.shape[0]:
        raise ValueError("Y and F must have the same gene count and ordered axis")
    if not np.allclose(F.sum(0), 1, atol=1e-12):
        raise ValueError("F columns must already be normalized to sum to one")
    if np.any(counts.sum(0) <= 0) or np.any(Y.sum(0) <= 0):
        raise ValueError("Reference profiles and bulk samples need positive library sizes")
    c = np.asarray(column_type)
    if c.ndim != 1 or len(c) != F.shape[1] or not np.issubdtype(c.dtype, np.integer):
        raise ValueError("column_type must be an integer vector matching reference columns")
    if np.any(c < 0):
        raise ValueError("column_type must use zero-based nonnegative IDs")
    K = int(c.max()) + 1 if n_types is None else int(n_types)
    if K < 1 or not np.array_equal(np.unique(c), np.arange(K)):
        raise ValueError("Every output type must have reference support; missing IDs are invalid")
    # prepare() additionally creates an unused complement bucket. An empty panel
    # makes no change to the FULL matrix and avoids any gene-selection input.
    models, info = core.prepare(F, counts, np.empty(0, dtype=int))
    P = models["FULL_COUNT"]
    Q = Y / Y.sum(0)
    centres = np.column_stack([P[:, c == k].mean(1) for k in range(K)])
    variances = np.zeros_like(centres)
    support = np.bincount(c, minlength=K)
    for k in range(K):
        if support[k] >= 2:
            variances[:, k] = P[:, c == k].var(1, ddof=1) / support[k]

    predictions, coefficients, initial_coefficients = [], [], []
    precisions, diagnostics, initial_diagnostics = [], [], []
    for n, q in enumerate(Q.T):
        initial, d0 = core.solve(P, q)
        pi = np.bincount(c, weights=initial, minlength=K)
        mean = centres @ pi
        variance = variances @ (pi * pi)
        precision = mean / (mean + Y[:, n].sum() * variance)
        x, d = core.solve(P, q, precision)
        d["initial_certified"] = d0["numeric_certified"]
        d["initial_gap"] = d0["global_simplex_gap"]
        d["numeric_certified"] = d["numeric_certified"] and d0["numeric_certified"]
        d["precision_min"] = float(precision.min())
        d["precision_median"] = float(np.median(precision))
        d["precision_max"] = float(precision.max())
        d["variance_unsupported_types"] = np.flatnonzero(support < 2).tolist()
        predictions.append(np.bincount(c, weights=x, minlength=K))
        coefficients.append(x)
        initial_coefficients.append(initial)
        precisions.append(precision)
        diagnostics.append(d)
        initial_diagnostics.append(d0)
    return {
        "prediction": np.asarray(predictions),
        "coefficients": np.asarray(coefficients),
        "initial_coefficients": np.asarray(initial_coefficients),
        "precision": np.asarray(precisions),
        "reference_centres": centres,
        "reference_mean_variances": variances,
        "reference_support": support,
        "diagnostics": diagnostics,
        "initial_diagnostics": initial_diagnostics,
        "reference_background": {
            **{k: v for k, v in info.items() if k not in {"panel", "mask"}},
            "observed_reference_zero_RNA_mass": Q[np.all(F == 0, axis=1)].sum(0).tolist(),
            "variance_unsupported_types": np.flatnonzero(support < 2).tolist(),
        },
    }
