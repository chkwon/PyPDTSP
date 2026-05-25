# PyPDTSP

[![CI](https://github.com/chkwon/PyPDTSP/actions/workflows/ci.yml/badge.svg)](https://github.com/chkwon/PyPDTSP/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pdtsp.svg)](https://pypi.org/project/pdtsp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

Python wrapper for the **Pickup-and-Delivery Traveling Salesman Problem (PDTSP)**
solvers from [`vidalt/PDTSP`](https://github.com/vidalt/PDTSP) — the
hybrid genetic search (`pdphgs`) and ruin-and-recreate (`pdprr`)
implementations accompanying Pacheco, Martinelli, Subramanian, Toffolo &
Vidal, *"Exponential-size neighborhoods for the pickup-and-delivery
traveling salesman problem"* (Transportation Science, 2022).

> **Status:** alpha. The Python surface may change between minor releases.

## Install

Prebuilt wheels for **Linux (x86_64) and macOS (x86_64 + arm64)**:

```bash
pip install pdtsp
```

**Windows is not yet supported by prebuilt wheels** — Windows users (and
anyone on a platform without a wheel) install from source. That needs
CMake, a C++17 compiler, and Boost (`program_options`, `filesystem`,
`system`, `regex`):

```bash
# Debian/Ubuntu
sudo apt install cmake g++ libboost-program-options-dev libboost-filesystem-dev libboost-system-dev libboost-regex-dev
# macOS
brew install cmake boost
# Windows (MSVC + vcpkg)
vcpkg install boost-program-options boost-filesystem boost-system boost-regex --triplet x64-windows-static-md
# then in a Developer PowerShell:
$env:CMAKE_TOOLCHAIN_FILE = "C:/vcpkg/scripts/buildsystems/vcpkg.cmake"

pip install pdtsp             # downloads sdist and builds from source
```

## Quick start

```python
from pdtsp import HGSSolver, HGSParameters

# Index 0 is the depot. Customers 1..4 form two pickup-delivery pairs:
#   pickup 1 -> delivery 3
#   pickup 2 -> delivery 4
data = {
    "x_coordinates": [0.0, 1.0, 2.0, 1.0, 2.0],
    "y_coordinates": [0.0, 1.0, 0.0, 0.0, 1.0],
    "pickup_delivery_pairs": [(1, 3), (2, 4)],
}

result = HGSSolver(HGSParameters(time_limit=10, seed=42)).solve(data)
print(result.cost)    # 5.0
print(result.route)   # [0, 1, 2, 4, 3, 0]
```

The Ruin & Recreate variant is a drop-in replacement:

```python
from pdtsp import RRSolver, RRParameters

solver = RRSolver(RRParameters(time_limit=10, seed=42, it=10_000, fast=True))
result = solver.solve(data)

print(result.cost)
print(result.time)
print(result.route)
```

## Explicit distance matrix (Grubhub format)

When you have arbitrary integer distances (not Euclidean coordinates), use
the matrix mode. Pickup/delivery pairs are implicit: odd indices are
pickups, the following even index is the paired delivery.

```python
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
result = HGSSolver(HGSParameters(time_limit=5)).solve(data)
```

## Input shape reference

### Coordinate mode

| Key                      | Type            | Notes                                                  |
|--------------------------|-----------------|--------------------------------------------------------|
| `x_coordinates`          | `Sequence[float]` | Length `N`. Depot is index 0.                        |
| `y_coordinates`          | `Sequence[float]` | Same length and convention.                          |
| `pickup_delivery_pairs`  | `Sequence[tuple[int, int]]` | Each `(pickup, delivery)` uses indices in `1..N-1`. Every customer must be in exactly one pair. |

### Matrix mode (Grubhub)

| Key                | Type                          | Notes                                       |
|--------------------|-------------------------------|---------------------------------------------|
| `distance_matrix`  | `Sequence[Sequence[float]]`   | `N` × `N` integer (or rounded) distances. `N - 1` must be even. |
| `name` (optional)  | `str`                         | Free-form instance label. Default `pdtsp_grubhub`. |

## Parameter reference

`HGSParameters` mirrors `pdphgs --help` (defaults from upstream commit
`451bc8a5`):

| Field            | Default                                | Upstream flag         |
|------------------|----------------------------------------|-----------------------|
| `time_limit`     | `None` (no limit)                      | `--time-limit`        |
| `it`             | `1_000_000`                            | `--it`                |
| `mu`             | `25`                                   | `--mu`                |
| `lam`            | `40`                                   | `--lambda`            |
| `div`            | `4000`                                 | `--div`               |
| `nb_elite`       | `1`                                    | `--nb-elite`          |
| `nb_close`       | `2`                                    | `--nb-close`          |
| `neighborhoods`  | `"RELOCATE-2OPT-2KOPT-OROPT-4OPT-BS"`  | `--neighborhoods`     |
| `bs_k`           | `3`                                    | `--bs-k`              |
| `or_k`           | `30`                                   | `--or-k`              |
| `ratio_slow_nb`  | `1.0`                                  | `--ratio-slow-nb`     |
| `seed`           | `0`                                    | `--seed`              |
| `verbose`        | `False`                                | `--verbose`           |

`RRParameters` mirrors `pdprr --help`:

| Field         | Default                  | Upstream flag    |
|---------------|--------------------------|------------------|
| `fast`        | `False`                  | `--fast`         |
| `time_limit`  | `None` (no limit)        | `--time-limit`   |
| `it`          | `50_000`                 | `--it`           |
| `p_accept`    | `3.0`                    | `--p-accept`     |
| `c_rate`      | `0.99987571600000003`    | `--c-rate`       |
| `seed`        | `0`                      | `--seed`         |
| `verbose`     | `False`                  | `--verbose`      |

## Result shape

`solver.solve(data)` returns a `RoutingSolution`:

| Field   | Type        | Notes                                                       |
|---------|-------------|-------------------------------------------------------------|
| `cost`  | `float`     | Best tour cost the solver reported.                         |
| `time`  | `float`     | Solver's own wall-clock (not subprocess wall time).         |
| `route` | `list[int]` | Closed tour, starts and ends at depot index 0.              |
| `raw`   | `dict\|str` | Full parsed JSON (or raw stdout block if JSON parse failed). |

## How it works

`HGSSolver` and `RRSolver` bundle the upstream native binaries (`pdphgs`
and `pdprr`) inside the package. Each `solve()` call:

1. Validates the input dict.
2. Writes a temporary `.PDT` file (coordinate mode) or matrix file
   (Grubhub mode).
3. Spawns the bundled binary via `subprocess.run`.
4. Parses the JSON document the binary prints to stdout.

Subprocess isolation sidesteps upstream's module-level globals — multiple
`solve()` calls in the same Python process are safe.

## Citing

```bibtex
@article{pacheco2022pdtsp,
  title   = {Exponential-Size Neighborhoods for the Pickup-and-Delivery
             Traveling Salesman Problem},
  author  = {Pacheco, Toni and Martinelli, Rafael and Subramanian, Anand
             and Toffolo, T{\'u}lio A. M. and Vidal, Thibaut},
  journal = {Transportation Science},
  year    = {2022},
  doi     = {10.1287/trsc.2022.1170}
}
```

## License

PyPDTSP is released under the [MIT License](LICENSE). The bundled binaries
are compiled from the MIT-licensed [`vidalt/PDTSP`](https://github.com/vidalt/PDTSP)
codebase (Copyright © 2022 Toni Pacheco) — see `LICENSE` for the upstream
attribution.
