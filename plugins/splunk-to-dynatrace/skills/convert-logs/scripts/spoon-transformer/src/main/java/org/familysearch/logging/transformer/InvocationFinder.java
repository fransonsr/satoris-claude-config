package org.familysearch.logging.transformer;

import spoon.reflect.CtModel;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.visitor.filter.TypeFilter;

import java.util.List;

/**
 * Finds method invocations by line number.
 */
public class InvocationFinder {

    /**
     * Finds the first invocation at the specified line number.
     *
     * @param model      Spoon AST model
     * @param targetLine Target line number (1-based)
     * @return Invocation at that line
     * @throws IllegalArgumentException if no invocation found at line
     */
    public static CtInvocation<?> findInvocationAtLine(CtModel model, int targetLine) {
        List<CtInvocation<?>> invocations = model.getElements(
                new TypeFilter<>(CtInvocation.class)
        );

        for (CtInvocation<?> inv : invocations) {
            if (inv.getPosition().isValidPosition() &&
                    inv.getPosition().getLine() == targetLine) {
                return inv;
            }
        }

        throw new IllegalArgumentException(
                "No invocation found at line " + targetLine
        );
    }
}
