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
 * 2. Import statement includes org.slf4j.Logger, org.apache.log4j.Logger, etc.
 * 3. Initializer contains "LoggerFactory", "Logger.getLogger", "LogFactory.getLog"
 * 4. Lombok @Slf4j, @Log4j, @Log4j2, @CommonsLog annotations
 *
 * Supported logging frameworks:
 * - SLF4J: org.slf4j.Logger
 * - Log4j 1.x: org.apache.log4j.Logger, org.apache.log4j.Category
 * - Log4j 2.x: org.apache.logging.log4j.Logger
 * - Logback: ch.qos.logback.classic.Logger
 * - Apache Commons Logging: org.apache.commons.logging.Log
 * - Java Util Logging: java.util.logging.Logger
 * - Lombok: @Slf4j, @Log4j, @Log4j2, @CommonsLog
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
        // Strategy 1: Type name contains "Logger", "Log", or "Category"
        String typeName = field.getType().getSimpleName();
        if (typeName.contains("Logger") || typeName.equals("Log") || typeName.equals("Category")) {
            return true;
        }

        // Strategy 2: Initializer contains logger factory patterns
        if (field.getDefaultExpression() != null) {
            String initializer = field.getDefaultExpression().toString();
            if (initializer.contains("LoggerFactory") ||    // SLF4J, Logback
                initializer.contains("Logger.getLogger") || // Log4j, JUL
                initializer.contains("LogManager.getLogger") || // Log4j 2.x
                initializer.contains("LogFactory.getLog")) { // Commons Logging
                return true;
            }
        }

        // Strategy 3: Lombok annotations (generates 'log' field)
        CtType<?> declaringType = field.getDeclaringType();
        if (declaringType != null && field.getSimpleName().equals("log")) {
            boolean hasLombokLogger = declaringType.getAnnotations().stream()
                .anyMatch(ann -> {
                    String annStr = ann.toString();
                    return annStr.contains("Slf4j") ||      // @Slf4j
                           annStr.contains("Log4j") ||      // @Log4j, @Log4j2
                           annStr.contains("CommonsLog") || // @CommonsLog
                           annStr.contains("Log");          // @Log (JUL)
                });
            if (hasLombokLogger) {
                return true;
            }
        }

        return false;
    }

    private String getDetectionStrategy(CtField<?> field) {
        String typeName = field.getType().getSimpleName();
        if (typeName.contains("Logger") || typeName.equals("Log") || typeName.equals("Category")) {
            return "type_name";
        }

        if (field.getDefaultExpression() != null) {
            String initializer = field.getDefaultExpression().toString();
            if (initializer.contains("LoggerFactory") ||
                initializer.contains("Logger.getLogger") ||
                initializer.contains("LogManager.getLogger") ||
                initializer.contains("LogFactory.getLog")) {
                return "logger_factory_pattern";
            }
        }

        CtType<?> declaringType = field.getDeclaringType();
        if (declaringType != null && field.getSimpleName().equals("log")) {
            boolean hasLombokLogger = declaringType.getAnnotations().stream()
                .anyMatch(ann -> {
                    String annStr = ann.toString();
                    return annStr.contains("Slf4j") ||
                           annStr.contains("Log4j") ||
                           annStr.contains("CommonsLog") ||
                           annStr.contains("Log");
                });
            if (hasLombokLogger) {
                return "lombok_annotation";
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
