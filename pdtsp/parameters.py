"""Algorithm-parameter dataclasses.

Two dataclasses, one per upstream binary. Field names mirror the upstream
CLI flags (camelCase variants of the kebab-case shell flags) so the
upstream README is directly applicable as a reference for what each knob
does. ``to_argv()`` formats the fields into a list of ``--flag=value``
strings ready to be appended to a subprocess argv.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


def _bool_flag(name: str, value: bool) -> List[str]:
    """Convert a boolean field to a CLI flag.

    Upstream uses boost::program_options switches, which are presence-only
    (no ``--flag=true``/``--flag=false``); pass the flag when ``True`` and
    omit when ``False``.
    """
    return [f"--{name}"] if value else []


@dataclass
class HGSParameters:
    """Tunables for the PDP-HGS (Hybrid Genetic Search) solver.

    Defaults track ``pdphgs --help`` from upstream commit
    ``451bc8a5``. See :file:`README.md` of the upstream repository for
    the algorithmic meaning of each knob.
    """

    # Stopping criteria
    time_limit: Optional[int] = None    # --time-limit, seconds; None => no limit
    it: int = 1_000_000                 # --it, iterations w/o improvement

    # Population
    mu: int = 25                        # --mu, minimum population size
    lam: int = 40                       # --lambda, offspring per generation
    div: int = 4000                     # --div, iters before diversification
    nb_elite: int = 1                   # --nb-elite
    nb_close: int = 2                   # --nb-close

    # Neighborhood structure
    neighborhoods: str = "RELOCATE-2OPT-2KOPT-OROPT-4OPT-BS"  # --neighborhoods
    bs_k: int = 3                       # --bs-k, Balas & Simonetti k
    or_k: int = 30                      # --or-k, Or-Opt k
    ratio_slow_nb: float = 1.0          # --ratio-slow-nb

    # Reproducibility / logging
    seed: int = 0                       # --seed
    verbose: bool = False               # --verbose

    def to_argv(self) -> List[str]:
        argv: List[str] = [
            f"--seed={int(self.seed)}",
            f"--it={int(self.it)}",
            f"--mu={int(self.mu)}",
            f"--lambda={int(self.lam)}",
            f"--div={int(self.div)}",
            f"--nb-elite={int(self.nb_elite)}",
            f"--nb-close={int(self.nb_close)}",
            f"--neighborhoods={self.neighborhoods}",
            f"--bs-k={int(self.bs_k)}",
            f"--or-k={int(self.or_k)}",
            f"--ratio-slow-nb={float(self.ratio_slow_nb)!r}",
        ]
        if self.time_limit is not None:
            argv.append(f"--time-limit={int(self.time_limit)}")
        argv += _bool_flag("verbose", self.verbose)
        return argv


@dataclass
class RRParameters:
    """Tunables for the PDP-RR (Ruin & Recreate) solver.

    Defaults track ``pdprr --help`` from upstream commit ``451bc8a5``.
    """

    fast: bool = False                 # --fast, use fast reinsertion
    time_limit: Optional[int] = None   # --time-limit, seconds; None => no limit
    it: int = 50_000                   # --it
    p_accept: float = 3.0              # --p-accept
    c_rate: float = 0.99987571600000003  # --c-rate (matches upstream default literally)
    seed: int = 0                      # --seed
    verbose: bool = False              # --verbose

    def to_argv(self) -> List[str]:
        argv: List[str] = [
            f"--seed={int(self.seed)}",
            f"--it={int(self.it)}",
            f"--p-accept={float(self.p_accept)!r}",
            f"--c-rate={float(self.c_rate)!r}",
        ]
        if self.time_limit is not None:
            argv.append(f"--time-limit={int(self.time_limit)}")
        argv += _bool_flag("fast", self.fast)
        argv += _bool_flag("verbose", self.verbose)
        return argv


__all__ = ["HGSParameters", "RRParameters"]
