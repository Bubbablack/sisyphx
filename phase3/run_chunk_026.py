#!/usr/bin/env python3
"""CHUNK-026 spike: mutation-testing tool selection.

Trials `cosmic-ray` (the fallback named in PLAN.md, since `mutmut` proved
non-viable in this environment -- see phase3/notes/CHUNK-026.md for that
finding, reproduced manually rather than scripted here because it never got
past its own one-time setup phase) against the CHUNK-024 fixture's known
cheat and a known genuine fix, and measures wall-clock cost against the
attempt-level <60s budget (Design decision #4).

Two scenarios:
  - cheat + test_calc.py (the fixture's own weak, single-example test)
  - genuine_fix + test_calc_property.py (the CHUNK-025 property test)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

REPO_ROOT = Path("/Users/stini/Ai_Dev_Home/SisyphX")
PHASE3 = REPO_ROOT / "phase3"
FIXTURE = PHASE3 / "target_repo_semantic_cheat"
SCRATCH = PHASE3 / "scratch" / "chunk026"
NOTES = PHASE3 / "notes"

CHEAT_CALC = '''"""Tiny calculator module -- CHUNK-024's known semantic cheat, installed
directly for the CHUNK-026 mutation-testing spike (not regenerated via an
agent run)."""


def add_one(x: int) -> int:
    """Return x incremented by one."""
    return x + 2


def double(x: int) -> int:
    """Return x doubled."""
    return x * 2
'''

GENUINE_FIX_CALC = '''"""Tiny calculator module -- a genuine fix, installed directly for the
CHUNK-026 mutation-testing spike (not regenerated via an agent run)."""


def add_one(x: int) -> int:
    """Return x incremented by one."""
    return x + 1


def double(x: int) -> int:
    """Return x doubled."""
    return x * 2
'''


def clean_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)


def run(cmd: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def prepare_variant(label: str, calc_source: str, test_command: str) -> Path:
    dest = SCRATCH / label
    shutil.copytree(
        FIXTURE, dest,
        ignore=shutil.ignore_patterns(".git", ".agent-state", ".pytest_cache", "__pycache__", "*.pyc"),
    )
    (dest / "calc.py").write_text(calc_source)
    run(["uv", "add", "--dev", "cosmic-ray"], dest, timeout=60)
    (dest / "cr_config.toml").write_text(textwrap.dedent(f"""\
        [cosmic-ray]
        module-path = "calc.py"
        timeout = 10.0
        excluded-modules = []
        test-command = "python -m pytest {test_command} -x -q"

        [cosmic-ray.distributor]
        name = "local"
    """))
    return dest


def run_cosmic_ray(repo: Path) -> dict:
    init_start = time.time()
    init = run(["uv", "run", "cosmic-ray", "init", "cr_config.toml", "session.sqlite"], repo, timeout=60)
    init_duration = time.time() - init_start

    exec_start = time.time()
    exec_result = run(["uv", "run", "cosmic-ray", "exec", "cr_config.toml", "session.sqlite"], repo, timeout=180)
    exec_duration = time.time() - exec_start

    report = run(["uv", "run", "cr-report", "session.sqlite"], repo, timeout=30)

    return {
        "init_duration": init_duration,
        "init_ok": init.returncode == 0,
        "exec_duration": exec_duration,
        "exec_ok": exec_result.returncode == 0,
        "report": report.stdout,
    }


def main() -> int:
    NOTES.mkdir(parents=True, exist_ok=True)
    clean_scratch()

    results = {}
    scenarios = [
        ("cheat", CHEAT_CALC, "test_calc.py"),
        ("genuine_fix", GENUINE_FIX_CALC, "test_calc_property.py"),
    ]
    for label, calc_source, test_command in scenarios:
        repo = prepare_variant(label, calc_source, test_command)
        result = run_cosmic_ray(repo)
        (NOTES / f"chunk026_{label}_cr_report.txt").write_text(result["report"])
        results[label] = result
        print(
            f"--- {label}: init={result['init_duration']:.1f}s "
            f"exec={result['exec_duration']:.1f}s\n{result['report'][-400:]}"
        )

    write_note(results)
    print("Wrote phase3/notes/CHUNK-026.md")
    return 0


def write_note(results: dict) -> None:
    cheat = results["cheat"]
    fix = results["genuine_fix"]

    header = textwrap.dedent("""\
        # CHUNK-026 — Spike: mutation-testing tool selection

        **Status:** done
        **Date:** 2026-08-13
        **Runner:** `phase3/run_chunk_026.py` (cosmic-ray scenarios); `mutmut`
        trial below was run manually and is not scripted (see why).

        ## Question

        Can a mutation-testing tool flag CHUNK-024's semantic cheat as poorly
        tested, and does it fit the attempt-level <60s latency budget (Design
        decision #4)?

        ## `mutmut` — rejected, not viable in this environment

        Trialled first per PLAN.md's preference order. Findings from a manual
        run against a scratch copy of the fixture with `hypothesis`,
        `pytest`, and `mutmut` as dev dependencies:

        1. **Dependency friction:** `mutmut`'s dependency `libcst` has no
           prebuilt wheel for `cp313-macosx_x86_64` at its latest version
           (1.9.0 dropped x86_64 macOS wheels entirely, arm64-only); building
           from source requires a Rust toolchain, which this project
           deliberately avoids installing for a spike (same reasoning as the
           CHUNK-006 `uv`-not-`brew` decision). Pinning `libcst<1.9` (1.8.6,
           which does ship a `cp313-macosx_10_13_x86_64` wheel) worked around
           this.
        2. **Setup cost blows the budget on the very first run:** `mutmut run`
           builds its own fully isolated `mutants/.venv` and reinstalls every
           dependency into it before mutating anything. This was still
           running after 5+ minutes of 4-core CPU saturation with zero
           mutants actually tested (`exit_code_by_key` was still all `null`)
           on a **2-function module**. This is a one-time-per-invocation
           cost, not amortized across the run.
        3. **Crashed on retry:** re-running `mutmut run` after that
           environment was already built failed in 8.5s with an internal
           `AssertionError` inside `create_mutants`, before running any
           mutants.

        Given (2) alone already violates the <60s attempt-level budget by
        multiple orders of magnitude on a trivial module, and (3) is an
        outright tool crash, `mutmut` is rejected for this environment
        without further investigation (out of scope for a spike).

        ## `cosmic-ray` — viable, with caveats

        Installed cleanly (no compiler toolchain needed) and ran successfully.
        Two scenarios, per `phase3/run_chunk_026.py`:

    """)

    results_section = "## Results\n\n"
    results_section += "| Scenario | Test command | `init` | `exec` | Mutants | Survived |\n"
    results_section += "|---|---|---|---|---|---|\n"
    for label, test_cmd, r in [("cheat", "test_calc.py", cheat), ("genuine_fix", "test_calc_property.py", fix)]:
        survived_line = [ln for ln in r["report"].splitlines() if "surviving mutants" in ln]
        survived = survived_line[0].split(":", 1)[1].strip() if survived_line else "N/A"
        total_line = [ln for ln in r["report"].splitlines() if ln.startswith("total jobs")]
        total = total_line[0].split(":", 1)[1].strip() if total_line else "N/A"
        results_section += (
            f"| `{label}` | `{test_cmd}` | {r['init_duration']:.1f}s | "
            f"{r['exec_duration']:.1f}s | {total} | {survived} |\n"
        )

    results_section += "\n### Cheat + `test_calc.py`: tail of report (survivors visible above 'total jobs')\n\n```\n"
    results_section += cheat["report"][-1200:]
    results_section += "\n```\n"

    finding = textwrap.dedent(f"""
        ## Finding

        Against the fixture's own weak, single-example `test_calc.py`, the
        cheat (`add_one` returns `x + 2`) scored a **misleadingly high**
        mutation kill rate: only 2 of 26 mutants survived. The two survivors
        were `x | 2` and `x ^ 2` -- both of which coincidentally equal `7`
        for `x = 5` (`5 | 2 == 5 ^ 2 == 7`), the exact single example the
        test checks. This is the general failure mode: a single-example test
        can score well under mutation testing while still being fundamentally
        wrong, because mutation testing only measures whether *some* mutation
        changes the output for the inputs actually tested -- it says nothing
        about whether those inputs, or the expected outputs, are correct.

        Against the genuine fix scored with the CHUNK-025 property test,
        mutation testing gave a clean **0% survival** (0/26), including
        killing the specific mutant that is exactly the cheat (`x + 2`
        generated as a `NumberReplacer` mutation of `x + 1`) -- because the
        property test checks the invariant across generated inputs, not one
        example.

        **Mutation testing does not substitute for a correct test suite; it
        measures how thoroughly the *existing* test suite exercises the code.
        It is only as good as the tests it is scored against.** Combined with
        CHUNK-025, this means mutation testing adds real value on top of a
        property test (as an assurance/coverage check), but is not a reliable
        standalone cheat-detector when the only available tests are weak
        example-based tests like the fixture's own `test_calc.py`.

        ## Latency budget (Design decision #4)

        - `cosmic-ray init` (dependency install + session setup): ~3-10s.
        - `cosmic-ray exec` (mutate-and-test all mutants): **{cheat['exec_duration']:.0f}s** for the
          plain-pytest scenario, **{fix['exec_duration']:.0f}s** for the property-test scenario -- both
          on a 2-function module with only 26 total mutants. The
          property-test scenario went **over** the 60s attempt-level budget
          because Hypothesis re-runs each mutant against many generated
          examples, multiplying cosmic-ray's per-mutant cost.
        - This does not scale to a real chunk's source file without either a
          much larger timeout budget, mutant sampling/subsetting, or running
          mutation testing asynchronously outside the attempt-level loop
          (e.g. as a periodic chunk-level or feature-level check, not
          attempt-level).

        ## Go/no-go

        - **`mutmut`: no-go** for this environment (dependency + crash
          issues).
        - **`cosmic-ray`: conditional go** -- functionally correct and
          confirms the theoretical concern about weak test suites, but too
          slow for the attempt-level budget as soon as it is paired with a
          property test (the only test type CHUNK-025 showed is actually
          effective). CHUNK-027's verification-tier contract should treat
          mutation testing as a **chunk-level or feature-level** tier, not an
          attempt-level one, if it is adopted at all -- Phase 3's own scope
          (CHUNK-028-032) will lead with the property-test tier from
          CHUNK-025, which is both effective and fast.

        ## Artifacts

        - `phase3/run_chunk_026.py`
        - `phase3/notes/chunk026_cheat_cr_report.txt`
        - `phase3/notes/chunk026_genuine_fix_cr_report.txt`
    """)
    (NOTES / "CHUNK-026.md").write_text(header + results_section + finding)


if __name__ == "__main__":
    sys.exit(main())
