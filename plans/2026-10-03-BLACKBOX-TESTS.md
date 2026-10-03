# Plan: Black-box tests

Status: **approved, not started**.

This plan covers only the black-box tests, a check that compares the plugin's output with a golden snapshot.
The modernization itself will be planned separately; this check is the safety net it builds on.

## Ground rules

- Commit messages follow the root `CLAUDE.md`: a terse single-line subject, and a body that is only a bare
  reference to this plan (`plans/2026-10-03-BLACKBOX-TESTS.md`).

## Goal

Before modernizing the build (Gradle wrapper, Kotlin, plugin-publish, lazy task API), put a check in place
that shows the plugin still behaves the same for its users. The check must:

- be **black-box**: it only uses the built plugin jar, so the build being upgraded can't affect it;
- compare the **report output** with a golden snapshot taken from today's plugin (0.9.6 at `7bd8da0`);
- run the plugin under **several consumer Gradle versions**;
- run with today's build first (green on the baseline), then stay green for every modernization step.

Out of scope: the Eclipse plugin configuration, the `exampleProjects/` JMH setup, running real benchmarks,
checking the publishing metadata (POM / plugin marker), and CI. Publishing gets its own check later; until CI is
added, the check runs locally.

## What "same behaviour" means

The plugin's whole contract is: given a JMH JSON file and an output folder, `jmhReport` writes these files:

| File | Expectation |
|---|---|
| `index.html`, `bundle.js`, `settings.js`, fonts, `favicons/favicon.ico` | byte-identical to the contents of `jmh-visualizer.zip`; no files missing, none extra |
| `provided.js` | **semantically** identical: evaluated as JS, it defines exactly the globals `providedBenchmarks` and `providedBenchmarkStore`, with the same values as the golden (see "Comparing `provided.js`") |
| the input JSON (if it lives in the output folder) | untouched: same hash as the fixture JSON; not part of the golden |

The check also covers:

- the run name comes from the result file's base name (`foo.json` → `'foo'` in `provided.js`);
- the task fails with a clear message when the input file is missing;
- the console prints `JMH Report generated, please open: file://…/index.html`.

## Layout

Everything lives in `blackbox-tests/`, a uv project that is independent of the Gradle build. The fixed points are:

- `CLAUDE.md`: how to run the check and how to update the golden, for agents and humans alike.
- `check.py`: the entry point, with the CLI described below.
- `gradle-versions.toml`: the registry of Gradle versions, described below.
- `golden/`: the committed expectation, in two parts:
  - SHA-256 hashes of the extracted visualizer files, i.e. every output file except `provided.js` and the input
    JSON. The set of files must match exactly. Large files like `bundle.js` already live in `jmh-visualizer.zip`,
    so git doesn't get a second copy of them.
  - the two `provided.js` globals as canonical JSON, kept in full because a failure there is the one we want to
    read. They're recorded for the run name `results`; scenarios with another run name (S3) compare against the
    same golden with the run name substituted (`providedBenchmarks = ['my-run']`, store key `'my-run'`).

So every scenario that succeeds compares against the same golden, wherever its output folder is.

Beyond that, how the code, the consumer fixture and the fixture JSON are organized is up to the implementer.

## Comparing `provided.js`

jmh-visualizer only loads `provided.js` with a `<script>` tag and reads the two globals (`store.ts`,
`DefaultTopBar.tsx` in the current jmh-visualizer source). So what matters is what the file evaluates to, not its text. Comments, the timestamp,
whitespace, line endings, quote style and the order of object keys may all change.

- A small Node script runs the file in a fresh `node:vm` context and prints
  `{"providedBenchmarks": …, "providedBenchmarkStore": …}` as JSON. It fails if the file doesn't evaluate, or if it
  defines any global other than these two. (A rewrite to `let`/`const` would still work in the browser but fail
  this check; that's a deliberately conservative false positive.)
- `check.py` loads that JSON and compares it with the golden as Python values. Dict comparison ignores
  key order, while list order still counts: the order of runs and benchmarks is what the visualizer displays.
- On a mismatch it prints a unified diff of both sides dumped with `sort_keys=True, indent=2`. `--update-golden`
  writes the golden in the same form.
- The timestamp comment on line 1 needs no special handling; it disappears during evaluation.
- Node comes from mise (pinned in `mise.toml`, like uv), so `check.py` stays stdlib-only Python.

The umlaut in the fixture (see "Fixture data") matters: if the plugin decodes or encodes the input with the wrong
charset, the evaluated string differs and the check fails. For that to work, the consumer runs with a non-UTF-8
default charset (see "The fixture consumer"); otherwise a rewrite that relies on the platform charset would go
unnoticed, since JDK 18+ defaults to UTF-8 (JEP 400) and so do typical locales.

## The fixture consumer

- It loads the plugin via `buildscript { repositories { flatDir … } dependencies { classpath … } }` plus
  `apply plugin: 'io.morethan.jmhreport'`. That works the same on Gradle 3.5 and 9.x, and no publishing is
  needed.
- No `kotlin-stdlib` goes on the classpath, unlike in `exampleProjects/`: plugin classloaders see Gradle's
  bundled Kotlin stdlib parent-first, so an added one is never used (verified on 3.5, 7.6.4, 8.14.3 and 9.7.1;
  the loaded stdlib was 1.1.0, 1.7.10, 2.0.21 and 2.4.0). So the fixture needs no remote repository and runs
  offline once the Gradle distributions are cached. For the modernization this means: the jar must target a
  Kotlin API version no newer than the embedded Kotlin of the oldest checked Gradle (1.7 for 7.6.4), and the
  check catches violations.
- The daemon runs with a non-UTF-8 default charset (`org.gradle.jvmargs=-Dfile.encoding=US-ASCII` in the
  fixture's `gradle.properties`; verified to take effect on JDK 25, and 0.9.6 still writes `größe` correctly).
- Later, once the modernized build can publish to a local file repo (`maven-publish` to `build/repo`), the fixture
  can resolve the plugin like real users do: via `pluginManagement` and `plugins { id … }`, with a real POM and
  plugin marker. That also tests the publishing metadata. This belongs to the modernization plan.
- One Gradle invocation per version should cover all scenarios (e.g. one subproject each, verified to work).
  S5 fails by design, so the run needs `--continue` and is expected to exit non-zero; whether each scenario
  passed comes from its output files and log lines, not from the exit code. (Running S5 separately and
  requiring exit 0 for the rest is an acceptable alternative.) Before the run,
  `check.py` puts the fixture JSON where a JMH run would have written it: `build/reports/jmh/results.json` of each
  scenario that needs an input (`my-run.json` for S3). `build/` is git-ignored, so it can't be committed there.

The baseline scenarios avoid the two known bugs in 0.9.6 (see "Known bugs"), so the golden records only correct
behaviour:

| # | Scenario | Config style | Expected today |
|---|---|---|---|
| S1 | explicit config equal to the intended defaults: `jmhResultPath = project.file('build/reports/jmh/results.json')`, `jmhReportOutput = project.file('build/reports/jmh')` | Groovy DSL, like the README | passes |
| S2 | as S1, but with absolute `String` paths: `project.file('…').absolutePath` | Groovy DSL | passes, same golden as S1 |
| S3 | result file with another base name (`my-run.json`) | `project.file(...)` (as S1) | passes, `providedBenchmarks = ['my-run']` |
| S5 | input missing | `project.file(...)` (as S1) | fails with `Input '…' does not exists!` |
| S7 | as S1, in Kotlin DSL (`build.gradle.kts`) | `configure<JmhReportExtension> { jmhResultPath = file("…").absolutePath }` (plus `import io.morethan.jmhreport.gradle.JmhReportExtension`): `apply plugin` generates no type-safe `jmhReport {}` accessor, the properties are `String?`, and relative strings hit the defaults bug. As a subproject it reuses the root's `buildscript` classpath, so a `.kts` `buildscript {}` block isn't exercised | same golden as S1; skipped on 3.5 (verified on 7.6.4, 8.14.3, 9.7.1) |
| S8 | as S1, run twice: before the second run the input is replaced (e.g. a `score` changed) | Groovy DSL | passes: the second `provided.js` reflects the new input, so the task must not be UP-TO-DATE. Guards the inputs/outputs work in the modernization |

### Known bugs, and the scenarios that come with their fixes

Both reproduce with the 0.9.6 jar on Gradle 3.5:

- **Defaults don't work.** `JmhReportExtension` declares relative `String` defaults, and `JmhReportTask` wraps
  them in `File(...)`, which resolves against the daemon's working directory instead of the project directory:
  `Input '~/.gradle/daemon/3.5/build/reports/jmh/results.json' does not exists!`. The same goes for any relative
  `String` the user sets.
- **The output folder must exist.** `ZipInputStream.extract` only creates directories for directory entries;
  the zip's first entry is a file at its root, so writing it fails with `FileNotFoundException` when the
  output folder is missing.

Once the check is green on the baseline, these get fixed as their own steps of the modernization. Each fix adds
its scenario, which must produce **exactly the same output as S1** (same golden, no `--update-golden`):

| # | Scenario | Added with |
|---|---|---|
| S4 | as S1, but the output folder (e.g. `build/reports/jmh-report`) doesn't exist yet | the `extract` fix |
| S6 | defaults: plugin applied, no `jmhReport {}` block | the defaults fix |

S1 is what the fixed defaults must be equivalent to, so S6 needs no golden of its own. The default file name
stays `results.json`. The defaults fix also adapts the README's "Configure the plugin" example, which still
says `result.json`: it switches to `results.json` and says that the block is only needed when the paths differ
from the defaults.

## Fixture data

The fixture JSON is a copy of
`e2e/fixtures/linked-hash-first-vs-iter-next-benchmark.json` from
[jmh-visualizer](https://github.com/mlangc/jmh-visualizer): real JMH output with 4 benchmarks, the `@Param`
`size` and `gc.alloc.rate` secondary metrics, about 23 KB. It's copied once (the source commit is noted in
`blackbox-tests/CLAUDE.md`) and not kept in sync. For S3, `check.py` places it as `my-run.json`.

One edit: the param `size` is renamed to `größe` in all four benchmarks, so the file stays consistent for the
visualizer. The source is pure ASCII, so without this edit the check wouldn't notice if a rewrite of the copy
loop in `JmhReportTask` stopped reading and writing UTF-8. The file must be saved as UTF-8; line endings don't
matter, because the check compares evaluated values.

The plugin doesn't parse the JSON; it copies it line by line into `provided.js`. The check does parse it: Node
evaluates `provided.js`, so the fixture must be valid JSON or evaluation fails. The check only looks at the
evaluated values, not at whether they match the schema the visualizer expects. Content that's realistic for the
visualizer is a bonus when you open a generated report by hand.

## Tooling

The check is written in Python, outside the Gradle build being modernized.

- `uv` and `node` are pinned in `mise.toml` next to Java, so `mise install` gives contributors everything they
  need. Node is only used to evaluate `provided.js` (see above). uv manages the Python interpreter itself (`requires-python` in `blackbox-tests/pyproject.toml`, e.g. `>=3.13`).
- The Python code only uses the standard library; there are no runtime dependencies.
- Dev dependencies are `ruff` (lint + format) and `mypy` (`strict = true`), configured in
  `blackbox-tests/pyproject.toml`.
- Commands, run from `blackbox-tests/`:
  - `uv run check.py …`
  - `uv run ruff check && uv run ruff format --check`
  - `uv run mypy .`

## `check.py`

Two modes:

```
# check: compare against golden/ on each given Gradle version
cd blackbox-tests && uv run check.py --jar ../build/libs/gradle-jmh-report-<v>.jar [--gradle 7.x,8.x,9.x]

# record: (over)write golden/ from a run on exactly one Gradle version; no comparison
cd blackbox-tests && uv run check.py --jar ../build/libs/gradle-jmh-report-<v>.jar --update-golden --gradle 3.5
```

Gradle versions play two roles:

- **Golden source: Gradle 3.5 on JDK 8.** The initial golden is recorded with the 0.9.6 jar on the Gradle version
  the plugin is built with today, as close to the current source as possible.
- **Check matrix: latest patch of 7.x, 8.x and 9.x.** Every version has to match the golden, unless it carries a
  recorded `known-failure` (see below).

### `gradle-versions.toml`

The Gradle versions the check knows about, each with the Java version it runs on:

```toml
[[gradle]]
name = "3.5"
version = "3.5"            # exactly the project's current wrapper version
mise-java = "corretto-8"

[[gradle]]
name = "7.x"
version = "7.6.4"
mise-java = "17"

[[gradle]]
name = "8.x"
version = "8.14.3"
mise-java = "21"

[[gradle]]
name = "9.x"
version = "9.8.0"
mise-java = "25"
```

- `--gradle` takes `name`s, comma-separated, and rejects names that aren't in the file. Without `--gradle`, a
  check runs every entry in file order, which is also the order of the result table.
- Bumping a patch version only changes `version`; commands and docs keep using the stable `name`.
- `check.py` rejects duplicate names.
- An optional `known-failure = "<short reason>"` marks a version on which the jar under test is known to fail
  (see step 4 under "Steps"). The check still runs it and reports "known failure"; if it unexpectedly passes, the check says
  so, so the stale field gets removed.
- The JDK comes only from mise. Always run `mise install java@<mise-java>` (idempotent) before
  `mise where java@<mise-java>`: `mise where java@21` fails when only `openjdk-21.0.2` is installed. Abort if
  `mise where` fails or yields nothing, because `gradlew` with an empty `JAVA_HOME` silently falls back to the
  `java` on `PATH`. Log the actual `java -version`. mise is required anyway for this repo.

For each Gradle version:

1. Copy the consumer fixture to a fresh temp dir.
2. Add a Gradle wrapper whose `distributionUrl` points at that version, so the distribution is downloaded on
   demand (and cached in `~/.gradle/wrapper/dists/`) and nothing beyond mise needs to be installed. The repo's
   3.5 `gradlew` and `gradle-wrapper.jar` start 7.6.4, 8.14.3 and 9.7.1 cleanly (verified). They also start
   9.8.0, but only `--version` ran on it so far; the probe scenarios ran on 9.7.1. Use `-bin`
   distributions, except `-all` for 3.5, which matches what's already cached from the project's wrapper.
3. Resolve the JDK for that version from `gradle-versions.toml` via mise.
4. Run all scenarios with `--stacktrace`, keep the log, and for Gradle ≥ 7 also add `--warning-mode all`.
5. Hash the output files (without `provided.js`) and compare them with the golden; evaluate `provided.js` and
   compare its globals with the golden; check that the input JSON is untouched. Check the
   `JMH Report generated, please open: …` console line. For S5, assert on the failure message instead. Compare
   paths in messages after `os.path.realpath` (the S5 message uses the canonical path; on macOS `/var/…` and
   `/private/var/…` differ).
6. Print a version × scenario matrix (pass / fail / skipped / known failure) and exit non-zero on any unexpected
   result.

`--update-golden` requires exactly one `--gradle` name and just writes `golden/` from that run. Checking that
the other Gradle versions agree is a separate, normal check run. Recording and checking stay two simple,
separate steps, and the golden can later be updated on whichever Gradle version the modernized jar supports
(e.g. after an intended change of the output); the `git diff` of `golden/` shows what changed.

S7 (Kotlin DSL) is skipped on 3.5, the only registered version without Kotlin DSL support; its expectation is
the same golden as S1: the DSL style must not change the output. S8 needs a second invocation; its second
`provided.js` is compared against the golden values with the same edit applied.

Extra signals, reported but not failing (at first):

- Gradle deprecation warnings per version (only Gradle's own lines, not JVM warnings such as JDK 25's
  "restricted method" notice), so we can see the `Task.project` warning disappear. It's expected on 8.x and 9.x
  only, not on 7.x;
- an S1 run with `--configuration-cache` on Gradle ≥ 8. It fails today and should pass after modernization.
  Once it does, it becomes a hard check.

## Steps

1. Fix the documented end-to-end example in passing: remove the unused `klaxon` classpath entry from
   `exampleProjects/*/build.gradle`. Separate commit.
2. Add `uv` and `node` to `mise.toml`, and set up `blackbox-tests/` as a uv project with `gradle-versions.toml`,
   the consumer fixture and the fixture JSON (see "Fixture data").
3. Write the check (clean under ruff + mypy). Build the jar from `7bd8da0` and record the golden with
   `--update-golden --gradle 3.5` (JDK 8).
4. Run the check on 3.5 (sanity: matches what was just recorded), then on the check matrix (7.x, 8.x, 9.x) with
   the same jar. All runs should match the 3.5 golden (probes with S1, S5 and S7 already ran fine on 7.6.4,
   8.14.3 and 9.7.1). If a Gradle version fails, find out why:
   - an error in the check itself (fixture, wrapper, JDK choice, …) gets fixed;
   - anything else, i.e. a real incompatibility of the 0.9.6 plugin with that Gradle version, is only recorded:
     the reason goes into `blackbox-tests/CLAUDE.md`, and the entry in `gradle-versions.toml` gets a
     `known-failure = "<short reason>"`. The check then reports that version as "known failure" instead of
     failing. Fixing it is left to the modernization; once fixed, the field is removed.
5. Document it in `blackbox-tests/CLAUDE.md`, with a short pointer to it in the root `CLAUDE.md`.
6. Hand off to a reviewer as described in "Agentic Reviews → By Subagents" in the root `CLAUDE.md`. The review
   covers all changes made under this plan, and the reviewer gets this plan as its brief. Wait for the
   findings, address the ones you agree with, and re-run the check if anything changed. Only then report back,
   listing each finding with how it was handled and why any were not addressed.

Done when the baseline jar matches the 3.5 golden on 7.x, 8.x and 9.x, or fails there for a recorded and
understood reason, and the review findings have been handled. How and when the check runs during the
modernization goes in the modernization plan.
