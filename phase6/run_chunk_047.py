#!/usr/bin/env python3
"""CHUNK-047 -- spike: confirm a `REVIEW:` marker detection approach.

Per PLAN.md's Phase 6 pre-scoped candidates, this is explicitly NOT
diff-based (see the module docstring rationale below) -- it scans real
current-state files directly, exactly once, as a startup precondition.

This script is throwaway spike code. If CHUNK-047's approach is confirmed,
CHUNK-048 promotes the winning detection function into
`phase2/review_marker_check.py` and wires it into `phase1/loop.py`.

Usage:
    python3 phase6/run_chunk_047.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Deliberately restricted to source-code-shaped file extensions. This is
# the single biggest finding of this spike: a naive repo-wide text grep for
# "REVIEW:" hits real, permanent false positives in THIS repo today --
# PLAN.md, AGENTS.md, and experiments/planner/BRIEF.md all discuss the
# `REVIEW:` convention itself in prose/fenced code examples. Restricting to
# code file extensions (never .md) sidesteps that whole class of false
# positive for free, without needing a markdown-fence parser.
CODE_EXTENSIONS: tuple[str, ...] = (
    ".py", ".php", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".sh", ".yml", ".yaml",
)

# A marker only counts if a recognized comment-leader token is immediately
# (modulo whitespace) followed by "REVIEW:" on the same line -- this is what
# lets "beside the relevant line" trailing-comment style (a PHP `//`
# end-of-line comment naming the tag) match, while plain prose mentioning
# the tag inside a string/docstring (no comment leader immediately before
# it) does not. It is a per-line heuristic, not a real parser -- a literal
# occurrence of the tag placed immediately after a real comment leader on
# the same line would still slip through undetected as a false negative;
# documented as a known limitation below, not solved here.
#
# NOTE: an earlier draft of this exact comment discussed the trailing-
# comment example using the literal tag syntax and tripped this file's own
# check when run against the real repo below -- a second, real instance of
# the same false-positive class AGENTS.md/PLAN.md hit in prose, but this
# time inside a code file where the .md extension filter doesn't help.
# Recorded in phase6/notes/CHUNK-047.md as a known limitation.
_MARKER_RE = re.compile(r"(?:#|//|/\*|<!--)\s*REVIEW:")

# Directories never worth descending into for this kind of scan.
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".agent-state"}


def find_review_markers(root: Path) -> list[tuple[Path, int, str]]:
    """Scan `root` for unresolved `REVIEW:` markers in source-code files.
    Returns a list of (path, line_number, line_text) for every match."""
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


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures_chunk047"

# Expected outcome per fixture, hand-built to cover both true positives and
# the specific false-positive shapes CHUNK-047's acceptance criteria calls
# out (a REVIEW: marker inside a string/docstring; a REVIEW: mention in
# prose/doc context).
EXPECTED: dict[str, int] = {
    "clean": 0,
    "marker_comment": 1,
    "marker_trailing": 1,
    "marker_in_string": 0,
    "doc_mention": 0,
}


def main() -> int:
    print("=== CHUNK-047 spike: fixture-by-fixture results ===\n")
    all_ok = True
    for name, expected_count in EXPECTED.items():
        fixture_dir = FIXTURES_DIR / name
        hits = find_review_markers(fixture_dir)
        ok = len(hits) == expected_count
        all_ok = all_ok and ok
        status = "OK" if ok else "MISMATCH"
        print(f"[{status}] {name}: expected {expected_count}, got {len(hits)}")
        for path, lineno, line in hits:
            print(f"    {path.relative_to(FIXTURES_DIR)}:{lineno}: {line}")
    print()

    print("=== Real-repo scan (repo-wide, source-code extensions only) ===\n")
    repo_hits = [
        (p, ln, txt)
        for (p, ln, txt) in find_review_markers(REPO_ROOT)
        if FIXTURES_DIR not in p.parents
    ]
    if repo_hits:
        for path, lineno, line in repo_hits:
            print(f"    {path.relative_to(REPO_ROOT)}:{lineno}: {line}")
    else:
        print("    (none -- confirms PLAN.md/AGENTS.md/BRIEF.md's REVIEW: "
              "mentions are correctly excluded by the .md extension filter)")

    print()
    print("=== VERDICT ===")
    print("all fixtures matched expectation" if all_ok else "one or more fixtures MISMATCHED -- see above")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
