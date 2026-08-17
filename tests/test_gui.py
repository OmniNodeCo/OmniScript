from __future__ import annotations

import unittest
from unittest.mock import patch

from omniscript.api import OmniEngine


class FakeVariable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeWidget:
    def __init__(self, *_args, **kwargs):
        self.state = "normal"
        self.command = kwargs.get("command")

    def pack(self, **_kwargs):
        return None

    def configure(self, **kwargs):
        self.state = kwargs.get("state", self.state)

    def focus_set(self):
        return None


class FakeText(FakeWidget):
    def __init__(self, *_args, **kwargs):
        super().__init__(*_args, **kwargs)
        self.value = ""

    def insert(self, _start, value):
        self.value = str(value)

    def delete(self, _start, _end):
        self.value = ""

    def get(self, _start, _end):
        return self.value


class FakeRoot(FakeWidget):
    def title(self, _value):
        return None

    def geometry(self, _value):
        return None

    def minsize(self, _width, _height):
        return None

    def mainloop(self):
        return None

    def destroy(self):
        return None

    def after_idle(self, action):
        action()

    def quit(self):
        return None


class FakeTk:
    Tk = FakeRoot
    StringVar = FakeVariable
    BooleanVar = FakeVariable
    Text = FakeText


class FakeTtk:
    Frame = FakeWidget
    Label = FakeWidget
    Entry = FakeWidget
    Button = FakeWidget
    Checkbutton = FakeWidget


class FakeMessageBox:
    @staticmethod
    def showinfo(*_args, **_kwargs):
        return None

    @staticmethod
    def showerror(*_args, **_kwargs):
        return None

    @staticmethod
    def askyesno(*_args, **_kwargs):
        return True


class GuiTests(unittest.TestCase):
    def test_simple_gui_api_without_a_real_display(self) -> None:
        source = """
use "gui"
seal window := gui.window("Test", 400, 240)
seal label := window.label("Name")
seal name := window.input("Ada")
seal accepted := window.checkbox("Ready", true)
seal notes := window.textbox("Hello", 5)
craft save() { return notes.get() }
seal save_button := window.button("Save", save)
assert name.get() == "Ada"
name.set("Lin")
assert name.get() == "Lin"
assert accepted.get()
assert notes.get() == "Hello"
label.disable()
label.enable()
name.focus()
window.space(10)
assert window.confirm("Question", "Continue?")
window.message("Done", "Saved")
window.run()
"""
        with patch("omniscript.gui._load_toolkit", return_value=(FakeTk, FakeTtk, FakeMessageBox)):
            OmniEngine().run(source)


if __name__ == "__main__":
    unittest.main()
