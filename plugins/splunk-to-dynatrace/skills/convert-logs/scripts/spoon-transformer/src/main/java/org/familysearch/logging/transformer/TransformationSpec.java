package org.familysearch.logging.transformer;

import java.util.List;

/**
 * Specification for transforming a traditional log statement to fluent API.
 * Deserialized from JSON input.
 */
public class TransformationSpec {
    private String file;
    private int line;
    private String logger;
    private String level;
    private List<Field> fields;
    private String message;
    private String exception;

    // Framework migration support (v3.0.2)
    private String framework;           // slf4j, log4j, log4j2, logback, commons-logging, jul
    private boolean fluentConversion = true;   // true for traditional→fluent, false for framework-only

    public String getFile() {
        return file;
    }

    public int getLine() {
        return line;
    }

    public String getLogger() {
        return logger;
    }

    public String getLevel() {
        return level;
    }

    public List<Field> getFields() {
        return fields;
    }

    public String getMessage() {
        return message;
    }

    public String getException() {
        return exception;
    }

    public String getFramework() {
        return framework;
    }

    public void setFramework(String framework) {
        this.framework = framework;
    }

    public boolean isFluentConversion() {
        return fluentConversion;
    }

    public void setFluentConversion(boolean fluentConversion) {
        this.fluentConversion = fluentConversion;
    }

    /**
     * Structured field key-value pair.
     */
    public static class Field {
        private String key;
        private String value;

        public String getKey() {
            return key;
        }

        public String getValue() {
            return value;
        }
    }
}
