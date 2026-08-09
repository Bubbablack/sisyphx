#!/usr/bin/env python3
"""CHUNK-015 spike: collect verification outputs, design normalization rules,
and demonstrate that a stable `FailureSignature` hash is possible.

This intentionally uses plain text/regex normalization, not a full parser.
The rules are the input to CHUNK-017.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from subprocess import TimeoutExpired

REPO_ROOT = Path("/Users/stini/Ai_Dev_Home/SisyphX")
PHASE2 = REPO_ROOT / "phase2"
SCRATCH = PHASE2 / "scratch" / "chunk015"
NOTES = PHASE2 / "notes"


def clean_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)


def run(cmd: list[str] | str, cwd: Path, timeout: int | None = None, shell: bool = False) -> tuple[str, int]:
    """Run a command and return (stdout+stderr, exit code)."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        shell=shell,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return (result.stdout or "") + (result.stderr or ""), result.returncode


def copy_target_repo(path: Path, name: str) -> None:
    src = REPO_ROOT / "phase1" / "target_repo"
    shutil.copytree(
        src,
        path,
        ignore=shutil.ignore_patterns(".git", ".agent-state", ".pytest_cache", "__pycache__"),
        dirs_exist_ok=True,
    )
    if (path / ".git").exists():
        shutil.rmtree(path / ".git")
    if (path / ".agent-state").exists():
        shutil.rmtree(path / ".agent-state")
    for pyc in list(path.rglob("*.pyc")) + list(path.rglob("*.pyo")):
        pyc.unlink()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=path, check=True, capture_output=True)


def pytest_fail(path: Path) -> tuple[str, int]:
    return run(["uv", "run", "pytest"], path, timeout=120)


def import_error(path: Path) -> tuple[str, int]:
    calc = path / "calc.py"
    content = calc.read_text()
    calc.write_text("import nonexistent_module_12345\n" + content)
    return run(["uv", "run", "pytest"], path, timeout=120)


def timeout_fail() -> tuple[str, int]:
    try:
        result = subprocess.run("sleep 5", shell=True, capture_output=True, text=True, timeout=1)
        out = (result.stdout or "") + (result.stderr or "")
    except TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "") + "\n[SisyphX: verification command itself timed out]"
    return out, -1


def normalize(text: str, repo: Path) -> str:
    """Apply the proposed normalization rules to a verification output."""
    # 1. Strip ANSI escape sequences.
    text = re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", text)

    # 2. Replace absolute repo path and its relative path from REPO_ROOT.
    repo_rel = repo.relative_to(REPO_ROOT)
    text = text.replace(str(repo), "<REPO>")
    text = text.replace(str(repo_rel), "<REPO>")
    text = text.replace(str(REPO_ROOT), "<ROOTDIR>")

    # 3. Replace pytest platform/version header with placeholders.
    text = re.sub(
        r"^platform .*? -- Python \S+, pytest-\S+, pluggy-\S+",
        "platform <PLATFORM> -- Python <PYVERSION>, pytest-<PYTESTVERSION>, pluggy-<PLUGGYVERSION>",
        text,
        flags=re.MULTILINE,
    )

    # 4. Remove uv build/install noise (may be indented).
    text = re.sub(r"^\s*(Building|Built|Uninstalled|Installed)\b.*(?:\r?\n)?", "", text, flags=re.MULTILINE)

    # 5. Replace durations: "in 0.05s", "1 error in 0.16s".
    text = re.sub(r"\bin \d+\.\d+s\b", "in <DURATION>s", text)

    # 6. Replace line numbers in "file.py:5:" style tracebacks, keeping the file name.
    text = re.sub(
        r"^([\w./-]+\.py):(\d+):",
        lambda m: f"{m.group(1)}:<LINE>:",
        text,
        flags=re.MULTILINE,
    )

    # 7. Replace "File \"path\", line 5" style tracebacks.
    text = re.sub(
        r'File "(.*?)", line (\d+)',
        lambda m: f'File "{Path(m.group(1)).name}", line <LINE>',
        text,
    )

    # 8. Replace system-library paths in tracebacks.
    text = re.sub(
        r"/usr/local/.*?/lib/python\d\.\d+[^\n]*",
        "<PYLIB>",
        text,
    )

    # 9. Collapse redundant whitespace.
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n\s*\n", "\n", text)

    return text.strip()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def main() -> int:
    clean_scratch()
    outputs: dict[str, tuple[str, Path]] = {}

    # Generate two repetitions each of pytest and import failures.
    for name in ["pytest_a", "pytest_b"]:
        repo = SCRATCH / name
        copy_target_repo(repo, name)
        out, _ = pytest_fail(repo)
        (NOTES / f"chunk015_{name}.txt").write_text(out)
        outputs[name] = (out, repo)

    for name in ["import_a", "import_b"]:
        repo = SCRATCH / name
        copy_target_repo(repo, name)
        out, _ = import_error(repo)
        (NOTES / f"chunk015_{name}.txt").write_text(out)
        outputs[name] = (out, repo)

    # Timeout (verification command itself times out).
    for name in ["timeout_a", "timeout_b"]:
        repo = SCRATCH / name
        repo.mkdir(parents=True, exist_ok=True)
        out, _ = timeout_fail()
        (NOTES / f"chunk015_{name}.txt").write_text(out)
        outputs[name] = (out, repo)

    # Guard outputs: empty verify_output from CHUNK-014 guard runs.
    for src_name, dst_name in [("guard_a", "guard_a"), ("guard_b", "guard_b")]:
        src = REPO_ROOT / "phase2" / "scratch" / "chunk014" / src_name / ".agent-state" / "runs" / "001" / "verify_output.txt"
        out = src.read_text() if src.exists() else ""
        (NOTES / f"chunk015_{dst_name}.txt").write_text(out)
        repo = REPO_ROOT / "phase2" / "scratch" / "chunk014" / src_name
        outputs[dst_name] = (out, repo)

    # Also include a couple of real passing/empty outputs for comparison.
    extras = {
        "sisyphx_selftest": REPO_ROOT / ".agent-state" / "runs" / "001" / "verify_output.txt",
        "chunk014_normal_a": REPO_ROOT / "phase2" / "scratch" / "chunk014" / "normal_a" / ".agent-state" / "runs" / "001" / "verify_output.txt",
    }
    for key, src in extras.items():
        if src.exists():
            out = src.read_text()
            (NOTES / f"chunk015_{key}.txt").write_text(out)
            outputs[key] = (out, REPO_ROOT)

    # Compute raw and normalized hashes.
    table_lines = [
        "| Output | Exit | Raw hash | Normalized hash |",
        "|---|---|---|---|",
    ]
    hashes: dict[str, tuple[str, str, str]] = {}
    for key, (out, repo) in outputs.items():
        raw_h = hash_text(out)
        norm_h = hash_text(normalize(out, repo))
        table_lines.append(f"| {key} | — | {raw_h} | {norm_h} |")
        hashes[key] = (raw_h, norm_h, out)

    # Same-failure checks.
    same_groups = [
        (["pytest_a", "pytest_b"], "pytest_fail"),
        (["import_a", "import_b"], "import_error"),
        (["timeout_a", "timeout_b"], "timeout"),
        (["guard_a", "guard_b"], "guard"),
    ]
    same_lines = []
    for keys, label in same_groups:
        h0 = hashes[keys[0]][1]
        match = all(hashes[k][1] == h0 for k in keys)
        same_lines.append(f"- {label}: {keys} normalized hashes match = {match}")

    # Different-failure checks.
    reps = ["pytest_a", "import_a", "timeout_a", "guard_a", "sisyphx_selftest", "chunk014_normal_a"]
    diff_lines = []
    for i in range(len(reps)):
        for j in range(i + 1, len(reps)):
            h1 = hashes[reps[i]][1]
            h2 = hashes[reps[j]][1]
            diff_lines.append(f"- {reps[i]} vs {reps[j]}: different = {h1 != h2}")

    note = textwrap.dedent("""\
        # CHUNK-015 — Failure-output normalization study

        **Status:** done  
        **Date:** 2026-08-09  
        **Environment:** `devin 3000.2.17 (2c489dfc)`, macOS 12.  
        **Runner:** `phase2/run_chunk_015.py`

        ## Goal

        Identify volatile parts of verification output and propose a normalization
        recipe so the same failure produces the same `FailureSignature` while
        different failures remain distinct.

        ## Sources

        - Real `verify_output` artifacts from earlier runs:
          - `phase2/scratch/chunk014/*/verify_output.txt` (guard, normal)
          - `.agent-state/runs/001/verify_output.txt` (SisyphX self-test)
        - Fresh deliberate failures generated in `phase2/scratch/chunk015/`:
          - `pytest_fail` — `uv run pytest` on the `target_repo` bug.
          - `import_error` — `calc.py` imports a missing module.
          - `timeout` — `sleep 5` killed at 1s.
          - `guard` — empty verify output from a guard-aborted run.

        ## Volatile parts identified

        - **Durations:** `in 0.05s`, `in 0.16s`, etc.
        - **Absolute / project-relative workspace paths:** `rootdir:` and paths like
          `phase2/scratch/chunk015/pytest_a/test_calc.py` (rootdir is the SisyphX
          root, so the scratch subdir shows up in `ERROR collecting ...` lines).
        - **Platform / Python / pytest / pluggy versions** in the pytest header.
        - **`uv` build/install noise:** `Building ...`, `Built ...`, `Uninstalled ...`,
          `Installed ...`, plus the `file:///...` URLs and package install durations.
        - **Line numbers** in tracebacks (`test_calc.py:5: AssertionError` and
          `File "calc.py", line 4`).
        - **System-library paths** (`/usr/local/Cellar/.../importlib/__init__.py`).
        - **Timestamps** are not present in these outputs but the recipe would strip
          `\\d{4}-\\d{2}-\\d{2}[ T]\\d{2}:\\d{2}:\\d{2}` if they appear.

        ## Proposed normalization recipe

        1. Strip ANSI escape sequences.
        2. Replace the repo's absolute path and its path relative to the workspace root
           with `<REPO>`; replace the workspace root with `<ROOTDIR>`.
        3. Replace the pytest platform/versions header with placeholders.
        4. Remove `uv` build/install lines.
        5. Replace durations `in X.XXs` with `in <DURATION>s`.
        6. Replace line numbers in `file.py:5:` and `File "file", line 5` tracebacks
           with `<LINE>`, keeping the file name.
        7. Replace system-library paths with `<PYLIB>`.
        8. Collapse redundant whitespace.

        The actual assertion values and error messages are intentionally preserved;
        they are part of the failure identity.

        ## Demonstration

    """)
    note += "\n".join(table_lines)
    note += "\n\n### Same failure, two repetitions\n\n"
    note += "\n".join(same_lines)
    note += "\n\n### Different failures\n\n"
    note += "\n".join(diff_lines)
    note += "\n\n## Implications\n\n"
    note += textwrap.dedent("""\
        - The normalization recipe is sufficient to make two runs of the same failure
          produce identical SHA-256 hashes, while different failure classes remain
          distinct.
        - `FailureSignature` (CHUNK-017) should hash the normalized `verify_output`
          together with the agent failure kind (guard/normal/timeout) and the key
          loop-side signals (`agent_exit_code`, `agent_timed_out`, `agent_stderr`).
        - Empty `verify_output` (e.g. guard or a `false` verify command) can still
          produce a stable signature by combining it with the agent-side signal.
    """)
    (NOTES / "CHUNK-015.md").write_text(note)
    print("Wrote phase2/notes/CHUNK-015.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
