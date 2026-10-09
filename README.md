# Gradle-JMH-Report

**_gradle-jmh-report_** is a [Gradle](http://gradle.org) plugin to manage and visualize the result of your [JMH](http://openjdk.java.net/projects/code-tools/jmh/) benchmarks.

**Note:** **This plugin is not for executing benchmarks**, its for reporting on already executed benchmarks. There are multiple ways how you can setup your JMH benchmark execution in Gradle, i've written in this [blog post](https://blog.morethan.io/jmh-with-gradle-from-easy-to-simple-dc872d57cf7f) about it!


## News

- 2026/10/09 - 1.0.0 Release - On pair with jmh-visualizer-1.0.0 / New plugin ID `io.github.mlangc.jmhreport` (was 
  `io.morethan.jmhreport`) and group `io.github.mlangc`, Gradle configuration cache support, requires Gradle 8.0 or newer
- 2024/04/19 - 0.9.6 Release - On pair with jmh-visualizer-0.9.6 / Couple of bug fixes
- 2018/10/03 - 0.9.0 Release - On pair with jmh-visualizer-0.9.1 / [Couple of smaller features](https://github.com/jzillmann/jmh-visualizer/milestone/6?closed=1)
- 2018/07/29 - 0.8.0 Release - On pair with jmh-visualizer-0.8.2 / Technical update, minor bug fixes
- 2017/10/31 - 0.7.0 Release - On pair with jmh-visualizer-0.7 / Multi Run Support
- 2017/09/04 - 0.6.0 Release - On pair with jmh-visualizer-0.6 / Layout Change
- 2017/07/30 - 0.5.0 Release - On pair with jmh-visualizer-0.5 / Focusing on Benchmarks
- 2017/05/30 - 0.4.0 Release - On pair with jmh-visualizer-0.4 / Report on secondary metrics
- 2017/05/14 - 0.2.0 Release - Integrate https://github.com/jzillmann/jmh-visualizer
- 2016/12/10 - 0.1.0 Release



## Features

- Create a HTML report for one benchmark run

**Wanted:**
- Create a HTML report for multiple benchmark runs 
- Archive your benchmark results in a structured way


## Getting Started
- Setup JMH for your project (However you wanne do it, you can use a [plugin](https://github.com/melix/jmh-gradle-plugin) or a simple [do-it-your-self script](exampleProjects/jmh.gradle). 
- Add the plugin:
```
plugins {
  id "io.github.mlangc.jmhreport" version "1.0.0"
}
```
  - **Coordinates:** Starting with 1.0.0 the plugin ID is `io.github.mlangc.jmhreport` (previously `io.morethan.jmhreport`), so 1.0.0 is not published under the old ID. The `jmhReport { jmhResultPath, jmhReportOutput }` extension and the `jmhReport` task are unchanged.
  - **Requirements:** Gradle 8.0 or newer.
- Configure the plugin (only needed if your paths differ from the defaults shown here; relative paths are resolved against the project directory):
```
jmhReport {
    jmhResultPath = project.file('build/reports/jmh/results.json')
    jmhReportOutput = project.file('build/reports/jmh')
}
```
- Build the report
  - Given your benchmarks have been executed and the json result file is present, you can execute ```./gradlew jmhReport``` which will build the html report.
  - You can setup a finalizer hook as well: ```tasks.jmh.finalizedBy tasks.jmhReport```. With this, every time you execute your jmh benchmarks, e.g. with _./gradlew jmh_, the _jmhReport_ task will run at the end.


## This is how it looks

![screenshot](https://cloud.githubusercontent.com/assets/148472/26032319/ace91322-3890-11e7-9d0e-7314020a8953.png)


## Project Build
- Execute the examples: `./gradlew jar ;cd exampleProjects; ./gradlew :java-benchmarks:jmh`
- How to publish the Gradle plugin:
  - (Optional) Integrate new version of https://github.com/mlangc/jmh-visualizer
    - `npm run providedZip`
    - `mv jmh-visualizer.zip <path to this repository>/src/main/resources/`
  - Increase version in _gradle.properties_
  - Update _News_ and _Getting Started_ in _README.md_
  - Test report: `./gradlew jar ;cd exampleProjects; ./gradlew :java-benchmarks:jmh -Pinclude=".*QuickBenchmark.*"`
  - Run the black-box tests (`--jar`, and `--repo` against a locally published repository), see _blackbox-tests/CLAUDE.md_
  - Validate the publication: `./gradlew publishPlugins --validate-only`
  - Commit & Push
  - tag with
    - `git tag -a $releaseVersion -m "$releaseVersion release"`
    - `git push --tags`
  - Execute: `./gradlew publishPlugins`
