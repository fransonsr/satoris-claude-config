package org.familysearch.logging.scanner;

import java.nio.file.Path;
import java.util.List;

/**
 * Configuration for the Spoon logger scanner.
 */
public class ScannerConfig {
    private final Path projectRoot;
    private final Path outputFile;
    private final boolean autoDiscover;
    private final List<Path> sourcePaths;
    private final boolean debug;
    private final String classpath;

    public ScannerConfig(Path projectRoot, Path outputFile, boolean autoDiscover,
                         List<Path> sourcePaths, boolean debug, String classpath) {
        this.projectRoot = projectRoot;
        this.outputFile = outputFile;
        this.autoDiscover = autoDiscover;
        this.sourcePaths = sourcePaths;
        this.debug = debug;
        this.classpath = classpath;
    }

    public Path getProjectRoot() {
        return projectRoot;
    }

    public Path getOutputFile() {
        return outputFile;
    }

    public boolean isAutoDiscover() {
        return autoDiscover;
    }

    public List<Path> getSourcePaths() {
        return sourcePaths;
    }

    public boolean isDebug() {
        return debug;
    }

    public String getClasspath() {
        return classpath;
    }

    public boolean hasClasspath() {
        return classpath != null && !classpath.isEmpty();
    }
}
