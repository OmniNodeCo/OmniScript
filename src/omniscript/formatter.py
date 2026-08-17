"""Conservative, comment-preserving formatter for OmniScript."""

from __future__ import annotations


def format_source(source: str, indent: str = "    ") -> str:
    """Normalize block indentation and trailing whitespace.

    Formatting is deliberately conservative: token spelling and comments stay
    untouched, while braces determine indentation. This makes `omni fmt` safe
    even before a full concrete-syntax-tree formatter exists.
    """

    output: list[str] = []
    depth = 0
    in_block_comment = 0
    for raw_line in source.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            output.append("")
            continue
        leading_closes = _leading_closing_braces(stripped) if in_block_comment == 0 else 0
        line_depth = max(0, depth - leading_closes)
        output.append(f"{indent * line_depth}{stripped}")
        opens, closes, in_block_comment = _brace_counts(stripped, in_block_comment)
        depth = max(0, depth + opens - closes)
    # All OmniScript text files use LF and end in exactly one newline.
    return "\n".join(output).rstrip() + "\n"


def _leading_closing_braces(line: str) -> int:
    index = 0
    count = 0
    while index < len(line):
        if line[index].isspace():
            index += 1
        elif line[index] == "}":
            count += 1
            index += 1
        else:
            break
    return count


def _brace_counts(line: str, block_depth: int) -> tuple[int, int, int]:
    opens = closes = 0
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        next_char = line[index + 1] if index + 1 < len(line) else ""
        if block_depth:
            if char == "/" and next_char == "*":
                block_depth += 1
                index += 2
                continue
            if char == "*" and next_char == "/":
                block_depth -= 1
                index += 2
                continue
            index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "#" or (char == "/" and next_char == "/"):
            break
        elif char == "/" and next_char == "*":
            block_depth = 1
            index += 2
            continue
        elif char == "{":
            opens += 1
        elif char == "}":
            closes += 1
        index += 1
    return opens, closes, block_depth
