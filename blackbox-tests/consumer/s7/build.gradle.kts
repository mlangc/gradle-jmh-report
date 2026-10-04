import com.github.mlangc.jmhreport.gradle.JmhReportExtension

apply(plugin = "com.github.mlangc.jmhreport")

configure<JmhReportExtension> {
    jmhResultPath = file("build/reports/jmh/results.json").absolutePath
    jmhReportOutput = file("build/reports/jmh").absolutePath
}
