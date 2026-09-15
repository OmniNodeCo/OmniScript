"""Language tests: run with `python3 -m unittest discover -s tests` or `./omni test`.

Each helper compiles and runs a snippet, so a failure shows the exact source line
that broke.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omniscript import make_interpreter  # noqa: E402
from omniscript.errors import (OmniError, OmniNameError, OmniRuntimeError,  # noqa: E402
                               OmniSyntaxError, OmniTypeError)
from omniscript.values import to_repr, type_name  # noqa: E402


def run(src: str, collect_output: bool = True):
    """Run OmniScript source; return (result, printed_text, interpreter)."""
    out = []
    interp = make_interpreter(writer=out.append, quiet=True)
    try:
        result = interp.run_source(src, "<test>")
    except OmniError as err:
        interp.enrich(err, "<test>")
        raise
    return result, "".join(out), interp


def value(src: str):
    """Evaluate a single expression and return it."""
    result, _, _ = run(src)
    return result


class LexerTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(value("0xff"), 255.0)
        self.assertEqual(value("0b1011"), 11.0)
        self.assertEqual(value("0o17"), 15.0)
        self.assertEqual(value("1_000_000"), 1000000.0)
        self.assertEqual(value("3.14"), 3.14)
        self.assertEqual(value("1e3"), 1000.0)
        self.assertEqual(value(".5"), 0.5)
        self.assertEqual(value("-2.5e-2"), -0.025)

    def test_ranges_are_not_floats(self):
        self.assertEqual(value("[1..4]"), [1.0, 2.0, 3.0])
        self.assertEqual(value("[1..=4]"), [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(value("[0..10..3]"), [0.0, 3.0, 6.0, 9.0])
        self.assertEqual(value("[10..0..-3]"), [10.0, 7.0, 4.0, 1.0])

    def test_comments(self):
        self.assertEqual(value("1 + 1 # trailing"), 2.0)
        self.assertEqual(value("# whole line\n2"), 2.0)
        self.assertEqual(value("1 + #{ hidden }# 1"), 2.0)
        self.assertEqual(value("1 + \\\n1"), 2.0)

    def test_string_interpolation(self):
        self.assertEqual(value('let a = 2\n"got \\{a * 3}"'), "got 6")
        self.assertEqual(value('"${"nested ${1}"}"'), "nested 1")
        self.assertEqual(value(r'"a\nb".lines().len()'), 2.0)

    def test_unclosed_string_raises(self):
        with self.assertRaises(OmniError):
            value('"oops')


class ExpressionTests(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(value("2 + 3 * 4"), 14.0)
        self.assertEqual(value("(2 + 3) * 4"), 20.0)
        self.assertEqual(value("2 ** 3 ** 2"), 512.0)
        self.assertEqual(value("7 / 2"), 3.5)
        self.assertEqual(value("7 % 3"), 1.0)
        self.assertEqual(value("-2 ** 2"), 4.0)
        self.assertEqual(value("10 - -3"), 13.0)

    def test_bitwise(self):
        self.assertEqual(value("5 & 3"), 1.0)
        self.assertEqual(value("5 | 3"), 7.0)
        self.assertEqual(value("5 ^ 3"), 6.0)
        self.assertEqual(value("1 << 4"), 16.0)
        self.assertEqual(value("~5"), -6.0)

    def test_comparison_and_logic(self):
        self.assertTrue(value("1 < 2 and 2 <= 2"))
        self.assertFalse(value("1 > 2 or 3 < 2"))
        self.assertTrue(value("not false"))
        self.assertTrue(value("true and true or false"))
        self.assertTrue(value('"a" == "a"'))
        self.assertTrue(value("[1,2] == [1,2]"))
        self.assertFalse(value("[1,2] == [2,1]"))
        self.assertTrue(value('{a: 1} == {a: 1}'))

    def test_type_checks(self):
        self.assertTrue(value("5 is num"))
        self.assertTrue(value('"x" is str'))
        self.assertTrue(value("[1] is list"))
        self.assertTrue(value("{a:1} is map"))
        self.assertTrue(value("null is null"))
        self.assertTrue(value("(x) -> x is fn"))
        self.assertFalse(value("5 is str"))
        self.assertTrue(value("5 isnt str"))
        self.assertTrue(value("4 is int"))
        self.assertFalse(value("4.5 is int"))

    def test_ternary_and_elvis(self):
        self.assertEqual(value("true ? 1 : 2"), 1.0)
        self.assertEqual(value("false ? 1 : 2"), 2.0)
        self.assertEqual(value("null ?? 7"), 7.0)
        self.assertEqual(value("3 ?? 7"), 3.0)
        self.assertEqual(value("false ?: 9"), 9.0)

    def test_string_ops(self):
        self.assertEqual(value('"ab" + "cd"'), "abcd")
        self.assertEqual(value('"ab" * 3'), "ababab")
        self.assertEqual(value('"Hello"[1]'), "e")
        self.assertEqual(value('"Hello"[-1]'), "o")
        self.assertEqual(value('"Hello"[1..3]'), "el")
        self.assertEqual(value('"Hello World".words().len()'), 2.0)

    def test_list_ops(self):
        self.assertEqual(value("[1,2] + [3]"), [1.0, 2.0, 3.0])
        self.assertEqual(value("[1,2,3][0..2]"), [1.0, 2.0])
        self.assertEqual(value("[1,2,3][::-1]"), [3.0, 2.0, 1.0])
        self.assertEqual(value("[1,2,3].len()"), 3.0)
        self.assertEqual(value("[*([1,2]), 3]"), [1.0, 2.0, 3.0])

    def test_map_ops(self):
        self.assertEqual(value('{a: 1, "b": 2}.a'), 1.0)
        self.assertEqual(value('{a: 1}["a"]'), 1.0)
        self.assertEqual(value('{a: 1}?.missing'), None)
        self.assertEqual(value('{a: 1, **{b: 2}}.keys()'), ["a", "b"])

    def test_optional_chaining(self):
        self.assertEqual(value("null?.x"), None)
        self.assertEqual(value("null?.x?.y ?? 5"), 5.0)
        self.assertEqual(value('{a: {b: 1}}?.a?.b'), 1.0)


class StatementTests(unittest.TestCase):
    def test_let_and_mut(self):
        self.assertEqual(value("mut x = 1\nx = 2\nx"), 2.0)
        with self.assertRaises(OmniRuntimeError):
            value("let x = 1\nx = 2\nx")

    def test_destructuring(self):
        self.assertEqual(value("let [a, b] = [1, 2]\na + b"), 3.0)
        self.assertEqual(value("let [a, *r] = [1, 2, 3]\nr"), [2.0, 3.0])
        self.assertEqual(value('let {a, b: c} = {a: 1, b: 2}\nc - a'), 1.0)
        self.assertEqual(value("let a, b = 1, 2\na + b"), 3.0)

    def test_if_expression(self):
        self.assertEqual(value("if 1 < 2 { 10 } else { 20 }"), 10.0)
        self.assertEqual(value("let x = if false { 1 } else if true { 2 } else { 3 }\nx"), 2.0)
        self.assertEqual(value("if false { 1 }"), None)

    def test_loops(self):
        self.assertEqual(value("mut s = 0\nfor i in 1..=5 { s += i }\ns"), 15.0)
        self.assertEqual(value("mut s = 0\nfor i in [1,2,3] { s += i }\ns"), 6.0)
        self.assertEqual(value('mut s = ""\nfor c in "abc" { s += c }\ns'), "abc")
        self.assertEqual(value("mut n = 0\nwhile n < 4 { n += 1 }\nn"), 4.0)
        self.assertEqual(value("mut s = 0\ndo { s += 1 } while s < 3\ns"), 3.0)
        self.assertEqual(value(
            "mut out = []\nfor i in 1..10 {\n  if i % 2 == 0 { continue }\n"
            "  if i > 5 { break }\n  out.push(i)\n}\nout"),
            [1.0, 3.0, 5.0])
        self.assertEqual(value('mut s = ""\nfor k, v in {a: 1, b: 2} { s += "${k}${v}" }\ns'), "a1b2")

    def test_match(self):
        self.assertEqual(value("match 3 { 1 => \"one\", 3 => \"three\", _ => \"other\" }"), "three")
        self.assertEqual(value('match [1, 2, 3] { [a, b, *r] => "${a}${b}${r.len()}" }'), "121")
        self.assertEqual(value('match {a: 5} { {a: n} when n > 3 => "big", _ => "small" }'), "big")
        self.assertEqual(value("match 7 { x is num when x > 5 => \"num!\", _ => \"no\" }"), "num!")
        with self.assertRaises(OmniRuntimeError):
            value("match 9 { 1 => \"x\" }")

    def test_functions(self):
        self.assertEqual(value("fn add(a, b) { a + b }\nadd(2, 3)"), 5.0)
        self.assertEqual(value("fn add(a, b = 10) { a + b }\nadd(1)"), 11.0)
        self.assertEqual(value("fn f(a, b = 2) { a * b }\nf(b: 5, a: 3)"), 15.0)
        self.assertEqual(value("fn f(*xs) { xs.sum() }\nf(1, 2, 3)"), 6.0)
        self.assertEqual(value("fn f(a, **kw) { kw }\nf(1, x: 2).x"), 2.0)
        self.assertEqual(value("let g = (x) -> x * 2\ng(4)"), 8.0)
        self.assertEqual(value("let g = (x) -> { x * 3 }\ng(4)"), 12.0)
        self.assertEqual(value("fn f() { return 5 }\nf()"), 5.0)
        self.assertEqual(value("fn fib(n) { if n < 2 { n } else { fib(n-1) + fib(n-2) } }\nfib(10)"), 55.0)

    def test_closures(self):
        self.assertEqual(value("fn counter() { mut n = 0\nfn bump() { n += 1; n }\nbump }\nlet c = counter()\nc()\nc()\nc()"), 3.0)

    def test_attributes(self):
        self.assertEqual(value("@memo\nfn slow(n) { n * 2 }\nslow(3) + slow(3)"), 12.0)

    def test_try_catch(self):
        self.assertEqual(value('try { error("x") } catch e { e.message }'), "x")
        self.assertEqual(value("try { 1 / 0 } catch e { \"div\" }"), "div")
        self.assertEqual(value("mut done = false\ntry { error(\"a\") } catch e { } finally { done = true }\ndone"), True)
        self.assertEqual(value("try { 5 } catch e { 6 }"), 5.0)

    def test_throw_user_values(self):
        self.assertEqual(value('try { throw "custom" } catch v { v }'), "custom")
        self.assertEqual(value("try { throw {code: 42} } catch v { v.code }"), 42.0)


class ClassTests(unittest.TestCase):
    def test_basic(self):
        src = '''
class Point {
  x = 0
  y = 0
  new(x, y) { self.x = x; self.y = y }
  fn dist() { sqrt(self.x ** 2 + self.y ** 2) }
  fn str() { "(${self.x},${self.y})" }
}
let p = new Point(3, 4)
'''
        self.assertEqual(value(src + "p.dist()"), 5.0)
        self.assertEqual(value(src + "str(p)"), "(3,4)")
        self.assertEqual(value(src + "p.x = 10\np.x"), 10.0)

    def test_inheritance(self):
        src = '''
class Animal {
  name = "?"
  new(name) { self.name = name }
  fn speak() { "..." }
}
class Dog : Animal {
  fn speak() { "woof" }
}
let d = new Dog("rex")
'''
        self.assertEqual(value(src + "d.speak()"), "woof")
        self.assertEqual(value(src + "d.name"), "rex")
        self.assertTrue(value(src + "d is Dog"))
        self.assertTrue(value(src + "d is Animal"))
        self.assertFalse(value(src + "new Animal(\"a\") is Dog"))


class HigherOrderTests(unittest.TestCase):
    def test_callbacks_ignore_extra_args(self):
        self.assertEqual(value("[1,2,3].map((x) -> x * 2)"), [2.0, 4.0, 6.0])
        self.assertEqual(value("[1,2,3].map((x, i) -> x + i)"), [1.0, 3.0, 5.0])

    def test_collection_functions(self):
        self.assertEqual(value("[3,1,2].sort()"), [1.0, 2.0, 3.0])
        self.assertEqual(value("[{n: 3},{n: 1}].sort(\"n\").map((r) -> r.n)"), [1.0, 3.0])
        self.assertEqual(value("[1,2,3,4].filter((x) -> x > 2)"), [3.0, 4.0])
        self.assertEqual(value("[1,2,3].reduce((a, b) -> a * b, 1)"), 6.0)
        self.assertEqual(value("[1,2,3].some((x) -> x == 2)"), True)
        self.assertEqual(value("[1,2,3].every((x) -> x > 0)"), True)
        self.assertEqual(value("[1,2,2,3].unique()"), [1.0, 2.0, 3.0])
        self.assertEqual(value("[1,2,3,4].chunk(2)"), [[1.0, 2.0], [3.0, 4.0]])
        self.assertEqual(value("[1,2].zip([3,4])"), [[1.0, 3.0], [2.0, 4.0]])
        self.assertEqual(value('[{g: "a", v: 1}, {g: "a", v: 2}, {g: "b", v: 3}].group_by("g").keys()'), ["a", "b"])
        self.assertEqual(value("[1,2,3].flat_map((x) -> [x, x])"), [1.0, 1.0, 2.0, 2.0, 3.0, 3.0])

    def test_pipelines(self):
        self.assertEqual(value("[3,1,2] |> sorted |> join(\"-\")"), "1-2-3")
        self.assertEqual(value('"a,b" |> split(",") |> len()'), 2.0)
        self.assertEqual(value("[1,2,3] |> .sum()"), 6.0)
        self.assertEqual(value("[1,2,3] ||> last()"), 3.0)
        self.assertEqual(value("fn add(a, b) { a + b }\n5 |> add(10)"), 15.0)


class BuiltinTests(unittest.TestCase):
    def test_strings(self):
        self.assertEqual(value('"Hello World".upper()'), "HELLO WORLD")
        self.assertEqual(value('"  x  ".trim()'), "x")
        self.assertEqual(value('"a-b-c".split("-")'), ["a", "b", "c"])
        self.assertEqual(value('["a","b"].join(", ")'), "a, b")
        self.assertEqual(value('"abc".reverse()'), "cba")
        self.assertEqual(value('"HelloWorld".snake()'), "hello_world")
        self.assertEqual(value('"hello_world".camel()'), "helloWorld")
        self.assertEqual(value('"x".repeat(3)'), "xxx")
        self.assertEqual(value('"abc".contains("b")'), True)

    def test_math(self):
        self.assertEqual(value("abs(-5)"), 5.0)
        self.assertEqual(value("sqrt(16)"), 4.0)
        self.assertEqual(value("floor(2.9)"), 2.0)
        self.assertEqual(value("ceil(2.1)"), 3.0)
        self.assertEqual(value("round(2.5)"), 2.0)
        self.assertEqual(value("clamp(15, 0, 10)"), 10.0)
        self.assertEqual(value("min([4,2,9])"), 2.0)
        self.assertEqual(value("max(1, 7, 3)"), 7.0)
        self.assertEqual(value("sum([1,2,3])"), 6.0)
        self.assertEqual(value("avg([2,4])"), 3.0)
        self.assertAlmostEqual(value("round_to(pi, 3)"), 3.142)

    def test_json(self):
        self.assertEqual(value('json(\'{"a": [1, 2]}\').a[1]'), 2.0)
        self.assertEqual(value('to_json({a: 1})'), '{"a": 1}')
        self.assertEqual(value('[1, "x", null].to_json()'), '[1, "x", null]')

    def test_csv(self):
        csv = '"name,age\\nalice,30\\nbob,25\\n"'
        self.assertEqual(value(f"read_csv(text: {csv}).len()"), 2.0)
        self.assertEqual(value(f"read_csv(text: {csv})[0].name"), "alice")
        self.assertEqual(value(f"read_csv(text: {csv}).map((r) -> r.age).sum()"), 55.0)

    def test_regex(self):
        self.assertEqual(value('regex("2026-09-15", r"(\\d+)-(\\d+)-(\\d+)")[1]'), "2026")
        self.assertEqual(value('regex_all("a1 b22 c333", r"\\d+")'), ["1", "22", "333"])
        self.assertTrue(value('regex_test("hello", r"^h")'))
        self.assertEqual(value('regex_replace("a  b", r"\\s+", "-")'), "a-b")

    def test_formatting(self):
        self.assertEqual(value('format("hi {} and {}", "a", "b")'), "hi a and b")
        self.assertEqual(value('(1234.567).format(",.2f")'), "1,234.57")
        self.assertEqual(value('(3).ordinal()'), "3rd")
        self.assertEqual(value('(21).ordinal()'), "21st")

    def test_table_output(self):
        _, out, _ = run('table([{a: 1, b: "x"}, {a: 2, b: "yy"}])')
        self.assertIn("a", out)
        self.assertIn("yy", out)
        self.assertIn("---", out)


class ErrorQualityTests(unittest.TestCase):
    def check(self, src, kind, *snippets):
        with self.assertRaises(kind) as ctx:
            run(src)
        err = ctx.exception
        text = err.render()
        for s in snippets:
            self.assertIn(s, text, f"expected {s!r} in:\n{text}")

    def test_undefined_name_suggests(self):
        self.check("let counter = 1\nprint(counterr)", OmniNameError,
                   "did you mean `counter`?")

    def test_type_error_shows_source(self):
        self.check('let x = "abc"\nx - 1', OmniTypeError, "x - 1", "needs numbers")

    def test_division_by_zero(self):
        self.check("1 / 0", OmniRuntimeError, "division by zero")

    def test_index_out_of_range(self):
        self.check("[1,2][9]", OmniRuntimeError, "out of range")

    def test_missing_argument(self):
        self.check("fn f(a, b) { a }\nf(1)", OmniRuntimeError, "missing its `b` argument")

    def test_unknown_member_suggests(self):
        self.check('"abc".uppe()', OmniTypeError, "did you mean `upper`?")

    def test_let_reassignment_explains(self):
        self.check("let x = 1\nx = 2", OmniRuntimeError, "declared with `let`", "mut x")

    def test_syntax_error_points(self):
        self.check("let x = (1 +", OmniSyntaxError, "end of input")

    def test_unmatched_brace(self):
        self.check("fn f() {\n  1\n", OmniSyntaxError, "missing its closing `}`")

    def test_match_exhaustiveness(self):
        self.check("match 5 { 1 => \"a\" }", OmniRuntimeError, "no match arm fits")


class GraphicsTests(unittest.TestCase):
    def test_canvas_basics(self):
        r, out, interp = run('''
let c = draw(20, 10, bg: "white")
c.pixel(0, 0, "#ff0000")
c.at(0, 0)
''')
        self.assertEqual(r, [255.0, 0.0, 0.0, 255.0])

    def test_png_is_valid(self):
        import struct
        import zlib
        r, out, interp = run('''
let c = draw(8, 8)
c.rect(0, 0, 8, 8, "#ff0000")
c.to_base64()
''')
        import base64
        data = base64.b64decode(r)
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn(b"IHDR", data)
        self.assertIn(b"IEND", data)

    def test_colors(self):
        self.assertEqual(value('rgb(255, 0, 0)'), [255.0, 0.0, 0.0, 255.0])
        self.assertEqual(value('hsl(0, 1, 0.5)'), [255.0, 0.0, 0.0, 255.0])
        self.assertEqual(value('mix_colors("black", "white", 0.5)'),
                         [127.0, 127.0, 127.0, 255.0])

    def test_chart_runs(self):
        r, out, _ = run('let c = chart([1,2,3], kind: "bar", width: 60, height: 40)\nc.w')
        self.assertEqual(r, 60.0)


class SystemTests(unittest.TestCase):
    def test_cmd(self):
        self.assertEqual(value('cmd("echo hi").trim()'), "hi")
        self.assertEqual(value('cmd("echo hi").ok'), True)
        self.assertEqual(value('cmd("false").ok'), False)
        self.assertEqual(value('cmd("printf \\"a\\\\nb\\\\n\\"").lines()'), ["a", "b"])

    def test_paths_and_files(self, ):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.txt")
            r, _, _ = run(f'''
write("{p}", "line1\\nline2")
read_lines("{p}")
''')
            self.assertEqual(r, ["line1", "line2"])
            self.assertTrue(value(f'exists("{p}")'))
            self.assertEqual(value(f'file_info("{p}").ext'), "txt")

    def test_path_helpers(self):
        self.assertEqual(value('path_join("a", "b.txt")'), os.path.join("a", "b.txt"))
        self.assertEqual(value('path_ext("a/b.txt")'), "txt")
        self.assertEqual(value('path_stem("a/b.txt")'), "b")


class ConcurrencyTests(unittest.TestCase):
    def test_parallel(self):
        r, _, _ = run('''
parallel([(x) -> x * 2, (x) -> x + 1].map((f) -> () -> f(10)))
''')
        self.assertEqual(r, [20.0, 11.0])

    def test_parallel_map(self):
        r, _, _ = run("parallel_map([1,2,3], (x) -> x * 10)")
        self.assertEqual(r, [10.0, 20.0, 30.0])

    def test_spawn(self):
        r, _, _ = run("spawn(() -> 42).get()")
        self.assertEqual(r, 42.0)


class ModuleTests(unittest.TestCase):
    def test_use(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            mod = os.path.join(d, "maths.omni")
            with open(mod, "w") as fh:
                fh.write("fn double(x) { x * 2 }\nlet secret = 7\n")
            main = os.path.join(d, "main.omni")
            with open(main, "w") as fh:
                fh.write('use "./maths.omni"\ndouble(secret)\n')
            out = []
            interp = make_interpreter(writer=out.append, root=d)
            with open(main) as fh:
                result = interp.run_source(fh.read(), main)
            self.assertEqual(result, 14.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class NewSyntaxTests(unittest.TestCase):
    """Features added while writing the examples and the reference docs."""

    def test_triple_quoted_strings(self):
        self.assertEqual(value('"""\na\nb\n"""'), "\na\nb\n")
        self.assertEqual(value("'''\nx\n'''"), "\nx\n")
        self.assertEqual(value('"""hi ${1 + 1}"""'), "hi 2")

    def test_raw_strings(self):
        self.assertEqual(value(r'r"\d+"'), r"\d+")
        self.assertEqual(value(r"r'a\b'"), r"a\b")
        self.assertEqual(value(r'r"no ${interp}"'), "no ${interp}")

    def test_open_slices(self):
        self.assertEqual(value('"hello"[..2]'), "he")
        self.assertEqual(value('"hello"[2..]'), "llo")
        self.assertEqual(value("[1,2,3][..2]"), [1.0, 2.0])
        self.assertEqual(value("[1,2,3][::-1]"), [3.0, 2.0, 1.0])
        self.assertEqual(value("[1,2,3][..=1]"), [1.0, 2.0])

    def test_range_bounds_use_arithmetic(self):
        self.assertEqual(value("let xs = [1,2,3,4]\n[0..xs.len() - 1]"),
                         [0.0, 1.0, 2.0])
        self.assertEqual(value("[2 * 2..8]"), [4.0, 5.0, 6.0, 7.0])
        self.assertEqual(value("2 + 3 * 4"), 14.0)

    def test_map_spread_with_double_star(self):
        self.assertEqual(value("{a: 1, **{b: 2}}.b"), 2.0)
        self.assertEqual(value("{a: 1, *{a: 9}}.a"), 9.0)

    def test_sort_accepts_a_comparator(self):
        self.assertEqual(value("[3,1,2].sort((a, b) -> a - b)"), [1.0, 2.0, 3.0])
        self.assertEqual(value("sorted([3,1,2], (a, b) -> b - a)"), [3.0, 2.0, 1.0])
        self.assertEqual(value('["bb","a","ccc"].sort((a, b) -> len(a) - len(b))'),
                         ["a", "bb", "ccc"])

    def test_for_with_index(self):
        self.assertEqual(value('let out = []\nfor i, ch in "ab" { out.push("${i}${ch}") }\nout'),
                         ["0a", "1b"])

    def test_method_and_function_agree(self):
        self.assertEqual(value("[1,2,3].map_each((x, i) -> x + i)"), [1.0, 3.0, 5.0])
        self.assertEqual(value('["a","b","a"].counts()'), {"a": 2.0, "b": 1.0})
        self.assertEqual(value("{a: 1, b: 2}.pick('a')"), {"a": 1.0})

    def test_try_as_an_expression(self):
        self.assertEqual(value('let m = try { error("x") } catch e { e.message }\nm'), "x")

    def test_super_calls_the_parent_method(self):
        src = """
        class A { fn name() { "a" } }
        class B : A { fn name() { super.name() + "b" } }
        new B().name()
        """
        self.assertEqual(value(src), "ab")

    def test_modules_load(self):
        interp = make_interpreter(writer=lambda *_: None, quiet=True)
        interp.run_source("use std/math", "<test>")
        self.assertEqual(interp.run_source("factorial(5)", "<test>"), 120.0)
        self.assertTrue(interp.run_source("is_prime(29)", "<test>"))

    def test_assert_builtins(self):
        self.assertTrue(value("assert_eq(1 + 1, 2)"))
        with self.assertRaises(Exception):
            run("assert_eq(1, 2)")
        self.assertTrue(value("assert_throws(() -> error('x'))"))


class HardeningTests(unittest.TestCase):
    """Edge cases found by the torture script."""

    def test_optional_call_on_a_missing_key(self):
        self.assertIsNone(value("let m = {a: 1}\nm?.missing()"))
        self.assertEqual(value('let m = {a: 1}\nm?.missing() ?? "none"'), "none")
        with self.assertRaises(Exception):
            run("let m = {a: 1}\nm.missing()")

    def test_flatten_depth(self):
        self.assertEqual(value("[1,[2,[3,[4]]]].flatten()"), [1.0, 2.0, [3.0, [4.0]]])
        self.assertEqual(value("[1,[2,[3,[4]]]].flatten(depth: -1)"),
                         [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(value("flatten([1,[2,[3]]], depth: 2)"), [1.0, 2.0, 3.0])

    def test_regex_replacement_groups(self):
        self.assertEqual(value(r'regex_replace("2026-09-15", r"(\d+)-(\d+)-(\d+)", "$3/$2/$1")'),
                         "15/09/2026")
        self.assertEqual(value(r'regex_replace("2026-09-15", r"(\d+)-(\d+)-(\d+)", "\\3")'),
                         "15")
        self.assertEqual(
            value(r'regex_replace("ada lovelace", r"(?P<f>\w+) (?P<l>\w+)", "\${l}, \${f}")'),
            "lovelace, ada")
        self.assertEqual(value(r'regex_replace("a b c", r" ", "_", count: 1)'), "a_b c")

    def test_regex_all_groups(self):
        self.assertEqual(value(r'regex_all("a1 b22", r"([a-z])(\d+)", groups: true)'),
                         [["a", "1"], ["b", "22"]])

    def test_escaped_dollar_is_literal(self):
        self.assertEqual(value(r'print_me = "\${x}"'), "${x}")
        self.assertEqual(value('let x = 1\n"${x}"'), "1")

    def test_new_then_method_chain(self):
        src = """
        class P { x = 0; y = 0
          new(x, y) { self.x = x; self.y = y }
          fn sum() { self.x + self.y } }
        new P(2, 3).sum()
        """
        self.assertEqual(value(src), 5.0)

    def test_protocol_hooks(self):
        src = """
        class Bag {
          items = []
          new(*xs) { self.items = list(xs) }
          fn len() { self.items.len() }
          fn iter() { self.items }
          fn eq(other) { self.items == other.items }
          fn str() { "Bag(${self.items.len()})" }
        }
        let b = new Bag(1, 2, 3)
        mut total = 0
        for x in b { total += x }
        [str(b), len(b), b == new Bag(1, 2, 3), total]
        """
        self.assertEqual(value(src), ["Bag(3)", 3.0, True, 6.0])

    def test_closures_capture_per_iteration(self):
        src = "let fns = []\nfor i in 1..=3 { fns.push(() -> i) }\nfns.map((f) -> f())"
        self.assertEqual(value(src), [1.0, 2.0, 3.0])

    def test_try_inside_map(self):
        src = 'let safe = (a, b) -> try { a / b } catch e { "err" }\n' \
              '[1, 0, 2].map((x) -> safe(10, x))'
        self.assertEqual(value(src), [10.0, "err", 5.0])
