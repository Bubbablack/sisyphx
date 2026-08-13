#!/usr/bin/env python3
"""CHUNK-038 tests for the test-authoring step (stubbed subprocess)."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from phase4.test_author import author_property_test, parse_status


def test_parse_status_extracts_last_line():
    stdout = 'blah\nSISYPHX_STATUS: {"outcome": "done", "summary": "wrote it"}'
    assert parse_status(stdout) == '{"outcome": "done", "summary": "wrote it"}'


def test_parse_status_none_when_absent():
    assert parse_status("no status line here") is None


def test_author_property_test_normal_completion_writes_file(tmp_path):
    acceptance = tmp_path / "acceptance_criteria.txt"
    acceptance.write_text("Write a property test for add_one.")

    fake_proc = MagicMock()
    fake_proc.communicate.return_value = ('SISYPHX_STATUS: {"outcome": "done"}', "")
    fake_proc.returncode = 0

    def fake_popen(cmd, cwd, stdout, stderr, text):
        # simulate the agent actually writing the file
        (tmp_path / "test_prop.py").write_text("def test_x(): assert True\n")
        return fake_proc

    with patch("phase4.test_author.subprocess.Popen", side_effect=fake_popen) as mock_popen:
        result = author_property_test(tmp_path, acceptance, "test_prop.py", timeout=30)

    assert result.agent_exit_code == 0
    assert result.agent_timed_out is False
    assert result.test_written is True
    assert result.test_source == "def test_x(): assert True\n"
    assert result.status == '{"outcome": "done"}'

    # confirm the contract from phase0/DEVIN_CLI_CONTRACT.md
    cmd = mock_popen.call_args.args[0]
    assert cmd[:3] == ["devin", "--permission-mode", "bypass"]
    assert "-p" in cmd
    assert "--prompt-file" in cmd
    assert "-c" not in cmd and "-r" not in cmd


def test_author_property_test_no_file_written(tmp_path):
    acceptance = tmp_path / "acceptance_criteria.txt"
    acceptance.write_text("Write a property test.")

    fake_proc = MagicMock()
    fake_proc.communicate.return_value = ('SISYPHX_STATUS: {"outcome": "blocked"}', "")
    fake_proc.returncode = 0

    with patch("phase4.test_author.subprocess.Popen", return_value=fake_proc):
        result = author_property_test(tmp_path, acceptance, "test_prop.py", timeout=30)

    assert result.test_written is False
    assert result.test_source == ""
    assert result.status == '{"outcome": "blocked"}'


def test_author_property_test_timeout_sends_sigterm_then_waits(tmp_path):
    acceptance = tmp_path / "acceptance_criteria.txt"
    acceptance.write_text("Write a property test.")

    fake_proc = MagicMock()
    fake_proc.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd="devin", timeout=30),
        ("partial output", ""),
    ]

    with patch("phase4.test_author.subprocess.Popen", return_value=fake_proc):
        result = author_property_test(tmp_path, acceptance, "test_prop.py", timeout=30)

    assert result.agent_timed_out is True
    fake_proc.terminate.assert_called_once()
    fake_proc.kill.assert_not_called()
    assert result.agent_stdout == "partial output"


def test_author_property_test_writes_prompt_file_from_acceptance_criteria(tmp_path):
    acceptance = tmp_path / "acceptance_criteria.txt"
    acceptance.write_text("Write a property test for double().")

    fake_proc = MagicMock()
    fake_proc.communicate.return_value = ("", "")
    fake_proc.returncode = 0

    with patch("phase4.test_author.subprocess.Popen", return_value=fake_proc) as mock_popen:
        author_property_test(tmp_path, acceptance, "test_prop.py", timeout=30)

    prompt_path = tmp_path / "_authoring_prompt.txt"
    assert prompt_path.exists()
    assert "Write a property test for double()." in prompt_path.read_text()
    assert "SISYPHX_STATUS" in prompt_path.read_text()

    cmd = mock_popen.call_args.args[0]
    assert str(prompt_path) in cmd


def test_author_property_test_is_config_driven_not_hardcoded(tmp_path):
    """A different acceptance-criteria file and a different expected
    output filename both work -- nothing is hardcoded to the CHUNK-034
    fixture's rotate_left scenario."""
    acceptance = tmp_path / "my_task.txt"
    acceptance.write_text("Write a property test for is_even().")

    fake_proc = MagicMock()
    fake_proc.communicate.return_value = ("", "")
    fake_proc.returncode = 0

    def fake_popen(cmd, cwd, stdout, stderr, text):
        (tmp_path / "test_is_even_property.py").write_text("def test_y(): pass\n")
        return fake_proc

    with patch("phase4.test_author.subprocess.Popen", side_effect=fake_popen):
        result = author_property_test(tmp_path, acceptance, "test_is_even_property.py", timeout=30)

    assert result.test_written is True
    assert result.test_path == tmp_path / "test_is_even_property.py"
