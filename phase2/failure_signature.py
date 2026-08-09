#!/usr/bin/env python3
"""CHUNK-017 — FailureSignature hashing.

Implements the normalization and classification rules recorded in CHUNK-015
and CHUNK-014, respectively. Wired into nothing yet; consumed by the loop in
CHUNK-018.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GUARD_SENTINEL = "Error: A tool was rejected by the user"


@dataclass(frozen=True)
class FailureSignature:
    kind: str
    normalized: str
    hash: str


def classify_failure(
    agent_exit_code: int,
    agent_timed_out: bool,
    agent_stderr: str,
    verify_exit_code: int,
) -> str:
    """Classify an iteration outcome using the detection rule from CHUNK-014.

    Returns one of: 'guard', 'agent-timeout', 'verify-timeout', 'verify-fail',
    'verify-pass', 'agent-error'.
    """
    if agent_timed_out:
        return "agent-timeout"
    if (
        agent_exit_code == 1
        and agent_stderr
        and GUARD_SENTINEL in agent_stderr
    ):
        return "guard"
    if agent_exit_code != 0:
        return "agent-error"
    if verify_exit_code == 0:
        return "verify-pass"
    if verify_exit_code == -1:
        return "verify-timeout"
    return "verify-fail"


def normalize_verify_output(
    text: str,
    repo_path: Path | None = None,
    repo_root: Path | None = None,
) -> str:
    """Apply the CHUNK-015 normalization recipe to a verification output.

    The normalized form is what goes into the stable hash. Volatile parts
    removed/replaced include durations, absolute workspace paths, line numbers,
    pytest versions, uv build noise, and system-library paths.
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    if repo_path is None:
        repo_path = repo_root

    # 1. Strip ANSI escape sequences.
    text = re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", text)

    # 2. Replace repo paths.
    try:
        repo_rel = repo_path.relative_to(repo_root)
    except ValueError:
        repo_rel = repo_path
    text = text.replace(str(repo_path), "<REPO>")
    text = text.replace(str(repo_rel), "<REPO>")
    text = text.replace(str(repo_root), "<ROOTDIR>")

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

    # 8. Replace system-library paths.
    text = re.sub(
        r"/usr/local/.*?/lib/python\d\.\d+[^\n]*",
        "<PYLIB>",
        text,
    )

    # 9. Collapse redundant whitespace.
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n\s*\n", "\n", text)

    return text.strip()


def _identity(kind: str, normalized: str, agent_exit_code: int, agent_stderr: str, verify_exit_code: int) -> str:
    """Compose the identity string that is hashed.

    For agent-side failures (guard, timeout) the verify output is not the cause,
    so it is ignored. For verify-fail the normalized output is the core signal.
    For agent-error the stderr is the core signal.
    """
    parts = [kind]
    if kind in ("guard", "agent-error"):
        parts.append(str(agent_exit_code))
        parts.append(agent_stderr.strip())
    if kind in ("agent-timeout", "verify-timeout"):
        # The source of the timeout is part of the identity, but the raw exit
        # code/signal is not, because it is platform- and kill-strategy-dependent.
        if kind == "agent-timeout":
            parts.append("agent")
        else:
            parts.append("verify")
    if kind in ("verify-fail", "verify-pass"):
        parts.append(normalized)
    return "\n".join(parts)


def failure_signature(
    verify_output: str,
    agent_exit_code: int,
    agent_timed_out: bool,
    agent_stderr: str,
    verify_exit_code: int = -1,
    repo_path: Path | None = None,
    repo_root: Path | None = None,
) -> FailureSignature:
    """Build a stable FailureSignature from the loop-side signals.

    The signature is stable for the same failure and distinct for different
    failure classes.
    """
    kind = classify_failure(agent_exit_code, agent_timed_out, agent_stderr, verify_exit_code)
    normalized = normalize_verify_output(verify_output, repo_path, repo_root)
    identity = _identity(kind, normalized, agent_exit_code, agent_stderr, verify_exit_code)
    digest = hashlib.sha256(identity.encode()).hexdigest()[:16]
    return FailureSignature(kind=kind, normalized=normalized, hash=digest)
