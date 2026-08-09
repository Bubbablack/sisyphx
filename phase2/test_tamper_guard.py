#!/usr/bin/env python3
"""CHUNK-020 tests for the test-tamper diff scanner."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from phase2.tamper_guard import scan_tamper


@pytest.fixture
def real_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "calc.py").write_text("def add(x): return x + 1\n")
    (tmp_path / "test_calc.py").write_text("def test_add(): assert add(1) == 2\n")
    (tmp_path / "README.md").write_text("# calc\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()


def test_scan_allows_source_edits(real_repo):
    (real_repo / "calc.py").write_text("def add(x): return x + 2\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is True
    assert offending == []


def test_scan_flags_test_file_edit(real_repo):
    (real_repo / "test_calc.py").write_text("def test_add(): assert add(1) == 3\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is False
    assert "test_calc.py" in offending


def test_scan_flags_new_test_file(real_repo):
    (real_repo / "test_new.py").write_text("def test_new(): pass\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is False
    assert "test_new.py" in offending


def test_scan_flags_pyproject_edit(real_repo):
    (real_repo / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is False
    assert "pyproject.toml" in offending


def test_scan_ignores_loop_managed_gitignore(real_repo):
    (real_repo / ".gitignore").write_text(".agent-state/\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is True


def test_scan_respects_permitted_paths(real_repo):
    (real_repo / "test_calc.py").write_text("def test_add(): assert add(1) == 3\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo), permitted_paths=("test_calc.py",))
    assert ok is True
    assert offending == []
