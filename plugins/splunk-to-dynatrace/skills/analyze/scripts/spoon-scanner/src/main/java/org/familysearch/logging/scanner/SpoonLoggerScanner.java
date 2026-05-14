package org.familysearch.logging.scanner;

import spoon.Launcher;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Main entry point for Spoon-based logger discovery scanner.
 *
 * Usage:
 *   java -jar spoon-scanner.jar <project-root> <output-file> [--auto-discover] [--debug]
 *
 * Arguments:
 *   project-root   : Root directory of the project to scan
 *   output-file    : Path to output JSON file
 *   --auto-discover: Automatically discover src/main/java and src/test/java (optional)
 *   --debug        : Enable debug logging (optional)
 *
 * Example:
 *   java -jar spoon-scanner.jar /path/to/project output.json --auto-discover
 */
public class SpoonLoggerScanner {
    public static void main(String[] args) {
        if (args.length < 2) {
            printUsage();
            System.exit(1);
        }

        Path projectRoot = Paths.get(args[0]);
        Path outputFile = Paths.get(args[1]);
        boolean autoDiscover = contains(args, "--auto-discover");
        boolean debug = contains(args, "--debug");

        // Validate project root
        if (!Files.exists(projectRoot) || !Files.isDirectory(projectRoot)) {
            System.err.println("Error: Project root does not exist or is not a directory: " + projectRoot);
            System.exit(1);
        }

        ScannerConfig config = new ScannerConfig(
            projectRoot,
            outputFile,
            autoDiscover,
            new ArrayList<>(),
            debug
        );

        try {
            List<LoggerCandidate> candidates = scan(config);

            JsonOutputWriter writer = new JsonOutputWriter();
            writer.write(candidates, outputFile, config);

            System.out.printf("Scan complete. Found %d candidates (%d declarations, %d calls)%n",
                candidates.size(),
                candidates.stream().filter(c -> c.getType() == CandidateType.LOGGER_DECLARATION).count(),
                candidates.stream().filter(c -> c.getType() == CandidateType.LOGGER_CALL).count());

            System.out.println("Output written to: " + outputFile.toAbsolutePath());

        } catch (Exception e) {
            System.err.println("Error during scan: " + e.getMessage());
            if (debug) {
                e.printStackTrace();
            }
            System.exit(1);
        }
    }

    private static List<LoggerCandidate> scan(ScannerConfig config) {
        Launcher launcher = new Launcher();

        // Configure Spoon for fast mode
        launcher.getEnvironment().setNoClasspath(true);      // Fast mode
        launcher.getEnvironment().setAutoImports(true);      // Import resolution
        launcher.getEnvironment().setCommentEnabled(false);  // Skip comments
        launcher.getEnvironment().setComplianceLevel(17);    // Java 17

        if (config.isDebug()) {
            launcher.getEnvironment().setLevel("INFO");
            System.out.println("[DEBUG] Spoon configured in noclasspath mode");
        } else {
            launcher.getEnvironment().setLevel("ERROR");
        }

        // Add input resources
        if (config.isAutoDiscover()) {
            int sourcesAdded = 0;

            // Try single-module project structure first
            Path mainJava = config.getProjectRoot().resolve("src/main/java");
            Path testJava = config.getProjectRoot().resolve("src/test/java");

            if (Files.exists(mainJava)) {
                launcher.addInputResource(mainJava.toString());
                sourcesAdded++;
                if (config.isDebug()) {
                    System.out.println("[DEBUG] Added source path: " + mainJava);
                }
            }
            if (Files.exists(testJava)) {
                launcher.addInputResource(testJava.toString());
                sourcesAdded++;
                if (config.isDebug()) {
                    System.out.println("[DEBUG] Added source path: " + testJava);
                }
            }

            // If single-module structure not found, try multi-module Maven structure
            if (sourcesAdded == 0) {
                if (config.isDebug()) {
                    System.out.println("[DEBUG] Single-module structure not found, checking for multi-module Maven project...");
                }

                try {
                    // Find all modules with src/main/java or src/test/java
                    Files.walk(config.getProjectRoot(), 5)
                        .filter(Files::isDirectory)
                        .filter(p -> p.endsWith("src/main/java") || p.endsWith("src/test/java"))
                        .forEach(p -> {
                            launcher.addInputResource(p.toString());
                            if (config.isDebug()) {
                                System.out.println("[DEBUG] Added source path: " + p);
                            }
                        });

                    // Count how many we found
                    sourcesAdded = (int) Files.walk(config.getProjectRoot(), 5)
                        .filter(Files::isDirectory)
                        .filter(p -> p.endsWith("src/main/java") || p.endsWith("src/test/java"))
                        .count();

                } catch (IOException e) {
                    System.err.println("Warning: Error scanning for multi-module structure: " + e.getMessage());
                }
            }

            if (sourcesAdded == 0) {
                System.err.println("Warning: No source directories found at standard locations");
            } else if (config.isDebug()) {
                System.out.println("[DEBUG] Total source directories added: " + sourcesAdded);
            }
        } else {
            for (Path sourcePath : config.getSourcePaths()) {
                if (Files.exists(sourcePath)) {
                    launcher.addInputResource(sourcePath.toString());
                    if (config.isDebug()) {
                        System.out.println("[DEBUG] Added source path: " + sourcePath);
                    }
                }
            }
        }

        // Build model
        if (config.isDebug()) {
            System.out.println("[DEBUG] Building Spoon model...");
        }
        launcher.buildModel();

        // Phase 1: Find logger field declarations
        if (config.isDebug()) {
            System.out.println("[DEBUG] Phase 1: Discovering logger fields...");
        }
        LoggerFieldProcessor fieldProcessor = new LoggerFieldProcessor(config);
        launcher.addProcessor(fieldProcessor);
        launcher.process();

        if (config.isDebug()) {
            System.out.printf("[DEBUG] Found %d logger declarations%n", fieldProcessor.getCandidates().size());
        }

        // Phase 2: Find logger calls
        Set<String> knownLoggerFields = fieldProcessor.getCandidates().stream()
            .map(LoggerCandidate::getName)
            .collect(Collectors.toSet());

        if (config.isDebug()) {
            System.out.println("[DEBUG] Phase 2: Discovering logger calls...");
            System.out.println("[DEBUG] Known logger fields: " + knownLoggerFields);
        }

        // Create new launcher for second processor (fresh processing)
        Launcher launcher2 = new Launcher();
        launcher2.getEnvironment().setNoClasspath(true);
        launcher2.getEnvironment().setAutoImports(true);
        launcher2.getEnvironment().setCommentEnabled(false);
        launcher2.getEnvironment().setComplianceLevel(17);
        launcher2.getEnvironment().setLevel(config.isDebug() ? "INFO" : "ERROR");

        // Re-add input resources (same discovery logic as Phase 1)
        if (config.isAutoDiscover()) {
            // Try single-module project structure first
            Path mainJava = config.getProjectRoot().resolve("src/main/java");
            Path testJava = config.getProjectRoot().resolve("src/test/java");

            int sourcesAdded = 0;
            if (Files.exists(mainJava)) {
                launcher2.addInputResource(mainJava.toString());
                sourcesAdded++;
            }
            if (Files.exists(testJava)) {
                launcher2.addInputResource(testJava.toString());
                sourcesAdded++;
            }

            // If single-module structure not found, try multi-module Maven structure
            if (sourcesAdded == 0) {
                try {
                    Files.walk(config.getProjectRoot(), 5)
                        .filter(Files::isDirectory)
                        .filter(p -> p.endsWith("src/main/java") || p.endsWith("src/test/java"))
                        .forEach(p -> launcher2.addInputResource(p.toString()));
                } catch (IOException e) {
                    // Already reported in Phase 1
                }
            }
        } else {
            for (Path sourcePath : config.getSourcePaths()) {
                if (Files.exists(sourcePath)) {
                    launcher2.addInputResource(sourcePath.toString());
                }
            }
        }

        launcher2.buildModel();
        LoggerCallProcessor callProcessor = new LoggerCallProcessor(config, knownLoggerFields);
        launcher2.addProcessor(callProcessor);
        launcher2.process();

        if (config.isDebug()) {
            System.out.printf("[DEBUG] Found %d logger calls%n", callProcessor.getCandidates().size());
        }

        // Combine results
        List<LoggerCandidate> allCandidates = new ArrayList<>();
        allCandidates.addAll(fieldProcessor.getCandidates());
        allCandidates.addAll(callProcessor.getCandidates());

        return allCandidates;
    }

    private static boolean contains(String[] args, String flag) {
        for (String arg : args) {
            if (arg.equals(flag)) {
                return true;
            }
        }
        return false;
    }

    private static void printUsage() {
        System.out.println("Spoon Logger Scanner v1.0.1");
        System.out.println();
        System.out.println("Usage: java -jar spoon-scanner.jar <project-root> <output-file> [options]");
        System.out.println();
        System.out.println("Arguments:");
        System.out.println("  project-root      Root directory of the project to scan");
        System.out.println("  output-file       Path to output JSON file");
        System.out.println();
        System.out.println("Options:");
        System.out.println("  --auto-discover   Automatically discover src/main/java and src/test/java");
        System.out.println("  --debug           Enable debug logging");
        System.out.println();
        System.out.println("Example:");
        System.out.println("  java -jar spoon-scanner.jar /path/to/project output.json --auto-discover");
    }
}
