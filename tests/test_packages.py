from __future__ import annotations

import unittest
from unittest.mock import patch

from omniscript.api import OmniEngine


class FakeHeaders:
    def get(self, name, default=None):
        return "application/json; charset=utf-8" if name.lower() == "content-type" else default

    def get_content_charset(self):
        return "utf-8"

    def items(self):
        return [("Content-Type", "application/json; charset=utf-8")]


class FakeHttpResponse:
    status = 200
    headers = FakeHeaders()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"project":"OmniScript","ready":true}'


class PackageTests(unittest.TestCase):
    def test_data_csv_crypto_date_and_system_packages(self) -> None:
        source = r'''
use "data"
use "csv" as table
use "crypto"
use "date"
use "system"

assert data.unique([1, 1, 2, 3, 2]) == [1, 2, 3]
assert data.flatten([1, [2, [3]]]) == [1, 2, 3]
assert data.chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
assert data.sum([1, 2, 3]) == 6
assert data.average([2, 4, 6]) == 4

seal people := table.parse("name,score\nAda,10\nLin,8\n")
assert people[0].name == "Ada"
assert people[1].score == "8"
assert "name,score" in table.stringify(people)

assert crypto.sha256("hello") == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
assert crypto.base64_decode(crypto.base64_encode("Omni")) == "Omni"
assert len(crypto.token(24)) == 24
assert len(crypto.uuid()) == 36

seal timestamp := date.parse("2026-08-17", "%Y-%m-%d")
assert date.format(timestamp, "%Y-%m-%d") == "2026-08-17"
assert "1970-01-01" in date.iso(0)

system.set_env("OMNISCRIPT_PACKAGE_TEST", "works")
assert system.env("OMNISCRIPT_PACKAGE_TEST") == "works"
assert kind(system.info()) == "map"
'''
        OmniEngine().run(source)

    def test_http_package_returns_simple_maps_and_json(self) -> None:
        source = '''
use "http"
seal response := http.get("https://example.test/api")
assert response.status == 200
assert response.ok
assert "OmniScript" in response.body
seal payload := http.json("https://example.test/api")
assert payload.project == "OmniScript"
assert payload.ready
'''
        with patch("omniscript.packages.urlopen", return_value=FakeHttpResponse()) as request:
            OmniEngine().run(source)
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
