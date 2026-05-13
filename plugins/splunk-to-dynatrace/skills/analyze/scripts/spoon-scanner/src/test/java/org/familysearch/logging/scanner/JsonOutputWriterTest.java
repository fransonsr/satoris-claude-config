package org.familysearch.logging.scanner;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.FileReader;
import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class JsonOutputWriterTest {

    @TempDir
    Path tempDir;

    private ScannerConfig createTestConfig() {
        return new ScannerConfig(
            Paths.get("/project/root"),
            tempDir.resolve("output.json"),
            false,
            Collections.emptyList(),
            false
        );
    }

    @Test
    void shouldWriteValidJson() throws IOException {
        JsonOutputWriter writer = new JsonOutputWriter();
        Path outputFile = tempDir.resolve("test-output.json");

        LoggerCandidate declaration = new LoggerCandidate(
            CandidateType.LOGGER_DECLARATION,
            "/path/to/MyClass.java",
            23,
            5,
            "LOGGER",
            "org.slf4j.Logger",
            null,
            false,
            "type_name"
        );

        LoggerCandidate call = new LoggerCandidate(
            CandidateType.LOGGER_CALL,
            "/path/to/MyClass.java",
            45,
            9,
            "LOGGER",
            null,
            "info",
            false,
            "method_name"
        );

        List<LoggerCandidate> candidates = Arrays.asList(declaration, call);
        ScannerConfig config = createTestConfig();

        writer.write(candidates, outputFile, config);

        assertTrue(outputFile.toFile().exists());

        // Verify JSON structure
        Gson gson = new Gson();
        try (FileReader reader = new FileReader(outputFile.toFile())) {
            JsonObject json = gson.fromJson(reader, JsonObject.class);

            assertTrue(json.has("metadata"));
            assertTrue(json.has("candidates"));

            JsonObject metadata = json.getAsJsonObject("metadata");
            assertEquals("spoon", metadata.get("scanner").getAsString());
            assertEquals("1.0.0", metadata.get("version").getAsString());
            assertEquals(2, metadata.get("total_candidates").getAsInt());
            assertEquals(1, metadata.get("declarations").getAsInt());
            assertEquals(1, metadata.get("calls").getAsInt());
        }
    }

    @Test
    void shouldWriteEmptyCandidatesList() throws IOException {
        JsonOutputWriter writer = new JsonOutputWriter();
        Path outputFile = tempDir.resolve("empty-output.json");

        writer.write(Collections.emptyList(), outputFile, createTestConfig());

        assertTrue(outputFile.toFile().exists());

        Gson gson = new Gson();
        try (FileReader reader = new FileReader(outputFile.toFile())) {
            JsonObject json = gson.fromJson(reader, JsonObject.class);
            JsonObject metadata = json.getAsJsonObject("metadata");
            assertEquals(0, metadata.get("total_candidates").getAsInt());
        }
    }

    @Test
    void shouldIncludeTimestamp() throws IOException {
        JsonOutputWriter writer = new JsonOutputWriter();
        Path outputFile = tempDir.resolve("timestamp-output.json");

        long before = System.currentTimeMillis();
        writer.write(Collections.emptyList(), outputFile, createTestConfig());
        long after = System.currentTimeMillis();

        Gson gson = new Gson();
        try (FileReader reader = new FileReader(outputFile.toFile())) {
            JsonObject json = gson.fromJson(reader, JsonObject.class);
            JsonObject metadata = json.getAsJsonObject("metadata");
            long timestamp = metadata.get("timestamp").getAsLong();

            assertTrue(timestamp >= before);
            assertTrue(timestamp <= after);
        }
    }
}
