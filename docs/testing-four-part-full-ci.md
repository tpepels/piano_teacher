# Four-part full release CI

The full Python release suite is split into four independently runnable,
**complete and non-overlapping** parts. Each standard pytest test module
(`tests/test_*.py` or `tests/*_test.py`, recursively) belongs to exactly
one part, including all its parameterizations and module-scoped fixtures.
The partitioner chooses modules **before collection/import**: an import or
syntax error in one part does not prevent the other parts from collecting.

The partition is deterministic for a given checkout and estimates relative
work from module size, test functions, parametrization and slow markers.
Actual wall-clock durations may differ. The existing strict quarantine
behavior and slow corpus tests are retained.

## Commands

Run from the repository root after `git pull --ff-only`:

```bash
bash scripts/ci-full.sh --plan
bash scripts/ci-full.sh --shard 1
bash scripts/ci-full.sh --status
```

When a part passes, the runner **automatically starts the next part**.
If any part fails or errors, it **stops immediately**, retaining the
log and status of that part. After fixing it, resume at the failing part:

```bash
bash scripts/ci-full.sh --shard 3
```

This runs part 3 and, if it passes, starts part 4. Parts 1 and 2 are
not rerun. You can also start at any other part directly.

```bash
bash scripts/ci-full.sh --all
```

This is also the default when invoking `bash scripts/ci-full.sh` without
arguments. It starts at part 1, advances to the next part **only when the
previous part passes**, and halts on the first failure. Already-passing
parts from the same clean Git revision are skipped. `--all --force`
reruns them as well, still stopping on the first failure.

## Logs, proof and cleanup

Every part has its own terminal output and retained log:

```text
playtest-results/ci-full/<git-revision>/shard-1.log
playtest-results/ci-full/<git-revision>/shard-2.log
playtest-results/ci-full/<git-revision>/shard-3.log
playtest-results/ci-full/<git-revision>/shard-4.log
```

A matching `shard-N.status` file contains PASS, FAIL or RUNNING.
`--status` prints all four states; a release is accepted **only when all
four show PASS on the same clean Git revision**. Changes to tracked or
untracked source files make the working tree dirty and produce diagnostic
logs without recording new release-gate PASS results. Once you commit and
pull a new revision, any earlier shard PASS values do not transfer.

The runner cleans retained legacy `/tmp/pytest-of-<user>/pytest-N` runs
only when no competing pytest process is detected. Each new part has a
private temporary directory and removes it on exit, including when a
test fails. The logs above remain available. Set `CI_FULL_KEEP_TMP=1` for
a run if raw generated files are needed for diagnosis; it will print the
retained path.

Pass extra pytest flags for diagnosis after `--`, for example
`bash scripts/ci-full.sh --shard 2 -- -x`. In this case **only shard 2**
runs; diagnostic/filtered runs do not advance automatically or count
as a full-shard PASS.

The separate 24-shard original-symbol notation audit, native physical
MIDI acceptance, packaging and learner-study gates remain outside this
four-part Python suite. A PASS here does not certify those gates.
