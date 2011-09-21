#
#  This file is part of Bakefile (http://www.bakefile.org)
#
#  Copyright (C) 2008-2011 Vaclav Slavik
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
#  IN THE SOFTWARE.
#

"""
Classes for simplification of expressions.

The :class:`Expr` class that represents a Bakefile expression (be it a
condition or variable value) is defined in this module, together with
useful functions for evaluating and simplifying expressions.
"""

from bkl.expr import *


class NoopSimplifier(Visitor):
    """
    This simplifier doesn't simplify anything.
    """
    def null(self, e):
        return e

    def literal(self, e):
        return e

    def list(self, e):
        return e

    def concat(self, e):
        return e

    def reference(self, e):
        return e

    def path(self, e):
        return e

    def bool(self, e):
        return e

    def if_(self, e):
        return e


class BasicSimplifier(NoopSimplifier):
    """
    Simplify expression *e*. This does "cheap" simplifications such
    as merging concatenated literals, recognizing always-false conditions,
    eliminating unnecessary variable references (turn ``foo=$(x);bar=$(foo)``
    into ``bar=$(x)``) etc.
    """
    def list(self, e):
        return ListExpr([self.visit(i) for i in e.items], pos=e.pos)

    def concat(self, e):
        # merge concatenated literals:
        items = [self.visit(i) for i in e.items]
        out = [items[0]]
        for i in items[1:]:
            if isinstance(i, LiteralExpr) and isinstance(out[-1], LiteralExpr):
                out[-1] = LiteralExpr(out[-1].value + i.value)
            else:
                out.append(i)
        if len(out) == 1:
            return out[0]
        else:
            return ConcatExpr(out, pos=e.pos)

    def reference(self, e):
        # Simple reference can be replaced with the referenced value. Do this
        # for (scalar) literals and other references only, though -- if the
        # value is e.g. a list, we want to keep it as a variable to avoid
        # duplication of large values.
        ref = e.get_value()
        if isinstance(ref, LiteralExpr) or isinstance(ref, ReferenceExpr):
            return ref
        else:
            return e

    def path(self, e):
        return PathExpr([self.visit(i) for i in e.components], e.anchor, pos=e.pos)
