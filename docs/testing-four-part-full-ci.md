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
bash scripts/ci-full.sh --shard 2
bash scripts/ci-full.sh --shard 3
bash scripts/ci-full.sh --shard 4
bash scripts/ci-full.sh --status
```

If one part fails, fix its failure and rerun **only that part**, e.g.
`bash scripts/ci-full.sh --shard 3`. No earlier part is rerun.

```bash
bash scripts/ci-full.sh --all
```

This is also the default when invoking `bash scripts/ci-full.sh` without
arguments. It runs all four sequentially, **continues after a failed part**
so the output contains all observed failures, and automatically skips
parts already recorded as passing on the same clean Git revision.
`--all --force` reruns all four even if previously passing.

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
`bash scripts/ci-full.sh --shard 2 -- -x`. Partial/filtered runs do
not count as a full-shard PASS.

The separate 24-shard original-symbol notation audit, native physical
MIDI acceptance, packaging and learner-study gates remain outside this
four-part Python suite. A PASS here does not certify those gates.
