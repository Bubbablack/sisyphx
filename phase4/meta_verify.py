"""CHUNK-039 -- per-individual-check meta-verification, per CHUNK-037's
contract (`phase4/notes/CHUNK-037.md`).

CHUNK-036/037 found that a combined-exit-code decision is unsafe: a single
broken check in an agent-authored test (e.g. a `FailedHealthCheck`) fails
unconditionally regardless of implementation correctness, and would
permanently block a genuinely correct fix if trusted naively. This module
never looks at a combined exit code. Instead:

    1. Run every individual test function (from the agent-authored
       property test AND the auto-generated `phase4/literal_examples.py`
       companion) against a known-good reference implementation. Any check
       that fails there is discarded -- it is broken/unreliable regardless
       of the candidate implementation, and must never count against a
       real candidate later (this is what avoids permanently blocking a
       correct fix over a health-check bug, per CHUNK-037's finding).
    2. Of the checks that survive step 1 ("valid checks"), run them against
       a known-bad reference implementation. Any valid check that fails
       there is "discriminating" -- proof that it actually distinguishes
       correct from incorrect behavior, not just an artifact of a
       particular implementation.
    3. The candidate test set is "sound" only if at least one discriminating
       check exists. If every check was discarded in step 1, there is
       nothing left to verify with, and the candidate is rejected outright.

Uses pytest's built-in `--junitxml` for robust per-test-function outcome
parsing (not fragile stdout scraping).
"""
from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MetaVerifyResult:
    sound: bool
    valid_checks: tuple[str, ...]           # passed against the known-good reference
    discarded_checks: tuple[str, ...]       # failed against the known-good reference -- never trusted
    discriminating_checks: tuple[str, ...]  # valid AND failed against the known-bad reference
    verify_tier2_command: str | None        # pytest invocation with discarded checks deselected, or None if unsound
    reason: str


def _run_pytest_junit(repo: Path, test_files: list[str]) -> dict[str, bool]:
    """Run pytest against `test_files` in `repo`; return {nodeid: passed}
    parsed from junit XML, not stdout text."""
    junit_path = repo / "_meta_verify_junit.xml"
    subprocess.run(
        ["uv", "run", "pytest", *test_files, f"--junitxml={junit_path}", "-q"],
        cwd=repo, capture_output=True, text=True, timeout=120,
    )
    outcomes: dict[str, bool] = {}
    if not junit_path.exists():
        return outcomes
    tree = ET.parse(junit_path)
    for testcase in tree.iter("testcase"):
        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        # classname is typically the dotted module path (e.g.
        # "test_listutils_property"); reconstruct a pytest-style nodeid
        # ("test_listutils_property.py::test_name") for use in --deselect.
        module = classname.rsplit(".", 1)[-1] if "." in classname else classname
        nodeid = f"{module}.py::{name}"
        failed = testcase.find("failure") is not None or testcase.find("error") is not None
        outcomes[nodeid] = not failed
    junit_path.unlink(missing_ok=True)
    return outcomes


def _prepare_variant(
    fixture_repo: Path,
    dest: Path,
    module_filename: str,
    module_source: str,
    candidate_test_files: dict[str, str],
) -> None:
    shutil.copytree(
        fixture_repo, dest,
        ignore=shutil.ignore_patterns(".git", ".agent-state", ".pytest_cache", "__pycache__", "*.pyc"),
    )
    (dest / module_filename).write_text(module_source)
    for filename, content in candidate_test_files.items():
        (dest / filename).write_text(content)


def meta_verify(
    fixture_repo: Path,
    scratch_dir: Path,
    module_filename: str,
    known_good_source: str,
    known_bad_source: str,
    candidate_test_files: dict[str, str],
) -> MetaVerifyResult:
    """Decide whether `candidate_test_files` (e.g. an agent-authored
    property test plus the auto-generated literal-examples companion) is
    sound enough to trust as a `--verify-tier2` command, per the
    per-individual-check contract above.

    `candidate_test_files` maps filename -> source content. `fixture_repo`
    should contain everything else the test files need (pyproject.toml,
    etc.) but NOT `module_filename` itself or any existing test files with
    conflicting names -- callers are responsible for that isolation, same
    as `phase4/test_author.py`'s authoring step.
    """
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)
    scratch_dir.mkdir(parents=True)

    test_filenames = list(candidate_test_files.keys())

    good_repo = scratch_dir / "known_good"
    _prepare_variant(fixture_repo, good_repo, module_filename, known_good_source, candidate_test_files)
    good_outcomes = _run_pytest_junit(good_repo, test_filenames)

    valid_checks = tuple(sorted(nodeid for nodeid, passed in good_outcomes.items() if passed))
    discarded_checks = tuple(sorted(nodeid for nodeid, passed in good_outcomes.items() if not passed))

    if not valid_checks:
        return MetaVerifyResult(
            sound=False,
            valid_checks=(),
            discarded_checks=discarded_checks,
            discriminating_checks=(),
            verify_tier2_command=None,
            reason=(
                "Every check failed against the known-good reference -- "
                "nothing left to verify with. Rejecting the candidate "
                "outright rather than trusting a test that never passes."
            ),
        )

    bad_repo = scratch_dir / "known_bad"
    _prepare_variant(fixture_repo, bad_repo, module_filename, known_bad_source, candidate_test_files)
    bad_outcomes = _run_pytest_junit(bad_repo, test_filenames)

    discriminating_checks = tuple(
        sorted(nodeid for nodeid in valid_checks if not bad_outcomes.get(nodeid, True))
    )

    if not discriminating_checks:
        return MetaVerifyResult(
            sound=False,
            valid_checks=valid_checks,
            discarded_checks=discarded_checks,
            discriminating_checks=(),
            verify_tier2_command=None,
            reason=(
                "All valid checks passed against the known-bad reference too "
                "-- none of them actually distinguish correct from incorrect "
                "behavior. Rejecting the candidate."
            ),
        )

    deselect_args = " ".join(f'--deselect "{nodeid}"' for nodeid in discarded_checks)
    command = f"uv run pytest {' '.join(test_filenames)}"
    if deselect_args:
        command += " " + deselect_args

    return MetaVerifyResult(
        sound=True,
        valid_checks=valid_checks,
        discarded_checks=discarded_checks,
        discriminating_checks=discriminating_checks,
        verify_tier2_command=command,
        reason=(
            f"{len(discriminating_checks)} of {len(valid_checks)} valid check(s) "
            f"discriminate known-good from known-bad "
            f"({len(discarded_checks)} discarded as broken/unreliable)."
        ),
    )
