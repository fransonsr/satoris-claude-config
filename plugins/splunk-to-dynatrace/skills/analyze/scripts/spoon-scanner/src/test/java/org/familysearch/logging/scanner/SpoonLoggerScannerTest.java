package org.familysearch.logging.scanner;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.FileReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpoonLoggerScannerTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldScanSimpleJavaProject() throws IOException {
        // Create a simple Java project structure
        Path srcDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(srcDir);

        String javaCode = """
            package com.example;
            import org.slf4j.Logger;
            import org.slf4j.LoggerFactory;

            public class Service {
                private static final Logger LOGGER = LoggerFactory.getLogger(Service.class);

                public void process() {
                    LOGGER.info("Processing started");
                    LOGGER.debug("Debug information");
                    LOGGER.error("An error occurred");
                }
            }
            """;

        Files.writeString(srcDir.resolve("Service.java"), javaCode);

        Path outputFile = tempDir.resolve("output.json");

        // Run scanner
        String[] args = {
            tempDir.toString(),
            outputFile.toString(),
            "--auto-discover"
        };

        SpoonLoggerScanner.main(args);

        // Verify output file exists
        assertTrue(Files.exists(outputFile));

        // Verify JSON content
        Gson gson = new Gson();
        try (FileReader reader = new FileReader(outputFile.toFile())) {
            JsonObject json = gson.fromJson(reader, JsonObject.class);

            JsonObject metadata = json.getAsJsonObject("metadata");
            assertEquals("spoon", metadata.get("scanner").getAsString());
            assertEquals("1.0.0", metadata.get("version").getAsString());

            // Should find 1 declaration + 3 calls = 4 total
            assertTrue(metadata.get("total_candidates").getAsInt() >= 4);
            assertEquals(1, metadata.get("declarations").getAsInt());
            assertTrue(metadata.get("calls").getAsInt() >= 3);

            JsonArray candidates = json.getAsJsonArray("candidates");
            assertTrue(candidates.size() >= 4);

            // Verify declaration
            boolean foundDeclaration = false;
            for (int i = 0; i < candidates.size(); i++) {
                JsonObject candidate = candidates.get(i).getAsJsonObject();
                if (candidate.get("type").getAsString().equals("LOGGER_DECLARATION")) {
                    foundDeclaration = true;
                    assertEquals("LOGGER", candidate.get("name").getAsString());
                }
            }
            assertTrue(foundDeclaration);

            // Verify calls
            long infoCalls = 0;
            long debugCalls = 0;
            long errorCalls = 0;

            for (int i = 0; i < candidates.size(); i++) {
                JsonObject candidate = candidates.get(i).getAsJsonObject();
                if (candidate.get("type").getAsString().equals("LOGGER_CALL")) {
                    String methodName = candidate.get("methodName").getAsString();
                    if ("info".equals(methodName)) infoCalls++;
                    if ("debug".equals(methodName)) debugCalls++;
                    if ("error".equals(methodName)) errorCalls++;
                }
            }

            assertTrue(infoCalls >= 1);
            assertTrue(debugCalls >= 1);
            assertTrue(errorCalls >= 1);
        }
    }

    @Test
    void shouldHandleMultipleClasses() throws IOException {
        Path srcDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(srcDir);

        String class1 = """
            package com.example;
            import org.slf4j.Logger;

            public class Class1 {
                private Logger log;

                public void method1() {
                    log.info("Class1");
                }
            }
            """;

        String class2 = """
            package com.example;
            import org.slf4j.Logger;

            public class Class2 {
                private Logger logger;

                public void method2() {
                    logger.warn("Class2");
                }
            }
            """;

        Files.writeString(srcDir.resolve("Class1.java"), class1);
        Files.writeString(srcDir.resolve("Class2.java"), class2);

        Path outputFile = tempDir.resolve("output.json");

        String[] args = {
            tempDir.toString(),
            outputFile.toString(),
            "--auto-discover"
        };

        SpoonLoggerScanner.main(args);

        Gson gson = new Gson();
        try (FileReader reader = new FileReader(outputFile.toFile())) {
            JsonObject json = gson.fromJson(reader, JsonObject.class);
            JsonObject metadata = json.getAsJsonObject("metadata");

            // Should find 2 declarations + 2 calls = 4 total
            assertEquals(4, metadata.get("total_candidates").getAsInt());
            assertEquals(2, metadata.get("declarations").getAsInt());
            assertEquals(2, metadata.get("calls").getAsInt());
        }
    }

    @Test
    void shouldHandleJava16PlusSyntax() throws IOException {
        Path srcDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(srcDir);

        // Test with records (Java 16+)
        String recordCode = """
            package com.example;
            import org.slf4j.Logger;
            import org.slf4j.LoggerFactory;

            public record UserRecord(String name, int age) {
                private static final Logger LOGGER = LoggerFactory.getLogger(UserRecord.class);

                public void validate() {
                    LOGGER.info("Validating user: {}", name);
                }
            }
            """;

        Files.writeString(srcDir.resolve("UserRecord.java"), recordCode);

        Path outputFile = tempDir.resolve("output.json");

        String[] args = {
            tempDir.toString(),
            outputFile.toString(),
            "--auto-discover"
        };

        SpoonLoggerScanner.main(args);

        // Verify it completed without parse errors
        assertTrue(Files.exists(outputFile));

        Gson gson = new Gson();
        try (FileReader reader = new FileReader(outputFile.toFile())) {
            JsonObject json = gson.fromJson(reader, JsonObject.class);
            JsonObject metadata = json.getAsJsonObject("metadata");

            // Should find logger declaration and call in record
            assertTrue(metadata.get("total_candidates").getAsInt() >= 2);
        }
    }
}
