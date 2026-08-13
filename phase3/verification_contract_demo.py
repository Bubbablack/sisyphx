"""CHUNK-027 throwaway demo: a minimal, standalone implementation of the
proposed two-tier verification contract (see phase3/notes/CHUNK-027.md),
used only to demonstrate the contract mechanically before CHUNK-028 builds
the real `phase3/verification_tiers.py`. Deliberately NOT wired into
`phase1/loop.py` -- that is CHUNK-031's job, after CHUNK-028/029/030 exist.

Mirrors `phase1/loop.py::run_verification`'s existing convention (plain
shell command, `subprocess.run(shell=True, cwd=repo, timeout=...)`) so the
real implementation can reuse it directly.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TierResult:
    ran: bool          # False if skipped (e.g. tier 2 skipped because tier 1 failed)
    exit_code: int | None
    output: str


@dataclass
class TieredVerificationResult:
    tier1: TierResult
    tier2: TierResult | None  # None if no tier 2 command was configured
    passed: bool
    failure_kind: str  # "verify-pass" / "verify-fail" / "verify-tier2-fail"


def _run_command(repo: Path, cmd: str, timeout: int) -> TierResult:
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=repo,
            capture_output=True, text=True, timeout=timeout,
        )
        return TierResult(ran=True, exit_code=proc.returncode, output=(proc.stdout or "") + (proc.stderr or ""))
    except subprocess.TimeoutExpired as e:
        output = (e.stdout or "") + (e.stderr or "")
        return TierResult(ran=True, exit_code=-1, output=output + "\n[SisyphX: verification command timed out]")


def run_tiered_verification(
    repo: Path,
    tier1_cmd: str,
    tier1_timeout: int,
    tier2_cmd: str | None = None,
    tier2_timeout: int = 60,
) -> TieredVerificationResult:
    """The proposed CHUNK-027 contract:

    1. Always run tier 1 (the project's own verification command) first --
       unchanged from Phase 1/2 behavior.
    2. If tier 1 fails, stop: tier 2 is skipped (no budget spent on a
       stronger check if the base gate already failed), failure_kind stays
       "verify-fail" exactly as today.
    3. If tier 1 passes and no tier 2 command is configured, the iteration
       passes -- fully backward compatible with chunks that declare no
       tier 2 (CHUNK-031's "opt-in per chunk" requirement).
    4. If tier 1 passes and tier 2 is configured, run tier 2. If tier 2
       fails, the iteration fails with the new, distinct failure_kind
       "verify-tier2-fail" (CHUNK-029) -- "the base tests were satisfied
       but a stronger check was not", which is exactly the semantic-cheat
       pattern from CHUNK-010/024.
    5. Both tiers passing -> "verify-pass", same as today.
    """
    tier1 = _run_command(repo, tier1_cmd, tier1_timeout)
    if tier1.exit_code != 0:
        return TieredVerificationResult(tier1=tier1, tier2=None, passed=False, failure_kind="verify-fail")

    if tier2_cmd is None:
        return TieredVerificationResult(tier1=tier1, tier2=None, passed=True, failure_kind="verify-pass")

    tier2 = _run_command(repo, tier2_cmd, tier2_timeout)
    if tier2.exit_code != 0:
        return TieredVerificationResult(tier1=tier1, tier2=tier2, passed=False, failure_kind="verify-tier2-fail")

    return TieredVerificationResult(tier1=tier1, tier2=tier2, passed=True, failure_kind="verify-pass")
