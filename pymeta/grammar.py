import sys, string
from builder import AstBuilder
from boot import BootOMetaGrammar
from runtime import OMetaBase, ParseError

OMetaGrammar = None

class OMeta(OMetaBase):
    """
    Base class for grammar definitions.
    """

    def makeGrammar(cls, grammar, globals, name="<OMeta grammar>"):
        if OMetaGrammar is None:
            g = BootOMetaGrammar(grammar)
        else:
            g = OMetaGrammar(grammar)

        rules = g.parseGrammar(name)

        grammarClass = type.__new__(type, name, (cls,), rules)
        grammarClass.globals = globals
        return grammarClass
    makeGrammar = classmethod(makeGrammar)

ometaGrammar = """
number ::= <spaces> ('-' <barenumber>:x => self.builder.exactly(-x)
                    |<barenumber>:x => self.builder.exactly(x))
barenumber ::= ('0' (('x'|'X') <hexdigit>*:hs => int(''.join(hs), 16)
                    |<octaldigit>*:ds => int('0'+''.join(ds), 8))
               |<digit>+:ds => int(''.join(ds)))
octaldigit ::= :x ?(x in string.octdigits) => x
hexdigit ::= :x ?(x in string.hexdigits) => x

character ::= <token "'"> :c <token "'"> => self.builder.exactly(c)

name ::= <letter>:x <letterOrDigit>*:xs !(xs.insert(0, x)) => ''.join(xs)

application ::= (<token '<'> <spaces> <name>:name
                  (' ' !(self.applicationArgs()):args
                     => self.builder.apply(name, self.name, *args)
                  |<token '>'>
                     => self.builder.apply(name)))

expr1 ::= (<application>
          |<ruleValue>
          |<semanticPredicate>
          |<semanticAction>
          |<number>
          |<character>
          |<token '('> <expr>:e <token ')'> => e
          |<token '['> <expr>:e <token ']'> => self.builder.listpattern(e))

expr2 ::= (<token '~'> (<token '~'> <expr2>:e => self.builder.lookahead(e)
                       |<expr2>:e => self.builder._not(e))
          |<expr1>)

expr3 ::= ((<expr2>:e (<token '*'> => self.builder.many(e)
                      |<token '+'> => self.builder.many1(e)
                      |<token '?'> => self.builder.optional(e)
                      | => e)):r
           (':' <name>:n => self.builder.bind(r, n)
           | => r)
          |<token ':'> <name>:n
           => self.builder.bind(self.builder.apply("anything"), n))

expr4 ::= <expr3>*:es => self.builder.sequence(es)

expr ::= <expr4>:e (<token '|'> <expr4>)*:es !(es.insert(0, e))
          => self.builder._or(es)

ruleValue ::= <token "=>"> => self.ruleValueExpr()

semanticPredicate ::= <token "?("> => self.semanticPredicateExpr()

semanticAction ::= <token "!("> => self.semanticActionExpr()

rulePart :requiredName ::= (<spaces> <name>:n ?(n == requiredName)
                            !(setattr(self, "name", n))
                            <expr4>:args
                            (<token "::="> <expr>:e
                               => self.builder.sequence([args, e])
                            |  => args))
rule ::= (<spaces> ~~(<name>:n) <rulePart n>:r
          (<rulePart n>+:rs => (n, self.builder._or([r] + rs))
          |                     => (n, r)))

grammar ::= <rule>*:rs <spaces> => self.builder.makeGrammar(rs)
"""

class OMetaGrammar(OMeta.makeGrammar(ometaGrammar, globals())):
    """
    The base grammar for parsing grammar definitions.
    """

    def parseGrammar(self, name="Grammar", builder=AstBuilder):
        """
        Entry point for converting a grammar to code (of some variety).

        @param name: The name for this grammar.

        @param builder: A class that implements the grammar-building interface
        (interface to be explicitly defined later)
        """
        self.builder = builder(name, self)
        res = self.apply("grammar")
        x = list(self.input)
        if x:
            x = repr(''.join(x))
            raise ParseError("Grammar parse failed. Leftover bits: %s" % (x,))
        return res


    def applicationArgs(self):
        """
        Collect rule arguments, a list of Python expressions separated by
        spaces.
        """
        args = []
        while True:
            try:
                arg, endchar = self.pythonExpr(" >")
                if not arg:
                    break
                args.append(arg)
                if endchar == '>':
                    break
            except ParseError:
                break
        if args:
            return args
        else:
            raise ParseError()

    def ruleValueExpr(self):
        """
        Find and generate code for a Python expression terminated by a close
        paren/brace or end of line.
        """
        expr, endchar = self.pythonExpr(endChars="\r\n)]")
        if str(endchar) in ")]":
            self.input.prev()
        return self.builder.compilePythonExpr(self.name, expr)

    def semanticActionExpr(self):
        """
        Find and generate code for a Python expression terminated by a
        close-paren, whose return value is ignored.
        """
        expr = self.builder.compilePythonExpr(self.name, self.pythonExpr(')')[0])
        return self.builder.action(expr)

    def semanticPredicateExpr(self):
        """
        Find and generate code for a Python expression terminated by a
        close-paren, whose return value determines the success of the pattern
        it's in.
        """
        expr = self.builder.compilePythonExpr(self.name, self.pythonExpr(')')[0])
        return self.builder.pred(expr)