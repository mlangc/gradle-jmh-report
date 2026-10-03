import io.morethan.jmhreport.gradle.JmhReportExtension

apply(plugin = "io.morethan.jmhreport")

configure<JmhReportExtension> {
    jmhResultPath = file("build/reports/jmh/results.json").absolutePath
    jmhReportOutput = file("build/reports/jmh").absolutePath
}
