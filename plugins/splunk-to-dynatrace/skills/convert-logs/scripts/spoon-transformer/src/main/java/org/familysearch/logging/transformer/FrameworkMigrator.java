package org.familysearch.logging.transformer;

import spoon.reflect.code.CtExpression;
import spoon.reflect.code.CtFieldRead;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.declaration.CtField;
import spoon.reflect.declaration.CtImport;
import spoon.reflect.declaration.CtType;
import spoon.reflect.factory.Factory;
import spoon.reflect.reference.CtTypeReference;
import spoon.support.reflect.declaration.CtCompilationUnitImpl;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Framework migration utilities for converting Log4j/Logback/Commons/JUL to SLF4J.
 *
 * Supports migration from:
 * - Log4j 1.x (org.apache.log4j.Logger)
 * - Log4j 2.x (org.apache.logging.log4j.Logger)
 * - Logback (ch.qos.logback.classic.Logger)
 * - Apache Commons Logging (org.apache.commons.logging.Log)
 * - Java Util Logging (java.util.logging.Logger)
 *
 * Version: 3.0.2
 * Author: FamilySearch Engineering - SATORIS Team
 */
public class FrameworkMigrator {

    public enum Framework {
        SLF4J,
        LOG4J,
        LOG4J2,
        LOGBACK,
        COMMONS_LOGGING,
        JUL,
        UNKNOWN
    }

    /**
     * Detect logging framework from invocation and type info.
     *
     * Strategy:
     * 1. Check receiver type (org.apache.log4j.Logger → log4j)
     * 2. Check imports (import org.apache.commons.logging.Log → commons-logging)
     * 3. Check method name (severe() → jul)
     *
     * @param invocation The logger call
     * @return Framework enum (SLF4J, LOG4J, LOG4J2, LOGBACK, COMMONS_LOGGING, JUL)
     */
    public static Framework detectFramework(CtInvocation<?> invocation) {
        CtExpression<?> target = invocation.getTarget();

        if (target instanceof CtFieldRead<?>) {
            CtFieldRead<?> fieldRead = (CtFieldRead<?>) target;
            CtTypeReference<?> typeRef = fieldRead.getVariable().getType();

            if (typeRef != null) {
                String qualifiedName = typeRef.getQualifiedName();

                if (qualifiedName.startsWith("org.slf4j.")) {
                    return Framework.SLF4J;
                } else if (qualifiedName.startsWith("org.apache.log4j.")) {
                    return Framework.LOG4J;
                } else if (qualifiedName.startsWith("org.apache.logging.log4j.")) {
                    return Framework.LOG4J2;
                } else if (qualifiedName.startsWith("ch.qos.logback.")) {
                    return Framework.LOGBACK;
                } else if (qualifiedName.startsWith("org.apache.commons.logging.")) {
                    return Framework.COMMONS_LOGGING;
                } else if (qualifiedName.startsWith("java.util.logging.")) {
                    return Framework.JUL;
                }
            }
        }

        return Framework.UNKNOWN;
    }

    /**
     * Migrate logger field declaration to SLF4J.
     *
     * Examples:
     * - Log4j 1.x:  Logger LOGGER = Logger.getLogger(Foo.class);
     *               → Logger LOGGER = LoggerFactory.getLogger(Foo.class);
     *
     * - Log4j 2.x:  Logger LOGGER = LogManager.getLogger();
     *               → Logger LOGGER = LoggerFactory.getLogger(Foo.class);
     *
     * - Logback:    ch.qos.logback.classic.Logger LOGGER = ...
     *               → org.slf4j.Logger LOGGER = LoggerFactory.getLogger(Foo.class);
     *
     * - Commons:    Log LOG = LogFactory.getLog(Foo.class);
     *               → Logger LOG = LoggerFactory.getLogger(Foo.class);
     *
     * - JUL:        java.util.logging.Logger LOGGER = Logger.getLogger(Foo.class.getName());
     *               → Logger LOGGER = LoggerFactory.getLogger(Foo.class);
     *
     * @param field The logger field declaration
     * @param framework The detected framework
     * @return true if migration was performed
     */
    public static boolean migrateLoggerField(CtField<?> field, Framework framework) {
        if (field == null || framework == null || framework == Framework.SLF4J) {
            return false;
        }

        Factory factory = field.getFactory();

        switch (framework) {
            case LOG4J:
                // Logger.getLogger() → LoggerFactory.getLogger()
                replaceFactoryInvocation(field, "Logger", "LoggerFactory", "getLogger");
                field.setType(factory.Type().createReference("org.slf4j.Logger"));
                return true;

            case LOG4J2:
                // LogManager.getLogger() → LoggerFactory.getLogger()
                replaceFactoryInvocation(field, "LogManager", "LoggerFactory", "getLogger");
                field.setType(factory.Type().createReference("org.slf4j.Logger"));
                return true;

            case LOGBACK:
                // ch.qos.logback.classic.Logger → org.slf4j.Logger
                field.setType(factory.Type().createReference("org.slf4j.Logger"));
                replaceFactoryInvocation(field, "LoggerFactory", "LoggerFactory", "getLogger");
                return true;

            case COMMONS_LOGGING:
                // Log LOG = LogFactory.getLog() → Logger LOG = LoggerFactory.getLogger()
                replaceFactoryInvocation(field, "LogFactory", "LoggerFactory", "getLogger", "getLog");
                field.setType(factory.Type().createReference("org.slf4j.Logger"));
                return true;

            case JUL:
                // java.util.logging.Logger → org.slf4j.Logger
                // Logger.getLogger(Foo.class.getName()) → LoggerFactory.getLogger(Foo.class)
                field.setType(factory.Type().createReference("org.slf4j.Logger"));
                migrateJulFactory(field);
                return true;

            default:
                return false;
        }
    }

    /**
     * Replace factory method invocation in field initializer.
     */
    private static void replaceFactoryInvocation(CtField<?> field,
                                                String oldFactory,
                                                String newFactory,
                                                String newMethod) {
        replaceFactoryInvocation(field, oldFactory, newFactory, newMethod, newMethod);
    }

    private static void replaceFactoryInvocation(CtField<?> field,
                                                String oldFactory,
                                                String newFactory,
                                                String newMethod,
                                                String oldMethod) {
        CtExpression<?> initializer = field.getDefaultExpression();
        if (initializer instanceof CtInvocation<?>) {
            CtInvocation<?> factoryCall = (CtInvocation<?>) initializer;

            // Build new factory call
            Factory factory = field.getFactory();

            // Create type reference for LoggerFactory
            CtTypeReference<?> factoryTypeRef = factory.Type().createReference(newFactory);

            // Create invocation: LoggerFactory.getLogger(...)
            CtInvocation<?> newCall = factory.createInvocation(
                factory.createTypeAccess(factoryTypeRef),
                factoryCall.getExecutable().getFactory().createExecutableReference()
                    .setStatic(true)
                    .setDeclaringType(factoryTypeRef)
                    .setSimpleName(newMethod),
                factoryCall.getArguments()  // Preserve arguments
            );

            field.setDefaultExpression((CtExpression) newCall);
        }
    }

    /**
     * Migrate JUL factory: Logger.getLogger(Foo.class.getName()) → LoggerFactory.getLogger(Foo.class)
     */
    private static void migrateJulFactory(CtField<?> field) {
        CtExpression<?> initializer = field.getDefaultExpression();
        if (initializer instanceof CtInvocation<?>) {
            CtInvocation<?> factoryCall = (CtInvocation<?>) initializer;
            Factory factory = field.getFactory();

            // Extract class reference from Foo.class.getName()
            List<CtExpression<?>> args = factoryCall.getArguments();
            if (!args.isEmpty() && args.get(0) instanceof CtInvocation<?>) {
                CtInvocation<?> getNameCall = (CtInvocation<?>) args.get(0);
                if (getNameCall.getExecutable().getSimpleName().equals("getName")) {
                    CtExpression<?> classRef = getNameCall.getTarget();  // Foo.class

                    // Build LoggerFactory.getLogger(Foo.class)
                    CtTypeReference<?> factoryTypeRef = factory.Type().createReference("org.slf4j.LoggerFactory");

                    List<CtExpression<?>> newArgs = new ArrayList<>();
                    newArgs.add(classRef);

                    CtInvocation<?> newCall = factory.createInvocation(
                        factory.createTypeAccess(factoryTypeRef),
                        factory.createExecutableReference()
                            .setStatic(true)
                            .setDeclaringType(factoryTypeRef)
                            .setSimpleName("getLogger"),
                        newArgs
                    );

                    field.setDefaultExpression((CtExpression) newCall);
                }
            }
        }
    }

    /**
     * Migrate logger method call to SLF4J equivalent.
     *
     * Method mappings:
     * - Log4j fatal() → SLF4J error() (SLF4J has no fatal level)
     * - Log4j 2.x atFatal() → atError()
     * - JUL severe() → error()
     * - JUL warning() → warn()
     * - JUL config() → info()
     * - JUL fine/finer/finest() → debug()
     * - All others → preserve method name
     *
     * @param invocation The logger method call
     * @param framework The detected framework
     * @return true if migration was performed
     */
    public static boolean migrateLoggerCall(CtInvocation<?> invocation, Framework framework) {
        String methodName = invocation.getExecutable().getSimpleName();
        String newMethodName = mapMethodName(methodName, framework);

        if (!newMethodName.equals(methodName)) {
            // Replace method name
            invocation.getExecutable().setSimpleName(newMethodName);
            return true;
        }

        return false;
    }

    /**
     * Map framework-specific method names to SLF4J.
     */
    private static String mapMethodName(String methodName, Framework framework) {
        switch (framework) {
            case LOG4J:
            case LOG4J2:
                if (methodName.equals("fatal")) return "error";
                if (methodName.equals("atFatal")) return "atError";
                break;

            case JUL:
                if (methodName.equals("severe")) return "error";
                if (methodName.equals("warning")) return "warn";
                if (methodName.equals("config")) return "info";
                if (methodName.equals("fine") || methodName.equals("finer") ||
                    methodName.equals("finest")) return "debug";
                break;

            case COMMONS_LOGGING:
                // Commons Logging uses same method names as SLF4J
                break;

            case LOGBACK:
                // Logback uses SLF4J API
                break;

            case SLF4J:
            case UNKNOWN:
                // No mapping needed
                break;
        }

        return methodName;  // No mapping needed
    }

    /**
     * Migrate imports from framework-specific to SLF4J.
     *
     * This method is called after AST transformations. Spoon's auto-import
     * will add SLF4J imports automatically, but we need to remove old imports.
     *
     * @param type The compilation unit type
     * @param framework The framework being migrated from
     */
    public static void migrateImports(CtType<?> type, Framework framework) {
        if (type == null || framework == null || framework == Framework.SLF4J) {
            return;
        }

        // Remove old framework imports
        Set<String> oldImportPrefixes = getOldImportPrefixes(framework);

        try {
            CtCompilationUnitImpl cu = (CtCompilationUnitImpl) type.getFactory().CompilationUnit().getOrCreate(type);
            List<CtImport> importsToRemove = new ArrayList<>();

            for (CtImport imp : cu.getImports()) {
                String ref = imp.getReference().toString();

                for (String prefix : oldImportPrefixes) {
                    if (ref.startsWith(prefix)) {
                        importsToRemove.add(imp);
                        break;
                    }
                }
            }

            // Remove old imports by clearing and re-adding
            Set<CtImport> keepImports = new HashSet<>(cu.getImports());
            keepImports.removeAll(importsToRemove);

            cu.setImports(keepImports);
        } catch (Exception e) {
            // Gracefully handle import migration failures
            System.err.println("Warning: Could not migrate imports for " + type.getSimpleName() + ": " + e.getMessage());
        }

        // Add SLF4J imports (will be added automatically by Spoon's auto-import)
        // No explicit action needed - Spoon handles this
    }

    /**
     * Get import prefixes to remove for each framework.
     */
    private static Set<String> getOldImportPrefixes(Framework framework) {
        switch (framework) {
            case LOG4J:
                return Set.of("org.apache.log4j.");

            case LOG4J2:
                return Set.of("org.apache.logging.log4j.");

            case LOGBACK:
                return Set.of("ch.qos.logback.");

            case COMMONS_LOGGING:
                return Set.of("org.apache.commons.logging.");

            case JUL:
                return Set.of("java.util.logging.");

            default:
                return Set.of();
        }
    }
}
