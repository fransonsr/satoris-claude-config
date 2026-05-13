package org.familysearch.logging.scanner;

/**
 * Type of logger candidate found during scanning.
 */
public enum CandidateType {
    /** Logger field declaration (e.g., private static final Logger LOGGER) */
    LOGGER_DECLARATION,

    /** Logger method call (e.g., LOGGER.info("message")) */
    LOGGER_CALL
}
