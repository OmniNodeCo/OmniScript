from __future__ import annotations

import unittest

from omniscript import ast_nodes as ast
from omniscript.errors import OmniSyntaxError
from omniscript.lexer import Lexer
from omniscript.parser import Parser
from omniscript.tokens import TokenKind as K


class LexerParserTests(unittest.TestCase):
    def test_custom_operators_and_literals(self) -> None:
        tokens = Lexer("bind n := 0x2a\nn <- n ** 2 ?? 0 |> text").scan()
        kinds = [token.kind for token in tokens]
        self.assertIn(K.DECLARE, kinds)
        self.assertIn(K.ASSIGN, kinds)
        self.assertIn(K.POWER, kinds)
        self.assertIn(K.COALESCE, kinds)
        self.assertIn(K.PIPE, kinds)
        self.assertEqual(tokens[3].literal, 42)

    def test_nested_comments_and_unicode_escape(self) -> None:
        tokens = Lexer('/* outer /* inner */ done */ "A\\u03a9"').scan()
        self.assertEqual(tokens[0].literal, "AΩ")

    def test_parser_builds_shape_and_each(self) -> None:
        source = """
shape Pair(left, right := 2) {
  craft total() { return self.left + self.right }
}
each value, index in 1..3 { emit value, index }
"""
        program = Parser(Lexer(source).scan()).parse()
        self.assertIsInstance(program.statements[0], ast.ShapeDecl)
        self.assertIsInstance(program.statements[1], ast.EachStmt)

    def test_reports_source_location(self) -> None:
        with self.assertRaises(OmniSyntaxError) as caught:
            Parser(Lexer("bind := 3", "bad.omni").scan()).parse()
        rendered = caught.exception.render()
        self.assertIn("bad.omni:1:6", rendered)
        self.assertIn("expected a name", rendered)


if __name__ == "__main__":
    unittest.main()
