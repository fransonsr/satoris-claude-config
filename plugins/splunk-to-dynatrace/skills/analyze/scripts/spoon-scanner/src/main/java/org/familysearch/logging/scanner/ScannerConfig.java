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

    public ScannerConfig(Path projectRoot, Path outputFile, boolean autoDiscover,
                         List<Path> sourcePaths, boolean debug) {
        this.projectRoot = projectRoot;
        this.outputFile = outputFile;
        this.autoDiscover = autoDiscover;
        this.sourcePaths = sourcePaths;
        this.debug = debug;
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
}
