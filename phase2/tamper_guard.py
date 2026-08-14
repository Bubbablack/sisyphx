#!/usr/bin/env python3
"""CHUNK-020 — post-iteration test-tamper diff scanner.

Detects edits to protected paths (tests, verify config, CI, lock files) after
an agent turn. Wired into the loop in CHUNK-020.

CHUNK-044 (Phase 5) widened `PROTECTED_PATTERNS` to also recognize
PHPUnit/Composer/Laravel conventions, per Design decision #3
(verification adapters configurable per-project, not hardcoded to one
language). This list already mixed ecosystem-agnostic entries (`Makefile`)
with Python-specific ones (`pyproject.toml`); adding the PHP equivalents is
a widening of the same list, not a new per-project configuration
mechanism -- `permitted_paths` remains the per-chunk override point.
"""
from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

# Paths the agent is never allowed to touch unless explicitly allowlisted.
# Keep globs in gitignore/fnmatch syntax.
PROTECTED_PATTERNS: tuple[str, ...] = (
    # test files (Python)
    "test_*.py",
    "*_test.py",
    "tests/*.py",  # fnmatch's `*` already crosses `/`, so this also
                   # matches nested paths like tests/sub/test_foo.py --
                   # `tests/**/*.py` looks more explicit but actually
                   # requires a literal extra `/` and never matches files
                   # directly under tests/ (found empirically in CHUNK-044
                   # while adding PHP coverage; the bug predates PHP and
                   # applied to Python too, just untested until now).
    "tests.py",
    # test files (PHP/PHPUnit -- CHUNK-044)
    "*Test.php",
    "tests/*.php",
    # verification config (Python)
    "pyproject.toml",
    "pytest.ini",
    "conftest.py",
    "setup.cfg",
    "tox.ini",
    "noxfile.py",
    "setup.py",
    # verification config (PHP/Composer/Laravel -- CHUNK-044)
    "composer.json",
    "composer.lock",
    "phpunit.xml",
    "phpunit.xml.dist",
    # CI / verify command config
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "Makefile",
    "justfile",
    "tasks.py",
    # dependencies / lock files
    "uv.lock",
    "requirements*.txt",
    "Pipfile.lock",
    "poetry.lock",
    # coverage / quality thresholds
    ".coveragerc",
    "codecov.yml",
    ".codecov.yml",
    # loop state (agent should not edit)
    ".agent-state/**",
    ".devin/hooks.v1.json",
)

# Paths the loop itself owns and may change. These are excluded from tamper
# reports because the agent did not create them.
LOOP_MANAGED_PATTERNS: tuple[str, ...] = (
    ".gitignore",
    ".agent-state/**",
)


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    for pat in patterns:
        if pat.endswith("/**"):
            dir_pat = pat[:-3]
            if fnmatch.fnmatch(path, pat) or path.startswith(dir_pat + "/") or path == dir_pat:
                return True
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path, pat.lstrip("./")):
            return True
    return False


def _changed_files(repo: Path, base: str) -> list[str]:
    """Return all changed/new/removed file paths between `base` and the
    current working tree + index."""
    names: list[str] = []

    # Staged and unstaged diffs relative to base.
    for args in (
        ["git", "diff", "--name-only", base, "--"],
        ["git", "diff", "--cached", "--name-only", base, "--"],
    ):
        proc = subprocess.run(args, cwd=repo, capture_output=True, text=True)
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if line and line not in names:
                names.append(line)

    # Untracked files (the agent may have created new tests).
    #
    # CHUNK-044 (Phase 5) found a real bug here: without
    # `--untracked-files=all`, git collapses an entirely new, untracked
    # directory into a single line for the directory itself (e.g. `?? tests/`)
    # instead of listing the files inside it -- so a new test file added
    # inside a brand-new `tests/` directory was silently invisible to every
    # protected-pattern check. Never caught before because every existing
    # test happened to add new test files at the repo root, not inside a new
    # subdirectory.
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    for line in (status.stdout or "").splitlines():
        if not line:
            continue
        state = line[:2]
        path = line[3:].strip()
        # Ignore deleted files unless they are protected (rare, but include anyway).
        if "D" in state:
            continue
        if path and path not in names:
            names.append(path)

    return names


def scan_tamper(
    repo: Path,
    base_ref: str,
    permitted_paths: tuple[str, ...] = (),
) -> tuple[bool, list[str]]:
    """Scan the working tree for edits to protected paths.

    Returns (ok, offending_paths). `permitted_paths` is a list of fnmatch globs
    that suppress the flag for a particular path (e.g. the task explicitly asks
    the agent to add a test).
    """
    offending: list[str] = []
    for path in _changed_files(repo, base_ref):
        if _matches(path, LOOP_MANAGED_PATTERNS):
            continue
        if _matches(path, permitted_paths):
            continue
        if _matches(path, PROTECTED_PATTERNS):
            offending.append(path)
    return not offending, offending
