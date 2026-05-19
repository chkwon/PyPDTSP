"""Public solver classes — :class:`HGSSolver` and :class:`RRSolver`.

Both solvers share the same I/O surface: ``solve(data)`` accepts a dict
containing either coordinates or an explicit distance matrix, writes a
tempfile, spawns the bundled native binary as a subprocess, and parses the
JSON it prints to stdout into a :class:`RoutingSolution`.

There is no in-process library API in upstream PDTSP — both ``pdphgs`` and
``pdprr`` live inside ``main()`` and emit results to stdout. Subprocess
isolation also sidesteps upstream's module-level globals
(``Application::instance`` etc.), which would otherwise prevent multiple
solves in the same Python process.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Callable, ClassVar, List, Mapping, Tuple, Union

from . import _io
from .parameters import HGSParameters, RRParameters


__all__ = [
    "HGSSolver",
    "RRSolver",
    "RoutingSolution",
    "PDTSPSolverError",
]


# ---------------------------------------------------------------------------
# Exceptions and result type
# ---------------------------------------------------------------------------


class PDTSPSolverError(RuntimeError):
    """Raised when the bundled solver binary exits non-zero or emits output
    that can't be parsed as a solution."""


@dataclass
class RoutingSolution:
    """Result of a single solve.

    Attributes:
        cost: Total tour cost reported by the solver.
        time: Solver's self-reported wall-clock seconds. This is the
            algorithm's own clock, not the Python-side subprocess runtime.
        route: The closed tour, starting and ending at the depot (index 0).
            Customer indices are 1..N-1 in the input's own index space.
        raw: The full parsed JSON document, or — when ``json.loads`` could
            not handle upstream's interpolated ``LSCompleteLog`` block — the
            raw stdout substring. Useful for inspecting ``evolution`` and
            other secondary fields.
    """

    cost: float
    time: float
    route: List[int] = field(default_factory=list)
    raw: Any = None

    @property
    def n_customers(self) -> int:
        """Number of customer visits (excluding the depot's start/end stops)."""
        return max(len(self.route) - 2, 0)


# ---------------------------------------------------------------------------
# Solver base + concrete classes
# ---------------------------------------------------------------------------


_ParamsT = Union[HGSParameters, RRParameters, None]


class _BaseSolver:
    BINARY: ClassVar[str]
    PARAM_CLASS: ClassVar[type]

    def __init__(self, parameters: _ParamsT = None, *, verbose: bool = False):
        if parameters is None:
            parameters = self.PARAM_CLASS()
        if not isinstance(parameters, self.PARAM_CLASS):
            raise TypeError(
                f"{type(self).__name__} expects parameters of type "
                f"{self.PARAM_CLASS.__name__}, got {type(parameters).__name__}"
            )
        # Mirror the verbose flag onto the parameters object if the caller
        # didn't pass one explicitly. The parameters object owns the source
        # of truth so to_argv() emits the right flags.
        if verbose and not getattr(parameters, "verbose", False):
            parameters.verbose = True
        self.parameters = parameters
        self.verbose = bool(parameters.verbose)

    # ---- public API -------------------------------------------------------

    def solve(self, data: Mapping[str, Any]) -> RoutingSolution:
        binary = self._binary_path()
        argv_prefix, file_writer = self._prepare_invocation(data)

        with tempfile.TemporaryDirectory(prefix="pdtsp-") as td_str:
            td = Path(td_str)
            instance = td / ("instance.PDT" if "x_coordinates" in data else "instance.txt")
            file_writer(instance)
            argv = [
                str(binary),
                f"--instance={instance}",
                *argv_prefix,
                *self.parameters.to_argv(),
            ]
            if self.verbose:
                print("PyPDTSP:", " ".join(argv))

            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
            )
            if self.verbose:
                if proc.stderr:
                    print(proc.stderr, end="")

            if proc.returncode != 0:
                raise PDTSPSolverError(
                    f"{self.BINARY} exited with code {proc.returncode}.\n"
                    f"argv: {argv}\n"
                    f"--- stdout ---\n{proc.stdout}\n"
                    f"--- stderr ---\n{proc.stderr}"
                )

            try:
                parsed = _io.parse_stdout(proc.stdout)
            except ValueError as exc:
                raise PDTSPSolverError(
                    f"could not parse {self.BINARY} stdout: {exc}\n"
                    f"--- stderr ---\n{proc.stderr}"
                ) from exc

            return RoutingSolution(
                cost=parsed["cost"],
                time=parsed["time"],
                route=parsed["solution"],
                raw=parsed["raw"],
            )

    # ---- internals --------------------------------------------------------

    def _binary_path(self) -> Path:
        """Locate the bundled executable inside the installed package.

        Resolved via :mod:`importlib.resources` so the wrapper works from
        wheels, editable installs, and zip-imports alike.
        """
        # Suffix selection mirrors setup.py — Windows binaries carry .exe,
        # Unix binaries do not.
        candidates = (self.BINARY, f"{self.BINARY}.exe")
        for name in candidates:
            path = Path(str(resources.files(__package__) / name))
            if path.is_file():
                return path
        searched = ", ".join(
            str(Path(str(resources.files(__package__) / n))) for n in candidates
        )
        # Last-ditch: maybe the user has installed the upstream binary
        # globally and just wants the Python wrapper around it.
        for name in candidates:
            global_hit = shutil.which(name)
            if global_hit:
                return Path(global_hit)
        raise PDTSPSolverError(
            f"could not find the {self.BINARY!r} binary inside the package "
            f"or on PATH. Searched: {searched}. Either install a prebuilt "
            "wheel (`pip install pdtsp`) or build from source — "
            "the source install needs CMake + a C++ compiler + Boost on PATH."
        )

    def _prepare_invocation(
        self, data: Mapping[str, Any]
    ) -> Tuple[List[str], Callable[[Path], None]]:
        """Validate ``data`` and return the argv-extension + a closure that
        writes the on-disk instance into a given path."""

        is_coord = "x_coordinates" in data or "y_coordinates" in data
        is_matrix = "distance_matrix" in data
        if is_coord and is_matrix:
            raise ValueError(
                "pass either coordinates (x_coordinates + y_coordinates + "
                "pickup_delivery_pairs) or distance_matrix, not both"
            )
        if not is_coord and not is_matrix:
            raise ValueError(
                "data must contain either ('x_coordinates', 'y_coordinates', "
                "'pickup_delivery_pairs') or ('distance_matrix',)"
            )

        if is_coord:
            for key in ("x_coordinates", "y_coordinates", "pickup_delivery_pairs"):
                if key not in data:
                    raise ValueError(
                        f"coordinate input is missing required key: {key!r}"
                    )
            x = list(data["x_coordinates"])
            y = list(data["y_coordinates"])
            pairs = [tuple(p) for p in data["pickup_delivery_pairs"]]

            def _writer(path: Path) -> None:
                _io.write_pdt(path, x=x, y=y, pairs=pairs)

            return [], _writer

        # matrix mode
        matrix = data["distance_matrix"]
        name = str(data.get("name", "pdtsp_grubhub"))

        def _writer(path: Path) -> None:
            _io.write_grubhub(path, name=name, distance_matrix=matrix)

        return ["--grubhub"], _writer


class HGSSolver(_BaseSolver):
    """Hybrid Genetic Search solver (PDP-HGS).

    The headline algorithm from Pacheco, Martinelli, Subramanian, Toffolo &
    Vidal (2022) — six PDTSP-adapted neighborhoods orchestrated by an HGS
    framework. Use :class:`HGSParameters` to tune the search.

    Example::

        from pdtsp import HGSSolver, HGSParameters
        solver = HGSSolver(HGSParameters(time_limit=10, seed=42))
        result = solver.solve({
            "x_coordinates": [...],
            "y_coordinates": [...],
            "pickup_delivery_pairs": [(1, 4), (2, 5), (3, 6)],
        })
        print(result.cost, result.route)
    """

    BINARY = "pdphgs"
    PARAM_CLASS = HGSParameters


class RRSolver(_BaseSolver):
    """Ruin & Recreate solver (PDP-RR).

    The Veenstra et al. (2017) baseline shipped alongside PDP-HGS with an
    optional O(n²) fast reinsertion operator. Use :class:`RRParameters` to
    tune.
    """

    BINARY = "pdprr"
    PARAM_CLASS = RRParameters
