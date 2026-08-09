#!/usr/bin/env python3
"""Throwaway probe for CHUNK-003.

Question: does subprocess.run(timeout=N) cleanly kill a slow `devin -p` call,
including anything IT spawned (e.g. a shell command it started)? And what
state does the workspace end up in?

Usage:
    python3 timeout_probe.py plain      # plain subprocess.run(timeout=)
    python3 timeout_probe.py pgroup     # Popen + start_new_session + killpg
"""
import os
import signal
import subprocess
import sys
import time

SCRATCH = "/Users/stini/Ai_Dev_Home/SisyphX/phase0/scratch"
SLOW_PATH = os.path.join(SCRATCH, "slow.txt")
SLEEP_SECONDS = 60
TIMEOUT_SECONDS = 20

PROMPT = (
    "Using your write tool, create a file called slow.txt containing exactly "
    "the text PART1 (no other text). Then run the shell command `sleep "
    f"{SLEEP_SECONDS}` and wait for it to fully complete before continuing. "
    "After that finishes, append PART2 on a new line to slow.txt. "
    "Then reply with exactly: SLOW_DONE"
)


def orphan_check(label: str) -> None:
    time.sleep(2)  # give the OS a moment to reap
    for pattern in ["sleep 60", "permission-mode bypass"]:
        ps = subprocess.run(
            ["pgrep", "-fl", pattern], capture_output=True, text=True
        )
        print(f"[{label}] pgrep '{pattern}':", ps.stdout.strip() or "(none found)")


def check_workspace() -> None:
    print("slow.txt exists:", os.path.exists(SLOW_PATH))
    if os.path.exists(SLOW_PATH):
        print("slow.txt contents:", repr(open(SLOW_PATH).read()))


def run_plain() -> None:
    if os.path.exists(SLOW_PATH):
        os.remove(SLOW_PATH)
    cmd = ["devin", "--permission-mode", "bypass", "-p", PROMPT]
    start = time.time()
    try:
        result = subprocess.run(
            cmd, cwd=SCRATCH, timeout=TIMEOUT_SECONDS,
            capture_output=True, text=True,
        )
        print(f"Completed WITHOUT timing out in {time.time()-start:.1f}s, "
              f"exit={result.returncode}")
    except subprocess.TimeoutExpired:
        print(f"TimeoutExpired after {time.time()-start:.1f}s "
              f"(requested timeout={TIMEOUT_SECONDS}s) -- process.kill() sent "
              f"to the direct child by subprocess.run internals")
    orphan_check("plain")
    check_workspace()


def run_pgroup() -> None:
    if os.path.exists(SLOW_PATH):
        os.remove(SLOW_PATH)
    cmd = ["devin", "--permission-mode", "bypass", "-p", PROMPT]
    start = time.time()
    proc = subprocess.Popen(
        cmd, cwd=SCRATCH, start_new_session=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=TIMEOUT_SECONDS)
        print(f"Completed WITHOUT timing out in {time.time()-start:.1f}s, "
              f"exit={proc.returncode}")
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        pgid = os.getpgid(proc.pid)
        print(f"TimeoutExpired after {elapsed:.1f}s -- killing whole process "
              f"group {pgid} with SIGKILL")
        os.killpg(pgid, signal.SIGKILL)
        proc.wait(timeout=5)
    orphan_check("pgroup")
    check_workspace()


def run_graceful() -> None:
    """SIGTERM the direct child first, give it a grace period to shut down
    (and hopefully reap its own children), then SIGKILL if still alive."""
    if os.path.exists(SLOW_PATH):
        os.remove(SLOW_PATH)
    cmd = ["devin", "--permission-mode", "bypass", "-p", PROMPT]
    start = time.time()
    proc = subprocess.Popen(
        cmd, cwd=SCRATCH,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=TIMEOUT_SECONDS)
        print(f"Completed WITHOUT timing out in {time.time()-start:.1f}s, "
              f"exit={proc.returncode}")
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"TimeoutExpired after {elapsed:.1f}s -- sending SIGTERM to pid "
              f"{proc.pid}, grace period 5s")
        proc.terminate()  # SIGTERM
        try:
            proc.wait(timeout=5)
            print(f"Process exited gracefully after SIGTERM, "
                  f"returncode={proc.returncode}")
        except subprocess.TimeoutExpired:
            print("Still alive after grace period -- SIGKILL")
            proc.kill()
            proc.wait(timeout=5)
    orphan_check("graceful")
    check_workspace()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "plain"
    if mode == "plain":
        run_plain()
    elif mode == "pgroup":
        run_pgroup()
    elif mode == "graceful":
        run_graceful()
    else:
        print("usage: timeout_probe.py [plain|pgroup|graceful]")
        sys.exit(2)
