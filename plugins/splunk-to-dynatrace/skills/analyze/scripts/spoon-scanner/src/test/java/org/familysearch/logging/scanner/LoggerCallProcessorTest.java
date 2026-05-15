package org.familysearch.logging.scanner;

import org.junit.jupiter.api.Test;
import spoon.Launcher;
import spoon.support.compiler.VirtualFile;

import java.nio.file.Paths;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class LoggerCallProcessorTest {

    private ScannerConfig createTestConfig() {
        return new ScannerConfig(
            Paths.get("."),
            Paths.get("/tmp/output.json"),
            false,
            Collections.emptyList(),
            false,
            null
        );
    }

    private List<LoggerCandidate> processJavaCode(String javaCode, Set<String> knownLoggerFields) {
        Launcher launcher = new Launcher();
        launcher.addInputResource(new VirtualFile(javaCode));
        launcher.getEnvironment().setNoClasspath(true);
        launcher.getEnvironment().setAutoImports(true);
        launcher.getEnvironment().setCommentEnabled(false);
        launcher.getEnvironment().setComplianceLevel(17);
        launcher.buildModel();

        LoggerCallProcessor processor = new LoggerCallProcessor(createTestConfig(), knownLoggerFields, new java.util.HashMap<>());
        launcher.addProcessor(processor);
        launcher.process();

        return processor.getCandidates();
    }

    @Test
    void shouldDetectInfoLogCall() {
        String javaCode = """
            package com.example;
            import org.slf4j.Logger;

            public class Service {
                private static final Logger LOGGER = null;

                public void doSomething() {
                    LOGGER.info("Processing request");
                }
            }
            """;

        Set<String> knownLoggers = Set.of("LOGGER");
        List<LoggerCandidate> candidates = processJavaCode(javaCode, knownLoggers);

        assertEquals(1, candidates.size());
        LoggerCandidate candidate = candidates.get(0);
        assertEquals(CandidateType.LOGGER_CALL, candidate.getType());
        assertEquals("info", candidate.getMethodName());
        assertEquals("LOGGER", candidate.getName());
        assertFalse(candidate.isNeedsValidation());
        // When both method_name and known_logger_field apply, known_logger_field takes precedence (more specific)
        assertEquals("known_logger_field", candidate.getDetectionStrategy());
    }

    @Test
    void shouldDetectAllLogLevels() {
        String javaCode = """
            package com.example;
            import org.slf4j.Logger;

            public class Service {
                private Logger log;

                public void doSomething() {
                    log.trace("trace");
                    log.debug("debug");
                    log.info("info");
                    log.warn("warn");
                    log.error("error");
                }
            }
            """;

        Set<String> knownLoggers = Set.of("log");
        List<LoggerCandidate> candidates = processJavaCode(javaCode, knownLoggers);

        assertEquals(5, candidates.size());
        Set<String> methods = new HashSet<>();
        for (LoggerCandidate candidate : candidates) {
            methods.add(candidate.getMethodName());
        }
        assertTrue(methods.contains("trace"));
        assertTrue(methods.contains("debug"));
        assertTrue(methods.contains("info"));
        assertTrue(methods.contains("warn"));
        assertTrue(methods.contains("error"));
    }

    @Test
    void shouldDetectFluentAPILogCalls() {
        String javaCode = """
            package com.example;
            import org.slf4j.Logger;

            public class Service {
                private Logger LOGGER;

                public void doSomething() {
                    LOGGER.atInfo().log("Processing");
                    LOGGER.atWarn().log("Warning");
                    LOGGER.atError().log("Error");
                }
            }
            """;

        Set<String> knownLoggers = Set.of("LOGGER");
        List<LoggerCandidate> candidates = processJavaCode(javaCode, knownLoggers);

        // Should detect atInfo(), atWarn(), atError() calls
        assertTrue(candidates.size() >= 3);
        long atInfoCount = candidates.stream()
            .filter(c -> "atInfo".equals(c.getMethodName()))
            .count();
        assertTrue(atInfoCount >= 1);
    }

    @Test
    void shouldDetectLoggerCallOnKnownField() {
        String javaCode = """
            package com.example;

            public class Service {
                private Object customLogger;

                public void doSomething() {
                    customLogger.info("message");
                }
            }
            """;

        Set<String> knownLoggers = Set.of("customLogger");
        List<LoggerCandidate> candidates = processJavaCode(javaCode, knownLoggers);

        assertEquals(1, candidates.size());
        assertEquals("customLogger", candidates.get(0).getName());
        assertEquals("known_logger_field", candidates.get(0).getDetectionStrategy());
    }

    @Test
    void shouldNotDetectNonLoggerMethodCalls() {
        String javaCode = """
            package com.example;

            public class Service {
                public void doSomething() {
                    System.out.println("Hello");
                    String.valueOf(123);
                    Integer.parseInt("456");
                }
            }
            """;

        List<LoggerCandidate> candidates = processJavaCode(javaCode, Collections.emptySet());

        assertEquals(0, candidates.size());
    }

    @Test
    void shouldExtractCorrectSourcePosition() {
        String javaCode = """
            package com.example;
            import org.slf4j.Logger;

            public class Service {
                private Logger LOGGER;

                public void doSomething() {
                    LOGGER.info("message");
                }
            }
            """;

        Set<String> knownLoggers = Set.of("LOGGER");
        List<LoggerCandidate> candidates = processJavaCode(javaCode, knownLoggers);

        assertEquals(1, candidates.size());
        LoggerCandidate candidate = candidates.get(0);
        assertEquals(8, candidate.getLine());
        assertTrue(candidate.getColumn() > 0);
    }

    @Test
    void shouldDetectMultipleLogCallsInSameMethod() {
        String javaCode = """
            package com.example;
            import org.slf4j.Logger;

            public class Service {
                private Logger LOGGER;

                public void process() {
                    LOGGER.info("Starting");
                    LOGGER.debug("Processing");
                    LOGGER.info("Complete");
                }
            }
            """;

        Set<String> knownLoggers = Set.of("LOGGER");
        List<LoggerCandidate> candidates = processJavaCode(javaCode, knownLoggers);

        assertEquals(3, candidates.size());
        long infoCount = candidates.stream()
            .filter(c -> "info".equals(c.getMethodName()))
            .count();
        assertEquals(2, infoCount);
    }

    @Test
    void shouldDetectLogCallsInDifferentMethods() {
        String javaCode = """
            package com.example;
            import org.slf4j.Logger;

            public class Service {
                private Logger LOGGER;

                public void method1() {
                    LOGGER.info("method1");
                }

                public void method2() {
                    LOGGER.warn("method2");
                }
            }
            """;

        Set<String> knownLoggers = Set.of("LOGGER");
        List<LoggerCandidate> candidates = processJavaCode(javaCode, knownLoggers);

        assertEquals(2, candidates.size());
    }

    @Test
    void shouldDetectLogCallWithParameters() {
        String javaCode = """
            package com.example;
            import org.slf4j.Logger;

            public class Service {
                private Logger LOGGER;

                public void process(String name, int value) {
                    LOGGER.info("Processing {} with value {}", name, value);
                }
            }
            """;

        Set<String> knownLoggers = Set.of("LOGGER");
        List<LoggerCandidate> candidates = processJavaCode(javaCode, knownLoggers);

        assertEquals(1, candidates.size());
        assertEquals("info", candidates.get(0).getMethodName());
    }

    @Test
    void shouldDetectLogCallInStaticMethod() {
        String javaCode = """
            package com.example;
            import org.slf4j.Logger;

            public class Service {
                private static Logger LOGGER;

                public static void process() {
                    LOGGER.error("Static error");
                }
            }
            """;

        Set<String> knownLoggers = Set.of("LOGGER");
        List<LoggerCandidate> candidates = processJavaCode(javaCode, knownLoggers);

        assertEquals(1, candidates.size());
        assertEquals("error", candidates.get(0).getMethodName());
    }

    @Test
    void shouldDetectLogCallInConstructor() {
        String javaCode = """
            package com.example;
            import org.slf4j.Logger;

            public class Service {
                private Logger LOGGER;

                public Service() {
                    LOGGER.info("Constructor called");
                }
            }
            """;

        Set<String> knownLoggers = Set.of("LOGGER");
        List<LoggerCandidate> candidates = processJavaCode(javaCode, knownLoggers);

        assertEquals(1, candidates.size());
    }
}
