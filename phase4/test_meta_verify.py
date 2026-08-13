#!/usr/bin/env python3
"""CHUNK-039 tests for per-individual-check meta-verification."""
from __future__ import annotations

from pathlib import Path

import pytest

from phase4.meta_verify import meta_verify

PYPROJECT = '''\
[project]
name = "meta-verify-test-fixture"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[dependency-groups]
dev = ["pytest>=8.0.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
include = ["*.py"]

[tool.pytest.ini_options]
testpaths = []
'''

GOOD_MODULE = "def add_one(x):\n    return x + 1\n"
BAD_MODULE = "def add_one(x):\n    return x\n"  # the original bug: forgets +1

SOUND_TEST = '''\
def test_add_one_normal():
    from module import add_one
    assert add_one(5) == 6
'''

BROKEN_TEST = '''\
def test_never_passes():
    assert False, "this check is broken regardless of the implementation"
'''

NON_DISCRIMINATING_TEST = '''\
def test_trivially_true():
    assert True
'''


@pytest.fixture
def fixture_repo(tmp_path):
    repo = tmp_path / "fixture"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(PYPROJECT)
    return repo


def test_sound_candidate_produces_discriminating_command(fixture_repo, tmp_path):
    result = meta_verify(
        fixture_repo=fixture_repo,
        scratch_dir=tmp_path / "scratch",
        module_filename="module.py",
        known_good_source=GOOD_MODULE,
        known_bad_source=BAD_MODULE,
        candidate_test_files={"test_candidate.py": SOUND_TEST},
    )
    assert result.sound is True
    assert result.valid_checks == ("test_candidate.py::test_add_one_normal",)
    assert result.discarded_checks == ()
    assert result.discriminating_checks == ("test_candidate.py::test_add_one_normal",)
    assert result.verify_tier2_command is not None
    assert "test_candidate.py" in result.verify_tier2_command
    assert "--deselect" not in result.verify_tier2_command


def test_broken_check_is_discarded_not_blocking(fixture_repo, tmp_path):
    """CHUNK-036/037's core finding: a check that fails against the
    known-good reference must be discarded, not treated as a real
    failure."""
    result = meta_verify(
        fixture_repo=fixture_repo,
        scratch_dir=tmp_path / "scratch",
        module_filename="module.py",
        known_good_source=GOOD_MODULE,
        known_bad_source=BAD_MODULE,
        candidate_test_files={"test_candidate.py": SOUND_TEST, "test_broken.py": BROKEN_TEST},
    )
    assert result.sound is True
    assert "test_broken.py::test_never_passes" in result.discarded_checks
    assert "test_candidate.py::test_add_one_normal" in result.valid_checks
    # the deselect flag must exclude the broken check from the resulting command
    assert '--deselect "test_broken.py::test_never_passes"' in result.verify_tier2_command


def test_all_checks_broken_is_rejected_outright(fixture_repo, tmp_path):
    result = meta_verify(
        fixture_repo=fixture_repo,
        scratch_dir=tmp_path / "scratch",
        module_filename="module.py",
        known_good_source=GOOD_MODULE,
        known_bad_source=BAD_MODULE,
        candidate_test_files={"test_broken.py": BROKEN_TEST},
    )
    assert result.sound is False
    assert result.valid_checks == ()
    assert result.verify_tier2_command is None
    assert "nothing left to verify" in result.reason


def test_non_discriminating_checks_are_rejected(fixture_repo, tmp_path):
    """A check that passes against both the known-good AND known-bad
    reference provides no signal and must not be trusted as sound."""
    result = meta_verify(
        fixture_repo=fixture_repo,
        scratch_dir=tmp_path / "scratch",
        module_filename="module.py",
        known_good_source=GOOD_MODULE,
        known_bad_source=BAD_MODULE,
        candidate_test_files={"test_candidate.py": NON_DISCRIMINATING_TEST},
    )
    assert result.sound is False
    assert result.discriminating_checks == ()
    assert result.verify_tier2_command is None


def test_mix_of_discriminating_and_non_discriminating_checks(fixture_repo, tmp_path):
    """A candidate with one real, discriminating check and one
    non-discriminating (but not broken) check is still sound -- the
    non-discriminating one simply contributes nothing, it isn't rejected
    as broken like a health-check failure would be."""
    result = meta_verify(
        fixture_repo=fixture_repo,
        scratch_dir=tmp_path / "scratch",
        module_filename="module.py",
        known_good_source=GOOD_MODULE,
        known_bad_source=BAD_MODULE,
        candidate_test_files={"test_candidate.py": SOUND_TEST, "test_trivial.py": NON_DISCRIMINATING_TEST},
    )
    assert result.sound is True
    assert "test_trivial.py::test_trivially_true" in result.valid_checks
    assert "test_trivial.py::test_trivially_true" not in result.discriminating_checks
    assert "test_candidate.py::test_add_one_normal" in result.discriminating_checks
