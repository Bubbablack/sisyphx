#!/usr/bin/env python3
"""CHUNK-048 tests for the review-marker startup precondition.

Reuses the five fixture shapes CHUNK-047's spike confirmed
(`phase6/notes/CHUNK-047.md`): clean, genuine-comment-marker,
genuine-trailing-marker, string-false-positive, doc-false-positive.
"""
from __future__ import annotations

from pathlib import Path

from phase2.review_marker_check import check_review_markers, find_review_markers


def test_clean_repo_has_no_markers(tmp_path):
    (tmp_path / "app.py").write_text(
        "def add(a, b):\n    # a normal comment, nothing to flag\n    return a + b\n"
    )
    ok, offending = check_review_markers(tmp_path)
    assert ok is True
    assert offending == []


def test_flags_genuine_comment_marker(tmp_path):
    (tmp_path / "app.py").write_text(
        "def retry_call():\n"
        "    # REVIEW: this retry loop has no backoff, can hammer the API -- fix?\n"
        "    pass\n"
    )
    ok, offending = check_review_markers(tmp_path)
    assert ok is False
    assert len(offending) == 1
    assert offending[0].startswith("app.py:2:")


def test_flags_genuine_trailing_marker_php(tmp_path):
    (tmp_path / "service.php").write_text(
        "<?php\n"
        "$result = $gateway->charge($amount); // REVIEW: no idempotency key\n"
    )
    ok, offending = check_review_markers(tmp_path)
    assert ok is False
    assert "service.php:2:" in offending[0]


def test_does_not_flag_marker_inside_string_or_docstring(tmp_path):
    (tmp_path / "app.py").write_text(
        '"""Docstring that mentions REVIEW: as ordinary prose."""\n'
        'TEMPLATE = "Please add a REVIEW: note if you have concerns."\n'
    )
    ok, offending = check_review_markers(tmp_path)
    assert ok is True
    assert offending == []


def test_does_not_flag_markdown_docs(tmp_path):
    (tmp_path / "NOTES.md").write_text(
        "When reviewing code, leave feedback using a `REVIEW:` tag, e.g.:\n\n"
        "```python\n# REVIEW: this retry loop has no backoff -- fix?\ndef f(): ...\n```\n"
    )
    ok, offending = check_review_markers(tmp_path)
    assert ok is True
    assert offending == []


def test_ignores_git_and_agent_state_dirs(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hooks.py").write_text("# REVIEW: fake, inside .git\n")
    (tmp_path / ".agent-state").mkdir()
    (tmp_path / ".agent-state" / "scratch.py").write_text("# REVIEW: fake, inside .agent-state\n")
    ok, offending = check_review_markers(tmp_path)
    assert ok is True
    assert offending == []


def test_find_review_markers_returns_path_line_text(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n# REVIEW: check this\ny = 2\n")
    hits = find_review_markers(tmp_path)
    assert len(hits) == 1
    path, lineno, text = hits[0]
    assert path == tmp_path / "app.py"
    assert lineno == 2
    assert "REVIEW: check this" in text


def test_reports_multiple_offenders_across_files(tmp_path):
    (tmp_path / "a.py").write_text("# REVIEW: first\n")
    (tmp_path / "b.php").write_text("<?php // REVIEW: second\n")
    ok, offending = check_review_markers(tmp_path)
    assert ok is False
    assert len(offending) == 2
