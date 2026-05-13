package org.familysearch.logging.scanner;

/**
 * Represents a logger declaration or logger call found during scanning.
 */
public class LoggerCandidate {
    private final CandidateType type;
    private final String file;
    private final int line;
    private final int column;
    private final String name;
    private final String typeName;
    private final String methodName;
    private final boolean needsValidation;
    private final String detectionStrategy;

    public LoggerCandidate(CandidateType type, String file, int line, int column,
                           String name, String typeName, String methodName,
                           boolean needsValidation, String detectionStrategy) {
        this.type = type;
        this.file = file;
        this.line = line;
        this.column = column;
        this.name = name;
        this.typeName = typeName;
        this.methodName = methodName;
        this.needsValidation = needsValidation;
        this.detectionStrategy = detectionStrategy;
    }

    public CandidateType getType() {
        return type;
    }

    public String getFile() {
        return file;
    }

    public int getLine() {
        return line;
    }

    public int getColumn() {
        return column;
    }

    public String getName() {
        return name;
    }

    public String getTypeName() {
        return typeName;
    }

    public String getMethodName() {
        return methodName;
    }

    public boolean isNeedsValidation() {
        return needsValidation;
    }

    public String getDetectionStrategy() {
        return detectionStrategy;
    }
}
