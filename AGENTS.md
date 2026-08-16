# AGENTS.md

Notes for AI agents (e.g. Devin) working in this repo.

## Review comment convention

When reviewing code, leave inline feedback using a `REVIEW:` tag directly
above or beside the relevant line, e.g.:

```python
# REVIEW: this retry loop has no backoff, can hammer the API -- fix?
def retry_call():
    ...
```

This is a manual, human-driven convention (not yet an automated guard --
see `PLAN.md`'s Phase 6+ "Review-marker guard" entry for the deferred plan
to eventually gate loop sign-off on this).

**To have an agent check/resolve outstanding review comments, ask
explicitly**, e.g.:

- "Address the REVIEW comments in `phase5/`."
- "Find and resolve any REVIEW comments in the repo."

When asked to do this, the agent should:

1. Search for the tag: `grep -rn "REVIEW:" <path>` (or repo-wide).
2. For each match, read the surrounding context and make the requested
   change.
3. Remove the `REVIEW:` comment once it has been addressed -- do not leave
   resolved review comments in the codebase.
4. If a comment can't be safely resolved (ambiguous, needs a human
   decision), leave it in place and call it out explicitly rather than
   guessing or silently dropping it.

This is opt-in per request, not automatic -- an agent should not go
hunting for and resolving `REVIEW:` comments unless asked to.
