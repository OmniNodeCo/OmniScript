#!/usr/bin/env python3
import sys
from omniscript import Lexer, Parser, Interpreter
from omniscript.errors import OmniError

LOGO = r"""
   ____                  _ ____            _       _
  / __ \                (_) ___|          (_)     | |
 | |  | |_ __ ___  _ __  \___ \ ___ _ __  _ _ __ | |_
 | |  | | '_ ` _ \| '_ \ ___) / __| '__|| | '_ \| __|
 | |__| | | | | | | | | |____/\__ \ |   | | |_) | |_
  \____/|_| |_| |_|_| |_|_____|___/_|   |_| .__/ \__|
                                           | |
                                           |_|  v1.0
"""


def run_file(filepath):
    try:
        with open(filepath, 'r') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found.")
        sys.exit(1)

    try:
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse()
        interpreter = Interpreter()
        interpreter.run(ast)
    except OmniError as e:
        print(e)
        sys.exit(1)


def repl():
    print(LOGO)
    print("  Type 'quit' to exit.\n")
    interpreter = Interpreter()

    while True:
        try:
            source = input("omni> ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if source.strip() in ("quit", "exit"):
            print("Bye!")
            break

        if not source.strip():
            continue

        open_braces = source.count('{') - source.count('}')
        while open_braces > 0:
            try:
                line = input("....  ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            source += '\n' + line
            open_braces = source.count('{') - source.count('}')

        try:
            lexer = Lexer(source)
            tokens = lexer.tokenize()
            parser = Parser(tokens)
            ast = parser.parse()
            result = interpreter.run(ast)
            if result is not None:
                print(interpreter._format(result))
        except OmniError as e:
            print(e)


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        filepath = sys.argv[1]
        if not filepath.endswith('.omni'):
            print("Warning: OmniScript files should use the .omni extension.")
        run_file(filepath)
    else:
        repl()