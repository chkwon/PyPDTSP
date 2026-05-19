"""Unit tests for the I/O layer (no binary, no JVM, no system deps)."""
from __future__ import annotations

from pathlib import Path

import pytest

from pdtsp import _io


def test_write_pdt_basic_layout(tmp_path: Path) -> None:
    path = tmp_path / "tiny.PDT"
    _io.write_pdt(
        path,
        x=[0.0, 1.0, 2.0, 3.0, 4.0],
        y=[0.0, 1.0, 2.0, 3.0, 4.0],
        pairs=[(1, 3), (2, 4)],
    )
    lines = path.read_text().strip().splitlines()
    # Line 1: total node count (1 depot + 4 customers)
    assert lines[0] == "5"
    # Line 2: depot, first column is positional (1) and the reader will
    # overwrite the parsed idx anyway.
    assert lines[1].startswith("1 0.0 0.0")
    # Customer 1 is a pickup paired with file-position 4 (= customer 3).
    assert lines[2] == "2 1.0 1.0 0 4"
    # Customer 2 is a pickup paired with file-position 5 (= customer 4).
    assert lines[3] == "3 2.0 2.0 0 5"
    # Customer 3 is the delivery for customer 1 (file-position 2).
    assert lines[4] == "4 3.0 3.0 1 2"
    # Customer 4 is the delivery for customer 2 (file-position 3).
    assert lines[5] == "5 4.0 4.0 1 3"
    # Terminator
    assert lines[6] == "-999"


def test_write_pdt_rejects_unpaired_customer(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="without a pickup/delivery pair"):
        _io.write_pdt(
            tmp_path / "x.PDT",
            x=[0.0, 1.0, 2.0, 3.0],
            y=[0.0, 1.0, 2.0, 3.0],
            pairs=[(1, 2)],  # customer 3 unpaired
        )


def test_write_pdt_rejects_duplicate_in_pairs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="more than one pair"):
        _io.write_pdt(
            tmp_path / "x.PDT",
            x=[0.0, 1.0, 2.0, 3.0, 4.0],
            y=[0.0, 1.0, 2.0, 3.0, 4.0],
            pairs=[(1, 2), (2, 3)],  # 2 appears twice
        )


def test_write_pdt_rejects_self_pair(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="coincide"):
        _io.write_pdt(
            tmp_path / "x.PDT",
            x=[0.0, 1.0, 2.0],
            y=[0.0, 1.0, 2.0],
            pairs=[(1, 1)],
        )


def test_write_pdt_rejects_out_of_range_index(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="out of range"):
        _io.write_pdt(
            tmp_path / "x.PDT",
            x=[0.0, 1.0, 2.0],
            y=[0.0, 1.0, 2.0],
            pairs=[(1, 9)],
        )


def test_write_grubhub_basic_layout(tmp_path: Path) -> None:
    path = tmp_path / "small.txt"
    matrix = [
        [0, 1, 2, 3, 4],
        [1, 0, 5, 6, 7],
        [2, 5, 0, 8, 9],
        [3, 6, 8, 0, 1],
        [4, 7, 9, 1, 0],
    ]
    _io.write_grubhub(path, name="demo", distance_matrix=matrix)
    lines = path.read_text().strip().splitlines()
    assert lines[0] == "demo"
    assert lines[1] == "Number of Nodes: 5"
    assert lines[2] == "0 1 2 3 4"
    assert lines[-1] == "4 7 9 1 0"


def test_write_grubhub_rejects_odd_customer_count(tmp_path: Path) -> None:
    # 1 depot + 2 customers (odd customer count when split for PD pairing —
    # actually 2 is even, this should pass). Try 1 depot + 1 customer:
    with pytest.raises(ValueError):
        _io.write_grubhub(
            tmp_path / "x.txt",
            name="bad",
            distance_matrix=[[0, 1], [1, 0]],  # only 1 customer, no pair
        )


def test_parse_stdout_handles_well_formed_rr_json() -> None:
    """Mirror the exact shape produced by PDP-RR/solver.cpp::PrintStats."""
    stdout = """{
  "version": "v1.0.0",
  "cost": 3585,
  "time": 0.041,
  "educate": 50000,
  "solution": [0, 3, 5, 2, 4, 1, 7, 9, 10, 8, 6, 0],
  "evolution": [
    {
       "iteration": 0,
       "time": 0.001,
       "cost": 4200
    },
    {
       "iteration": 17,
       "time": 0.012,
       "cost": 3585
    }
  ]
}
"""
    out = _io.parse_stdout(stdout)
    assert out["cost"] == 3585.0
    assert out["time"] == pytest.approx(0.041)
    assert out["solution"] == [0, 3, 5, 2, 4, 1, 7, 9, 10, 8, 6, 0]
    assert isinstance(out["raw"], dict)
    assert out["raw"]["evolution"][1]["cost"] == 3585


def test_parse_stdout_falls_back_when_json_invalid() -> None:
    """When upstream's LSCompleteLog block contains non-JSON content, we
    fall back to regex extraction of the fields we care about."""
    stdout = """garbage prefix
{
  "version": "1.0",
  "cost": 1234.5,
  "time": 2.5,
  LSCompleteLog: some tab\tdelimited\tnonsense,
  "solution": [0, 1, 2, 3, 0]
}
"""
    out = _io.parse_stdout(stdout)
    assert out["cost"] == pytest.approx(1234.5)
    assert out["time"] == pytest.approx(2.5)
    assert out["solution"] == [0, 1, 2, 3, 0]
    # raw should be a string in fallback mode (the JSON block substring),
    # not a parsed dict.
    assert isinstance(out["raw"], str)


def test_parse_stdout_raises_on_missing_block() -> None:
    with pytest.raises(ValueError, match="could not locate"):
        _io.parse_stdout("no braces at all here, just text")


def test_parse_stdout_raises_on_no_cost() -> None:
    with pytest.raises(ValueError, match="could not be extracted"):
        _io.parse_stdout('{ "solution": [0, 1, 0], "nothing": "useful" }')
