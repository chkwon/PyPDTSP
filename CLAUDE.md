# CLAUDE.md — developer notes for PyPDTSP

This file is read by Claude Code when it's working in this repo. It exists
to capture the non-obvious bits that aren't derivable from reading the code.

## What this package is

A thin Python wrapper around two C++ binaries (`pdphgs`, `pdprr`) from
[`vidalt/PDTSP`](https://github.com/vidalt/PDTSP). There is no in-process
library API upstream — both solvers live inside `main()` and emit results
to stdout — so the wrapper shells out via subprocess and parses the JSON
output.

## Repository layout

```
pdtsp/                 the Python package
  parameters.py          HGSParameters, RRParameters dataclasses
  _io.py                 .PDT writer, --grubhub writer, JSON stdout parser
  solver.py              HGSSolver, RRSolver, RoutingSolution
  tests/                 pytest tests
setup.py                 downloads pinned upstream, patches CMakeLists, builds
pyproject.toml           project metadata + cibuildwheel config
instances/small.PDT      Dumitrescu prob5a, used by smoke tests
examples/                user-facing example scripts
.github/workflows/       ci.yml (test matrix), release.yml (cibuildwheel + PyPI)
```

## Bumping the upstream pin

1. Update `UPSTREAM_SHA` in `setup.py` to the new commit hash.
2. Compute the new tarball SHA-256:
   ```bash
   curl -fsSL "https://github.com/vidalt/PDTSP/archive/<SHA>.tar.gz" | shasum -a 256
   ```
3. Update `UPSTREAM_TARBALL_SHA256` in `setup.py`.
4. Re-read `PDP-HGS/main.cpp` and `PDP-RR/solver.cpp` to verify the JSON
   stdout format hasn't drifted (look at the `else` branch that runs when
   `--verbose` is off). Adjust `pdtsp/_io.py::parse_stdout` if needed.
5. If CLI flags changed, update the two dataclasses in
   `pdtsp/parameters.py` and the README's parameter tables.
6. Run the full local smoke test:
   `pip install -e . --config-settings editable_mode=compat && pytest pdtsp/tests -v`.

## Editable installs need `editable_mode=compat`

PEP 660 editable installs (`pip install -e .`) default to setuptools'
"lenient" strategy, which creates a `.pth` shim pointing at the source
directory and **skips invoking `build_py`/`develop`** on some
Python + OS combinations (observed on macOS and Windows with Python 3.10).
That means our custom `BuildPyCommand` doesn't run and the binaries never
get built.

Always pass `--config-settings editable_mode=compat` for development
installs. This forces the legacy `setup.py develop` path, which invokes
our `DevelopCommand` and produces `pdtsp/pdphgs` + `pdtsp/pdprr`.

CI uses the same flag (`.github/workflows/ci.yml`). Non-editable installs
(`pip install .` or wheel builds via cibuildwheel) always invoke
`build_py`, so this caveat doesn't apply there.

## The CMakeLists patch

Upstream's `CMakeLists.txt` adds `-march=native` to `CMAKE_CXX_FLAGS`. We
strip this in `setup.py::_patch_cmakelists` so binaries built in CI run
on every CPU we ship wheels for. If upstream ever changes the flag wording
or moves it to a different file, the patch will silently no-op (a warning
is printed); fix the `str.replace` to match the new wording.

## Why subprocess instead of pybind11 / ctypes

* Upstream has no `solve()` library entry — refactoring `main.cpp` into
  one would mean maintaining a non-trivial patch series against a frozen
  upstream (last commit August 2022).
* Subprocess isolation works around upstream's module-level globals
  (`Application::instance` etc.). Multiple solves in the same Python
  process are inherently safe.
* Subprocess overhead is tens of ms per call — irrelevant for solves
  measured in seconds.

If a user shows up needing sub-millisecond solve overhead, a future v0.2
can refactor to a library API + pybind11. The Python surface (parameter
dataclasses, `solve(data)` signature, `RoutingSolution`) is designed so
that's a backend swap, not an API break.

## JSON parsing fragility

The HGS binary interpolates `LSCompleteLog()` content directly into the
JSON document it prints. We don't fully control whether that text is
well-formed JSON across every parameter combination. `_io.parse_stdout`
therefore:

1. Tries `json.loads` on the whole block first.
2. Falls back to regex extraction of `"cost"`, `"time"`, `"solution"`
   when that fails.

The fallback is exercised by `test_parse_stdout_falls_back_when_json_invalid`
in `pdtsp/tests/test_io.py`. If a real solver run hits the fallback
path on CI, capture the offending stdout and add it as a new fixture.

## Cutting a release

1. Bump `version` in `pyproject.toml`.
2. Commit on `main`, push, wait for CI to go green.
3. Tag and push the tag:
   ```bash
   git tag v0.X.Y && git push origin v0.X.Y
   ```
4. `release.yml` builds wheels via cibuildwheel on three OSes plus an
   sdist, then publishes to PyPI via OIDC trusted publishing, signs with
   Sigstore, and cuts a GitHub Release. No API tokens or secrets are
   required — TestPyPI/PyPI trusted publishing must be configured for the
   `pdtsp` project under your PyPI account.

For a dry run before tagging, trigger `release.yml` manually via the
GitHub Actions "Run workflow" button; it'll publish to TestPyPI instead.
