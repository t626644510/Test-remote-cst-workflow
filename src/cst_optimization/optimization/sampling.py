"""Design-space sampling strategies (LHS and Sobol sequences)."""

from __future__ import annotations

import numpy as np
from scipy.stats import qmc


def latin_hypercube_sampling(
    bounds: np.ndarray,
    n_samples: int,
    seed: int | None = None,
) -> np.ndarray:
    """Generate Latin Hypercube Samples within the given bounds.

    Parameters
    ----------
    bounds : np.ndarray
        ``(N, 2)`` array of ``[low, high]`` for each dimension.
    n_samples : int
        Number of samples to draw.
    seed : int or None
        Random seed for reproducibility.

    Returns
    -------
    np.ndarray
        Shape ``(n_samples, N)`` array of samples.
    """
    n_dims = bounds.shape[0]
    sampler = qmc.LatinHypercube(d=n_dims, seed=seed)
    unit = sampler.random(n=n_samples)  # in [0, 1]^d
    return _scale_to_bounds(unit, bounds)


def sobol_sampling(
    bounds: np.ndarray,
    n_samples: int,
    scramble: bool = True,
    seed: int | None = None,
) -> np.ndarray:
    """Generate Sobol' sequence samples within the given bounds.

    Parameters
    ----------
    bounds : np.ndarray
        ``(N, 2)`` array for each dimension.
    n_samples : int
        Number of samples.  Rounded up to the next power of 2 if needed.
    scramble : bool
        If ``True``, use Owen-type scrambling for better uniformity.
    seed : int or None
        Random seed.

    Returns
    -------
    np.ndarray
        Shape ``(n_samples, N)``.
    """
    n_dims = bounds.shape[0]
    # Round up to next power of two for Sobol
    n_sobol = 1
    while n_sobol < n_samples:
        n_sobol <<= 1

    sampler = qmc.Sobol(d=n_dims, scramble=scramble, seed=seed)
    unit = sampler.random(n=n_sobol)[:n_samples]  # truncate
    return _scale_to_bounds(unit, bounds)


def random_sampling(
    bounds: np.ndarray,
    n_samples: int,
    seed: int | None = None,
) -> np.ndarray:
    """Generate uniform random samples within the given bounds.

    Parameters
    ----------
    bounds : np.ndarray
        ``(N, 2)`` array.
    n_samples : int
        Number of samples.
    seed : int or None
        Random seed.

    Returns
    -------
    np.ndarray
        Shape ``(n_samples, N)``.
    """
    rng = np.random.RandomState(seed)
    n_dims = bounds.shape[0]
    unit = rng.uniform(size=(n_samples, n_dims))
    return _scale_to_bounds(unit, bounds)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def unit_cube_lhs(n_samples: int, n_dims: int, seed: int | None = None) -> np.ndarray:
    """Generate LHS samples directly in the ``[0, 1]^D`` unit cube.

    Unlike ``latin_hypercube_sampling``, this does **not** apply physical
    bounds — scaling is handled separately by ``ParameterSet.normalize()``
    / ``denormalize()`` during the optimisation loop.

    Parameters
    ----------
    n_samples : int
    n_dims : int
    seed : int or None

    Returns
    -------
    np.ndarray
        Shape ``(n_samples, n_dims)``, each element in [0, 1].
    """
    sampler = qmc.LatinHypercube(d=n_dims, seed=seed)
    return sampler.random(n=n_samples)


def constrained_unit_cube_lhs(
    n_samples: int,
    n_dims: int,
    parameter_set: Any,
    seed: int | None = None,
    max_attempts_per_point: int = 500,
) -> np.ndarray:
    """Generate LHS samples in [0, 1]^D that satisfy all geometric constraints.

    For each sample, a random point is drawn in the unit cube, denormalised
    to physical space, and checked against the constraints attached to
    *parameter_set*.  If infeasible the point is retried up to
    *max_attempts_per_point* times.

    Parameters
    ----------
    n_samples : int
        Number of feasible samples required.
    n_dims : int
        Dimensionality.
    parameter_set : ParameterSet
        Must have ``.constraints`` and ``.denormalize()`` attached.
    seed : int or None
    max_attempts_per_point : int
        Retries per sample point before raising.

    Returns
    -------
    np.ndarray
        Shape ``(n_samples, n_dims)`` in [0, 1].

    Raises
    ------
    RuntimeError
        If a feasible point cannot be found within the retry budget.
    """
    rng = np.random.RandomState(seed)
    X_norm = np.empty((n_samples, n_dims))

    for i in range(n_samples):
        found = False
        for _ in range(max_attempts_per_point):
            candidate = rng.uniform(0.0, 1.0, size=n_dims)
            x_phys = parameter_set.denormalize(candidate)
            if parameter_set.is_feasible(x_phys):
                X_norm[i] = candidate
                found = True
                break

        if not found:
            raise RuntimeError(
                f"Could not find a feasible sample for point {i} "
                f"after {max_attempts_per_point} attempts.  "
                f"Check constraint feasibility of the parameter bounds."
            )

    # Apply LHS post-hoc: sort each column independently to approximate
    # Latin Hypercube stratification while preserving feasibility.
    for j in range(n_dims):
        col = X_norm[:, j].copy()
        sampler = qmc.LatinHypercube(d=1, seed=seed)
        ideal = sampler.random(n=n_samples).ravel()
        order = np.argsort(col)
        X_norm[order, j] = np.sort(ideal)

    # LHS sorting can break feasibility — re-verify and patch.
    for i in range(n_samples):
        x_phys = parameter_set.denormalize(X_norm[i])
        if not parameter_set.is_feasible(x_phys):
            # Re-sample this point
            for _ in range(max_attempts_per_point):
                candidate = rng.uniform(0.0, 1.0, size=n_dims)
                x_phys = parameter_set.denormalize(candidate)
                if parameter_set.is_feasible(x_phys):
                    X_norm[i] = candidate
                    break
            else:
                raise RuntimeError(
                    f"LHS re-sort broke feasibility for point {i} "
                    f"and re-sampling failed after {max_attempts_per_point} attempts."
                )

    return X_norm


def _scale_to_bounds(unit: np.ndarray, bounds: np.ndarray) -> np.ndarray:
    """Map unit-cube points ``[0, 1]^d`` to physical bounds."""
    lo = bounds[:, 0]
    hi = bounds[:, 1]
    return lo + unit * (hi - lo)
