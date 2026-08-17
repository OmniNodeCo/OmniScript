from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omniscript.api import OmniEngine
from omniscript.errors import OmniCheckError, OmniRuntimeError


class RuntimeTests(unittest.TestCase):
    def run_source(self, source: str):
        engine = OmniEngine()
        result = engine.run(source)
        return result, engine

    def test_functions_closures_ranges_and_pipelines(self) -> None:
        source = """
craft sum(values) {
    bind total := 0
    each value in values { total <- total + value }
    return total
}
bind values := 1..5
emit values |> sum |> text
"""
        result, _engine = self.run_source(source)
        self.assertEqual(result.output, ["15"])

    def test_shapes_maps_and_mutation(self) -> None:
        source = """
shape Counter(value := 0) {
    craft next() {
        self.value <- self.value + 1
        return self.value
    }
}
bind counter := Counter()
bind metadata := {name: "visits"}
metadata.count <- counter.next()
metadata["count"] <- counter.next()
emit metadata.name, metadata.count
"""
        result, _engine = self.run_source(source)
        self.assertEqual(result.output, ["visits 2"])

    def test_control_flow_and_default_parameters(self) -> None:
        source = """
craft label(value, prefix := "item") { return prefix + ":" + text(value) }
bind found := []
each value in 1..8 {
    when value % 2 == 0 { continue }
    push(found, label(value))
    when len(found) == 3 { break }
}
assert found == ["item:1", "item:3", "item:5"]
"""
        result, _engine = self.run_source(source)
        self.assertIsNone(result.value)

    def test_builtin_modules(self) -> None:
        source = """
use "math"
use "text" as words
assert math.sqrt(81) == 9
assert words.upper("omni") == "OMNI"
"""
        self.run_source(source)

    def test_file_module(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tools.omni").write_text(
                "craft triple(value) { return value * 3 }\nseal title := 'Tools'\n",
                encoding="utf-8",
            )
            main = root / "main.omni"
            main.write_text('use "./tools" as tools\nemit tools.title, tools.triple(7)\n', encoding="utf-8")
            result = OmniEngine().run_file(main)
            self.assertEqual(result.output, ["Tools 21"])

    def test_nested_craft_closure(self) -> None:
        source = """
craft make_adder(amount) {
    craft add(value) { return value + amount }
    return add
}
seal add_two := make_adder(2)
assert add_two(40) == 42
"""
        self.run_source(source)

    def test_seal_is_enforced_by_checker(self) -> None:
        with self.assertRaises(OmniCheckError):
            self.run_source("seal answer := 42\nanswer <- 0\n")

    def test_shape_fields_require_self_inside_methods(self) -> None:
        source = "shape Box(value) { craft open() { return value } }"
        with self.assertRaises(OmniCheckError):
            self.run_source(source)

    def test_unchecked_top_level_control_flow_is_still_diagnosed(self) -> None:
        with self.assertRaises(OmniRuntimeError) as caught:
            OmniEngine().run("return 3", check=False)
        self.assertIn("inside a craft", caught.exception.message)

    def test_assertion_has_runtime_diagnostic(self) -> None:
        with self.assertRaises(OmniRuntimeError) as caught:
            self.run_source('assert false, "not okay"')
        self.assertEqual(caught.exception.message, "not okay")


if __name__ == "__main__":
    unittest.main()
