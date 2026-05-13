package org.familysearch.logging.scanner;

import spoon.processing.AbstractProcessor;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.code.CtFieldRead;
import spoon.reflect.code.CtExpression;
import spoon.reflect.cu.SourcePosition;
import spoon.reflect.cu.position.NoSourcePosition;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * Spoon processor that discovers logger method calls.
 *
 * Detection strategies (noclasspath mode):
 * 1. Method name matches known log levels (trace, debug, info, warn, error, atTrace, atDebug, atInfo, atWarn, atError)
 * 2. Target is a known logger field (from LoggerFieldProcessor)
 * 3. Target name matches logger pattern (fallback heuristic)
 */
public class LoggerCallProcessor extends AbstractProcessor<CtInvocation<?>> {
    private final List<LoggerCandidate> candidates = new ArrayList<>();
    private final ScannerConfig config;
    private final Set<String> knownLoggerFields;

    private static final Set<String> LOG_LEVELS = Set.of(
        "trace", "debug", "info", "warn", "error",
        "atTrace", "atDebug", "atInfo", "atWarn", "atError"
    );

    public LoggerCallProcessor(ScannerConfig config, Set<String> knownLoggerFields) {
        this.config = config;
        this.knownLoggerFields = knownLoggerFields;
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
            String strategy = getDetectionStrategy(invocation);
            boolean needsValidation = strategy.equals("heuristic_scope_pattern");

            LoggerCandidate candidate = new LoggerCandidate(
                CandidateType.LOGGER_CALL,
                file, line, column,
                loggerName, null, methodName,
                needsValidation,
                strategy
            );

            candidates.add(candidate);

            if (config.isDebug()) {
                System.out.printf("[DEBUG] Found logger call: %s.%s() at %s:%d (strategy: %s)%n",
                    loggerName, methodName, file, line, strategy);
            }
        }
    }

    private boolean isLoggerCall(CtInvocation<?> invocation) {
        String methodName = invocation.getExecutable().getSimpleName();

        // Strategy 1: Method name matches log levels
        if (LOG_LEVELS.contains(methodName)) {
            return true;
        }

        // Strategy 2: Called on known logger field
        CtExpression<?> target = invocation.getTarget();
        if (target instanceof CtFieldRead<?>) {
            CtFieldRead<?> fieldRead = (CtFieldRead<?>) target;
            String fieldName = fieldRead.getVariable().getSimpleName();

            if (knownLoggerFields.contains(fieldName)) {
                return true;
            }
        }

        // Strategy 3: Scope name pattern (fallback)
        if (target != null) {
            String targetName = target.toString();
            if (targetName.matches("(?i).*(logger|log).*")) {
                return true;
            }
        }

        return false;
    }

    private String getDetectionStrategy(CtInvocation<?> invocation) {
        String methodName = invocation.getExecutable().getSimpleName();

        // Check known logger field first (more specific)
        CtExpression<?> target = invocation.getTarget();
        if (target instanceof CtFieldRead<?>) {
            CtFieldRead<?> fieldRead = (CtFieldRead<?>) target;
            String fieldName = fieldRead.getVariable().getSimpleName();

            if (knownLoggerFields.contains(fieldName)) {
                return "known_logger_field";
            }
        }

        // Then check method name
        if (LOG_LEVELS.contains(methodName)) {
            return "method_name";
        }

        return "heuristic_scope_pattern";
    }

    private String extractLoggerName(CtInvocation<?> invocation) {
        CtExpression<?> target = invocation.getTarget();
        if (target instanceof CtFieldRead<?>) {
            CtFieldRead<?> fieldRead = (CtFieldRead<?>) target;
            return fieldRead.getVariable().getSimpleName();
        }
        return null;
    }

    public List<LoggerCandidate> getCandidates() {
        return candidates;
    }
}
