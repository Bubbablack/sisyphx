"""CHUNK-040 -- pre-loop planning step wiring test authoring
(`phase4/test_author.py`, CHUNK-038) and meta-verification
(`phase4/meta_verify.py`, CHUNK-039) together, per CHUNK-037's contract.

Sequence:
    1. Author a candidate property test from acceptance criteria alone, in
       an isolated sandbox (never the implementer's actual workspace).
    2. If no test was written, stop and escalate -- do not run the
       implementer agent at all.
    3. Auto-generate the literal-examples companion test
       (`phase4/literal_examples.py`) from the same acceptance criteria.
    4. Meta-verify both files together against known-good/known-bad
       references. If unsound, stop and escalate -- do not run the
       implementer agent unprotected, and do not silently fall back to
       tier 1 only (that would hide the fact that no tier-2 protection
       exists for this chunk).
    5. Only if sound: write both test files into the implementer's
       workspace and invoke `phase1/loop.py` with `--verify-tier2` set to
       the meta-verified command.

This module never runs the implementer agent unless step 4 passed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOP = REPO_ROOT / "phase1" / "loop.py"

# Same convention as phase1/loop.py's LOOP_AUTHOR_NAME/EMAIL, so a
# pre-loop planning commit is traceable to SisyphX itself, not a stray
# local git identity.
PLANNING_AUTHOR_NAME = "SisyphX Loop"
PLANNING_AUTHOR_EMAIL = "loop@sisyphx.local"

sys.path.insert(0, str(REPO_ROOT))
from phase4.literal_examples import extract_literal_examples, generate_literal_example_test  # noqa: E402
from phase4.meta_verify import MetaVerifyResult, meta_verify  # noqa: E402
from phase4.test_author import AuthoringResult, author_property_test  # noqa: E402


@dataclass(frozen=True)
class PlanAndRunResult:
    exit_code: int          # process-style: same codes as loop.py, plus 5 = authoring/meta-verify rejected
    stage: str               # "authoring-failed" | "meta-verify-rejected" | "loop"
    authoring_result: AuthoringResult | None
    meta_verify_result: MetaVerifyResult | None
    escalation_path: Path | None


AUTHORING_OR_METAVERIFY_REJECTED_EXIT_CODE = 5


def _run_loop_subprocess(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Isolated so tests can stub just the loop invocation without also
    having to stub the (real, cheap) `git init` calls used to set up the
    authoring sandbox."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def write_escalation_brief(
    repo: Path,
    stage: str,
    reason: str,
    authoring_result: AuthoringResult | None,
) -> Path:
    """A lightweight escalation brief for the pre-loop planning stage --
    distinct from `phase2/recovery_ladder.write_escalation_brief`, which
    assumes an iteration history that doesn't exist yet at this stage (the
    implementer agent never ran)."""
    path = repo / ".agent-state" / "escalation.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    authored_section = ""
    if authoring_result is not None and authoring_result.test_written:
        authored_section = (
            "\n## Authored test (rejected by meta-verification)\n\n```python\n"
            + authoring_result.test_source.strip() + "\n```\n"
        )

    body = (
        "# SisyphX Phase 4 planning-stage escalation\n\n"
        f"## Stage\n\n`{stage}`\n\n"
        f"## Reason\n\n{reason}\n"
        f"{authored_section}\n"
        "## What this means\n\n"
        "The implementer agent was **not** run. Either no candidate "
        "property test could be authored from the acceptance criteria, or "
        "the candidate test failed meta-verification (it never executes, "
        "or it does not distinguish a known-good from a known-bad "
        "reference). Running the implementer without tier-2 protection, or "
        "silently falling back to tier-1-only verification, would hide "
        "this gap rather than surface it -- so the loop was not started.\n"
    )
    path.write_text(body)
    return path


def plan_and_run(
    *,
    implementer_repo: Path,
    task_path: Path,
    verify_cmd: str,
    verification_fixture_repo: Path,
    acceptance_criteria_path: Path,
    module_filename: str,
    test_filename: str,
    known_good_source: str,
    known_bad_source: str,
    authoring_sandbox: Path,
    meta_verify_scratch: Path,
    authoring_timeout: int = 240,
    verify_timeout: int = 120,
    verify_tier2_timeout: int = 30,
    max_iterations: int = 6,
    agent_timeout: int = 240,
) -> PlanAndRunResult:
    """Run the full CHUNK-040 pipeline. See module docstring for the
    sequence. `implementer_repo` is the actual workspace the implementer
    agent will edit (already containing the buggy module, task file, and
    project files) -- untouched by authoring or meta-verification until
    step 5."""
    # Step 1: author, in complete isolation from the implementer's repo.
    authoring_sandbox.mkdir(parents=True, exist_ok=True)
    sandbox_acceptance = authoring_sandbox / acceptance_criteria_path.name
    sandbox_acceptance.write_text(acceptance_criteria_path.read_text())
    subprocess.run(["git", "init", "-q"], cwd=authoring_sandbox, check=True)
    subprocess.run(["git", "add", "-A"], cwd=authoring_sandbox, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Initial state: acceptance criteria only"], cwd=authoring_sandbox, check=True)

    authoring_result = author_property_test(
        repo=authoring_sandbox,
        acceptance_criteria_path=sandbox_acceptance,
        test_filename=test_filename,
        timeout=authoring_timeout,
    )

    if not authoring_result.test_written:
        escalation = write_escalation_brief(
            implementer_repo, "authoring-failed",
            f"No candidate test file was written. Agent status: {authoring_result.status!r}, "
            f"exit_code={authoring_result.agent_exit_code}, timed_out={authoring_result.agent_timed_out}.",
            authoring_result,
        )
        return PlanAndRunResult(
            exit_code=AUTHORING_OR_METAVERIFY_REJECTED_EXIT_CODE,
            stage="authoring-failed",
            authoring_result=authoring_result,
            meta_verify_result=None,
            escalation_path=escalation,
        )

    # Step 3: auto-generate the literal-examples companion, always.
    acceptance_text = acceptance_criteria_path.read_text()
    examples = extract_literal_examples(acceptance_text)
    literal_test_source = generate_literal_example_test(examples, module=module_filename.removesuffix(".py"))

    candidate_test_files = {test_filename: authoring_result.test_source}
    if literal_test_source:
        candidate_test_files["test_literal_examples.py"] = literal_test_source

    # Step 4: meta-verify.
    meta_result = meta_verify(
        fixture_repo=verification_fixture_repo,
        scratch_dir=meta_verify_scratch,
        module_filename=module_filename,
        known_good_source=known_good_source,
        known_bad_source=known_bad_source,
        candidate_test_files=candidate_test_files,
    )

    if not meta_result.sound:
        escalation = write_escalation_brief(
            implementer_repo, "meta-verify-rejected", meta_result.reason, authoring_result,
        )
        return PlanAndRunResult(
            exit_code=AUTHORING_OR_METAVERIFY_REJECTED_EXIT_CODE,
            stage="meta-verify-rejected",
            authoring_result=authoring_result,
            meta_verify_result=meta_result,
            escalation_path=escalation,
        )

    # Step 5: write the meta-verified files into the implementer's real
    # workspace and run the loop with tier 2 wired in.
    #
    # These files must be committed as part of the *baseline* before the
    # loop's first iteration -- not left uncommitted. `phase1/loop.py`'s
    # tamper guard (CHUNK-020) flags any new/changed `test_*.py` file that
    # appears between an iteration's head_before and its result as
    # agent-introduced tampering. If these planning-stage files are left
    # uncommitted, the loop's very first tamper scan sees them as newly
    # added and incorrectly blocks the run (found empirically in this
    # chunk's real-run verification -- see phase4/notes/CHUNK-040.md).
    for filename, content in candidate_test_files.items():
        (implementer_repo / filename).write_text(content)
    subprocess.run(["git", "add", "-A"], cwd=implementer_repo, check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=implementer_repo)
    if diff.returncode != 0:  # non-zero means there ARE staged changes
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": PLANNING_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": PLANNING_AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": PLANNING_AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": PLANNING_AUTHOR_EMAIL,
        }
        subprocess.run(
            ["git", "commit", "-m", "SisyphX Phase 4: add meta-verified tier-2 test files"],
            cwd=implementer_repo, check=True, env=env,
        )

    cmd = [
        sys.executable, str(LOOP),
        "--repo", str(implementer_repo),
        "--task", str(task_path),
        "--verify", verify_cmd,
        "--verify-tier2", meta_result.verify_tier2_command,
        "--verify-tier2-timeout", str(verify_tier2_timeout),
        "--verify-timeout", str(verify_timeout),
        "--max-iterations", str(max_iterations),
        "--agent-timeout", str(agent_timeout),
    ]
    proc = _run_loop_subprocess(cmd, timeout=agent_timeout * max_iterations + 300)

    return PlanAndRunResult(
        exit_code=proc.returncode,
        stage="loop",
        authoring_result=authoring_result,
        meta_verify_result=meta_result,
        escalation_path=None,
    )
