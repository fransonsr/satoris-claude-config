package org.familysearch.logging.scanner;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ScannerConfigTest {

    @Test
    void shouldCreateConfigWithAutoDiscover() {
        Path projectRoot = Paths.get("/path/to/project");
        Path outputFile = Paths.get("/tmp/output.json");

        ScannerConfig config = new ScannerConfig(
            projectRoot,
            outputFile,
            true,
            Collections.emptyList(),
            false
        );

        assertEquals(projectRoot, config.getProjectRoot());
        assertEquals(outputFile, config.getOutputFile());
        assertTrue(config.isAutoDiscover());
        assertTrue(config.getSourcePaths().isEmpty());
        assertFalse(config.isDebug());
    }

    @Test
    void shouldCreateConfigWithExplicitSourcePaths() {
        Path projectRoot = Paths.get("/path/to/project");
        Path outputFile = Paths.get("/tmp/output.json");
        List<Path> sourcePaths = Arrays.asList(
            Paths.get("/path/to/project/module1/src/main/java"),
            Paths.get("/path/to/project/module2/src/main/java")
        );

        ScannerConfig config = new ScannerConfig(
            projectRoot,
            outputFile,
            false,
            sourcePaths,
            true
        );

        assertEquals(projectRoot, config.getProjectRoot());
        assertEquals(outputFile, config.getOutputFile());
        assertFalse(config.isAutoDiscover());
        assertEquals(2, config.getSourcePaths().size());
        assertTrue(config.isDebug());
    }

    @Test
    void shouldEnableDebugMode() {
        ScannerConfig config = new ScannerConfig(
            Paths.get("."),
            Paths.get("/tmp/output.json"),
            true,
            Collections.emptyList(),
            true
        );

        assertTrue(config.isDebug());
    }
}
