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
