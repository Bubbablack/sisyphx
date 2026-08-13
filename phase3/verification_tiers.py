"""CHUNK-028 -- pluggable second verification tier, per the contract decided
in CHUNK-027 (`phase3/notes/CHUNK-027.md`).

Promotes `phase3/verification_contract_demo.py`'s throwaway logic into the
real module `loop.py` will use starting at CHUNK-031. Deliberately mirrors
`phase1/loop.py::run_verification`'s existing convention exactly: a tier is
just a plain shell command run via `subprocess.run(shell=True, cwd=repo,
timeout=...)`, never through the agent's own exec tool. No new execution
model, no Pydantic/config file format yet -- config is passed in by the
caller (loop.py's CLI args from CHUNK-031), same as tier 1 already is.

Contract (CHUNK-027):
    1. Tier 1 (the project's own verification command) always runs first.
    2. If tier 1 fails, tier 2 is skipped entirely -- failure_kind stays
       "verify-fail", exactly as Phase 1/2.
    3. If tier 1 passes and no tier 2 command was configured, the result is
       "verify-pass" -- fully backward compatible with chunks that declare
       no tier 2.
    4. If tier 1 passes and tier 2 is configured, tier 2 runs. A tier 2
       failure produces the new, distinct failure_kind "verify-tier2-fail"
       rather than a misleading "verify-pass".
    5. Both tiers passing -> "verify-pass".
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

# Per CHUNK-025/026: property-test-style tiers run in ~1-2s; mutation-testing
# style commands should not be used as an attempt-level tier 2 (CHUNK-026
# measured 52-64s on a trivial module). This default keeps tier 2 well
# inside the attempt-level <60s budget from Design decision #4 while still
# giving real property tests headroom.
DEFAULT_TIER2_TIMEOUT_SECONDS = 30


@dataclass
class TierResult:
    """The raw result of running one verification tier."""
    ran: bool                 # False only for tier2 when it was skipped/not configured
    exit_code: int | None
    output: str                # combined stdout+stderr
    timed_out: bool = False


@dataclass
class TieredVerificationResult:
    tier1: TierResult
    tier2: TierResult | None   # None if tier 2 was not configured for this chunk
    passed: bool
    failure_kind: str          # "verify-pass" | "verify-fail" | "verify-tier2-fail"


def _run_tier(repo: Path, cmd: str, timeout: int) -> TierResult:
    """Run one verification tier as its own subprocess -- never through the
    agent's exec tool. Same timeout-handling convention as
    `phase1/loop.py::run_verification` (CHUNK-003: bounding a subprocess is
    always the loop's job, never left to the tool itself)."""
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=repo,
            capture_output=True, text=True, timeout=timeout,
        )
        return TierResult(ran=True, exit_code=proc.returncode, output=(proc.stdout or "") + (proc.stderr or ""))
    except subprocess.TimeoutExpired as e:
        output = (e.stdout or "") + (e.stderr or "")
        return TierResult(
            ran=True, exit_code=-1, timed_out=True,
            output=output + "\n[SisyphX: verification tier timed out]",
        )


def run_tiered_verification(
    repo: Path,
    tier1_cmd: str,
    tier1_timeout: int,
    tier2_cmd: str | None = None,
    tier2_timeout: int = DEFAULT_TIER2_TIMEOUT_SECONDS,
) -> TieredVerificationResult:
    """Run tier 1 (required) and, only if it passes, tier 2 (opt-in). See
    module docstring for the full contract."""
    tier1 = _run_tier(repo, tier1_cmd, tier1_timeout)
    if tier1.exit_code != 0:
        return TieredVerificationResult(tier1=tier1, tier2=None, passed=False, failure_kind="verify-fail")

    if tier2_cmd is None:
        return TieredVerificationResult(tier1=tier1, tier2=None, passed=True, failure_kind="verify-pass")

    tier2 = _run_tier(repo, tier2_cmd, tier2_timeout)
    if tier2.exit_code != 0:
        return TieredVerificationResult(tier1=tier1, tier2=tier2, passed=False, failure_kind="verify-tier2-fail")

    return TieredVerificationResult(tier1=tier1, tier2=tier2, passed=True, failure_kind="verify-pass")
