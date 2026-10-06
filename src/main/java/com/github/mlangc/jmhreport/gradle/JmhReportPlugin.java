/**
 * Copyright 2016 the original author or authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package com.github.mlangc.jmhreport.gradle;

import com.github.mlangc.jmhreport.gradle.task.JmhReportTask;
import org.gradle.api.Plugin;
import org.gradle.api.Project;

import java.io.File;

public class JmhReportPlugin implements Plugin<Project> {

    public static final String EXTENSION = "jmhReport";

    @Override
    public void apply(Project project) {
        JmhReportExtension extension = project.getExtensions().create(EXTENSION, JmhReportExtension.class);
        // The extension is filled in after the plugin is applied, so the values have to be read lazily.
        // The layout resolves relative paths against the project directory.
        // This applies to every JmhReportTask, including the ones registered by the build script itself.
        project.getTasks().withType(JmhReportTask.class).configureEach(task -> {
            task.getJmhResultFile().convention(project.getLayout().file(project.provider(() ->
                    new File(requireNonNull(extension.getJmhResultPath(), "jmhResultPath must not be null")))));
            task.getJmhReportOutputFolder().convention(project.getLayout().dir(project.provider(() ->
                    new File(requireNonNull(extension.getJmhReportOutput(), "jmhReportOutput must not be null")))));
        });

        // create (not register) keeps the plugin usable with Gradle versions before 4.9
        project.getTasks().create("jmhReport", JmhReportTask.class)
                .setDescription("Create an HTML report for the latest JMH results.");
    }

    private static String requireNonNull(String value, String message) {
        if (value == null) {
            throw new IllegalStateException(message);
        }
        return value;
    }
}
