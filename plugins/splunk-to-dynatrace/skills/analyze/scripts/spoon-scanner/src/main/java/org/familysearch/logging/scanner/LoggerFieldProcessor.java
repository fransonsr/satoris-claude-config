package org.familysearch.logging.scanner;

import spoon.processing.AbstractProcessor;
import spoon.reflect.declaration.CtField;
import spoon.reflect.declaration.CtType;
import spoon.reflect.reference.CtTypeReference;
import spoon.reflect.cu.SourcePosition;
import spoon.reflect.cu.position.NoSourcePosition;

import java.util.ArrayList;
import java.util.List;

/**
 * Spoon processor that discovers logger field declarations.
 *
 * Detection strategies (noclasspath mode):
 * 1. Type name contains "Logger" or "Log"
 * 2. Import statement includes org.slf4j.Logger
 * 3. Initializer contains "LoggerFactory"
 * 4. Lombok @Slf4j annotation (generates 'log' field)
 */
public class LoggerFieldProcessor extends AbstractProcessor<CtField<?>> {
    private final List<LoggerCandidate> candidates = new ArrayList<>();
    private final ScannerConfig config;

    public LoggerFieldProcessor(ScannerConfig config) {
        this.config = config;
    }

    @Override
    public void process(CtField<?> field) {
        if (field.getPosition() instanceof NoSourcePosition) {
            return;
        }

        if (isLoggerField(field)) {
            SourcePosition pos = field.getPosition();
            String file = pos.getFile() != null ? pos.getFile().getAbsolutePath() : "unknown";
            int line = pos.getLine();
            int column = pos.getColumn();
            String name = field.getSimpleName();
            String typeName = getTypeName(field);

            String strategy = getDetectionStrategy(field);
            boolean needsValidation = strategy.equals("heuristic_name_pattern") ||
                                      strategy.equals("heuristic_scope_pattern");

            LoggerCandidate candidate = new LoggerCandidate(
                CandidateType.LOGGER_DECLARATION,
                file, line, column,
                name, typeName, null,
                needsValidation,
                strategy
            );

            candidates.add(candidate);

            if (config.isDebug()) {
                System.out.printf("[DEBUG] Found logger field: %s at %s:%d (strategy: %s)%n",
                    name, file, line, strategy);
            }
        }
    }

    private boolean isLoggerField(CtField<?> field) {
        // Strategy 1: Type name contains "Logger" or "Log"
        String typeName = field.getType().getSimpleName();
        if (typeName.contains("Logger") || typeName.equals("Log")) {
            return true;
        }

        // Strategy 2: Initializer contains "LoggerFactory"
        if (field.getDefaultExpression() != null) {
            String initializer = field.getDefaultExpression().toString();
            if (initializer.contains("LoggerFactory")) {
                return true;
            }
        }

        // Strategy 3: Lombok @Slf4j annotation (generates 'log' field)
        CtType<?> declaringType = field.getDeclaringType();
        if (declaringType != null && field.getSimpleName().equals("log")) {
            boolean hasSlf4j = declaringType.getAnnotations().stream()
                .anyMatch(ann -> ann.toString().contains("Slf4j"));
            if (hasSlf4j) {
                return true;
            }
        }

        return false;
    }

    private String getDetectionStrategy(CtField<?> field) {
        String typeName = field.getType().getSimpleName();
        if (typeName.contains("Logger") || typeName.equals("Log")) {
            return "type_name";
        }

        if (field.getDefaultExpression() != null) {
            String initializer = field.getDefaultExpression().toString();
            if (initializer.contains("LoggerFactory")) {
                return "logger_factory_pattern";
            }
        }

        CtType<?> declaringType = field.getDeclaringType();
        if (declaringType != null && field.getSimpleName().equals("log")) {
            boolean hasSlf4j = declaringType.getAnnotations().stream()
                .anyMatch(ann -> ann.toString().contains("Slf4j"));
            if (hasSlf4j) {
                return "lombok_slf4j";
            }
        }

        return "heuristic_name_pattern";
    }

    private String getTypeName(CtField<?> field) {
        CtTypeReference<?> typeRef = field.getType();
        if (typeRef != null) {
            // Try to get qualified name, fall back to simple name in noclasspath mode
            String qualifiedName = typeRef.getQualifiedName();
            if (qualifiedName != null && !qualifiedName.isEmpty()) {
                return qualifiedName;
            }
            return typeRef.getSimpleName();
        }
        return "unknown";
    }

    public List<LoggerCandidate> getCandidates() {
        return candidates;
    }
}
