"""Abstract base class and result container for derived physics quantities.

Every quantity computed from raw CST data (frequency, Q, gradient, etc.)
is a ``PhysicsQuantity`` subclass.  This promotes single-responsibility
derivation and makes the physics independently testable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np

from ..core.results import ResultBundle


class PhysicsQuantity(ABC):
    """Abstract base for a derived physics observable.

    Subclasses implement ``compute()``, which takes a ``ResultBundle``
    and returns a float.  The bundle carries raw CST data (S-parameter
    arrays, scalar table values, etc.).

    Class Attributes
    ----------------
    name : str
        Short identifier (e.g. ``"f_res"``).
    unit : str
        SI unit in plain text (e.g. ``"Hz"``, ``"dimensionless"``).
    description : str
        Human-readable one-line description.
    """

    name: ClassVar[str] = ""
    unit: ClassVar[str] = ""
    description: ClassVar[str] = ""

    @abstractmethod
    def compute(self, bundle: ResultBundle) -> float:
        """Compute the quantity from raw CST result data.

        Parameters
        ----------
        bundle : ResultBundle
            Aggregated raw results from one CST simulation.

        Returns
        -------
        float
            The computed quantity, expressed in ``self.unit``.
        """
        ...

    @classmethod
    def derivation(cls) -> str:
        """Return the mathematical derivation as a LaTeX-style comment string."""
        return cls.__doc__ or "(no derivation recorded)"
