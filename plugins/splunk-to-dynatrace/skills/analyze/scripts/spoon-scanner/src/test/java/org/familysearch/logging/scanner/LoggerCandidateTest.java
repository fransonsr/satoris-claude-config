package org.familysearch.logging.scanner;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class LoggerCandidateTest {

    @Test
    void shouldCreateLoggerDeclarationCandidate() {
        LoggerCandidate candidate = new LoggerCandidate(
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

        assertEquals(CandidateType.LOGGER_DECLARATION, candidate.getType());
        assertEquals("/path/to/MyClass.java", candidate.getFile());
        assertEquals(23, candidate.getLine());
        assertEquals(5, candidate.getColumn());
        assertEquals("LOGGER", candidate.getName());
        assertEquals("org.slf4j.Logger", candidate.getTypeName());
        assertNull(candidate.getMethodName());
        assertFalse(candidate.isNeedsValidation());
        assertEquals("type_name", candidate.getDetectionStrategy());
    }

    @Test
    void shouldCreateLoggerCallCandidate() {
        LoggerCandidate candidate = new LoggerCandidate(
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

        assertEquals(CandidateType.LOGGER_CALL, candidate.getType());
        assertEquals("/path/to/MyClass.java", candidate.getFile());
        assertEquals(45, candidate.getLine());
        assertEquals(9, candidate.getColumn());
        assertEquals("LOGGER", candidate.getName());
        assertNull(candidate.getTypeName());
        assertEquals("info", candidate.getMethodName());
        assertFalse(candidate.isNeedsValidation());
        assertEquals("method_name", candidate.getDetectionStrategy());
    }

    @Test
    void shouldMarkCandidateAsNeedingValidation() {
        LoggerCandidate candidate = new LoggerCandidate(
            CandidateType.LOGGER_CALL,
            "/path/to/MyClass.java",
            100,
            12,
            null,
            null,
            "info",
            true,
            "heuristic_scope_pattern"
        );

        assertTrue(candidate.isNeedsValidation());
        assertEquals("heuristic_scope_pattern", candidate.getDetectionStrategy());
    }

    @Test
    void shouldHandleNullValues() {
        LoggerCandidate candidate = new LoggerCandidate(
            CandidateType.LOGGER_CALL,
            "/path/to/file.java",
            1,
            1,
            null,
            null,
            null,
            false,
            "test_strategy"
        );

        assertNull(candidate.getName());
        assertNull(candidate.getTypeName());
        assertNull(candidate.getMethodName());
    }
}
