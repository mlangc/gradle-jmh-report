# CLAUDE.md

This file provides guidance to agents when working with code in this repository.

## What this is

A Gradle plugin (`io.morethan.jmhreport`, written in Kotlin) that turns an existing JMH JSON result file into an HTML report. It does **not** run benchmarks; it only reports on results already produced by some other JMH setup.

## Build & test

The build is pinned to an old toolchain: Gradle 3.5 wrapper, Kotlin 1.1.x, `sourceCompatibility=1.7`, `compile`/`testCompile` configurations, `jcenter()`. An upgrade of the wrapper to 4.9 was attempted and reverted (see git log), so don't bump Gradle/Kotlin as a side effect of other changes. Gradle 3.5 needs an old JDK (Java 8) to run.

- Build plugin jar: `./gradlew jar` (output in `build/libs/`)
- Run tests: `./gradlew test`
- Single test class: `./gradlew test --tests io.morethan.jmhreport.jmh.ExtensionsTest` (tests use Spek 1.x on JUnit 4 with AssertJ; note the test's package `io.morethan.jmhreport.jmh` differs from its directory)
- End-to-end check against the example project (uses the jar from `build/libs` via a `flatDir` repo):
  `./gradlew jar; ./gradlew -p exampleProjects/java-benchmarks/ jmh -Pinclude=".*QuickBenchmark.*"`
  The example's `jmh` task is finalized by `jmhReport`, which writes `exampleProjects/java-benchmarks/build/reports/jmh/index.html`.

## Architecture

The plugin is tiny; the real UI lives in a separate project, [jmh-visualizer](https://github.com/jzillmann/jmh-visualizer), shipped here as a prebuilt bundle.

- `src/main/resources/META-INF/gradle-plugins/io.morethan.jmhreport.properties` maps the plugin ID to `JmhReportPlugin`.
- `JmhReportPlugin` registers the `jmhReport` extension (`JmhReportExtension`: `jmhResultPath`, `jmhReportOutput`) and the `jmhReport` task.
- `JmhReportTask` does all the work:
  1. Extracts `src/main/resources/jmh-visualizer.zip` (the built jmh-visualizer webapp: `index.html`, `bundle.js`, fonts, and a placeholder `provided.js`) into `jmhReportOutput`, using the `ZipInputStream.extract` extension in `Extensions.kt`.
  2. Overwrites `provided.js` with the JMH result JSON embedded as JS globals (`providedBenchmarks`, `providedBenchmarkStore`, keyed by the result file's base name). jmh-visualizer reads these globals at load time, so the contract between the two projects is the shape of `provided.js`.
- The task declares no Gradle inputs/outputs, so it is never up-to-date and always re-runs.

`exampleProjects/` holds standalone Gradle builds (Java and Kotlin benchmarks) that consume the locally built jar. `exampleProjects/jmh.gradle` is a do-it-yourself JMH setup script they apply (supports `-Pinclude`, `-Pexclude`, `-Pformat`, `-Pprofilers`, `-PjvmArgs`).

## Release process (from README)

1. (Optional) Update the visualizer: in jmh-visualizer run `npm run providedZip`, then replace `src/main/resources/jmh-visualizer.zip`.
2. Bump `projectVersion` in `gradle.properties`.
3. Update *News* and *Getting Started* in `README.md`, and the plugin version in every `exampleProjects/*/build.gradle`.
4. Test the report with the example project (command above).
5. Commit, tag (`git tag -a $releaseVersion -m "$releaseVersion release"`, `git push --tags`), then `./gradlew publishPlugins`.
