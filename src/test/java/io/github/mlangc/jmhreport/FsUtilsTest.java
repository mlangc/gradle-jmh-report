package io.github.mlangc.jmhreport;

import org.junit.jupiter.api.Test;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.util.zip.ZipInputStream;

import static org.assertj.core.api.Assertions.assertThat;

class FsUtilsTest {

    @Test
    void extractsZip() throws IOException {
        // the target folder must not exist: extract creates it
        File testFolder = new File("build/tests/not/yet/there");
        deleteRecursively(new File("build/tests"));

        try (InputStream jmhVisualizerZip = getClass().getResourceAsStream("/jmh-visualizer.zip")) {
            assertThat(jmhVisualizerZip).isNotNull();
            try (ZipInputStream zipStream = new ZipInputStream(jmhVisualizerZip)) {
                FsUtils.extract(zipStream, testFolder);
            }
        }

        assertThat(new File(testFolder, "bundle.js")).exists();
        assertThat(new File(testFolder, "index.html")).exists();
        assertThat(new File(testFolder, "favicons")).exists().isDirectory();
        assertThat(new File(testFolder, "favicons/favicon.ico")).exists();
    }

    private static void deleteRecursively(File file) {
        File[] children = file.listFiles();
        if (children != null) {
            for (File child : children) {
                deleteRecursively(child);
            }
        }
        file.delete();
    }
}
