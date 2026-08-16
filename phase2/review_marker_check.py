#!/usr/bin/env python3
"""CHUNK-048 -- review-marker startup precondition.

Promotes CHUNK-047's confirmed spike (`phase6/run_chunk_047.py`) into a
real module. Detects unresolved `REVIEW:` markers (the manual convention
documented in `AGENTS.md`) so `loop.py` can refuse to *begin* a run while
any are outstanding, rather than trying to police them per-iteration.

Why a one-shot startup precondition and not a per-iteration guard (see
PLAN.md's Phase 6 design note, dated 2026-08-15): `loop.py` commits every
iteration regardless of outcome (CHUNK-010), so a diff-based check against
`head_before` would silently stop seeing a marker left in an earlier
iteration once the diff base moved past it -- tamper_guard.py never hits
this because a tamper trip is a hard stop with no further iterations. This
check instead scans real current-state files directly, once, before
iteration 1 -- the same pattern as CHUNK-045's `--repo`-toplevel check.

Why repo-wide, not `permitted_paths`-scoped (CHUNK-047's decision): the
`REVIEW:` convention is a human-driven signal that some concern exists
*somewhere* in the codebase; scoping the check to only the current chunk's
`permitted_paths` would let the loop start new automated work while a
flagged concern sits unresolved just outside that scope, defeating the
point of a fail-fast precondition.
"""
from __future__ import annotations

import re
from pathlib import Path

# Deliberately restricted to source-code-shaped file extensions, never
# `.md`. CHUNK-047's spike found this repo's own `PLAN.md`/`AGENTS.md`/
# `experiments/planner/BRIEF.md` discuss the `REVIEW:` convention itself in
# prose and fenced code-block examples -- a naive repo-wide text grep would
# permanently false-positive on this repo's own documentation.
CODE_EXTENSIONS: tuple[str, ...] = (
    ".py", ".php", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".sh", ".yml", ".yaml",
)

# A marker only counts if a recognized comment-leader token is immediately
# (modulo whitespace) followed by the tag on the same line -- this is what
# lets a trailing end-of-line comment ("beside the relevant line" per
# `AGENTS.md`) match, while the tag appearing in ordinary string/docstring
# prose (no comment leader immediately before it) does not. Known, accepted
# limitation (CHUNK-047): a per-line regex, not a real parser -- a string
# literal containing a comment-leader token immediately followed by the tag
# on the same physical line would still match; a code comment discussing
# the tag by name (not as a real marker) will also false-positive.
_MARKER_RE = re.compile(r"(?:#|//|/\*|<!--)\s*REVIEW:")

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".agent-state"}


def find_review_markers(root: Path) -> list[tuple[Path, int, str]]:
    """Scan `root` for unresolved `REVIEW:` markers in source-code files.
    Returns a list of (path, line_number, line_text) for every match, in a
    stable (sorted-by-path) order."""
    hits: list[tuple[Path, int, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in CODE_EXTENSIONS:
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _MARKER_RE.search(line):
                hits.append((path, lineno, line.strip()))
    return hits


def check_review_markers(repo: Path) -> tuple[bool, list[str]]:
    """Repo-wide precondition check. Returns (ok, offending) where
    `offending` is a list of human-readable `"relative/path:line: text"`
    strings, empty when `ok` is True."""
    offending = [
        f"{path.relative_to(repo)}:{lineno}: {text}"
        for path, lineno, text in find_review_markers(repo)
    ]
    return not offending, offending
