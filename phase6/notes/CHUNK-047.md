# CHUNK-047 — Spike: confirm `REVIEW:` marker detection approach

**Status:** done
**Date:** 2026-08-16
**Runner:** `phase6/run_chunk_047.py`
**Fixtures:** `phase6/fixtures_chunk047/{clean,marker_comment,marker_trailing,marker_in_string,doc_mention}`

## Question

Does a straightforward scan for `REVIEW:` markers work without excessive
false positives, on real fixtures, before committing to CHUNK-048's
implementation? And: repo-wide, or `permitted_paths`-scoped?

## Method

`phase6/run_chunk_047.py` implements `find_review_markers(root)`: walks a
directory tree, restricts to a fixed list of source-code file extensions
(`.py .php .js .jsx .ts .tsx .go .java .rb .c .cc .cpp .h .hpp .sh .yml
.yaml` — deliberately never `.md`), and on each line requires a recognized
comment-leader token (`#`, `//`, `/*`, `<!--`) immediately (modulo
whitespace) followed by the literal tag, via one regex. This is explicitly
**not** diff-based (see PLAN.md's Phase 6 rationale: `loop.py` commits
every iteration regardless of outcome, so a diff-based check against
`head_before` would silently stop seeing a marker left in an earlier
iteration once the diff base moved past it — this scans real current-state
files directly instead, same principle as CHUNK-045's `--repo`-toplevel
check).

Five hand-built fixtures, plus a real scan of the SisyphX repo itself:

| Fixture | Content | Expected |
|---|---|---|
| `clean` | ordinary code, no markers | 0 |
| `marker_comment` | genuine marker on its own comment line above code | 1 |
| `marker_trailing` | genuine marker beside code, PHP trailing `//` comment | 1 |
| `marker_in_string` | the literal tag appears in a docstring/f-string/plain string, no comment leader immediately before it | 0 (false-positive check) |
| `doc_mention` | a markdown file discussing the convention, including a fenced code-block example that looks exactly like a real marker | 0 (false-positive check) |

## Results

All 5 fixtures matched expectation exactly (see script output). The real
repo-wide scan (excluding fixtures) returned **zero** matches.

## Findings

1. **A naive repo-wide text grep for the tag is not safe in this repo
   today.** `PLAN.md` (10 occurrences), `AGENTS.md` (5), and
   `experiments/planner/BRIEF.md` (5) all discuss the review-marker
   convention itself in prose and in a fenced code-block *example* — the
   exact scenario the `doc_mention` fixture reproduces. `AGENTS.md`'s own
   example line (`# REVIEW: this retry loop has no backoff...`) is
   syntactically indistinguishable from a real marker if you don't also
   know it's inside a markdown fence. Restricting the scan to source-code
   file extensions and never `.md` sidesteps this whole class for free,
   without needing a markdown-fence-aware parser.
2. **The same false-positive class recurs *inside* code files too, where
   the extension filter can't help.** While writing this spike's own
   comment explaining the trailing-comment example, using the literal tag
   syntax inside that explanatory comment tripped the checker against the
   real repo scan (a `#`-comment in a `.py` file, discussing the syntax,
   is indistinguishable from a real marker). Fixed by rephrasing the
   comment to avoid the literal syntax — but this is a genuine, recorded
   limitation of a pure syntactic scan, not a hypothetical one: **any code
   comment discussing the `REVIEW:` tag by name, in a comment, will
   false-positive.** No fix is being applied for this narrow case now
   (documenting the convention/tooling in prose inside code comments is
   rare); this is the honest bounded limitation, same spirit as CHUNK-037's
   explicitly bounded literal-example-only guarantee.
3. **Comment-leader-adjacency avoids the string/docstring false positive.**
   Requiring the comment leader immediately before the tag (not just
   present anywhere on the line) correctly ignores the tag appearing in
   ordinary string/docstring prose (`marker_in_string` fixture), matching
   CHUNK-047's acceptance criteria concern directly.
4. **Known, accepted false-negative**: a per-line regex heuristic is not a
   real parser. A string literal containing the literal comment-leader
   text immediately followed by the tag on the same physical line (e.g.
   `s = "# REVIEW: fake"`) would still match and false-positive; the
   inverse (a real marker somehow embedded oddly) is not specifically
   tested. Not solved here — same "explicit, bounded limitation" posture
   as prior phases when a mechanical check has a known edge it doesn't
   cover.

## Decision: repo-wide, not `permitted_paths`-scoped

Per the open question PLAN.md left for this spike: **repo-wide**, not
scoped to a chunk's `permitted_paths`. Reasoning:

- The whole point of the `REVIEW:` convention (per `AGENTS.md`) is a
  human-driven, ad hoc signal that *some* outstanding concern exists
  *somewhere* in the codebase that hasn't been resolved. Scoping the
  startup check to only the current chunk's `permitted_paths` would let
  the loop start new automated work while a known, flagged concern sits
  unresolved just outside that chunk's declared scope — defeating the
  purpose of a fail-fast precondition.
  ("Blunter" is the intended behavior here: it's the same choice as
  CHUNK-045's whole-repo-toplevel precondition, which also has no
  finer-grained scoping.)
- Restricting to source-code file extensions (finding 1, above) already
  does the bulk of the practical false-positive-avoidance work that
  motivated considering scoping at all; the remaining risk (an unrelated
  stray marker elsewhere blocking a chunk) is judged an acceptable,
  visible cost — the loop's error message can and should name the exact
  offending file/line so a human/agent can resolve it quickly rather than
  guess.
- `permitted_paths` scoping would also need threading a new parameter into
  the checker and into `loop.py`'s call site for comparatively little
  benefit; keeping the checker a plain `find_review_markers(root) ->
  list[...]` with no chunk-specific parameters keeps CHUNK-048 simpler and
  matches this spike's confirmed design.

## Implications for CHUNK-048

- Promote `find_review_markers()` (this file) into
  `phase2/review_marker_check.py` largely as-is: same extension list, same
  comment-leader-adjacency regex, same repo-wide (non-scoped) walk.
- Wire it into `phase1/loop.py` as a one-shot precondition check before
  iteration 1, alongside the existing `--repo`-toplevel check
  (CHUNK-045's pattern) — print the offending file/line(s) and refuse to
  start, per PLAN.md's Phase 6 final design.
- `pytest` unit tests for CHUNK-048 should reuse these five fixture
  shapes (clean / genuine-comment-marker / genuine-trailing-marker /
  string-false-positive / doc-false-positive) rather than inventing new
  ones.

## Artifacts

- `phase6/run_chunk_047.py`
- `phase6/fixtures_chunk047/clean/app.py`
- `phase6/fixtures_chunk047/marker_comment/app.py`
- `phase6/fixtures_chunk047/marker_trailing/service.php`
- `phase6/fixtures_chunk047/marker_in_string/app.py`
- `phase6/fixtures_chunk047/doc_mention/NOTES.md`
