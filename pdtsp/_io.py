"""Instance serialization and stdout-JSON parsing helpers.

These are pure-Python, side-effect-free utilities the solver layer composes.
Keeping them separate from :mod:`pdtsp.solver` means the unit-test tier
can exercise them without needing the compiled binaries.

Format references — both confirmed against upstream commit ``451bc8a5``:

* ``.PDT`` (default) — ``PDP-HGS/pdp/instancereader.cpp::InstanceReader::fromFile``
* ``--grubhub`` matrix — ``PDP-HGS/pdp/instancereader.cpp::InstanceReaderGrubhub::fromFile``
* JSON stdout (HGS) — ``PDP-HGS/main.cpp`` (the ``else`` branch around line 102)
* JSON stdout (RR)  — ``PDP-RR/solver.cpp::Solver::PrintStats``
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


# ---------------------------------------------------------------------------
# Instance writers
# ---------------------------------------------------------------------------


def write_pdt(
    path: Path,
    *,
    x: Sequence[float],
    y: Sequence[float],
    pairs: Sequence[Tuple[int, int]],
) -> None:
    """Write a coordinate-format ``.PDT`` instance file.

    The on-disk layout (per ``InstanceReader::fromFile``) is::

        N
        <_> <x[0]> <y[0]>                       # depot; first column ignored
        <i> <x[i]> <y[i]> <flag> <pair_1idx>    # one line per customer
        ...
        -999

    where ``flag=0`` indicates a pickup and ``flag=1`` indicates a delivery.
    ``pair_1idx`` is the 1-indexed file-position of the mate node (depot
    occupies position 1, customer ``k`` occupies position ``k+1``).

    Args:
        path: Destination file path.
        x: x-coordinates, length ``N`` where ``N-1`` is the number of
            customers. ``x[0]`` is the depot.
        y: y-coordinates, same length and convention as ``x``.
        pairs: List of ``(pickup_idx, delivery_idx)`` tuples in 1..N-1 space
            (depot is index 0 and never appears in a pair). Each customer
            index must appear exactly once across all pairs.
    """
    x = list(x)
    y = list(y)
    if len(x) != len(y):
        raise ValueError(
            f"x and y must have the same length; got {len(x)} vs {len(y)}"
        )
    n = len(x)
    if n < 3:
        raise ValueError(
            f"PDTSP needs at least 1 pickup + 1 delivery + a depot (n>=3); "
            f"got n={n}"
        )

    flag = [None] * n     # None for depot, 0 for pickup, 1 for delivery
    mate = [None] * n
    flag[0] = None
    seen: List[int] = []
    for p, d in pairs:
        if not (1 <= p < n) or not (1 <= d < n):
            raise ValueError(
                f"pair ({p}, {d}) out of range 1..{n - 1} (n={n})"
            )
        if p == d:
            raise ValueError(f"pickup and delivery indices coincide: {p}")
        for idx in (p, d):
            if idx in seen:
                raise ValueError(
                    f"customer index {idx} appears in more than one pair"
                )
            seen.append(idx)
        flag[p] = 0
        flag[d] = 1
        mate[p] = d
        mate[d] = p
    missing = [i for i in range(1, n) if flag[i] is None]
    if missing:
        raise ValueError(
            f"customers without a pickup/delivery pair: {missing}. "
            f"Every non-depot index in 1..{n - 1} must be covered by `pairs`."
        )

    lines: List[str] = [str(n), f"1 {_fmt(x[0])} {_fmt(y[0])}"]
    for i in range(1, n):
        # File-position = i + 1 because the depot occupies position 1.
        # InstanceReader::fromFile overwrites the leading idx with its own
        # idxCount, but we still write a sensible value for human readers.
        lines.append(
            f"{i + 1} {_fmt(x[i])} {_fmt(y[i])} {flag[i]} {mate[i] + 1}"
        )
    lines.append("-999")
    path.write_text("\n".join(lines) + "\n")


def write_grubhub(
    path: Path,
    *,
    name: str,
    distance_matrix: Sequence[Sequence[float]],
) -> None:
    """Write an explicit distance-matrix instance for use with ``--grubhub``.

    Pickup/delivery pairing in this mode is implicit: odd-indexed nodes
    (1, 3, 5, …) are pickups and the following even-indexed node is the
    paired delivery. Node 0 is the depot. The matrix is N×N integers.

    Args:
        path: Destination file path.
        name: A short human-readable instance name (first line of the file).
        distance_matrix: ``N``×``N`` integer (or numeric, rounded) matrix.
            ``N`` must be odd ``+ 1`` (i.e. even total: 1 depot + an even
            number of customers, so they can be split into pickup/delivery
            pairs).
    """
    if not name or "\n" in name:
        raise ValueError("`name` must be a single non-empty line")
    rows = [list(r) for r in distance_matrix]
    n = len(rows)
    if n < 3:
        raise ValueError(f"distance_matrix too small (n={n}); need n>=3")
    if (n - 1) % 2 != 0:
        raise ValueError(
            "grubhub format requires an even number of customers "
            "(matrix dimension N must be odd; depot at index 0 plus "
            "pairs at (1,2), (3,4), ...). "
            f"Got N={n}, which leaves {n - 1} customers."
        )
    for i, row in enumerate(rows):
        if len(row) != n:
            raise ValueError(
                f"row {i} has length {len(row)}, expected {n}"
            )
    lines: List[str] = [name, f"Number of Nodes: {n}"]
    for row in rows:
        # Upstream parses with `liness >> dist` (int) then rounds with
        # `int(dist + 0.5)`. We emit rounded integers so the on-disk value
        # is unambiguous regardless of locale or float precision.
        lines.append(" ".join(str(int(round(float(v)))) for v in row))
    path.write_text("\n".join(lines) + "\n")


def _fmt(v: float) -> str:
    """Format a coordinate the way upstream parses it (free-form numeric).

    We use ``repr(float(v))`` so integers round-trip as ``1.0`` (still
    accepted by ``operator>>``) and ``.PDT`` files round-trip cleanly
    through ``write_pdt`` without lossy str conversion.
    """
    return repr(float(v))


# ---------------------------------------------------------------------------
# Stdout JSON parsing
# ---------------------------------------------------------------------------


_SOLUTION_RE = re.compile(r'"solution"\s*:\s*\[(?P<body>[^\]]*)\]')
_COST_RE = re.compile(r'"cost"\s*:\s*(?P<v>-?[0-9eE.+-]+)')
_TIME_RE = re.compile(r'"time"\s*:\s*(?P<v>-?[0-9eE.+-]+)')


def parse_stdout(stdout: str) -> Dict[str, Any]:
    """Parse the JSON document that ``pdphgs``/``pdprr`` print to stdout.

    Strategy: locate the outermost ``{...}`` block and run :func:`json.loads`
    on it. If that fails (upstream's HGS path interpolates
    ``LSCompleteLog()`` content into the document and we can't guarantee
    that text is well-formed JSON across every parameter combination), fall
    back to regex extraction of the fields we actually consume —
    ``cost``, ``time``, and ``solution``.

    Returns a dict with at least these keys:

    * ``cost`` (``float``)
    * ``time`` (``float``)
    * ``solution`` (``list[int]``) — the tour, starting and ending at depot 0
    * ``raw`` (``str | dict``) — the parsed JSON document if ``json.loads``
        succeeded, otherwise the raw substring we attempted to parse

    Raises :class:`ValueError` if the required fields can't be extracted.
    """
    block = _extract_json_block(stdout)
    if block is None:
        raise ValueError(
            "could not locate a JSON object in solver stdout. "
            "If you passed --verbose, the solver emits human-readable text "
            "instead of JSON; the wrapper invokes the solver without "
            "--verbose by default.\n"
            f"--- stdout ---\n{stdout}"
        )

    parsed: Any = None
    try:
        parsed = json.loads(block)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict) and "cost" in parsed and "solution" in parsed:
        return {
            "cost": float(parsed["cost"]),
            "time": float(parsed.get("time", 0.0)),
            "solution": [int(v) for v in parsed["solution"]],
            "raw": parsed,
        }

    # Fallback: regex extraction. Tolerates LSCompleteLog content that
    # isn't strictly JSON-conformant.
    cost_m = _COST_RE.search(block)
    time_m = _TIME_RE.search(block)
    sol_m = _SOLUTION_RE.search(block)
    if not (cost_m and sol_m):
        raise ValueError(
            "JSON block found but `cost` and/or `solution` could not be "
            f"extracted. Raw block:\n{block}"
        )
    solution = [int(s) for s in sol_m.group("body").replace(",", " ").split()]
    return {
        "cost": float(cost_m.group("v")),
        "time": float(time_m.group("v")) if time_m else 0.0,
        "solution": solution,
        "raw": block,
    }


def _extract_json_block(text: str) -> str | None:
    """Return the substring from the first ``{`` to its matching ``}``.

    Counts braces in a single pass so that nested objects (the ``evolution``
    array's entries) don't trip a naive ``str.find('}')``.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


__all__ = ["write_pdt", "write_grubhub", "parse_stdout"]
