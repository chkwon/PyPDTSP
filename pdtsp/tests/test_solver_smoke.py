"""Integration tests — solve real instances with the bundled binaries.

Skipped cleanly when the binaries aren't present (e.g. on a freshly cloned
checkout where ``pip install -e .`` hasn't been run yet). The CI matrix
runs ``pip install -e .`` before pytest, so on CI these tests *must* run.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pdtsp import HGSParameters, HGSSolver, PDTSPSolverError, RRParameters, RRSolver


REPO_ROOT = Path(__file__).resolve().parents[2]
SMALL_PDT = REPO_ROOT / "instances" / "small.PDT"


def _binary_available(solver_cls) -> bool:
    """Probe-style check that the bundled native binary exists for ``solver_cls``."""
    try:
        solver_cls()._binary_path()
        return True
    except PDTSPSolverError:
        return False


hgs_required = pytest.mark.skipif(
    not _binary_available(HGSSolver),
    reason="pdphgs binary not built; run `pip install -e .` first.",
)
rr_required = pytest.mark.skipif(
    not _binary_available(RRSolver),
    reason="pdprr binary not built; run `pip install -e .` first.",
)


def _valid_tiny_problem() -> dict:
    return {
        "x_coordinates": [0.0, 1.0, 2.0, 1.0, 2.0],
        "y_coordinates": [0.0, 1.0, 0.0, 0.0, 1.0],
        "pickup_delivery_pairs": [(1, 3), (2, 4)],
    }


@hgs_required
def test_hgs_solves_small_pdt_instance() -> None:
    """Solve the bundled Dumitrescu prob5a instance with HGS."""
    if not SMALL_PDT.is_file():
        # When tests run against an installed wheel rather than from the
        # repo checkout, the instances/ directory may not be on disk. Skip
        # rather than fail in that case — the wheel doesn't ship instance
        # files (they're sdist-only).
        pytest.skip(f"test instance not present at {SMALL_PDT}")
    # The .PDT writer in the package accepts coordinate dicts. For solving
    # an existing on-disk instance, we drop down to the same subprocess
    # invocation the wrapper would emit.
    solver = HGSSolver(HGSParameters(time_limit=2, seed=1, it=5_000))
    # Build argv manually since the small instance is already a .PDT.
    import subprocess
    argv = [
        str(solver._binary_path()),
        f"--instance={SMALL_PDT}",
        *solver.parameters.to_argv(),
    ]
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    from pdtsp import _io
    parsed = _io.parse_stdout(proc.stdout)
    assert parsed["cost"] > 0
    # The best-known cost for prob5a is 3585 (from the bundled .sol). HGS
    # with a 2-second budget on this 10-customer instance should match it.
    assert parsed["cost"] == pytest.approx(3585, rel=0.05)
    assert parsed["solution"][0] == 0 and parsed["solution"][-1] == 0


@hgs_required
def test_hgs_solve_coordinate_dict() -> None:
    """End-to-end: dict → tempfile → subprocess → RoutingSolution."""
    result = HGSSolver(HGSParameters(time_limit=1, seed=1, it=1_000)).solve(
        _valid_tiny_problem()
    )
    assert result.cost > 0
    assert result.route[0] == 0 and result.route[-1] == 0
    visited = set(result.route)
    assert visited == {0, 1, 2, 3, 4}, (
        f"every node must appear in the tour exactly once (depot at the "
        f"endpoints); got route={result.route}"
    )


@rr_required
def test_rr_solve_coordinate_dict() -> None:
    result = RRSolver(RRParameters(time_limit=1, seed=1, it=5_000, fast=True)).solve(
        _valid_tiny_problem()
    )
    assert result.cost > 0
    assert result.route[0] == 0 and result.route[-1] == 0
    assert set(result.route) == {0, 1, 2, 3, 4}


@hgs_required
def test_hgs_determinism_with_fixed_seed() -> None:
    """Two solves with identical seed + budget must produce identical cost."""
    params = HGSParameters(time_limit=1, seed=12345, it=2_000)
    a = HGSSolver(params).solve(_valid_tiny_problem())
    b = HGSSolver(params).solve(_valid_tiny_problem())
    assert a.cost == b.cost
    assert a.route == b.route


@hgs_required
def test_hgs_solves_grubhub_distance_matrix() -> None:
    """Matrix-input path: setup.py patches an upstream nullptr-deref in the
    grubhub reader; this test makes sure that patch keeps working."""
    data = {
        "name": "demo",
        "distance_matrix": [
            [0, 10, 12, 15, 18],
            [10, 0,  5,  7, 11],
            [12, 5,  0,  6,  8],
            [15, 7,  6,  0,  4],
            [18, 11, 8,  4,  0],
        ],
    }
    result = HGSSolver(HGSParameters(time_limit=1, seed=1, it=1_000)).solve(data)
    assert result.cost > 0
    assert result.route[0] == 0 and result.route[-1] == 0
    assert set(result.route) == {0, 1, 2, 3, 4}


@hgs_required
def test_hgs_rejects_unpaired_customer_input() -> None:
    """Validation happens before subprocess spawn; bad input -> ValueError."""
    bad = {
        "x_coordinates": [0.0, 1.0, 2.0, 3.0, 4.0],
        "y_coordinates": [0.0, 1.0, 2.0, 3.0, 4.0],
        "pickup_delivery_pairs": [(1, 2)],  # 3 and 4 unpaired
    }
    with pytest.raises(ValueError, match="without a pickup/delivery pair"):
        HGSSolver(HGSParameters(time_limit=1)).solve(bad)
