"""Unit tests for parameter dataclasses' argv conversion."""
from __future__ import annotations

from pdtsp import HGSParameters, RRParameters


def test_hgs_defaults_produce_expected_argv() -> None:
    argv = HGSParameters().to_argv()
    assert "--seed=0" in argv
    assert "--it=1000000" in argv
    assert "--mu=25" in argv
    assert "--lambda=40" in argv  # upstream flag is --lambda, Python field is lam
    assert "--div=4000" in argv
    assert "--nb-elite=1" in argv
    assert "--nb-close=2" in argv
    assert "--neighborhoods=RELOCATE-2OPT-2KOPT-OROPT-4OPT-BS" in argv
    assert "--bs-k=3" in argv
    assert "--or-k=30" in argv
    # default time_limit is None — must NOT appear
    assert not any(a.startswith("--time-limit") for a in argv)
    # default verbose is False — must NOT appear
    assert "--verbose" not in argv


def test_hgs_time_limit_and_verbose_emit_flags() -> None:
    p = HGSParameters(time_limit=5, verbose=True)
    argv = p.to_argv()
    assert "--time-limit=5" in argv
    assert "--verbose" in argv


def test_hgs_seed_and_neighborhoods_override() -> None:
    p = HGSParameters(seed=42, neighborhoods="RELOCATE-2OPT")
    argv = p.to_argv()
    assert "--seed=42" in argv
    assert "--neighborhoods=RELOCATE-2OPT" in argv


def test_rr_defaults_produce_expected_argv() -> None:
    argv = RRParameters().to_argv()
    assert "--seed=0" in argv
    assert "--it=50000" in argv
    assert any(a.startswith("--p-accept=") for a in argv)
    assert any(a.startswith("--c-rate=") for a in argv)
    # default fast / verbose / time_limit are off — must NOT appear
    assert "--fast" not in argv
    assert "--verbose" not in argv
    assert not any(a.startswith("--time-limit") for a in argv)


def test_rr_fast_and_time_limit() -> None:
    p = RRParameters(fast=True, time_limit=10, verbose=True)
    argv = p.to_argv()
    assert "--fast" in argv
    assert "--time-limit=10" in argv
    assert "--verbose" in argv
