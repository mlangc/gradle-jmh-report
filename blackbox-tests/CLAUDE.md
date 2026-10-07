# CLAUDE.md

Black-box check for the plugin: it runs the built jar (or a published copy) under several consumer Gradle versions and compares the
generated report with a golden snapshot. It is independent of the Gradle build in the repo root, so it keeps working
while that build is modernized. Background and rationale: `plans/2026-10-03-BLACKBOX-TESTS.md`; the `--repo` mode comes from
`plans/2026-10-06-RELEASE-1.0.0.md`.

## Running

Needs `mise install` (Java versions, `node`, `uv`). From the repository root:

```
./gradlew jar                                              # JDK 8 via mise, as usual
cd blackbox-tests
uv run check.py --jar ../build/libs/gradle-jmh-report-<v>.jar [--gradle 8.0,8.x]
uv run ruff check && uv run ruff format --check && uv run mypy .
```

- Alternatively check a *published* plugin through its plugin marker artifact, as real users get it (S10's
  `JmhReportTask` reference and the `CC` runs included). `check.py` only consumes a repository; produce one outside
  of it, from the repository root, with a throw-away local repo so that `~/.m2` is never touched or shadowed:

  ```
  R=$(mktemp -d)                    # must be an absolute path
  ./gradlew publishToMavenLocal -Dmaven.repo.local=$R
  cd blackbox-tests
  uv run check.py --repo $R --plugin-version <v> [--gradle 8.0,8.x]
  ```

  `--repo` and `--plugin-version` are required together and mutually exclusive with `--jar`. File repositories
  aren't cached in the Gradle user home, so a stale copy of the same version can't hide a change.
  A `--portal` mode (repository block = `gradlePluginPortal()`, nothing else changes) is planned in
  `plans/2026-10-06-RELEASE-1.0.0.md`.
- `--gradle` takes names from `gradle-versions.toml`; without it every entry runs. Gradle distributions are
  downloaded on first use (`~/.gradle/wrapper/dists/`), JDKs come from mise.
- Prints a version × scenario matrix and exits non-zero on any unexpected result. Gradle logs are kept in
  `build/logs/`; the temp project dirs are only kept when the check failed.
- On Gradle ≥ 8, S1, S6 and S10 are also run twice each with `--configuration-cache` (the first run must store an
  entry, the second must reuse it and regenerate the deleted report). A failure there fails the check. Deprecation warnings are
  reported but don't fail the check. The result is the `CC` column of the matrix.

## Updating the golden

Only when the plugin's output is meant to change (e.g. a new jmh-visualizer bundle):

```
uv run check.py --jar ../build/libs/gradle-jmh-report-<v>.jar --update-golden --gradle <name>
```

Requires exactly one Gradle name (initially `8.0`). It records `golden/` from scenario S1 without comparing
anything; then run a normal check on all versions. `git diff golden/` shows what changed. `golden/` holds SHA-256
hashes of the extracted visualizer files and the two `provided.js` globals as canonical JSON.

## Layout

- `check.py`: entry point. `evaluate_provided.mjs`: runs `provided.js` in a `node:vm` context and prints the two
  globals as JSON (fails on any other global).
- `gradle-versions.toml`: Gradle versions to check, with the Java version each runs on. Beyond the plan's keys,
  `distribution = "all"` selects the `-all` distribution (no version uses it at the moment). `known-failure = "<reason>"` marks a
  version where the jar is known to fail; it then shows as "known failure", and the check complains once it
  passes again so the field gets removed. No version has one at the moment.
- `consumer/`: the Gradle fixture project, one subproject per scenario; the subprojects apply the plugin by ID.
  `check.py` generates the root `build.gradle` (jar mode: `buildscript` classpath from `libs/` through `flatDir`;
  repo mode: `plugins { id … version … apply false }`) and, in repo mode, prepends a `pluginManagement`
  block with the repository to `settings.gradle`; it also adds a wrapper for the Gradle version under test. The daemon runs
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
| S7 | as S1 in Kotlin DSL (skipped below Gradle 5, i.e. never at the moment) | golden |
| S8 | as S1, run twice with a changed `score` in between | second run reflects the change (not UP-TO-DATE) |
| S9 | as S1, plus a task declaring the input as its output, run together with `jmhReport` without a dependency | golden |
| S10 | as S1, but the report comes from a subclass of `JmhReportTask` registered by the build script (`jmhReport` disabled) | golden |
| S11 | a `JmhReportTask` registered by the build script, relative `File`s set directly on its properties (`jmhReport` disabled) | golden |

S4 and S6 guard fixes of two bugs in 0.9.6: relative `String` paths (and so the defaults) used to resolve against
the daemon's working directory, and the output folder used to have to exist already.

## Gotchas

- The jar is plain Java 8 and bundles no Kotlin; it must keep working as a consumer plugin on Gradle 8.0 (no APIs newer than that).
  Gradle 8.0 is the oldest supported version.
- Always `mise install java@<x>` before `mise where java@<x>`; `check.py` does this.
- Gradle 9.8.0 is the newest checked version; to bump a patch version only change `version` in
  `gradle-versions.toml`.
