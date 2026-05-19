"""PyPDTSP — Python wrapper for the PDP-HGS and PDP-RR solvers
(`vidalt/PDTSP <https://github.com/vidalt/PDTSP>`_).
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version

from .parameters import HGSParameters, RRParameters
from .solver import (
    HGSSolver,
    PDTSPSolverError,
    RoutingSolution,
    RRSolver,
)

try:
    __version__ = _pkg_version("pdtsp")
except PackageNotFoundError:  # local checkout, not installed
    __version__ = "0+unknown"

__all__ = [
    "HGSParameters",
    "RRParameters",
    "HGSSolver",
    "RRSolver",
    "RoutingSolution",
    "PDTSPSolverError",
    "__version__",
]
