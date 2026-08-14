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


def test_scan_flags_new_test_file_directly_under_tests_dir_python(real_repo):
    """Regression test (found in CHUNK-044): `tests/*.py` must catch a file
    directly under `tests/`, not just nested subdirectories -- the original
    `tests/**/*.py` pattern required a literal extra `/` and silently never
    matched this case."""
    (real_repo / "tests").mkdir()
    (real_repo / "tests" / "test_example.py").write_text("def test_x(): pass\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is False
    assert "tests/test_example.py" in offending


def test_scan_flags_new_test_file_nested_under_tests_dir_python(real_repo):
    (real_repo / "tests" / "sub").mkdir(parents=True)
    (real_repo / "tests" / "sub" / "test_example.py").write_text("def test_x(): pass\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is False
    assert "tests/sub/test_example.py" in offending


# -- CHUNK-044 (Phase 5): PHP/Laravel/PHPUnit conventions ------------------


def test_scan_flags_phpunit_test_file_edit(real_repo):
    (real_repo / "CalcTest.php").write_text("<?php // a test\n")
    subprocess.run(["git", "add", "-A"], cwd=real_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add php test"], cwd=real_repo, check=True)
    head = _head(real_repo)
    (real_repo / "CalcTest.php").write_text("<?php // tampered\n")
    ok, offending = scan_tamper(real_repo, head)
    assert ok is False
    assert "CalcTest.php" in offending


def test_scan_flags_new_test_file_under_tests_dir_php(real_repo):
    (real_repo / "tests").mkdir()
    (real_repo / "tests" / "ExampleTest.php").write_text("<?php // new test\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is False
    assert "tests/ExampleTest.php" in offending


def test_scan_flags_new_test_file_under_nested_tests_dir_php(real_repo):
    """Matches the real Illima Energy layout: tests/Feature/*.php."""
    (real_repo / "tests" / "Feature").mkdir(parents=True)
    (real_repo / "tests" / "Feature" / "ExampleTest.php").write_text("<?php // new test\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is False
    assert "tests/Feature/ExampleTest.php" in offending


def test_scan_flags_composer_json_edit(real_repo):
    (real_repo / "composer.json").write_text('{"name": "x"}\n')
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is False
    assert "composer.json" in offending


def test_scan_flags_composer_lock_edit(real_repo):
    (real_repo / "composer.lock").write_text("{}\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is False
    assert "composer.lock" in offending


def test_scan_flags_phpunit_xml_edit(real_repo):
    (real_repo / "phpunit.xml").write_text("<phpunit></phpunit>\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is False
    assert "phpunit.xml" in offending


def test_scan_allows_php_source_edits(real_repo):
    """Editing an ordinary PHP source file (not a test, not Composer/PHPUnit
    config) is not flagged -- same policy as Python source edits."""
    (real_repo / "Calc.php").write_text("<?php function add($x) { return $x + 2; }\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo))
    assert ok is True
    assert offending == []


def test_scan_respects_permitted_paths_for_php(real_repo):
    (real_repo / "phpunit.xml").write_text("<phpunit></phpunit>\n")
    ok, offending = scan_tamper(real_repo, _head(real_repo), permitted_paths=("phpunit.xml",))
    assert ok is True
    assert offending == []
