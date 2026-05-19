# Test instances

This directory holds a single small instance used by `pdtsp/tests/test_solver_smoke.py`.

* `small.PDT` — verbatim copy of `Dumitrescu/prob5a.txt` from upstream
  [`vidalt/PDTSP`](https://github.com/vidalt/PDTSP) at commit `451bc8a5`. 5
  pickup-delivery pairs over Euclidean coordinates. Best-known cost: 3585
  (from the bundled `prob5a.sol`).

Upstream's `instances/` directory contains a much larger collection
(`RBO00/`, `Dumitrescu/`, `PDP-X/`, `Grubhub/`) used in the original
publication. Those instances are not redistributed here to keep the wheel
small; clone the upstream repo if you need them.
