package io.morethan.jmhreport;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public final class Extensions {

    private Extensions() {
    }

    /** Extracts all entries of the zip into the given directory, creating it (and missing parents) if necessary. */
    public static void extract(ZipInputStream zipStream, File targetDirectory) throws IOException {
        targetDirectory.mkdirs();
        ZipEntry entry;
        while ((entry = zipStream.getNextEntry()) != null) {
            File entryFile = new File(targetDirectory, entry.getName());
            if (entry.isDirectory()) {
                entryFile.mkdirs();
            } else {
                entryFile.getParentFile().mkdirs();
                Files.copy(zipStream, entryFile.toPath(), StandardCopyOption.REPLACE_EXISTING);
            }
        }
    }
}
