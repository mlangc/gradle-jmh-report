import io.github.mlangc.jmhreport.gradle.JmhReportExtension

apply(plugin = "io.github.mlangc.jmhreport")

configure<JmhReportExtension> {
    jmhResultPath = file("build/reports/jmh/results.json").absolutePath
    jmhReportOutput = file("build/reports/jmh").absolutePath
}
