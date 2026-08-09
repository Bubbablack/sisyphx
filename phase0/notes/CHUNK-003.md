# CHUNK-003 — Confirm timeout is our responsibility

**Status:** done
**Date:** 2026-08-08
**Script:** `phase0/timeout_probe.py` (kept as a reference artifact, not deleted)

## Method

Prompt asks Devin (with `--permission-mode bypass`, per CHUNK-001) to: write
`slow.txt` = `PART1` → run `sleep 60` via its exec tool and wait for it → append
`PART2` → reply. We impose a 20s timeout (shorter than the 60s sleep) from the
Python side and inspect what's left behind, three different ways.

## Results

| Kill strategy | Top-level `devin` process | `sleep 60` grandchild | Workspace state |
|---|---|---|---|
| `subprocess.run(timeout=20)` (plain `.kill()`, SIGKILL to direct child only) | killed | **leaked** (reparented to `launchd`, PID 1) | `slow.txt` = `PART1` exactly, no corruption |
| `Popen(start_new_session=True)` + `os.killpg(pgid, SIGKILL)` | killed | **leaked** (same as above) | same |
| `Popen()` + `.terminate()` (SIGTERM) + 5s grace + `.kill()` fallback | killed (exited via SIGTERM, returncode -15, no custom handler) | **leaked** (same as above) | same |

`ps -o pid,ppid,pgid,command` on the orphaned `sleep 60` showed `PPID=1`
(already reparented to `launchd`) with its **own** `PGID` distinct from
devin's — i.e. Devin CLI puts commands it spawns via its exec tool into their
own process group from the start (consistent with its documented
foreground/background job management — see `essential-commands.mdx`: "If a
command is still running after the default wait period, Devin moves it to the
background"). This means **no signal sent to the top-level `devin` process,
by any of the three standard techniques above, ever reaches a shell command it
already started.** This is architectural, not a bug we can work around with a
different kill() call.

## Conclusion

1. **Timeout enforcement is entirely SisyphX's responsibility** — confirmed,
   no native `--timeout` flag exists (per CHUNK-001), and standard Python
   subprocess timeout mechanisms reliably kill the `devin` process itself.
2. **But killing `devin` does not guarantee killing whatever shell command it
   was running at that moment.** This is a real, tested limitation, not
   speculation.
3. **Killing mid-task does not corrupt workspace state.** In every run,
   `slow.txt` contained exactly `PART1` — the interrupted write never happened,
   the prior write was intact. Combined with Phase 1's "commit every
   iteration regardless of outcome," a timed-out iteration just produces a
   commit of whatever partial state existed at kill time — safe, not
   corrupted, just incomplete.

## Decision for `loop.py`

- Use the **graceful pattern** (SIGTERM, 5s grace period, SIGKILL fallback) as
  the default — it's no worse than the alternatives for the orphan problem,
  and it's the more polite default if a future Devin CLI version ever adds
  its own SIGTERM cleanup handler.
- **Treat a timeout as an exceptional event, not a routine one.** Pick a
  per-chunk timeout generous enough that hitting it is rare; when it does
  happen, log a clear, loud warning in `runs/log.jsonl` noting that background
  processes the agent started *may still be running* and haven't been
  verified clean.
- **Deferred hardening (Phase 2+, not blocking Phase 1):** a process-snapshot
  diff (`ps` before/after each iteration, kill anything new that appeared
  during the iteration window and has no living parent) would close this gap
  properly. Not building it now — Phase 1 is intentionally minimal and
  timeouts should be rare with a sane budget.
- **Open question carried to CHUNK-004:** does `--sandbox` change this at
  all? Sandbox is documented as filesystem/network containment, not process
  lifecycle management, so it likely doesn't — but worth a one-line check
  when we get there rather than assuming.

## Raw artifacts

- `test7_plain.txt`, `test7_pgroup.txt`, `test7_graceful.txt`
