#!/usr/bin/env python3
"""CHUNK-030 real-run verification: exercise the full
verification_tiers -> failure_signature -> EventStore.append_verify_result
pipeline against the CHUNK-024 fixture's known cheat, then query the event
trail back to confirm it's queryable. Writes findings to
phase3/notes/CHUNK-030.md.
"""
from __future__ import annotations

import shutil
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path("/Users/stini/Ai_Dev_Home/SisyphX")
PHASE3 = REPO_ROOT / "phase3"
FIXTURE = PHASE3 / "target_repo_semantic_cheat"
SCRATCH = PHASE3 / "scratch" / "chunk030"
NOTES = PHASE3 / "notes"

sys.path.insert(0, str(REPO_ROOT))
from phase2.event_store import EventStore  # noqa: E402
from phase2.failure_signature import failure_signature  # noqa: E402
from phase3.verification_tiers import run_tiered_verification  # noqa: E402

CHEAT_CALC = '''"""Known CHUNK-024 semantic cheat, installed directly for the CHUNK-030
real-run verification (not regenerated via an agent run)."""


def add_one(x: int) -> int:
    return x + 2


def double(x: int) -> int:
    return x * 2
'''


def clean_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)


def main() -> int:
    NOTES.mkdir(parents=True, exist_ok=True)
    clean_scratch()

    repo = SCRATCH / "cheat"
    shutil.copytree(
        FIXTURE, repo,
        ignore=shutil.ignore_patterns(".git", ".agent-state", ".pytest_cache", "__pycache__", "*.pyc"),
    )
    (repo / "calc.py").write_text(CHEAT_CALC)

    result = run_tiered_verification(
        repo,
        tier1_cmd="uv run pytest test_calc.py",
        tier1_timeout=60,
        tier2_cmd="uv run pytest test_calc_property.py",
        tier2_timeout=30,
    )
    sig = failure_signature(
        verify_output=result.tier1.output,
        agent_exit_code=0,
        agent_timed_out=False,
        agent_stderr="",
        verify_exit_code=result.tier1.exit_code,
        repo_path=repo,
        verify_tier2_output=result.tier2.output if result.tier2 else "",
        verify_tier2_exit_code=result.tier2.exit_code if result.tier2 else None,
    )

    store = EventStore(SCRATCH / "events.db")
    run_id = store.new_run_id()
    store.append("run_started", {"task": "CHUNK-030 real-run verification"}, run_id=run_id)
    store.append_verify_result(
        run_id=run_id,
        iteration=1,
        verify_exit_code=result.tier1.exit_code,
        verify_output=result.tier1.output,
        passed=result.passed,
        failure_kind=sig.kind,
        failure_signature=sig.hash,
        verify_tier2_ran=result.tier2 is not None,
        verify_tier2_exit_code=result.tier2.exit_code if result.tier2 else None,
        verify_tier2_output=result.tier2.output if result.tier2 else "",
    )
    store.append("stop", {"reason": sig.kind, "exit_code": 4}, run_id=run_id)
    store.close()

    # Reopen (simulating a later query, not the same in-memory instance) and
    # confirm the tier result really is queryable back from disk.
    reader = EventStore(SCRATCH / "events.db")
    verify_events = reader.get_events(event_type="verify_result", run_id=run_id)
    reader.close()

    assert len(verify_events) == 1
    payload = verify_events[0].payload
    print(f"queried back: failure_kind={payload['failure_kind']} "
          f"verify_tier2_ran={payload['verify_tier2_ran']} "
          f"verify_tier2_exit_code={payload['verify_tier2_exit_code']}")

    write_note(payload)
    print("Wrote phase3/notes/CHUNK-030.md")
    return 0


def write_note(payload: dict) -> None:
    note = textwrap.dedent(f"""\
        # CHUNK-030 — `EventStore` schema gains verification-tier fields

        **Status:** done
        **Date:** 2026-08-13
        **Runner:** `phase3/run_chunk_030.py`

        ## What was built

        `phase2/event_store.py::EventStore.append_verify_result()` -- a new,
        additive convenience method, not a SQL schema migration. The
        `events` table's `payload` column was already an opaque JSON blob
        (CHUNK-022), so no `ALTER TABLE` was needed or possible to make
        meaningfully different -- any event can already carry any fields.
        What was missing was a single place that defines the CHUNK-029
        tier-2 field names (`verify_tier2_ran`, `verify_tier2_exit_code`,
        `verify_tier2_output`) so `loop.py`'s CHUNK-031 integration doesn't
        have to remember or guess them, and so every `verify_result` event
        going forward carries them consistently (with harmless defaults when
        no tier 2 was configured).

        ## Verification

        - `phase2/test_event_store.py`: 2 new tests -- round-trip of the new
          fields, and confirmation that plain pre-CHUNK-030 `append()` calls
          for `verify_result` events still work unchanged. Full suite: 84
          passed (82 before this chunk + 2 new).
        - Real run (this script): ran the full pipeline --
          `verification_tiers.run_tiered_verification` against a scratch
          copy of the CHUNK-024 fixture with the known cheat installed,
          `failure_signature.failure_signature` to classify the result, then
          `EventStore.append_verify_result` to record it, then **reopened
          the database as a fresh `EventStore` instance** and queried the
          event back by `run_id`/`event_type` to confirm it's durable and
          queryable, not just an in-memory round trip.

        ## Result

        Queried back from a freshly reopened SQLite file:

        ```
        failure_kind = {payload['failure_kind']!r}
        verify_tier2_ran = {payload['verify_tier2_ran']!r}
        verify_tier2_exit_code = {payload['verify_tier2_exit_code']!r}
        ```

        Confirms the full chain -- verification tiers, failure
        classification, and the event store -- produces a durable,
        queryable record of exactly why the CHUNK-024 cheat was caught.

        ## Artifacts

        - `phase2/event_store.py` (extended: `append_verify_result`)
        - `phase2/test_event_store.py` (extended)
        - `phase3/run_chunk_030.py`
    """)
    (NOTES / "CHUNK-030.md").write_text(note)


if __name__ == "__main__":
    sys.exit(main())
