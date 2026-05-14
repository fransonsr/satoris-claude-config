package org.familysearch.logging.transformer;

import spoon.reflect.code.CtExpression;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.factory.Factory;
import spoon.reflect.reference.CtExecutableReference;

import java.util.List;

/**
 * Builds fluent API method chains using Spoon's factory API.
 * <p>
 * Transforms: LOGGER.info("msg", arg1, arg2)
 * Into: LOGGER.atInfo().addKeyValue("key1", val1).addKeyValue("key2", val2).log("msg")
 */
public class FluentChainBuilder {

    /**
     * Builds a complete fluent API chain.
     *
     * @param target  Logger target expression (e.g., LOGGER)
     * @param level   Log level (info, warn, error, debug, trace)
     * @param fields  Structured fields to add
     * @param message Log message
     * @return Complete fluent invocation chain
     */
    public static CtInvocation<?> buildFluentChain(
            CtExpression<?> target,
            String level,
            List<TransformationSpec.Field> fields,
            String message,
            String exception) {

        Factory factory = target.getFactory();

        // Step 1: LOGGER.atInfo()
        CtInvocation<?> chain = buildAtLevelCall(factory, target, level);

        // Step 2: .addKeyValue("key", value) for each field
        for (TransformationSpec.Field field : fields) {
            chain = buildAddKeyValueCall(factory, chain, field);
        }

        // Step 3: .setCause(exception) if present
        if (exception != null && !exception.isEmpty()) {
            chain = buildSetCauseCall(factory, chain, exception);
        }

        // Step 4: .log("message")
        chain = buildLogCall(factory, chain, message);

        return chain;
    }

    /**
     * Builds: target.atLevel()
     */
    private static CtInvocation<?> buildAtLevelCall(
            Factory factory,
            CtExpression<?> target,
            String level) {

        String methodName = "at" + capitalize(level);
        CtExecutableReference<?> execRef = factory.createExecutableReference();
        execRef.setSimpleName(methodName);

        CtInvocation<?> invocation = factory.createInvocation(
                target.clone(),
                execRef
        );

        return invocation;
    }

    /**
     * Builds: chain.addKeyValue("key", value)
     */
    private static CtInvocation<?> buildAddKeyValueCall(
            Factory factory,
            CtInvocation<?> chain,
            TransformationSpec.Field field) {

        CtExecutableReference<?> execRef = factory.createExecutableReference();
        execRef.setSimpleName("addKeyValue");

        CtInvocation<?> invocation = factory.createInvocation(
                chain,
                execRef
        );

        // Add key argument (String literal)
        invocation.addArgument(factory.createLiteral(field.getKey()));

        // Add value argument (parse as expression)
        CtExpression<?> valueExpr = parseExpression(factory, field.getValue());
        invocation.addArgument(valueExpr);

        return invocation;
    }

    /**
     * Builds: chain.setCause(exception)
     */
    private static CtInvocation<?> buildSetCauseCall(
            Factory factory,
            CtInvocation<?> chain,
            String exception) {

        CtExecutableReference<?> execRef = factory.createExecutableReference();
        execRef.setSimpleName("setCause");

        CtInvocation<?> invocation = factory.createInvocation(
                chain,
                execRef
        );

        // Add exception argument (parse as expression)
        CtExpression<?> exceptionExpr = parseExpression(factory, exception);
        invocation.addArgument(exceptionExpr);

        return invocation;
    }

    /**
     * Builds: chain.log("message")
     */
    private static CtInvocation<?> buildLogCall(
            Factory factory,
            CtInvocation<?> chain,
            String message) {

        CtExecutableReference<?> execRef = factory.createExecutableReference();
        execRef.setSimpleName("log");

        CtInvocation<?> invocation = factory.createInvocation(
                chain,
                execRef
        );

        invocation.addArgument(factory.createLiteral(message));

        return invocation;
    }

    /**
     * Parses a string into a Spoon expression.
     * Uses Spoon's code snippet parser.
     *
     * @param factory Factory for creating expressions
     * @param code    Code snippet (e.g., "personId", "person.getId()")
     * @return Parsed expression
     */
    private static CtExpression<?> parseExpression(Factory factory, String code) {
        try {
            // Use Spoon's snippet parser for expressions
            return factory.createCodeSnippetExpression(code);
        } catch (Exception e) {
            // Fallback: treat as string literal if parsing fails
            return factory.createLiteral(code);
        }
    }

    /**
     * Capitalizes first letter of string.
     */
    private static String capitalize(String str) {
        if (str == null || str.isEmpty()) {
            return str;
        }
        return str.substring(0, 1).toUpperCase() + str.substring(1);
    }
}
