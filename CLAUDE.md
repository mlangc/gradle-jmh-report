# CLAUDE.md

This file provides guidance to agents when working with code in this repository.

## What this is

A Gradle plugin (`io.github.mlangc.jmhreport`, written in Java 8) that turns an existing JMH JSON result file into an HTML report. It does **not** run benchmarks; it only reports on results already produced by some other JMH setup.

## Commit message style

The maintainer's own commits are almost always a single-line subject with no
body — e.g. `Release 0.9.6`, `Quick hack for heterogenous test setups of a
class`, `Fix multi file gists`, `#35 Stabelize gist order`. The multi-line
ones in the log are squash-merged PRs or dependabot's auto-generated
messages, not commits the maintainer wrote by hand. Match this: keep the
subject terse and skip any descriptive body/bullet list. This is about the
message content only — Claude Code's own attribution trailer
(`Co-Authored-By:` / `Claude-Session:`), when the session's settings call for
it, still gets appended mechanically and doesn't count as "body prose."

One narrow exception: when working from a tracked implementation plan (e.g.
`plans/*.md`), the body may contain a bare reference to that plan and
nothing else — no descriptive prose, no bullet list. A plan may state this
requirement itself (see its own Ground rules); absent that, still keep
bodies empty by default.

## Build & test

The build uses the Gradle 8.0.2 wrapper (run it with JDK 8 via mise), `java-gradle-plugin`, source/target Java 8, and JUnit 5 with AssertJ for tests. Keep the plugin code usable with old consumer Gradle versions (Gradle 8.0 is the oldest supported version, so don't use APIs newer than that); the blackbox tests check this down to 8.0. The wrapper (8.0.2) and the blackbox floor (8.0) are intentionally different Gradle versions, to widen coverage; don't align them. Because the build itself runs on 8.0.2, use `.set(...)` on lazy properties in `build.gradle` (e.g. `tags`, `website`); the `=` assignment only works from Gradle 8.2.

- Build plugin jar: `./gradlew jar` (output in `build/libs/`)
- Run tests: `./gradlew test`
- Single test class: `./gradlew test --tests io.github.mlangc.jmhreport.FsUtilsTest` (JUnit 5 with AssertJ)
- End-to-end check against the example project (uses the jar from `build/libs` via a `flatDir` repo):
  `./gradlew jar; (cd exampleProjects && ./gradlew :java-benchmarks:jmh -Pinclude=".*QuickBenchmark.*")`
  The example's `jmh` task is finalized by `jmhReport`, which writes `exampleProjects/java-benchmarks/build/reports/jmh/index.html`.
- Black-box check of the built jar against a golden report, under several Gradle versions: see
  `blackbox-tests/CLAUDE.md`. Run it before and after changes to the plugin or the build.

## Architecture

The plugin is tiny; the real UI lives in a separate project, [jmh-visualizer](https://github.com/jzillmann/jmh-visualizer), shipped here as a prebuilt bundle.

- The plugin ID (`io.github.mlangc.jmhreport`) and `JmhReportPlugin` are declared in the `gradlePlugin {}` block of `build.gradle`; `java-gradle-plugin` generates the `META-INF/gradle-plugins/*.properties` mapping from it.
- `JmhReportPlugin` registers the `jmhReport` extension (`JmhReportExtension`: `jmhResultPath`, `jmhReportOutput`) and the `jmhReport` task.
- `JmhReportTask` does all the work. It has two `@Internal` properties, `jmhResultFile` and `jmhReportOutputFolder`; the plugin sets them as conventions, for every `JmhReportTask` (also ones a build registers itself), lazily from the extension, with relative paths resolved against the project directory. The action must never touch `project` (configuration cache). They are deliberately not `@InputFile`/`@OutputDirectory`: Gradle would then demand a task dependency when e.g. a JMH task declares the result file as its output, and the report would become skippable.
  1. Extracts `src/main/resources/jmh-visualizer.zip` (the built jmh-visualizer webapp: `index.html`, `bundle.js`, fonts, and a placeholder `provided.js`) into `jmhReportOutput`, using `FsUtils.extract`.
  2. Overwrites `provided.js` with the JMH result JSON embedded as JS globals (`providedBenchmarks`, `providedBenchmarkStore`, keyed by the result file's base name). jmh-visualizer reads these globals at load time, so the contract between the two projects is the shape of `provided.js`.
- The task declares no Gradle inputs/outputs, so it is never up-to-date and always re-runs.

`exampleProjects/` is a standalone multi-project Gradle build (own wrapper; `java-benchmarks` and `kotlin-benchmarks` subprojects) that consumes the locally built jar. `exampleProjects/jmh.gradle` is a do-it-yourself JMH setup script they apply (supports `-Pinclude`, `-Pexclude`, `-Pformat`, `-Pprofilers`, `-PjvmArgs`).

## Release process (from README)

1. (Optional) Update the visualizer: in jmh-visualizer run `npm run providedZip`, then replace `src/main/resources/jmh-visualizer.zip`.
2. Bump `projectVersion` in `gradle.properties`.
3. Update *News* and *Getting Started* in `README.md` (`exampleProjects/` reads the plugin version from `gradle.properties`).
4. Test the report with the example project (command above), and run the black-box tests, in `--jar` and `--repo` mode (`blackbox-tests/CLAUDE.md`).
5. Validate the publication without uploading: `./gradlew publishPlugins --validate-only` (needs `gradle.publish.key` / `gradle.publish.secret`).
6. Commit, tag (`git tag -a $releaseVersion -m "$releaseVersion release"`, `git push --tags`), then `./gradlew publishPlugins`.

## Agentic Reviews

### By Subagents

When I ask you to let a subagent review your work, please consider this:
- Use Opus as a reviewer, in a fresh subagent — not a fork, since a fork
  inherits your full context and always runs on your own model, which
  defeats the point of an independent pair of eyes.
- Tell the subagent what you were tasked to do.
- Where I gave you a specific instruction, constraint, or correction that
  shapes what the review should check, quote my own words directly rather
  than only your paraphrase of them — a paraphrase can silently carry your
  own misreading forward, and the reviewer has no way to catch that if it
  only ever sees your restatement. Don't dump the whole conversation on it
  though; a fresh pair of eyes is the point.
- The reviewer must not modify the implementer's worktree, and is expected
  to report findings back rather than fix anything itself. It's encouraged
  to create its own temporary worktree off the implementer's branch to
  experiment, confirm suspicions, or verify proposed fixes.

### By You

If I ask you to review something directly, don't change anything in the
worktree — just report your findings. Base them on evidence rather than
speculation: as with the subagent reviewer above, you're encouraged to create
your own temporary worktree to experiment in and confirm your suspicions.
