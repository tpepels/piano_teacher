# Code quality gate

The `quality` job runs on every main push and manual core/full CI run.
It is independent of Python, Godot and fingering behavior tests. The
exact-commit status is `piano-teacher/quality`.

- Ruff: Python correctness, unused names/imports, bugbear, import sorting,
  simplification, modernization, comprehensions, cyclomatic complexity
  and selected security checks.
- gdlint: GDScript lint rules. Native Godot syntax and behavior remain
  separate checks (the third-party parser may lag Godot).
- ShellCheck: shell lint, plus strict Bash syntax.
- Python compilation and Node syntax: strict for all tracked source.
- actionlint: strict workflow YAML, expressions and embedded shell.
- Unit tests for the diagnostic comparator.

## Existing debt

The starting commit is `38c22a51aec90782c3cba152e1c371bbd81dbd3d`. The gate compares
current lint findings against that immutable Git snapshot, by file,
rule, message and occurrence count, ignoring line-number movement.
New diagnostic counts fail, including in tests and scripts. The gate scans
all tracked sources and prints debt counts. It does not automatically
advance the baseline or eliminate existing debt. A finding matching the
original snapshot can be reintroduced after being fixed; a reviewed cleanup
can remove that allowance by tightening the baseline. Changed diagnostic
messages, including complexity changes, are treated as new findings.
Native syntax checks and workflow checks have no baseline exception.

## Run locally

Use Python 3.12, Node 22, Go and a Git checkout containing the baseline.

```sh
python -m pip install -r requirements-quality.txt
go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.7
export PATH="$(go env GOPATH)/bin:$PATH"
python -m pytest --noconftest -q tests/test_quality_gate.py
python scripts/quality_gate.py
```

Run `python scripts/quality_gate.py --strict` to fail on all current lint
debt and print every finding. Add new files to the Git index before running
locally. No code is modified. Coverage is informational; no new coverage
threshold is imposed. Branch protection must separately require the quality
status to prevent merges or protected-branch updates.
