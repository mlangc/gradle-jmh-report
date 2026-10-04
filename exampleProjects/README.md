# JMH example projects

A standalone Gradle build (independent of the plugin's own build) with two subprojects:
- java-benchmarks: benchmarking simple things of Java
- kotlin-benchmarks: benchmarking simple things of Kotlin

The build consumes the plugin jar from `../build/libs`, so build that first.

## How to execute

```
./gradlew jar
cd exampleProjects
./gradlew :java-benchmarks:jmh
./gradlew :kotlin-benchmarks:jmh
```

Use `-Pinclude=".*QuickBenchmark.*"` to run only some benchmarks (see `./gradlew jmhHelp`). The report ends up in
`<project>/build/reports/jmh/index.html`.
