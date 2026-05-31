"""Visualisation helpers for optimisation results.

Provides convergence plots, Pareto front visualisation, and sensitivity
bar charts.  All functions are independent of the optimisation framework
— they accept plain numpy arrays.
"""

from __future__ import annotations

import numpy as np

# All functions require matplotlib at call time (lazy import)
# to keep the dependency optional for headless usage.


def plot_convergence(
    history_f: list[np.ndarray],
    title: str = "Optimisation Convergence",
    xlabel: str = "Evaluation",
    ylabel: str = "Objective Value",
    ax=None,
):
    """Plot the best-so-far convergence curve.

    Parameters
    ----------
    history_f : list[np.ndarray]
        Objective values in evaluation order.  For single-objective each
        entry should be ``[f_val]``; for multi-objective the first column
        is used.
    title, xlabel, ylabel : str
        Plot labels.
    ax : matplotlib Axes or None
        If ``None``, creates a new figure.

    Returns
    -------
    matplotlib.figure.Figure
    """
    import matplotlib.pyplot as plt

    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4))
    else:
        fig = ax.figure

    f_vals = np.array([f[0] if len(f) > 0 else np.nan for f in history_f])
    best_so_far = np.minimum.accumulate(f_vals)

    ax.plot(best_so_far, "b-", linewidth=1.5)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    return fig


def plot_pareto_front(
    pareto_f: np.ndarray,
    obj_labels: tuple[str, str] | None = None,
    title: str = "Pareto Front",
    ax=None,
):
    """Plot a 2-D Pareto front.

    Parameters
    ----------
    pareto_f : np.ndarray
        ``(N, 2)`` array of Pareto-optimal objective values.
    obj_labels : tuple[str, str] or None
        Axis labels for the two objectives.
    title : str
        Plot title.
    ax : matplotlib Axes or None

    Returns
    -------
    matplotlib.figure.Figure
    """
    import matplotlib.pyplot as plt

    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 5))
    else:
        fig = ax.figure

    ax.scatter(pareto_f[:, 0], pareto_f[:, 1], c="darkblue", s=30, zorder=3)
    ax.plot(pareto_f[:, 0], pareto_f[:, 1], "b-", alpha=0.3, linewidth=1)

    if obj_labels:
        ax.set_xlabel(obj_labels[0])
        ax.set_ylabel(obj_labels[1])
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    return fig


def plot_sensitivity_bars(
    sobol_result,
    title: str = "Sobol' Sensitivity Indices",
    ax=None,
):
    """Bar chart of first-order and total-effect Sobol' indices.

    Parameters
    ----------
    sobol_result : SobolResult
    title : str
    ax : matplotlib Axes or None

    Returns
    -------
    matplotlib.figure.Figure
    """
    import matplotlib.pyplot as plt

    names = sobol_result.parameter_names
    s1 = [sobol_result.first_order[n] for n in names]
    st = [sobol_result.total_effect[n] for n in names]

    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 5))
    else:
        fig = ax.figure

    x = np.arange(len(names))
    width = 0.35

    ax.bar(x - width / 2, s1, width, label="First-order (S1)", color="steelblue")
    ax.bar(x + width / 2, st, width, label="Total effect (ST)", color="coral")

    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("Sensitivity Index")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

    return fig
