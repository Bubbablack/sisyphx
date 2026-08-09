#!/usr/bin/env python3
"""CHUNK-006: run 5 varied real Devin CLI invocations, each instructed to end
with a SISYPHX_STATUS line, and check the parser handles all 5 real outputs."""
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from status_parser import parse_status  # noqa: E402

SCRATCH = "/Users/stini/Ai_Dev_Home/SisyphX/phase0/scratch"
NOTES = "/Users/stini/Ai_Dev_Home/SisyphX/phase0/notes"

SUFFIX = (
    '\n\nWhen you are finished (whether fully successful, partially '
    'successful, or blocked), end your response with exactly one line in '
    'this exact format: SISYPHX_STATUS: {"outcome": "done|blocked|partial", '
    '"summary": "<one short sentence>"}. Use "done" only if fully '
    'successful, "blocked" if you could not proceed at all, "partial" if you '
    'made some progress but did not finish.'
)

TASKS = [
    ("trivial", "What is 7 times 8? Just state the number."),
    ("write", "Create a file called note_signal1.txt containing the word HELLO, using your write tool."),
    ("impossible", "Read the file /this/path/definitely/does/not/exist/anywhere_xyz.txt and tell me its contents."),
    ("edit", "Create allowed_src/note_signal2.txt with content BASE first, then edit it to append a line MORE_TEXT."),
    ("exec", "Run the shell command `date` using your exec tool and tell me what it printed."),
]

results = []
for name, task in TASKS:
    prompt = task + SUFFIX
    proc = subprocess.run(
        ["devin", "--permission-mode", "bypass", "-p", prompt],
        cwd=SCRATCH, capture_output=True, text=True, timeout=60,
    )
    out_path = os.path.join(NOTES, f"test14_{name}_stdout.txt")
    with open(out_path, "w") as f:
        f.write(proc.stdout)
        if proc.stderr:
            f.write("\n--STDERR--\n" + proc.stderr)

    parsed = parse_status(proc.stdout)
    results.append((name, proc.returncode, parsed))
    print(f"[{name}] exit={proc.returncode} parsed={parsed}")

print("\n=== summary ===")
n_parsed = sum(1 for _, _, p in results if p is not None)
print(f"{n_parsed}/{len(results)} runs produced a parseable status line")
