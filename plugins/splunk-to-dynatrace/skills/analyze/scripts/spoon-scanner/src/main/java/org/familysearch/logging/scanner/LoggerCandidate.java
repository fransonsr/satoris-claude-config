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
    private final String framework;
    private final String inheritedFrom;  // Nullable: parent class name if logger is inherited

    public LoggerCandidate(CandidateType type, String file, int line, int column,
                           String name, String typeName, String methodName,
                           boolean needsValidation, String detectionStrategy) {
        this(type, file, line, column, name, typeName, methodName, needsValidation, detectionStrategy, null);
    }

    public LoggerCandidate(CandidateType type, String file, int line, int column,
                           String name, String typeName, String methodName,
                           boolean needsValidation, String detectionStrategy, String inheritedFrom) {
        this.type = type;
        this.file = file;
        this.line = line;
        this.column = column;
        this.name = name;
        this.typeName = typeName;
        this.methodName = methodName;
        this.needsValidation = needsValidation;
        this.detectionStrategy = detectionStrategy;
        this.framework = detectFramework(typeName);
        this.inheritedFrom = inheritedFrom;
    }

    /**
     * Detect logging framework from type name.
     *
     * @param typeName Qualified or simple type name
     * @return Framework name: "slf4j", "log4j", "log4j2", "logback", "commons-logging", "jul", "unknown"
     */
    private static String detectFramework(String typeName) {
        if (typeName == null || typeName.isEmpty()) {
            return "unknown";
        }

        // SLF4J (facade)
        if (typeName.startsWith("org.slf4j.")) {
            return "slf4j";
        }

        // Log4j 1.x
        if (typeName.startsWith("org.apache.log4j.")) {
            return "log4j";
        }

        // Log4j 2.x
        if (typeName.startsWith("org.apache.logging.log4j.")) {
            return "log4j2";
        }

        // Logback (implementation of SLF4J)
        if (typeName.startsWith("ch.qos.logback.")) {
            return "logback";
        }

        // Apache Commons Logging
        if (typeName.startsWith("org.apache.commons.logging.")) {
            return "commons-logging";
        }

        // Java Util Logging
        if (typeName.startsWith("java.util.logging.")) {
            return "jul";
        }

        // Simple name heuristics (when qualified name unavailable in noclasspath mode)
        if (typeName.equals("Logger") || typeName.equals("Log")) {
            return "unknown";  // Can't determine without qualified name
        }

        return "unknown";
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

    public String getFramework() {
        return framework;
    }

    public String getInheritedFrom() {
        return inheritedFrom;
    }
}
