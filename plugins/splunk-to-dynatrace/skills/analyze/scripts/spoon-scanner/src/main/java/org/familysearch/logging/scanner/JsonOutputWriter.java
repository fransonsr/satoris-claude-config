package org.familysearch.logging.scanner;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.FileWriter;
import java.io.IOException;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Writes logger candidates to JSON format.
 *
 * Output format:
 * {
 *   "metadata": {
 *     "scanner": "spoon",
 *     "version": "1.0.0",
 *     "timestamp": 1715616123456,
 *     "project_root": "/path/to/project",
 *     "total_candidates": 1237,
 *     "declarations": 252,
 *     "calls": 985
 *   },
 *   "candidates": [ ... ]
 * }
 */
public class JsonOutputWriter {
    private final Gson gson;

    public JsonOutputWriter() {
        this.gson = new GsonBuilder()
            .setPrettyPrinting()
            .create();
    }

    public void write(List<LoggerCandidate> candidates, Path outputFile, ScannerConfig config) throws IOException {
        Map<String, Object> output = new HashMap<>();

        // Metadata
        Map<String, Object> metadata = new HashMap<>();
        metadata.put("scanner", "spoon");
        metadata.put("version", "1.0.0");
        metadata.put("timestamp", System.currentTimeMillis());
        metadata.put("project_root", config.getProjectRoot().toString());
        metadata.put("total_candidates", candidates.size());

        long declarations = candidates.stream()
            .filter(c -> c.getType() == CandidateType.LOGGER_DECLARATION)
            .count();
        long calls = candidates.stream()
            .filter(c -> c.getType() == CandidateType.LOGGER_CALL)
            .count();

        metadata.put("declarations", declarations);
        metadata.put("calls", calls);

        output.put("metadata", metadata);
        output.put("candidates", candidates);

        try (FileWriter writer = new FileWriter(outputFile.toFile())) {
            gson.toJson(output, writer);
        }
    }
}
