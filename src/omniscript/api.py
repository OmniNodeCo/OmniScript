"""Stable embedding API for OmniScript."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .ast_nodes import Program
from .checker import check_program
from .errors import OmniCheckError
from .lexer import Lexer
from .parser import Parser
from .runtime import Environment, Interpreter
from .tokens import Token


@dataclass(slots=True)
class RunResult:
    value: Any
    output: list[str]
    environment: Environment


class OmniEngine:
    """Compile and execute OmniScript without shelling out to the CLI."""

    def __init__(
        self,
        output: Callable[[str], None] | None = None,
        input_provider: Callable[[str], str] | None = None,
    ):
        self.output_lines: list[str] = []

        def handle_output(line: str) -> None:
            self.output_lines.append(line)
            if output:
                output(line)

        self.interpreter = Interpreter(handle_output, input_provider)

    @staticmethod
    def tokens(source: str, source_name: str = "<memory>") -> list[Token]:
        return Lexer(source, source_name).scan()

    @classmethod
    def parse(cls, source: str, source_name: str = "<memory>") -> Program:
        return Parser(cls.tokens(source, source_name)).parse()

    @classmethod
    def check(cls, source: str, source_name: str = "<memory>") -> list[OmniCheckError]:
        return check_program(cls.parse(source, source_name))

    def run(
        self,
        source: str,
        source_name: str = "<memory>",
        *,
        check: bool = True,
        environment: Environment | None = None,
    ) -> RunResult:
        program = self.parse(source, source_name)
        if check:
            errors = check_program(program)
            if errors:
                raise errors[0]
        environment = environment or self.interpreter.new_environment()
        if not source_name.startswith("<") and "__file__" not in environment.bindings:
            environment.define("__file__", source_name, False)
        start = len(self.output_lines)
        value = self.interpreter.interpret(program, environment)
        return RunResult(value, self.output_lines[start:], environment)

    def run_file(self, path: str | Path, *, check: bool = True) -> RunResult:
        resolved = Path(path).resolve()
        source = resolved.read_text(encoding="utf-8")
        return self.run(source, str(resolved), check=check)
