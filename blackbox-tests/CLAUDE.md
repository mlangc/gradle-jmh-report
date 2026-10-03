# CLAUDE.md

Black-box check for the plugin jar: it runs the built jar under several consumer Gradle versions and compares the
generated report with a golden snapshot. It is independent of the Gradle build in the repo root, so it keeps working
while that build is modernized. Background and rationale: `plans/2026-10-03-BLACKBOX-TESTS.md`.

## Running

Needs `mise install` (Java versions, `node`, `uv`). From the repository root:

```
./gradlew jar                                              # JDK 8 via mise, as usual
cd blackbox-tests
uv run check.py --jar ../build/libs/gradle-jmh-report-<v>.jar [--gradle 7.x,8.x]
uv run ruff check && uv run ruff format --check && uv run mypy .
```

- `--gradle` takes names from `gradle-versions.toml`; without it every entry runs. Gradle distributions are
  downloaded on first use (`~/.gradle/wrapper/dists/`), JDKs come from mise.
- Prints a version × scenario matrix and exits non-zero on any unexpected result. Gradle logs are kept in
  `build/logs/`; the temp project dirs are only kept when the check failed.
- Deprecation warnings and the `--configuration-cache` run (Gradle ≥ 8) are reported but don't fail the check.
  Today: `Task.project` deprecation on 8.x and 9.x, configuration cache fails. Both should go away with the
  modernization; the configuration-cache run then becomes a hard check.

## Updating the golden

Only when the plugin's output is meant to change (e.g. a new jmh-visualizer bundle):

```
uv run check.py --jar ../build/libs/gradle-jmh-report-<v>.jar --update-golden --gradle <name>
```

Requires exactly one Gradle name (initially `3.5`). It records `golden/` from scenario S1 without comparing
anything; then run a normal check on all versions. `git diff golden/` shows what changed. `golden/` holds SHA-256
hashes of the extracted visualizer files and the two `provided.js` globals as canonical JSON.

## Layout

- `check.py`: entry point. `evaluate_provided.mjs`: runs `provided.js` in a `node:vm` context and prints the two
  globals as JSON (fails on any other global).
- `gradle-versions.toml`: Gradle versions to check, with the Java version each runs on. Beyond the plan's keys,
  `distribution = "all"` selects the `-all` distribution (used for 3.5 only). `known-failure = "<reason>"` marks a
  version where the jar is known to fail; it then shows as "known failure", and the check complains once it
  passes again so the field gets removed. No version has one at the moment.
- `consumer/`: the Gradle fixture project, one subproject per scenario, loading the jar from `libs/` through
  `flatDir` (filled by `check.py`, which also adds a wrapper for the Gradle version under test). The daemon runs
  with `-Dfile.encoding=US-ASCII` on purpose.
- `data/results.json`: the input fixture. A copy of `e2e/fixtures/linked-hash-first-vs-iter-next-benchmark.json`
  from https://github.com/mlangc/jmh-visualizer at commit `ff75572af2effc5ea9e1441515713bced82a3597`, with
  the param `size` renamed to `größe` (so a charset regression shows up). Not kept in sync.

## Scenarios

| # | What | Expectation |
|---|---|---|
| S1 | explicit config = intended defaults, `File` values | golden |
| S2 | as S1, absolute `String` paths | golden |
| S3 | input named `my-run.json` | golden with run name `my-run` |
| S4 | as S1, output folder `build/reports/jmh-report` doesn't exist yet | golden |
| S5 | input missing | fails with `Input '…' does not exists!` |
| S6 | defaults: no `jmhReport {}` block | golden |
| S7 | as S1 in Kotlin DSL (skipped on 3.5) | golden |
| S8 | as S1, run twice with a changed `score` in between | second run reflects the change (not UP-TO-DATE) |

S4 and S6 guard fixes of two bugs in 0.9.6: relative `String` paths (and so the defaults) used to resolve against
the daemon's working directory, and the output folder used to have to exist already.

## Gotchas

- The jar is plain Java 8 and bundles no Kotlin; it must keep working as a consumer plugin on Gradle 3.5 (no APIs newer than that,
  e.g. `tasks.register`).
- Always `mise install java@<x>` before `mise where java@<x>`; `check.py` does this.
- Gradle 9.8.0 is the newest checked version; to bump a patch version only change `version` in
  `gradle-versions.toml`.
