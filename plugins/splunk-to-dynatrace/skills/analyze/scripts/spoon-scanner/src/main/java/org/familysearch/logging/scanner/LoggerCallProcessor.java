package org.familysearch.logging.scanner;

import spoon.processing.AbstractProcessor;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.code.CtFieldRead;
import spoon.reflect.code.CtExpression;
import spoon.reflect.cu.SourcePosition;
import spoon.reflect.cu.position.NoSourcePosition;
import spoon.reflect.reference.CtTypeReference;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Spoon processor that discovers logger method calls.
 *
 * Detection strategies (noclasspath mode with type validation):
 * 1. Known logger field: Target is a logger field identified in Phase 1 (most reliable)
 * 2. Type-verified method: Method name matches log levels AND receiver type is Logger (semantic validation)
 *
 * Removed in v3.0.1:
 * - Strategy 3 (regex pattern matching on scope name) - too broad, caused 80% false positive rate
 */
public class LoggerCallProcessor extends AbstractProcessor<CtInvocation<?>> {
    private final List<LoggerCandidate> candidates = new ArrayList<>();
    private final ScannerConfig config;
    private final Set<String> knownLoggerFields;
    private final Map<String, LoggerFieldProcessor.InheritedLoggerInfo> inheritedLoggers;

    private static final Set<String> LOG_LEVELS = Set.of(
        // Standard levels (SLF4J, Log4j, Logback)
        "trace", "debug", "info", "warn", "error", "fatal",
        // Log4j 2.x fluent API
        "atTrace", "atDebug", "atInfo", "atWarn", "atError", "atFatal",
        // Java Util Logging methods
        "finest", "finer", "fine", "config", "warning", "severe"
    );

    public LoggerCallProcessor(ScannerConfig config, Set<String> knownLoggerFields,
                              Map<String, LoggerFieldProcessor.InheritedLoggerInfo> inheritedLoggers) {
        this.config = config;
        this.knownLoggerFields = knownLoggerFields;
        this.inheritedLoggers = inheritedLoggers;
    }

    @Override
    public void process(CtInvocation<?> invocation) {
        if (invocation.getPosition() instanceof NoSourcePosition) {
            return;
        }

        if (isLoggerCall(invocation)) {
            SourcePosition pos = invocation.getPosition();
            String file = pos.getFile() != null ? pos.getFile().getAbsolutePath() : "unknown";
            int line = pos.getLine();
            int column = pos.getColumn();
            String methodName = invocation.getExecutable().getSimpleName();
            String loggerName = extractLoggerName(invocation);

            // NEW: Extract receiver type for validation
            String receiverType = extractReceiverType(invocation);

            // NEW: Extract inherited logger info
            LoggerFieldProcessor.InheritedLoggerInfo inheritedInfo = getInheritedLoggerInfo(invocation);
            String inheritedFrom = inheritedInfo != null ? inheritedInfo.getParentClass() : null;

            String strategy = getDetectionStrategy(invocation, receiverType);
            boolean needsValidation = strategy.equals("method_name_no_type") ||
                                      receiverType == null;

            LoggerCandidate candidate = new LoggerCandidate(
                CandidateType.LOGGER_CALL,
                file, line, column,
                loggerName, receiverType, methodName,  // receiverType added here
                needsValidation,
                strategy,
                inheritedFrom  // NEW: Add inherited source
            );

            candidates.add(candidate);

            if (config.isDebug()) {
                System.out.printf("[DEBUG] Found logger call: %s.%s() at %s:%d (type: %s, strategy: %s%s)%n",
                    loggerName, methodName, file, line, receiverType, strategy,
                    inheritedFrom != null ? ", inherited from: " + inheritedFrom : "");
            }
        }
    }

    /**
     * Extract the type of the receiver expression (target of method call).
     *
     * In noclasspath mode, Spoon can still infer types from:
     * - Import statements (org.slf4j.Logger)
     * - Field declarations
     * - Variable declarations
     *
     * @param invocation The method invocation
     * @return Type name (qualified if available, simple otherwise), or null
     */
    private String extractReceiverType(CtInvocation<?> invocation) {
        CtExpression<?> target = invocation.getTarget();
        if (target == null) {
            return null;
        }

        // Strategy 1: Get type from CtFieldRead (most common: LOGGER.info())
        if (target instanceof CtFieldRead<?>) {
            CtFieldRead<?> fieldRead = (CtFieldRead<?>) target;
            CtTypeReference<?> typeRef = fieldRead.getVariable().getType();
            if (typeRef != null) {
                String qualifiedName = typeRef.getQualifiedName();
                if (qualifiedName != null && !qualifiedName.isEmpty()) {
                    return qualifiedName;  // e.g., "org.slf4j.Logger"
                }
                return typeRef.getSimpleName();  // e.g., "Logger"
            }
        }

        // Strategy 2: Get type from target expression directly
        CtTypeReference<?> typeRef = target.getType();
        if (typeRef != null) {
            String qualifiedName = typeRef.getQualifiedName();
            if (qualifiedName != null && !qualifiedName.isEmpty()) {
                return qualifiedName;
            }
            return typeRef.getSimpleName();
        }

        return null;
    }

    /**
     * Check if a type name indicates a Logger type.
     *
     * Supports multiple logging frameworks:
     * - SLF4J: org.slf4j.Logger
     * - Log4j 1.x: org.apache.log4j.Logger, org.apache.log4j.Category
     * - Log4j 2.x: org.apache.logging.log4j.Logger
     * - Logback: ch.qos.logback.classic.Logger
     * - Apache Commons Logging: org.apache.commons.logging.Log
     * - Java Util Logging: java.util.logging.Logger
     *
     * @param typeName The type name to check
     * @return True if type is a Logger
     */
    private boolean isLoggerType(String typeName) {
        if (typeName == null || typeName.isEmpty()) {
            return false;
        }

        // SLF4J (standard facade)
        if (typeName.equals("org.slf4j.Logger") || typeName.equals("Logger")) {
            return true;
        }

        // Log4j 1.x (org.apache.log4j.Logger, org.apache.log4j.Category)
        if (typeName.startsWith("org.apache.log4j.")) {
            return true;
        }

        // Log4j 2.x (org.apache.logging.log4j.Logger)
        if (typeName.startsWith("org.apache.logging.log4j.")) {
            return true;
        }

        // Logback (ch.qos.logback.classic.Logger)
        if (typeName.startsWith("ch.qos.logback.")) {
            return true;
        }

        // Apache Commons Logging (org.apache.commons.logging.Log)
        if (typeName.startsWith("org.apache.commons.logging.")) {
            return true;
        }

        // Java Util Logging (java.util.logging.Logger)
        if (typeName.startsWith("java.util.logging.")) {
            return true;
        }

        // Fallback: contains "Logger" or "Log" (covers edge cases and simple names)
        return typeName.contains("Logger") ||
               typeName.contains("slf4j") ||
               typeName.contains("log4j") ||
               typeName.equals("Log");  // Commons Logging simple name
    }

    private boolean isLoggerCall(CtInvocation<?> invocation) {
        String methodName = invocation.getExecutable().getSimpleName();
        CtExpression<?> target = invocation.getTarget();

        // Strategy 1: Called on known logger field (from Phase 1)
        // This includes both locally declared AND inherited logger fields
        if (target instanceof CtFieldRead<?>) {
            CtFieldRead<?> fieldRead = (CtFieldRead<?>) target;
            String fieldName = fieldRead.getVariable().getSimpleName();

            // Check local logger fields
            if (knownLoggerFields.contains(fieldName)) {
                return true;  // High confidence - known local logger field
            }

            // Check inherited logger fields
            // Need to determine the current class context
            spoon.reflect.declaration.CtType<?> enclosingType = invocation.getParent(spoon.reflect.declaration.CtType.class);
            if (enclosingType != null) {
                String className = enclosingType.getQualifiedName();
                String inheritedKey = className + ":" + fieldName;

                if (inheritedLoggers.containsKey(inheritedKey)) {
                    return true;  // High confidence - inherited logger field
                }
            }
        }

        // Strategy 2: Method name matches log levels AND receiver type is Logger
        // This catches loggers we missed in Phase 1 (local variables, parameters, etc.)
        if (LOG_LEVELS.contains(methodName)) {
            String receiverType = extractReceiverType(invocation);
            if (isLoggerType(receiverType)) {
                return true;  // Verified logger call
            }

            // If we can't determine type, mark for validation (noclasspath limitation)
            if (receiverType == null) {
                // Conservative: assume it might be a logger if method name matches
                // But mark needsValidation=true so Python can verify
                return true;
            }

            // Receiver type is known and NOT a Logger - definitely not a logger call
            return false;
        }

        // Strategy 3 REMOVED - regex pattern was too broad and unreliable
        // All other cases are not logger calls
        return false;
    }

    private String getDetectionStrategy(CtInvocation<?> invocation, String receiverType) {
        String methodName = invocation.getExecutable().getSimpleName();

        // Strategy 1: Known logger field (most reliable)
        CtExpression<?> target = invocation.getTarget();
        if (target instanceof CtFieldRead<?>) {
            CtFieldRead<?> fieldRead = (CtFieldRead<?>) target;
            String fieldName = fieldRead.getVariable().getSimpleName();

            // Check local logger field
            if (knownLoggerFields.contains(fieldName)) {
                return "known_logger_field";
            }

            // Check inherited logger field
            spoon.reflect.declaration.CtType<?> enclosingType = invocation.getParent(spoon.reflect.declaration.CtType.class);
            if (enclosingType != null) {
                String className = enclosingType.getQualifiedName();
                String inheritedKey = className + ":" + fieldName;

                if (inheritedLoggers.containsKey(inheritedKey)) {
                    return "inherited_logger_field";
                }
            }
        }

        // Strategy 2: Method name + type verification
        if (LOG_LEVELS.contains(methodName)) {
            if (isLoggerType(receiverType)) {
                return "method_name_with_type";
            }
            return "method_name_no_type";  // Needs validation
        }

        return "unknown";
    }

    private String extractLoggerName(CtInvocation<?> invocation) {
        CtExpression<?> target = invocation.getTarget();
        if (target instanceof CtFieldRead<?>) {
            CtFieldRead<?> fieldRead = (CtFieldRead<?>) target;
            return fieldRead.getVariable().getSimpleName();
        }
        return null;
    }

    /**
     * Extract information about inherited logger for output.
     *
     * @param invocation Method invocation
     * @return InheritedLoggerInfo if this is an inherited logger call, null otherwise
     */
    private LoggerFieldProcessor.InheritedLoggerInfo getInheritedLoggerInfo(CtInvocation<?> invocation) {
        CtExpression<?> target = invocation.getTarget();
        if (!(target instanceof CtFieldRead<?>)) {
            return null;
        }

        CtFieldRead<?> fieldRead = (CtFieldRead<?>) target;
        String fieldName = fieldRead.getVariable().getSimpleName();

        // Determine current class context
        spoon.reflect.declaration.CtType<?> enclosingType = invocation.getParent(spoon.reflect.declaration.CtType.class);
        if (enclosingType != null) {
            String className = enclosingType.getQualifiedName();
            String inheritedKey = className + ":" + fieldName;

            return inheritedLoggers.get(inheritedKey);  // Returns null if not found
        }

        return null;
    }

    public List<LoggerCandidate> getCandidates() {
        return candidates;
    }
}
